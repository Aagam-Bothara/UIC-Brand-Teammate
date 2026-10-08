"""Tests for backend/services/rewrite_service.py (no real AWS: fake Bedrock clients + botocore Stubber)."""

from __future__ import annotations

import boto3
import pytest
from botocore.exceptions import ClientError, ReadTimeoutError
from botocore.stub import Stubber

from backend.services import rewrite_service as rw

FAST, QUALITY = "fast-model", "quality-model"
ALL = list(rw.RULESET_IDS)


def issue(iid, ruleset, start, end, text, suggestion=None, scope="span", severity="medium", url=None,
          title=None):
    return {"issue_id": iid, "ruleset": ruleset, "rule_id": iid.rsplit("-", 1)[0], "severity": severity,
            "message": f"msg {iid}", "start": start, "end": end, "excerpt": text[start:end],
            "suggestion": suggestion, "guideline_url": url, "guideline_title": title, "scope": scope,
            "rule_name": "Rule"}


def chunk(cid="c1", category="name", score=0.5, url="https://brand.uic.edu/messaging/name-and-boilerplate/"):
    return {"chunk_id": cid, "text": "Use University of Illinois Chicago.", "score": score,
            "source_id": "name-boilerplate", "source_title": "Name and boilerplate", "source_url": url,
            "category": category, "section": "University name"}


def tool_response(edits, summary="ok", skipped=None, name=rw.TOOL_NAME):
    data = {"edits": edits, "summary": summary}
    if skipped is not None:
        data["skipped_issue_ids"] = skipped
    return {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": "t1", "name": name, "input": data}}]}},
        "stopReason": "tool_use", "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
        "metrics": {"latencyMs": 5}}


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        r = self.responses.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r


def client_error(code, status=400):
    return ClientError({"Error": {"Code": code, "Message": code},
                        "ResponseMetadata": {"HTTPStatusCode": status}}, "Converse")


def service(client, **kw):
    return rw.RewriteService(client, model_fast=FAST, model_quality=QUALITY, sleep=lambda s: None, **kw)


# --------------------------------------------------------------------------- edit -> change mapping

def test_edit_maps_to_change_with_offsets_and_linked_issue_guideline():
    text = "Welcome to the University of Illinois at Chicago campus."
    s = text.index("University")
    iss = [issue("brand-001-1", "brand", s, s + len("University of Illinois at Chicago"), text,
                 url="https://brand.uic.edu/x", title="UIC Name and boilerplate")]
    edits = [{"ruleset": "brand", "original": "University of Illinois at Chicago",
              "replacement": "University of Illinois Chicago", "explanation": "Official name.",
              "issue_ids": ["brand-001-1"]}]
    changes, dropped = rw.edits_to_changes(text, edits, iss, [chunk()], ALL)
    assert dropped == {}
    (c,) = changes
    assert list(c) == list(rw._CHANGE_KEYS)
    assert text[c["original_start"]:c["original_end"]] == c["original_text"] == edits[0]["original"]
    assert c["change_id"] == "chg-1" and c["issue_ids"] == ["brand-001-1"]
    assert c["guideline_url"] == "https://brand.uic.edu/x" and c["guideline_title"] == "UIC Name and boilerplate"
    assert rw.apply_changes(text, changes) == "Welcome to the University of Illinois Chicago campus."


def test_not_found_overlap_noop_and_bad_ruleset_are_dropped():
    text = "Click here to register. Click here for info."
    edits = [
        {"ruleset": "accessibility", "original": "Click here to register", "replacement": "Register now",
         "explanation": "x", "issue_ids": []},
        {"ruleset": "accessibility", "original": "here to register", "replacement": "y", "explanation": "x",
         "issue_ids": []},  # overlaps the first
        {"ruleset": "content", "original": "nonexistent words", "replacement": "z", "explanation": "x",
         "issue_ids": []},
        {"ruleset": "content", "original": "info", "replacement": "info", "explanation": "x", "issue_ids": []},
        {"ruleset": "brand", "original": "for", "replacement": "about", "explanation": "x", "issue_ids": []},
        {"original": "Click"},  # malformed
    ]
    changes, dropped = rw.edits_to_changes(text, edits, [], [], ["accessibility", "content"])
    assert [c["original_text"] for c in changes] == ["Click here to register"]
    assert dropped == {"overlap": 1, "not_found": 1, "no_op": 1, "ruleset": 1, "malformed": 1}


def test_prefers_occurrence_overlapping_referenced_issue_else_first_unused():
    text = "Click here. Then click here. Click here!"
    second = text.index("Click here!")
    iss = [issue("access-001-2", "accessibility", second, second + 10, text)]
    edits = [{"ruleset": "accessibility", "original": "Click here", "replacement": "Open the form",
              "explanation": "x", "issue_ids": ["access-001-2"]},
             {"ruleset": "accessibility", "original": "Click here", "replacement": "See details",
              "explanation": "x", "issue_ids": []}]
    changes, _ = rw.edits_to_changes(text, edits, iss, [], ALL)
    assert [(c["original_start"], c["rewritten_text"]) for c in changes] == [(0, "See details"),
                                                                             (second, "Open the form")]
    assert [c["change_id"] for c in changes] == ["chg-1", "chg-2"]


def test_whitespace_and_quote_normalization():
    text = "It’s going to be   AMAZING!!\nSee  you there."
    edits = [{"ruleset": "content", "original": "It's going to be AMAZING!!", "replacement": "It will be great.",
              "explanation": "x", "issue_ids": []},
             {"ruleset": "content", "original": " See you there. ", "replacement": " See you soon. ",
              "explanation": "x", "issue_ids": []}]
    changes, dropped = rw.edits_to_changes(text, edits, [], [], ALL)
    assert dropped == {}
    assert changes[0]["original_text"] == "It’s going to be   AMAZING!!"
    assert changes[1]["original_text"] == "See  you there."
    assert changes[1]["rewritten_text"] == "See you soon."  # copied padding stripped
    assert rw.apply_changes(text, changes) == "It will be great.\nSee you soon."


def test_emoji_offsets_are_code_points():
    text = "🎉🎉 Join us at UIC 😀 for fun!!"
    edits = [{"ruleset": "content", "original": "fun!!", "replacement": "fun!", "explanation": "x",
              "issue_ids": []}]
    (c,), _ = rw.edits_to_changes(text, edits, [], [], ALL)
    assert text[c["original_start"]:c["original_end"]] == "fun!!"
    assert c["original_start"] == text.index("fun!!")


def test_ruleset_falls_back_to_linked_issue_and_auto_links_issues():
    text = "We will utilize the space."
    s = text.index("utilize")
    iss = [issue("reading-005-1", "reading_level", s, s + 7, text, suggestion="use")]
    changes, _ = rw.edits_to_changes(text, [{"ruleset": "bogus", "original": "utilize", "replacement": "use",
                                            "explanation": "", "issue_ids": ["reading-005-1"]}], iss, [], ALL)
    assert changes[0]["ruleset"] == "reading_level"
    assert changes[0]["explanation"] == "msg reading-005-1"  # empty explanation -> issue message
    changes, _ = rw.edits_to_changes(text, [{"ruleset": "reading_level", "original": "utilize the",
                                            "replacement": "use the", "explanation": "x"}], iss, [], ALL)
    assert changes[0]["issue_ids"] == ["reading-005-1"]


def test_guideline_from_best_rag_chunk_for_ruleset():
    text = "Hey guys, welcome."
    chunks = [chunk("n1", "name", 0.9), chunk("t1", "tone", 0.4, url="https://brand.uic.edu/messaging/voice-and-tone/")]
    changes, _ = rw.edits_to_changes(text, [{"ruleset": "audience_tone", "original": "Hey guys",
                                            "replacement": "Hi everyone", "explanation": "x", "issue_ids": []}],
                                     [], chunks, ALL)
    assert changes[0]["guideline_url"] == "https://brand.uic.edu/messaging/voice-and-tone/"
    assert changes[0]["guideline_title"] == "Name and boilerplate — University name"


# --------------------------------------------------------------------------- model selection

def test_select_model_adaptive():
    short = "word " * 50
    assert rw.select_model(short, [{}] * 3, FAST, QUALITY)[0] == FAST
    assert rw.select_model(short, [{}] * 8, FAST, QUALITY)[0] == QUALITY
    assert rw.select_model("word " * 300, [], FAST, QUALITY)[0] == QUALITY


def test_rewrite_uses_fast_model_for_short_text_and_forces_tool():
    text = "Hey guys, welcome."
    client = FakeClient(tool_response([{"ruleset": "audience_tone", "original": "Hey guys",
                                        "replacement": "Hi everyone", "explanation": "Inclusive.",
                                        "issue_ids": []}], summary="One fix."))
    res = service(client).rewrite(text, [], [chunk()], "Students", "Email", ["audience_tone"])
    call = client.calls[0]
    assert call["modelId"] == FAST
    assert call["toolConfig"]["toolChoice"] == {"tool": {"name": rw.TOOL_NAME}}
    schema = call["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]
    assert schema["properties"]["edits"]["items"]["properties"]["ruleset"]["enum"] == ["audience_tone"]
    assert "grade 8" in call["system"][0]["text"] and "Name and boilerplate" in call["system"][0]["text"]
    assert res.model_used == FAST and not res.fallback and res.summary == "One fix."
    assert res.changes[0]["rewritten_text"] == "Hi everyone"


def test_instruction_is_added_to_prompt():
    client = FakeClient(tool_response([]))
    service(client).rewrite("Hello there.", [], [], "Faculty", "Website", ALL, instruction="Make it more formal")
    assert "Make it more formal" in client.calls[0]["messages"][0]["content"][0]["text"]
    assert "grade 10" in client.calls[0]["system"][0]["text"]


# --------------------------------------------------------------------------- retries / fallback

def test_retries_throttling_then_succeeds():
    client = FakeClient(client_error("ThrottlingException", 429), tool_response([]))
    sleeps = []
    svc = rw.RewriteService(client, model_fast=FAST, model_quality=QUALITY, sleep=sleeps.append)
    res = svc.rewrite("Short text.", [], [], "Staff", "Email", ALL)
    assert res.model_used == FAST and res.attempts == 2 and len(sleeps) == 1 and not res.fallback


def test_quality_failure_switches_to_fast_model():
    text = "word " * 400
    client = FakeClient(ReadTimeoutError(endpoint_url="https://x"), tool_response([]))
    res = service(client).rewrite(text, [], [], "Staff", "Email", ALL)
    assert [c["modelId"] for c in client.calls] == [QUALITY, FAST]
    assert res.model_used == FAST


def test_non_retryable_error_on_fast_model_falls_back_to_rules():
    text = "We will utilize the space prior to noon. Click here."
    u = text.index("utilize")
    p = text.index("prior to")
    c = text.index("Click here")
    iss = [issue("reading-005-1", "reading_level", u, u + 7, text, suggestion="use"),
           issue("content-006-2", "content", p, p + 8, text, suggestion="before"),
           issue("access-001-1", "accessibility", c, c + 10, text, suggestion="Describe where the link goes"),
           issue("reading-001-1", "reading_level", 0, len(text), text, suggestion="use", scope="document")]
    client = FakeClient(client_error("AccessDeniedException", 403))
    res = service(client).rewrite(text, iss, [], "Students", "Email", ALL)
    assert len(client.calls) == 1
    assert res.fallback and res.model_used == rw.FALLBACK_MODEL
    assert [(ch["original_text"], ch["rewritten_text"]) for ch in res.changes] == [("utilize", "use"),
                                                                                 ("prior to", "before")]
    assert rw.apply_changes(text, res.changes) == "We will use the space before noon. Click here."


def test_time_budget_exhausted_falls_back_without_calling():
    client = FakeClient()
    res = service(client).rewrite("Hi.", [], [], "Staff", "Email", ALL, deadline=0.0)
    assert res.fallback and client.calls == []


def test_missing_tool_call_is_retried_then_falls_back():
    no_tool = {"output": {"message": {"content": [{"text": "sorry"}]}}, "stopReason": "end_turn"}
    client = FakeClient(no_tool, no_tool, no_tool)
    res = service(client).rewrite("Hi.", [], [], "Staff", "Email", ALL)
    assert len(client.calls) == 3 and res.fallback


def test_gap_fill_adds_missed_literal_fixes_but_respects_skipped():
    text = "Meet on March 5th at 4pm in the Fall."
    m, f, fall = text.index("March 5th"), text.index("4pm"), text.index("Fall")
    iss = [issue("content-005-1", "content", m, m + 9, text, suggestion="March 5"),
           issue("content-003-2", "content", f, f + 3, text, suggestion="4 p.m."),
           issue("content-026-1", "content", fall, fall + 4, text, suggestion="fall")]
    client = FakeClient(tool_response([{"ruleset": "content", "original": "March 5th", "replacement": "March 5",
                                        "explanation": "Dates.", "issue_ids": ["content-005-1"]}],
                                      skipped=["content-026-1"]))
    res = service(client).rewrite(text, iss, [], "Staff", "Email", ALL)
    assert [ch["rewritten_text"] for ch in res.changes] == ["March 5", "4 p.m."]
    assert [ch["change_id"] for ch in res.changes] == ["chg-1", "chg-2"]
    assert res.dropped.get("gap_filled") == 1


def test_literal_suggestion_detection_and_case():
    assert rw.is_literal_suggestion("University of Illinois Chicago")
    assert rw.is_literal_suggestion("use") and rw.is_literal_suggestion("4 p.m.")
    for s in ("Describe where the link goes", "Split into two or more sentences", "Replace with a period",
              "Use sentence case", "(remove this comma)", "people / everyone", "UIC + space + full word", None, ""):
        assert not rw.is_literal_suggestion(s)
    text = "Utilize it."
    ch = rw.fallback_changes(text, [issue("reading-005-1", "reading_level", 0, 7, text, suggestion="use")], ALL)
    assert ch[0]["rewritten_text"] == "Use"


def test_parse_tool_output_with_botocore_stubber():
    client = boto3.client("bedrock-runtime", region_name="us-east-1", aws_access_key_id="x",
                          aws_secret_access_key="x")
    stub = Stubber(client)
    edits = [{"ruleset": "brand", "original": "UIC's", "replacement": "UIC’s", "explanation": "x",
              "issue_ids": []}]
    stub.add_response("converse", {
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t", "name": rw.TOOL_NAME, "input": {"edits": edits, "summary": "s"}}}]}},
        "stopReason": "tool_use", "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        "metrics": {"latencyMs": 1}})
    with stub:
        res = service(client).rewrite("UIC's campus.", [], [], "Staff", "Email", ["brand"])
    assert not res.fallback and res.changes[0]["rewritten_text"] == "UIC’s"
    with pytest.raises(rw.RewriteError):
        rw.parse_tool_output({"output": {"message": {"content": [{"toolUse": {"name": rw.TOOL_NAME,
                                                                               "input": {"x": 1}}}]}}})
