#!/usr/bin/env bash
# Run all LiminalQA benchmarks.
#
# Usage:
#   ./scripts/run_benchmarks.sh             # criterion only
#   ./scripts/run_benchmarks.sh --k6        # criterion + k6 (server must be running)
#   ./scripts/run_benchmarks.sh --k6-only   # k6 only
#   ./scripts/run_benchmarks.sh --rps 1000  # set k6 target RPS

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Defaults
RUN_CRITERION=true
RUN_K6=false
TARGET_RPS="${TARGET_RPS:-100}"
BASE_URL="${LIMINALQA_URL:-http://localhost:8080}"
AUTH_TOKEN="${LIMINAL_AUTH_TOKEN:-}"

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --k6)        RUN_K6=true; shift ;;
    --k6-only)   RUN_CRITERION=false; RUN_K6=true; shift ;;
    --rps)       TARGET_RPS="$2"; shift 2 ;;
    --url)       BASE_URL="$2"; shift 2 ;;
    --token)     AUTH_TOKEN="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ── Criterion ────────────────────────────────────────────────────────────────
if $RUN_CRITERION; then
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Running criterion benchmarks..."
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  cd "$REPO_ROOT"
  cargo bench -p liminalqa-db 2>&1

  REPORT_DIR="$REPO_ROOT/target/criterion"
  if [[ -d "$REPORT_DIR" ]]; then
    echo ""
    echo "  HTML report: $REPORT_DIR/storage/report/index.html"
  fi
fi

# ── k6 ───────────────────────────────────────────────────────────────────────
if $RUN_K6; then
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Running k6 REST load test..."
  echo "  URL        : $BASE_URL"
  echo "  Target RPS : $TARGET_RPS"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  if ! command -v k6 &>/dev/null; then
    echo ""
    echo "  k6 not found. Install from https://k6.io/docs/get-started/installation/"
    echo "  e.g.: brew install k6   |   apt install k6   |   snap install k6"
    exit 1
  fi

  K6_ARGS=(
    "--env" "BASE_URL=${BASE_URL}"
    "--env" "TARGET_RPS=${TARGET_RPS}"
  )
  if [[ -n "$AUTH_TOKEN" ]]; then
    K6_ARGS+=("--env" "AUTH_TOKEN=${AUTH_TOKEN}")
  fi

  cd "$REPO_ROOT"
  k6 run "${K6_ARGS[@]}" scripts/bench_rest.js
fi

echo ""
echo "Done."
