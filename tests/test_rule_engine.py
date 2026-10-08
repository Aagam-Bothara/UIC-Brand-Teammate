import json
from pathlib import Path

import pytest

from backend.services.rule_engine import (
    MAX_WORDS,
    RuleEngine,
    RulesetValidationError,
    TextTooLongError,
    UnknownRulesetError,
)
from conftest import rule_ids

RULESETS_DIR = Path(__file__).resolve().parents[1] / "rulesets"


# ---------------------------------------------------------------- loading


def test_loads_all_five_rulesets(engine):
    assert set(engine.rulesets) == {"brand", "accessibility", "content", "reading_level", "audience_tone"}


def test_ruleset_sizes_meet_plan(engine):
    rs = engine.rulesets
    assert len(rs["brand"].rules) >= 10
    assert len(rs["accessibility"].rules) >= 8
    assert len(rs["content"].rules) >= 8
    assert len(rs["reading_level"].rules) >= 3
    assert len(rs["audience_tone"].rules) >= 3


def test_rulesets_match_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((RULESETS_DIR / "schema" / "ruleset.schema.json").read_text())
    for path in RULESETS_DIR.glob("*.json"):
        jsonschema.validate(json.loads(path.read_text()), schema)


def _write(tmp_path, data, name="x.json"):
    (tmp_path / name).write_text(json.dumps(data))


def _ruleset(rules):
    return {"ruleset_id": "x", "ruleset_name": "X", "highlight_color": "#000000", "rules": rules}


def _rule(**kw):
    base = {"rule_id": "x-001", "name": "X", "severity": "low", "pattern_type": "regex", "pattern": "foo"}
    base.update(kw)
    return base


def test_invalid_regex_is_rejected(tmp_path):
    _write(tmp_path, _ruleset([_rule(pattern="(unclosed")]))
    with pytest.raises(RulesetValidationError, match="invalid regex"):
        RuleEngine(tmp_path)


def test_unknown_function_is_rejected(tmp_path):
    _write(tmp_path, _ruleset([_rule(pattern_type="function", pattern="nope")]))
    with pytest.raises(RulesetValidationError, match="unknown rule function"):
        RuleEngine(tmp_path)


def test_bad_severity_is_rejected(tmp_path):
    _write(tmp_path, _ruleset([_rule(severity="critical")]))
    with pytest.raises(RulesetValidationError):
        RuleEngine(tmp_path)


def test_duplicate_rule_ids_are_rejected(tmp_path):
    _write(tmp_path, _ruleset([_rule(), _rule()]))
    with pytest.raises(RulesetValidationError, match="duplicate rule_id"):
        RuleEngine(tmp_path)


# ---------------------------------------------------------------- pattern types


def test_keyword_rule_with_suggestion_map(tmp_path):
    _write(tmp_path, _ruleset([_rule(pattern_type="keyword", pattern={"in order to": "to"})]))
    r = RuleEngine(tmp_path).analyze_text("We met In Order To plan.")
    (issue,) = r.issues
    assert issue.matched_text == "In Order To"
    assert issue.suggestion == "to"


def test_keyword_respects_word_boundaries(tmp_path):
    _write(tmp_path, _ruleset([_rule(pattern_type="keyword", pattern=["lame"])]))
    assert RuleEngine(tmp_path).analyze_text("Blame the flames.").issues == []


def test_regex_suggestion_backreference(engine):
    r = engine.analyze_text("Read the e-mails.", rulesets=["content"])
    (issue,) = [i for i in r.issues if i.rule_id == "content-001"]
    assert issue.suggestion == "emails"


def test_issue_positions_and_context(engine):
    text = "Line one.\nWelcome to the University of Illinois at Chicago campus."
    r = engine.analyze_text(text, rulesets=["brand"])
    issue = next(i for i in r.issues if i.rule_id == "brand-001")
    assert text[issue.start:issue.end] == "University of Illinois at Chicago"
    assert issue.line == 2
    assert "University of Illinois at Chicago" in issue.context
    assert issue.highlight_color == "#3B82F6"
    assert issue.guideline_url.startswith("https://brand.uic.edu/")


def test_issues_are_sorted_by_position(engine):
    r = engine.analyze_text("Send an e-mail to the the office at 3:00 PM.", rulesets=["content"])
    starts = [i.start for i in r.issues]
    assert starts == sorted(starts)


def test_disabled_rule_is_skipped(tmp_path):
    _write(tmp_path, _ruleset([_rule(enabled=False)]))
    assert RuleEngine(tmp_path).analyze_text("foo").issues == []


# ---------------------------------------------------------------- filters & errors


def test_audience_filter(engine):
    text = "We're gonna meet tomorrow."
    assert "tone-001" in rule_ids(engine.analyze_text(text, ["audience_tone"], audience="faculty"))
    assert "tone-001" not in rule_ids(engine.analyze_text(text, ["audience_tone"], audience="students"))


def test_channel_filter(engine):
    text = "Details: https://example.com/page"
    assert "access-005" in rule_ids(engine.analyze_text(text, ["accessibility"], channel="email"))
    assert "access-005" not in rule_ids(engine.analyze_text(text, ["accessibility"], channel="social_media"))
    assert "access-005" not in rule_ids(engine.analyze_text(text, ["accessibility"], channel=None))


def test_only_requested_rulesets_run(engine):
    r = engine.analyze_text("University of Illinois at Chicago e-mail", rulesets=["content"])
    assert {i.ruleset_id for i in r.issues} == {"content"}
    assert r.rulesets_applied == ["content"]
    assert r.issue_counts == {"content": 1}


def test_unknown_ruleset_raises(engine):
    with pytest.raises(UnknownRulesetError):
        engine.analyze_text("hello", rulesets=["nope"])


def test_text_too_long_raises(engine):
    with pytest.raises(TextTooLongError):
        engine.analyze_text("word " * (MAX_WORDS + 1))


def test_invalid_audience_raises(engine):
    with pytest.raises(ValueError):
        engine.analyze_text("hello", audience="alumni")


def test_clean_text_has_no_issues(engine):
    text = (
        "The University of Illinois Chicago welcomes new students on Oct. 15 at 3 p.m. "
        "Come to Student Center East. Meet your advisers and make new friends. "
        "Email the orientation office with any questions. We hope to see you there."
    )
    r = engine.analyze_text(text, audience="students", channel="email")
    assert r.issues == [], [(i.rule_id, i.matched_text) for i in r.issues]


# ---------------------------------------------------------------- brand rules


@pytest.mark.parametrize("text,rule_id,expected_suggestion", [
    ("University of Illinois at Chicago", "brand-001", "University of Illinois Chicago"),
    ("University of Illinois-Chicago", "brand-002", "University of Illinois Chicago"),
    ("University of Illinois, Chicago", "brand-002", "University of Illinois Chicago"),
    ("U.I.C. students", "brand-003", "UIC"),
    ("U of I Chicago", "brand-004", "UIC"),
    ("Univ. of Illinois", "brand-005", "University of Illinois Chicago"),
    ("go uic", "brand-007", "UIC"),
    ("UIC University", "brand-008", "UIC"),
    ("Illinois-Chicago", "brand-009", "UIC"),
    ("Chicago Circle Campus", "brand-010", "UIC"),
    ("the University of Illinois library", "brand-011", "University of Illinois Chicago"),
    ("U of I", "brand-012", "UIC"),
    ("Contact the University today.", "brand-013", "university"),
])
def test_brand_rules_fire(engine, text, rule_id, expected_suggestion):
    r = engine.analyze_text(text, rulesets=["brand"])
    hits = [i for i in r.issues if i.rule_id == rule_id]
    assert hits, f"{rule_id} did not fire on {text!r}; got {rule_ids(r)}"
    assert hits[0].suggestion == expected_suggestion


@pytest.mark.parametrize("text", [
    "The University of Illinois Chicago is in Chicago. UIC is a public university.",
    "Email us at orientation@uic.edu or visit go.uic.edu/apply.",
    "Follow #uicflames for updates. University of Illinois Chicago",
    "University of Illinois System and University of Illinois Urbana-Champaign",
    "The University of Illinois Chicago Flames won. UIC fans cheered.",
])
def test_brand_rules_do_not_false_positive(engine, text):
    r = engine.analyze_text(text, rulesets=["brand"])
    assert r.issues == [], [(i.rule_id, i.matched_text) for i in r.issues]


def test_first_reference_checked_on_every_channel(engine):
    for channel in [None, "email", "website", "social_media"]:
        assert "brand-006" in rule_ids(engine.analyze_text("UIC is great.", ["brand"], channel=channel))


def test_first_reference_ok_when_full_name_comes_first(engine):
    r = engine.analyze_text("University of Illinois Chicago (UIC) students. UIC rocks.", rulesets=["brand"])
    assert "brand-006" not in rule_ids(r)


# ---------------------------------------------------------------- accessibility rules


def test_accessibility_rules(engine):
    text = (
        "CLICK HERE to register. The wheelchair-bound student won. "
        "![](photo.png) See the attached flyer. Contact the OSA office."
    )
    ids = rule_ids(engine.analyze_text(text, ["accessibility"]))
    for expected in ["access-001", "access-002", "access-003", "access-004", "access-010", "access-007"]:
        assert expected in ids


def test_acronym_defined_in_parentheses_is_ok(engine):
    r = engine.analyze_text("The Office of Student Affairs (OSA) helps. Visit OSA.", ["accessibility"])
    assert "access-007" not in rule_ids(r)


def test_all_caps_ignores_known_acronyms(engine):
    r = engine.analyze_text("Bring your UIC ID to the event.", ["accessibility"])
    assert "access-002" not in rule_ids(r)


def test_emoji_overuse_flags_extras_only(engine):
    r = engine.analyze_text("Party 🎉🎉🎉🎉🎉", ["accessibility"])
    assert rule_ids(r).count("access-008") == 2


def test_img_tag_with_alt_is_ok(engine):
    r = engine.analyze_text('<img src="a.png" alt="Students on the quad">', ["accessibility"])
    assert "access-004" not in rule_ids(r)


# ---------------------------------------------------------------- content rules


@pytest.mark.parametrize("text,suggestion", [
    ("3:00 PM", "3 p.m."),
    ("9:30am", "9:30 a.m."),
    ("10 A.M.", "10 a.m."),
    ("12 PM", "noon"),
    ("12:00 am", "midnight"),
])
def test_time_format(engine, text, suggestion):
    r = engine.analyze_text(f"Meet at {text} today.", ["content"])
    issue = next(i for i in r.issues if i.rule_id == "content-003")
    assert issue.suggestion == suggestion


def test_time_format_keeps_sentence_period(engine):
    r = engine.analyze_text("Doors open at 3:00 PM. See you there.", ["content"])
    issue = next(i for i in r.issues if i.rule_id == "content-003")
    assert issue.matched_text == "3:00 PM"


def test_all_caps_does_not_cross_sentences(engine):
    r = engine.analyze_text("Starts at 3 PM. CLICK HERE to RSVP NOW.", ["accessibility"])
    caps = [i.matched_text for i in r.issues if i.rule_id == "access-002"]
    assert caps == ["CLICK HERE", "NOW"]


def test_correct_time_format_passes(engine):
    r = engine.analyze_text("Meet at 3 p.m. or 9:30 a.m. or noon.", ["content"])
    assert "content-003" not in rule_ids(r)


def test_social_length_limit(engine):
    text = "Come to the fall welcome. " * 20
    assert "content-011" in rule_ids(engine.analyze_text(text, ["content"], channel="social_media"))
    assert "content-011" not in rule_ids(engine.analyze_text(text, ["content"], channel="email"))


def test_content_misc(engine):
    text = "Students  & staff should read the the memo on October 8th. Call (312) 555-0100."
    r = engine.analyze_text(text, ["content"])
    by_id = {i.rule_id: i for i in r.issues}
    assert by_id["content-008"].suggestion == " "
    assert by_id["content-009"].suggestion == "and"
    assert by_id["content-007"].suggestion == "the"
    assert by_id["content-005"].suggestion == "October 8"
    assert by_id["content-010"].suggestion == "312-555-0100"


# ---------------------------------------------------------------- tone & reading level


def test_exclamations_used_rarely_in_email_and_web(engine):
    text = "Great! Wow! Amazing!"
    assert rule_ids(engine.analyze_text(text, ["audience_tone"], channel="email")).count("tone-006") == 2
    assert "tone-006" not in rule_ids(engine.analyze_text(text, ["audience_tone"], channel="social_media"))


def test_reading_level_rule_is_document_scope(engine):
    text = (
        "The institutional administration subsequently determined that comprehensive "
        "interdisciplinary collaboration necessitates considerable organizational "
        "restructuring. Consequently, departmental representatives must demonstrate "
        "substantial accountability regarding programmatic implementation initiatives. "
        "Accordingly, administrative personnel should anticipate additional institutional "
        "documentation requirements."
    )
    r = engine.analyze_text(text, ["reading_level"], audience="students")
    issue = next(i for i in r.issues if i.rule_id == "reading-001")
    assert issue.scope == "document"
    assert issue.severity.value == "high"
    assert r.reading_level.meets_target is False


def test_reading_level_targets_depend_on_audience(engine):
    r_students = engine.analyze_text("Hello there.", audience="students")
    r_faculty = engine.analyze_text("Hello there.", audience="faculty")
    assert r_students.reading_level.target_grade == 8
    assert r_faculty.reading_level.target_grade == 10


def test_long_sentence(engine):
    text = " ".join(["word"] * 30) + "."
    assert "reading-003" in rule_ids(engine.analyze_text(text, ["reading_level"]))


def test_text_stats(engine):
    r = engine.analyze_text("One two three. Four five.\n\nSix seven.")
    assert r.text_stats.word_count == 7
    assert r.text_stats.sentence_count == 3
    assert r.text_stats.paragraph_count == 2


# ---------------------------------------------------------------- UIC brand site rules


@pytest.mark.parametrize("text,rule_id,expected_suggestion", [
    ("the University of Illinois Chicago (UIC) campus", "brand-014", "University of Illinois Chicago"),
    ("Welcome to UICampus life", "brand-015", None),
    ("Visit UIC Hospital today", "brand-016", "UI Health"),
    ("UI Health College of Dentistry", "brand-016", "University of Illinois Chicago College of"),
    ("Meet at Chicago Circle Center", "brand-017", "UIC Student Center East"),
    ("John Marshall Law School alumni", "brand-017", "University of Illinois Chicago School of Law"),
    ("Read UIC Today for news", "brand-018", "UIC today"),
    ("The Jane Adams Hull House Museum", "brand-018", "Jane Addams"),
    ("Parking on east campus", "brand-019", "the east side of campus"),
])
def test_uic_brand_site_rules(engine, text, rule_id, expected_suggestion):
    hits = [i for i in engine.analyze_text(text, ["brand"]).issues if i.rule_id == rule_id]
    assert hits, f"{rule_id} did not fire on {text!r}"
    if expected_suggestion:
        assert hits[0].suggestion == expected_suggestion


def test_c_rule_allows_hashtags_and_uicc_is_historic(engine):
    ids = rule_ids(engine.analyze_text("Follow #UICFlames", ["brand"]))
    assert "brand-015" not in ids


@pytest.mark.parametrize("text,rule_id,suggestion", [
    ("Classes start September 3.", "content-014", "Sept."),
    ("Classes start Mar. 3.", "content-014", "March"),
    ("Classes start Sep 3.", "content-014", "Sept."),
    ("We meet in Oct. every year.", "content-014", "October"),
    ("Call 312.555.0100.", "content-013", "312-555-0100"),
    ("All freshmen live in the dorms.", "content-016", "first-year students"),
    ("She earned a Ph.D. in 2010.", "content-017", "PhD"),
    ("He has a Bachelors degree.", "content-017", "bachelor's degree"),
    ("Fees rose 5 percent.", "content-018", "5%"),
    ("Meet on Halsted St. near campus.", "content-019", "Street"),
    ("UIC is in Chicago, Illinois and growing.", "content-020", "Chicago"),
    ("Welcome!!", "content-021", "!"),
    ("Bring a pen, paper, and a laptop.", "content-022", "(remove this comma)"),
    ("We have 3 new advisers.", "content-023", "three"),
    ("It was great—really great.", "content-024", 'Use a comma, colon or parentheses (or " — ")'),
    ("It was great -- really great.", "content-024", 'Use a comma, colon or parentheses (or " — ")'),
    ("Ranked #1 in the city.", "content-025", "No. 1"),
    ("Register for the Fall semester now.", "content-026", "fall"),
    ('He called it "historic".', "content-027", '."'),
    ("Bring snacks (e.g chips).", "content-028", "e.g."),
    ("Send it to M/C 289.", "content-029", "MC 289"),
    ("An easily-remembered rule.", "content-030", "easily remembered"),
    ("Visit the healthcare fair on-line.", "content-015", "online"),
])
def test_uic_editorial_rules(engine, text, rule_id, suggestion):
    hits = [i for i in engine.analyze_text(text, ["content"]).issues if i.rule_id == rule_id]
    assert hits, f"{rule_id} did not fire on {text!r}; got {rule_ids(engine.analyze_text(text, ['content']))}"
    assert hits[0].suggestion == suggestion


@pytest.mark.parametrize("text", [
    "Classes start Sept. 3 and end in December.",
    "Our office is at 1200 W. Harrison St. in Chicago.",
    "Bring a pen, paper and a laptop.",
    "Meet at 3 p.m. in Room 2 on Oct. 8.",
    "Her 5-year-old son scored 95% on the test.",
    "Steps:\n1. Register\n2. Pay",
    "Fall is a great season. The fall semester starts soon.",
    "The University of Illinois Chicago School of Law is in the Loop.",
])
def test_uic_editorial_rules_do_not_false_positive(engine, text):
    r = engine.analyze_text(text, ["content"])
    assert r.issues == [], [(i.rule_id, i.matched_text) for i in r.issues]


@pytest.mark.parametrize("text,rule_id", [
    ("Students who are hearing-impaired can request captions.", "access-003"),
    ("Don't turn a blind eye to feedback.", "access-003"),
    ("Our program supports minority students.", "tone-007"),
    ("The bill affects illegal immigrants.", "tone-008"),
    ("We serve disadvantaged communities.", "tone-009"),
    ("We empower students.", "tone-010"),
    ("Join us for the chancellor's investiture.", "tone-011"),
    ("Each student should bring his or her ID.", "tone-002"),
    ("The chairman will speak.", "tone-002"),
])
def test_inclusive_language_rules(engine, text, rule_id):
    assert rule_id in rule_ids(engine.analyze_text(text, ["accessibility", "audience_tone"]))


def test_every_rule_has_source_and_guideline(engine):
    for rs in engine.rulesets.values():
        for rule in rs.rules:
            assert rule.source, rule.rule_id
            assert rule.guideline_url, rule.rule_id


# ---------------------------------------------------------------- team decisions (2026-10-08)


@pytest.mark.parametrize("text,suggestion", [
    ("Our alumni are invited.", "alums"),
    ("She is an alumna of the college.", "alum"),
    ("Alumni are welcome.", "Alums"),
])
def test_alumni_terms(engine, text, suggestion):
    hits = [i for i in engine.analyze_text(text, ["audience_tone"]).issues if i.rule_id == "tone-012"]
    assert hits and hits[0].suggestion == suggestion


def test_alumni_formal_names_are_kept(engine):
    text = "Join the University of Illinois Alumni Association at Alumni Weekend."
    assert "tone-012" not in rule_ids(engine.analyze_text(text, ["audience_tone"]))


def test_sentence_length_depends_on_audience(engine):
    text = " ".join(["word"] * 22) + "."
    assert "reading-003" in rule_ids(engine.analyze_text(text, ["reading_level"], audience="students"))
    assert "reading-003" not in rule_ids(engine.analyze_text(text, ["reading_level"], audience="faculty"))
    assert "reading-003" not in rule_ids(engine.analyze_text(text, ["reading_level"], audience="staff"))


def test_email_word_limit_is_200(engine):
    assert "content-012" not in rule_ids(engine.analyze_text("word " * 200, ["content"], channel="email"))
    assert "content-012" in rule_ids(engine.analyze_text("word " * 201, ["content"], channel="email"))


def test_social_limit_is_500_characters(engine):
    assert "content-011" not in rule_ids(engine.analyze_text("a" * 500, ["content"], channel="social_media"))
    assert "content-011" in rule_ids(engine.analyze_text("a" * 501, ["content"], channel="social_media"))
