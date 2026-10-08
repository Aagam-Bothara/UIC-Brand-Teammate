"""Tests for backend/api/analyze_routes.py and the integrated app (backend/api/main.py)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend.api import analyze_routes as ar
from backend.api.main import app
from backend.services.orchestrator import AnalysisUnavailableError
from backend.services.rule_engine import TextTooLongError

ALL = ["brand", "accessibility", "content", "reading_level", "audience_tone"]


def fake_analysis(text="Hey guys!"):
    return {
        "analysis_id": "a1", "original": text, "rewritten": "Hi everyone!",
        "changes": [{"change_id": "chg-1", "ruleset": "audience_tone", "original_start": 0, "original_end": 9,
                     "original_text": "Hey guys!", "rewritten_text": "Hi everyone!", "explanation": "x",
                     "issue_ids": ["tone-002-1"], "guideline_url": None, "guideline_title": None}],
        "issues": [{"issue_id": "tone-002-1", "ruleset": "audience_tone", "rule_id": "tone-002",
                    "severity": "medium", "message": "m", "start": 0, "end": 8, "excerpt": "Hey guys",
                    "suggestion": "Hi everyone", "guideline_url": None, "guideline_title": None,
                    "scope": "span", "rule_name": "Gendered language"}],
        "scores": {"brand": 95, "accessibility": 100,
                   "reading_level": {"grade": 2.1, "target": 8, "audience": "Students"},
                   "total_issues": 1, "status": "Approved"},
        "guidelines": [], "audience": "Students", "channel": "Email", "rulesets": ALL,
        "model_used": "m", "latency_ms": 5,
    }


@pytest.fixture
def client():
    seen = {}

    def analyzer(payload):
        seen["analyze"] = payload
        return fake_analysis(payload["text"])

    def refiner(payload):
        seen["refine"] = payload
        return {"reply": "ok", "analysis": None, "guidelines": []}

    app.dependency_overrides[ar.get_analyzer] = lambda: analyzer
    app.dependency_overrides[ar.get_refiner] = lambda: refiner
    c = TestClient(app)
    c.seen = seen
    yield c
    app.dependency_overrides.clear()


def test_analyze_ok_and_normalizes_audience_channel(client):
    r = client.post("/api/analyze", json={"text": "Hey guys!", "audience": "students", "channel": "social_media",
                                          "rulesets": ["brand"]})
    assert r.status_code == 200, r.text
    assert client.seen["analyze"] == {"text": "Hey guys!", "audience": "Students", "channel": "Social Media",
                                      "rulesets": ["brand"]}
    body = r.json()
    assert set(body) == set(fake_analysis())
    assert body["changes"][0]["ruleset"] == "audience_tone"


def test_analyze_defaults(client):
    r = client.post("/api/analyze", json={"text": "Hello"})
    assert r.status_code == 200
    assert client.seen["analyze"]["rulesets"] == ALL and client.seen["analyze"]["audience"] == "Students"


@pytest.mark.parametrize("body", [
    {"text": ""}, {"text": "   "}, {"text": "x", "audience": "Alumni"}, {"text": "x", "channel": "Fax"},
    {"text": "x", "rulesets": ["nope"]}, {"audience": "Students"}, {"text": "x" * 40001},
])
def test_analyze_validation_422(client, body):
    assert client.post("/api/analyze", json=body).status_code == 422


@pytest.mark.parametrize("exc,code", [
    (TextTooLongError("Text has 6000 words"), 422),
    (ValueError("bad"), 422),
    (AnalysisUnavailableError("rule engine unavailable"), 503),
    (type("RAGServiceError", (Exception,), {})("kb down"), 503),
])
def test_analyze_error_mapping(exc, code):
    def boom(payload):
        raise exc
    app.dependency_overrides[ar.get_analyzer] = lambda: boom
    try:
        r = TestClient(app).post("/api/analyze", json={"text": "Hello"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == code and "detail" in r.json()


def test_refine_ok_and_validation(client):
    body = {"message": "How do I write the name?", "original": "Hey guys!", "current_text": "Hey guys!",
            "audience": "Faculty", "channel": "Website", "rulesets": ALL,
            "history": [{"role": "user", "content": "hi"}], "analysis_id": None}
    r = client.post("/api/llm/refine", json=body)
    assert r.status_code == 200 and r.json() == {"reply": "ok", "analysis": None, "guidelines": []}
    assert client.seen["refine"]["history"] == [{"role": "user", "content": "hi"}]
    assert client.post("/api/llm/refine", json={**body, "message": " "}).status_code == 422
    assert client.post("/api/llm/refine", json={**body, "history": [{"role": "system", "content": "x"}]}
                       ).status_code == 422


def test_refine_returns_analysis(client):
    app.dependency_overrides[ar.get_refiner] = lambda: (
        lambda p: {"reply": "done", "analysis": fake_analysis(), "guidelines": []})
    r = client.post("/api/llm/refine", json={"message": "Make it formal", "original": "Hey guys!"})
    assert r.status_code == 200 and r.json()["analysis"]["analysis_id"] == "a1"


def test_integrated_app_mounts_all_routers():
    paths = {route["path"] for route in [{"path": p} for p in app.openapi()["paths"]]}
    for p in ("/api/analyze", "/api/llm/refine", "/api/rules", "/api/rules/{ruleset_id}", "/api/rules/check",
              "/api/audiences", "/api/rag/retrieve", "/api/rag/context", "/api/rag/health", "/api/health"):
        assert p in paths


def test_integrated_rules_endpoints_and_cors():
    c = TestClient(app)
    r = c.get("/api/rules", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 200 and len(r.json()["rulesets"]) == 5
    assert r.headers["access-control-allow-origin"] == "*"
    assert c.get("/api/audiences").status_code == 200


def test_lambda_handler_serves_integrated_app():
    from backend.api.lambda_app import handler

    event = {"version": "2.0", "routeKey": "$default", "rawPath": "/api/rules", "rawQueryString": "",
             "headers": {"host": "x"}, "isBase64Encoded": False,
             "requestContext": {"http": {"method": "GET", "path": "/api/rules", "sourceIp": "1.1.1.1",
                                         "protocol": "HTTP/1.1", "userAgent": "t"},
                                "stage": "$default", "requestId": "r", "domainName": "x", "accountId": "1",
                                "apiId": "x", "routeKey": "$default", "timeEpoch": 0, "time": ""}}
    resp = handler(event, None)
    assert resp["statusCode"] == 200 and len(json.loads(resp["body"])["rulesets"]) == 5
