"""Tests for backend/services/orchestrator.py (real WS2 rule engine, fake RAG + fake Bedrock)."""

from __future__ import annotations

import threading
import time

import pytest

from backend.services import orchestrator as o
from backend.services import rewrite_service as rw
from backend.services.rule_engine import RuleEngine
from tests.unit.test_rewrite_service import FakeClient, chunk, client_error, tool_response

ALL = list(rw.RULESET_IDS)
SAMPLE = ("Hey guys!\n\nThe University of Illinois at Chicago Career Services office will host the Fall Career "
          "Fair on March 5th from 12pm to 4pm in the Student Center East. In order to prepare, students should "
          "utilize the resume review sessions prior to the event. Over 100 employers will be there and it's "
          "going to be AMAZING!!\n\nClick here to register ASAP. For more info, email careers@uic.edu.")

# Field sets of frontend/src/types/api.ts
ANALYZE_KEYS = {"analysis_id", "original", "rewritten", "changes", "issues", "scores", "guidelines", "audience",
                "channel", "rulesets", "model_used", "latency_ms"}
CHANGE_KEYS = {"change_id", "ruleset", "original_start", "original_end", "original_text", "rewritten_text",
               "explanation", "issue_ids", "guideline_url", "guideline_title"}
ISSUE_KEYS = {"issue_id", "ruleset", "rule_id", "severity", "message", "start", "end", "excerpt", "suggestion",
              "guideline_url", "guideline_title", "scope", "rule_name"}
SCORES_KEYS = {"brand", "accessibility", "reading_level", "total_issues", "status"}
CHUNK_KEYS = {"chunk_id", "text", "score", "source_id", "source_title", "source_url", "category", "section"}


@pytest.fixture(scope="module")
def engine():
    return RuleEngine()


class FakeRAG:
    def __init__(self, chunks=None, delay=0.0, error=None):
        self.chunks = chunks if chunks is not None else [chunk()]
        self.delay, self.error = delay, error
        self.calls = []
        self.threads = set()

    def retrieve_for_text(self, text, audience=None, channel=None, rulesets=None, top_k=8):
        self.calls.append(("retrieve_for_text", audience, channel, rulesets))
        self.threads.add(threading.get_ident())
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.chunks

    def retrieve_guidelines(self, query, audience=None, top_k=5):
        self.calls.append(("retrieve_guidelines", query, audience))
        return self.chunks


def js_slice(s: str, start: int, end: int) -> str:
    """JS String.prototype.slice semantics (UTF-16 code units)."""
    b = s.encode("utf-16-le")
    return b[start * 2:end * 2].decode("utf-16-le")


def sample_edits():
    return [
        {"ruleset": "audience_tone", "original": "Hey guys!", "replacement": "Hi everyone!",
         "explanation": "Inclusive greeting.", "issue_ids": ["tone-002-1"]},
        {"ruleset": "brand", "original": "University of Illinois at Chicago",
         "replacement": "University of Illinois Chicago", "explanation": "Official name.", "issue_ids": []},
        {"ruleset": "content", "original": "March 5th", "replacement": "March 5", "explanation": "Dates.",
         "issue_ids": []},
        {"ruleset": "accessibility", "original": "Click here to register ASAP.",
         "replacement": "Register for the career fair.", "explanation": "Descriptive links.", "issue_ids": []},
        {"ruleset": "reading_level", "original": "utilize", "replacement": "use", "explanation": "Simpler.",
         "issue_ids": []},
    ]


def run(engine, text=SAMPLE, edits=None, rag=None, client=None, **req):
    client = client or FakeClient(tool_response(sample_edits() if edits is None else edits))
    svc = rw.RewriteService(client, model_fast="fast-model", model_quality="quality-model", sleep=lambda s: None)
    body = {"text": text, "audience": "Students", "channel": "Email", "rulesets": ALL, **req}
    return o.analyze(body, engine=engine, rag=rag or FakeRAG(), rewriter=svc), client


def test_response_shape_matches_ts_contract(engine):
    r, client = run(engine)
    assert set(r) == ANALYZE_KEYS
    assert r["original"] == SAMPLE and r["audience"] == "Students" and r["channel"] == "Email"
    assert r["rulesets"] == ALL and r["model_used"] == "quality-model"  # 14 issues -> quality
    assert isinstance(r["latency_ms"], int) and len(r["analysis_id"]) == 36
    assert r["changes"] and all(set(c) == CHANGE_KEYS for c in r["changes"])
    assert r["issues"] and all(set(i) == ISSUE_KEYS for i in r["issues"])
    assert all(set(g) == CHUNK_KEYS for g in r["guidelines"])
    s = r["scores"]
    assert set(s) == SCORES_KEYS and set(s["reading_level"]) == {"grade", "target", "audience"}
    assert s["reading_level"]["target"] == 8 and s["reading_level"]["audience"] == "Students"
    assert s["status"] in {"Approved", "Minor Revisions Needed", "Major Revisions Needed"}
    assert {c["ruleset"] for c in r["changes"]} == set(ALL)
    for i in r["issues"]:
        assert i["ruleset"] in ALL and i["severity"] in {"high", "medium", "low"} and i["scope"] in {"span", "document"}
    # issue mapping like ws2Adapter: excerpt = matched_text, guideline title from rule source
    brand = next(i for i in r["issues"] if i["rule_id"] == "brand-001")
    assert brand["excerpt"] == "University of Illinois at Chicago" and brand["guideline_title"]
    # changes apply cleanly and `rewritten` = all applied
    for c in r["changes"]:
        assert js_slice(SAMPLE, c["original_start"], c["original_end"]) == c["original_text"]
    assert "University of Illinois Chicago" in r["rewritten"] and "Hi everyone!" in r["rewritten"]
    assert "March 5 " in r["rewritten"] and "4 p.m." in r["rewritten"]  # gap-filled from rules
    # issues linked to changes exist
    ids = {i["issue_id"] for i in r["issues"]}
    assert all(iid in ids for c in r["changes"] for iid in c["issue_ids"])


def test_utf16_offsets_with_emoji(engine):
    text = "🎉🎉 Hey guys! Join us at the University of Illinois at Chicago 😀 on March 5th."
    r, _ = run(engine, text=text)
    assert r["changes"] and r["issues"]
    for c in r["changes"]:
        assert js_slice(text, c["original_start"], c["original_end"]) == c["original_text"]
    for i in r["issues"]:
        if i["scope"] == "span":
            assert js_slice(text, i["start"], i["end"]) == i["excerpt"]
    brand = next(c for c in r["changes"] if c["ruleset"] == "brand")
    assert brand["original_start"] == text.index("University") + 2  # two emoji before it, 2 units each


def test_utf16_converter():
    conv = o.utf16_converter("a😀b")
    assert [conv(i) for i in range(4)] == [0, 1, 3, 4]
    assert conv(99) == 4


@pytest.mark.parametrize("status,expected", [("Approved", "Approved"),
                                             ("Minor Revisions", "Minor Revisions Needed"),
                                             ("Major Revisions", "Major Revisions Needed")])
def test_status_mapping(status, expected):
    assert o.STATUS_MAP[status] == expected


def test_clean_text_is_approved(engine):
    r, _ = run(engine, text="Students can meet advisers in the library on Monday.", edits=[])
    assert r["scores"]["status"] == "Approved" and r["changes"] == [] and r["rewritten"] == r["original"]
    assert r["model_used"] == "fast-model"


def test_title_and_lowercase_inputs_and_ruleset_subset(engine):
    rag = FakeRAG()
    r, client = run(engine, rag=rag, audience="faculty", channel="social_media", rulesets=["brand"])
    assert r["audience"] == "Faculty" and r["channel"] == "Social Media" and r["rulesets"] == ["brand"]
    assert {i["ruleset"] for i in r["issues"]} == {"brand"}
    assert {c["ruleset"] for c in r["changes"]} == {"brand"}
    assert rag.calls[0] == ("retrieve_for_text", "Faculty", "Social Media", ["brand"])
    assert r["scores"]["reading_level"]["target"] == 10


@pytest.mark.parametrize("field,value", [("audience", "Alumni"), ("channel", "Fax"), ("rulesets", ["nope"]),
                                         ("text", "   ")])
def test_invalid_input_raises_value_error(engine, field, value):
    with pytest.raises(ValueError):
        run(engine, **{field: value})


def test_rules_and_rag_run_in_parallel(engine, monkeypatch):
    class SlowEngine:
        rulesets = engine.rulesets

        def analyze_text(self, *a):
            time.sleep(0.3)
            return engine.analyze_text(*a)

    rag = FakeRAG(delay=0.3)
    t0 = time.perf_counter()
    r, _ = run(SlowEngine(), rag=rag)
    assert time.perf_counter() - t0 < 0.55
    assert rag.threads and threading.get_ident() not in rag.threads
    assert r["guidelines"]


def test_rag_failure_degrades_to_no_guidelines(engine):
    r, _ = run(engine, rag=FakeRAG(error=RuntimeError("kb down")))
    assert r["guidelines"] == [] and r["changes"]


def test_bedrock_failure_returns_rules_fallback(engine):
    client = FakeClient(client_error("AccessDeniedException", 403), client_error("AccessDeniedException", 403))
    r, _ = run(engine, client=client)
    assert r["model_used"] == "rules-fallback"
    got = {(c["original_text"], c["rewritten_text"]) for c in r["changes"]}
    assert ("University of Illinois at Chicago", "University of Illinois Chicago") in got
    assert ("utilize", "use") in got and ("12pm", "noon") in got
    for c in r["changes"]:
        assert js_slice(SAMPLE, c["original_start"], c["original_end"]) == c["original_text"]


# --------------------------------------------------------------------------- refine

def respond(intent, reply, instruction=""):
    return tool_response([], name=o.RESPOND_TOOL) | {"output": {"message": {"content": [
        {"toolUse": {"toolUseId": "r", "name": o.RESPOND_TOOL,
                     "input": {"intent": intent, "reply": reply, "instruction": instruction}}}]}}}


def refine_req(message, **kw):
    return {"message": message, "original": SAMPLE, "current_text": SAMPLE, "audience": "Students",
            "channel": "Email", "rulesets": ALL, "history": [{"role": "user", "content": "hi"},
                                                            {"role": "assistant", "content": "hello"}], **kw}


def test_refine_question_answers_with_guidelines(engine):
    client = FakeClient(respond("answer", "Use the full name.\n\n> University of Illinois Chicago\n\nSource: x"))
    svc = rw.RewriteService(client, model_fast="fast-model", model_quality="quality-model", sleep=lambda s: None)
    rag = FakeRAG()
    r = o.refine(refine_req("How do I write the university's name?"), engine=engine, rag=rag, rewriter=svc)
    assert set(r) == {"reply", "analysis", "guidelines"}
    assert r["analysis"] is None and r["reply"].startswith("Use the full name")
    assert r["guidelines"] and set(r["guidelines"][0]) == CHUNK_KEYS
    assert rag.calls[0] == ("retrieve_guidelines", "How do I write the university's name?", "Students")
    call = client.calls[0]
    assert call["modelId"] == "fast-model"
    assert "assistant: hello" in call["messages"][0]["content"][0]["text"]


def test_refine_rewrite_reruns_analysis_with_instruction(engine):
    client = FakeClient(respond("rewrite", "I'll make it more formal.", "Use a formal tone."),
                        tool_response(sample_edits()))
    svc = rw.RewriteService(client, model_fast="fast-model", model_quality="quality-model", sleep=lambda s: None)
    r = o.refine(refine_req("Make it more formal"), engine=engine, rag=FakeRAG(), rewriter=svc)
    assert r["analysis"] and set(r["analysis"]) == ANALYZE_KEYS and r["analysis"]["original"] == SAMPLE
    assert "Use a formal tone." in client.calls[1]["messages"][0]["content"][0]["text"]
    assert "suggested change" in r["reply"]


def test_refine_llm_failure_uses_heuristics(engine):
    client = FakeClient(*[client_error("AccessDeniedException", 403)] * 6)
    svc = rw.RewriteService(client, model_fast="fast-model", model_quality="quality-model", sleep=lambda s: None)
    r = o.refine(refine_req("How do I write the name?"), engine=engine, rag=FakeRAG(), rewriter=svc)
    assert r["analysis"] is None and "Source: https://brand.uic.edu" in r["reply"]
    r = o.refine(refine_req("Make it shorter"), engine=engine, rag=FakeRAG(), rewriter=svc)
    assert r["analysis"]["model_used"] == "rules-fallback"
