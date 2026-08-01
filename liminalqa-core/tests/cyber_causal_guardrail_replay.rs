use std::path::Path;
use std::process::Command;

#[test]
fn deterministic_cyber_causal_guardrail_replay_passes() {
    let repo = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("workspace root must exist");
    let output = Command::new("python3")
        .current_dir(repo)
        .arg("scripts/verify_cyber_guardrail_ci.py")
        .output()
        .expect("security replay verifier must start");

    assert!(
        output.status.success(),
        "security replay verifier failed\nstdout:\n{}\nstderr:\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}
