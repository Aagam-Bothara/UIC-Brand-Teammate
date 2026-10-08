"""HTTP API for Workstream 1 (RAG): guideline retrieval endpoints.

Binding contract: docs/API_CONTRACT.md (Workstream 1 section).

Endpoints (prefix ``/api/rag``):

* ``POST /retrieve`` - free-text search over the UIC brand guidelines.
* ``POST /context``  - guideline context for a draft (used by the orchestrator / LLM service).
* ``GET  /sources``  - the guideline sources that were scraped and indexed.
* ``GET  /health``   - backend status (bedrock | local), KB id and chunk count.

The service is injected through the :func:`get_service` dependency, so tests (and the
integrated app) can swap it with ``app.dependency_overrides[get_service] = ...``.
``backend.services.rag_service`` is imported lazily so this module imports cleanly on its own.

Error mapping: ``ValueError`` -> 422, ``RAGServiceError`` -> 503 ``{"detail": "..."}``.
"""

from __future__ import annotations

import time
from typing import Annotated, Any, Callable, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.logging_utils import get_logger

logger = get_logger("api.rag_routes")

__all__ = [
    "router",
    "get_service",
    "CATEGORIES",
    "RULESETS",
    "AUDIENCES",
    "CHANNELS",
    "RetrieveRequest",
    "ContextRequest",
    "GuidelineChunkModel",
    "RetrievalResponse",
    "SourceEntry",
    "SourcesResponse",
    "HealthResponse",
    "ErrorResponse",
]

# --------------------------------------------------------------------------------------
# Constants (mirrors docs/API_CONTRACT.md)
# --------------------------------------------------------------------------------------

CATEGORIES: tuple[str, ...] = ("name", "tone", "audience", "editorial")
Category = Literal["name", "tone", "audience", "editorial"]

# Spec values (SPEC 1) — documented/used in examples, not enforced (free text is accepted).
RULESETS: tuple[str, ...] = ("brand", "accessibility", "content", "reading_level", "audience_tone")
AUDIENCES: tuple[str, ...] = ("Students", "Faculty", "Staff")
CHANNELS: tuple[str, ...] = ("Email", "Website", "Social Media")

QUERY_MAX_CHARS = 1000
TEXT_MAX_CHARS = 40000
AUDIENCE_MAX_CHARS = 200
TOP_K_MIN, TOP_K_MAX = 1, 20

_EXAMPLE_CHUNK = {
    "chunk_id": "name-boilerplate-002",
    "text": (
        "# Name and boilerplate — University name\n\n"
        "On first reference, use the full name: University of Illinois Chicago. "
        "Do not use \"at\" in the name. UIC is acceptable on second reference."
    ),
    "score": 0.82,
    "source_id": "name-boilerplate",
    "source_title": "Name and boilerplate",
    "source_url": "https://brand.uic.edu/messaging/name-and-boilerplate/",
    "category": "name",
    "section": "University name",
}


# --------------------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------------------


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must contain non-whitespace characters")
    return value


def _not_bool(value: Any) -> Any:
    # Pydantic's lax mode would turn JSON true/false into 1/0; the service rejects bools too.
    if isinstance(value, bool):
        raise ValueError("must be an integer, not a boolean")
    return value


class RetrieveRequest(BaseModel):
    """Free-text search over the indexed UIC brand guidelines."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"query": "how to write the university name", "top_k": 5, "category": "name"},
                {"query": "tone for a registration reminder", "top_k": 3, "audience": "Students"},
                {"query": "serial comma", "top_k": 3},
            ]
        },
    )

    query: str = Field(
        ...,
        min_length=1,
        max_length=QUERY_MAX_CHARS,
        description=f"Natural-language search query (1-{QUERY_MAX_CHARS} characters).",
        examples=["how to write the university name"],
    )
    top_k: int = Field(
        5,
        ge=TOP_K_MIN,
        le=TOP_K_MAX,
        description=f"Maximum number of chunks to return ({TOP_K_MIN}-{TOP_K_MAX}).",
    )
    category: Category | None = Field(
        None,
        description=(
            "Restrict the search to one guideline category (name, tone, audience, editorial). "
            "Takes precedence over `audience`. Omit/null to search all."
        ),
        examples=["name"],
    )
    audience: str | None = Field(
        None,
        max_length=AUDIENCE_MAX_CHARS,
        description=(
            "Optional target audience (free text; spec audiences: Students, Faculty, Staff). "
            "When given without `category`, uses audience-aware retrieval "
            "(`retrieve_guidelines`)."
        ),
        examples=["Students"],
    )

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        return _not_blank(value)

    @field_validator("top_k", mode="before")
    @classmethod
    def _top_k_not_bool(cls, value: Any) -> Any:
        return _not_bool(value)


class ContextRequest(BaseModel):
    """A draft plus its context; returns the guideline chunks most relevant to reviewing it."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "text": (
                        "Hey students! Click here to register for the University of Illinois "
                        "at Chicago spring career fair."
                    ),
                    "audience": "Students",
                    "channel": "Email",
                    "rulesets": ["brand", "accessibility", "reading_level"],
                    "top_k": 8,
                }
            ]
        },
    )

    text: str = Field(
        ...,
        min_length=1,
        max_length=TEXT_MAX_CHARS,
        description=f"The draft content to be reviewed (1-{TEXT_MAX_CHARS} characters).",
    )
    audience: str | None = Field(
        None,
        max_length=AUDIENCE_MAX_CHARS,
        description="Intended audience (free text; spec audiences: Students, Faculty, Staff).",
        examples=["Students"],
    )
    channel: str | None = Field(
        None,
        max_length=200,
        description="Delivery channel (free text; spec channels: Email, Website, Social Media).",
        examples=["Email"],
    )
    rulesets: list[Annotated[str, Field(max_length=50)]] | None = Field(
        None,
        max_length=20,
        description=(
            "Workstream 2 rulesets to check (brand, accessibility, content, reading_level, "
            "audience_tone). Mapped to categories: brand -> name+editorial, accessibility -> "
            "editorial, content -> editorial+audience, reading_level -> tone+audience, "
            "audience_tone -> tone+audience; anything else / empty -> all categories."
        ),
        examples=[["brand", "accessibility", "reading_level"]],
    )
    top_k: int = Field(
        8,
        ge=TOP_K_MIN,
        le=TOP_K_MAX,
        description=f"Maximum number of chunks to return ({TOP_K_MIN}-{TOP_K_MAX}).",
    )

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        return _not_blank(value)

    @field_validator("top_k", mode="before")
    @classmethod
    def _top_k_not_bool(cls, value: Any) -> Any:
        return _not_bool(value)


# --------------------------------------------------------------------------------------
# Response models
# --------------------------------------------------------------------------------------


class GuidelineChunkModel(BaseModel):
    """One retrieved guideline chunk (mirrors ``rag_service.GuidelineChunk``)."""

    model_config = ConfigDict(from_attributes=True, json_schema_extra={"examples": [_EXAMPLE_CHUNK]})

    chunk_id: str = Field(..., description="Stable chunk id, '<source_id>-<NNN>'.")
    text: str = Field(..., description="Chunk text; starts with '# <title> — <section>'.")
    score: float = Field(..., description="Relevance score, higher is better (0..1).")
    source_id: str = Field(..., description="Guideline source id, e.g. 'editorial-style'.")
    source_title: str = Field(..., description="Human-readable source title.")
    source_url: str = Field(..., description="URL of the source guideline page (for citations).")
    category: str = Field(..., description="One of: name, tone, audience, editorial.")
    section: str | None = Field(None, description="Section heading the chunk came from, if any.")


class RetrievalResponse(BaseModel):
    """Response for both ``/retrieve`` and ``/context``."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"results": [_EXAMPLE_CHUNK], "backend": "local", "latency_ms": 12}]
        }
    )

    results: list[GuidelineChunkModel] = Field(..., description="Chunks ordered by descending score.")
    backend: str = Field(..., description="Retrieval backend actually used: 'bedrock' or 'local'.")
    latency_ms: int = Field(..., ge=0, description="Server-side retrieval time in milliseconds.")


class SourceEntry(BaseModel):
    """A guideline source (an entry of ``guidelines_manifest.json`` ``sources``)."""

    model_config = ConfigDict(extra="allow")

    source_id: str = Field(..., description="Source id, e.g. 'editorial-style'.")
    title: str = Field(..., description="Source title.")
    url: str = Field(..., description="Source URL.")
    category: str = Field(..., description="Guideline category.")
    raw_path: str | None = Field(None, description="Path of the raw markdown, relative to data/guidelines/.")
    chunk_count: int | None = Field(None, ge=0, description="Number of chunks produced from this source.")
    sha256: str | None = Field(None, description="SHA-256 of the raw markdown (change detection).")


class SourcesResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "sources": [
                        {
                            "source_id": "name-boilerplate",
                            "title": "Name and boilerplate",
                            "url": "https://brand.uic.edu/messaging/name-and-boilerplate/",
                            "category": "name",
                            "raw_path": "raw/name-boilerplate.md",
                            "chunk_count": 42,
                            "sha256": "9f2c...",
                        }
                    ]
                }
            ]
        }
    )

    sources: list[SourceEntry] = Field(..., description="Indexed guideline sources.")


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [
                {"status": "ok", "backend": "local", "kb_id": None, "chunk_count": 120,
                 "reason": None, "last_backend": "local"},
                {
                    "status": "degraded",
                    "backend": "bedrock",
                    "kb_id": "ABCDEFGHIJ",
                    "chunk_count": 120,
                    "reason": "bedrock unavailable; serving from local fallback",
                    "last_backend": "local",
                },
            ]
        },
    )

    status: Literal["ok", "degraded"] = Field(..., description="'ok' or 'degraded'.")
    backend: str = Field(..., description="Backend in use: 'bedrock' or 'local'.")
    kb_id: str | None = Field(None, description="Bedrock Knowledge Base id, null for the local backend.")
    chunk_count: int | None = Field(None, ge=0, description="Number of indexed chunks, if known.")
    reason: str | None = Field(
        None, description="Why status is 'degraded' (e.g. Bedrock fallback); null when ok."
    )
    last_backend: str | None = Field(
        None,
        description="Backend that served the most recent retrieval ('local' after an auto-mode "
        "Bedrock fallback); null if unknown.",
    )


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable error message.")

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"detail": "RAG backend unavailable: Bedrock throttled"}]}
    )


# --------------------------------------------------------------------------------------
# Dependency + error mapping
# --------------------------------------------------------------------------------------


def _is_rag_service_error(exc: BaseException) -> bool:
    """True if ``exc`` is a ``RAGServiceError``.

    Matched by class name across the MRO so this module never has to import
    ``backend.services.rag_service`` at import time (and fakes in tests can define their own).
    """
    return any(cls.__name__ == "RAGServiceError" for cls in type(exc).__mro__)


def get_service() -> Any:
    """FastAPI dependency returning the process-wide ``RAGService``.

    Override in tests / the integrated app via ``app.dependency_overrides[get_service]``.
    """
    try:
        from backend.services.rag_service import get_rag_service  # lazy import
    except ImportError as exc:  # pragma: no cover - only before rag_service.py exists
        logger.error("RAG service module unavailable: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG service is not available",
        ) from exc
    try:
        return get_rag_service()
    except Exception as exc:
        if _is_rag_service_error(exc):
            logger.error("RAG service failed to initialise: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"RAG backend unavailable: {exc}",
            ) from exc
        raise


ServiceDep = Annotated[Any, Depends(get_service)]

T = TypeVar("T")


def _call(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Invoke a service method, mapping ValueError -> 422 and RAGServiceError -> 503."""
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if _is_rag_service_error(exc):
            logger.warning("RAG backend error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"RAG backend unavailable: {exc}",
            ) from exc
        raise


def _to_response(chunks: list[Any], service: Any, started: float) -> RetrievalResponse:
    return RetrievalResponse(
        results=[GuidelineChunkModel.model_validate(c) for c in chunks],
        backend=str(getattr(service, "backend", "unknown")),
        latency_ms=int(round((time.perf_counter() - started) * 1000)),
    )


# --------------------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------------------

_ERRORS: dict[int | str, dict[str, Any]] = {
    503: {"model": ErrorResponse, "description": "Retrieval backend unavailable (Bedrock/local index failure)."},
}

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post(
    "/retrieve",
    response_model=RetrievalResponse,
    summary="Search the UIC brand guidelines",
    description=(
        "Semantic (Bedrock Knowledge Base) or BM25 (local) search over the scraped UIC brand "
        "guidelines. Results are ordered by descending `score`.\n\n"
        "Dispatch: `category` given -> `retrieve(query, top_k, category)`; else `audience` "
        "given -> `retrieve_guidelines(query, audience, top_k)`; else `retrieve(query, top_k)`. "
        "Categories: `name`, `tone`, `audience`, `editorial`."
    ),
    responses=_ERRORS,
)
def retrieve(body: RetrieveRequest, service: ServiceDep) -> RetrievalResponse:
    started = time.perf_counter()
    if body.category is not None:
        chunks = _call(service.retrieve, body.query, top_k=body.top_k, category=body.category)
    elif body.audience is not None:
        chunks = _call(service.retrieve_guidelines, body.query, audience=body.audience, top_k=body.top_k)
    else:
        chunks = _call(service.retrieve, body.query, top_k=body.top_k)
    return _to_response(chunks, service, started)


@router.post(
    "/context",
    response_model=RetrievalResponse,
    summary="Guideline context for a draft",
    description=(
        "Returns the guideline chunks most relevant to reviewing `text` for the given audience, "
        "channel and rulesets. Used by the orchestrator / LLM service to ground suggestions. "
        "Response shape is identical to `/retrieve`."
    ),
    responses=_ERRORS,
)
def context(body: ContextRequest, service: ServiceDep) -> RetrievalResponse:
    started = time.perf_counter()
    chunks = _call(
        service.retrieve_for_text,
        body.text,
        audience=body.audience,
        channel=body.channel,
        rulesets=body.rulesets,
        top_k=body.top_k,
    )
    return _to_response(chunks, service, started)


@router.get(
    "/sources",
    response_model=SourcesResponse,
    summary="List indexed guideline sources",
    description="The guideline pages that were scraped and indexed (from `guidelines_manifest.json`).",
    responses=_ERRORS,
)
def sources(service: ServiceDep) -> SourcesResponse:
    return SourcesResponse(sources=[SourceEntry.model_validate(s) for s in _call(service.list_sources)])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="RAG backend health",
    description=(
        "Reports `status` (`ok`/`degraded`), the backend in use, the KB id, the chunk count and, "
        "when degraded, a `reason`. A degraded backend still returns **200**; 503 is returned "
        "only when the service cannot answer at all."
    ),
    responses=_ERRORS,
)
def health(service: ServiceDep) -> HealthResponse:
    return HealthResponse.model_validate(_call(service.health))
