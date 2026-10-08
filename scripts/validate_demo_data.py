"""Validate the demo drafts against the Workstream 2 rule engine (Task I.7, dataset validation).

    .venv/bin/python scripts/validate_demo_data.py            # verify offsets, run engine, write reports
    .venv/bin/python scripts/validate_demo_data.py --check    # verify offsets only, write nothing
    .venv/bin/python scripts/validate_demo_data.py --fix-offsets   # recompute start/end from evidence

Inputs:  data/demo/demo_drafts.json
Outputs: data/demo/VALIDATION.md, data/demo/validation_results.json and
         frontend/src/data/demoSamples.json (compact list for the UI sample picker)

Offsets in demo_drafts.json are JavaScript (UTF-16 code unit) offsets, end-exclusive, so the
frontend can use them with String.prototype.slice. Exit status is 1 if any offset is wrong
(after --fix-offsets, only if an evidence string cannot be found). The reports are fully
determined by the drafts and the rulesets, so re-running without changes is a no-op.
"""
from __future__ import annotations

import argparse
import re
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DRAFTS_PATH = ROOT / "data" / "demo" / "demo_drafts.json"
REPORT_PATH = ROOT / "data" / "demo" / "VALIDATION.md"
RESULTS_PATH = ROOT / "data" / "demo" / "validation_results.json"
SAMPLES_PATH = ROOT / "frontend" / "src" / "data" / "demoSamples.json"
# Frontend display form of the status (frontend/src/types/api.ts ComplianceStatus).
STATUS_HINT = {"Approved": "Approved", "Minor Revisions": "Minor Revisions Needed",
               "Major Revisions": "Major Revisions Needed"}

RULESETS = ["brand", "accessibility", "content", "reading_level", "audience_tone"]
AUDIENCES = {"Students": "students", "Faculty": "faculty", "Staff": "staff"}
CHANNELS = {"Email": "email", "Website": "website", "Social Media": "social_media"}
STATUSES = ["Approved", "Minor Revisions", "Major Revisions"]

# Which rule-engine rules count as detecting each dataset issue label.
# An empty list means the rule engine has no rule for it (a Workstream 2 gap).
DETECTING_RULES: Dict[str, List[str]] = {
    # brand
    "Missing UIC tagline": [],
    "Unapproved department logo": [],
    "Incorrect UIC logo version": [],
    "Wrong brand colors used": [],
    "Non-standard fonts detected": [],
    "Incorrect header formatting": ["access-002"],
    "Missing official template": [],
    "Missing disclaimer text": [],
    "Unauthorized stock photography": [],
    "Brand voice inconsistency": [f"brand-{i:03d}" for i in range(1, 20)]
    + ["tone-002", "tone-006", "tone-010", "content-021", "content-025", "access-002"],
    # accessibility
    "No skip navigation": [],
    "Flashing content detected": [],
    "Missing alt text on images": ["access-004"],
    "No keyboard navigation support": [],
    "No heading hierarchy": [],
    "Video missing captions": [],
    "Table without headers": [],
    "Small font size (<12pt)": [],
    "Low color contrast ratio": [],
    "Form fields unlabeled": [],
    "Missing language attribute": [],
    "PDF not tagged for screen readers": [],
    "Links not descriptive": ["access-001", "access-005"],
    # reading level
    "Reading level": ["reading-001", "reading-002", "reading-003"],
    "Excessive paragraph length": ["reading-004"],
    # content
    "Broken hyperlinks": [],
    "Duplicate content detected": [],
    "Inconsistent date formats": ["content-005", "content-014"],
    "Missing contact information": [],
    "Missing subject line (email)": [],
    "Missing call-to-action": [],
    "Outdated statistics referenced": [],
    "Spelling/grammar errors detected": ["content-007"],
    # audience tone
    "Tone mismatch for target audience": [
        "tone-001", "tone-002", "tone-003", "tone-004", "tone-005", "tone-006", "content-021", "access-002",
    ],
    "Jargon not defined for audience": ["tone-003", "access-007", "reading-005"],
    "Passive voice overuse": ["tone-005"],
}


# Engine findings on these drafts that look wrong on inspection. Each entry is
# (rule_id, regex searched in the issue's context, explanation). Reported, never filtered.
KNOWN_FALSE_POSITIVES = [
    ("content-022", r"Architecture, Design, and the Arts",
     "Serial comma rule fires on the official college name \"College of Architecture, Design, and the Arts\"."),
    ("content-022", r"Suite \d+, or call",
     "Serial comma rule fires on an address comma (\"Building, Suite 3030, or call\")."),
    ("content-022", r"this year, and the review",
     "Serial comma rule fires on a comma that joins two independent clauses, not a list."),
    ("content-007", r"_{2,}\s+_{2,}",
     "Repeated-word rule treats form blanks (\"____ ____\") as a repeated word because \\w includes underscores."),
    ("content-007", r"research Research",
     "Repeated-word rule matches across a line break, from the end of a heading to the first word of the next line."),
    ("content-030", r"https?:?//\S*ly-",
     "The -ly hyphen rule fires inside URLs (misspelled paths such as \"famly-events\")."),
    ("access-007", r"AGAIN",
     "Acronym rule flags a single all-caps word used for emphasis (\"AGAIN\"); it is shouting, not an acronym."),
    ("access-007", r"\bQR\b",
     "Acronym rule flags \"QR\" (as in QR code), which is widely understood; consider adding it to the allowlist."),
    ("access-005", r"https?://\S+\.\s*$|https?://\S+\.(?=\s|…|$)",
     "Raw-URL rule includes the sentence-ending period in the matched URL."),
]


def detecting_rules(label: str) -> List[str]:
    if label.startswith("Reading level"):
        return DETECTING_RULES["Reading level"]
    return DETECTING_RULES[label]


# ---------------------------------------------------------------------------
# Offsets (JS UTF-16 <-> Python code points)
# ---------------------------------------------------------------------------


def utf16_len(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def js_slice(text: str, start: int, end: int) -> str:
    units = text.encode("utf-16-le")
    return units[2 * start:2 * end].decode("utf-16-le", errors="strict")


def py_index(text: str, utf16_offset: int) -> int:
    """Convert a UTF-16 offset into a Python string index."""
    n = 0
    for i, ch in enumerate(text):
        if n >= utf16_offset:
            return i
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def find_occurrence(text: str, evidence: str, occurrence: int) -> Optional[Tuple[int, int]]:
    pos = -1
    for _ in range(occurrence):
        pos = text.find(evidence, pos + 1)
        if pos < 0:
            return None
    return utf16_len(text[:pos]), utf16_len(text[:pos + len(evidence)])


def spans(draft: dict):
    for kind in ("planted_issues", "editorial_slips"):
        for item in draft.get(kind, []):
            yield kind, item


def check_offsets(drafts: List[dict]) -> List[str]:
    errors = []
    for d in drafts:
        for kind, item in spans(d):
            ev = item.get("evidence")
            where = f"{d['demo_id']} {kind} {item.get('dataset_issue') or item.get('expected_rule_id')}"
            if ev is None:
                if item.get("start") is not None or item.get("end") is not None:
                    errors.append(f"{where}: evidence is null but start/end are set")
                continue
            s, e = item.get("start"), item.get("end")
            if not isinstance(s, int) or not isinstance(e, int) or not 0 <= s < e <= utf16_len(d["text"]):
                errors.append(f"{where}: invalid offsets {s}..{e}")
                continue
            got = js_slice(d["text"], s, e)
            if got != ev:
                errors.append(f"{where}: text[{s}:{e}] is {got!r}, expected {ev!r}")
    return errors


def fix_offsets(drafts: List[dict]) -> List[str]:
    errors = []
    for d in drafts:
        for kind, item in spans(d):
            ev = item.get("evidence")
            if ev is None:
                item["start"] = item["end"] = None
                continue
            found = find_occurrence(d["text"], ev, item.get("occurrence", 1))
            if found is None:
                errors.append(f"{d['demo_id']}: evidence not found: {ev!r}")
            else:
                item["start"], item["end"] = found
    return errors


# ---------------------------------------------------------------------------
# Engine run
# ---------------------------------------------------------------------------


def overlaps(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def run_engine(drafts: List[dict]) -> List[dict]:
    from backend.services import reading_level as rl
    from backend.services.rule_engine import RuleEngine
    from backend.services.scoring_service import calculate_scores

    engine = RuleEngine()
    results = []
    for d in drafts:
        text = d["text"]
        audience = AUDIENCES[d["audience"]]
        channel = CHANNELS[d["channel"]]
        analysis = engine.analyze_text(text, rulesets=d.get("suggested_rulesets") or None,
                                       audience=audience, channel=channel)
        scores = calculate_scores(analysis)
        metrics = rl.compute_metrics(text)
        issues = analysis.issues

        accounted = set()  # indexes of engine issues explained by a planted issue or slip

        planted_results = []
        for p in d["planted_issues"]:
            rules = detecting_rules(p["dataset_issue"])
            hits = []
            if p["evidence"] is not None:
                span = (py_index(text, p["start"]), py_index(text, p["end"]))
                for i, iss in enumerate(issues):
                    if iss.rule_id in rules and (iss.scope == "document" or overlaps(span, (iss.start, iss.end))):
                        hits.append(i)
            else:
                hits = [i for i, iss in enumerate(issues) if iss.rule_id in rules]
            accounted.update(hits)
            planted_results.append({
                "dataset_issue": p["dataset_issue"],
                "ruleset": p["ruleset"],
                "detectable": bool(rules),
                "detected": bool(hits),
                "rule_ids": sorted({issues[i].rule_id for i in hits}),
            })

        slip_results = []
        for s in d.get("editorial_slips", []):
            span = (py_index(text, s["start"]), py_index(text, s["end"]))
            hits = [i for i, iss in enumerate(issues)
                    if iss.rule_id == s["expected_rule_id"] and overlaps(span, (iss.start, iss.end))]
            accounted.update(hits)
            slip_results.append({"evidence": s["evidence"], "expected_rule_id": s["expected_rule_id"],
                                 "detected": bool(hits)})

        extra = [
            {"rule_id": iss.rule_id, "ruleset": iss.ruleset_id, "severity": iss.severity.value,
             "scope": iss.scope,
             "matched_text": iss.matched_text if iss.scope == "span" else "(whole document)",
             "context": iss.context}
            for i, iss in enumerate(issues) if i not in accounted
        ]

        exp = d["dataset_expectations"]
        results.append({
            "demo_id": d["demo_id"],
            "source_communication_id": d["source_communication_id"],
            "communication_type": d["communication_type"],
            "audience": d["audience"],
            "channel": d["channel"],
            "dataset": {
                "status": exp["compliance_status"],
                "status_mapped": exp["compliance_status_mapped"],
                "brand_score": exp["brand_compliance_score"],
                "accessibility_score": exp["accessibility_score"],
                "total_issues": exp["total_issues_flagged"],
                "fk_grade": exp["flesch_kincaid_grade_level"],
            },
            "engine_result": {
                "issue_counts": dict(analysis.issue_counts),
                "total_issues": scores.total_issues,
                "rule_ids": sorted({i.rule_id for i in issues}),
                "brand_score": scores.brand_score,
                "accessibility_score": scores.accessibility_score,
                "status": scores.status.value,
                "status_reason": scores.status_reason,
                "reading_grade": round(metrics.grade_level, 1),
                "reading_target": rl.grade_target_for(audience),
                "word_count": analysis.text_stats.word_count,
            },
            "status_match": scores.status.value == exp["compliance_status_mapped"],
            "planted": planted_results,
            "slips": slip_results,
            "unplanned_engine_issues": extra,
        })
    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "n/a"


def build_report(drafts: List[dict], results: List[dict]) -> str:
    n = len(results)
    status_ok = sum(r["status_match"] for r in results)
    planted = [p for r in results for p in r["planted"]]
    detectable = [p for p in planted if p["detectable"]]
    detected = [p for p in planted if p["detected"]]
    slips = [s for r in results for s in r["slips"]]
    slips_ok = [s for s in slips if s["detected"]]
    brand_mae = sum(abs(r["engine_result"]["brand_score"] - r["dataset"]["brand_score"]) for r in results) / n
    acc_mae = sum(abs(r["engine_result"]["accessibility_score"] - r["dataset"]["accessibility_score"])
                  for r in results) / n
    within1 = sum(
        abs(STATUSES.index(r["engine_result"]["status"]) - STATUSES.index(r["dataset"]["status_mapped"])) <= 1
        for r in results)

    confusion = Counter((r["dataset"]["status_mapped"], r["engine_result"]["status"]) for r in results)

    out = [
        "# Demo data validation (Task I.7, first pass)",
        "",
        "Generated by `scripts/validate_demo_data.py`. Do not edit by hand.",
        "",
        f"The {n} hand-written drafts in `demo_drafts.json` were run through the Workstream 2 rule engine "
        "(`RuleEngine().analyze_text` with all five rulesets, the draft's mapped audience and channel) and "
        "`scoring_service.calculate_scores`. Each draft plants exactly the issues listed for its source row "
        "in Team8Dataset.xlsx. Drafts were edited only to make planted issues concrete and to keep clean drafts "
        "within UIC style and the audience's reading target. They were not tuned to improve agreement.",
        "",
        "## Summary",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Status agreement (engine vs dataset) | **{status_ok}/{n} ({pct(status_ok, n)})** |",
        f"| Status within one level | {within1}/{n} ({pct(within1, n)}) |",
        f"| Planted dataset issues detected (all) | {len(detected)}/{len(planted)} ({pct(len(detected), len(planted))}) |",
        f"| Planted issues detected, among types the engine has a rule for | "
        f"{sum(p['detected'] for p in detectable)}/{len(detectable)} "
        f"({pct(sum(p['detected'] for p in detectable), len(detectable))}) |",
        f"| Editorial slips detected (UIC style errors woven into the text) | {len(slips_ok)}/{len(slips)} "
        f"({pct(len(slips_ok), len(slips))}) |",
        f"| Mean absolute score gap, brand / accessibility | {brand_mae:.1f} / {acc_mae:.1f} points |",
        "",
        "Planted-issue counts are per evidence entry: a dataset label can have more than one planted span "
        "(for example two non-descriptive links). Dataset status \"Rejected - Full Rewrite\" is treated as Major Revisions.",
        "",
        "### Status confusion matrix (rows: dataset, columns: engine)",
        "",
        "| Dataset \\ Engine | " + " | ".join(STATUSES) + " |",
        "|---|" + "---:|" * len(STATUSES),
    ]
    for ds in STATUSES:
        out.append(f"| {ds} | " + " | ".join(str(confusion.get((ds, es), 0)) for es in STATUSES) + " |")
    out.append("")

    out += [
        "## Per-draft results",
        "",
        "| Demo | Source | Type | Audience / channel | Dataset status | Engine status | Brand (ds → eng) "
        "| Access. (ds → eng) | Issues (ds → eng) | FK (ds → eng, target) | Planted detected |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        ds, en = r["dataset"], r["engine_result"]
        det = sum(p["detected"] for p in r["planted"])
        mark = "" if r["status_match"] else " ✗"
        out.append(
            f"| {r['demo_id']} | {r['source_communication_id']} | {r['communication_type']} "
            f"| {r['audience']} / {r['channel']} | {ds['status_mapped']} | {en['status']}{mark} "
            f"| {ds['brand_score']:g} → {en['brand_score']} | {ds['accessibility_score']:g} → {en['accessibility_score']} "
            f"| {ds['total_issues']} → {en['total_issues']} | {ds['fk_grade']:g} → {en['reading_grade']:g} "
            f"({en['reading_target']:g}) | {det}/{len(r['planted'])} |"
        )
    out.append("")

    out += ["## Planted vs detected, by draft", ""]
    for r in results:
        en = r["engine_result"]
        counts = ", ".join(f"{k} {v}" for k, v in en["issue_counts"].items())
        out += [f"### {r['demo_id']} ({r['source_communication_id']}, {r['communication_type']})", "",
                f"Engine issues by ruleset: {counts}. Rules hit: {', '.join(en['rule_ids']) or 'none'}.", ""]
        if r["planted"]:
            out += ["| Dataset issue | Ruleset | Engine has a rule | Detected by |", "|---|---|---|---|"]
            for p in r["planted"]:
                out.append(f"| {p['dataset_issue']} | {p['ruleset']} | {'yes' if p['detectable'] else 'no'} "
                           f"| {', '.join(p['rule_ids']) if p['detected'] else '—'} |")
            out.append("")
        else:
            out += ["No planted issues (clean draft).", ""]
        if r["slips"]:
            out.append("Editorial slips: " + "; ".join(
                f"`{s['evidence']}` → {s['expected_rule_id']} {'✓' if s['detected'] else '✗'}" for s in r["slips"]) + ".")
            out.append("")
        if r["unplanned_engine_issues"]:
            grouped = Counter(f"{x['rule_id']} `{x['matched_text'][:40]}`" for x in r["unplanned_engine_issues"])
            out.append("Engine findings not tied to a planted issue: " + "; ".join(
                f"{k}" + (f" ×{v}" if v > 1 else "") for k, v in grouped.items()) + ".")
            out.append("")

    # Gaps
    by_label = defaultdict(lambda: [0, 0])
    for p in planted:
        label = "Reading level at Grade N" if p["dataset_issue"].startswith("Reading level") else p["dataset_issue"]
        by_label[label][0] += 1
        by_label[label][1] += p["detected"]
    out += [
        "## Detection by dataset issue type",
        "",
        "| Dataset issue | Ruleset | Planted | Detected | Engine rules that count |",
        "|---|---|---:|---:|---|",
    ]
    ruleset_of = {}
    for d in drafts:
        for p in d["planted_issues"]:
            label = "Reading level at Grade N" if p["dataset_issue"].startswith("Reading level") else p["dataset_issue"]
            ruleset_of[label] = p["ruleset"]
    for label in sorted(by_label, key=lambda k: (ruleset_of[k], k)):
        rules = detecting_rules(label)
        shown = "brand-*, " + ", ".join(r for r in rules if not r.startswith("brand-")) if len(rules) > 10 else ", ".join(rules)
        out.append(f"| {label} | {ruleset_of[label]} | {by_label[label][0]} | {by_label[label][1]} | {shown or '—'} |")
    out.append("")

    gaps = sorted(k for k in by_label if not detecting_rules(k))
    out += [
        "## Rule-engine gaps (for Workstream 2)",
        "",
        f"The rule engine has no rule for {len(gaps)} of the {len(by_label)} dataset issue types planted here:",
        "",
    ]
    visual = {"Unapproved department logo", "Incorrect UIC logo version", "Wrong brand colors used",
              "Non-standard fonts detected", "Unauthorized stock photography", "Low color contrast ratio",
              "Small font size (<12pt)", "Flashing content detected"}
    structural = {"No skip navigation", "No keyboard navigation support", "No heading hierarchy",
                  "Table without headers", "Form fields unlabeled", "Missing language attribute",
                  "PDF not tagged for screen readers", "Video missing captions", "Missing official template"}
    groups = [
        ("Visual and design issues (need the rendered file or image analysis, Phase 2)", visual),
        ("Document structure and media issues (need HTML/PDF/video input, not plain text)", structural),
        ("Absence and semantic checks (possible as new text rules or LLM checks)", None),
    ]
    for title, members in groups:
        items = [g for g in gaps if (members is None and not any(g in m for _, m in groups[:2]))
                 or (members is not None and g in members)]
        if items:
            out.append(f"- **{title}:** " + "; ".join(items) + ".")
    out += [
        "",
        "Ideas for the absence and semantic group: required-element checks per channel (subject line for email, "
        "contact line, call to action, accommodation or disclaimer statement, tagline), a URL syntax check "
        "(`https//`, spaces, misspelled paths) for broken links, a duplicate-sentence check, a stale-year check "
        "for statistics (\"In 2012, ...\"), and a passive-voice heuristic. A spelling checker would catch "
        "typos like \"recieve\"; today only doubled words are caught.",
        "",
    ]
    partial = [(k, v) for k, v in by_label.items() if detecting_rules(k) and v[1] < v[0]]
    if partial:
        out += ["Issue types with a rule that still missed some planted instances:", ""]
        why = {
            "Missing alt text on images": "access-004 only matches Markdown or HTML images, not a text placeholder "
                                          "such as `[Image: photo.jpg]`.",
            "Inconsistent date formats": "content-005 and content-014 catch ordinals and month abbreviations, but not "
                                         "numeric dates (`8/20`, `10/23`) mixed with written dates.",
            "Passive voice overuse": "tone-005 only matches set bureaucratic phrases (\"it is recommended that\"), "
                                     "not general passive voice (\"will be led by\").",
            "Spelling/grammar errors detected": "content-007 catches doubled words only; there is no spelling check "
                                                "(\"recieve\").",
            "Brand voice inconsistency": "hype without a style error (\"the coolest nursing school... nobody does it "
                                         "better\") has no rule.",
        }
        for k, v in sorted(partial):
            out.append(f"- **{k}** ({v[1]}/{v[0]}): {why.get(k, 'see per-draft tables.')}")
        out.append("")

    fp_hits = defaultdict(list)

    for r in results:
        for x in r["unplanned_engine_issues"]:
            for rule_id, pattern, explanation in KNOWN_FALSE_POSITIVES:
                if x["rule_id"] == rule_id and re.search(pattern, x["context"].replace("\n", " ")):
                    fp_hits[(rule_id, explanation)].append(r["demo_id"])
                    break
    if fp_hits:
        out += ["## Likely false positives (for Workstream 2)", "",
                "Engine findings on these drafts that look wrong on inspection. They are counted in the engine "
                "scores above; nothing is filtered.", "",
                "| Rule | Drafts | Problem |", "|---|---|---|"]
        for (rule_id, explanation), ids in sorted(fp_hits.items()):
            out.append(f"| {rule_id} | {', '.join(sorted(set(ids)))} | {explanation} |")
        out.append("")

    # Disagreements
    out += ["## Notes on disagreements", ""]
    over = [r for r in results if STATUSES.index(r["engine_result"]["status"]) > STATUSES.index(r["dataset"]["status_mapped"])]
    under = [r for r in results if STATUSES.index(r["engine_result"]["status"]) < STATUSES.index(r["dataset"]["status_mapped"])]
    if over:
        out.append(f"- **Engine stricter than dataset ({len(over)}):** " + ", ".join(
            f"{r['demo_id']} ({r['dataset']['status_mapped']} → {r['engine_result']['status']}: "
            f"{r['engine_result']['status_reason']})" for r in over) + ".")
    if under:
        out.append(f"- **Engine more lenient than dataset ({len(under)}):** " + ", ".join(
            f"{r['demo_id']} ({r['dataset']['status_mapped']} → {r['engine_result']['status']}, "
            f"{sum(p['detected'] for p in r['planted'])}/{len(r['planted'])} planted detected)" for r in under) + ".")
    doc_level = [r["demo_id"] for r in results
                 if any(x["rule_id"] == "reading-001" for x in r["unplanned_engine_issues"])]
    sentence_level = [r["demo_id"] for r in results
                      if any(x["rule_id"] in ("reading-002", "reading-003", "reading-004")
                             for x in r["unplanned_engine_issues"])]
    if doc_level:
        out.append(f"- **Whole-document reading level above target, with no reading-level label in the dataset "
                   f"({len(doc_level)}):** " + ", ".join(doc_level) + ". These drafts were written near the row's "
                   "`flesch_kincaid_grade_level`, which is above the SPEC target (8 for students, 10 for faculty and "
                   "staff). The dataset only labels some rows like this, so its reading-level label is inconsistent.")
    if sentence_level:
        out.append(f"- **Sentence or paragraph reading findings not tied to a planted issue ({len(sentence_level)}):** "
                   + ", ".join(sentence_level) + ". reading-002/003/004 flag single long or dense sentences and "
                   "paragraphs, including in clean drafts. One finding does not change an Approved status, but "
                   "these rules are stricter than the dataset's approval bar.")
    out += [
        "- **Dataset labels vs SPEC thresholds:** the dataset's own statuses do not follow the SPEC rules. "
        "For example, some rows labeled Major have three issues and scores in the 50s, and some rows labeled "
        "Approved have accessibility scores in the 70s. The engine applies the SPEC thresholds exactly, so it "
        "cannot agree on every row.",
        "- **Score scales differ:** dataset scores are continuous (for example 54.4) and include visual and "
        "structural issues the engine never sees. Engine scores come only from text rules.",
        "",
    ]
    return "\n".join(out)


def build_samples(drafts: List[dict], results: List[dict]) -> List[dict]:
    """Compact sample list for the UI, most dramatic first: dataset status (Major, Minor, Approved),
    then the engine's issue count, then demo_id."""
    by_id = {r["demo_id"]: r for r in results}

    def key(d):
        status = d["dataset_expectations"]["compliance_status_mapped"]
        return (-STATUSES.index(status), -by_id[d["demo_id"]]["engine_result"]["total_issues"], d["demo_id"])

    return [
        {
            "id": d["demo_id"],
            "title": d["title"],
            "communication_type": d["communication_type"],
            "department": d["department"],
            "audience": d["audience"],
            "channel": d["channel"],
            "status_hint": STATUS_HINT[d["dataset_expectations"]["compliance_status_mapped"]],
            "featured": bool(d.get("featured")),
            "text": d["text"],
        }
        for d in sorted(drafts, key=key)
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only verify offsets; write nothing")
    ap.add_argument("--fix-offsets", action="store_true", help="recompute start/end from evidence and save")
    args = ap.parse_args(argv)

    drafts = json.loads(DRAFTS_PATH.read_text(encoding="utf-8"))

    if args.fix_offsets:
        errors = fix_offsets(drafts)
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        DRAFTS_PATH.write_text(json.dumps(drafts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Recomputed offsets in {DRAFTS_PATH.relative_to(ROOT)}")

    errors = check_offsets(drafts)
    if errors:
        print("Offset errors:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    n_spans = sum(1 for d in drafts for kind, item in spans(d) if item.get("evidence") is not None)
    print(f"Offsets OK: {n_spans} evidence spans in {len(drafts)} drafts")
    if args.check:
        return 0

    results = run_engine(drafts)
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(build_report(drafts, results) + "\n", encoding="utf-8")
    SAMPLES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SAMPLES_PATH.write_text(json.dumps(build_samples(drafts, results), indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    status_ok = sum(r["status_match"] for r in results)
    planted = [p for r in results for p in r["planted"]]
    print(f"Status agreement: {status_ok}/{len(results)}; planted detected: "
          f"{sum(p['detected'] for p in planted)}/{len(planted)}")
    print(f"Wrote {REPORT_PATH.relative_to(ROOT)}, {RESULTS_PATH.relative_to(ROOT)} "
          f"and {SAMPLES_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
