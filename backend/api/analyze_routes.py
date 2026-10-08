"""HTTP API for the integrated analysis (Task I.3): ``POST /api/analyze`` and ``POST /api/llm/refine``.

Shapes are binding: ``frontend/src/types/api.ts`` (AnalyzeRequest/AnalyzeResponse, RefineRequest/
RefineResponse). See docs/ANALYZE_API.md.

Audience / channel are accepted in the frontend's Title case ("Students", "Social Media") and in
WS2's lowercase form ("students", "social_media"); responses always use Title case.

Error mapping (same convention as rag_routes): invalid input -> 422 ``{"detail": ...}``; rule engine
unavailable (rulesets missing) or RAG backend error -> 503. Bedrock failures do NOT fail the request:
the response falls back to rule-based changes with ``model_used = "rules-fallback"``.

The orchestrator functions are injected via :func:`get_analyzer` / :func:`get_refiner` so tests can
override them with ``app.dependency_overrides``.
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.logging_utils import get_logger

logger = get_logger("api.analyze_routes")

RulesetId = Literal["brand", "accessibility", "content", "reading_level", "audience_tone"]
AudienceT = Literal["Students", "Faculty", "Staff"]
ChannelT = Literal["Email", "Website", "Social Media"]
SeverityT = Literal["high", "medium", "low"]
StatusT = Literal["Approved", "Minor Revisions Needed", "Major Revisions Needed"]

ALL_RULESETS: list[str] = ["brand", "accessibility", "content", "reading_level", "audience_tone"]
TEXT_MAX_CHARS = 40000  # ~5,000 words (SPEC FR-1); the rule engine enforces the word limit
MESSAGE_MAX_CHARS = 2000

_AUDIENCE = {"students": "Students", "faculty": "Faculty", "staff": "Staff"}
_CHANNEL = {"email": "Email", "website": "Website", "social_media": "Social Media",
            "social media": "Social Media", "social-media": "Social Media"}

SAMPLE_TEXT = ("Hey guys!\n\nThe University of Illinois at Chicago Career Services office will host the Fall "
               "Career Fair on March 5th from 12pm to 4pm in the Student Center East. In order to prepare, "
               "students should utilize the resume review sessions prior to the event.\n\n"
               "Click here to register ASAP. For more info, email careers@uic.edu.")


def _audience(v: Any) -> Any:
    return _AUDIENCE.get(v.strip().lower(), v) if isinstance(v, str) else v


def _channel(v: Any) -> Any:
    return _CHANNEL.get(v.strip().lower(), v) if isinstance(v, str) else v


def _not_blank(v: str) -> str:
    if not v.strip():
        raise ValueError("must contain non-whitespace characters")
    return v


# --------------------------------------------------------------------------------- models


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "text": SAMPLE_TEXT, "audience": "Students", "channel": "Email", "rulesets": ALL_RULESETS}]})

    text: str = Field(..., min_length=1, max_length=TEXT_MAX_CHARS, description="Draft to analyze.")
    audience: AudienceT = Field("Students", description="Students | Faculty | Staff (lowercase accepted).")
    channel: ChannelT = Field("Email", description="Email | Website | Social Media (social_media accepted).")
    rulesets: list[RulesetId] = Field(default_factory=lambda: list(ALL_RULESETS),
                                      description="Rulesets to apply; empty/omitted = all five.")

    v_text = field_validator("text")(_not_blank)
    v_aud = field_validator("audience", mode="before")(_audience)
    v_ch = field_validator("channel", mode="before")(_channel)


class IssueModel(BaseModel):
    issue_id: str
    ruleset: RulesetId
    rule_id: str
    severity: SeverityT
    message: str
    start: int = Field(description="UTF-16 offset into `original` (inclusive)")
    end: int = Field(description="UTF-16 offset into `original` (exclusive)")
    excerpt: str
    suggestion: Optional[str] = None
    guideline_url: Optional[str] = None
    guideline_title: Optional[str] = None
    scope: Literal["span", "document"] = "span"
    rule_name: Optional[str] = None


class ChangeModel(BaseModel):
    change_id: str
    ruleset: RulesetId
    original_start: int = Field(description="UTF-16 offset into `original`")
    original_end: int = Field(description="UTF-16 offset into `original`")
    original_text: str
    rewritten_text: str
    explanation: str
    issue_ids: list[str]
    guideline_url: Optional[str] = None
    guideline_title: Optional[str] = None


class GuidelineChunkModel(BaseModel):
    chunk_id: str
    text: str
    score: float
    source_id: str
    source_title: str
    source_url: str
    category: str
    section: Optional[str] = None


class ReadingLevelModel(BaseModel):
    grade: float
    target: float
    audience: AudienceT


class ScoresModel(BaseModel):
    brand: int
    accessibility: int
    reading_level: ReadingLevelModel
    total_issues: int
    status: StatusT


class AnalyzeResponse(BaseModel):
    analysis_id: str
    original: str
    rewritten: str = Field(description="`original` with ALL changes applied.")
    changes: list[ChangeModel]
    issues: list[IssueModel]
    scores: ScoresModel
    guidelines: list[GuidelineChunkModel]
    audience: AudienceT
    channel: ChannelT
    rulesets: list[RulesetId]
    model_used: str = Field(description="Bedrock model id, or 'rules-fallback' when Bedrock was unavailable.")
    latency_ms: int


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class RefineRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "message": "How do I write the university's name?", "original": SAMPLE_TEXT,
        "current_text": SAMPLE_TEXT, "audience": "Students", "channel": "Email", "rulesets": ALL_RULESETS,
        "history": [], "analysis_id": None}]})

    message: str = Field(..., min_length=1, max_length=MESSAGE_MAX_CHARS)
    # Empty when the user chats before pasting a draft (style questions).
    original: str = Field("", max_length=TEXT_MAX_CHARS)
    current_text: str = Field("", max_length=TEXT_MAX_CHARS * 2)
    audience: AudienceT = "Students"
    channel: ChannelT = "Email"
    rulesets: list[RulesetId] = Field(default_factory=lambda: list(ALL_RULESETS))
    history: list[ChatTurn] = Field(default_factory=list)
    analysis_id: Optional[str] = None

    v_msg = field_validator("message")(_not_blank)
    v_aud = field_validator("audience", mode="before")(_audience)
    v_ch = field_validator("channel", mode="before")(_channel)


class RefineResponse(BaseModel):
    reply: str
    analysis: Optional[AnalyzeResponse] = None
    guidelines: list[GuidelineChunkModel] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    detail: str


# --------------------------------------------------------------------------------- deps


def get_analyzer() -> Callable[..., dict]:
    from backend.services.orchestrator import analyze
    return analyze


def get_refiner() -> Callable[..., dict]:
    from backend.services.orchestrator import refine
    return refine


def _is_named(exc: BaseException, *names: str) -> bool:
    return any(cls.__name__ in names for cls in type(exc).__mro__)


def _run(fn: Callable[..., dict], payload: dict) -> dict:
    try:
        return fn(payload)
    except HTTPException:
        raise
    except ValueError as exc:  # includes TextTooLongError
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        if _is_named(exc, "UnknownRulesetError"):
            raise HTTPException(status_code=422, detail=f"Unknown ruleset {exc.args[0]!r}") from exc
        if _is_named(exc, "AnalysisUnavailableError", "RAGServiceError", "RulesetValidationError"):
            logger.error("analysis backend unavailable: %s", exc)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                                detail=f"Analysis backend unavailable: {exc}") from exc
        raise


_ERRORS: dict[int | str, dict[str, Any]] = {
    422: {"description": "Invalid request (blank/too-long text, unknown audience/channel/ruleset)."},
    503: {"model": ErrorResponse, "description": "Rule engine or retrieval backend unavailable."},
}

router = APIRouter(tags=["analyze"])


@router.post("/api/analyze", response_model=AnalyzeResponse, responses=_ERRORS,
             summary="Analyze and rewrite a draft",
             description="Runs the rule engine (WS2) and guideline retrieval (WS1) in parallel, then asks "
                         "Claude on Bedrock for surgical, ruleset-tagged edits (Haiku for short/simple drafts, "
                         "Sonnet otherwise). Offsets are UTF-16 indexes into `original`.")
def analyze_endpoint(body: AnalyzeRequest,
                     analyzer: Annotated[Callable[..., dict], Depends(get_analyzer)]) -> dict:
    return _run(analyzer, body.model_dump())


@router.post("/api/llm/refine", response_model=RefineResponse, responses=_ERRORS,
             summary="Chat: answer a question or refine the rewrite",
             description="Questions get a short answer citing a UIC guideline (`> quote` + source URL). "
                         "Change requests (\"make it more formal\") re-run the analysis on `original` with the "
                         "instruction and return the new `analysis`.")
def refine_endpoint(body: RefineRequest,
                    refiner: Annotated[Callable[..., dict], Depends(get_refiner)]) -> dict:
    return _run(refiner, body.model_dump())
