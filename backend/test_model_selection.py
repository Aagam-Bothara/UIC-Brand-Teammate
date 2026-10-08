"""Offline unit tests for Task 3.5 adaptive model selection and cost tracking."""

import io
import json
import logging

import pytest

from backend.services.llm_service import LLMService


class FakeBedrockClient:
    def __init__(self, input_tokens=1_000, output_tokens=200):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def invoke_model(self, **kwargs):
        body = {
            "content": [{"text": "Rewritten text"}],
            "usage": {
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
            },
        }
        return {"body": io.BytesIO(json.dumps(body).encode("utf-8"))}


@pytest.fixture
def service():
    return LLMService(bedrock_client=FakeBedrockClient())


def test_short_simple_text_selects_haiku(service):
    decision = service.select_model("UIC welcomes students.", task="rewrite")

    assert decision.model_id == service.HAIKU_MODEL_ID
    assert 0 <= decision.complexity_score < service.COMPLEXITY_SCORE_THRESHOLD
    assert decision.reason == "simple_content_cost_optimized"
    assert decision.metrics["task"] == "rewrite"


def test_more_than_500_words_always_selects_sonnet(service):
    decision = service.select_model("word " * 501)

    assert decision.model_id == service.SONNET_MODEL_ID
    assert decision.reason == "word_count_above_500"


def test_issue_burden_can_route_short_complex_text_to_sonnet(service):
    text = (
        "Institutional accessibility requirements significantly "
        "complicate communications " * 12 + "."
    )
    issues = [{"severity": "critical"} for _ in range(4)]

    decision = service.select_model(text, issues=issues)

    assert len(text.split()) < service.WORD_COUNT_THRESHOLD
    assert decision.model_id == service.SONNET_MODEL_ID
    assert decision.complexity_score >= service.COMPLEXITY_SCORE_THRESHOLD


def test_selection_decision_is_structured_logged(service, caplog):
    with caplog.at_level(logging.INFO):
        service.select_model("A short announcement.", task="detection")

    record = next(
        record
        for record in caplog.records
        if record.message.startswith("model_selection ")
    )
    payload = json.loads(record.message.removeprefix("model_selection "))
    assert payload["model_name"] == "haiku"
    assert payload["metrics"]["task"] == "detection"
    assert "complexity_score" in payload


def test_actual_usage_tracks_cost_savings_against_sonnet(service):
    response = service._invoke_model_with_retry(
        model_id=service.HAIKU_MODEL_ID,
        system_prompt="system",
        user_prompt="user",
        max_tokens=100,
        temperature=0.0,
    )
    metrics = service.get_cost_metrics()

    assert response.estimated_cost_usd == pytest.approx(0.0005)
    assert response.estimated_savings_usd == pytest.approx(0.0055)
    assert metrics["requests_with_usage"] == 1
    assert metrics["haiku_requests"] == 1
    assert metrics["actual_cost_usd"] == response.estimated_cost_usd
    assert metrics["estimated_savings_usd"] == response.estimated_savings_usd


def test_legacy_private_selector_still_returns_model_id(service):
    assert service._select_model("Short text") == service.HAIKU_MODEL_ID
