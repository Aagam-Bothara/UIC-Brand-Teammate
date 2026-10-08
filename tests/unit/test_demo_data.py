"""Schema and offset checks for the demo drafts (data/demo/demo_drafts.json) and the
UI sample list (frontend/src/data/demoSamples.json)."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DRAFTS_PATH = ROOT / "data" / "demo" / "demo_drafts.json"
SAMPLES_PATH = ROOT / "frontend" / "src" / "data" / "demoSamples.json"

AUDIENCES = {"Students", "Faculty", "Staff"}
CHANNELS = {"Email", "Website", "Social Media"}
RULESETS = {"brand", "accessibility", "content", "reading_level", "audience_tone"}
DATASET_STATUSES = {"Approved", "Minor Revisions Needed", "Major Revisions Needed", "Rejected - Full Rewrite"}
MAPPED_STATUSES = ["Approved", "Minor Revisions", "Major Revisions"]
STATUS_HINTS = ["Approved", "Minor Revisions Needed", "Major Revisions Needed"]

DRAFT_KEYS = {
    "demo_id", "source_communication_id", "title", "communication_type", "department", "author_role",
    "draft_date", "target_audience_original", "audience", "distribution_channel_original", "channel",
    "suggested_rulesets", "text", "planted_issues", "editorial_slips", "dataset_expectations",
    "demo_notes", "featured",
}
EXPECTATION_KEYS = {
    "compliance_status", "compliance_status_mapped", "brand_compliance_score", "accessibility_score",
    "total_issues_flagged", "flesch_kincaid_grade_level", "manual_review_time_minutes",
    "ai_review_time_seconds", "time_savings_minutes",
}
SAMPLE_KEYS = {"id", "title", "communication_type", "department", "audience", "channel",
               "status_hint", "featured", "text"}


def js_slice(text: str, start: int, end: int) -> str:
    """Equivalent of JavaScript text.slice(start, end) (UTF-16 code units)."""
    return text.encode("utf-16-le")[2 * start:2 * end].decode("utf-16-le")


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


@pytest.fixture(scope="module")
def drafts():
    return json.loads(DRAFTS_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def samples():
    return json.loads(SAMPLES_PATH.read_text(encoding="utf-8"))


def test_draft_count_and_ids(drafts):
    assert isinstance(drafts, list)
    assert len(drafts) == 24
    ids = [d["demo_id"] for d in drafts]
    assert len(set(ids)) == 24
    assert all(re.fullmatch(r"demo-\d{2}", i) for i in ids)
    sources = [d["source_communication_id"] for d in drafts]
    assert len(set(sources)) == 24
    assert all(re.fullmatch(r"COMM-\d{5}", s) for s in sources)


def test_draft_schema(drafts):
    for d in drafts:
        assert set(d) == DRAFT_KEYS, d["demo_id"]
        assert d["audience"] in AUDIENCES
        assert d["channel"] in CHANNELS
        assert set(d["suggested_rulesets"]) <= RULESETS and d["suggested_rulesets"]
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", d["draft_date"])
        assert isinstance(d["featured"], bool)
        assert d["title"] and d["demo_notes"]
        exp = d["dataset_expectations"]
        assert EXPECTATION_KEYS <= set(exp)
        assert exp["compliance_status"] in DATASET_STATUSES
        assert exp["compliance_status_mapped"] in MAPPED_STATUSES


def test_draft_text_length(drafts):
    for d in drafts:
        words = len(d["text"].split())
        assert 50 <= words <= 260, (d["demo_id"], words)


def test_planted_issues_match_dataset_counts(drafts):
    for d in drafts:
        labels = {p["dataset_issue"] for p in d["planted_issues"]}
        assert len(labels) == d["dataset_expectations"]["total_issues_flagged"], d["demo_id"]
        for p in d["planted_issues"]:
            assert p["ruleset"] in RULESETS
            assert p["dataset_category"] in {"brand", "accessibility", "content"}


def test_offsets_are_exact(drafts):
    for d in drafts:
        text = d["text"]
        for kind in ("planted_issues", "editorial_slips"):
            for item in d[kind]:
                ev = item["evidence"]
                if ev is None:
                    assert item["start"] is None and item["end"] is None
                    continue
                s, e = item["start"], item["end"]
                assert isinstance(s, int) and isinstance(e, int)
                assert 0 <= s < e <= utf16_len(text), (d["demo_id"], ev)
                assert js_slice(text, s, e) == ev, (d["demo_id"], kind, ev)


def test_slips_name_real_rules(drafts):
    for d in drafts:
        for s in d["editorial_slips"]:
            assert s["ruleset"] in RULESETS
            assert re.fullmatch(r"(brand|access|content|reading|tone)-\d{3}", s["expected_rule_id"])


def test_status_spread(drafts):
    counts = {s: 0 for s in MAPPED_STATUSES}
    for d in drafts:
        counts[d["dataset_expectations"]["compliance_status_mapped"]] += 1
    assert all(n >= 6 for n in counts.values()), counts
    assert {d["audience"] for d in drafts} == AUDIENCES
    assert {d["channel"] for d in drafts} == CHANNELS


def test_featured_count(drafts, samples):
    assert sum(d["featured"] for d in drafts) == 3
    assert sum(s["featured"] for s in samples) == 3
    assert {d["demo_id"] for d in drafts if d["featured"]} == {s["id"] for s in samples if s["featured"]}


def test_samples_schema_and_order(drafts, samples):
    assert len(samples) == 24
    by_id = {d["demo_id"]: d for d in drafts}
    assert {s["id"] for s in samples} == set(by_id)
    for s in samples:
        assert set(s) == SAMPLE_KEYS
        assert s["audience"] in AUDIENCES
        assert s["channel"] in CHANNELS
        assert s["status_hint"] in STATUS_HINTS
        d = by_id[s["id"]]
        assert s["text"] == d["text"]
        assert s["audience"] == d["audience"] and s["channel"] == d["channel"]
    # Most dramatic first: Major, then Minor, then Approved.
    ranks = [STATUS_HINTS.index(s["status_hint"]) for s in samples]
    assert ranks == sorted(ranks, reverse=True)


def test_validation_script_offset_check():
    from scripts.validate_demo_data import main

    assert main(["--check"]) == 0
