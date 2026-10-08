"""Deterministic rule engine (Task 2.2).

Loads ruleset JSON files from /rulesets/ and checks text against them.

Public interface (consumed by the orchestrator, Task I.3):

    engine = RuleEngine()
    result = engine.analyze_text(text, rulesets=["brand", "accessibility"],
                                 audience="students", channel="email")
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Pattern, Tuple

from pydantic import ValidationError

from . import reading_level as rl
from .models import (
    AnalysisResult,
    Audience,
    Channel,
    Issue,
    PatternType,
    ReadingLevel,
    Rule,
    Ruleset,
    Severity,
    TextStats,
)
from .rule_functions import RULE_FUNCTIONS, RuleContext, RuleMatch

logger = logging.getLogger(__name__)

DEFAULT_RULESETS_DIR = Path(__file__).resolve().parents[2] / "rulesets"
MAX_WORDS = 5000
CONTEXT_CHARS = 40
MAX_MATCHED_TEXT = 300
_SEVERITY_ORDER = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}


class RulesetValidationError(ValueError):
    """Raised when a ruleset file is malformed."""


class TextTooLongError(ValueError):
    """Raised when input exceeds MAX_WORDS."""


class UnknownRulesetError(KeyError):
    """Raised when a requested ruleset_id does not exist."""


class RuleEngine:
    def __init__(self, rulesets_dir: Optional[os.PathLike] = None):
        self.rulesets_dir = Path(
            rulesets_dir or os.environ.get("RULESETS_DIR") or DEFAULT_RULESETS_DIR
        )
        self._rulesets: Dict[str, Ruleset] = {}
        self._compiled: Dict[str, Pattern] = {}  # rule_id -> compiled regex
        self._keyword_suggestions: Dict[str, Dict[str, str]] = {}  # rule_id -> {kw_lower: suggestion}
        self.reload()

    # ------------------------------------------------------------------
    # Loading & validation
    # ------------------------------------------------------------------

    def reload(self) -> None:
        """(Re)load every *.json ruleset in rulesets_dir."""
        if not self.rulesets_dir.is_dir():
            raise RulesetValidationError(f"Rulesets directory not found: {self.rulesets_dir}")

        rulesets: Dict[str, Ruleset] = {}
        compiled: Dict[str, Pattern] = {}
        keyword_suggestions: Dict[str, Dict[str, str]] = {}
        seen_rule_ids: Dict[str, str] = {}

        for path in sorted(self.rulesets_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                ruleset = Ruleset.model_validate(data)
            except (json.JSONDecodeError, ValidationError) as e:
                raise RulesetValidationError(f"{path.name}: {e}") from e

            if ruleset.ruleset_id in rulesets:
                raise RulesetValidationError(f"{path.name}: duplicate ruleset_id '{ruleset.ruleset_id}'")

            for rule in ruleset.rules:
                where = f"{path.name} / {rule.rule_id}"
                if rule.rule_id in seen_rule_ids:
                    raise RulesetValidationError(
                        f"{where}: duplicate rule_id (also in {seen_rule_ids[rule.rule_id]})"
                    )
                seen_rule_ids[rule.rule_id] = path.name
                compiled[rule.rule_id], suggestions = self._compile_rule(rule, where)
                if suggestions:
                    keyword_suggestions[rule.rule_id] = suggestions

            rulesets[ruleset.ruleset_id] = ruleset

        self._rulesets = rulesets
        self._compiled = {k: v for k, v in compiled.items() if v is not None}
        self._keyword_suggestions = keyword_suggestions
        logger.info(
            "Loaded %d rulesets (%d rules) from %s",
            len(rulesets), len(seen_rule_ids), self.rulesets_dir,
        )

    @staticmethod
    def _compile_rule(rule: Rule, where: str) -> Tuple[Optional[Pattern], Dict[str, str]]:
        flags = 0 if rule.case_sensitive else re.IGNORECASE

        if rule.pattern_type == PatternType.REGEX:
            if not isinstance(rule.pattern, str):
                raise RulesetValidationError(f"{where}: regex pattern must be a string")
            try:
                return re.compile(rule.pattern, flags | re.MULTILINE), {}
            except re.error as e:
                raise RulesetValidationError(f"{where}: invalid regex: {e}") from e

        if rule.pattern_type == PatternType.KEYWORD:
            if isinstance(rule.pattern, str):
                keywords, suggestions = [rule.pattern], {}
            elif isinstance(rule.pattern, list):
                keywords, suggestions = list(rule.pattern), {}
            else:
                keywords = list(rule.pattern.keys())
                suggestions = {k.lower(): v for k, v in rule.pattern.items()}
            if not keywords or not all(isinstance(k, str) and k.strip() for k in keywords):
                raise RulesetValidationError(f"{where}: keyword pattern must contain non-empty strings")
            # Longest first so "in order to" wins over "order".
            alternation = "|".join(re.escape(k) for k in sorted(keywords, key=len, reverse=True))
            return re.compile(rf"(?<!\w)(?:{alternation})(?!\w)", flags), suggestions

        # FUNCTION
        if not isinstance(rule.pattern, str) or rule.pattern not in RULE_FUNCTIONS:
            raise RulesetValidationError(
                f"{where}: unknown rule function '{rule.pattern}'. "
                f"Available: {sorted(RULE_FUNCTIONS)}"
            )
        return None, {}

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def rulesets(self) -> Dict[str, Ruleset]:
        return dict(self._rulesets)

    def get_ruleset(self, ruleset_id: str) -> Ruleset:
        try:
            return self._rulesets[ruleset_id]
        except KeyError:
            raise UnknownRulesetError(ruleset_id) from None

    def default_ruleset_ids(self) -> List[str]:
        return [rid for rid, rs in self._rulesets.items() if rs.enabled]

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyze_text(
        self,
        text: str,
        rulesets: Optional[Iterable[str]] = None,
        audience: str = "students",
        channel: Optional[str] = None,
    ) -> AnalysisResult:
        """Check `text` against the selected rulesets.

        rulesets: ruleset_ids to apply; None means every ruleset enabled by default.
        """
        audience_enum = Audience(audience.lower())
        channel_enum = Channel(channel.lower()) if channel else None

        word_count = len(rl.words(text))
        if word_count > MAX_WORDS:
            raise TextTooLongError(f"Text has {word_count} words; the maximum is {MAX_WORDS}.")

        ruleset_ids = list(dict.fromkeys(rulesets)) if rulesets is not None else self.default_ruleset_ids()
        for rid in ruleset_ids:
            if rid not in self._rulesets:
                raise UnknownRulesetError(rid)

        issues: List[Issue] = []
        for rid in ruleset_ids:
            ruleset = self._rulesets[rid]
            for rule in ruleset.rules:
                if not self._rule_applies(rule, audience_enum, channel_enum):
                    continue
                try:
                    matches = self._run_rule(rule, text, audience_enum.value,
                                             channel_enum.value if channel_enum else None)
                except Exception:  # one bad rule should never break the whole analysis
                    logger.exception("Rule %s failed", rule.rule_id)
                    continue
                for i, match in enumerate(matches, start=1):
                    issues.append(self._build_issue(text, ruleset, rule, match, i))

        issues.sort(key=lambda x: (x.start, _SEVERITY_ORDER[x.severity], x.rule_id))

        issue_counts = {rid: 0 for rid in ruleset_ids}
        severity_counts = {s.value: 0 for s in Severity}
        for issue in issues:
            issue_counts[issue.ruleset_id] += 1
            severity_counts[issue.severity.value] += 1

        metrics = rl.compute_metrics(text)
        target = rl.grade_target_for(audience_enum.value)

        logger.info(
            "Analyzed %d words for audience=%s channel=%s rulesets=%s: %d issues",
            word_count, audience_enum.value, channel_enum.value if channel_enum else None,
            ruleset_ids, len(issues),
        )

        return AnalysisResult(
            audience=audience_enum,
            channel=channel_enum,
            rulesets_applied=ruleset_ids,
            issues=issues,
            issue_counts=issue_counts,
            severity_counts=severity_counts,
            reading_level=ReadingLevel(
                grade_level=metrics.grade_level,
                reading_ease=metrics.reading_ease,
                target_grade=target,
                meets_target=metrics.grade_level <= target,
                word_count=metrics.word_count,
                sentence_count=metrics.sentence_count,
                syllable_count=metrics.syllable_count,
                avg_words_per_sentence=round(metrics.avg_words_per_sentence, 1),
                avg_syllables_per_word=round(metrics.avg_syllables_per_word, 2),
            ),
            text_stats=TextStats(
                word_count=word_count,
                character_count=len(text),
                sentence_count=len(rl.split_sentences(text)),
                paragraph_count=len(rl.split_paragraphs(text)),
            ),
        )

    @staticmethod
    def _rule_applies(rule: Rule, audience: Audience, channel: Optional[Channel]) -> bool:
        if not rule.enabled:
            return False
        if rule.audiences and audience not in rule.audiences:
            return False
        if rule.channels and (channel is None or channel not in rule.channels):
            return False
        return True

    def _run_rule(self, rule: Rule, text: str, audience: str, channel: Optional[str]) -> List[RuleMatch]:
        if rule.pattern_type == PatternType.FUNCTION:
            ctx = RuleContext(audience=audience, channel=channel, params=rule.params)
            return RULE_FUNCTIONS[rule.pattern](text, ctx)

        regex = self._compiled[rule.rule_id]
        suggestions = self._keyword_suggestions.get(rule.rule_id, {})
        matches = []
        for m in regex.finditer(text):
            if m.end() == m.start():
                continue  # ignore zero-width matches
            suggestion = suggestions.get(m.group(0).lower())
            if suggestion is None and rule.pattern_type == PatternType.REGEX and rule.suggestion:
                # Allow backreferences such as "\\1" in regex suggestions.
                try:
                    suggestion = m.expand(rule.suggestion)
                except (re.error, IndexError):
                    suggestion = rule.suggestion
            matches.append(RuleMatch(m.start(), m.end(), suggestion=suggestion))
        return matches

    @staticmethod
    def _build_issue(text: str, ruleset: Ruleset, rule: Rule, match: RuleMatch, n: int) -> Issue:
        start = max(0, min(match.start, len(text)))
        end = max(start, min(match.end, len(text)))
        matched = text[start:end]
        if len(matched) > MAX_MATCHED_TEXT:
            matched = matched[:MAX_MATCHED_TEXT] + "…"

        if match.scope == "document":
            context = text[:2 * CONTEXT_CHARS].strip() + ("…" if len(text) > 2 * CONTEXT_CHARS else "")
        else:
            c_start = max(0, start - CONTEXT_CHARS)
            c_end = min(len(text), end + CONTEXT_CHARS)
            context = (
                ("…" if c_start > 0 else "")
                + text[c_start:c_end].replace("\n", " ")
                + ("…" if c_end < len(text) else "")
            )

        return Issue(
            issue_id=f"{rule.rule_id}-{n}",
            rule_id=rule.rule_id,
            ruleset_id=ruleset.ruleset_id,
            rule_name=rule.name,
            severity=Severity(match.severity) if match.severity else rule.severity,
            message=match.message or rule.message or rule.description or rule.name,
            matched_text=matched,
            start=start,
            end=end,
            line=text.count("\n", 0, start) + 1,
            context=context,
            suggestion=match.suggestion if match.suggestion is not None else rule.suggestion,
            guideline_url=rule.guideline_url,
            highlight_color=ruleset.highlight_color,
            scope=match.scope,
        )


_default_engine: Optional[RuleEngine] = None


def get_engine() -> RuleEngine:
    """Process-wide singleton (rulesets are loaded once per Lambda container)."""
    global _default_engine
    if _default_engine is None:
        _default_engine = RuleEngine()
    return _default_engine


def analyze_text(
    text: str,
    rulesets: Optional[Iterable[str]] = None,
    audience: str = "students",
    channel: Optional[str] = None,
) -> AnalysisResult:
    """Module-level convenience wrapper matching the SPEC interface."""
    return get_engine().analyze_text(text, rulesets, audience, channel)
