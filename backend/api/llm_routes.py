"""FastAPI routes for LLM rewriting, refinement, and change explanations.

Task 3.8 keeps HTTP concerns separate from the Bedrock-facing service.  The
service dependency is intentionally lazy so importing this module (including
OpenAPI generation and unit tests) never creates an AWS client.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from pydantic import AliasChoices, BaseModel, Field, model_validator

from backend.services.change_parser import ChangeParser, ChangeParserError
from backend.services.llm_service import LLMResponse, LLMService, LLMServiceError
from backend.services.models import Audience, Channel
from backend.services.refinement import RefinementValidationError
from backend.services.text_diff import TextDiffError, TextDiffer


MAX_WORDS = 5_000
VALID_RULESETS = {
    "BRAND",
    "ACCESSIBILITY",
    "CONTENT",
    "READING_LEVEL",
    "AUDIENCE_TONE",
}

RULESET_RATIONALES = {
    "BRAND": "aligns the wording with UIC names, terminology, and brand guidance",
    "ACCESSIBILITY": "makes the message clearer and easier to understand",
    "CONTENT": "improves correctness, precision, or concision",
    "READING_LEVEL": "brings sentence structure and vocabulary closer to the audience's target reading level",
    "AUDIENCE_TONE": "better matches the expected tone for the selected audience",
}

router = APIRouter(prefix="/api/llm", tags=["llm"])


class Guideline(BaseModel):
    """A RAG-provided guideline excerpt passed through to the LLM."""

    title: str = "UIC guideline"
    text: str = Field(
        min_length=1,
        validation_alias=AliasChoices("text", "content"),
        description="Retrieved guideline excerpt (also accepts `content`)",
    )
    source_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("source_url", "url"),
        description="Guideline source (also accepts `url`)",
    )


class RewriteRequest(BaseModel):
    original_text: str = Field(min_length=1, description=f"Source text (maximum {MAX_WORDS} words)")
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    guidelines: List[Guideline] = Field(default_factory=list)
    audience: Audience = Audience.STUDENTS
    channel: Channel = Channel.EMAIL

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "original_text": "The University of Illinois at Chicago welcomes you!",
                "issues": [{"ruleset_id": "brand", "message": "Use the current university name."}],
                "guidelines": [{
                    "title": "UIC Editorial Style Guide",
                    "content": "Use University of Illinois Chicago on first reference.",
                    "url": "https://today.uic.edu/uic-editorial-style-guide/",
                }],
                "audience": "students",
                "channel": "email",
            }]
        }
    }

    @model_validator(mode="after")
    def validate_text(self):
        _validate_document(self.original_text, "original_text")
        return self


class RefineRequest(BaseModel):
    current_text: str = Field(min_length=1, description=f"Current text (maximum {MAX_WORDS} words)")
    refinement_request: str = Field(min_length=1, max_length=2_000)
    audience: Audience = Audience.STUDENTS
    channel: Channel = Channel.EMAIL
    context: Optional[str] = Field(default=None, max_length=10_000)
    selection_start: Optional[int] = Field(default=None, ge=0)
    selection_end: Optional[int] = Field(default=None, ge=0)

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "current_text": "Students should submit the form before Friday.",
                "refinement_request": "Make this warmer and more concise.",
                "audience": "students",
                "channel": "email",
            }]
        }
    }

    @model_validator(mode="after")
    def validate_input(self):
        _validate_document(self.current_text, "current_text")
        if not self.refinement_request.strip():
            raise ValueError("refinement_request must not be blank")
        if (self.selection_start is None) != (self.selection_end is None):
            raise ValueError("selection_start and selection_end must be provided together")
        if self.selection_start is not None and not (
            self.selection_start < self.selection_end <= len(self.current_text)  # type: ignore[operator]
        ):
            raise ValueError("selection must satisfy 0 <= start < end <= text length")
        return self


class ChangeView(BaseModel):
    text: str
    rulesets: List[str]
    start_pos: int
    end_pos: int
    html: str


class ParsedRewrite(BaseModel):
    plain_text: str
    html: str
    changes: List[ChangeView]
    stats: Dict[str, int]
    warnings: List[str]


class DiffAnnotationView(BaseModel):
    change_id: str
    operation: str
    original_text: str
    revised_text: str
    original_start: int
    original_end: int
    revised_start: int
    revised_end: int
    rulesets: List[str]
    explanation: str


class DiffView(BaseModel):
    original_text: str
    revised_text: str
    annotations: List[DiffAnnotationView]
    original_html: str
    revised_html: str
    stats: Dict[str, int]
    similarity_ratio: float
    warnings: List[str]


class ModelMetadata(BaseModel):
    model_id: str
    latency_ms: float
    token_usage: Optional[Dict[str, int]] = None
    selection: Optional[Dict[str, Any]] = None
    estimated_cost_usd: Optional[float] = None
    estimated_savings_usd: Optional[float] = None


class RewriteResponse(BaseModel):
    original_text: str
    tagged_text: str
    rewritten: ParsedRewrite
    diff: DiffView
    model: ModelMetadata


class RefineResponse(RewriteResponse):
    refinement: Optional[Dict[str, Any]] = None


class ExplainRequest(BaseModel):
    original_text: str = Field(description="Text before the individual change")
    revised_text: str = Field(description="Text after the individual change")
    rulesets: List[str] = Field(default_factory=lambda: ["CONTENT"], min_length=1)
    guideline_title: Optional[str] = None
    guideline_url: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "original_text": "University of Illinois at Chicago",
                "revised_text": "University of Illinois Chicago",
                "rulesets": ["BRAND"],
                "guideline_title": "UIC Editorial Style Guide",
                "guideline_url": "https://today.uic.edu/uic-editorial-style-guide/",
            }]
        }
    }

    @model_validator(mode="after")
    def normalize_rulesets(self):
        normalized: List[str] = []
        for value in self.rulesets:
            name = value.strip().upper()
            if name not in VALID_RULESETS:
                raise ValueError(f"unknown ruleset: {value}")
            if name not in normalized:
                normalized.append(name)
        self.rulesets = normalized
        if self.original_text == self.revised_text:
            raise ValueError("original_text and revised_text must differ")
        return self


class GuidelineReference(BaseModel):
    title: str
    url: Optional[str] = None


class ExplainResponse(BaseModel):
    summary: str
    rationale: str
    operation: str
    rulesets: List[str]
    guideline: Optional[GuidelineReference] = None


@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    """Return one reusable service per Lambda execution environment."""

    return LLMService()


def _validate_document(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    if len(value.split()) > MAX_WORDS:
        raise ValueError(f"{field_name} must contain at most {MAX_WORDS} words")


def _guidelines_for_service(guidelines: List[Guideline]) -> List[Dict[str, str]]:
    # LLMService accepts flexible dictionaries; omit absent URLs rather than
    # serializing them as the string "None" in a prompt.
    return [
        {key: value for key, value in {
            "text": item.text,
            "source_url": item.source_url,
        }.items() if value is not None}
        for item in guidelines
    ]


def _rulesets_from_issues(issues: List[Dict[str, Any]]) -> List[str]:
    result: List[str] = []
    for issue in issues:
        value = issue.get("ruleset_id") or issue.get("ruleset")
        if isinstance(value, str) and value.strip().upper() in VALID_RULESETS:
            name = value.strip().upper()
            if name not in result:
                result.append(name)
    return result or ["CONTENT"]


def _metadata(response: LLMResponse) -> ModelMetadata:
    return ModelMetadata(
        model_id=response.model_id,
        latency_ms=response.latency_ms,
        token_usage=response.token_usage,
        selection=response.selection,
        estimated_cost_usd=response.estimated_cost_usd,
        estimated_savings_usd=response.estimated_savings_usd,
    )


def _build_rewrite_response(
    original_text: str,
    response: LLMResponse,
    rulesets: List[str],
) -> RewriteResponse:
    try:
        parsed = ChangeParser().parse(response.text)
        diff = TextDiffer().compare(original_text, parsed.plain_text, rulesets=rulesets)
    except (ChangeParserError, TextDiffError) as exc:
        raise HTTPException(status_code=500, detail=f"Could not process model output: {exc}") from exc
    return RewriteResponse(
        original_text=original_text,
        tagged_text=response.text,
        rewritten=ParsedRewrite(**parsed.to_dict()),
        diff=DiffView(**diff.to_dict()),
        model=_metadata(response),
    )


@router.post(
    "/rewrite",
    response_model=RewriteResponse,
    summary="Rewrite text with progressive-reveal annotations",
    description="Rewrites text with Bedrock, parses inline ruleset tags, and returns a deterministic side-by-side diff.",
    responses={502: {"description": "Bedrock invocation or configuration failed"}},
)
def rewrite_text(req: RewriteRequest, service: LLMService = Depends(get_llm_service)):
    try:
        response = service.rewrite_text(
            original_text=req.original_text,
            issues=req.issues,
            guidelines=_guidelines_for_service(req.guidelines),
            audience=req.audience.value,
            channel=req.channel.value,
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=f"LLM rewrite failed: {exc}") from exc
    return _build_rewrite_response(req.original_text, response, _rulesets_from_issues(req.issues))


@router.post(
    "/refine",
    response_model=RefineResponse,
    summary="Refine all or part of the current text",
    description="Applies a natural-language refinement request while preserving selected-text boundaries and change tags.",
    responses={400: {"description": "Invalid selection or refinement request"}, 502: {"description": "Bedrock invocation failed"}},
)
def refine_text(req: RefineRequest, service: LLMService = Depends(get_llm_service)):
    try:
        response = service.refine_text(
            current_text=req.current_text,
            refinement_request=req.refinement_request,
            audience=req.audience.value,
            channel=req.channel.value,
            context=req.context,
            selection_start=req.selection_start,
            selection_end=req.selection_end,
        )
    except RefinementValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=f"LLM refinement failed: {exc}") from exc

    base = _build_rewrite_response(
        req.current_text,
        response,
        list((response.refinement or {}).get("rulesets", ["CONTENT"])),
    )
    return RefineResponse(**base.model_dump(), refinement=response.refinement)


@router.post(
    "/explain",
    response_model=ExplainResponse,
    summary="Explain an individual proposed change",
    description="Creates a concise explanation for the UI from a before/after change and its ruleset metadata.",
)
def explain_change(req: ExplainRequest):
    if not req.original_text:
        operation = "insert"
        summary = f'Added "{req.revised_text}".'
    elif not req.revised_text:
        operation = "delete"
        summary = f'Removed "{req.original_text}".'
    else:
        operation = "replace"
        summary = f'Changed "{req.original_text}" to "{req.revised_text}".'

    reasons = [RULESET_RATIONALES[name] for name in req.rulesets]
    rationale = "This change " + "; and ".join(reasons) + "."
    guideline = None
    if req.guideline_title or req.guideline_url:
        guideline = GuidelineReference(
            title=req.guideline_title or "UIC guideline",
            url=req.guideline_url,
        )
    return ExplainResponse(
        summary=summary,
        rationale=rationale,
        operation=operation,
        rulesets=req.rulesets,
        guideline=guideline,
    )


app = FastAPI(
    title="UIC Editorial Assistant - LLM API",
    version="1.0.0",
    description="Task 3.8 endpoints for rewriting, chat refinement, and change explanations.",
)
app.include_router(router)
