# Rule Engine & Scoring (Workstream 2)

The rule engine checks text against UIC brand, accessibility, content, reading-level and tone rules. Its output is a list of issues with exact character positions, plus compliance scores. The orchestrator passes the issues to the LLM (Workstream 3) as rewrite instructions. The frontend (Workstream 4) uses the positions for highlighting and the scores for the compliance panel.

## Layout

```
backend/
  services/
    models.py           Pydantic models (Rule, Ruleset, Issue, AnalysisResult, ScoreResult)
    rule_engine.py      RuleEngine: loads /rulesets, runs rules, builds issues
    rule_functions.py   Function-based rules (reading level, acronyms, first reference, …)
    reading_level.py    Flesch-Kincaid grade / reading ease, syllables, sentence splitting
    scoring_service.py  Score calculation and status classification
  api/
    rules_routes.py     FastAPI router: /api/rules, /api/rules/{id}, /api/rules/check, /api/audiences
rulesets/
  *.json                One file per ruleset (see RULESETS.md)
  schema/ruleset.schema.json
scripts/generate_rules_mocks.py     Regenerate tests/mocks/*.json
scripts/generate_rules_review.py    Regenerate docs/RULES_REVIEW.md
tests/
  test_rule_engine.py, test_reading_level.py, test_scoring_service.py, test_rules_routes.py
  mocks/                Generated sample responses for other workstreams
```

## Running locally

```bash
python3 -m venv .venv && source .venv/bin/activate   # see note below
pip install -r requirements.txt
pytest                                               # 169 tests
uvicorn backend.api.rules_routes:app --reload        # http://127.0.0.1:8000/docs
```

> **Note:** `python -m venv` refuses to create a venv in a path that contains `:`. If your checkout path has one (e.g. `AWS:UIC/`), create the venv somewhere else, e.g. `python3 -m venv ~/venvs/uic`.

## Python interface (for the orchestrator, Task I.3)

```python
from backend.services.rule_engine import analyze_text          # uses a cached RuleEngine
from backend.services.scoring_service import calculate_scores

analysis = analyze_text(
    text,
    rulesets=["brand", "accessibility"],   # None = all rulesets with "enabled": true
    audience="students",                   # students | faculty | staff
    channel="email",                       # email | website | social_media | None
)
scores = calculate_scores(analysis)

for issue in analysis.issues:
    print(issue.rule_id, issue.severity, issue.matched_text, "→", issue.suggestion)
```

Exceptions:

| Exception | When |
|---|---|
| `TextTooLongError` | More than 5,000 words |
| `UnknownRulesetError` | A requested ruleset_id doesn't exist |
| `ValueError` | Invalid audience or channel |
| `RulesetValidationError` | A ruleset file is malformed (raised at startup, with the file name and rule_id) |

A rule that throws at runtime is logged and skipped, so one bad rule never fails the whole request.

## How analysis works

1. The rulesets are loaded and validated once per process. Regexes are precompiled. Keyword lists are compiled into one regex with word boundaries, longest phrase first.
2. For each selected ruleset, each rule runs only if it is `enabled` and its `audiences` / `channels` filters match the request. A rule with a `channels` filter does not run when no channel is given.
3. Each match becomes an `Issue`:

| Field | Meaning |
|---|---|
| `start`, `end` | Character offsets into the **original** text (end exclusive). Use these for highlighting. |
| `scope` | `"span"`: highlight `start..end`. `"document"`: the issue applies to the whole text (e.g. overall reading level), so show it in the sidebar and don't highlight it. |
| `line` | 1-based line number |
| `context` | About 40 characters either side, for display in an issue list |
| `suggestion` | Replacement text when the rule knows it (e.g. `"3 p.m."`), otherwise advice |
| `highlight_color` | The ruleset's color |
| `issue_id` | `"{rule_id}-{n}"`, stable for the same input |

4. Issues are sorted by position, then by severity.
5. `AnalysisResult` also includes `issue_counts` per ruleset, `severity_counts`, `reading_level` (grade, ease, audience target, `meets_target`) and `text_stats`.

## Reading level

Flesch-Kincaid grade = `0.39 × words/sentences + 11.8 × syllables/words − 15.59`.

| Audience | Target grade |
|---|---|
| students | 8 |
| faculty | 10 |
| staff | 10 |

Sentences are split on `. ! ?` and on line breaks, so headings and bullets count as separate sentences. Common abbreviations (Dr., Oct., a.m., e.g.) don't end a sentence, except that a.m./p.m./etc. do when a capitalized word follows. Syllables are counted heuristically, with an override table for common words that the heuristic gets wrong.

## Scoring

| Score | Rulesets that feed it |
|---|---|
| `brand_score` | brand, content, audience_tone |
| `accessibility_score` | accessibility, reading_level |

- Each score starts at 100 and loses 10 / 5 / 2 points per high / medium / low issue, with a floor of 0.
- **Per-rule cap:** a single rule deducts for at most 3 occurrences, so ten "e-mail"s don't zero the score. Every occurrence is still listed and counted in `total_issues`.
- `ruleset_scores` gives the same calculation for each ruleset on its own.

Status (checked in this order):

1. **Major Revisions**: either score < 70, or `total_issues` > 5
2. **Approved**: both scores ≥ 90 and `total_issues` ≤ 2
3. **Minor Revisions**: everything else

`status_reason` explains which condition applied. The mapping and thresholds are constants at the top of `scoring_service.py`.

## REST API

### `GET /api/rules?include_rules=false`

Lists rulesets for the ruleset panel.

```json
{ "rulesets": [ { "ruleset_id": "brand", "ruleset_name": "Brand Compliance Rules",
  "description": "…", "enabled": true, "highlight_color": "#3B82F6", "rule_count": 13 } ] }
```

### `GET /api/rules/{ruleset_id}`

Returns one ruleset with its full `rules` array. Returns 404 if the ID is unknown.

### `POST /api/rules/check`

```json
{ "text": "…", "audience": "students", "channel": "email",
  "rulesets": ["brand", "accessibility"] }
```

`audience` defaults to `students`. `channel` and `rulesets` are optional.

The response is `{ "analysis": AnalysisResult, "scores": ScoreResult }`. See `tests/mocks/rules_check_response.json` for a full example.

Errors: 422 for an empty or invalid body or an unknown audience/channel; 400 for whitespace-only text, more than 5,000 words, or an unknown ruleset.

### `GET /api/audiences`

```json
{ "audiences": [ { "audience_id": "students", "label": "Students", "target_grade_level": 8.0 }, … ],
  "channels": ["email", "website", "social_media"] }
```

### Mounting in the main app

```python
from backend.api.rules_routes import router as rules_router
app.include_router(rules_router)
```

## Mock data for other teams

These files in `tests/mocks/` are generated from the real engine:

| File | Contents |
|---|---|
| `rules_list_response.json` | `GET /api/rules` |
| `audiences_response.json` | `GET /api/audiences` |
| `rules_check_request.json` | Sample messy orientation email |
| `rules_check_response.json` | Its analysis (24 issues, Major Revisions) |
| `rules_check_response_clean.json` | A compliant text (Approved, 100/100) |

Regenerate them with `python scripts/generate_rules_mocks.py` after changing rules.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `RULESETS_DIR` | `<repo>/rulesets` | Where to load ruleset JSON from (useful for Lambda packaging) |

The engine has no AWS dependencies. In Lambda, its log output goes to CloudWatch through the standard `logging` module.
