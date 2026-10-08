#!/usr/bin/env bash
# Build the frontend against the live backend and deploy it to AWS Amplify Hosting (Task I.6).
# Usage: scripts/aws/deploy_frontend.sh [AMPLIFY_APP_ID]   (default: the uic-brand-teammate app)
# Needs AWS credentials in the shell. The API URL is read from /uic-editorial/rag_api_url.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_ID="${1:-$(aws amplify list-apps --query "apps[?name=='uic-brand-teammate'].appId | [0]" --output text)}"
[[ -n "$APP_ID" && "$APP_ID" != "None" ]] || { echo "error: Amplify app uic-brand-teammate not found; pass its app id" >&2; exit 2; }
API_URL="$(aws ssm get-parameter --name /uic-editorial/rag_api_url --query Parameter.Value --output text)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT
echo "Building frontend against $API_URL"
(cd "$REPO_ROOT/frontend" && VITE_USE_MOCKS=false VITE_API_BASE_URL="$API_URL" VITE_RAG_API_URL="$API_URL" \
  npx vite build --outDir "$OUT/dist" --emptyOutDir >/dev/null)
(cd "$OUT/dist" && zip -qr "$OUT/site.zip" .)
read -r JOB URL < <(aws amplify create-deployment --app-id "$APP_ID" --branch-name main --query "[jobId,zipUploadUrl]" --output text)
curl -sf -T "$OUT/site.zip" -H "Content-Type: application/zip" "$URL" >/dev/null
aws amplify start-deployment --app-id "$APP_ID" --branch-name main --job-id "$JOB" >/dev/null
for _ in $(seq 60); do
  STATUS="$(aws amplify get-job --app-id "$APP_ID" --branch-name main --job-id "$JOB" --query job.summary.status --output text)"
  [[ "$STATUS" == SUCCEED || "$STATUS" == FAILED ]] && break
  sleep 3
done
echo "Deployment $JOB: $STATUS"
echo "https://main.$APP_ID.amplifyapp.com"
[[ "$STATUS" == SUCCEED ]]
