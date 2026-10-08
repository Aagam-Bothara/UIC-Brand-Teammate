"""Shared data models for the rule engine and scoring service (Workstream 2).

These Pydantic models double as the API response schema, so the frontend
(`/src/types/api.ts`) and the orchestrator can rely on the same field names.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PatternType(str, Enum):
    REGEX = "regex"
    KEYWORD = "keyword"
    FUNCTION = "function"


class Audience(str, Enum):
    STUDENTS = "students"
    FACULTY = "faculty"
    STAFF = "staff"


class Channel(str, Enum):
    EMAIL = "email"
    WEBSITE = "website"
    SOCIAL_MEDIA = "social_media"


class ComplianceStatus(str, Enum):
    APPROVED = "Approved"
    MINOR_REVISIONS = "Minor Revisions"
    MAJOR_REVISIONS = "Major Revisions"


# --------------------------------------------------------------------------
# Rule configuration (mirrors rulesets/schema/ruleset.schema.json)
# --------------------------------------------------------------------------


class Rule(BaseModel):
    rule_id: str
    name: str
    description: str = ""
    severity: Severity
    pattern_type: PatternType
    # regex: a pattern string
    # keyword: a string, a list of strings, or a {keyword: suggestion} map
    # function: the name of a registered function in rule_functions.py
    pattern: Union[str, List[str], Dict[str, str]]
    case_sensitive: bool = False
    message: str = ""
    suggestion: Optional[str] = None
    guideline_url: Optional[str] = None
    # Where the rule comes from, e.g. "UIC Editorial and Style Guide: Time".
    source: str = ""
    enabled: bool = True
    # Empty list means "applies to all audiences / channels".
    audiences: List[Audience] = Field(default_factory=list)
    channels: List[Channel] = Field(default_factory=list)
    # Extra parameters passed to function-based rules.
    params: Dict[str, Any] = Field(default_factory=dict)


class Ruleset(BaseModel):
    ruleset_id: str
    ruleset_name: str
    description: str = ""
    enabled: bool = True
    highlight_color: str
    rules: List[Rule]


# --------------------------------------------------------------------------
# Analysis output
# --------------------------------------------------------------------------


class Issue(BaseModel):
    issue_id: str
    rule_id: str
    ruleset_id: str
    rule_name: str
    severity: Severity
    message: str
    matched_text: str
    start: int = Field(description="Character offset (inclusive) in the original text")
    end: int = Field(description="Character offset (exclusive) in the original text")
    line: int = Field(description="1-based line number of `start`")
    context: str = Field(description="Snippet of surrounding text for display")
    scope: str = Field(
        default="span",
        description='"span" = highlight start..end; "document" = applies to the whole text',
    )
    suggestion: Optional[str] = None
    guideline_url: Optional[str] = None
    highlight_color: str


class ReadingLevel(BaseModel):
    grade_level: float
    reading_ease: float
    target_grade: float
    meets_target: bool
    word_count: int
    sentence_count: int
    syllable_count: int
    avg_words_per_sentence: float
    avg_syllables_per_word: float


class TextStats(BaseModel):
    word_count: int
    character_count: int
    sentence_count: int
    paragraph_count: int


class AnalysisResult(BaseModel):
    audience: Audience
    channel: Optional[Channel] = None
    rulesets_applied: List[str]
    issues: List[Issue]
    issue_counts: Dict[str, int] = Field(
        description="Number of issues per ruleset_id (every applied ruleset is present)"
    )
    severity_counts: Dict[str, int]
    reading_level: ReadingLevel
    text_stats: TextStats


class ScoreResult(BaseModel):
    brand_score: int
    accessibility_score: int
    ruleset_scores: Dict[str, int]
    total_issues: int
    status: ComplianceStatus
    status_reason: str
