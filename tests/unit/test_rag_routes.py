"""Tests for backend/api/rag_routes.py (Workstream 1, Task 1.6).

Most tests use a fake service implementing the contract interface (docs/API_CONTRACT.md) via
``app.dependency_overrides``. The "real service" section at the end runs the actual RAGService
(local backend over tests/fixtures/guidelines, Bedrock via botocore Stubber). No AWS is touched.
"""

from __future__ import annotations

import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.rag_routes import (
    HealthResponse,
    RetrievalResponse,
    RetrieveRequest,
    ContextRequest,
    SourcesResponse,
    get_service,
    router,
)

MOCKS = Path(__file__).resolve().parents[1] / "mocks"
CHUNK_KEYS = {"chunk_id", "text", "score", "source_id", "source_title", "source_url", "category", "section"}


# --------------------------------------------------------------------------------------
# Fake service (contract interface only)
# --------------------------------------------------------------------------------------


class RAGServiceError(Exception):
    """Stand-in for backend.services.rag_service.RAGServiceError (matched by class name)."""


@dataclass
class FakeChunk:
    chunk_id: str
    text: str
    score: float
    source_id: str
    source_title: str
    source_url: str
    category: str
    section: str | None


def _chunk(n: int, category: str = "editorial", score: float = 0.5) -> FakeChunk:
    return FakeChunk(
        chunk_id=f"editorial-style-{n:03d}",
        text=f"# Editorial and style guide — Section {n}\n\nUse University of Illinois Chicago.",
        score=score,
        source_id="editorial-style",
        source_title="Editorial and style guide",
        source_url="https://brand.uic.edu/messaging/editorial-and-style-guide/",
        category=category,
        section=f"Section {n}",
    )


class FakeRAGService:
    backend = "local"

    def __init__(self, fail: Exception | None = None):
        self.fail = fail
        self.calls: list[tuple[str, tuple, dict]] = []

    def _maybe_fail(self):
        if self.fail is not None:
            raise self.fail

    def retrieve(self, query, top_k=5, category=None):
        self.calls.append(("retrieve", (query,), {"top_k": top_k, "category": category}))
        self._maybe_fail()
        return [_chunk(i, category or "editorial", 1.0 - i / 10) for i in range(1, top_k + 1)][:3]

    def retrieve_guidelines(self, query, audience=None, top_k=5):
        self.calls.append(("retrieve_guidelines", (query,), {"audience": audience, "top_k": top_k}))
        self._maybe_fail()
        return [_chunk(i, "audience", 0.8 - i / 10) for i in range(1, min(top_k, 3) + 1)]

    def retrieve_for_text(self, text, audience=None, channel=None, rulesets=None, top_k=8):
        self.calls.append(
            ("retrieve_for_text", (text,),
             {"audience": audience, "channel": channel, "rulesets": rulesets, "top_k": top_k})
        )
        self._maybe_fail()
        return [_chunk(i, score=0.9 - i / 20) for i in range(1, min(top_k, 4) + 1)]

    def list_sources(self):
        self._maybe_fail()
        return json.loads((MOCKS / "rag_sources_response.json").read_text())["sources"]

    def health(self):
        self._maybe_fail()
        return {"status": "ok", "backend": "local", "kb_id": None, "chunk_count": 120}


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def fake() -> FakeRAGService:
    return FakeRAGService()


@pytest.fixture
def client(app: FastAPI, fake: FakeRAGService) -> TestClient:
    app.dependency_overrides[get_service] = lambda: fake
    return TestClient(app)


def _failing_client(app: FastAPI, exc: Exception) -> TestClient:
    app.dependency_overrides[get_service] = lambda: FakeRAGService(fail=exc)
    return TestClient(app)


# --------------------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------------------


def test_retrieve_happy_path(client: TestClient, fake: FakeRAGService):
    r = client.post("/api/rag/retrieve", json={"query": "university name", "top_k": 5, "category": "name"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"results", "backend", "latency_ms"}
    assert body["backend"] == "local"
    assert isinstance(body["latency_ms"], int) and body["latency_ms"] >= 0
    assert len(body["results"]) == 3
    for item in body["results"]:
        assert set(item) == CHUNK_KEYS
    assert fake.calls == [("retrieve", ("university name",), {"top_k": 5, "category": "name"})]


def test_retrieve_defaults(client: TestClient, fake: FakeRAGService):
    r = client.post("/api/rag/retrieve", json={"query": "serial comma"})
    assert r.status_code == 200
    assert fake.calls == [("retrieve", ("serial comma",), {"top_k": 5, "category": None})]


def test_retrieve_with_audience_dispatches_to_retrieve_guidelines(client: TestClient, fake: FakeRAGService):
    r = client.post("/api/rag/retrieve", json={"query": "tone for reminders", "audience": "Students", "top_k": 4})
    assert r.status_code == 200
    assert fake.calls == [("retrieve_guidelines", ("tone for reminders",), {"audience": "Students", "top_k": 4})]
    body = r.json()
    assert set(body) == {"results", "backend", "latency_ms"}
    assert all(set(item) == CHUNK_KEYS for item in body["results"])


def test_retrieve_category_takes_precedence_over_audience(client: TestClient, fake: FakeRAGService):
    r = client.post("/api/rag/retrieve", json={"query": "q", "category": "tone", "audience": "Faculty"})
    assert r.status_code == 200
    assert fake.calls == [("retrieve", ("q",), {"top_k": 5, "category": "tone"})]


def test_retrieve_free_text_audience_accepted(client: TestClient, fake: FakeRAGService):
    r = client.post("/api/rag/retrieve", json={"query": "q", "audience": "Prospective graduate students"})
    assert r.status_code == 200
    assert fake.calls[0][0] == "retrieve_guidelines"


def test_context_happy_path(client: TestClient, fake: FakeRAGService):
    req = json.loads((MOCKS / "rag_context_request.json").read_text())
    r = client.post("/api/rag/context", json=req)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"results", "backend", "latency_ms"}
    assert all(set(item) == CHUNK_KEYS for item in body["results"])
    name, args, kwargs = fake.calls[0]
    assert name == "retrieve_for_text"
    assert args == (req["text"],)
    assert kwargs == {"audience": "Students", "channel": "Email",
                      "rulesets": ["brand", "accessibility", "reading_level"], "top_k": 8}


def test_context_minimal(client: TestClient, fake: FakeRAGService):
    r = client.post("/api/rag/context", json={"text": "Welcome back to UIC!"})
    assert r.status_code == 200
    assert fake.calls[0][2] == {"audience": None, "channel": None, "rulesets": None, "top_k": 8}


def test_sources(client: TestClient):
    r = client.get("/api/rag/sources")
    assert r.status_code == 200
    sources = r.json()["sources"]
    assert {s["source_id"] for s in sources} == {
        "name-boilerplate", "voice-tone", "brand-strategy", "editorial-style"
    }
    assert {"source_id", "title", "url", "category", "raw_path", "chunk_count", "sha256"} <= set(sources[0])


def test_health(client: TestClient):
    r = client.get("/api/rag/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "backend": "local", "kb_id": None, "chunk_count": 120,
                        "reason": None, "last_backend": None}


def test_health_degraded_is_200_with_reason(app: FastAPI):
    class Degraded(FakeRAGService):
        def health(self):
            return {"status": "degraded", "backend": "local", "kb_id": "KB123",
                    "chunk_count": 120, "reason": "Bedrock unreachable; using local fallback"}

    app.dependency_overrides[get_service] = lambda: Degraded()
    r = TestClient(app).get("/api/rag/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"
    assert r.json()["reason"].startswith("Bedrock unreachable")


def test_unknown_rulesets_accepted(client: TestClient, fake: FakeRAGService):
    r = client.post("/api/rag/context", json={"text": "draft", "rulesets": ["audience_tone", "something_new"]})
    assert r.status_code == 200
    assert fake.calls[0][2]["rulesets"] == ["audience_tone", "something_new"]


# --------------------------------------------------------------------------------------
# Validation (422)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "x" * 1001},
        {"query": "ok", "top_k": 0},
        {"query": "ok", "top_k": 21},
        {"query": "ok", "top_k": True},
        {"query": "ok", "top_k": False},
        {"query": "ok", "top_k": 2.5},
        {"query": "ok", "top_k": None},
        {"query": "ok", "category": "marketing"},
        {"query": "ok", "category": "accessibility"},
        {"query": "ok", "audience": "x" * 201},
        {"query": "ok", "unexpected": 1},
        {},
    ],
)
def test_retrieve_validation_422(client: TestClient, fake: FakeRAGService, payload):
    r = client.post("/api/rag/retrieve", json=payload)
    assert r.status_code == 422
    assert fake.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "\n\t "},
        {"text": "x" * 40001},
        {"text": "ok", "audience": "x" * 201},
        {"text": "ok", "top_k": 0},
        {"text": "ok", "top_k": 21},
        {"text": "ok", "top_k": True},
        {"text": "ok", "rulesets": "brand"},
        {},
    ],
)
def test_context_validation_422(client: TestClient, fake: FakeRAGService, payload):
    r = client.post("/api/rag/context", json=payload)
    assert r.status_code == 422
    assert fake.calls == []


def test_limits_inclusive(client: TestClient):
    assert client.post("/api/rag/retrieve", json={"query": "x" * 1000, "top_k": 20}).status_code == 200
    assert client.post("/api/rag/retrieve", json={"query": "x", "top_k": 1}).status_code == 200
    assert client.post("/api/rag/context", json={"text": "x" * 40000, "top_k": 20}).status_code == 200


@pytest.mark.parametrize("category", ["name", "tone", "audience", "editorial"])
def test_all_categories_accepted(client: TestClient, category):
    r = client.post("/api/rag/retrieve", json={"query": "q", "category": category})
    assert r.status_code == 200


def test_service_value_error_maps_to_422(app: FastAPI):
    c = _failing_client(app, ValueError("query too vague"))
    r = c.post("/api/rag/retrieve", json={"query": "q"})
    assert r.status_code == 422
    assert r.json() == {"detail": "query too vague"}


# --------------------------------------------------------------------------------------
# Backend failure (503)
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("post", "/api/rag/retrieve", {"query": "q"}),
        ("post", "/api/rag/retrieve", {"query": "q", "audience": "Staff"}),
        ("post", "/api/rag/context", {"text": "draft"}),
        ("get", "/api/rag/sources", None),
        ("get", "/api/rag/health", None),
    ],
)
def test_rag_service_error_maps_to_503(app: FastAPI, method, path, payload):
    c = _failing_client(app, RAGServiceError("Bedrock throttled"))
    r = c.request(method.upper(), path, json=payload)
    assert r.status_code == 503
    assert set(r.json()) == {"detail"}
    assert "Bedrock throttled" in r.json()["detail"]


def test_subclass_of_rag_service_error_maps_to_503(app: FastAPI):
    class BedrockDown(RAGServiceError):
        pass

    c = _failing_client(app, BedrockDown("kb unreachable"))
    assert c.post("/api/rag/retrieve", json={"query": "q"}).status_code == 503


def test_unexpected_error_is_not_masked_as_503(app: FastAPI):
    c = TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides[get_service] = lambda: FakeRAGService(fail=RuntimeError("bug"))
    assert c.post("/api/rag/retrieve", json={"query": "q"}).status_code == 500


def test_get_service_uses_get_rag_service(app: FastAPI, monkeypatch):
    """Real dependency path, with a stub rag_service module (no real backend import)."""
    fake = FakeRAGService()
    mod = types.ModuleType("backend.services.rag_service")
    mod.get_rag_service = lambda: fake
    monkeypatch.setitem(sys.modules, "backend.services.rag_service", mod)
    r = TestClient(app).get("/api/rag/health")
    assert r.status_code == 200


def test_get_service_init_failure_maps_to_503(app: FastAPI, monkeypatch):
    mod = types.ModuleType("backend.services.rag_service")

    def boom():
        raise RAGServiceError("no index and no KB configured")

    mod.get_rag_service = boom
    monkeypatch.setitem(sys.modules, "backend.services.rag_service", mod)
    r = TestClient(app).post("/api/rag/retrieve", json={"query": "q"})
    assert r.status_code == 503
    assert "no index" in r.json()["detail"]


# --------------------------------------------------------------------------------------
# OpenAPI
# --------------------------------------------------------------------------------------


def test_openapi_includes_endpoints(client: TestClient):
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "post" in paths["/api/rag/retrieve"]
    assert "post" in paths["/api/rag/context"]
    assert "get" in paths["/api/rag/sources"]
    assert "get" in paths["/api/rag/health"]
    for path, method in [("/api/rag/retrieve", "post"), ("/api/rag/context", "post"),
                         ("/api/rag/sources", "get"), ("/api/rag/health", "get")]:
        op = paths[path][method]
        assert op["tags"] == ["rag"]
        assert op["summary"]
        assert "503" in op["responses"]
    assert "422" in paths["/api/rag/retrieve"]["post"]["responses"]
    comps = schema["components"]["schemas"]
    assert comps["RetrieveRequest"]["properties"]["category"]
    assert comps["RetrieveRequest"]["properties"]["query"]["maxLength"] == 1000


def test_dev_server_mounts_router():
    from backend.api.dev_server import app as dev_app

    paths = set(dev_app.openapi()["paths"])
    assert {"/api/rag/retrieve", "/api/rag/context", "/api/rag/sources", "/api/rag/health"} <= paths


# --------------------------------------------------------------------------------------
# Mock files (consumed by Workstreams 2-4) must match the response models
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,model",
    [
        ("rag_retrieve_response.json", RetrievalResponse),
        ("rag_context_response.json", RetrievalResponse),
        ("rag_sources_response.json", SourcesResponse),
        ("rag_health_response.json", HealthResponse),
        ("rag_retrieve_request.json", RetrieveRequest),
        ("rag_context_request.json", ContextRequest),
    ],
)
def test_mock_files_match_models(filename, model):
    data = json.loads((MOCKS / filename).read_text())
    parsed = model.model_validate(data)
    if model is RetrievalResponse:
        scores = [c.score for c in parsed.results]
        assert scores == sorted(scores, reverse=True)
        assert all(set(c) == CHUNK_KEYS for c in data["results"])
        assert all(c.category in {"name", "tone", "audience", "editorial"} for c in parsed.results)
        assert all(c.text.startswith(f"# {c.source_title} — ") for c in parsed.results)


def test_mock_health_chunk_count_matches_sources():
    sources = json.loads((MOCKS / "rag_sources_response.json").read_text())["sources"]
    health = json.loads((MOCKS / "rag_health_response.json").read_text())
    assert health["chunk_count"] == sum(s["chunk_count"] for s in sources)


CONTRACT_SOURCES = {
    "name-boilerplate": ("name", "https://brand.uic.edu/messaging/name-and-boilerplate/"),
    "voice-tone": ("tone", "https://brand.uic.edu/messaging/voice-and-tone/"),
    "brand-strategy": ("audience", "https://brand.uic.edu/messaging/brand-strategy/"),
    "editorial-style": ("editorial", "https://brand.uic.edu/messaging/editorial-and-style-guide/"),
}


def test_mocks_use_contract_sources():
    sources = json.loads((MOCKS / "rag_sources_response.json").read_text())["sources"]
    assert {s["source_id"]: (s["category"], s["url"]) for s in sources} == CONTRACT_SOURCES
    for name in ("rag_retrieve_response.json", "rag_context_response.json"):
        for c in json.loads((MOCKS / name).read_text())["results"]:
            assert (c["category"], c["source_url"]) == CONTRACT_SOURCES[c["source_id"]]
            assert c["chunk_id"].startswith(c["source_id"] + "-")


def test_mock_requests_use_spec_values():
    from backend.api.rag_routes import AUDIENCES, CHANNELS, RULESETS

    req = json.loads((MOCKS / "rag_context_request.json").read_text())
    assert req["audience"] in AUDIENCES
    assert req["channel"] in CHANNELS
    assert set(req["rulesets"]) <= set(RULESETS)


def test_numeric_top_k_forms_still_accepted(client: TestClient, fake: FakeRAGService):
    """Only booleans are rejected; integral floats and numeric strings keep working."""
    assert client.post("/api/rag/retrieve", json={"query": "q", "top_k": 2.0}).status_code == 200
    assert client.post("/api/rag/retrieve", json={"query": "q", "top_k": "3"}).status_code == 200
    assert [call[2]["top_k"] for call in fake.calls] == [2, 3]
    assert all(type(call[2]["top_k"]) is int for call in fake.calls)


# --------------------------------------------------------------------------------------
# Real service (no fake): shapes, mocks and error mapping against backend.services.rag_service
# --------------------------------------------------------------------------------------

FIXTURE_GUIDELINES = Path(__file__).resolve().parents[1] / "fixtures" / "guidelines"


@pytest.fixture
def real_local_client(app: FastAPI) -> TestClient:
    from backend.services.rag_service import RAGService

    svc = RAGService("local", guidelines_dir=FIXTURE_GUIDELINES)
    app.dependency_overrides[get_service] = lambda: svc
    return TestClient(app)


def _keys(name: str) -> dict:
    return json.loads((MOCKS / name).read_text())


def test_real_service_responses_match_mock_shapes(real_local_client: TestClient):
    c = real_local_client
    retrieve = c.post("/api/rag/retrieve", json=_keys("rag_retrieve_request.json")).json()
    context = c.post("/api/rag/context", json=_keys("rag_context_request.json")).json()
    audience = c.post("/api/rag/retrieve", json={"query": "tone", "audience": "Students"}).json()
    for body, mock in ((retrieve, "rag_retrieve_response.json"), (context, "rag_context_response.json"),
                       (audience, "rag_retrieve_response.json")):
        assert set(body) == set(_keys(mock))
        assert body["backend"] == "local"
        assert body["results"], "fixture index should produce hits"
        for item in body["results"]:
            assert set(item) == CHUNK_KEYS
            assert 0.0 <= item["score"] <= 1.0
            assert item["category"] in {"name", "tone", "audience", "editorial"}
        scores = [i["score"] for i in body["results"]]
        assert scores == sorted(scores, reverse=True)

    health = c.get("/api/rag/health").json()
    assert set(health) == set(_keys("rag_health_response.json"))
    assert health["status"] == "ok" and health["backend"] == "local" and health["kb_id"] is None

    sources = c.get("/api/rag/sources").json()["sources"]
    mock_source_keys = set(_keys("rag_sources_response.json")["sources"][0])
    assert sources and all(set(s) == mock_source_keys for s in sources)


def test_real_service_bedrock_errors_map_to_503_and_fallback_reports_local(app: FastAPI):
    import boto3
    from botocore.stub import Stubber

    from backend.services.rag_service import RAGService

    def service(mode: str) -> tuple[RAGService, Stubber]:
        svc = RAGService(mode, kb_id="KBTEST1234", region="us-east-1", guidelines_dir=FIXTURE_GUIDELINES)
        svc._sleep = lambda _s: None
        client = boto3.client("bedrock-agent-runtime", region_name="us-east-1",
                              aws_access_key_id="testing", aws_secret_access_key="testing")
        svc._bedrock._client = client
        stub = Stubber(client)
        stub.activate()
        return svc, stub

    strict, stub = service("bedrock")
    stub.add_client_error("retrieve", "AccessDeniedException", http_status_code=403)
    app.dependency_overrides[get_service] = lambda: strict
    r = TestClient(app).post("/api/rag/retrieve", json={"query": "university name"})
    assert r.status_code == 503
    assert r.json()["detail"].startswith("RAG backend unavailable: ")

    auto, stub = service("auto")
    stub.add_client_error("retrieve", "AccessDeniedException", http_status_code=403)
    app.dependency_overrides[get_service] = lambda: auto
    c = TestClient(app)
    r = c.post("/api/rag/retrieve", json={"query": "university name"})
    assert r.status_code == 200 and r.json()["backend"] == "local"
    health = c.get("/api/rag/health").json()
    assert (health["status"], health["backend"], health["last_backend"]) == ("degraded", "bedrock", "local")


def test_real_get_service_bedrock_without_kb_is_503(app: FastAPI, monkeypatch):
    from backend.config import reset_settings
    from backend.services import rag_service

    monkeypatch.setenv("UIC_RAG_BACKEND", "bedrock")
    monkeypatch.setenv("UIC_SSM_ENABLED", "0")
    monkeypatch.delenv("UIC_KB_ID", raising=False)
    reset_settings()
    rag_service.reset_rag_service()
    try:
        r = TestClient(app).get("/api/rag/health")
        assert r.status_code == 503
        assert "Knowledge Base id" in r.json()["detail"]
    finally:
        rag_service.reset_rag_service()
        monkeypatch.undo()
        reset_settings()
