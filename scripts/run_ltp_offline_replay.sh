#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <trace.jsonl> <evidence-dir> <ltp-repo-dir> <ltp-sha>" >&2
  exit 2
fi

trace_path="$(realpath "$1")"
evidence_dir="$(realpath "$2")"
ltp_dir="$(realpath "$3")"
ltp_sha="$4"
report_dir="${evidence_dir}/ltp"
mkdir -p "${report_dir}"

dump_failure() {
  echo "--- LTP audit diagnostics ---" >&2
  for file in registry-parity.stderr.txt registry-parity.stdout.txt inspector.stderr.txt inspector-report.json replay-1.stderr.txt replay-1.stdout.txt replay-2.stderr.txt replay-2.stdout.txt explain-step-008.stderr.txt; do
    if [ -s "${report_dir}/${file}" ]; then
      echo "### ${file}" >&2
      cat "${report_dir}/${file}" >&2
    fi
  done
}
trap dump_failure ERR

if [[ ! "${ltp_sha}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ltp-sha must be a lowercase 40-character SHA" >&2
  exit 2
fi

test "$(git -C "${ltp_dir}" rev-parse HEAD)" = "${ltp_sha}"
test -s "${trace_path}"

registry_path="${ltp_dir}/docs/contracts/ltp-critical-actions.v0.1.json"
test -s "${registry_path}"
registry_sha="$(sha256sum "${registry_path}" | awk '{print $1}')"

cat > "${report_dir}/commands.txt" <<EOF
LTP_INSPECT_FREEZE_CLOCK=1 LTP_BUILD=${ltp_sha} pnpm -w ltp:inspect trace --strict --quiet --format json --color never --profile agents --replay-check --input ${trace_path}
LTP_BUILD=${ltp_sha} pnpm -w ltp:inspect replay --color never --input ${trace_path}
LTP_BUILD=${ltp_sha} pnpm -w ltp:inspect replay --color never --input ${trace_path}
LTP_BUILD=${ltp_sha} pnpm -w ltp:inspect explain --color never --input ${trace_path} --at step-008
EOF

printf '%s\n' "${ltp_sha}" > "${report_dir}/ltp-inspector-sha.txt"
printf '%s\n' "${registry_sha}" > "${report_dir}/critical-actions-registry.sha256"

set +e
(
  cd "${ltp_dir}"
  pnpm exec vitest run tools/ltp-inspect/critical_actions_registry.test.ts --reporter=dot
) > "${report_dir}/registry-parity.stdout.txt" 2> "${report_dir}/registry-parity.stderr.txt"
registry_code=$?
set -e
printf '%s\n' "${registry_code}" > "${report_dir}/registry-parity.exit-code.txt"
if [ "${registry_code}" -ne 0 ]; then
  echo "critical-action registry parity failed" >&2
  dump_failure
  exit "${registry_code}"
fi

set +e
(
  cd "${ltp_dir}"
  LTP_INSPECT_FREEZE_CLOCK=1 LTP_BUILD="${ltp_sha}" \
    pnpm -w ltp:inspect trace --strict --quiet --format json --color never \
      --profile agents --replay-check --input "${trace_path}"
) > "${report_dir}/inspector-report.json" 2> "${report_dir}/inspector.stderr.txt"
inspect_code=$?
set -e
printf '%s\n' "${inspect_code}" > "${report_dir}/inspector.exit-code.txt"
if [ "${inspect_code}" -ne 0 ]; then
  echo "strict LTP inspection failed with exit ${inspect_code}" >&2
  dump_failure
  exit "${inspect_code}"
fi

python3 - "${report_dir}/inspector-report.json" "${ltp_sha}" <<'PY'
import json
import sys
from pathlib import Path

report_path = Path(sys.argv[1])
ltp_sha = sys.argv[2]
report = json.loads(report_path.read_text(encoding="utf-8"))
compliance = report.get("compliance") or {}
audit = report.get("audit_summary") or {}
assert report.get("tool", {}).get("build") == ltp_sha
assert compliance.get("profile") == "agents"
assert compliance.get("trace_integrity") == "verified"
assert compliance.get("identity_binding") == "ok"
assert compliance.get("replay_determinism") == "ok"
assert audit.get("verdict") == "PASS"
assert audit.get("failed_checks") == []
assert audit.get("violations") == []
PY

for attempt in 1 2; do
  set +e
  (
    cd "${ltp_dir}"
    LTP_BUILD="${ltp_sha}" pnpm -w ltp:inspect replay --color never --input "${trace_path}"
  ) > "${report_dir}/replay-${attempt}.stdout.txt" 2> "${report_dir}/replay-${attempt}.stderr.txt"
  replay_code=$?
  set -e
  printf '%s\n' "${replay_code}" > "${report_dir}/replay-${attempt}.exit-code.txt"
  if [ "${replay_code}" -ne 0 ]; then
    echo "replay ${attempt} failed with exit ${replay_code}" >&2
    dump_failure
    exit "${replay_code}"
  fi
done

cmp --silent "${report_dir}/replay-1.stdout.txt" "${report_dir}/replay-2.stdout.txt"
replay_one_sha="$(sha256sum "${report_dir}/replay-1.stdout.txt" | awk '{print $1}')"
replay_two_sha="$(sha256sum "${report_dir}/replay-2.stdout.txt" | awk '{print $1}')"
test "${replay_one_sha}" = "${replay_two_sha}"

set +e
(
  cd "${ltp_dir}"
  LTP_BUILD="${ltp_sha}" pnpm -w ltp:inspect explain --color never --input "${trace_path}" --at step-008
) > "${report_dir}/explain-step-008.stdout.txt" 2> "${report_dir}/explain-step-008.stderr.txt"
explain_code=$?
set -e
printf '%s\n' "${explain_code}" > "${report_dir}/explain-step-008.exit-code.txt"
if [ "${explain_code}" -ne 0 ]; then
  echo "explain failed with exit ${explain_code}" >&2
  dump_failure
  exit "${explain_code}"
fi

python3 - "${report_dir}" "${replay_one_sha}" "${replay_two_sha}" "${ltp_sha}" "${registry_sha}" <<'PY'
import json
import sys
from pathlib import Path

report_dir = Path(sys.argv[1])
payload = {
    "schema_version": "liminalqa-ltp-replay-comparison-v1",
    "byte_identical": True,
    "replay_1_sha256": sys.argv[2],
    "replay_2_sha256": sys.argv[3],
    "ltp_inspector_sha": sys.argv[4],
    "critical_actions_registry_sha256": sys.argv[5],
    "inspector_exit_code": int((report_dir / "inspector.exit-code.txt").read_text().strip()),
    "replay_1_exit_code": int((report_dir / "replay-1.exit-code.txt").read_text().strip()),
    "replay_2_exit_code": int((report_dir / "replay-2.exit-code.txt").read_text().strip()),
}
(report_dir / "replay-comparison.json").write_text(
    json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

sha256sum "${trace_path}" > "${report_dir}/trace.sha256"
sha256sum "${report_dir}/inspector-report.json" > "${report_dir}/inspector-report.sha256"
