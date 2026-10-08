# RAG API Reference (Workstream 1)

This file is a readable companion to [`API_CONTRACT.md`](API_CONTRACT.md), which is binding.
Setup instructions are in [`RAG_SETUP.md`](RAG_SETUP.md).

- **HTTP router:** `backend/api/rag_routes.py`. It is a FastAPI `APIRouter` with prefix `/api/rag` and tag `rag`.
- **Standalone dev server:** `.venv/bin/uvicorn backend.api.dev_server:app --reload`. Interactive docs are at `/docs`.
- **Integrated app:** `backend/api/main.py` (Task I.3) mounts the same router.
- **Deployed (AWS Lambda + API Gateway):** `https://rtjsllveri.execute-api.us-east-1.amazonaws.com`
  (docs at `/docs`; current value always in Parameter Store `/uic-editorial/rag_api_url`).
  Lambda entrypoint: `backend/api/lambda_app.py`; deploy with `scripts/aws/deploy_rag_api.py`.

| method | path | purpose |
|---|---|---|
| POST | `/api/rag/retrieve` | Free-text search over the guidelines |
| POST | `/api/rag/context` | Guideline context for a draft (orchestrator / LLM service) |
| GET | `/api/rag/sources` | Indexed guideline sources |
| GET | `/api/rag/health` | Backend status |

**Spec values:**

| | values | enforced? |
|---|---|---|
| Categories | `name` (Name and boilerplate), `tone` (Voice and tone), `audience` (Brand strategy), `editorial` (Editorial and style guide) | yes (422 if unknown) |
| Rulesets | `brand`, `accessibility`, `content`, `reading_level`, `audience_tone` | no (unknown values search all categories) |
| Audiences | `Students`, `Faculty`, `Staff` | no (free text, ≤200 chars) |
| Channels | `Email`, `Website`, `Social Media` | no (free text, ≤200 chars) |

**Limits:**
- `query` is 1–1000 chars.
- `text` is 1–40000 chars (about 5,000 words).
- `audience` and `channel` are at most 200 chars each.
- Strings that are only whitespace are rejected.
- `top_k` is 1–20.
- Unknown request fields are rejected with 422.

---

## Result chunk

Each item in `results` has this shape:

```json
{
  "chunk_id": "name-boilerplate-002",
  "text": "# Name and boilerplate — University name\n\nOn first reference, use the full name ...",
  "score": 0.91,
  "source_id": "name-boilerplate",
  "source_title": "Name and boilerplate",
  "source_url": "https://brand.uic.edu/messaging/name-and-boilerplate/",
  "category": "name",
  "section": "University name"
}
```

- `results` are sorted by `score`, highest first. Higher means more relevant. Scores are in 0..1 (Bedrock similarity, or normalized BM25 for the local backend). The two backends score differently, so compare scores only within one response.
- `text` always starts with `# <source_title> — <section>`, so each chunk can stand alone in a prompt.
- `section` may be `null`.
- Use `source_url` and `source_title` for citations in the UI.

## POST /api/rag/retrieve

| field | type | default | notes |
|---|---|---|---|
| `query` | string | required | 1–1000 chars |
| `top_k` | int | 5 | 1–20 (JSON booleans are rejected) |
| `category` | string \| null | null | `name` \| `tone` \| `audience` \| `editorial`; null searches all |
| `audience` | string \| null | null | e.g. `Students`, `Faculty`, `Staff` (≤200 chars) |

The endpoint picks a service method from the fields you send:

| request | service call |
|---|---|
| `category` given | `retrieve(query, top_k, category)` |
| no `category`, `audience` given | `retrieve_guidelines(query, audience, top_k)` (audience-aware, searches all categories) |
| neither | `retrieve(query, top_k)` |

```bash
curl -s -X POST http://127.0.0.1:8000/api/rag/retrieve \
  -H 'content-type: application/json' \
  -d '{"query": "how to write the university name", "top_k": 3, "category": "name"}'

curl -s -X POST http://127.0.0.1:8000/api/rag/retrieve \
  -H 'content-type: application/json' \
  -d '{"query": "tone for a registration reminder", "audience": "Students"}'
```

```json
{
  "results": [ { "chunk_id": "name-boilerplate-002", "score": 0.91, "...": "..." } ],
  "backend": "local",
  "latency_ms": 11
}
```

- `backend` is the backend that was actually used (`bedrock` or `local`).
- `latency_ms` is the time spent on the server.
- Full example: `tests/mocks/rag_retrieve_response.json`. Example request: `tests/mocks/rag_retrieve_request.json`.

## POST /api/rag/context

The orchestrator and LLM service use this endpoint to ground suggestions in the guidelines.

| field | type | default | notes |
|---|---|---|---|
| `text` | string | required | the draft, 1–40000 chars |
| `audience` | string \| null | null | `Students`, `Faculty`, `Staff` (free text, ≤200 chars) |
| `channel` | string \| null | null | `Email`, `Website`, `Social Media` (free text, ≤200 chars) |
| `rulesets` | string[] \| null | null | Workstream 2 rulesets (see the mapping below) |
| `top_k` | int | 8 | 1–20 |

Each ruleset searches these categories:

| ruleset | categories |
|---|---|
| `brand` | name, editorial |
| `accessibility` | editorial |
| `content` | editorial, audience |
| `reading_level` | tone, audience |
| `audience_tone` | tone, audience |
| other / empty | all |

The service builds several queries from the draft, audience, channel and rulesets. It retrieves for
each relevant category, removes duplicates by `chunk_id`, and returns the `top_k` chunks with the
highest scores.

```bash
curl -s -X POST http://127.0.0.1:8000/api/rag/context \
  -H 'content-type: application/json' \
  -d @tests/mocks/rag_context_request.json
```

The response has the same shape as `/retrieve`. The mock pair is:

- `tests/mocks/rag_context_request.json`: a draft email to Students, with rulesets `brand`, `accessibility` and `reading_level`. The draft has several problems: "University of Illinois at Chicago", "Click here", "Hey guys", an image with no alt text, "March 5th" and "12pm".
- `tests/mocks/rag_context_response.json`: the 8 chunks a good retrieval should return for that draft. They cover the university name, link text, tone by audience, the student audience, dates and times, brand attributes, alt text and key messages.

## GET /api/rag/sources

```bash
curl -s http://127.0.0.1:8000/api/rag/sources
```

```json
{"sources": [{"source_id": "name-boilerplate", "title": "Name and boilerplate",
  "url": "https://brand.uic.edu/messaging/name-and-boilerplate/", "category": "name",
  "raw_path": "raw/name-boilerplate.md", "chunk_count": 14, "sha256": "..."}]}
```

The entries are the manifest's `sources`. Any extra manifest fields are passed through unchanged.
Mock: `tests/mocks/rag_sources_response.json`.

## GET /api/rag/health

```bash
curl -s http://127.0.0.1:8000/api/rag/health
```

```json
{"status": "ok", "backend": "local", "kb_id": null, "chunk_count": 120, "reason": null,
 "last_backend": "local"}
```

- `status` is `ok` or `degraded`. A degraded backend still returns **HTTP 200**. In that case `reason` explains why, for example that Bedrock failed and the local fallback answered. `reason` is `null` when the status is `ok`.
- `backend` is the configured backend. `last_backend` is the backend that served the most recent retrieval (`local` after a Bedrock fallback).
- `kb_id` and `chunk_count` may be `null`. `kb_id` is `null` for the local backend.
- A missing or empty local index is reported here as `degraded` (`chunk_count: 0`); retrieval then returns `200` with empty `results`, not `503`.
- The endpoint returns 503 only when the service cannot report its health at all.
- Mock: `tests/mocks/rag_health_response.json`.

## Errors

| status | when | body |
|---|---|---|
| 422 | The request fails validation (FastAPI default), or the service raised `ValueError` | **Two shapes.** Request validation returns `detail` as a list of `{loc, msg, type}` objects. A service `ValueError` returns `detail` as a string. Clients should handle both. |
| 503 | The backend is unavailable: `RAGServiceError`, the service cannot be initialised, or `rag_service` cannot be imported | `{"detail": "RAG backend unavailable: <reason>"}` |
| 500 | Unexpected bug (not masked) | — |

On a 503, clients should show a non-blocking "guidelines unavailable" state. They should not fail the whole review.

---

## In-process Python interface

The orchestrator (Task I.3) and the LLM service run in the same process as the API. They should
call the service directly instead of going over HTTP:

```python
from backend.services.rag_service import get_rag_service, RAGServiceError, GuidelineChunk

rag = get_rag_service()          # process-wide singleton; backend picked from config
print(rag.backend)               # "bedrock" | "local"

try:
    chunks: list[GuidelineChunk] = rag.retrieve_for_text(
        draft_text,
        audience="Students",
        channel="Email",
        rulesets=["brand", "accessibility", "reading_level"],
        top_k=8,
    )
except ValueError:
    ...                          # bad input (empty text, unknown category, ...)
except RAGServiceError:
    chunks = []                  # backend down; continue without guideline context

prompt_context = "\n\n---\n\n".join(c.text for c in chunks)          # each chunk names its source
citations = {c.source_url: c.source_title for c in chunks}
```

Other methods:

- `rag.retrieve(query, top_k=5, category=None)`
- `rag.retrieve_guidelines(query, audience=None, top_k=5)` (SPEC 1 name; audience-aware). `Guideline` is an alias of `GuidelineChunk`.
- `rag.list_sources()`
- `rag.health()`

`rag.backend` reflects a fallback after each call. `GuidelineChunk` is a dataclass with the same fields as the JSON result chunk. To get a dict, use
`dataclasses.asdict(chunk)`.

Mounting the router in the integrated app (Task I.3):

```python
from backend.api.rag_routes import router as rag_router
app.include_router(rag_router)
```

To test against a fake service, override the dependency:

```python
from backend.api.rag_routes import get_service
app.dependency_overrides[get_service] = lambda: FakeRAGService()
```

`tests/unit/test_rag_routes.py` has a full example of a fake service.

## Mocks for Workstreams 2–4

The mocks in `tests/mocks/` let you build before the backend is live:

| file | what |
|---|---|
| `rag_retrieve_request.json` / `rag_retrieve_response.json` | `/retrieve` for "how to write the university name" (`category: name`) |
| `rag_context_request.json` / `rag_context_response.json` | `/context` for a sample email to Students |
| `rag_sources_response.json` | `/sources` (4 sources, 120 chunks) |
| `rag_health_response.json` | `/health` (local backend) |

The guideline text in the mocks is illustrative and written in UIC style. It is not quoted
verbatim from brand.uic.edu. The real text comes from the scraper. A unit test validates every mock
against the response models, so the mocks always match the API.
