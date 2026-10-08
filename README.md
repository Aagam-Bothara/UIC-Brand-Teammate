# UIC Brand Teammate

AI editorial assistant that checks University of Illinois Chicago communications against UIC brand guidelines and rewrites them. Hackathon project (UIC Editorial Assistant, Team 8). Full requirements: [docs/SPEC.md](docs/SPEC.md).

Paste a draft, pick an audience (Students / Faculty / Staff), a channel (Email / Website / Social Media) and up to five rulesets (Brand, Accessibility, Content, Reading Level, Audience Tone). You get:

- side-by-side original vs. revised text, revealed one ruleset at a time
- each change explained with the UIC guideline it comes from, and accept/reject per change
- live brand and accessibility scores with an Approved / Minor / Major Revisions status
- an "Ask the editor" chat for follow-up refinements
- export to clipboard, text or PDF

## Architecture

```
React app (frontend/, Vite)                                   Workstream 4
   │  axios, 3 retries with backoff
   ▼
API Gateway HTTP API → Lambda → FastAPI  (backend/api/main.py)
   ├─ /api/rag/*        RAG service ──► Bedrock Knowledge Base HFJFKHPXI0     WS1
   │                                    (S3 Vectors, Titan Embeddings v2)
   ├─ /api/rules, /api/rules/check, /api/audiences
   │                    rule engine + scoring (rulesets/*.json)              WS2
   ├─ /api/analyze      orchestrator: RAG + rules + rewrite                  I.3
   └─ /api/llm/refine   rewrite service ──► Bedrock Claude (Haiku 4.5 / Sonnet) WS3
```

## Live URLs

| What | URL |
|---|---|
| Backend API (OpenAPI docs at `/docs`) | https://rtjsllveri.execute-api.us-east-1.amazonaws.com |
| Frontend | https://main.d3ax0n8zonbnh0.amplifyapp.com (AWS Amplify; redeploy with `scripts/aws/deploy_frontend.sh`) |

The RAG endpoints are live. The integrated app (`/api/analyze`, `/api/llm/refine`, `/api/rules`, `/api/audiences`) is being deployed to the same URL (Tasks I.3 / I.5).

## Repo layout

```
UIC-Brand-Teammate/
├── backend/
│   ├── api/          # main.py (integrated app), rag_routes, rules_routes, analyze_routes, lambda_app
│   ├── services/     # rag_service (WS1), rule_engine + scoring_service + reading_level (WS2),
│   │                 # llm_service + change_parser (WS3), rewrite_service + orchestrator (I.3)
│   ├── prompts/      # system, rewrite and detection prompt templates (WS3)
│   └── docs/         # LLM_SERVICE, CHANGE_PARSER, INTEGRATION_GUIDE (WS3)
├── frontend/         # React 19 + TypeScript + Vite + Tailwind v4 (WS4)
├── rulesets/         # brand, accessibility, content, reading_level, audience_tone (+ JSON schema)
├── data/guidelines/  # scraped UIC brand guidelines (raw, chunks, manifest)
├── data/demo/        # 24 synthetic drafts from Team8Dataset + validation report
├── scripts/          # guideline scraper, dataset profiling/validation, aws/ deploy + teardown
├── infra/iam/        # IAM policy templates
├── tests/            # backend tests, fixtures, mocks
└── docs/             # SPEC, API contract, checklist, per-workstream docs
```

## Quick start

Backend (Python 3.11+):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/pytest -q                                    # backend tests
.venv/bin/uvicorn backend.api.main:app --reload        # http://127.0.0.1:8000/docs
```

Without AWS credentials the RAG service falls back to local search over `data/guidelines/`. See [docs/RAG_SETUP.md](docs/RAG_SETUP.md) for AWS setup.

Frontend (Node 20+):

```bash
cd frontend
cp .env.example .env.local      # VITE_USE_MOCKS, VITE_API_BASE_URL, VITE_RAG_API_URL
npm install
npm run dev                     # add -- --port 5180 to match the team's local setup
npm test                        # ~170 vitest tests
```

With `VITE_USE_MOCKS=true` (the default) the UI runs fully on mock data, but guideline excerpts still come from the live RAG API. Click **Try a sample ▾** to load a demo draft; the Career Fair email triggers all five rulesets.

## Status

| Workstream | Owner | Status |
|---|---|---|
| 1. RAG & knowledge base | Aagam Bothara | Done, deployed (KB `HFJFKHPXI0`, RAG API live) |
| 2. Rule engine & scoring | Juhi Anand | Merged |
| 3. LLM service, change parser, prompts | Tomas M. | Merged (commit 67ced9b) |
| 4. Frontend | Team 8 | Done (runs on mocks, live switch via env) |
| I.3 / I.5 Integrated backend on Lambda | Team 8 | In progress: deploying `backend/api/main.py` |
| I.6 Amplify frontend deploy | Team 8 | Not started |
| I.7 Dataset validation | Team 8 | 24 drafts validated, 75% status agreement ([data/demo/VALIDATION.md](data/demo/VALIDATION.md)) |

Open decision: SPEC status thresholds match the dataset's status on 79% of 300 rows; a data-fitted rule gives 90%. See [docs/MASTER_CHECKLIST.md](docs/MASTER_CHECKLIST.md) (Notes & Blockers).

## Docs

| Doc | Covers |
|---|---|
| [docs/SPEC.md](docs/SPEC.md) | Requirements |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | Shared API contracts |
| [docs/MASTER_CHECKLIST.md](docs/MASTER_CHECKLIST.md) | Task status, notes, blockers |
| [docs/RAG_SETUP.md](docs/RAG_SETUP.md), [docs/RAG_API.md](docs/RAG_API.md) | WS1 setup and endpoints |
| [docs/RULE_ENGINE.md](docs/RULE_ENGINE.md), [docs/RULESETS.md](docs/RULESETS.md) | WS2 engine, scoring, rules |
| [backend/README.md](backend/README.md), [backend/docs/](backend/docs/) | WS3 Bedrock setup, LLM service, change parser |
| [docs/FRONTEND.md](docs/FRONTEND.md), [frontend/DESIGN.md](frontend/DESIGN.md) | WS4 architecture and design system |
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | How to use the app |
| [data/demo/README.md](data/demo/README.md) | Demo drafts and validation |

## Brand marks

The official UIC logo in `frontend/public/brand/` is a UIC trademark. Confirm usage with UIC Strategic Marketing and Communications (smcs@uic.edu) before any public deployment.

## Team

Aagam Bothara (WS1), Juhi Anand (WS2), Tomas M. (WS3), Team 8 (WS4, integration)
