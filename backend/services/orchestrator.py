"""Analysis orchestrator (Task I.3): rules + RAG in parallel -> rewrite -> AnalyzeResponse.

Output shapes are binding: ``frontend/src/types/api.ts`` (``AnalyzeResponse``, ``RefineResponse``).

    analyze(request)  -> AnalyzeResponse dict
    refine(request)   -> RefineResponse dict

Data flow (SPEC "Data Flow")::

    ┌ WS2 RuleEngine.analyze_text + calculate_scores ┐
    │                                                ├─> rewrite (WS3 stand-in) ─> assemble
    └ WS1 RAGService.retrieve_for_text               ┘

Every offset in the response (issues and changes) is a **JS UTF-16** index into ``original``
(Python works in code points; emoji and other astral characters count as 2 in JS).
"""

from __future__ import annotations

import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any

from backend.logging_utils import get_logger
from backend.services import rewrite_service as rw

logger = get_logger(__name__)

RULESET_IDS = rw.RULESET_IDS
AUDIENCES: dict[str, str] = {"students": "Students", "faculty": "Faculty", "staff": "Staff"}
CHANNELS: dict[str, str] = {"email": "Email", "website": "Website", "social_media": "Social Media"}
STATUS_MAP: dict[str, str] = {
    "Approved": "Approved",
    "Minor Revisions": "Minor Revisions Needed",
    "Major Revisions": "Major Revisions Needed",
}

# Time budget for one /api/analyze (API Gateway HTTP API integrations time out at 30 s; the
# Lambda timeout is 29 s). Rules + RAG normally take < 2 s; the rest goes to the model.
REQUEST_BUDGET_S = 20.0  # leave headroom under Lambda/API Gateway's hard 29 s cut-off (Bedrock latency varies)
RAG_TIMEOUT_S = 5.0
RAG_TOP_K = 8
REFINE_GUIDELINES_TOP_K = 4
REFINE_HISTORY_MESSAGES = 8

URL_TITLES: dict[str, str] = {
    "name-and-boilerplate": "Name and boilerplate",
    "voice-and-tone": "Voice and tone",
    "brand-strategy": "Brand strategy",
    "editorial-and-style-guide": "Editorial and style guide",
}

_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="orchestrator")


class AnalysisUnavailableError(Exception):
    """A required backend (rule engine) could not serve the request -> HTTP 503."""


# --- normalization helpers ----------------------------------------------------------------


def normalize_audience(value: str) -> tuple[str, str]:
    """``'Students'`` / ``'students'`` -> ``('students', 'Students')``; raises ValueError."""
    key = (value or "").strip().lower()
    if key not in AUDIENCES:
        raise ValueError(f"audience must be one of {list(AUDIENCES.values())}, got {value!r}")
    return key, AUDIENCES[key]


def normalize_channel(value: str) -> tuple[str, str]:
    """``'Social Media'`` / ``'social_media'`` / ``'social media'`` -> ``('social_media', 'Social Media')``."""
    key = re.sub(r"[\s\-]+", "_", (value or "").strip().lower())
    if key not in CHANNELS:
        raise ValueError(f"channel must be one of {list(CHANNELS.values())}, got {value!r}")
    return key, CHANNELS[key]


def normalize_rulesets(values: list[str] | None) -> list[str]:
    if not values:
        return list(RULESET_IDS)
    out = []
    for v in values:
        if v not in RULESET_IDS:
            raise ValueError(f"unknown ruleset {v!r}; expected one of {list(RULESET_IDS)}")
        if v not in out:
            out.append(v)
    return out


def utf16_converter(text: str):
    """Map a Python code-point index to a JS UTF-16 index (mirror of ws2Adapter.codePointToUtf16)."""
    table = [0] * (len(text) + 1)
    u = 0
    for i, ch in enumerate(text):
        table[i] = u
        u += 2 if ord(ch) > 0xFFFF else 1
    table[len(text)] = u
    return lambda i: table[max(0, min(int(i), len(text)))]


def _num(x: float) -> float | int:
    return int(x) if float(x).is_integer() else round(float(x), 1)


def _to_dict(obj: Any) -> dict:
    if isinstance(obj, dict):
        return dict(obj)
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return dict(vars(obj))


def _title_for_url(url: str | None) -> str | None:
    if not url:
        return None
    for slug, title in URL_TITLES.items():
        if slug in url:
            return title
    return None


# --- dependencies (overridable in tests) ---------------------------------------------------


def _default_engine():
    from backend.services.rule_engine import get_engine
    return get_engine()


def _default_rag():
    from backend.services.rag_service import get_rag_service
    return get_rag_service()


_rule_sources: dict[int, dict[str, str]] = {}
_rule_sources_lock = threading.Lock()


def _rule_source_titles(engine: Any) -> dict[str, str]:
    """rule_id -> short guideline title from the rule's ``source`` (e.g. "UIC Editorial guide: Time")."""
    key = id(engine)
    with _rule_sources_lock:
        if key not in _rule_sources:
            titles: dict[str, str] = {}
            try:
                for rs in engine.rulesets.values():
                    for rule in rs.rules:
                        src = (getattr(rule, "source", "") or "").split(";")[0].strip()
                        if src:
                            titles[rule.rule_id] = src
            except Exception:  # noqa: BLE001 - titles are cosmetic
                pass
            _rule_sources[key] = titles
        return _rule_sources[key]


def map_issue(issue: Any, titles: dict[str, str]) -> dict:
    """WS2 Issue -> frontend Issue (code-point offsets; converted to UTF-16 later)."""
    g = issue if isinstance(issue, dict) else issue.model_dump(mode="json")
    sev = g["severity"].value if hasattr(g["severity"], "value") else g["severity"]
    url = g.get("guideline_url")
    return {
        "issue_id": g["issue_id"],
        "ruleset": g["ruleset_id"],
        "rule_id": g["rule_id"],
        "severity": sev,
        "message": g["message"],
        "start": g["start"],
        "end": g["end"],
        "excerpt": g["matched_text"],
        "suggestion": g.get("suggestion"),
        "guideline_url": url,
        "guideline_title": titles.get(g["rule_id"]) or _title_for_url(url),
        "scope": g.get("scope") or "span",
        "rule_name": g.get("rule_name"),
    }


# --- analyze ------------------------------------------------------------------------------


def _field(req: Any, name: str, default: Any = None) -> Any:
    if isinstance(req, dict):
        return req.get(name, default)
    return getattr(req, name, default)


def analyze(req: Any, *, instruction: str | None = None, engine: Any = None, rag: Any = None,
            rewriter: Any = None, started: float | None = None, budget_s: float = REQUEST_BUDGET_S) -> dict:
    """Run the full analysis for an AnalyzeRequest (pydantic model or dict).

    Raises ValueError for invalid input (-> 422) and AnalysisUnavailableError (-> 503) when the
    rule engine cannot load. RAG and Bedrock failures degrade gracefully (no guidelines /
    rule-based fallback changes).
    """
    t_start = started if started is not None else time.monotonic()
    t0 = time.perf_counter()
    text = _field(req, "text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must contain non-whitespace characters")
    aud_key, aud_title = normalize_audience(_field(req, "audience"))
    ch_key, ch_title = normalize_channel(_field(req, "channel"))
    rulesets = normalize_rulesets(_field(req, "rulesets"))

    if engine is None:
        try:
            engine = _default_engine()
        except Exception as exc:  # RulesetValidationError: rulesets missing/malformed
            raise AnalysisUnavailableError(f"rule engine unavailable: {exc}") from exc
    if rag is None:
        try:
            rag = _default_rag()
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAG service unavailable", extra={"event": "orchestrator_rag_init_error",
                                                             "error": str(exc)})
            rag = None
    rewriter = rewriter or rw.get_rewrite_service()

    # 1. rules + RAG in parallel
    rules_f = _pool.submit(engine.analyze_text, text, rulesets, aud_key, ch_key)
    rag_f = (_pool.submit(rag.retrieve_for_text, text, audience=aud_title, channel=ch_title,
                          rulesets=rulesets, top_k=RAG_TOP_K) if rag is not None else None)
    analysis = rules_f.result()  # ValueError subclasses propagate (-> 422)
    from backend.services.scoring_service import calculate_scores
    scores = calculate_scores(analysis)
    t_rules = time.perf_counter()

    guidelines: list[Any] = []
    if rag_f is not None:
        try:
            guidelines = list(rag_f.result(timeout=RAG_TIMEOUT_S))
        except FutureTimeout:
            logger.warning("RAG timed out; continuing without guidelines",
                           extra={"event": "orchestrator_rag_timeout"})
        except Exception as exc:  # noqa: BLE001 - RAG is enrichment, not required
            logger.warning("RAG failed; continuing without guidelines",
                           extra={"event": "orchestrator_rag_error", "error": str(exc)[:300]})
    t_rag = time.perf_counter()

    titles = _rule_source_titles(engine)
    issues = [map_issue(i, titles) for i in analysis.issues]

    # 2. rewrite (adaptive model, retries, fallback)
    result = rewriter.rewrite(text, issues, guidelines, aud_title, ch_title, rulesets,
                              instruction=instruction, deadline=t_start + budget_s)
    rewritten = rw.apply_changes(text, result.changes)

    # 3. assemble (UTF-16 offsets)
    conv = utf16_converter(text)
    out_issues = [{**i, "start": conv(i["start"]), "end": conv(i["end"])} for i in issues]
    out_changes = [{**c, "original_start": conv(c["original_start"]), "original_end": conv(c["original_end"])}
                   for c in result.changes]
    status = scores.status.value if hasattr(scores.status, "value") else str(scores.status)
    rl = analysis.reading_level
    latency_ms = round((time.perf_counter() - t0) * 1000)
    response = {
        "analysis_id": str(uuid.uuid4()),
        "original": text,
        "rewritten": rewritten,
        "changes": out_changes,
        "issues": out_issues,
        "scores": {
            "brand": scores.brand_score,
            "accessibility": scores.accessibility_score,
            "reading_level": {"grade": _num(rl.grade_level), "target": _num(rl.target_grade), "audience": aud_title},
            "total_issues": scores.total_issues,
            "status": STATUS_MAP.get(status, status),
        },
        "guidelines": [_to_dict(g) for g in guidelines],
        "audience": aud_title,
        "channel": ch_title,
        "rulesets": rulesets,
        "model_used": result.model_used,
        "latency_ms": latency_ms,
    }
    logger.info("analyze done", extra={
        "event": "analyze_done", "analysis_id": response["analysis_id"], "model": result.model_used,
        "fallback": result.fallback, "latency_ms": latency_ms,
        "rules_ms": round((t_rules - t0) * 1000), "rag_wait_ms": round((t_rag - t_rules) * 1000),
        "rewrite_ms": result.latency_ms, "issue_count": len(out_issues), "change_count": len(out_changes),
        "guideline_count": len(guidelines), "audience": aud_title, "channel": ch_title,
        "rulesets": rulesets, "words": len(text.split()), "instruction": bool(instruction)})
    return response


# --- refine (chat) ------------------------------------------------------------------------

RESPOND_TOOL = "respond"


def _respond_tool() -> dict:
    return {"toolSpec": {
        "name": RESPOND_TOOL,
        "description": "Reply to the author's chat message.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "intent": {"type": "string", "enum": ["answer", "rewrite"],
                           "description": "'answer' for a question / explanation request; 'rewrite' when "
                                          "the author asks to change the text (e.g. 'make it more formal', "
                                          "'shorter', 'fix the dates', 'don't change X')."},
                "reply": {"type": "string",
                          "description": "For 'answer': a brief answer (<= 120 words) that quotes the relevant "
                                         "UIC guideline on its own line as '> quote' followed by "
                                         "'Source: <url>'. For 'rewrite': one short sentence saying what "
                                         "you will change."},
                "instruction": {"type": "string",
                                "description": "For 'rewrite': the author's request restated as a precise "
                                               "editing instruction. Empty for 'answer'."},
            },
            "required": ["intent", "reply", "instruction"],
        }},
    }}


def _refine_system(audience: str, channel: str, rulesets: list[str], guidelines: list[Any]) -> str:
    blocks = "\n".join(
        f'<guideline title="{rw._guideline_title(c)}" url="{rw._g(c, "source_url")}">\n'
        f'{(rw._g(c, "text") or "")[:1500]}\n</guideline>' for c in guidelines) or "(none retrieved)"
    return f"""You are the UIC Editorial Assistant chat. You help University of Illinois Chicago (UIC) faculty \
and staff apply the official UIC brand, voice-and-tone and editorial style guidelines.

The author is writing for {audience} via {channel}; enabled checks: {', '.join(rulesets)}.

Decide what the author's latest message is:
- A question or a request for an explanation -> intent "answer". Answer briefly and concretely, grounded in the \
guideline excerpts below. Quote the most relevant guideline sentence on its own line as "> ..." followed by \
"Source: <url>". If the excerpts do not cover it, say so and give your best UIC-style advice without inventing \
a quote.
- A request to change the draft (tone, length, formality, wording, fix or keep something) -> intent "rewrite", \
with a precise editing instruction.

Never invent facts, names, dates or URLs.

UIC guideline excerpts:
{blocks}

Respond only by calling the {RESPOND_TOOL} tool."""


_QUESTION_START = re.compile(r"^\s*(how|what|why|when|where|which|who|can|could|should|is|are|do|does|"
                             r"may|explain|tell me)\b", re.I)


def _heuristic_intent(message: str) -> str:
    return "answer" if message.strip().endswith("?") or _QUESTION_START.match(message) else "rewrite"


def _heuristic_answer(guidelines: list[Any]) -> str:
    if not guidelines:
        return ("I couldn't reach the AI assistant just now. Please check the UIC brand guidelines at "
                "https://brand.uic.edu/messaging/ or try again.")
    c = guidelines[0]
    body = re.sub(r"^#.*\n+", "", (rw._g(c, "text") or "")).strip()
    sentence = re.split(r"(?<=[.!?])\s+", body)[0][:300] if body else ""
    return (f"Here is the most relevant UIC guideline I found ({rw._guideline_title(c)}):\n\n"
            f"> {sentence}\n\nSource: {rw._g(c, 'source_url')}")


def _describe_edits(original: str, rewritten: str, limit: int = 25) -> str:
    """Bullet list of phrase-level edits (original -> rewritten), for chat context."""
    import difflib
    a, b = original.split(), rewritten.split()
    out = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        before, after = " ".join(a[i1:i2])[:120], " ".join(b[j1:j2])[:120]
        out.append(f'- "{before}" -> "{after}"')
        if len(out) >= limit:
            break
    return "\n".join(out) or "(no edits)"


def refine(req: Any, *, engine: Any = None, rag: Any = None, rewriter: Any = None) -> dict:
    """Chat refinement (FR-11). Returns a RefineResponse dict ``{reply, analysis, guidelines}``."""
    t_start = time.monotonic()
    t0 = time.perf_counter()
    message = _field(req, "message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("message must contain non-whitespace characters")
    original = _field(req, "original")
    if original is None:
        original = ""
    if not isinstance(original, str):
        raise ValueError("original must be a string")
    has_draft = bool(original.strip())  # users may ask style questions before pasting a draft
    current_text = _field(req, "current_text") or original
    _, aud_title = normalize_audience(_field(req, "audience"))
    _, ch_title = normalize_channel(_field(req, "channel"))
    rulesets = normalize_rulesets(_field(req, "rulesets"))
    history = _field(req, "history") or []
    rewriter = rewriter or rw.get_rewrite_service()

    if rag is None:
        try:
            rag = _default_rag()
        except Exception:  # noqa: BLE001
            rag = None
    guidelines: list[Any] = []
    if rag is not None:
        try:
            # Bounded like analyze's RAG step: a slow Knowledge Base must not eat the request budget.
            guidelines = list(_pool.submit(rag.retrieve_guidelines, message[:1000], audience=aud_title,
                                           top_k=REFINE_GUIDELINES_TOP_K).result(timeout=RAG_TIMEOUT_S))
        except FutureTimeout:
            logger.warning("refine RAG timed out", extra={"event": "refine_rag_timeout"})
        except Exception as exc:  # noqa: BLE001
            logger.warning("refine RAG failed", extra={"event": "refine_rag_error", "error": str(exc)[:300]})

    transcript = []
    for m in list(history)[-REFINE_HISTORY_MESSAGES:]:
        role = _field(m, "role")
        content = _field(m, "content")
        if role in ("user", "assistant") and isinstance(content, str):
            transcript.append(f"{role}: {content[:1500]}")
    if not has_draft:
        draft_ctx = "<current_draft>(The user has not pasted a draft yet. Answer style questions only.)</current_draft>\n\n"
    elif current_text.strip() != original.strip():
        # Tell the model what it already changed, so "why did you change X?" can be answered.
        draft_ctx = (f"<original_draft>\n{original[:10000]}\n</original_draft>\n\n"
                     f"<your_suggested_rewrite>\n{current_text[:10000]}\n</your_suggested_rewrite>\n\n"
                     f"<edits_you_made>\n{_describe_edits(original, current_text)}\n</edits_you_made>\n\n")
    else:
        draft_ctx = f"<current_draft>\n{current_text[:20000]}\n</current_draft>\n\n"
    user = (draft_ctx
            + (f"<chat_history>\n" + "\n".join(transcript) + "\n</chat_history>\n\n" if transcript else "")
            + f"<message>{message}</message>")

    model_used = rewriter.model_fast if hasattr(rewriter, "model_fast") else "unknown"
    try:
        data, model_used, _ = rewriter.converse_tool(
            model_used, _refine_system(aud_title, ch_title, rulesets, guidelines), user, _respond_tool(),
            deadline=t_start + 8.0, max_tokens=1024)
        intent = data.get("intent") if data.get("intent") in ("answer", "rewrite") else _heuristic_intent(message)
        reply = str(data.get("reply") or "").strip()
        instruction = str(data.get("instruction") or "").strip() or message
    except Exception as exc:  # noqa: BLE001 - degrade to heuristics
        logger.warning("refine LLM failed; using heuristics", extra={"event": "refine_fallback",
                                                                      "error": str(exc)[:300]})
        intent = _heuristic_intent(message)
        reply = _heuristic_answer(guidelines) if intent == "answer" else ""
        instruction = message
        model_used = rw.FALLBACK_MODEL

    analysis = None
    if intent == "rewrite" and not has_draft:
        intent = "answer"
        reply = reply or "Paste your draft and click Analyze first, then I can rewrite it the way you'd like."
    if intent == "rewrite":
        analysis = analyze({"text": original, "audience": aud_title, "channel": ch_title, "rulesets": rulesets},
                           instruction=instruction, engine=engine, rag=rag, rewriter=rewriter,
                           started=t_start, budget_s=REQUEST_BUDGET_S)
        n = len(analysis["changes"])
        if analysis["model_used"] == rw.FALLBACK_MODEL:
            reply = ("I couldn't reach the AI editor just now, so I re-applied the rule-based fixes "
                     f"({n} change{'s' if n != 1 else ''}). Please try your request again in a moment.")
        else:
            reply = (reply or "Done.") + f" The updated rewrite has {n} suggested change{'s' if n != 1 else ''}."
    if not reply:
        reply = _heuristic_answer(guidelines)

    logger.info("refine done", extra={"event": "refine_done", "intent": intent, "model": model_used,
                                      "latency_ms": round((time.perf_counter() - t0) * 1000),
                                      "guideline_count": len(guidelines)})
    return {"reply": reply, "analysis": analysis, "guidelines": [_to_dict(g) for g in guidelines]}


__all__ = ["analyze", "refine", "AnalysisUnavailableError", "utf16_converter", "normalize_audience",
           "normalize_channel", "normalize_rulesets", "map_issue", "STATUS_MAP"]
