from fastapi.testclient import TestClient

from backend.api.rules_routes import app

client = TestClient(app)


def test_list_rulesets():
    r = client.get("/api/rules")
    assert r.status_code == 200
    rulesets = r.json()["rulesets"]
    assert {rs["ruleset_id"] for rs in rulesets} == {
        "brand", "accessibility", "content", "reading_level", "audience_tone"
    }
    assert all("rules" not in rs for rs in rulesets)
    assert all(rs["rule_count"] > 0 for rs in rulesets)


def test_list_rulesets_with_rules():
    r = client.get("/api/rules", params={"include_rules": True})
    assert all(len(rs["rules"]) == rs["rule_count"] for rs in r.json()["rulesets"])


def test_get_ruleset():
    r = client.get("/api/rules/brand")
    assert r.status_code == 200
    assert r.json()["rules"][0]["rule_id"] == "brand-001"


def test_get_unknown_ruleset_404():
    assert client.get("/api/rules/nope").status_code == 404


def test_check_text():
    r = client.post("/api/rules/check", json={
        "text": "Hey guys! Visit the University of Illinois at Chicago at 3:00 PM.",
        "audience": "students",
        "channel": "email",
    })
    assert r.status_code == 200
    body = r.json()
    ids = {i["rule_id"] for i in body["analysis"]["issues"]}
    assert {"brand-001", "content-003", "tone-002"} <= ids
    assert body["scores"]["status"] in {"Approved", "Minor Revisions", "Major Revisions"}
    assert 0 <= body["scores"]["brand_score"] <= 100


def test_check_subset_of_rulesets():
    r = client.post("/api/rules/check", json={"text": "e-mail us", "rulesets": ["brand"]})
    assert r.status_code == 200
    assert r.json()["analysis"]["issues"] == []


def test_check_validation_errors():
    assert client.post("/api/rules/check", json={"text": ""}).status_code == 422
    assert client.post("/api/rules/check", json={"text": "   "}).status_code == 400
    assert client.post("/api/rules/check", json={"text": "hi", "audience": "alumni"}).status_code == 422
    assert client.post("/api/rules/check", json={"text": "hi", "rulesets": ["nope"]}).status_code == 400
    assert client.post("/api/rules/check", json={"text": "word " * 5001}).status_code == 400


def test_audiences():
    body = client.get("/api/audiences").json()
    targets = {a["audience_id"]: a["target_grade_level"] for a in body["audiences"]}
    assert targets == {"students": 8, "faculty": 10, "staff": 10}
    assert body["channels"] == ["email", "website", "social_media"]
