"""Compliance scoring (Task 2.7).

Algorithm (SPEC "Scoring Algorithm"):
  - Each score starts at 100.
  - Deduct per issue by severity: high -10, medium -5, low -2 (floor 0).
  - Brand and accessibility are scored separately (see SCORE_GROUPS).
  - Status:
      Approved         both scores >= 90 AND total_issues <= 2
      Major Revisions  any score < 70 OR total_issues > 5
      Minor Revisions  everything else (scores 70-89 or 3-5 issues)

To stop one repeated mistake (e.g. "e-mail" ten times) from zeroing a score,
each rule deducts for at most MAX_DEDUCTIONS_PER_RULE occurrences. Every
occurrence is still reported as an issue and counted in total_issues.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from .models import AnalysisResult, ComplianceStatus, Issue, ScoreResult, Severity

SEVERITY_DEDUCTIONS = {Severity.HIGH: 10, Severity.MEDIUM: 5, Severity.LOW: 2}
MAX_DEDUCTIONS_PER_RULE = 3

# Which rulesets feed each headline score.
SCORE_GROUPS: Dict[str, List[str]] = {
    "brand": ["brand", "content", "audience_tone"],
    "accessibility": ["accessibility", "reading_level"],
}

APPROVED_MIN_SCORE = 90
APPROVED_MAX_ISSUES = 2
MAJOR_MAX_SCORE = 70      # any score below this -> Major Revisions
MAJOR_MIN_ISSUES = 6      # more than 5 issues -> Major Revisions


def score_issues(issues: Iterable[Issue]) -> int:
    """Return a 0-100 score for a set of issues."""
    per_rule: Dict[str, int] = defaultdict(int)
    deduction = 0
    for issue in issues:
        if per_rule[issue.rule_id] >= MAX_DEDUCTIONS_PER_RULE:
            continue
        per_rule[issue.rule_id] += 1
        deduction += SEVERITY_DEDUCTIONS[issue.severity]
    return max(0, 100 - deduction)


def classify_status(brand_score: int, accessibility_score: int, total_issues: int):
    """Return (status, human-readable reason)."""
    low = min(brand_score, accessibility_score)
    if low < MAJOR_MAX_SCORE:
        return ComplianceStatus.MAJOR_REVISIONS, f"A score is below {MAJOR_MAX_SCORE} ({low})."
    if total_issues >= MAJOR_MIN_ISSUES:
        return ComplianceStatus.MAJOR_REVISIONS, f"{total_issues} issues found (more than {MAJOR_MIN_ISSUES - 1})."
    if low >= APPROVED_MIN_SCORE and total_issues <= APPROVED_MAX_ISSUES:
        return ComplianceStatus.APPROVED, (
            f"Both scores are {APPROVED_MIN_SCORE}+ with {total_issues} issue(s)."
        )
    if low < APPROVED_MIN_SCORE:
        return ComplianceStatus.MINOR_REVISIONS, f"Lowest score is {low} (target {APPROVED_MIN_SCORE}+)."
    return ComplianceStatus.MINOR_REVISIONS, (
        f"{total_issues} issues found (at most {APPROVED_MAX_ISSUES} for approval)."
    )


def calculate_scores(analysis: AnalysisResult) -> ScoreResult:
    by_ruleset: Dict[str, List[Issue]] = defaultdict(list)
    for issue in analysis.issues:
        by_ruleset[issue.ruleset_id].append(issue)

    ruleset_scores = {rid: score_issues(by_ruleset[rid]) for rid in analysis.rulesets_applied}

    def group_score(group: str) -> int:
        members = SCORE_GROUPS[group]
        return score_issues(i for rid in members for i in by_ruleset.get(rid, []))

    brand = group_score("brand")
    accessibility = group_score("accessibility")
    total = len(analysis.issues)
    status, reason = classify_status(brand, accessibility, total)

    return ScoreResult(
        brand_score=brand,
        accessibility_score=accessibility,
        ruleset_scores=ruleset_scores,
        total_issues=total,
        status=status,
        status_reason=reason,
    )
