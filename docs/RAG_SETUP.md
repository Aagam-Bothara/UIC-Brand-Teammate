# Workstream 1 (RAG): Setup and Run

How to set up, run and test the guideline retrieval layer. The binding interface is
[`API_CONTRACT.md`](API_CONTRACT.md). The endpoint reference is in [`RAG_API.md`](RAG_API.md).

There are two backends behind the same `RAGService` interface:

| backend | when it's used | needs AWS? |
|---|---|---|
| `local` | No Knowledge Base id is configured, or `UIC_RAG_BACKEND=local` | No. Uses BM25 over `data/guidelines/` |
| `bedrock` | A KB id is configured (`UIC_KB_ID` or SSM), or `UIC_RAG_BACKEND=bedrock` | Yes. Uses a Bedrock Knowledge Base |

In `auto` mode (the default), a Bedrock failure falls back to `local` and logs a warning.

---

## 1. Python environment

Use Python 3.11 or newer. Run all commands from the repo root.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 2. Scrape the guidelines (no AWS)

```bash
.venv/bin/python -m scripts.scrape_guidelines
```

This fetches the 4 brand.uic.edu pages and writes them under `data/guidelines/`:

| source_id | category | page |
|---|---|---|
| `name-boilerplate` | `name` | Name and boilerplate |
| `voice-tone` | `tone` | Voice and tone |
| `brand-strategy` | `audience` | Brand strategy (key audiences and messaging) |
| `editorial-style` | `editorial` | Editorial and style guide |

The output layout:

```
data/guidelines/
├── raw/<source_id>.md                          # full page as markdown
├── chunks/<source_id>-<NNN>.md                 # ~1,000-char chunks (what Bedrock ingests)
├── chunks/<source_id>-<NNN>.md.metadata.json   # Bedrock KB metadata sidecar
└── guidelines_manifest.json                    # sources + chunks (the local backend's index)
```

Run it again whenever the guideline pages change. The `sha256` per source in the manifest shows
which sources changed.

## 3. Run the RAG dev server locally (no AWS)

```bash
export UIC_RAG_BACKEND=local     # force the local backend
export UIC_SSM_ENABLED=0         # skip Parameter Store lookups (no AWS calls at all)
.venv/bin/uvicorn backend.api.dev_server:app --reload
```

Then open http://127.0.0.1:8000/docs. The page has interactive Swagger docs for
`/api/rag/retrieve`, `/context`, `/sources` and `/health`.

```bash
curl -s localhost:8000/api/rag/health
curl -s -X POST localhost:8000/api/rag/retrieve -H 'content-type: application/json' \
  -d '{"query":"how to write the university name","top_k":3}'
```

`backend/api/dev_server.py` mounts only the RAG router, with CORS enabled for `localhost:3000` and
`localhost:5173`. The full app is `backend/api/main.py` (Task I.3), which includes the same
router.

## 4. AWS setup (Bedrock Knowledge Base)

**Prerequisites:**
- AWS credentials in your shell (`aws configure`, or pass `--profile NAME`).
- Bedrock model access to **Titan Text Embeddings V2** in the target region.
- Run `python -m scripts.scrape_guidelines` first, so `data/guidelines/chunks/` exists.

Run the scripts as files with `python scripts/aws/<script>.py`, not with `-m`, because they import
`aws_common` from their own directory. Every script is idempotent and accepts these options:

- `--region` (default `us-east-1`)
- `--profile NAME`
- `--dry-run`, which prints the planned changes without making them. With no credentials,
  `--dry-run` shows an offline preview instead.

Run with `--dry-run` first.

| script | purpose | extra options |
|---|---|---|
| `scripts/aws/setup_base.py` | IAM roles `uic-editorial-lambda-role` and `uic-editorial-kb-role` (policies are in `infra/iam/`), SSM `/uic-editorial/region` and `/uic-editorial/environment`, and log group `/uic-editorial/backend` with 14-day retention | `--environment dev`, `--bucket`, `--vector-bucket` |
| `scripts/aws/setup_s3.py` | Creates the guidelines bucket (`uic-editorial-guidelines-<account>-<region>`: versioned, private, SSE-S3), uploads the chunks listed in `guidelines_manifest.json` and their sidecars under `guidelines/` (chunk files the manifest does not list are reported and skipped), and sets `/uic-editorial/guidelines_bucket` | `--bucket` (default: the SSM value, then the default name), `--source-dir`, `--manifest`, `--prefix`, `--delete-stale` (removes objects not in the manifest), `--verbose` |
| `scripts/aws/setup_knowledge_base.py` | Creates the S3 Vectors bucket and index, then the Bedrock KB `uic-editorial-guidelines-kb` (Titan v2, 1024 dims) with its S3 data source. Sets `/uic-editorial/knowledge_base_id`, `data_source_id` and `vector_bucket`. Runs ingestion and an optional test query | `--no-ingest`, `--test-query "..."`, `--top-k`, `--category`, `--query-only`, `--kb-id`, `--chunking none\|fixed`, `--timeout`, `--ingest-timeout` |
| `scripts/aws/deploy_rag_api.py` | Builds the Lambda package (`backend/` + `data/guidelines/` + `requirements-lambda.txt`, arm64 wheels), creates/updates Lambda `uic-editorial-rag-api` (python3.13, handler `backend.api.lambda_app.handler`, logs to `/uic-editorial/backend`), creates HTTP API `uic-editorial-rag-api` (`$default` route → Lambda), sets `/uic-editorial/rag_api_url`, then smoke-tests `/api/rag/health`. Code is only re-uploaded when it changed | `--cors-origins` (default `*`), `--no-smoke-test` |
| `scripts/aws/setup_all.sh` | Runs the four scripts above in order, using `.venv/bin/python` if it exists | Accepts only `--region`, `--profile`, `--dry-run` and `--test-query "..."` (also the `--opt=value` forms) |
| `scripts/aws/teardown.py` | Deletes everything the setup scripts created, in this order: RAG API (HTTP API + Lambda), KB, vectors, guidelines bucket (all versions), SSM, log group, IAM. **Nothing is deleted without `--yes`.** | `--yes`, `--components api,kb,vectors,s3,ssm,logs,iam`, `--all-params`, `--bucket`, `--vector-bucket`, `--timeout` |

Commands, in order:

```bash
.venv/bin/python -m scripts.scrape_guidelines

.venv/bin/python scripts/aws/setup_base.py --region us-east-1 --dry-run
.venv/bin/python scripts/aws/setup_base.py --region us-east-1

.venv/bin/python scripts/aws/setup_s3.py --region us-east-1 --dry-run
.venv/bin/python scripts/aws/setup_s3.py --region us-east-1

.venv/bin/python scripts/aws/setup_knowledge_base.py --region us-east-1 --dry-run
.venv/bin/python scripts/aws/setup_knowledge_base.py --region us-east-1 \
    --test-query "how do I write the university name" --category name

.venv/bin/python scripts/aws/deploy_rag_api.py --region us-east-1 --dry-run
.venv/bin/python scripts/aws/deploy_rag_api.py --region us-east-1
```

Or run all four in one go:

```bash
bash scripts/aws/setup_all.sh --region us-east-1 --dry-run
bash scripts/aws/setup_all.sh --region us-east-1 --test-query "how do I write the university name"
```

Teardown, to stop costs:

```bash
.venv/bin/python scripts/aws/teardown.py --region us-east-1             # preview only
.venv/bin/python scripts/aws/teardown.py --region us-east-1 --yes       # actually delete
.venv/bin/python scripts/aws/teardown.py --region us-east-1 --yes --components kb,vectors  # keep the bucket
```

To query an existing KB without changing anything:

```bash
.venv/bin/python scripts/aws/setup_knowledge_base.py --query-only --test-query "tone for students"
```

Once setup finishes, the backend finds the KB id in Parameter Store on its own. Run the server with
the default `auto` backend and confirm that `/api/rag/health` reports `"backend": "bedrock"`:

```bash
unset UIC_RAG_BACKEND UIC_SSM_ENABLED
.venv/bin/uvicorn backend.api.dev_server:app --reload
```

After re-scraping, run `setup_s3.py --delete-stale` and then `setup_knowledge_base.py` to re-ingest.
Re-run `deploy_rag_api.py` after any code or guideline change so the Lambda gets the new package.

### Deployed RAG API

`deploy_rag_api.py` prints the base URL and stores it in Parameter Store:

```bash
aws ssm get-parameter --name /uic-editorial/rag_api_url --query Parameter.Value --output text
```

Current deployment (workshop account, us-east-1): **https://rtjsllveri.execute-api.us-east-1.amazonaws.com**
(interactive docs at `/docs`). The Lambda serves from the Bedrock KB and falls back to local search
over the bundled `data/guidelines/` if Bedrock fails. The URL changes if the API is deleted and
re-created (e.g. a new workshop account) — re-read it from Parameter Store.

## 5. Configuration

Each setting resolves in this order: **environment variable, then SSM Parameter Store, then
default**. The logic is in `backend/config.py`.

| setting | env var | Parameter Store | default |
|---|---|---|---|
| AWS region | `AWS_REGION` | — | `us-east-1` |
| Knowledge Base ID | `UIC_KB_ID` | `/uic-editorial/knowledge_base_id` | none (local backend) |
| Guidelines bucket | `UIC_GUIDELINES_BUCKET` | `/uic-editorial/guidelines_bucket` | none |
| RAG backend | `UIC_RAG_BACKEND` (`auto`/`bedrock`/`local`) | — | `auto` |
| Log group | `UIC_LOG_GROUP` | — | `/uic-editorial/backend` |
| Local guidelines dir | `UIC_GUIDELINES_DIR` | — | `data/guidelines` |
| Disable SSM lookups | `UIC_SSM_ENABLED=0` | — | enabled |

`UIC_GUIDELINES_DIR` and `UIC_SSM_ENABLED` are local conveniences and are not part of the contract.
Put values in `.env` (it is gitignored) or export them in your shell. Never commit credentials.

## 6. Tests

```bash
.venv/bin/pytest tests/unit -q                         # all unit tests (no AWS; moto/fakes only)
.venv/bin/pytest tests/unit/test_rag_routes.py -q      # HTTP layer only (uses a fake service)
```

`test_rag_routes.py` also checks every `tests/mocks/rag_*.json` against the response models. If
you change the API, update the mocks to match.

## 7. Troubleshooting

| symptom | cause / fix |
|---|---|
| `/api/rag/*` returns `503 "RAG service is not available"` | `backend/services/rag_service.py` failed to import. Run `.venv/bin/python -c "import backend.services.rag_service"` to see the error. |
| Local backend returns empty `results`; `/health` says `"status": "degraded"`, `"chunk_count": 0` | No index was found (`reason` names the path). Run `python -m scripts.scrape_guidelines` and check that `data/guidelines/guidelines_manifest.json` exists (or that `UIC_GUIDELINES_DIR` points to it). |
| `503 "RAG backend unavailable: ..."` | `UIC_RAG_BACKEND=bedrock` with no KB id, or Bedrock failed with the explicit `bedrock` backend (no local fallback). Use the default `auto` backend to fall back to `local`. |
| Health says `"backend": "local"` but you expected Bedrock | No KB id was resolved. Set `UIC_KB_ID`, or check `aws ssm get-parameter --name /uic-editorial/knowledge_base_id`, the credentials and the region. Also make sure `UIC_SSM_ENABLED` is not `0`. |
| Health says `"status": "degraded"` (still HTTP 200) | Bedrock failed and the server is answering from the local fallback. The `reason` field says why. Check the server logs and CloudWatch `/uic-editorial/backend`. |
| Server starts slowly offline | It is trying SSM without network or credentials. Set `UIC_SSM_ENABLED=0`. |
| `AccessDeniedException` from Bedrock | Titan Text Embeddings V2 access is not enabled in that region, or the role is missing `bedrock:Retrieve`. Re-run `setup_base.py`, then `setup_knowledge_base.py`, which narrows the policy to the KB ARN. |
| Ingestion job fails | Check the KB data source in the console. The chunks and `.metadata.json` sidecars must be next to each other under `guidelines/` in S3. Re-run `setup_s3.py --delete-stale`. |
| `ModuleNotFoundError: No module named 'aws_common'` | You ran a script with `-m`. Run it as a file instead: `python scripts/aws/setup_s3.py`. |
| `422` from the API | The request is outside the limits: `query` must be 1–1000 chars, `text` 1–40000, `audience`/`channel` ≤200, `top_k` 1–20, and `category` must be one of `name`, `tone`, `audience`, `editorial`. The response body lists the failing field. |
