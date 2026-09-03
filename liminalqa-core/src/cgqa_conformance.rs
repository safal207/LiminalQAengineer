//! Native runner for the pinned ContractGraph-QA/LiminalQA conformance suite.
//!
//! The runner validates local bytes only. It does not open LIMINAL-DB, make a
//! network request, execute a candidate, or authorize a target-system action.

use crate::cgqa_interop::{
    sha256_hex, CgqaCandidateExport, CgqaEvidenceExport, CGQA_EVIDENCE_PROFILE,
    CGQA_EVIDENCE_SCHEMA, LIMINAL_CANDIDATE_PROFILE, LIMINAL_CANDIDATE_SCHEMA,
};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::{Component, Path, PathBuf};
use thiserror::Error;

pub const SUITE_SCHEMA: &str = "org.contractgraph-qa.liminalqa-interop-conformance-suite.v0.1";
pub const RESULT_SCHEMA: &str = "org.contractgraph-qa.liminalqa-interop-conformance-result.v0.1";
pub const SUITE_ID: &str = "cgqa-liminalqa-v0.1";
pub const SUITE_VERSION: &str = "0.1.0";
pub const SUITE_SHA256: &str = "562e2f9ae699f001b9ccf1b2b9f6dd30c435d53d668b5fd9a04ca15ca1e4faac";
pub const SUITE_SCHEMA_SHA256: &str =
    "34acfc677802683c6c452a728ed533e92803a74d989b397d2d0fe549b1da93f9";
pub const RESULT_SCHEMA_SHA256: &str =
    "388d0aadbb8d30fb5aee223a89f29884b89a1b3303ac88dae8b21e91ab11b423";
pub const VALID_NON_AUTHORIZING: &str = "VALID_NON_AUTHORIZING";
pub const INVALID_BLOCKED: &str = "INVALID_BLOCKED";
pub const UNSAFE_ACCEPTED: &str = "UNSAFE_ACCEPTED";
pub const CLAIM_BOUNDARY: &str = "Synthetic conformance verifies adapter behavior only for these pinned fixtures and mutations. It does not verify a production system, prove security or completeness, authorize an action, or replace independent replay against the exact subject.";

const CGQA_SCHEMA_SHA256: &str = "53b0b4a0b1f4d77de26b8be9dbb90006ea0bd30c5cd3960a2f3e7d44d9664184";
const CGQA_FIXTURE_SHA256: &str =
    "e1d5a14c5c1b75e2cfffaf87bf526fd61e141a0c5b7828de4f275e9792fda3ce";
const LIMINAL_SCHEMA_SHA256: &str =
    "896e32921d41925a976fef5d0ba561a08bd1f2265a08bc9ccf5065a3238a4f60";
const LIMINAL_FIXTURE_SHA256: &str =
    "60b794934959c30f9957d0e54de83d7760ac38b618b0676603d721daa8ef11d3";

#[derive(Debug, Error)]
pub enum CgqaConformanceError {
    #[error("invalid CGQA conformance suite: {0}")]
    Invalid(String),
    #[error("CGQA conformance I/O error: {0}")]
    Io(#[from] std::io::Error),
    #[error("invalid CGQA conformance JSON: {0}")]
    Json(#[from] serde_json::Error),
}

fn invalid(message: impl Into<String>) -> CgqaConformanceError {
    CgqaConformanceError::Invalid(message.into())
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct PinnedPath {
    path: String,
    sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Contract {
    id: String,
    artifact_schema: String,
    artifact_profile: String,
    owner_repository: String,
    producer_commit: String,
    schema_path: String,
    schema_sha256: String,
    fixture_path: String,
    fixture_sha256: String,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
enum Operation {
    Identity,
    Replace { pointer: String, value: Value },
    Add { pointer: String, value: Value },
    Remove { pointer: String },
    DuplicateRootKey { key: String, value: Value },
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Case {
    id: String,
    contract: String,
    category: String,
    description: String,
    operation: Operation,
    expected_input_sha256: String,
    expected_semantics: String,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct Suite {
    schema: String,
    suite_id: String,
    version: String,
    suite_schema: PinnedPath,
    result_schema: PinnedPath,
    contracts: Vec<Contract>,
    cases: Vec<Case>,
    claim_boundary: String,
}

enum AssetSource {
    Embedded,
    External(PathBuf),
}

impl AssetSource {
    fn read(&self, relative: &str) -> Result<Vec<u8>, CgqaConformanceError> {
        match self {
            Self::Embedded => embedded_asset(relative)
                .map(|bytes| bytes.to_vec())
                .ok_or_else(|| invalid(format!("unsupported embedded suite asset: {relative}"))),
            Self::External(root) => read_external_asset(root, relative),
        }
    }
}

struct LoadedSuite {
    suite: Suite,
    suite_raw: Vec<u8>,
    fixtures: BTreeMap<String, Vec<u8>>,
}

fn embedded_asset(relative: &str) -> Option<&'static [u8]> {
    match relative {
        "suite.json" => Some(include_bytes!(
            "../../conformance/cgqa-liminalqa-v0.1/suite.json"
        )),
        "suite.schema.json" => Some(include_bytes!(
            "../../conformance/cgqa-liminalqa-v0.1/suite.schema.json"
        )),
        "result.schema.json" => Some(include_bytes!(
            "../../conformance/cgqa-liminalqa-v0.1/result.schema.json"
        )),
        "schemas/cgqa-liminalqa-evidence-v0.1.schema.json" => Some(include_bytes!(
            "../../conformance/cgqa-liminalqa-v0.1/schemas/cgqa-liminalqa-evidence-v0.1.schema.json"
        )),
        "schemas/liminalqa-cgqa-candidates-v0.1.schema.json" => Some(include_bytes!(
            "../../conformance/cgqa-liminalqa-v0.1/schemas/liminalqa-cgqa-candidates-v0.1.schema.json"
        )),
        "fixtures/cgqa-liminalqa-evidence-v0.1.json" => Some(include_bytes!(
            "../../conformance/cgqa-liminalqa-v0.1/fixtures/cgqa-liminalqa-evidence-v0.1.json"
        )),
        "fixtures/liminalqa-cgqa-candidates-v0.1.json" => Some(include_bytes!(
            "../../conformance/cgqa-liminalqa-v0.1/fixtures/liminalqa-cgqa-candidates-v0.1.json"
        )),
        _ => None,
    }
}

fn safe_relative_path(value: &str) -> Result<&Path, CgqaConformanceError> {
    let path = Path::new(value);
    if path.is_absolute()
        || path.extension().and_then(|extension| extension.to_str()) != Some("json")
        || path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(invalid(format!(
            "suite asset path must be a traversal-free relative JSON path: {value}"
        )));
    }
    Ok(path)
}

fn read_external_asset(root: &Path, relative: &str) -> Result<Vec<u8>, CgqaConformanceError> {
    let relative_path = safe_relative_path(relative)?;
    let candidate = root.join(relative_path);
    let metadata = fs::symlink_metadata(&candidate)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(invalid(format!(
            "suite asset must be a regular non-symlink file: {relative}"
        )));
    }
    let resolved = fs::canonicalize(&candidate)?;
    if !resolved.starts_with(root) {
        return Err(invalid(format!(
            "suite asset escapes suite root: {relative}"
        )));
    }
    Ok(fs::read(resolved)?)
}

fn load_suite(path: Option<&Path>) -> Result<LoadedSuite, CgqaConformanceError> {
    let (source, suite_raw) = match path {
        None => (
            AssetSource::Embedded,
            embedded_asset("suite.json")
                .expect("embedded v0.1 suite must exist")
                .to_vec(),
        ),
        Some(path) => {
            if path
                .components()
                .any(|component| component == Component::ParentDir)
            {
                return Err(invalid("suite path must not contain parent traversal"));
            }
            let metadata = fs::symlink_metadata(path)?;
            if metadata.file_type().is_symlink() || !metadata.is_file() {
                return Err(invalid("suite must be a regular non-symlink file"));
            }
            let resolved = fs::canonicalize(path)?;
            let root = resolved
                .parent()
                .ok_or_else(|| invalid("suite must have a parent directory"))?
                .to_path_buf();
            (AssetSource::External(root), fs::read(resolved)?)
        }
    };

    if sha256_hex(&suite_raw) != SUITE_SHA256 {
        return Err(invalid("suite digest does not match the v0.1 pin"));
    }
    let suite: Suite = serde_json::from_slice(&suite_raw)?;
    validate_suite(&suite)?;

    let suite_schema = source.read(&suite.suite_schema.path)?;
    if sha256_hex(&suite_schema) != suite.suite_schema.sha256 {
        return Err(invalid("suite schema digest mismatch"));
    }
    serde_json::from_slice::<Value>(&suite_schema)?;

    let result_schema = source.read(&suite.result_schema.path)?;
    if sha256_hex(&result_schema) != suite.result_schema.sha256 {
        return Err(invalid("result schema digest mismatch"));
    }
    serde_json::from_slice::<Value>(&result_schema)?;

    let mut fixtures = BTreeMap::new();
    for contract in &suite.contracts {
        let schema_raw = source.read(&contract.schema_path)?;
        if sha256_hex(&schema_raw) != contract.schema_sha256 {
            return Err(invalid(format!(
                "contract {} schema digest mismatch",
                contract.id
            )));
        }
        serde_json::from_slice::<Value>(&schema_raw)?;

        let fixture_raw = source.read(&contract.fixture_path)?;
        if sha256_hex(&fixture_raw) != contract.fixture_sha256 {
            return Err(invalid(format!(
                "contract {} fixture digest mismatch",
                contract.id
            )));
        }
        let fixture: Value = serde_json::from_slice(&fixture_raw)?;
        if fixture.get("schema").and_then(Value::as_str) != Some(contract.artifact_schema.as_str())
            || fixture.get("profile").and_then(Value::as_str)
                != Some(contract.artifact_profile.as_str())
        {
            return Err(invalid(format!(
                "contract {} fixture identity mismatch",
                contract.id
            )));
        }
        fixtures.insert(contract.id.clone(), fixture_raw);
    }

    Ok(LoadedSuite {
        suite,
        suite_raw,
        fixtures,
    })
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn safe_id(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    value.len() <= 200
        && first.is_ascii_alphanumeric()
        && chars.all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '.' | '_' | ':' | '-')
        })
}

fn validate_suite(suite: &Suite) -> Result<(), CgqaConformanceError> {
    if suite.schema != SUITE_SCHEMA
        || suite.suite_id != SUITE_ID
        || suite.version != SUITE_VERSION
        || suite.claim_boundary != CLAIM_BOUNDARY
    {
        return Err(invalid("suite identity or claim boundary is unsupported"));
    }
    if suite.suite_schema.path != "suite.schema.json"
        || suite.suite_schema.sha256 != SUITE_SCHEMA_SHA256
        || suite.result_schema.path != "result.schema.json"
        || suite.result_schema.sha256 != RESULT_SCHEMA_SHA256
    {
        return Err(invalid("suite schema pins are unsupported"));
    }
    if suite.contracts.len() != 2 || suite.cases.len() != 14 {
        return Err(invalid(
            "v0.1 suite must contain two contracts and 14 cases",
        ));
    }

    let mut contract_ids = HashSet::new();
    for contract in &suite.contracts {
        if !safe_id(&contract.id)
            || !valid_sha256(&contract.schema_sha256)
            || !valid_sha256(&contract.fixture_sha256)
            || contract.producer_commit.len() != 40
            || !contract
                .producer_commit
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            || !contract_ids.insert(contract.id.as_str())
        {
            return Err(invalid(
                "suite contains an invalid or duplicate contract pin",
            ));
        }
        let expected = match contract.id.as_str() {
            "cgqa-evidence" => (
                CGQA_EVIDENCE_SCHEMA,
                CGQA_EVIDENCE_PROFILE,
                "safal207/ContractGraph-QA",
                "bdf7ced074e3a7baf57cf89ac68be9674bd76a02",
                CGQA_SCHEMA_SHA256,
                CGQA_FIXTURE_SHA256,
            ),
            "liminal-candidates" => (
                LIMINAL_CANDIDATE_SCHEMA,
                LIMINAL_CANDIDATE_PROFILE,
                "safal207/LiminalQAengineer",
                "db9c85f678aafd6e28487e0679a9fb6c3ebfb0c3",
                LIMINAL_SCHEMA_SHA256,
                LIMINAL_FIXTURE_SHA256,
            ),
            _ => return Err(invalid("suite contains an unsupported contract")),
        };
        if contract.artifact_schema != expected.0
            || contract.artifact_profile != expected.1
            || contract.owner_repository != expected.2
            || contract.producer_commit != expected.3
            || contract.schema_sha256 != expected.4
            || contract.fixture_sha256 != expected.5
        {
            return Err(invalid(format!(
                "contract {} does not match the v0.1 pin",
                contract.id
            )));
        }
        safe_relative_path(&contract.schema_path)?;
        safe_relative_path(&contract.fixture_path)?;
    }

    let expected_categories: HashSet<&str> = [
        "golden",
        "authority_escalation",
        "semantic_mismatch",
        "temporal_inversion",
        "unknown_field",
        "ambiguous_json",
        "verification_weakening",
        "unsafe_identifier",
    ]
    .into_iter()
    .collect();
    let mut categories = HashSet::new();
    let mut case_ids = HashSet::new();
    let mut coverage: BTreeMap<&str, HashSet<&str>> = BTreeMap::new();
    for case in &suite.cases {
        if !safe_id(&case.id)
            || !contract_ids.contains(case.contract.as_str())
            || case.description.trim().is_empty()
            || !valid_sha256(&case.expected_input_sha256)
            || !matches!(
                case.expected_semantics.as_str(),
                VALID_NON_AUTHORIZING | INVALID_BLOCKED
            )
            || !case_ids.insert(case.id.as_str())
        {
            return Err(invalid("suite contains an invalid or duplicate case"));
        }
        categories.insert(case.category.as_str());
        coverage
            .entry(case.contract.as_str())
            .or_default()
            .insert(case.expected_semantics.as_str());
    }
    if categories != expected_categories
        || coverage.len() != suite.contracts.len()
        || coverage.values().any(|outcomes| {
            outcomes.len() != 2
                || !outcomes.contains(VALID_NON_AUTHORIZING)
                || !outcomes.contains(INVALID_BLOCKED)
        })
    {
        return Err(invalid(
            "suite cases do not cover every control and expected semantic",
        ));
    }
    Ok(())
}

fn pointer_tokens(pointer: &str) -> Result<Vec<String>, CgqaConformanceError> {
    if !pointer.starts_with('/') {
        return Err(invalid("operation pointer must be a JSON Pointer"));
    }
    pointer[1..]
        .split('/')
        .map(|token| {
            let mut decoded = String::new();
            let mut characters = token.chars();
            while let Some(character) = characters.next() {
                if character != '~' {
                    decoded.push(character);
                    continue;
                }
                match characters.next() {
                    Some('0') => decoded.push('~'),
                    Some('1') => decoded.push('/'),
                    _ => return Err(invalid("operation pointer contains an invalid escape")),
                }
            }
            Ok(decoded)
        })
        .collect()
}

fn array_index(token: &str) -> Result<usize, CgqaConformanceError> {
    if token.is_empty() || !token.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(invalid(format!(
            "operation list pointer is invalid: {token}"
        )));
    }
    token
        .parse::<usize>()
        .map_err(|_| invalid(format!("operation list index is invalid: {token}")))
}

fn navigate_mut<'a>(
    mut current: &'a mut Value,
    tokens: &[String],
) -> Result<&'a mut Value, CgqaConformanceError> {
    for token in tokens {
        current = match current {
            Value::Object(object) => object.get_mut(token).ok_or_else(|| {
                invalid(format!("operation pointer component is absent: {token}"))
            })?,
            Value::Array(array) => {
                let index = array_index(token)?;
                array.get_mut(index).ok_or_else(|| {
                    invalid(format!("operation list index is out of range: {index}"))
                })?
            }
            _ => return Err(invalid("operation pointer traverses a scalar value")),
        };
    }
    Ok(current)
}

fn apply_operation(
    base_raw: &[u8],
    operation: &Operation,
) -> Result<Vec<u8>, CgqaConformanceError> {
    if matches!(operation, Operation::Identity) {
        return Ok(base_raw.to_vec());
    }

    let mut document: Value = serde_json::from_slice(base_raw)?;
    if let Operation::DuplicateRootKey { key, value } = operation {
        let object = document
            .as_object()
            .ok_or_else(|| invalid("duplicate_root_key requires an object fixture"))?;
        if !object.contains_key(key) {
            return Err(invalid(format!(
                "duplicate_root_key target does not exist: {key}"
            )));
        }
        let start = base_raw
            .iter()
            .position(|byte| !byte.is_ascii_whitespace())
            .ok_or_else(|| invalid("case fixture is empty"))?;
        if base_raw[start] != b'{' {
            return Err(invalid("duplicate_root_key requires an object fixture"));
        }
        let mut result = Vec::new();
        result.push(b'{');
        result.extend(serde_json::to_vec(key)?);
        result.push(b':');
        result.extend(serde_json::to_vec(value)?);
        result.push(b',');
        result.extend_from_slice(&base_raw[start + 1..]);
        return Ok(result);
    }

    let (kind, pointer, replacement) = match operation {
        Operation::Replace { pointer, value } => ("replace", pointer, Some(value)),
        Operation::Add { pointer, value } => ("add", pointer, Some(value)),
        Operation::Remove { pointer } => ("remove", pointer, None),
        Operation::Identity | Operation::DuplicateRootKey { .. } => unreachable!(),
    };
    let tokens = pointer_tokens(pointer)?;
    let (last, parents) = tokens
        .split_last()
        .ok_or_else(|| invalid("operation pointer must not target the document root"))?;
    let container = navigate_mut(&mut document, parents)?;
    match container {
        Value::Object(object) => match kind {
            "add" => {
                if object.contains_key(last) {
                    return Err(invalid(format!("add target already exists: {last}")));
                }
                object.insert(
                    last.clone(),
                    replacement.expect("add has a replacement value").clone(),
                );
            }
            "replace" => {
                let target = object
                    .get_mut(last)
                    .ok_or_else(|| invalid(format!("operation target does not exist: {last}")))?;
                *target = replacement
                    .expect("replace has a replacement value")
                    .clone();
            }
            "remove" => {
                if object.remove(last).is_none() {
                    return Err(invalid(format!("operation target does not exist: {last}")));
                }
            }
            _ => unreachable!(),
        },
        Value::Array(array) => {
            let index = array_index(last)?;
            match kind {
                "add" => {
                    if index > array.len() {
                        return Err(invalid(format!(
                            "operation list index is out of range: {index}"
                        )));
                    }
                    array.insert(
                        index,
                        replacement.expect("add has a replacement value").clone(),
                    );
                }
                "replace" => {
                    let target = array.get_mut(index).ok_or_else(|| {
                        invalid(format!("operation list index is out of range: {index}"))
                    })?;
                    *target = replacement
                        .expect("replace has a replacement value")
                        .clone();
                }
                "remove" => {
                    if index >= array.len() {
                        return Err(invalid(format!(
                            "operation list index is out of range: {index}"
                        )));
                    }
                    array.remove(index);
                }
                _ => unreachable!(),
            }
        }
        _ => {
            return Err(invalid(
                "operation pointer parent must be an object or array",
            ))
        }
    }

    let mut canonical = serde_json::to_vec(&document)?;
    canonical.push(b'\n');
    Ok(canonical)
}

fn observe(artifact_schema: &str, raw: &[u8]) -> (String, String) {
    if artifact_schema == CGQA_EVIDENCE_SCHEMA {
        return match CgqaEvidenceExport::from_json(raw) {
            Ok(evidence) if evidence.authority.may_authorize_action => (
                UNSAFE_ACCEPTED.to_string(),
                "adapter accepted evidence with action authority".to_string(),
            ),
            Ok(_) => (
                VALID_NON_AUTHORIZING.to_string(),
                "profile accepted without action authority".to_string(),
            ),
            Err(error) => (INVALID_BLOCKED.to_string(), error.to_string()),
        };
    }
    if artifact_schema == LIMINAL_CANDIDATE_SCHEMA {
        return match CgqaCandidateExport::from_json(raw) {
            Ok(candidates)
                if candidates.authority.may_authorize_action
                    || !candidates.authority.requires_cgqa_verification =>
            {
                (
                    UNSAFE_ACCEPTED.to_string(),
                    "adapter accepted candidate authority or weakened verification".to_string(),
                )
            }
            Ok(_) => (
                VALID_NON_AUTHORIZING.to_string(),
                "profile accepted without action authority".to_string(),
            ),
            Err(error) => (INVALID_BLOCKED.to_string(), error.to_string()),
        };
    }
    (
        INVALID_BLOCKED.to_string(),
        format!("unsupported artifact schema: {artifact_schema}"),
    )
}

/// Run all pinned vectors through the native Rust adapter.
pub fn run_cgqa_conformance_suite(path: Option<&Path>) -> Result<Value, CgqaConformanceError> {
    let loaded = load_suite(path)?;
    let contracts: BTreeMap<&str, &Contract> = loaded
        .suite
        .contracts
        .iter()
        .map(|contract| (contract.id.as_str(), contract))
        .collect();
    let mut results = Vec::new();
    let mut passed = 0_u64;
    for case in &loaded.suite.cases {
        let contract = contracts
            .get(case.contract.as_str())
            .ok_or_else(|| invalid(format!("unknown case contract: {}", case.contract)))?;
        let fixture = loaded
            .fixtures
            .get(case.contract.as_str())
            .ok_or_else(|| invalid(format!("missing fixture for contract: {}", case.contract)))?;
        let input = apply_operation(fixture, &case.operation)?;
        let input_sha256 = sha256_hex(&input);
        if input_sha256 != case.expected_input_sha256 {
            return Err(invalid(format!(
                "case {} mutation digest does not match the v0.1 pin",
                case.id
            )));
        }
        let (observed, diagnostic) = observe(&contract.artifact_schema, &input);
        let status = if observed == case.expected_semantics {
            passed += 1;
            "PASS"
        } else {
            "FAIL"
        };
        results.push(json!({
            "id": case.id,
            "contract": case.contract,
            "category": case.category,
            "status": status,
            "expectedSemantics": case.expected_semantics,
            "observedSemantics": observed,
            "inputSha256": input_sha256,
            "diagnostic": diagnostic,
            "sideEffectExecuted": false
        }));
    }

    let total = results.len() as u64;
    let contract_pins: Vec<Value> = loaded
        .suite
        .contracts
        .iter()
        .map(|contract| {
            json!({
                "id": contract.id,
                "artifactSchema": contract.artifact_schema,
                "artifactProfile": contract.artifact_profile,
                "ownerRepository": contract.owner_repository,
                "producerCommit": contract.producer_commit,
                "schemaSha256": contract.schema_sha256,
                "fixtureSha256": contract.fixture_sha256
            })
        })
        .collect();
    let mut report = json!({
        "schema": RESULT_SCHEMA,
        "suiteId": loaded.suite.suite_id,
        "suiteVersion": loaded.suite.version,
        "suiteSha256": sha256_hex(&loaded.suite_raw),
        "implementation": {
            "name": "liminalqa",
            "version": env!("CARGO_PKG_VERSION"),
            "language": "rust"
        },
        "status": if passed == total { "PASS" } else { "FAIL" },
        "counts": {"total": total, "passed": passed, "failed": total - passed},
        "contractPins": contract_pins,
        "results": results,
        "authority": {
            "classification": "conformance_evidence_only",
            "mayAuthorizeAction": false
        },
        "claimBoundary": loaded.suite.claim_boundary
    });
    let report_digest = sha256_hex(&serde_json::to_vec(&report)?);
    report.as_object_mut().expect("report is an object").insert(
        "reportId".to_string(),
        Value::String(format!(
            "liminalqa-interop-conformance-{}",
            &report_digest[..24]
        )),
    );
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn embedded_suite_is_exact_and_all_vectors_pass() {
        let report = run_cgqa_conformance_suite(None).unwrap();
        assert_eq!(report["suiteSha256"], SUITE_SHA256);
        assert_eq!(report["status"], "PASS");
        assert_eq!(report["counts"]["total"], 14);
        assert_eq!(report["counts"]["passed"], 14);
        assert_eq!(report["counts"]["failed"], 0);
        assert!(report["results"]
            .as_array()
            .expect("conformance results must be an array")
            .iter()
            .all(|result| result["sideEffectExecuted"] == false));
        assert_eq!(report["authority"]["mayAuthorizeAction"], false);
    }

    #[test]
    fn candidate_decoder_rejects_weakened_fresh_verification() {
        let fixture = embedded_asset("fixtures/liminalqa-cgqa-candidates-v0.1.json")
            .expect("candidate fixture must be embedded");
        let mut candidate: Value = serde_json::from_slice(fixture).unwrap();
        candidate["candidates"][0]["requiredChecks"]
            .as_array_mut()
            .expect("requiredChecks must be an array")
            .retain(|check| check != "independent_cgqa_replay");
        let error =
            CgqaCandidateExport::from_json(&serde_json::to_vec(&candidate).unwrap()).unwrap_err();
        assert!(error.to_string().contains("independent_cgqa_replay"));
    }
}
