#!/usr/bin/env bash
# Run the Workstream 1 AWS setup in order: base (IAM, SSM, logs) -> S3 -> Knowledge Base
# -> RAG API (Lambda + API Gateway).
#
# Usage: scripts/aws/setup_all.sh [--region REGION] [--profile NAME] [--dry-run]
#                                 [--test-query "TEXT"]
# All steps are idempotent; re-running is safe. Stop costs with:
#   python scripts/aws/teardown.py --region REGION --yes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON="$REPO_ROOT/.venv/bin/python"
else
  PYTHON="${PYTHON:-python3}"
fi

COMMON=()
KB_EXTRA=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --region|--profile)
      [[ $# -ge 2 ]] || { echo "error: $1 needs a value" >&2; exit 2; }
      COMMON+=("$1" "$2"); shift 2 ;;
    --region=*|--profile=*)
      COMMON+=("$1"); shift ;;
    --dry-run)
      COMMON+=("--dry-run"); shift ;;
    --test-query)
      [[ $# -ge 2 ]] || { echo "error: --test-query needs a value" >&2; exit 2; }
      KB_EXTRA+=("--test-query" "$2"); shift 2 ;;
    --test-query=*)
      KB_EXTRA+=("$1"); shift ;;
    -h|--help)
      sed -n '2,8p' "$0"; exit 0 ;;
    *)
      echo "error: unknown argument $1 (see --help)" >&2; exit 2 ;;
  esac
done

run_step() {
  local title="$1"; shift
  echo
  echo "################################################################"
  echo "# $title"
  echo "################################################################"
  "$PYTHON" "$@"
}

run_step "1/4 Base setup (IAM roles, Parameter Store, CloudWatch Logs)" \
  "$SCRIPT_DIR/setup_base.py" ${COMMON[@]+"${COMMON[@]}"}
run_step "2/4 Guidelines S3 bucket + upload" \
  "$SCRIPT_DIR/setup_s3.py" ${COMMON[@]+"${COMMON[@]}"}
run_step "3/4 Bedrock Knowledge Base (S3 Vectors) + ingestion" \
  "$SCRIPT_DIR/setup_knowledge_base.py" ${COMMON[@]+"${COMMON[@]}"} ${KB_EXTRA[@]+"${KB_EXTRA[@]}"}
run_step "4/4 RAG API (Lambda + API Gateway HTTP API)" \
  "$SCRIPT_DIR/deploy_rag_api.py" ${COMMON[@]+"${COMMON[@]}"}

echo
echo "All Workstream 1 AWS setup steps finished."
