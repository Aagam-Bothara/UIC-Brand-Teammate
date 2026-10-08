# Rulesets

Rules live in `/rulesets/*.json`, one file per ruleset. Every `*.json` file in that folder is loaded when the server starts. All files must validate against [`rulesets/schema/ruleset.schema.json`](../rulesets/schema/ruleset.schema.json); `pytest` checks this.

See [RULE_ENGINE.md](RULE_ENGINE.md) for how rules are run and scored.

## Adding or changing a rule

1. Add an entry to the right ruleset file. Use the next free `rule_id` (`brand-014`, `content-013`, …).
2. Pick a `pattern_type`:
   - **`keyword`**: plain phrases, matched case-insensitively on word boundaries. Use a `{ "phrase": "replacement" }` map so each match gets its own suggestion.
   - **`regex`**: Python regular expression. Matching is case-insensitive unless `"case_sensitive": true`. Remember to double every backslash in JSON (`\\b`). A `suggestion` may use backreferences such as `"email\\1"`.
   - **`function`**: logic that a pattern can't express (counts, reading level, "first reference"). Write it in `backend/services/rule_functions.py` with `@rule_function("name")` and set `"pattern": "name"`. Settings go in `params`.
3. Limit the rule to specific `audiences` (`students`, `faculty`, `staff`) or `channels` (`email`, `website`, `social_media`) if needed. Leave these out to apply everywhere.
4. Add a test case in `tests/test_rule_engine.py`, then run `pytest`.
5. Run `python scripts/generate_rules_mocks.py` so the mock files stay current.

To turn a rule off without deleting it, set `"enabled": false`.

### Rule fields

| Field | Required | Notes |
|---|---|---|
| `rule_id` | yes | Unique across all rulesets, e.g. `brand-001` |
| `name` | yes | Short label shown in the UI |
| `severity` | yes | `high` (−10), `medium` (−5), `low` (−2) |
| `pattern_type` | yes | `regex`, `keyword`, `function` |
| `pattern` | yes | See above |
| `message` | | Explanation shown to the user |
| `suggestion` | | Replacement text or advice |
| `guideline_url` | | Link to the UIC guideline |
| `source` | | Where the rule comes from (UIC page and section, WCAG, or team-defined) |
| `case_sensitive` | | Default `false` |
| `audiences` / `channels` | | Default: all |
| `params` | | Function-rule settings. A value can be a single number or a per-audience map, e.g. `{"students": 20, "faculty": 25, "staff": 25}` |
| `enabled` | | Default `true` |

## Current rules

The full rule list is in [RULES_REVIEW.md](RULES_REVIEW.md), with each rule's source on brand.uic.edu. It is generated from the JSON, so regenerate it after any change:

```bash
python scripts/generate_rules_review.py
```

The rules were extracted from these pages on 2026-10-08:

| Page | Used for |
|---|---|
| [Name and boilerplate](https://brand.uic.edu/messaging/name-and-boilerplate/) | Official name, first reference, no "(UIC)" |
| [Editorial and style guide](https://brand.uic.edu/messaging/editorial-and-style-guide/) | UIC-specific terms, AP-based style, punctuation, dates, times, numbers |
| [Inclusive Language Guide](https://brand.uic.edu/messaging/inclusive-language-guide/) | Disability, gender, race/ethnicity, immigration, socioeconomic terms |
| [Voice and tone](https://brand.uic.edu/messaging/voice-and-tone/) | No filler, short sentences, confident and direct |
| [Social media guidelines](https://brand.uic.edu/resources/social-media-guidelines/) | Brief posts, alt text, professional tone |
| [ADA compliance](https://brand.uic.edu/resources/ada-compliance/) | Requires WCAG 2.1 AA, which is the basis for the accessibility checks |

> The SPEC's `brand-attributes-and-tone` and `key-audience-and-messaging` URLs now return 404. They have been replaced by *Voice and tone* and *Brand strategy*.

## Known limitations

- Reading level uses a heuristic syllable counter, so grades can be off by about ±1 compared with published calculators. Very short texts (under 30 words) skip the document-level check.
- `brand-013` only flags "the University" mid-sentence. Sentence-initial "The University" is not checked.
- `serial_comma` (content-022) and `small_numerals` (content-023) are heuristics. They can flag a comma that joins clauses, or a numeral in a context not on the exception list. Both are low severity.
- `content-015` flags "theater", following UIC's spelling of its own theatre. Other organizations' venue names may legitimately use "theater".
- Tone, voice and brand attributes that need judgment are left to the RAG + LLM pipeline (Workstreams 1 and 3). These rules cover only checks that can be decided mechanically.
