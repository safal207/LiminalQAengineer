//! File-first CGQA interop commands. These paths deliberately do not open LIMINAL-DB.

use anyhow::{anyhow, Context, Result};
use liminalqa_core::cgqa_interop::{
    export_candidates, import_receipt, CgqaEvidenceExport,
};
use serde::Serialize;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Component, Path, PathBuf};

fn reject_parent_traversal(path: &Path, label: &str) -> Result<()> {
    if path
        .components()
        .any(|component| component == Component::ParentDir)
    {
        return Err(anyhow!("{label} must not contain parent-directory traversal"));
    }
    Ok(())
}

fn read_input(path: &Path) -> Result<(PathBuf, Vec<u8>)> {
    reject_parent_traversal(path, "input")?;
    let metadata = fs::symlink_metadata(path)
        .with_context(|| format!("failed to inspect input {}", path.display()))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(anyhow!("input must be a regular non-symlink file"));
    }
    let canonical = fs::canonicalize(path)
        .with_context(|| format!("failed to resolve input {}", path.display()))?;
    let bytes = fs::read(&canonical)
        .with_context(|| format!("failed to read input {}", canonical.display()))?;
    Ok((canonical, bytes))
}

fn prepare_output(path: &Path, input: &Path, force: bool) -> Result<PathBuf> {
    reject_parent_traversal(path, "output")?;
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    if absolute == input {
        return Err(anyhow!("output must be distinct from input"));
    }
    if absolute.exists() {
        let metadata = fs::symlink_metadata(&absolute)?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(anyhow!("output must be a regular non-symlink file"));
        }
        if fs::canonicalize(&absolute)? == input {
            return Err(anyhow!("output must be distinct from input"));
        }
        if !force {
            return Err(anyhow!(
                "output already exists: {}; use --force to replace it",
                absolute.display()
            ));
        }
    }
    Ok(absolute)
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| anyhow!("output must have a parent directory"))?;
    fs::create_dir_all(parent)?;
    let temporary = parent.join(format!(
        ".{}.{}.tmp",
        path.file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("liminal-interop"),
        std::process::id()
    ));
    let result = (|| -> Result<()> {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temporary)
            .with_context(|| format!("failed to create {}", temporary.display()))?;
        let mut payload = serde_json::to_vec_pretty(value)?;
        payload.push(b'\n');
        file.write_all(&payload)?;
        file.sync_all()?;
        fs::rename(&temporary, path)
            .with_context(|| format!("failed to publish {}", path.display()))?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

pub fn execute_import(input: &Path, output: &Path, force: bool) -> Result<()> {
    let (input_path, source_bytes) = read_input(input)?;
    let evidence = CgqaEvidenceExport::from_json(&source_bytes)?;
    let output_path = prepare_output(output, &input_path, force)?;
    let receipt = import_receipt(&evidence, &source_bytes)?;
    write_json(&output_path, &receipt)?;
    println!("{}", output_path.display());
    Ok(())
}

pub fn execute_candidate_export(
    input: &Path,
    output: &Path,
    derived_at: &str,
    operation_id: &str,
    attempt_id: &str,
    force: bool,
) -> Result<()> {
    let (input_path, source_bytes) = read_input(input)?;
    let evidence = CgqaEvidenceExport::from_json(&source_bytes)?;
    let output_path = prepare_output(output, &input_path, force)?;
    let candidates = export_candidates(
        &evidence,
        &source_bytes,
        derived_at,
        operation_id,
        attempt_id,
    )?;
    write_json(&output_path, &candidates)?;
    println!("{}", output_path.display());
    Ok(())
}
