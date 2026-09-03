//! Offline execution of the pinned CGQA/LiminalQA conformance vectors.

use anyhow::{anyhow, Result};
use liminalqa_core::cgqa_conformance::run_cgqa_conformance_suite;
use std::path::Path;

pub fn execute(suite: Option<&Path>) -> Result<()> {
    let report = run_cgqa_conformance_suite(suite)?;
    println!("{}", serde_json::to_string(&report)?);
    if report["status"] != "PASS" {
        return Err(anyhow!("one or more CGQA conformance vectors failed"));
    }
    Ok(())
}
