from fastapi.testclient import TestClient

from backend.api.llm_routes import app, get_llm_service
from backend.services.llm_service import LLMResponse, ModelInvocationError


class FakeLLMService:
    def rewrite_text(self, **kwargs):
        assert kwargs["audience"] == "students"
        assert kwargs["channel"] == "email"
        return LLMResponse(
            text="Welcome to [BRAND]University of Illinois Chicago[/BRAND]!",
            model_id="fake-haiku",
            latency_ms=12.5,
            token_usage={"input_tokens": 20, "output_tokens": 10},
            selection={"model_name": "Haiku", "complexity_score": 8},
        )

    def refine_text(self, **kwargs):
        assert kwargs["refinement_request"] == "Make it warmer."
        return LLMResponse(
            text="[AUDIENCE_TONE]Welcome, students![/AUDIENCE_TONE]",
            model_id="fake-haiku",
            latency_ms=9,
            refinement={
                "patterns": ["welcoming"],
                "rulesets": ["AUDIENCE_TONE"],
                "is_partial": False,
            },
        )


class FailingLLMService:
    def rewrite_text(self, **kwargs):
        raise ModelInvocationError("Bedrock unavailable")


app.dependency_overrides[get_llm_service] = lambda: FakeLLMService()
client = TestClient(app)


def test_rewrite_returns_parser_diff_and_model_metadata():
    response = client.post("/api/llm/rewrite", json={
        "original_text": "Welcome to the University of Illinois at Chicago!",
        "issues": [{"ruleset_id": "brand", "message": "Use the current name."}],
        "guidelines": [{"content": "Use University of Illinois Chicago."}],
        "audience": "students",
        "channel": "email",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["rewritten"]["plain_text"] == "Welcome to University of Illinois Chicago!"
    assert body["rewritten"]["changes"][0]["rulesets"] == ["BRAND"]
    assert body["diff"]["stats"]["total"] > 0
    assert body["diff"]["annotations"][0]["rulesets"] == ["BRAND"]
    assert body["model"]["model_id"] == "fake-haiku"


def test_refine_returns_plan_and_parsed_result():
    response = client.post("/api/llm/refine", json={
        "current_text": "Students should attend.",
        "refinement_request": "Make it warmer.",
        "audience": "students",
        "channel": "email",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["rewritten"]["plain_text"] == "Welcome, students!"
    assert body["refinement"]["patterns"] == ["welcoming"]
    assert body["diff"]["annotations"][0]["rulesets"] == ["AUDIENCE_TONE"]


def test_explain_change_with_guideline_attribution():
    response = client.post("/api/llm/explain", json={
        "original_text": "University of Illinois at Chicago",
        "revised_text": "University of Illinois Chicago",
        "rulesets": ["brand"],
        "guideline_title": "UIC Editorial Style Guide",
        "guideline_url": "https://today.uic.edu/uic-editorial-style-guide/",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "replace"
    assert body["rulesets"] == ["BRAND"]
    assert body["guideline"]["title"] == "UIC Editorial Style Guide"
    assert "UIC" in body["rationale"]


def test_request_validation_and_service_error_mapping():
    assert client.post("/api/llm/rewrite", json={"original_text": "   "}).status_code == 422
    assert client.post("/api/llm/refine", json={
        "current_text": "Hello",
        "refinement_request": "shorter",
        "selection_start": 3,
    }).status_code == 422
    assert client.post("/api/llm/explain", json={
        "original_text": "same",
        "revised_text": "same",
    }).status_code == 422

    app.dependency_overrides[get_llm_service] = lambda: FailingLLMService()
    try:
        response = client.post("/api/llm/rewrite", json={"original_text": "Hello"})
        assert response.status_code == 502
        assert "Bedrock unavailable" in response.json()["detail"]
    finally:
        app.dependency_overrides[get_llm_service] = lambda: FakeLLMService()


def test_openapi_documents_all_task_38_endpoints():
    schema = client.get("/openapi.json").json()
    for path in ("/api/llm/rewrite", "/api/llm/refine", "/api/llm/explain"):
        assert path in schema["paths"]
        assert "summary" in schema["paths"][path]["post"]
        assert "description" in schema["paths"][path]["post"]
