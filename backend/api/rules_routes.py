"""Rule engine HTTP endpoints (Task 2.8).

Mount on the main app (Task I.3):

    from backend.api.rules_routes import router as rules_router
    app.include_router(rules_router)

Run standalone for development:

    uvicorn backend.api.rules_routes:app --reload
    open http://127.0.0.1:8000/docs
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from backend.services import reading_level as rl
from backend.services.models import (
    AnalysisResult,
    Audience,
    Channel,
    Rule,
    ScoreResult,
)
from backend.services.rule_engine import (
    MAX_WORDS,
    RuleEngine,
    TextTooLongError,
    UnknownRulesetError,
    get_engine,
)
from backend.services.scoring_service import calculate_scores

router = APIRouter(tags=["rules"])


# --------------------------------------------------------------------------
# Request / response models
# --------------------------------------------------------------------------


class RulesetSummary(BaseModel):
    ruleset_id: str
    ruleset_name: str
    description: str
    enabled: bool = Field(description="Selected by default")
    highlight_color: str
    rule_count: int
    rules: Optional[List[Rule]] = None


class RulesetsResponse(BaseModel):
    rulesets: List[RulesetSummary]


class CheckRequest(BaseModel):
    text: str = Field(min_length=1, description=f"Text to check (max {MAX_WORDS} words)")
    audience: Audience = Audience.STUDENTS
    channel: Optional[Channel] = None
    rulesets: Optional[List[str]] = Field(
        default=None, description="ruleset_ids to apply; omit for all default-enabled rulesets"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{
                "text": "Hey guys! Join us at the University of Illinois at Chicago "
                        "on October 15th at 3:00 PM. CLICK HERE to RSVP.",
                "audience": "students",
                "channel": "email",
                "rulesets": ["brand", "accessibility", "content", "reading_level", "audience_tone"],
            }]
        }
    }


class CheckResponse(BaseModel):
    analysis: AnalysisResult
    scores: ScoreResult


class AudienceInfo(BaseModel):
    audience_id: Audience
    label: str
    target_grade_level: float


class AudiencesResponse(BaseModel):
    audiences: List[AudienceInfo]
    channels: List[Channel]


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


@router.get("/api/rules", response_model=RulesetsResponse, response_model_exclude_none=True,
            summary="List available rulesets")
def list_rulesets(
    include_rules: bool = Query(False, description="Include each ruleset's full rule list"),
    engine: RuleEngine = Depends(get_engine),
):
    return RulesetsResponse(rulesets=[
        RulesetSummary(
            ruleset_id=rs.ruleset_id,
            ruleset_name=rs.ruleset_name,
            description=rs.description,
            enabled=rs.enabled,
            highlight_color=rs.highlight_color,
            rule_count=len(rs.rules),
            rules=rs.rules if include_rules else None,
        )
        for rs in engine.rulesets.values()
    ])


@router.get("/api/rules/{ruleset_id}", response_model=RulesetSummary,
            summary="Get one ruleset with its rules")
def get_ruleset(ruleset_id: str, engine: RuleEngine = Depends(get_engine)):
    try:
        rs = engine.get_ruleset(ruleset_id)
    except UnknownRulesetError:
        raise HTTPException(status_code=404, detail=f"Unknown ruleset '{ruleset_id}'")
    return RulesetSummary(
        ruleset_id=rs.ruleset_id,
        ruleset_name=rs.ruleset_name,
        description=rs.description,
        enabled=rs.enabled,
        highlight_color=rs.highlight_color,
        rule_count=len(rs.rules),
        rules=rs.rules,
    )


@router.post("/api/rules/check", response_model=CheckResponse,
             summary="Check text against rulesets and score it",
             responses={400: {"description": "Text too long or unknown ruleset"}})
def check_text(req: CheckRequest, engine: RuleEngine = Depends(get_engine)):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text must not be empty.")
    try:
        analysis = engine.analyze_text(
            req.text,
            rulesets=req.rulesets,
            audience=req.audience.value,
            channel=req.channel.value if req.channel else None,
        )
    except TextTooLongError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnknownRulesetError as e:
        raise HTTPException(status_code=400, detail=f"Unknown ruleset '{e.args[0]}'")
    return CheckResponse(analysis=analysis, scores=calculate_scores(analysis))


@router.get("/api/audiences", response_model=AudiencesResponse,
            summary="List supported audiences and channels")
def list_audiences():
    return AudiencesResponse(
        audiences=[
            AudienceInfo(audience_id=a, label=a.value.capitalize(),
                         target_grade_level=rl.grade_target_for(a.value))
            for a in Audience
        ],
        channels=list(Channel),
    )


# Standalone app for local development / Workstream 2 testing.
app = FastAPI(title="UIC Editorial Assistant – Rule Engine", version="1.0.0")
app.include_router(router)
