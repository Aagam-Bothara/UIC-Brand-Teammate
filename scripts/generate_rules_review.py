"""Generate docs/RULES_REVIEW.md: a review table of every rule, built from rulesets/*.json.

    python scripts/generate_rules_review.py

Rerun after changing any ruleset so the table matches what is implemented.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORDER = ["brand", "accessibility", "content", "reading_level", "audience_tone"]
MAX_EXAMPLES = 8

HEADER = """# Rules Review

Every rule the engine checks, generated from `rulesets/*.json` by
`scripts/generate_rules_review.py`. Do not edit by hand.

**Source** says where each rule comes from:
- **UIC …**: stated on brand.uic.edu (Name and boilerplate, Editorial and Style Guide,
  Inclusive Language Guide, Voice and tone, Social media guidelines).
- **Inferred from UIC …**: follows from a UIC rule but isn't spelled out word for word.
- **WCAG 2.1 AA**: UIC's ADA compliance page requires WCAG 2.1 AA but gives no specific
  writing rules, so these checks come from WCAG.
- **Team-defined**: our own threshold or word list (from the SPEC), not from UIC.

Severity deducts from the score: high −10, medium −5, low −2.

"""


def esc(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def what_it_flags(rule: dict) -> str:
    pattern = rule["pattern"]
    if rule["pattern_type"] == "keyword":
        if isinstance(pattern, dict):
            items = [f"\"{k}\" → \"{v}\"" for k, v in pattern.items()]
        else:
            items = [f"\"{k}\"" for k in ([pattern] if isinstance(pattern, str) else pattern)]
        more = len(items) - MAX_EXAMPLES
        shown = "; ".join(items[:MAX_EXAMPLES])
        return shown + (f"; +{more} more" if more > 0 else "")
    return rule.get("message", "")


def applies_to(rule: dict) -> str:
    parts = []
    if rule.get("audiences"):
        parts.append(", ".join(rule["audiences"]))
    if rule.get("channels"):
        parts.append(", ".join(rule["channels"]).replace("social_media", "social"))
    return "; ".join(parts) or "all"


def main():
    out = [HEADER]
    summary = ["| Ruleset | Rules | From UIC site | Inferred | WCAG | Team-defined |",
               "|---|---|---|---|---|---|"]
    sections = []
    for rid in ORDER:
        data = json.loads((ROOT / "rulesets" / f"{rid}.json").read_text(encoding="utf-8"))
        counts = {"uic": 0, "inferred": 0, "wcag": 0, "team": 0}
        rows = []
        for rule in data["rules"]:
            src = rule.get("source", "")
            if src.startswith("Inferred"):
                counts["inferred"] += 1
            elif src.startswith("UIC"):
                counts["uic"] += 1
            elif src.startswith("WCAG"):
                counts["wcag"] += 1
            else:
                counts["team"] += 1
            fix = rule.get("suggestion") or ("per match" if isinstance(rule["pattern"], dict) else "")
            if rule["pattern_type"] == "function" and not rule.get("suggestion"):
                fix = "computed per match"
            if not rule.get("enabled", True):
                fix += " (disabled)"
            link = f"[{esc(src)}]({rule['guideline_url']})" if rule.get("guideline_url") else esc(src)
            rows.append(
                f"| {rule['rule_id']} | {esc(rule['name'])} | {rule['severity']} | "
                f"{esc(what_it_flags(rule))} | {esc(fix)} | {link} | {applies_to(rule)} |"
            )
        summary.append(
            f"| {data['ruleset_name']} | {len(data['rules'])} | {counts['uic']} | "
            f"{counts['inferred']} | {counts['wcag']} | {counts['team']} |"
        )
        sections.append(
            f"## {data['ruleset_name']} (`{rid}`)\n\n{data['description']}\n\n"
            "| ID | Rule | Severity | What it flags | Fix | Source | Applies to |\n"
            "|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n"
        )
    out.append("## Summary\n\n" + "\n".join(summary) + "\n\n")
    out.append("\n".join(sections))
    out.append(NOT_AUTOMATED)
    path = ROOT / "docs" / "RULES_REVIEW.md"
    path.write_text("".join(out), encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


NOT_AUTOMATED = """
## UIC guidelines not implemented as rules

These need judgment or context that pattern matching can't supply. The RAG + LLM rewrite
(Workstreams 1 and 3) should cover them using the guideline text.

| Guideline | Why it isn't a rule |
|---|---|
| Titles: capitalize before a name, lowercase after ("Chancellor Marie Lynn Miranda" vs. "Mary Smith, dean,") | Needs to know which words are names and titles |
| Gov./Sen./Rep. before names; Dr. only for medical/dental degrees | Needs name detection |
| Department names: capitalize formal names, lowercase later references | Needs to know first vs. later reference to the same department |
| Class-year format (John Jones '87, MS '89) and alumni terms | Rare in this tool's content; risky to auto-detect |
| Possessives, colon capitalization, semicolons, hyphenated compound modifiers | Grammar that needs parsing |
| Faculty/staff verb agreement ("faculty take" vs. "the faculty takes") | Grammar that needs parsing |
| Academic/fiscal year format (2025-26; FY 2026) | Too many valid forms to flag reliably |
| Numbers: ordinals first through ninth spelled out | Partly covered (content-005, content-023); full ordinal check is noisy |
| Inclusive language: don't mention race, disability, immigration status, religion or sexual orientation unless relevant and approved | Needs judgment about relevance |
| Identity-first vs. person-first language; use the person's own terms (Latinx/Latino, Deaf/deaf, tribe names) | Depends on the person's preference |
| "Pacific Islander" is not "Asian"; capitalize Black and Indigenous; lowercase white | Capitalization rules: possible future rule, but high false-positive risk (e.g. "white paper") |
| Religion: avoid "extremist", "militant", "cult", "sect" | Common non-religious uses ("cult classic") cause false positives |
| Voice and tone: community-centered, resilient, innovative, welcoming, purposeful, bold; "Make It Known" | Qualitative; the LLM prompt should use these |
| Don't use the brand narrative or "Make It Known" verbatim as a tagline in external copy | Needs context about the piece |
| Brand strategy: frame outcomes around achievement, not debt ("what you will achieve," not "what you owe") | Qualitative |
| Social media: alt text on every photo, captions on video, approved logos and templates | Images and video are out of scope for Phase 1 (text only) |

## Conflicts between UIC pages (resolved 2026-10-08)

Team decision: apply the stricter guideline on every channel and for every audience.

| Topic | Conflict | Decision | Rule |
|---|---|---|---|
| Alumni terms | The Editorial guide allows alumnus/alumna/alumni/alumnae; the Inclusive Language Guide prefers "alum/alums" | Flag gendered terms and suggest alum/alums; formal names (Alumni Association, Alumni Weekend) are left alone | tone-012 |
| First reference to UIC | The Name and boilerplate page says to use the full name wherever possible; the Editorial guide allows "UIC" first for internal audiences | Require the full name first on all channels and audiences | brand-006 |
| Em dashes | The Editorial guide recommends spaced em dashes but also says to avoid them in documents sent or converted electronically | Flag every em dash (all our channels are electronic); suggest a comma, colon or parentheses, or a spaced dash | content-024 |

## Team-defined limits (set 2026-10-08)

| Limit | Value | Rule |
|---|---|---|
| Social media post length | 500 characters | content-011 |
| Email length | 200 words | content-012 |
| Sentence length | Students 20 words; faculty and staff 25 words | reading-003 (and reading-002 skips sentences over these limits) |
"""

if __name__ == "__main__":
    main()
