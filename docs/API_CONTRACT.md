# API Contract

Shared contract between workstreams (Task I.1). Each workstream owns its section.
Status: **Workstream 1 (RAG) — draft, pending team sign-off.** Workstreams 2–4 add their sections below.

---

## Workstream 1: RAG & Knowledge Infrastructure

### Guideline sources

The 4 pages named in SPEC 1 ("RAG Scope: All 4 UIC brand guideline pages"). Two of the spec's URLs
now 404 on brand.uic.edu; they were renamed and the live equivalents are used:

| source_id | category | URL | spec name |
|---|---|---|---|
| `name-boilerplate` | `name` | https://brand.uic.edu/messaging/name-and-boilerplate/ | Name and boilerplate |
| `voice-tone` | `tone` | https://brand.uic.edu/messaging/voice-and-tone/ | Brand attributes and tone (old URL 404s) |
| `brand-strategy` | `audience` | https://brand.uic.edu/messaging/brand-strategy/ | Key audience and messaging (old URL 404s) |
| `editorial-style` | `editorial` | https://brand.uic.edu/messaging/editorial-and-style-guide/ | Editorial and style guide |

`category` is one of: `name`, `tone`, `audience`, `editorial`.

### Rulesets, audiences, channels (from SPEC 1)

- Rulesets (5): `brand`, `accessibility`, `content`, `reading_level`, `audience_tone`
- Audiences (3): `Students`, `Faculty`, `Staff`
- Channels (3): `Email`, `Website`, `Social Media`

### Ruleset → category mapping

Used by `retrieve_for_text` to decide which guideline categories are relevant.

| ruleset (Workstream 2) | categories searched |
|---|---|
| `brand` | `name`, `editorial` |
| `accessibility` | `editorial` |
| `content` | `editorial`, `audience` |
| `reading_level` | `tone`, `audience` |
| `audience_tone` | `tone`, `audience` |
| anything else / empty | all categories |

### On-disk layout (produced by `scripts/scrape_guidelines.py`)

```
data/guidelines/
├── raw/<source_id>.md                         # full page converted to markdown
├── chunks/<source_id>-<NNN>.md                # one chunk per file (what S3 / Bedrock KB ingests)
├── chunks/<source_id>-<NNN>.md.metadata.json  # Bedrock KB metadata sidecar
└── guidelines_manifest.json
```

Chunk `.metadata.json` sidecar (Bedrock KB format):

```json
{"metadataAttributes": {"source_id": "editorial-style", "category": "editorial",
  "title": "Editorial and style guide", "url": "https://...", "section": "Capitalization"}}
```

`guidelines_manifest.json`:

```json
{
  "generated_at": "2026-10-08T12:00:00Z",
  "sources": [
    {"source_id": "editorial-style", "title": "Editorial and style guide", "url": "https://...",
     "category": "editorial", "raw_path": "raw/editorial-style.md", "chunk_count": 42, "sha256": "..."}
  ],
  "chunks": [
    {"chunk_id": "editorial-style-001", "source_id": "editorial-style", "category": "editorial",
     "title": "Editorial and style guide", "url": "https://...", "section": "Capitalization",
     "path": "chunks/editorial-style-001.md", "text": "...", "char_count": 812}
  ]
}
```

Chunking: split on markdown headings, then pack to ~1,000 characters max (never split mid-sentence),
~100 characters overlap. Each chunk's text starts with `# <title> — <section>` so it is self-describing.

### Python interface — `backend/services/rag_service.py`

```python
@dataclass
class GuidelineChunk:
    chunk_id: str
    text: str
    score: float            # higher = more relevant; 0..1 for bedrock, normalized 0..1 for local
    source_id: str
    source_title: str
    source_url: str
    category: str
    section: str | None

Guideline = GuidelineChunk   # SPEC 1 name for the result type

class RAGService:
    def __init__(self, backend: str | None = None, *, kb_id: str | None = None,
                 region: str | None = None, guidelines_dir: str | Path | None = None): ...
        # backend: "bedrock" | "local" | None (auto: bedrock if a KB id is configured, else local)

    backend: str  # the backend actually in use

    def retrieve(self, query: str, top_k: int = 5,
                 category: str | None = None) -> list[GuidelineChunk]: ...

    def retrieve_for_text(self, text: str, audience: str | None = None,
                          channel: str | None = None, rulesets: list[str] | None = None,
                          top_k: int = 8) -> list[GuidelineChunk]: ...
        # Builds several queries from the draft text + audience/channel + rulesets,
        # retrieves per relevant category, de-duplicates by chunk_id, returns top_k by score.

    def retrieve_guidelines(self, query: str, audience: str | None = None,
                            top_k: int = 5) -> list[Guideline]: ...
        # SPEC 1 interface for Workstream 1. Audience-aware retrieve across all categories:
        # adds an audience hint to the query and also pulls the best `audience` category
        # chunk for that audience. Same result type as retrieve().

    def list_sources(self) -> list[dict]: ...   # manifest "sources" entries
    def health(self) -> dict: ...               # {"status": "ok"|"degraded", "backend": ..., "kb_id": ..., "chunk_count": ...}

class RAGServiceError(Exception): ...
```

Errors: invalid input → `ValueError`. Backend failure after retries → `RAGServiceError`.
In `auto` mode a Bedrock failure falls back to the local backend and logs a warning.

### Configuration — `backend/config.py`

Values resolve in order: environment variable → SSM Parameter Store → default.

| setting | env var | Parameter Store | default |
|---|---|---|---|
| AWS region | `AWS_REGION` | — | `us-east-1` |
| Knowledge Base ID | `UIC_KB_ID` | `/uic-editorial/knowledge_base_id` | none (→ local backend) |
| Guidelines bucket | `UIC_GUIDELINES_BUCKET` | `/uic-editorial/guidelines_bucket` | none |
| RAG backend | `UIC_RAG_BACKEND` | — | `auto` |
| Log group | `UIC_LOG_GROUP` | — | `/uic-editorial/backend` |

### HTTP endpoints — `backend/api/rag_routes.py` (FastAPI `APIRouter`, prefix `/api/rag`)

**`POST /api/rag/retrieve`**

```json
// request
{"query": "how to write the university name", "top_k": 5, "category": "name", "audience": "Students"}
// response 200
{"results": [{"chunk_id": "editorial-style-003", "text": "...", "score": 0.82,
              "source_id": "name-boilerplate", "source_title": "Name and boilerplate",
              "source_url": "https://...", "category": "name", "section": "University name"}],
 "backend": "local", "latency_ms": 12}
```

**`POST /api/rag/context`** — used by the orchestrator / LLM service

```json
// request
{"text": "<draft>", "audience": "Students", "channel": "Email",
 "rulesets": ["brand", "accessibility", "reading_level"], "top_k": 8}
// response 200: same shape as /retrieve
```

**`GET /api/rag/sources`** → `{"sources": [ ...manifest source entries... ]}`

**`GET /api/rag/health`** → `{"status": "ok", "backend": "local", "kb_id": null, "chunk_count": 120}`

Errors: `422` for validation errors (FastAPI default), `503` with `{"detail": "..."}` when the backend is unavailable.

`/retrieve` dispatch: `category` given → `retrieve(query, top_k, category)`; else `audience` given → `retrieve_guidelines(query, audience, top_k)`; else `retrieve(query, top_k)`. `audience` is optional free text (max 200 chars); the 3 spec audiences are `Students`, `Faculty`, `Staff`.

Limits: `query` 1–1000 chars, `text` 1–40000 chars (~5,000 words, SPEC FR-1), `top_k` 1–20, `category` must be a known category.

Mocks: `tests/mocks/rag_retrieve_response.json`, `tests/mocks/rag_context_response.json`,
`tests/mocks/rag_sources_response.json`, `tests/mocks/rag_health_response.json`.

## Analyze API (integrated backend)

`POST /api/analyze` and `POST /api/llm/refine` are served by `backend/api/main.py` (same Lambda/URL as the RAG API).
The binding request/response shapes are **`frontend/src/types/api.ts`** (`AnalyzeRequest`, `AnalyzeResponse`,
`Change`, `Issue`, `Scores`, `RefineRequest`, `RefineResponse`); offsets are JS UTF-16 indexes. Details, model
selection and fallback behaviour: [ANALYZE_API.md](ANALYZE_API.md).
