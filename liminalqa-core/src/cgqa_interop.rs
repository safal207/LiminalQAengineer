//! Strict ContractGraph-QA interoperability profiles.
//!
//! Imported CGQA records remain bounded evidence. Derived records are only
//! non-authoritative candidate seeds and can neither authorize an action nor
//! stand in for a fresh ContractGraph-QA verification run.

use chrono::{DateTime, FixedOffset};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use thiserror::Error;

pub const CGQA_EVIDENCE_SCHEMA: &str = "org.contractgraph-qa.liminalqa-evidence.v0.1";
pub const CGQA_EVIDENCE_PROFILE: &str =
    "org.contractgraph-qa.bounded-invariant-evidence.v0.1";
pub const CGQA_EVIDENCE_SCHEMA_SHA256: &str =
    "53b0b4a0b1f4d77de26b8be9dbb90006ea0bd30c5cd3960a2f3e7d44d9664184";
pub const LIMINAL_IMPORT_SCHEMA: &str = "org.liminalqa.cgqa-import-receipt.v0.1";
pub const LIMINAL_IMPORT_PROFILE: &str = "org.liminalqa.bounded-evidence-intake.v0.1";
pub const LIMINAL_CANDIDATE_SCHEMA: &str = "org.liminalqa.cgqa-candidates.v0.1";
pub const LIMINAL_CANDIDATE_PROFILE: &str =
    "org.liminalqa.non-authoritative-candidate-seeds.v0.1";

#[derive(Debug, Error, PartialEq, Eq)]
pub enum CgqaInteropError {
    #[error("invalid CGQA interop profile: {0}")]
    Invalid(String),
    #[error("invalid CGQA interop JSON: {0}")]
    Json(String),
}

fn invalid(message: impl Into<String>) -> CgqaInteropError {
    CgqaInteropError::Invalid(message.into())
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Producer {
    pub name: String,
    pub version: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Subject {
    pub repository: String,
    pub commit_sha: String,
    pub contract: String,
    pub network: String,
    pub scope_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Identity {
    pub trace_id: String,
    pub operation_id: String,
    pub attempt_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EvidenceTimes {
    pub valid_at: String,
    pub observed_at: String,
    pub recorded_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Sha256Digest {
    pub algorithm: String,
    pub value: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct AdapterIdentity {
    pub id: String,
    pub version: String,
    pub digest: Sha256Digest,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SearchBound {
    pub search_run_id: String,
    pub max_depth: u64,
    pub explored_candidates: u64,
    pub replay: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct StatusCounts {
    pub violated: u64,
    pub not_found_within_bound: u64,
    pub inconclusive: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Assessment {
    pub kind: String,
    pub status_vocabulary: Vec<String>,
    pub counts: StatusCounts,
    pub continuity_verdict: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct InvariantCheck {
    pub invariant_id: String,
    pub title: String,
    pub severity: String,
    pub status: String,
    pub explored_candidates: u64,
    pub notes: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub finding_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path_length: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EvidenceArtifact {
    pub artifact_id: String,
    pub media_type: String,
    pub sha256: String,
    pub bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EvidenceDebt {
    pub invariant_id: String,
    pub status: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EvidenceAuthority {
    pub classification: String,
    pub may_authorize_action: bool,
    pub action_authorization: String,
    pub continuity_verdict_owner: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CgqaEvidenceExport {
    pub schema: String,
    pub profile: String,
    pub export_id: String,
    pub producer: Producer,
    pub subject: Subject,
    pub identity: Identity,
    pub times: EvidenceTimes,
    pub adapter: AdapterIdentity,
    pub bound: SearchBound,
    pub assessment: Assessment,
    pub checks: Vec<InvariantCheck>,
    pub artifacts: Vec<EvidenceArtifact>,
    pub causal_parents: Vec<String>,
    pub verification_debt: Vec<EvidenceDebt>,
    pub limitations: Vec<String>,
    pub authority: EvidenceAuthority,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SourceEvidenceRef {
    pub schema: String,
    pub export_id: String,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CandidateAuthority {
    pub classification: String,
    pub may_authorize_action: bool,
    pub requires_cgqa_verification: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Candidate {
    pub candidate_id: String,
    pub invariant_id: String,
    pub source_status: String,
    pub kind: String,
    pub priority: String,
    pub reason: String,
    pub required_checks: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CandidateDebt {
    pub invariant_id: String,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CgqaCandidateExport {
    pub schema: String,
    pub profile: String,
    pub export_id: String,
    pub producer: Producer,
    pub source_evidence: SourceEvidenceRef,
    pub subject: Subject,
    pub identity: Identity,
    pub derived_at: String,
    pub authority: CandidateAuthority,
    pub candidates: Vec<Candidate>,
    pub causal_parents: Vec<String>,
    pub limitations: Vec<String>,
    pub verification_debt: Vec<CandidateDebt>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ImportSource {
    pub schema: String,
    pub export_id: String,
    pub sha256: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct CgqaImportReceipt {
    pub schema: String,
    pub profile: String,
    pub receipt_id: String,
    pub consumer: Producer,
    pub source: ImportSource,
    pub subject: Subject,
    pub identity: Identity,
    pub accepted_as: String,
    pub may_authorize_action: bool,
    pub status_counts: StatusCounts,
    pub limitations: Vec<String>,
}

pub fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    digest
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<Vec<_>>()
        .concat()
}

fn non_blank(value: &str, field: &str) -> Result<(), CgqaInteropError> {
    if value.trim().is_empty() {
        return Err(invalid(format!("{field} must be a non-empty string")));
    }
    Ok(())
}

fn safe_id(value: &str, field: &str) -> Result<(), CgqaInteropError> {
    non_blank(value, field)?;
    let mut chars = value.chars();
    let first = chars.next().expect("non-blank checked above");
    if value.len() > 200
        || !first.is_ascii_alphanumeric()
        || !chars.all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | ':' | '-'))
    {
        return Err(invalid(format!(
            "{field} contains unsafe identifier characters"
        )));
    }
    Ok(())
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn timestamp(value: &str, field: &str) -> Result<DateTime<FixedOffset>, CgqaInteropError> {
    DateTime::parse_from_rfc3339(value)
        .map_err(|_| invalid(format!("{field} must be an RFC 3339 timestamp with explicit offset")))
}

fn validate_subject(subject: &Subject) -> Result<(), CgqaInteropError> {
    non_blank(&subject.repository, "subject.repository")?;
    non_blank(&subject.contract, "subject.contract")?;
    non_blank(&subject.network, "subject.network")?;
    non_blank(&subject.scope_id, "subject.scopeId")?;
    if subject.commit_sha.len() != 40
        || !subject
            .commit_sha
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(invalid(
            "subject.commitSha must be a full lowercase 40-character commit SHA",
        ));
    }
    Ok(())
}

fn validate_identity(identity: &Identity) -> Result<(), CgqaInteropError> {
    safe_id(&identity.trace_id, "identity.traceId")?;
    safe_id(&identity.operation_id, "identity.operationId")?;
    safe_id(&identity.attempt_id, "identity.attemptId")
}

fn ensure_source_matches(
    evidence: &CgqaEvidenceExport,
    source_bytes: &[u8],
) -> Result<(), CgqaInteropError> {
    let decoded = CgqaEvidenceExport::from_json(source_bytes)?;
    if decoded != *evidence {
        return Err(invalid(
            "source bytes do not encode the validated CGQA evidence",
        ));
    }
    Ok(())
}

impl CgqaEvidenceExport {
    pub fn from_json(bytes: &[u8]) -> Result<Self, CgqaInteropError> {
        let profile: Self = serde_json::from_slice(bytes)
            .map_err(|error| CgqaInteropError::Json(error.to_string()))?;
        profile.validate()?;
        Ok(profile)
    }

    pub fn validate(&self) -> Result<(), CgqaInteropError> {
        if self.schema != CGQA_EVIDENCE_SCHEMA {
            return Err(invalid("schema is unsupported"));
        }
        if self.profile != CGQA_EVIDENCE_PROFILE {
            return Err(invalid("profile is unsupported"));
        }
        safe_id(&self.export_id, "exportId")?;
        if self.producer.name != "contractgraph-qa" {
            return Err(invalid("producer.name must be contractgraph-qa"));
        }
        non_blank(&self.producer.version, "producer.version")?;
        validate_subject(&self.subject)?;
        validate_identity(&self.identity)?;

        let valid_at = timestamp(&self.times.valid_at, "times.validAt")?;
        let observed_at = timestamp(&self.times.observed_at, "times.observedAt")?;
        let recorded_at = timestamp(&self.times.recorded_at, "times.recordedAt")?;
        if !(valid_at <= observed_at && observed_at <= recorded_at) {
            return Err(invalid(
                "times must satisfy validAt <= observedAt <= recordedAt",
            ));
        }

        non_blank(&self.adapter.id, "adapter.id")?;
        non_blank(&self.adapter.version, "adapter.version")?;
        if self.adapter.digest.algorithm != "sha256" || !valid_sha256(&self.adapter.digest.value)
        {
            return Err(invalid("adapter.digest must contain lowercase sha256"));
        }
        safe_id(&self.bound.search_run_id, "bound.searchRunId")?;
        if self.bound.max_depth == 0 {
            return Err(invalid("bound.maxDepth must be greater than zero"));
        }
        non_blank(&self.bound.replay, "bound.replay")?;

        if self.assessment.kind != "bounded_invariant_search"
            || self.assessment.continuity_verdict != "not_computed"
        {
            return Err(invalid(
                "assessment must be bounded_invariant_search with continuityVerdict=not_computed",
            ));
        }
        let expected_vocabulary = vec![
            "violated".to_string(),
            "not_found_within_bound".to_string(),
            "inconclusive".to_string(),
        ];
        if self.assessment.status_vocabulary != expected_vocabulary {
            return Err(invalid(
                "assessment.statusVocabulary must preserve the canonical CGQA statuses",
            ));
        }
        if self.checks.is_empty() {
            return Err(invalid("checks must be non-empty"));
        }

        let mut seen = HashSet::new();
        let mut violated = 0_u64;
        let mut not_found = 0_u64;
        let mut inconclusive = 0_u64;
        let mut explored = 0_u64;
        for (index, check) in self.checks.iter().enumerate() {
            safe_id(&check.invariant_id, &format!("checks[{index}].invariantId"))?;
            if !seen.insert(&check.invariant_id) {
                return Err(invalid(format!(
                    "duplicate invariant in checks: {}",
                    check.invariant_id
                )));
            }
            non_blank(&check.title, &format!("checks[{index}].title"))?;
            if !matches!(
                check.severity.as_str(),
                "critical" | "high" | "medium" | "low" | "info"
            ) {
                return Err(invalid(format!(
                    "checks[{index}].severity is unsupported"
                )));
            }
            non_blank(&check.notes, &format!("checks[{index}].notes"))?;
            explored = explored
                .checked_add(check.explored_candidates)
                .ok_or_else(|| invalid("exploredCandidates overflow"))?;
            match check.status.as_str() {
                "violated" => {
                    violated += 1;
                    let finding_id = check.finding_id.as_deref().ok_or_else(|| {
                        invalid(format!("checks[{index}] violated status requires findingId"))
                    })?;
                    safe_id(finding_id, &format!("checks[{index}].findingId"))?;
                    if check.path_length.unwrap_or(0) == 0 {
                        return Err(invalid(format!(
                            "checks[{index}] violated status requires positive pathLength"
                        )));
                    }
                }
                "not_found_within_bound" => {
                    not_found += 1;
                    if check.finding_id.is_some() || check.path_length.is_some() {
                        return Err(invalid(format!(
                            "checks[{index}] not_found_within_bound must not carry finding fields"
                        )));
                    }
                }
                "inconclusive" => {
                    inconclusive += 1;
                    if check.finding_id.is_some() || check.path_length.is_some() {
                        return Err(invalid(format!(
                            "checks[{index}] inconclusive must not carry finding fields"
                        )));
                    }
                }
                _ => return Err(invalid(format!("checks[{index}].status is unsupported"))),
            }
        }
        if self.assessment.counts.violated != violated
            || self.assessment.counts.not_found_within_bound != not_found
            || self.assessment.counts.inconclusive != inconclusive
        {
            return Err(invalid("assessment.counts does not match checks"));
        }
        if self.bound.explored_candidates != explored {
            return Err(invalid("bound.exploredCandidates does not match checks"));
        }

        if self.artifacts.is_empty() {
            return Err(invalid("artifacts must be non-empty"));
        }
        let mut artifact_ids = HashSet::new();
        for (index, artifact) in self.artifacts.iter().enumerate() {
            safe_id(
                &artifact.artifact_id,
                &format!("artifacts[{index}].artifactId"),
            )?;
            if !artifact_ids.insert(&artifact.artifact_id) {
                return Err(invalid(format!(
                    "duplicate artifact id: {}",
                    artifact.artifact_id
                )));
            }
            non_blank(&artifact.media_type, &format!("artifacts[{index}].mediaType"))?;
            if !valid_sha256(&artifact.sha256) || artifact.bytes == 0 {
                return Err(invalid(format!(
                    "artifacts[{index}] must contain lowercase sha256 and positive bytes"
                )));
            }
        }
        let mut parents = HashSet::new();
        for (index, parent) in self.causal_parents.iter().enumerate() {
            safe_id(parent, &format!("causalParents[{index}]"))?;
            if !parents.insert(parent) {
                return Err(invalid("causalParents contains duplicates"));
            }
        }

        let expected_debt: HashSet<&str> = self
            .checks
            .iter()
            .filter(|check| check.status == "inconclusive")
            .map(|check| check.invariant_id.as_str())
            .collect();
        let mut actual_debt = HashSet::new();
        for (index, debt) in self.verification_debt.iter().enumerate() {
            safe_id(
                &debt.invariant_id,
                &format!("verificationDebt[{index}].invariantId"),
            )?;
            if debt.status != "inconclusive" {
                return Err(invalid(format!(
                    "verificationDebt[{index}].status must be inconclusive"
                )));
            }
            non_blank(&debt.reason, &format!("verificationDebt[{index}].reason"))?;
            if !actual_debt.insert(debt.invariant_id.as_str()) {
                return Err(invalid("verificationDebt contains duplicate invariants"));
            }
        }
        if expected_debt != actual_debt {
            return Err(invalid(
                "verificationDebt must enumerate every and only inconclusive check",
            ));
        }
        if self.limitations.is_empty()
            || self
                .limitations
                .iter()
                .any(|limitation| limitation.trim().is_empty())
        {
            return Err(invalid("limitations must contain non-empty entries"));
        }
        if self.authority.classification != "evidence_only"
            || self.authority.may_authorize_action
            || self.authority.action_authorization != "not_evaluated"
            || self.authority.continuity_verdict_owner != "ltp"
        {
            return Err(invalid(
                "authority must remain evidence_only, non-authorizing, and LTP-owned for continuity",
            ));
        }
        Ok(())
    }
}

pub fn import_receipt(
    evidence: &CgqaEvidenceExport,
    source_bytes: &[u8],
) -> Result<CgqaImportReceipt, CgqaInteropError> {
    evidence.validate()?;
    ensure_source_matches(evidence, source_bytes)?;
    let source_sha = sha256_hex(source_bytes);
    Ok(CgqaImportReceipt {
        schema: LIMINAL_IMPORT_SCHEMA.to_string(),
        profile: LIMINAL_IMPORT_PROFILE.to_string(),
        receipt_id: format!("liminal-cgqa-import-{}", &source_sha[..24]),
        consumer: Producer {
            name: "liminalqa".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
        },
        source: ImportSource {
            schema: evidence.schema.clone(),
            export_id: evidence.export_id.clone(),
            sha256: source_sha,
        },
        subject: evidence.subject.clone(),
        identity: evidence.identity.clone(),
        accepted_as: "bounded_evidence".to_string(),
        may_authorize_action: false,
        status_counts: evidence.assessment.counts.clone(),
        limitations: vec![
            "Import validates structure and semantic boundaries; it does not prove the underlying claim."
                .to_string(),
            "The receipt is not an action authorization or an LTP continuity verdict.".to_string(),
        ],
    })
}

fn candidate_priority(severity: &str) -> String {
    match severity {
        "critical" => "critical",
        "high" => "high",
        "medium" => "medium",
        _ => "low",
    }
    .to_string()
}

pub fn export_candidates(
    evidence: &CgqaEvidenceExport,
    source_bytes: &[u8],
    derived_at: &str,
    operation_id: &str,
    attempt_id: &str,
) -> Result<CgqaCandidateExport, CgqaInteropError> {
    evidence.validate()?;
    ensure_source_matches(evidence, source_bytes)?;
    let derived = timestamp(derived_at, "derivedAt")?;
    let recorded = timestamp(&evidence.times.recorded_at, "times.recordedAt")?;
    if derived < recorded {
        return Err(invalid("derivedAt must not precede source times.recordedAt"));
    }
    safe_id(operation_id, "identity.operationId")?;
    safe_id(attempt_id, "identity.attemptId")?;

    let source_sha = sha256_hex(source_bytes);
    let mut candidates = Vec::new();
    let mut debt = Vec::new();
    for check in &evidence.checks {
        let (kind, required_checks) = match check.status.as_str() {
            "violated" => (
                "replay_regression",
                vec![
                    "exact_subject".to_string(),
                    "independent_cgqa_replay".to_string(),
                    "failing_path_integrity".to_string(),
                ],
            ),
            "inconclusive" => {
                debt.push(CandidateDebt {
                    invariant_id: check.invariant_id.clone(),
                    reason: check.notes.clone(),
                });
                (
                    "verification_debt",
                    vec![
                        "exact_subject".to_string(),
                        "reviewed_bound_change".to_string(),
                        "independent_cgqa_replay".to_string(),
                    ],
                )
            }
            "not_found_within_bound" => continue,
            _ => unreachable!("validated evidence contains only canonical statuses"),
        };
        let seed = format!(
            "{}:{}:{}:{}",
            evidence.export_id, check.invariant_id, check.status, kind
        );
        candidates.push(Candidate {
            candidate_id: format!(
                "liminal-candidate-{}",
                &sha256_hex(seed.as_bytes())[..24]
            ),
            invariant_id: check.invariant_id.clone(),
            source_status: check.status.clone(),
            kind: kind.to_string(),
            priority: candidate_priority(&check.severity),
            reason: check.notes.clone(),
            required_checks,
        });
    }

    let export_seed = format!(
        "{}:{}:{}:{}:{}",
        evidence.export_id, source_sha, derived_at, operation_id, attempt_id
    );
    Ok(CgqaCandidateExport {
        schema: LIMINAL_CANDIDATE_SCHEMA.to_string(),
        profile: LIMINAL_CANDIDATE_PROFILE.to_string(),
        export_id: format!(
            "liminal-candidates-{}",
            &sha256_hex(export_seed.as_bytes())[..24]
        ),
        producer: Producer {
            name: "liminalqa".to_string(),
            version: env!("CARGO_PKG_VERSION").to_string(),
        },
        source_evidence: SourceEvidenceRef {
            schema: evidence.schema.clone(),
            export_id: evidence.export_id.clone(),
            sha256: source_sha,
        },
        subject: evidence.subject.clone(),
        identity: Identity {
            trace_id: evidence.identity.trace_id.clone(),
            operation_id: operation_id.to_string(),
            attempt_id: attempt_id.to_string(),
        },
        derived_at: derived_at.to_string(),
        authority: CandidateAuthority {
            classification: "non_authoritative_seed".to_string(),
            may_authorize_action: false,
            requires_cgqa_verification: true,
        },
        candidates,
        causal_parents: vec![evidence.export_id.clone()],
        limitations: vec![
            "Candidates are hypotheses derived from bounded evidence, not verified findings."
                .to_string(),
            "ContractGraph-QA must independently replay each candidate against the exact commit."
                .to_string(),
            "Candidate export cannot authorize an action or compute an LTP continuity verdict."
                .to_string(),
        ],
        verification_debt: debt,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture_bytes() -> &'static [u8] {
        include_bytes!("../tests/fixtures/cgqa-liminalqa-evidence-v0.1.json")
    }

    #[test]
    fn imports_all_three_statuses_without_collapsing_not_found_to_pass() {
        let evidence = CgqaEvidenceExport::from_json(fixture_bytes()).unwrap();
        assert_eq!(
            evidence
                .checks
                .iter()
                .map(|check| check.status.as_str())
                .collect::<Vec<_>>(),
            vec!["violated", "not_found_within_bound", "inconclusive"]
        );
        let receipt = import_receipt(&evidence, fixture_bytes()).unwrap();
        assert_eq!(receipt.accepted_as, "bounded_evidence");
        assert!(!receipt.may_authorize_action);
    }

    #[test]
    fn rejects_evidence_that_claims_action_authority() {
        let mut value: serde_json::Value = serde_json::from_slice(fixture_bytes()).unwrap();
        value["authority"]["mayAuthorizeAction"] = serde_json::Value::Bool(true);
        let bytes = serde_json::to_vec(&value).unwrap();
        let error = CgqaEvidenceExport::from_json(&bytes).unwrap_err();
        assert!(error.to_string().contains("authority must remain evidence_only"));
    }

    #[test]
    fn rejects_duplicate_debt_and_unknown_severity() {
        let mut duplicate_debt: serde_json::Value =
            serde_json::from_slice(fixture_bytes()).unwrap();
        let duplicate = duplicate_debt["verificationDebt"][0].clone();
        duplicate_debt["verificationDebt"]
            .as_array_mut()
            .unwrap()
            .push(duplicate);
        let error = CgqaEvidenceExport::from_json(&serde_json::to_vec(&duplicate_debt).unwrap())
            .unwrap_err();
        assert!(error.to_string().contains("duplicate invariants"));

        let mut unknown_severity: serde_json::Value =
            serde_json::from_slice(fixture_bytes()).unwrap();
        unknown_severity["checks"][0]["severity"] =
            serde_json::Value::String("urgent".to_string());
        let error = CgqaEvidenceExport::from_json(&serde_json::to_vec(&unknown_severity).unwrap())
            .unwrap_err();
        assert!(error.to_string().contains("severity is unsupported"));
    }

    #[test]
    fn rejects_source_bytes_that_do_not_match_the_validated_evidence() {
        let evidence = CgqaEvidenceExport::from_json(fixture_bytes()).unwrap();
        let mut other: serde_json::Value = serde_json::from_slice(fixture_bytes()).unwrap();
        other["exportId"] = serde_json::Value::String("cgqa-liminalqa-other".to_string());
        let other_bytes = serde_json::to_vec(&other).unwrap();

        let import_error = import_receipt(&evidence, &other_bytes).unwrap_err();
        assert!(import_error.to_string().contains("source bytes do not encode"));

        let export_error = export_candidates(
            &evidence,
            &other_bytes,
            "2026-09-03T10:03:00Z",
            "liminal-candidate-derivation-001",
            "attempt-001",
        )
        .unwrap_err();
        assert!(export_error.to_string().contains("source bytes do not encode"));
    }

    #[test]
    fn rejects_unknown_fields_fail_closed() {
        let mut value: serde_json::Value = serde_json::from_slice(fixture_bytes()).unwrap();
        value["authorization"] = serde_json::Value::String("ALLOW".to_string());
        let bytes = serde_json::to_vec(&value).unwrap();
        assert!(matches!(
            CgqaEvidenceExport::from_json(&bytes),
            Err(CgqaInteropError::Json(_))
        ));
    }

    #[test]
    fn candidate_export_is_deterministic_and_skips_not_found_status() {
        let evidence = CgqaEvidenceExport::from_json(fixture_bytes()).unwrap();
        let first = export_candidates(
            &evidence,
            fixture_bytes(),
            "2026-09-03T10:03:00Z",
            "liminal-candidate-derivation-001",
            "attempt-001",
        )
        .unwrap();
        let second = export_candidates(
            &evidence,
            fixture_bytes(),
            "2026-09-03T10:03:00Z",
            "liminal-candidate-derivation-001",
            "attempt-001",
        )
        .unwrap();
        assert_eq!(first, second);
        assert_eq!(first.candidates.len(), 2);
        assert!(first
            .candidates
            .iter()
            .all(|candidate| candidate.source_status != "not_found_within_bound"));
        assert!(!first.authority.may_authorize_action);
        assert!(first.authority.requires_cgqa_verification);
        let expected: CgqaCandidateExport = serde_json::from_slice(include_bytes!(
            "../tests/fixtures/liminalqa-cgqa-candidates-v0.1.json"
        ))
        .unwrap();
        assert_eq!(first, expected);
    }

    #[test]
    fn candidate_export_rejects_temporal_inversion() {
        let evidence = CgqaEvidenceExport::from_json(fixture_bytes()).unwrap();
        let error = export_candidates(
            &evidence,
            fixture_bytes(),
            "2026-09-03T09:59:59Z",
            "liminal-candidate-derivation-001",
            "attempt-001",
        )
        .unwrap_err();
        assert!(error.to_string().contains("derivedAt must not precede"));
    }

    #[test]
    fn consumer_pin_names_the_exact_producer_schema_and_commit() {
        let pin: serde_json::Value = serde_json::from_slice(include_bytes!(
            "../../schemas/interop/cgqa-liminalqa-evidence-v0.1.external-contract.json"
        ))
        .unwrap();
        assert_eq!(pin["producerSchema"], CGQA_EVIDENCE_SCHEMA);
        assert_eq!(pin["producerProfile"], CGQA_EVIDENCE_PROFILE);
        assert_eq!(pin["schemaSha256"], CGQA_EVIDENCE_SCHEMA_SHA256);
        assert_eq!(
            pin["producerCommit"],
            "bdf7ced074e3a7baf57cf89ac68be9674bd76a02"
        );
    }
}
