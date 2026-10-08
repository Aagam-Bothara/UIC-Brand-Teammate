"""Interim LLM rewrite service (stand-in for Workstream 3's ``llm_service.py``).

Turns a draft + rule-engine issues + retrieved UIC guideline excerpts into a list of
**layered edits** (frontend ``Change`` objects, see ``frontend/src/types/api.ts``) using Claude on
Amazon Bedrock (Converse API with a forced ``submit_edits`` tool, so the output is always JSON).

Pipeline::

    RewriteService.rewrite(text, issues, guidelines, audience, channel, rulesets, instruction)
      -> select_model()            Haiku for short/simple drafts, Sonnet otherwise (SPEC "Adaptive")
      -> converse (forced tool)    3 attempts, exponential backoff + jitter, overall time budget
      -> edits_to_changes()        locate each edit's `original` in the draft -> offsets
      -> RewriteResult             (falls back to deterministic rule suggestions if Bedrock fails)

All offsets produced here are **Python code-point** indexes into ``text``; the orchestrator
converts them to JS UTF-16 indexes for the frontend.

``issues`` are frontend-shaped issue dicts (``issue_id, ruleset, rule_id, rule_name, severity,
message, start, end, excerpt, scope, suggestion, guideline_url, guideline_title``) with code-point
offsets - the orchestrator builds them from WS2's ``AnalysisResult``. ``guidelines`` are WS1
``GuidelineChunk`` objects or dicts.

WS3 replacement: implement the same ``rewrite(...) -> RewriteResult`` signature (or wrap
``LLMService.rewrite_text``) and swap :func:`get_rewrite_service`; see docs/ANALYZE_API.md.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from backend.config import get_model_settings, get_settings
from backend.logging_utils import get_logger

logger = get_logger(__name__)

RULESET_IDS: tuple[str, ...] = ("brand", "accessibility", "content", "reading_level", "audience_tone")

RULESET_LABELS: dict[str, str] = {
    "brand": "Brand (official names, UIC terminology, boilerplate)",
    "accessibility": "Accessibility (descriptive links, plain language, inclusive/person-first wording, "
                     "no ALL CAPS, emoji/hashtag hygiene)",
    "content": "Content / editorial style (AP-based UIC editorial guide: dates, times, numbers, "
               "punctuation, word choice, filler)",
    "reading_level": "Reading level (shorter sentences, simpler words for the audience's target grade)",
    "audience_tone": "Audience & tone (UIC voice: confident, warm, direct, you-centered, inclusive; "
                     "suited to the audience and channel)",
}

# Guideline categories per ruleset (same mapping as WS1's RAGService.RULESET_CATEGORIES).
RULESET_CATEGORIES: dict[str, tuple[str, ...]] = {
    "brand": ("name", "editorial"),
    "accessibility": ("editorial",),
    "content": ("editorial", "audience"),
    "reading_level": ("tone", "audience"),
    "audience_tone": ("tone", "audience"),
}

AUDIENCE_GRADE: dict[str, int] = {"students": 8, "faculty": 10, "staff": 10}

CHANNEL_GUIDANCE: dict[str, str] = {
    "email": "Email: lead with the key point and the action, short paragraphs, descriptive link text "
             "(never 'click here'), a clear call to action.",
    "website": "Website: scannable, front-load key information, descriptive headings and link text, "
               "plain language.",
    "social media": "Social media: brief and conversational yet professional, at most one or two emoji, "
                    "CamelCase hashtags, no ALL CAPS shouting.",
}

# --- model selection / retry policy -------------------------------------------------------

FAST_MAX_WORDS = 300      # < 300 words ...
FAST_MAX_ISSUES = 8       # ... and < 8 issues -> fast model (Haiku); otherwise quality (Sonnet)
MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 0.5
BACKOFF_CAP_S = 4.0
DEFAULT_BUDGET_S = 18.0   # whole rewrite step; /api/analyze must stay well under 29 s (API Gateway)
MIN_ATTEMPT_S = 3.0       # don't start an attempt with less time than this left
CONNECT_TIMEOUT_S = 3
MAX_TOKENS_FAST = 4096
MAX_TOKENS_QUALITY = 6000

MAX_GUIDELINES_IN_PROMPT = 8
MAX_GUIDELINE_CHARS = 1200
MAX_ISSUES_IN_PROMPT = 80

RETRYABLE_CODES = frozenset({
    "ThrottlingException", "Throttling", "TooManyRequestsException", "ServiceUnavailableException",
    "ServiceUnavailable", "InternalServerException", "InternalServerError", "InternalFailure",
    "ModelNotReadyException", "ModelTimeoutException", "ModelErrorException", "RequestTimeout",
    "RequestTimeoutException", "ServiceQuotaExceededException",
    # botocore transport errors (exception class names)
    "ReadTimeoutError", "ConnectTimeoutError", "EndpointConnectionError", "ConnectionClosedError",
    "ResponseStreamingError",
})

TOOL_NAME = "submit_edits"

FALLBACK_MODEL = "rules-fallback"


class RewriteError(Exception):
    """The model call failed or returned unusable output."""


@dataclass
class RewriteResult:
    changes: list[dict]            # frontend Change dicts, code-point offsets into the draft
    model_used: str                # Bedrock model id, or "rules-fallback"
    summary: str = ""
    latency_ms: int = 0
    fallback: bool = False
    attempts: int = 0
    error: str | None = None
    dropped: dict[str, int] = field(default_factory=dict)


# --- helpers ------------------------------------------------------------------------------


def _g(obj: Any, key: str, default: Any = None) -> Any:
    """Field access for dicts and dataclass/pydantic objects alike."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _error_code(exc: BaseException) -> tuple[str, int | None]:
    resp = getattr(exc, "response", None)
    if isinstance(resp, dict):
        code = resp.get("Error", {}).get("Code", "") or type(exc).__name__
        return code, resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return type(exc).__name__, None


def is_retryable(exc: BaseException) -> bool:
    code, status = _error_code(exc)
    if code in RETRYABLE_CODES:
        return True
    return status is not None and status >= 500


def select_model(text: str, issues: list[dict], fast: str, quality: str) -> tuple[str, str]:
    """Adaptive model choice (SPEC): ``(model_id, reason)``."""
    words = len(text.split())
    n = len(issues)
    if words < FAST_MAX_WORDS and n < FAST_MAX_ISSUES:
        return fast, f"fast: {words} words < {FAST_MAX_WORDS} and {n} issues < {FAST_MAX_ISSUES}"
    return quality, f"quality: {words} words, {n} issues"


# --- locating edits in the draft ----------------------------------------------------------

_CHAR_NORMALIZE = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "`": "'",
    "“": '"', "”": '"', "„": '"', "″": '"',
    "–": "-", "—": "-", "‑": "-", " ": " ",
}


def _normalize_with_map(s: str) -> tuple[str, list[int]]:
    """Fold curly quotes/dashes and collapse whitespace runs to one space.

    Returns the normalized string and, for each of its characters, the index of the source
    character it came from.
    """
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(s):
        ch = _CHAR_NORMALIZE.get(ch, ch)
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(ch)
            idx.append(i)
            prev_space = False
    return "".join(out), idx


def _find_all(haystack: str, needle: str) -> list[int]:
    out, i = [], haystack.find(needle)
    while i != -1:
        out.append(i)
        i = haystack.find(needle, i + 1)
    return out


def find_candidates(text: str, needle: str) -> list[tuple[int, int]]:
    """All spans of ``needle`` in ``text``: exact matches, else whitespace/quote-normalized ones."""
    if not needle:
        return []
    exact = [(i, i + len(needle)) for i in _find_all(text, needle)]
    if exact:
        return exact
    norm_text, idx = _normalize_with_map(text)
    norm_needle, _ = _normalize_with_map(needle.strip())
    if not norm_needle.strip():
        return []
    spans = []
    for ns in _find_all(norm_text, norm_needle):
        ne = ns + len(norm_needle)
        spans.append((idx[ns], idx[ne - 1] + 1))
    if spans:
        return spans
    # Last resort: case-insensitive (the model sometimes re-capitalizes a sentence start).
    lower = norm_text.lower()
    return [(idx[ns], idx[ns + len(norm_needle) - 1] + 1) for ns in _find_all(lower, norm_needle.lower())]


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _guideline_title(chunk: Any) -> str:
    title = _g(chunk, "source_title") or ""
    section = _g(chunk, "section")
    return f"{title} — {section}" if section and section != title else title


def best_guideline_for(ruleset: str, guidelines: Iterable[Any]) -> Any | None:
    """Highest-scoring chunk in one of the ruleset's categories (else the best overall)."""
    chunks = [c for c in guidelines if _g(c, "source_url")]
    if not chunks:
        return None
    cats = RULESET_CATEGORIES.get(ruleset, ())
    preferred = [c for c in chunks if _g(c, "category") in cats]
    pool = preferred or chunks
    return max(pool, key=lambda c: float(_g(c, "score", 0) or 0))


def edits_to_changes(text: str, edits: list[dict], issues: list[dict], guidelines: list[Any],
                     rulesets: list[str]) -> tuple[list[dict], dict[str, int]]:
    """Map model edits to non-overlapping frontend ``Change`` dicts (code-point offsets).

    Returns ``(changes, dropped_counts)``. Edits whose ``original`` cannot be found, that overlap an
    earlier accepted edit, that change nothing, or whose ruleset is not requested are dropped.
    """
    by_id = {i["issue_id"]: i for i in issues}
    allowed = set(rulesets)
    used: list[tuple[int, int]] = []
    accepted: list[dict] = []
    dropped: dict[str, int] = {}

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for edit in edits:
        if not isinstance(edit, dict):
            drop("malformed")
            continue
        original = edit.get("original")
        replacement = edit.get("replacement")
        if not isinstance(original, str) or not isinstance(replacement, str) or not original.strip():
            drop("malformed")
            continue
        issue_ids = [i for i in (edit.get("issue_ids") or []) if isinstance(i, str) and i in by_id]
        ruleset = edit.get("ruleset")
        if ruleset not in allowed:
            linked = [by_id[i]["ruleset"] for i in issue_ids if by_id[i]["ruleset"] in allowed]
            if not linked:
                drop("ruleset")
                continue
            ruleset = linked[0]

        # Trim whitespace the model copied around the phrase (and the same padding on the replacement).
        lead = original[: len(original) - len(original.lstrip())]
        trail = original[len(original.rstrip()):]
        needle = original.strip()
        if lead and replacement.startswith(lead):
            replacement = replacement[len(lead):]
        if trail and replacement.endswith(trail):
            replacement = replacement[: len(replacement) - len(trail)]

        candidates = find_candidates(text, needle)
        if not candidates:
            drop("not_found")
            continue
        free = [c for c in candidates if not any(_overlaps(c, u) for u in used)]
        if not free:
            drop("overlap")
            continue
        ref_spans = [(by_id[i]["start"], by_id[i]["end"]) for i in issue_ids
                     if by_id[i].get("scope", "span") == "span"]
        preferred = [c for c in free if any(_overlaps(c, r) for r in ref_spans)]
        start, end = (preferred or free)[0]
        original_text = text[start:end]
        if replacement == original_text:
            drop("no_op")
            continue

        if not issue_ids:  # auto-link span issues of the same ruleset that this edit covers
            issue_ids = [i["issue_id"] for i in issues
                         if i["ruleset"] == ruleset and i.get("scope", "span") == "span"
                         and _overlaps((start, end), (i["start"], i["end"]))]

        url = title = None
        for iid in issue_ids:
            if by_id[iid].get("guideline_url"):
                url, title = by_id[iid]["guideline_url"], by_id[iid].get("guideline_title")
                break
        if not url:
            chunk = best_guideline_for(ruleset, guidelines)
            if chunk is not None:
                url, title = _g(chunk, "source_url"), _guideline_title(chunk)

        explanation = edit.get("explanation") if isinstance(edit.get("explanation"), str) else ""
        if not explanation.strip() and issue_ids:
            explanation = by_id[issue_ids[0]].get("message") or ""
        used.append((start, end))
        accepted.append({
            "ruleset": ruleset,
            "original_start": start,
            "original_end": end,
            "original_text": original_text,
            "rewritten_text": replacement,
            "explanation": explanation.strip(),
            "issue_ids": issue_ids,
            "guideline_url": url,
            "guideline_title": title or None,
        })

    accepted.sort(key=lambda c: (c["original_start"], c["original_end"]))
    for n, ch in enumerate(accepted, start=1):
        ch["change_id"] = f"chg-{n}"
    return [_order_change(c) for c in accepted], dropped


_CHANGE_KEYS = ("change_id", "ruleset", "original_start", "original_end", "original_text",
                "rewritten_text", "explanation", "issue_ids", "guideline_url", "guideline_title")


def _order_change(c: dict) -> dict:
    return {k: c.get(k) for k in _CHANGE_KEYS}


def apply_changes(text: str, changes: list[dict]) -> str:
    """Apply non-overlapping changes (code-point offsets) to ``text``."""
    out, pos = [], 0
    for c in sorted(changes, key=lambda c: c["original_start"]):
        out.append(text[pos:c["original_start"]])
        out.append(c["rewritten_text"])
        pos = c["original_end"]
    out.append(text[pos:])
    return "".join(out)


# --- deterministic fallback ---------------------------------------------------------------

_INSTRUCTION_VERBS = frozenset("""
Add Avoid Break Capitalize Change Check Consider Define Delete Describe Include Keep Limit Make Move
Name Provide Refer Reframe Remove Rephrase Replace Reword Rewrite Shorten Simplify Spell Split Try Use
Write
""".split())


def is_literal_suggestion(suggestion: str | None) -> bool:
    """True when a WS2 suggestion is replacement text (not an instruction like "Describe ...")."""
    if not suggestion or not suggestion.strip():
        return False
    s = suggestion.strip()
    if s.startswith("(") or " / " in s or "+" in s or "e.g." in s or "\\" in s:
        return False
    first = s.split()[0]
    if first in _INSTRUCTION_VERBS and len(s.split()) > 1:
        return False
    return True


def fallback_changes(text: str, issues: list[dict], rulesets: list[str]) -> list[dict]:
    """Deterministic changes from rule-engine suggestions that are literal replacement text."""
    allowed = set(rulesets)
    sev = {"high": 0, "medium": 1, "low": 2}
    cands = sorted((i for i in issues if i.get("scope", "span") == "span" and i["ruleset"] in allowed
                    and i["end"] > i["start"] and is_literal_suggestion(i.get("suggestion"))),
                   key=lambda i: (i["start"], sev.get(i.get("severity"), 3)))
    used: list[tuple[int, int]] = []
    changes: list[dict] = []
    for i in cands:
        span = (i["start"], i["end"])
        if any(_overlaps(span, u) for u in used):
            continue
        original = text[i["start"]:i["end"]]
        repl = i["suggestion"]
        if original[:1].isupper() and repl[:1].islower():
            repl = repl[0].upper() + repl[1:]
        if repl == original:
            continue
        used.append(span)
        changes.append({
            "ruleset": i["ruleset"], "original_start": i["start"], "original_end": i["end"],
            "original_text": original, "rewritten_text": repl,
            "explanation": i.get("message") or "", "issue_ids": [i["issue_id"]],
            "guideline_url": i.get("guideline_url"), "guideline_title": i.get("guideline_title"),
        })
    for n, ch in enumerate(changes, start=1):
        ch["change_id"] = f"chg-{n}"
    return [_order_change(c) for c in changes]


def gap_fill(text: str, changes: list[dict], issues: list[dict], rulesets: list[str],
             skipped: Iterable[str] = ()) -> tuple[list[dict], int]:
    """Add deterministic fixes for literal-suggestion issues the model neither fixed nor skipped.

    Only issues that no model change covers (by id or by span) and that do not overlap a model
    change are filled. Returns ``(changes renumbered in document order, number added)``.
    """
    covered = {iid for c in changes for iid in c["issue_ids"]} | set(skipped)
    spans = [(c["original_start"], c["original_end"]) for c in changes]
    todo = [i for i in issues if i["issue_id"] not in covered
            and not any(_overlaps((i["start"], i["end"]), sp) for sp in spans)]
    extra = fallback_changes(text, todo, rulesets)
    for c in extra:
        c["explanation"] = c["explanation"] or "Rule-based fix."
    merged = sorted(changes + extra, key=lambda c: (c["original_start"], c["original_end"]))
    for n, ch in enumerate(merged, start=1):
        ch["change_id"] = f"chg-{n}"
    return merged, len(extra)


# --- prompt -------------------------------------------------------------------------------


def tool_spec(rulesets: list[str]) -> dict:
    return {"toolSpec": {
        "name": TOOL_NAME,
        "description": "Submit the list of surgical edits to the draft.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "edits": {
                    "type": "array",
                    "description": "Non-overlapping edits, in document order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ruleset": {"type": "string", "enum": list(rulesets),
                                        "description": "The single best ruleset this edit belongs to."},
                            "original": {"type": "string",
                                         "description": "EXACT substring copied character-for-character "
                                                        "from the draft (a phrase or one sentence). Must be "
                                                        "long enough to be unambiguous."},
                            "replacement": {"type": "string",
                                            "description": "Text that replaces `original` (may be empty to delete)."},
                            "explanation": {"type": "string",
                                            "description": "1-2 plain-English sentences: why, citing the UIC "
                                                           "guideline when relevant."},
                            "issue_ids": {"type": "array", "items": {"type": "string"},
                                          "description": "ids of the provided issues this edit fixes (may be empty)."},
                        },
                        "required": ["ruleset", "original", "replacement", "explanation", "issue_ids"],
                    },
                },
                "skipped_issue_ids": {"type": "array", "items": {"type": "string"},
                                      "description": "ids of provided issues deliberately left unchanged "
                                                     "(false positives in context)."},
                "summary": {"type": "string", "description": "One sentence summarizing the edits."},
            },
            "required": ["edits", "summary"],
        }},
    }}


def build_system_prompt(audience: str, channel: str, rulesets: list[str], guidelines: list[Any]) -> str:
    grade = AUDIENCE_GRADE.get(audience.lower(), 10)
    rs_lines = "\n".join(f"- {r}: {RULESET_LABELS.get(r, r)}" for r in rulesets)
    excerpts = []
    for c in list(guidelines)[:MAX_GUIDELINES_IN_PROMPT]:
        body = (_g(c, "text") or "")[:MAX_GUIDELINE_CHARS]
        excerpts.append(f'<guideline title="{_guideline_title(c)}" url="{_g(c, "source_url")}">\n{body}\n</guideline>')
    guideline_block = "\n".join(excerpts) or "(no excerpts retrieved; rely on the issues list)"
    return f"""You are the UIC Editorial Assistant, an expert editor for the University of Illinois Chicago (UIC). \
You apply the official UIC brand, voice-and-tone and editorial style guidelines to communications written by \
faculty and staff.

Your job: propose minimal, surgical edits to the draft so it complies with the UIC guidelines and suits its \
audience and channel.

Audience: {audience} (target reading level: grade {grade} or lower).
Channel: {channel}. {CHANNEL_GUIDANCE.get(channel.lower(), '')}

Enabled rulesets (tag every edit with exactly one of these; ignore problems outside them):
{rs_lines}

Rules for edits:
1. Fix every provided rule-engine issue that belongs to an enabled ruleset when a sensible fix exists \
(reference it in issue_ids). Document-level issues (e.g. reading level, length) are fixed by simplifying or \
splitting the specific sentences that cause them.
2. Also fix other clear guideline problems you notice (tone, inclusive language, clarity) - but only real problems.
3. Edits are word-, phrase- or sentence-level. NEVER rewrite the whole document or a whole paragraph at once. \
Each `original` must be an EXACT, verbatim substring of the draft (same spelling, punctuation, capitalization \
and spacing) and edits must not overlap. Use the shortest `original` that makes the fix unambiguous \
(e.g. "March 5th" -> "March 5", not the whole sentence).
4. Prefer one small edit per issue so the author can accept each fix separately; only combine fixes when they \
touch the same words. Fix a too-long sentence with a minimal split at a natural break (e.g. replace \
" and it's" with ". It's"), never by retyping the whole sentence, so the other word-level fixes in it still apply.
5. If a provided issue is a false positive in context (e.g. a capitalized word that is part of a proper name), \
do not edit it; list its id in skipped_issue_ids.
6. Every edit must stand on its own (the author may accept any subset): never move content from one place \
to another and never drop facts (cutting filler words is fine) unless the author asks. Do not add new sentences or claims that are not in the draft.
7. Keep the meaning. Never invent facts, names, dates, times, places, numbers, URLs or email addresses. If a \
fix would need missing information (e.g. a link destination), rephrase around it instead of making it up.
8. Keep the author's voice; adapt tone and reading level for the audience and channel.
9. Explanations: 1-2 short plain-English sentences, citing the UIC guideline (by name) when relevant.

UIC guideline excerpts (retrieved for this draft):
{guideline_block}

Respond only by calling the {TOOL_NAME} tool."""


def build_user_prompt(text: str, issues: list[dict], instruction: str | None) -> str:
    rows = []
    for i in issues[:MAX_ISSUES_IN_PROMPT]:
        row = {"issue_id": i["issue_id"], "ruleset": i["ruleset"], "rule": i.get("rule_name") or i.get("rule_id"),
               "severity": i.get("severity"), "message": i.get("message"), "scope": i.get("scope", "span")}
        if i.get("scope", "span") == "span":
            row["text"] = i.get("excerpt")
        if i.get("suggestion"):
            row["suggestion"] = i["suggestion"]
        rows.append(row)
    parts = [f"<draft>\n{text}\n</draft>",
             "Rule-engine issues found in the draft (JSON):\n" + json.dumps(rows, ensure_ascii=False)]
    if instruction:
        parts.append("Additional request from the author (apply it throughout, still as surgical edits, "
                     f"and tag each edit with the best ruleset):\n<request>{instruction}</request>")
    parts.append(f"Call {TOOL_NAME} with your edits.")
    return "\n\n".join(parts)


def parse_tool_output(response: dict) -> dict:
    """Extract the ``submit_edits`` tool input from a Converse response."""
    content = (((response or {}).get("output") or {}).get("message") or {}).get("content") or []
    for block in content:
        tu = block.get("toolUse") if isinstance(block, dict) else None
        if tu and tu.get("name") == TOOL_NAME:
            data = tu.get("input")
            if isinstance(data, str):  # defensive: some SDKs hand back a JSON string
                data = json.loads(data)
            if not isinstance(data, dict) or not isinstance(data.get("edits"), list):
                raise RewriteError("submit_edits input has no edits list")
            return data
    raise RewriteError(f"model did not call {TOOL_NAME} (stopReason={response.get('stopReason')})")


# --- service ------------------------------------------------------------------------------


class RewriteService:
    """Bedrock-backed rewrite with adaptive model choice, retries and a deterministic fallback."""

    def __init__(self, client: Any = None, *, model_fast: str | None = None, model_quality: str | None = None,
                 region: str | None = None, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._client_override = client
        self._model_fast = model_fast
        self._model_quality = model_quality
        self._region = region
        self._sleep = sleep
        self._clock = clock
        self._clients: dict[int, Any] = {}
        self._lock = threading.Lock()

    @property
    def model_fast(self) -> str:
        return self._model_fast or get_model_settings().fast

    @property
    def model_quality(self) -> str:
        return self._model_quality or get_model_settings().quality

    def _client(self, read_timeout: float) -> Any:
        if self._client_override is not None:
            return self._client_override
        key = max(5, int(read_timeout))
        with self._lock:
            if key not in self._clients:
                import boto3
                from botocore.config import Config

                self._clients[key] = boto3.client(
                    "bedrock-runtime", region_name=self._region or get_settings().aws_region,
                    config=Config(connect_timeout=CONNECT_TIMEOUT_S, read_timeout=key,
                                  retries={"max_attempts": 1, "mode": "standard"}))
            return self._clients[key]

    # -- model call ------------------------------------------------------------------------

    def converse_tool(self, model: str, system: str, user: str, tool: dict, deadline: float,
                      max_tokens: int) -> tuple[dict, str, int]:
        """Forced-tool Converse call with retries. Returns ``(tool_input, model_used, attempts)``.

        Retries throttling / 5xx / timeouts with exponential backoff + jitter while time remains
        before ``deadline``. A failure on the quality model switches later attempts to the fast
        model (faster, separate quota). Raises :class:`RewriteError` when every attempt fails.
        """
        tool_name = tool["toolSpec"]["name"]
        last: BaseException | None = None
        attempt = 0
        current = model
        while attempt < MAX_ATTEMPTS:
            remaining = deadline - self._clock()
            if remaining < MIN_ATTEMPT_S:
                break
            attempt += 1
            t0 = time.perf_counter()
            try:
                resp = self._client(remaining).converse(
                    modelId=current,
                    system=[{"text": system}],
                    messages=[{"role": "user", "content": [{"text": user}]}],
                    inferenceConfig={"maxTokens": max_tokens},
                    toolConfig={"tools": [tool], "toolChoice": {"tool": {"name": tool_name}}},
                )
                data = _tool_input(resp, tool_name)
                usage = resp.get("usage") or {}
                logger.info("bedrock converse ok", extra={
                    "event": "llm_converse", "model": current, "attempt": attempt, "tool": tool_name,
                    "latency_ms": round((time.perf_counter() - t0) * 1000), "stop_reason": resp.get("stopReason"),
                    "input_tokens": usage.get("inputTokens"), "output_tokens": usage.get("outputTokens")})
                return data, current, attempt
            except Exception as exc:  # noqa: BLE001 - classified below
                last = exc
                code, status = _error_code(exc)
                retryable = is_retryable(exc) or isinstance(exc, RewriteError)
                logger.warning("bedrock converse failed", extra={
                    "event": "llm_converse_error", "model": current, "attempt": attempt, "tool": tool_name,
                    "error": code, "status": status, "retryable": retryable,
                    "latency_ms": round((time.perf_counter() - t0) * 1000), "detail": str(exc)[:300]})
                switched = current != self.model_fast
                if switched:
                    current = self.model_fast  # quality model failed: fall back to the fast one
                if not retryable and not switched:
                    break
                if attempt < MAX_ATTEMPTS and retryable:
                    delay = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2 ** (attempt - 1)))
                    delay = delay / 2 + random.uniform(0, delay / 2)
                    if deadline - self._clock() - delay >= MIN_ATTEMPT_S:
                        self._sleep(delay)
        raise RewriteError(f"Bedrock call failed after {attempt} attempt(s): "
                           f"{_error_code(last)[0] if last else 'time budget exhausted'}")

    # -- public API ------------------------------------------------------------------------

    def rewrite(self, text: str, issues: list[dict], guidelines: list[Any], audience: str, channel: str,
                rulesets: list[str], instruction: str | None = None, deadline: float | None = None,
                ) -> RewriteResult:
        t0 = time.perf_counter()
        deadline = deadline if deadline is not None else self._clock() + DEFAULT_BUDGET_S
        rs = [r for r in rulesets if r in RULESET_IDS] or list(RULESET_IDS)
        relevant = [i for i in issues if i["ruleset"] in rs]
        model, reason = select_model(text, relevant, self.model_fast, self.model_quality)
        max_tokens = MAX_TOKENS_FAST if model == self.model_fast else MAX_TOKENS_QUALITY
        logger.info("rewrite model selected", extra={"event": "rewrite_model_selected", "model": model,
                                                     "reason": reason, "instruction": bool(instruction)})
        try:
            data, used, attempts = self.converse_tool(
                model, build_system_prompt(audience, channel, rs, guidelines),
                build_user_prompt(text, relevant, instruction), tool_spec(rs), deadline, max_tokens)
            changes, dropped = edits_to_changes(text, data.get("edits") or [], relevant, guidelines, rs)
            skipped = [i for i in (data.get("skipped_issue_ids") or []) if isinstance(i, str)]
            changes, filled = gap_fill(text, changes, relevant, rs, skipped)
            if filled:
                dropped["gap_filled"] = filled
            result = RewriteResult(changes=changes, model_used=used, summary=str(data.get("summary") or ""),
                                   attempts=attempts, dropped=dropped)
        except Exception as exc:  # noqa: BLE001 - any failure -> deterministic fallback
            logger.error("rewrite failed; using rule-based fallback",
                         extra={"event": "rewrite_fallback", "error": str(exc)[:300]})
            changes = fallback_changes(text, relevant, rs)
            result = RewriteResult(changes=changes, model_used=FALLBACK_MODEL, fallback=True, error=str(exc),
                                   summary=f"Applied {len(changes)} rule-based fixes (AI rewrite unavailable).")
        result.latency_ms = round((time.perf_counter() - t0) * 1000)
        per_ruleset: dict[str, int] = {}
        for c in result.changes:
            per_ruleset[c["ruleset"]] = per_ruleset.get(c["ruleset"], 0) + 1
        logger.info("rewrite done", extra={
            "event": "rewrite_done", "model": result.model_used, "fallback": result.fallback,
            "latency_ms": result.latency_ms, "change_count": len(result.changes), "per_ruleset": per_ruleset,
            "dropped": result.dropped, "words": len(text.split()), "issue_count": len(relevant)})
        return result


def _tool_input(resp: dict, tool_name: str) -> dict:
    if tool_name == TOOL_NAME:
        return parse_tool_output(resp)
    content = (((resp or {}).get("output") or {}).get("message") or {}).get("content") or []
    for block in content:
        tu = block.get("toolUse") if isinstance(block, dict) else None
        if tu and tu.get("name") == tool_name and isinstance(tu.get("input"), dict):
            return tu["input"]
    raise RewriteError(f"model did not call {tool_name} (stopReason={resp.get('stopReason')})")


_service: RewriteService | None = None
_service_lock = threading.Lock()


def get_rewrite_service() -> RewriteService:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = RewriteService()
    return _service


def reset_rewrite_service() -> None:
    global _service
    with _service_lock:
        _service = None
