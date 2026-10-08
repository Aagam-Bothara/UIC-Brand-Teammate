import pytest

from backend.services.models import ComplianceStatus, Issue, Severity
from backend.services.scoring_service import calculate_scores, classify_status, score_issues


def make_issue(severity, rule_id="r-001", ruleset_id="brand"):
    return Issue(
        issue_id=f"{rule_id}-x", rule_id=rule_id, ruleset_id=ruleset_id, rule_name="R",
        severity=Severity(severity), message="m", matched_text="t", start=0, end=1,
        line=1, context="t", highlight_color="#000000",
    )


def test_no_issues_scores_100():
    assert score_issues([]) == 100


def test_severity_deductions():
    issues = [make_issue("high", "a-001"), make_issue("medium", "b-001"), make_issue("low", "c-001")]
    assert score_issues(issues) == 100 - 10 - 5 - 2


def test_per_rule_cap():
    issues = [make_issue("high", "a-001") for _ in range(10)]
    assert score_issues(issues) == 70  # capped at 3 deductions


def test_score_floor_is_zero():
    issues = [make_issue("high", f"r-{i:03}") for i in range(20)]
    assert score_issues(issues) == 0


@pytest.mark.parametrize("brand,access,issues,expected", [
    (100, 100, 0, ComplianceStatus.APPROVED),
    (90, 92, 2, ComplianceStatus.APPROVED),
    (90, 92, 3, ComplianceStatus.MINOR_REVISIONS),
    (89, 100, 1, ComplianceStatus.MINOR_REVISIONS),
    (70, 70, 5, ComplianceStatus.MINOR_REVISIONS),
    (69, 100, 1, ComplianceStatus.MAJOR_REVISIONS),
    (95, 95, 6, ComplianceStatus.MAJOR_REVISIONS),
])
def test_classify_status(brand, access, issues, expected):
    status, reason = classify_status(brand, access, issues)
    assert status == expected
    assert reason


def test_calculate_scores_groups_rulesets(engine):
    text = "Welcome to the University of Illinois at Chicago. CLICK HERE to RSVP."
    analysis = engine.analyze_text(text, audience="students", channel="email")
    scores = calculate_scores(analysis)
    assert scores.brand_score == 100 - 10       # brand-001 (high)
    assert scores.accessibility_score == 100 - 5 - 5  # access-001 + access-002 (medium)
    assert scores.total_issues == len(analysis.issues)
    assert set(scores.ruleset_scores) == set(analysis.rulesets_applied)
    assert scores.status == ComplianceStatus.MINOR_REVISIONS


def test_clean_text_is_approved(engine):
    analysis = engine.analyze_text("University of Illinois Chicago welcomes you.", audience="faculty")
    scores = calculate_scores(analysis)
    assert scores.status == ComplianceStatus.APPROVED
    assert scores.brand_score == scores.accessibility_score == 100
