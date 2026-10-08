# Demo data

Twenty-four synthetic UIC communication drafts for demos, UI testing and dataset validation (Task I.7). Each draft is based on one row of `Team8Dataset.xlsx` and contains exactly the issues that row lists.

| File | What it is |
|---|---|
| `demo_drafts.json` | The 24 drafts with metadata, planted issues (with exact offsets) and the dataset's expected scores. This is the source of truth. |
| `DATASET_PROFILE.md` | Profile of all 300 dataset rows: distributions, issue vocabulary, averages by status. |
| `VALIDATION.md` | Rule engine vs dataset comparison for each draft, overall agreement, engine gaps and likely false positives. Generated. |
| `validation_results.json` | Machine-readable version of the validation, including each draft's `engine_result`. Generated. |
| `../../frontend/src/data/demoSamples.json` | Compact list for the UI sample picker. Generated from the drafts. |

## How the drafts were made

1. **Profile.** `scripts/profile_dataset.py` reads the `Communications_Review` sheet (300 rows, 27 columns) and writes `DATASET_PROFILE.md`. The dataset has metadata and issue labels but no message text.
2. **Select.** We picked 24 rows by hand, with help from a coverage search:
   - All 14 communication types.
   - 8 Approved, 8 Minor Revisions Needed and 8 Major Revisions Needed rows.
   - 16 departments.
   - All three mapped audiences and channels.
   - Every issue label in the dataset except the 8-row variant "Reading level above Grade 10", which is covered by the "Reading level at Grade N" form.
   - Rows whose type, channel and audience fit together were preferred (no 1,000-word "social media post" sent by press distribution).
3. **Write.** Each draft is a realistic UIC message of the row's type, department and audience, dated near `draft_date`, and 60–185 words long. The dataset's `word_count` is kept in `dataset_expectations.word_count`. Every dataset issue is made concrete in the text:
   - **Text issues are written in:** "click here", a 140-word paragraph, `https//` links, "the the", legalistic tone for families, "Hey y'all... gonna... lol" for staff.
   - **Visual and structural issues appear as production notes,** the way a draft reaches a reviewer: `[Banner: light yellow text on a white background]`, `[Video: ... no captions]`, `[Letterhead: 2009 memo template with the old ... logo]`.
   - **Absences stay absent.** No subject line, no contact line, no call to action, no tagline. These have `evidence: null`.
   - **Brand slips.** Rows with brand issues also contain common UIC style slips that the rule engine checks for: "University of Illinois at Chicago", "UIC" before the full name, "e-mail", "April 15th", "12pm", "#1", "85 percent". These are listed separately as `editorial_slips`, so `planted_issues` matches the dataset row exactly.
   - **Clean rows.** Rows with no issues are on-brand copy that stays within the audience's reading target.
   - **Reading level.** Other drafts were written near the row's `flesch_kincaid_grade_level`.
   - **Placeholder details.** People are fictional, phone numbers are 312-555-01xx and email addresses are generic office addresses.
4. **Validate.** `scripts/validate_demo_data.py` runs the drafts through the Workstream 2 rule engine and writes the reports. Drafts were not tuned to improve agreement.

## Field mapping

The app supports three audiences and three channels. The dataset has more, so each draft keeps the original value (`target_audience_original`, `distribution_channel_original`) next to the mapped one (`audience`, `channel`).

| Dataset `target_audience` | App audience | Why |
|---|---|---|
| Current Students, Prospective Students | Students | Direct match |
| Parents & Families | Students | Student-facing family communications; grade 8 plain-language target |
| General Public | Students | Closest plain-language (grade 8) target |
| Faculty, Research Community | Faculty | Academic readers |
| Staff | Staff | Direct match |
| Alumni, Donors, Media | Staff | Adult, non-academic professional readers; grade 10 target |

| Dataset `distribution_channel` | App channel | Why |
|---|---|---|
| Email, Press Distribution | Email | Sent as email |
| University Website, Intranet, Mobile App | Website | Published pages |
| Print | Website | Long-form published copy; there is no print channel |
| Social Media | Social Media | Direct match |
| SMS, Digital Signage, Video Platform | Social Media | Short-form, glanceable or video copy; the 500-character social limit applies |

| Dataset `compliance_status` | App status (`compliance_status_mapped`) |
|---|---|
| Approved | Approved |
| Minor Revisions Needed | Minor Revisions |
| Major Revisions Needed, Rejected - Full Rewrite | Major Revisions |

Dataset issue labels map to the app's rulesets as follows:

| Ruleset | Dataset issue labels |
|---|---|
| `brand` | The 10 brand labels: logo, tagline, colors, fonts, template, disclaimer, stock photography, header formatting, brand voice |
| `accessibility` | All accessibility labels except reading level |
| `reading_level` | "Reading level at Grade N", "Excessive paragraph length" |
| `content` | Broken links, duplicate content, date formats, contact information, subject line, call to action, outdated statistics, spelling/grammar |
| `audience_tone` | Tone mismatch, undefined jargon, passive voice |

## `demo_drafts.json` schema

```jsonc
{
  "demo_id": "demo-01",                       // stable id, also used by demoSamples.json
  "source_communication_id": "COMM-00228",
  "title": "Family newsletter — College of Engineering",
  "communication_type": "Student Newsletter", // dataset value
  "department": "College of Engineering",
  "author_role": "Faculty Member",
  "draft_date": "2025-10-06",
  "target_audience_original": "Parents & Families",
  "audience": "Students",                     // Students | Faculty | Staff
  "distribution_channel_original": "Mobile App",
  "channel": "Website",                       // Email | Website | Social Media
  "suggested_rulesets": ["brand", "accessibility", "content", "reading_level", "audience_tone"],
  "text": "…",
  "planted_issues": [{
    "dataset_issue": "Low color contrast ratio", // exact dataset string
    "dataset_category": "accessibility",         // dataset column: brand | accessibility | content
    "ruleset": "accessibility",                  // app ruleset
    "evidence": "light yellow text on a white background", // or null for an absence
    "start": 825, "end": 864,                    // JS UTF-16 offsets, end-exclusive; null when evidence is null
    "occurrence": 2                              // optional: which occurrence of evidence (default 1)
  }],
  "editorial_slips": [{
    "evidence": "85 percent", "start": 724, "end": 734,
    "ruleset": "content", "expected_rule_id": "content-018", "note": "UIC style uses the % sign"
  }],
  "dataset_expectations": {
    "compliance_status": "Major Revisions Needed", "compliance_status_mapped": "Major Revisions",
    "brand_compliance_score": 54.8, "accessibility_score": 49.3, "total_issues_flagged": 8,
    "brand_issues_count": 3, "accessibility_issues_count": 3, "content_issues_count": 2,
    "flesch_kincaid_grade_level": 13.1, "word_count": 356, "image_count": 0, "link_count": 0,
    "manual_review_time_minutes": 32.6, "ai_review_time_seconds": 7.2, "time_savings_minutes": 32.5,
    "published": "No"
  },
  "demo_notes": "One sentence on why this draft demos well.",
  "featured": true
}
```

A dataset label can have more than one planted span, for example two "click here" links for "Links not descriptive". The number of distinct `dataset_issue` values always equals `total_issues_flagged`. `text.slice(start, end) === evidence` holds in JavaScript.

`demoSamples.json` entries are `{id, title, communication_type, department, audience, channel, status_hint, featured, text}`. They are ordered from most dramatic to clean: dataset status (Major, Minor, Approved), then the engine's issue count. `status_hint` uses the frontend's display strings (`Approved`, `Minor Revisions Needed`, `Major Revisions Needed`).

## Featured samples

| Demo | Why |
|---|---|
| `demo-01` Engineering family newsletter (Students / Website) | All five rulesets fire in the rule engine: brand hype and naming, "#1" and "!!!", "85 percent", a dense grade-13 paragraph, a headerless table and notes about contrast and captions. 150 words. |
| `demo-03` Simulation center video script (Faculty / Social Media) | "Hey guys!", "University of Illinois-Chicago" and "!!" sit next to logo, font, stock footage and caption notes. It also exceeds the social character limit, which shows channel rules. |
| `demo-11` Business school media newsletter (Staff / Email) | Two "click here" links, a "Read more", a misspelled raw URL, no subject line and no call to action. These are the easiest accessibility fixes for an audience to understand. |

## Regenerating

```bash
# Verify offsets only (fast; also run by the unit test)
.venv/bin/python scripts/validate_demo_data.py --check

# Full validation: rewrites VALIDATION.md, validation_results.json and frontend/src/data/demoSamples.json
.venv/bin/python scripts/validate_demo_data.py

# After editing a draft's text, recompute every start/end from its evidence string
.venv/bin/python scripts/validate_demo_data.py --fix-offsets

# Tests
.venv/bin/pytest -q tests/unit/test_demo_data.py

# Dataset profile (needs openpyxl, which is not in requirements.txt; the workbook is only read)
python -I scripts/profile_dataset.py ~/Downloads/Team8Dataset.xlsx data/demo/DATASET_PROFILE.md
```

The validation script exits non-zero if any offset is wrong. Its output depends only on the drafts and the rulesets, so re-running without changes produces identical files. Re-run it after any change to `rulesets/*.json` to refresh the agreement numbers.
