"""Unit tests for backend.services.rag_service (no real AWS calls)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest import mock

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from backend.config import reset_settings
from backend.services import rag_service
from backend.services.rag_service import (CATEGORIES, MAX_TEXT_CHARS, Guideline, GuidelineChunk, RAGService,
                                          RAGServiceError, get_rag_service, reset_rag_service, stem, tokenize)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "guidelines"
KB_ID = "KBTEST1234"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    for name in ["UIC_KB_ID", "UIC_GUIDELINES_BUCKET", "UIC_RAG_BACKEND", "UIC_GUIDELINES_DIR", "AWS_REGION"]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("UIC_SSM_ENABLED", "0")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    reset_settings()
    reset_rag_service()
    yield
    reset_settings()
    reset_rag_service()


@pytest.fixture
def local() -> RAGService:
    return RAGService("local", guidelines_dir=FIXTURES)


@pytest.fixture
def log_records():
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collect(level=logging.DEBUG)
    logger = logging.getLogger("uic")
    logger.addHandler(handler)
    yield records
    logger.removeHandler(handler)


def _events(records) -> list[str]:
    return [getattr(r, "event", None) for r in records]


def _bedrock_service(backend: str = "bedrock", guidelines_dir: Path = FIXTURES):
    svc = RAGService(backend, kb_id=KB_ID, region="us-east-1", guidelines_dir=guidelines_dir)
    client = boto3.client("bedrock-agent-runtime", region_name="us-east-1")
    svc._bedrock._client = client
    svc._sleep = lambda _s: None  # no real backoff waits in tests
    return svc, Stubber(client)


def _retrieval_result(chunk: str, source_id: str, category: str, title: str, section: str, score: float) -> dict:
    return {
        "content": {"text": f"# {title} — {section}\n\nBody of {chunk}."},
        "location": {"type": "S3", "s3Location": {"uri": f"s3://uic-guidelines/chunks/{chunk}.md"}},
        "score": score,
        "metadata": {"source_id": source_id, "category": category, "title": title,
                     "url": f"https://brand.uic.edu/{source_id}/", "section": section,
                     "x-amz-bedrock-kb-source-uri": f"s3://uic-guidelines/chunks/{chunk}.md"},
    }


def _expected(query: str, top_k: int, category: str | None = None) -> dict:
    cfg: dict = {"numberOfResults": top_k}
    if category:
        cfg["filter"] = {"equals": {"key": "category", "value": category}}
    return {"knowledgeBaseId": KB_ID, "retrievalQuery": {"text": query},
            "retrievalConfiguration": {"vectorSearchConfiguration": cfg}}


# --- tokenizer / BM25 -------------------------------------------------------------------


def test_tokenizer_lowercases_drops_stopwords_and_stems():
    assert tokenize("The Capitalization of Titles") == ["capitaliz", "titl"]
    assert stem("capitalized") == stem("capitalize") == stem("capitalizing") == stem("capitalization")
    assert stem("links") == stem("linking") == "link"
    assert "the" not in tokenize("the and of to")


def test_local_bm25_ranks_relevant_chunk_first(local):
    cases = {
        "how to write the university name": "name-boilerplate-001",
        "alt text for images and link text": "editorial-style-003",
        "capitalize professor and dean titles": "editorial-style-002",
        "gender-neutral pronouns chairman freshman": "editorial-style-004",
        "plain language reading level short sentences": "voice-tone-002",
    }
    for query, expected in cases.items():
        results = local.retrieve(query, top_k=3)
        assert results, query
        assert results[0].chunk_id == expected, (query, [r.chunk_id for r in results])


def test_local_scores_are_normalized_and_sorted(local):
    results = local.retrieve("university name UIC abbreviation", top_k=10)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert all(0.0 < s <= 1.0 for s in scores)
    assert scores[0] < 1.0  # upper-bound normalization does not saturate


def test_local_result_fields_are_populated(local):
    top = local.retrieve("Sept. a.m. p.m. dates", top_k=1)[0]
    assert isinstance(top, GuidelineChunk) and Guideline is GuidelineChunk
    assert top.chunk_id == "editorial-style-001"
    assert top.source_id == "editorial-style"
    assert top.source_title == "Editorial and style guide"
    assert top.source_url.startswith("https://brand.uic.edu/")
    assert top.category == "editorial"
    assert top.section == "Dates and times"
    assert top.text.startswith("# Editorial and style guide — Dates and times")
    assert set(top.to_dict()) == {"chunk_id", "text", "score", "source_id", "source_title", "source_url",
                                  "category", "section"}


def test_category_filter(local):
    results = local.retrieve("university name tone audience students", top_k=10, category="audience")
    assert results and all(r.category == "audience" for r in results)
    unfiltered = {r.category for r in local.retrieve("university name tone audience students", top_k=10)}
    assert len(unfiltered) > 1


def test_no_match_returns_empty(local):
    assert local.retrieve("xylophone zeppelin", top_k=5) == []


def test_retrieval_is_logged_with_latency(local, log_records):
    local.retrieve("university name", top_k=2)
    rec = next(r for r in log_records if getattr(r, "event", None) == "rag_retrieve")
    assert rec.backend == "local" and rec.result_count >= 1 and rec.latency_ms >= 0


# --- validation ---------------------------------------------------------------------------


@pytest.mark.parametrize("kwargs", [
    {"query": ""}, {"query": "   "}, {"query": "x" * 1001}, {"query": 42},
    {"query": "ok", "top_k": 0}, {"query": "ok", "top_k": 21}, {"query": "ok", "top_k": True},
    {"query": "ok", "top_k": "5"}, {"query": "ok", "category": "voice"}, {"query": "ok", "category": "unknown"},
])
def test_retrieve_validation(local, kwargs):
    with pytest.raises(ValueError):
        local.retrieve(**kwargs)


def test_retrieve_accepts_limits(local):
    local.retrieve("x" * 1000, top_k=20)
    for cat in CATEGORIES:
        local.retrieve("guidelines", top_k=1, category=cat)


@pytest.mark.parametrize("kwargs", [
    {"text": ""}, {"text": "a" * (MAX_TEXT_CHARS + 1)}, {"text": "ok draft", "top_k": 0},
    {"text": "ok draft", "rulesets": "brand"}, {"text": "ok draft", "rulesets": [1]},
    {"text": "ok draft", "audience": 5},
])
def test_retrieve_for_text_validation(local, kwargs):
    with pytest.raises(ValueError):
        local.retrieve_for_text(**kwargs)


def test_retrieve_for_text_accepts_long_text(local):
    long_draft = ("UIC students should click here for info. " * 2000)[:MAX_TEXT_CHARS]
    assert local.retrieve_for_text(long_draft, top_k=5)


def test_constructor_validation():
    with pytest.raises(ValueError):
        RAGService("elasticsearch", guidelines_dir=FIXTURES)
    with pytest.raises(RAGServiceError):
        RAGService("bedrock", guidelines_dir=FIXTURES)  # no KB id configured


# --- retrieve_for_text ----------------------------------------------------------------------

DRAFT = ("Join us! The University of Illinois at Chicago invites all freshmen to the Welcome Week BBQ on "
         "Sept. 5th at 12 p.m. Click here to RSVP. Each student, he or she, should bring a photo ID.")


def test_ruleset_category_mapping():
    f = RAGService.categories_for_rulesets
    assert f(["brand"]) == ["name", "editorial"]
    assert f(["accessibility"]) == ["editorial"]
    assert f(["content"]) == ["audience", "editorial"]
    assert f(["reading_level"]) == ["tone", "audience"]
    assert f(["audience_tone"]) == ["tone", "audience"]
    assert f(["brand", "audience_tone"]) == list(CATEGORIES)
    assert f(None) == f([]) == f(["something-else"]) == list(CATEGORIES)


def test_retrieve_for_text_respects_ruleset_categories(local):
    results = local.retrieve_for_text(DRAFT, rulesets=["accessibility"], top_k=10)
    assert results and {r.category for r in results} == {"editorial"}
    ids = [r.chunk_id for r in results]
    assert "editorial-style-003" in ids  # link text / alt text
    assert "editorial-style-004" in ids  # "he or she", "freshmen"

    results = local.retrieve_for_text(DRAFT, rulesets=["reading_level"], top_k=10)
    assert results and {r.category for r in results} <= {"tone", "audience"}


def test_retrieve_for_text_dedupes_and_limits(local):
    results = local.retrieve_for_text(DRAFT, audience="Students", channel="Email",
                                      rulesets=["brand", "accessibility", "reading_level"], top_k=6)
    ids = [r.chunk_id for r in results]
    assert len(ids) == len(set(ids)) == 6
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)
    assert "name-boilerplate-001" in ids


def test_retrieve_for_text_keeps_max_score_per_chunk(local):
    low = GuidelineChunk("c1", "t", 0.2, "s", "S", "u", "editorial", None)
    high = GuidelineChunk("c1", "t", 0.9, "s", "S", "u", "editorial", None)
    other = GuidelineChunk("c2", "t", 0.5, "s", "S", "u", "tone", None)
    seq = iter([([low, other], "local"), ([high], "local")])
    with mock.patch.object(local, "build_queries", return_value=[("q1", "editorial"), ("q2", "tone")]), \
            mock.patch.object(local, "_search", side_effect=lambda *a: next(seq)):
        results = local.retrieve_for_text("some draft text", top_k=5)
    assert [(r.chunk_id, r.score) for r in results] == [("c1", 0.9), ("c2", 0.5)]


def test_build_queries_includes_audience_channel_and_ruleset_queries(local):
    pairs = local.build_queries(DRAFT, audience="Faculty", channel="Website", rulesets=["brand", "accessibility"])
    queries = [q for q, _ in pairs]
    assert any("Faculty" in q and "faculty" in q for q in queries)
    assert any(q.startswith("Website") for q in queries)
    assert ("university name usage UIC University of Illinois Chicago", "name") in pairs
    assert ("accessibility alt text descriptive link text", "editorial") in pairs
    assert all(cat in ("name", "editorial") for _, cat in pairs)
    assert len(pairs) == len(set((q.lower(), c) for q, c in pairs))
    assert len(pairs) <= rag_service.MAX_SUBQUERIES


# --- retrieve_guidelines (SPEC 1 interface) ----------------------------------------------------


@pytest.mark.parametrize("audience,expected", [
    ("Students", "brand-strategy-001"), ("Faculty", "brand-strategy-002"), ("Staff", "brand-strategy-002"),
])
def test_retrieve_guidelines_includes_best_audience_chunk(local, audience, expected):
    results = local.retrieve_guidelines("how should we describe UIC", audience=audience, top_k=3)
    ids = [r.chunk_id for r in results]
    assert expected in ids
    assert len(ids) == len(set(ids)) <= 3
    assert len({r.category for r in results}) > 1  # searched across all categories


def test_retrieve_guidelines_audience_chunk_survives_small_top_k(local):
    results = local.retrieve_guidelines("university name abbreviation", audience="Students", top_k=1)
    assert [r.category for r in results] == ["audience"]
    results = local.retrieve_guidelines("university name abbreviation", audience="Students", top_k=2)
    assert {r.chunk_id for r in results} == {"name-boilerplate-001", "brand-strategy-001"}


def test_retrieve_guidelines_without_audience_matches_retrieve(local):
    assert local.retrieve_guidelines("academic titles", top_k=3) == local.retrieve("academic titles", top_k=3)


def test_retrieve_guidelines_validation(local):
    with pytest.raises(ValueError):
        local.retrieve_guidelines("", audience="Students")
    with pytest.raises(ValueError):
        local.retrieve_guidelines("ok", top_k=0)
    with pytest.raises(ValueError):
        local.retrieve_guidelines("ok", audience=["Students"])


# --- missing manifest ---------------------------------------------------------------------------


def test_missing_manifest_is_degraded_not_fatal(tmp_path, log_records):
    svc = RAGService("local", guidelines_dir=tmp_path / "nope")
    assert svc.retrieve("university name") == []
    assert svc.retrieve_for_text(DRAFT) == []
    assert svc.list_sources() == []
    health = svc.health()
    assert health["status"] == "degraded" and health["backend"] == "local"
    assert health["chunk_count"] == 0 and "manifest not found" in health["reason"]
    assert "rag_manifest_missing" in _events(log_records)
    assert any(r.levelno == logging.WARNING for r in log_records)


def test_empty_manifest_is_degraded(tmp_path):
    (tmp_path / "guidelines_manifest.json").write_text(json.dumps({"sources": [], "chunks": []}))
    health = RAGService("local", guidelines_dir=tmp_path).health()
    assert health["status"] == "degraded" and health["reason"]


def test_health_and_sources_ok(local):
    health = local.health()
    assert health == {"status": "ok", "backend": "local", "kb_id": None, "chunk_count": 10, "reason": None,
                      "last_backend": "local"}
    sources = local.list_sources()
    assert {s["source_id"] for s in sources} == {"name-boilerplate", "voice-tone", "brand-strategy",
                                                 "editorial-style"}
    assert {s["category"] for s in sources} == set(CATEGORIES)


def test_chunk_text_loaded_from_file_when_missing_in_manifest(tmp_path):
    manifest = json.loads((FIXTURES / "guidelines_manifest.json").read_text())
    for c in manifest["chunks"]:
        c.pop("text")
    (tmp_path / "chunks").mkdir()
    for f in (FIXTURES / "chunks").glob("*.md"):
        (tmp_path / "chunks" / f.name).write_text(f.read_text())
    (tmp_path / "guidelines_manifest.json").write_text(json.dumps(manifest))
    svc = RAGService("local", guidelines_dir=tmp_path)
    assert svc.retrieve("university name", top_k=1)[0].chunk_id == "name-boilerplate-001"


# --- bedrock backend ------------------------------------------------------------------------------


def test_bedrock_maps_results_and_sends_filter():
    svc, stub = _bedrock_service()
    stub.add_response("retrieve", {"retrievalResults": [
        _retrieval_result("name-boilerplate-001", "name-boilerplate", "name", "Name and boilerplate",
                          "University name", 0.82),
        _retrieval_result("name-boilerplate-002", "name-boilerplate", "name", "Name and boilerplate",
                          "Boilerplate", 0.61),
    ]}, _expected("how to write the university name", 2, "name"))
    with stub:
        results = svc.retrieve("how to write the university name", top_k=2, category="name")
        stub.assert_no_pending_responses()
    assert svc.backend == "bedrock"
    first = results[0]
    assert first.chunk_id == "name-boilerplate-001"
    assert first.score == 0.82
    assert first.source_id == "name-boilerplate"
    assert first.source_title == "Name and boilerplate"
    assert first.source_url == "https://brand.uic.edu/name-boilerplate/"
    assert first.category == "name"
    assert first.section == "University name"
    assert first.text.startswith("# Name and boilerplate")
    assert [r.chunk_id for r in results] == ["name-boilerplate-001", "name-boilerplate-002"]


def test_bedrock_no_filter_without_category_and_metadata_fallbacks():
    svc, stub = _bedrock_service()
    result = {"content": {"text": "Some tone guidance"}, "score": 0.5,
              "location": {"type": "S3", "s3Location": {"uri": "s3://b/chunks/voice-tone-007.md"}},
              "metadata": {"source_id": "voice-tone"}}
    stub.add_response("retrieve", {"retrievalResults": [result]}, _expected("tone", 5))
    with stub:
        (chunk,) = svc.retrieve("tone")
    assert chunk.chunk_id == "voice-tone-007"
    assert chunk.category == "tone"
    assert chunk.source_title == "Voice and tone"
    assert chunk.source_url == "https://brand.uic.edu/messaging/voice-and-tone/"
    assert chunk.section is None


def test_bedrock_retries_throttling_then_succeeds(log_records):
    svc, stub = _bedrock_service()
    sleeps: list[float] = []
    svc._sleep = sleeps.append
    stub.add_client_error("retrieve", service_error_code="ThrottlingException", http_status_code=429)
    stub.add_client_error("retrieve", service_error_code="ServiceUnavailableException", http_status_code=503)
    stub.add_response("retrieve", {"retrievalResults": [
        _retrieval_result("editorial-style-001", "editorial-style", "editorial", "Editorial and style guide",
                          "Dates and times", 0.7)]})
    with stub:
        results = svc.retrieve("dates")
        stub.assert_no_pending_responses()
    assert [r.chunk_id for r in results] == ["editorial-style-001"]
    assert len(sleeps) == 2 and all(0 <= s <= rag_service.BACKOFF_CAP_S for s in sleeps)
    assert _events(log_records).count("rag_bedrock_retry") == 2


def test_bedrock_gives_up_after_max_attempts():
    svc, stub = _bedrock_service()
    for _ in range(rag_service.MAX_ATTEMPTS):
        stub.add_client_error("retrieve", service_error_code="InternalServerException", http_status_code=500)
    with stub, pytest.raises(RAGServiceError, match="after 3 attempts"):
        svc.retrieve("dates")
    stub.assert_no_pending_responses()


@pytest.mark.parametrize("code,status", [("AccessDeniedException", 403), ("ResourceNotFoundException", 404),
                                         ("ValidationException", 400)])
def test_bedrock_non_retryable_error_raises_immediately(code, status):
    svc, stub = _bedrock_service()
    sleeps: list[float] = []
    svc._sleep = sleeps.append
    stub.add_client_error("retrieve", service_error_code=code, http_status_code=status)
    stub.add_response("retrieve", {"retrievalResults": []})  # must NOT be consumed
    with stub, pytest.raises(RAGServiceError, match=code):
        svc.retrieve("dates")
    assert sleeps == []
    assert len(stub._queue) == 1


def test_bedrock_client_is_created_lazily():
    svc = RAGService("bedrock", kb_id=KB_ID, region="us-east-1", guidelines_dir=FIXTURES)
    assert svc._bedrock._client is None
    with mock.patch("boto3.client") as factory:
        _ = svc._bedrock.client
        _ = svc._bedrock.client
    factory.assert_called_once()
    args, kwargs = factory.call_args
    assert args[0] == "bedrock-agent-runtime" and kwargs["region_name"] == "us-east-1"
    assert kwargs["config"].retries["mode"] == "adaptive"


# --- auto mode ---------------------------------------------------------------------------------------


def test_auto_mode_picks_backend_from_config(monkeypatch):
    assert RAGService(guidelines_dir=FIXTURES).backend == "local"
    monkeypatch.setenv("UIC_KB_ID", KB_ID)
    reset_settings()
    svc = RAGService(guidelines_dir=FIXTURES)
    assert svc.mode == "auto" and svc.backend == "bedrock" and svc.kb_id == KB_ID


def test_auto_mode_falls_back_to_local_on_bedrock_failure(log_records):
    svc = RAGService("auto", kb_id=KB_ID, region="us-east-1", guidelines_dir=FIXTURES)
    svc._sleep = lambda _s: None
    client = mock.MagicMock()
    client.retrieve.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "nope"},
         "ResponseMetadata": {"HTTPStatusCode": 403}}, "Retrieve")
    svc._bedrock._client = client

    assert svc.backend == "bedrock"
    results = svc.retrieve("how to write the university name", top_k=2)
    assert results and results[0].chunk_id == "name-boilerplate-001"
    assert svc.backend == "local" and svc.last_backend == "local"
    assert "rag_fallback" in _events(log_records)
    fallback = next(r for r in log_records if getattr(r, "event", None) == "rag_fallback")
    assert fallback.levelno == logging.WARNING

    health = svc.health()
    assert health["status"] == "degraded" and "fallback" in health["reason"]
    assert health["backend"] == "bedrock"

    # Circuit breaker: subsequent calls go straight to local without hitting Bedrock.
    svc.retrieve_for_text(DRAFT, rulesets=["brand"])
    assert client.retrieve.call_count == 1

    # After the cooldown Bedrock is tried again and `backend` flips back on success.
    svc._bedrock_down_until = 0.0
    client.retrieve.side_effect = None
    client.retrieve.return_value = {"retrievalResults": [
        _retrieval_result("voice-tone-001", "voice-tone", "tone", "Voice and tone", "Brand attributes", 0.9)]}
    assert svc.retrieve("tone")[0].chunk_id == "voice-tone-001"
    assert svc.backend == "bedrock"


def test_explicit_bedrock_mode_does_not_fall_back():
    svc, stub = _bedrock_service("bedrock")
    stub.add_client_error("retrieve", service_error_code="AccessDeniedException", http_status_code=403)
    with stub, pytest.raises(RAGServiceError):
        svc.retrieve("university name")
    assert svc.health()["status"] == "ok"


def test_auto_bedrock_without_local_fallback_is_degraded(tmp_path):
    svc = RAGService("auto", kb_id=KB_ID, region="us-east-1", guidelines_dir=tmp_path)
    health = svc.health()
    assert health["status"] == "degraded" and "no local fallback" in health["reason"]


def test_bedrock_retrieve_for_text_runs_queries_and_dedupes():
    svc = RAGService("bedrock", kb_id=KB_ID, region="us-east-1", guidelines_dir=FIXTURES)
    client = mock.MagicMock()

    def fake_retrieve(**kwargs):
        cat = kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"]["equals"]["value"]
        sid = {"name": "name-boilerplate", "editorial": "editorial-style"}[cat]
        return {"retrievalResults": [_retrieval_result(f"{sid}-001", sid, cat, sid, "S", 0.5),
                                     _retrieval_result(f"{sid}-002", sid, cat, sid, "S", 0.4)]}

    client.retrieve.side_effect = fake_retrieve
    svc._bedrock._client = client
    results = svc.retrieve_for_text(DRAFT, rulesets=["brand"], top_k=8)
    assert client.retrieve.call_count > 2
    assert sorted(r.chunk_id for r in results) == ["editorial-style-001", "editorial-style-002",
                                                   "name-boilerplate-001", "name-boilerplate-002"]
    assert svc.backend == "bedrock"


# --- singleton -------------------------------------------------------------------------------------


def test_get_rag_service_singleton(monkeypatch):
    monkeypatch.setenv("UIC_GUIDELINES_DIR", str(FIXTURES))
    reset_settings()
    a = get_rag_service()
    assert a is get_rag_service()
    assert a.backend == "local" and a.health()["chunk_count"] == 10
    reset_rag_service()
    assert get_rag_service() is not a


# --- QA regression tests ---------------------------------------------------------------------------


@pytest.mark.parametrize("draft", ["a" * MAX_TEXT_CHARS, "1" * MAX_TEXT_CHARS, "a." * (MAX_TEXT_CHARS // 2),
                                   "https://example.com/" + "x" * (MAX_TEXT_CHARS - 20)],
                         ids=["letters", "digits", "dotted", "url"])
def test_retrieve_for_text_pathological_40k_input_is_fast(local, draft):
    """Long runs without whitespace used to trigger O(n^2) regex backtracking (~5 s)."""
    import time

    t0 = time.perf_counter()
    local.retrieve_for_text(draft, top_k=20)
    assert time.perf_counter() - t0 < 1.0


def test_email_and_phone_topic_rule_still_matches(local):
    pairs = local.build_queries("Questions? Email jane.doe+news@uic.edu or call (312) 555-0100.")
    assert any(q == "phone numbers email addresses format" for q, _ in pairs)
    pairs = local.build_queries("Questions? Write to jane.doe@uic.edu today please.")
    assert any(q == "phone numbers email addresses format" for q, _ in pairs)


def test_build_queries_keeps_audience_and_channel_with_all_rulesets(local):
    """With every ruleset selected the sub-query budget used to drop the audience/channel queries."""
    rulesets = ["brand", "accessibility", "content", "reading_level", "audience_tone"]
    pairs = local.build_queries(DRAFT + " Dr. Smith, Professor of Chemistry, will speak.",
                                audience="Students", channel="Email", rulesets=rulesets)
    queries = [q for q, _ in pairs]
    assert len(pairs) <= rag_service.MAX_SUBQUERIES
    assert any(q.startswith("writing for Students") for q in queries)
    assert any(q.startswith("Email") for q in queries)
    # every requested ruleset still contributes at least its first (most important) query
    for rs in rulesets:
        assert rag_service._RULESET_QUERIES[rs][0][0] in queries, rs


def test_bm25_unknown_query_terms_lower_the_score():
    """Query terms absent from the corpus count toward the normalization bound (no inflated scores)."""
    idx = rag_service.BM25Index([["comma", "seri"], ["colon"], ["dash"]])
    (only_known,) = idx.score(["comma"])
    (with_unknown,) = idx.score(["comma", "oxford"])
    assert 0.0 < with_unknown[1] < only_known[1] <= 1.0
    assert idx.score(["oxford"]) == []  # only unknown terms -> nothing
    assert rag_service.BM25Index([]).score(["comma"]) == []  # empty corpus
    assert idx.score([]) == []


def test_bm25_scores_bounded_for_extreme_lengths():
    docs = [["x"] * 500, ["x"], ["y"] * 3, []]
    for q in (["x"], ["x", "y"], ["y"]):
        for _, s in rag_service.BM25Index(docs).score(q):
            assert 0.0 < s <= 1.0 and s == s  # no NaN


def test_backend_attribute_is_per_thread():
    """Under concurrent requests each thread must see the backend that served *its* call."""
    import threading

    svc = RAGService("auto", kb_id=KB_ID, region="us-east-1", guidelines_dir=FIXTURES)
    barrier = threading.Barrier(2)
    seen: dict[str, str] = {}

    def fake_search(query, top_k, category):
        return [], ("local" if query == "fallback" else "bedrock")

    def worker(query):
        svc.retrieve(query)
        barrier.wait()  # both calls finished before either reads `backend`
        seen[query] = svc.backend

    with mock.patch.object(svc, "_search", side_effect=fake_search):
        threads = [threading.Thread(target=worker, args=(q,)) for q in ("fallback", "ok")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert seen == {"fallback": "local", "ok": "bedrock"}


def test_mixed_backend_results_are_rescored_locally():
    """If Bedrock fails mid-request in auto mode, all sub-queries are served by local BM25 so
    scores from the two backends (cosine vs BM25) are never mixed in one ranking."""
    svc = RAGService("auto", kb_id=KB_ID, region="us-east-1", guidelines_dir=FIXTURES)
    svc._sleep = lambda _s: None
    calls = {"n": 0}

    def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"retrievalResults": [_retrieval_result("bedrock-only-001", "voice-tone", "tone", "Voice and tone",
                                                           "X", 0.99)]}
        raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"},
                           "ResponseMetadata": {"HTTPStatusCode": 403}}, "Retrieve")

    client = mock.MagicMock()
    client.retrieve.side_effect = flaky
    svc._bedrock._client = client
    results = svc.retrieve_guidelines("university name", audience="Students", top_k=3)
    assert svc.backend == "local"
    assert "bedrock-only-001" not in [r.chunk_id for r in results]
    assert results == RAGService("local", guidelines_dir=FIXTURES).retrieve_guidelines(
        "university name", audience="Students", top_k=3)


def test_manifest_reloaded_after_scraper_rerun(tmp_path, monkeypatch):
    import os

    manifest = json.loads((FIXTURES / "guidelines_manifest.json").read_text())
    path = tmp_path / "guidelines_manifest.json"
    path.write_text(json.dumps(manifest))
    svc = RAGService("local", guidelines_dir=tmp_path)
    assert svc.health()["chunk_count"] == 10

    manifest["chunks"] = manifest["chunks"][:4]
    path.write_text(json.dumps(manifest))
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))
    assert svc.health()["chunk_count"] == 10  # not re-checked before MANIFEST_RETRY_S
    clock = [rag_service.time.monotonic() + rag_service.MANIFEST_RETRY_S + 1]
    monkeypatch.setattr(rag_service.time, "monotonic", lambda: clock[0])
    assert svc.health()["chunk_count"] == 4

    # A broken rewrite keeps serving the last good index.
    path.write_text("{not json")
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000_000))
    clock[0] += rag_service.MANIFEST_RETRY_S + 1
    assert svc.health()["chunk_count"] == 4
    assert svc.retrieve("university name", top_k=1)


@pytest.mark.parametrize("content", ["[]", '{"chunks": ["oops"]}', '{"chunks": 5}', '"text"'])
def test_malformed_manifest_shape_is_degraded_not_crash(tmp_path, content):
    (tmp_path / "guidelines_manifest.json").write_text(content)
    svc = RAGService("local", guidelines_dir=tmp_path)
    assert svc.retrieve("university name") == []
    assert svc.health()["status"] == "degraded"


def test_audience_and_channel_over_limit_are_rejected(local):
    with pytest.raises(ValueError):
        local.retrieve_guidelines("ok", audience="x" * 201)
    with pytest.raises(ValueError):
        local.retrieve_for_text("ok draft", audience="x" * 201)
    with pytest.raises(ValueError):
        local.retrieve_for_text("ok draft", channel="x" * 201)
    local.retrieve_for_text("ok draft", audience="x" * 200, channel="y" * 200)
    assert local.retrieve_guidelines("academic titles", audience="   ", top_k=3) == \
        local.retrieve("academic titles", top_k=3)


def test_bedrock_result_without_metadata_derives_source_from_chunk_id():
    (chunk,) = rag_service._BedrockRetriever._map_results([
        {"content": {"text": "body"}, "score": 0.4,
         "location": {"type": "S3", "s3Location": {"uri": "s3://b/chunks/editorial-style-012.md"}}}])
    assert chunk.chunk_id == "editorial-style-012"
    assert chunk.source_id == "editorial-style" and chunk.category == "editorial"
    assert chunk.source_title == "Editorial and style guide"


def test_bedrock_client_does_not_stack_botocore_retries_on_ours():
    """botocore retries x our MAX_ATTEMPTS used to allow 9 HTTP attempts x 10 s read timeout."""
    svc = RAGService("bedrock", kb_id=KB_ID, region="us-east-1", guidelines_dir=FIXTURES)
    with mock.patch("boto3.client") as factory:
        _ = svc._bedrock.client
    cfg = factory.call_args.kwargs["config"]
    assert cfg.retries.get("total_max_attempts") == 1
    worst = rag_service.MAX_ATTEMPTS * (cfg.connect_timeout + cfg.read_timeout)
    assert worst <= 30


def test_bedrock_retry_respects_time_budget(monkeypatch):
    from botocore.exceptions import ReadTimeoutError

    svc = RAGService("bedrock", kb_id=KB_ID, region="us-east-1", guidelines_dir=FIXTURES)
    clock = [1000.0]
    monkeypatch.setattr(rag_service.time, "monotonic", lambda: clock[0])
    svc._sleep = lambda s: clock.__setitem__(0, clock[0] + s)
    client = mock.MagicMock()

    def slow_timeout(**_kw):
        clock[0] += rag_service.RETRY_BUDGET_S  # one attempt eats the whole budget
        raise ReadTimeoutError(endpoint_url="https://bedrock")

    client.retrieve.side_effect = slow_timeout
    svc._bedrock._client = client
    with pytest.raises(RAGServiceError):
        svc.retrieve("dates")
    assert client.retrieve.call_count == 1


def test_auto_mode_stops_retrying_once_breaker_is_open():
    svc = RAGService("auto", kb_id=KB_ID, region="us-east-1", guidelines_dir=FIXTURES)
    client = mock.MagicMock()

    def throttled(**_kw):
        svc._bedrock_down_until = rag_service.time.monotonic() + 30  # another request tripped it
        raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow"},
                           "ResponseMetadata": {"HTTPStatusCode": 429}}, "Retrieve")

    client.retrieve.side_effect = throttled
    svc._bedrock._client = client
    svc._sleep = lambda _s: None
    assert svc.retrieve("university name", top_k=1)[0].chunk_id == "name-boilerplate-001"
    assert client.retrieve.call_count == 1 and svc.backend == "local"


def test_explicit_bedrock_retrieve_for_text_cancels_queued_subqueries_on_failure():
    svc = RAGService("bedrock", kb_id=KB_ID, region="us-east-1", guidelines_dir=FIXTURES)
    client = mock.MagicMock()
    client.retrieve.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "no"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
        "Retrieve")
    svc._bedrock._client = client
    pairs = svc.build_queries(DRAFT)
    assert len(pairs) > rag_service.BEDROCK_PARALLELISM * 2
    with pytest.raises(RAGServiceError):
        svc.retrieve_for_text(DRAFT)
    assert client.retrieve.call_count <= rag_service.BEDROCK_PARALLELISM


@pytest.mark.parametrize("a,b", [("name", "named"), ("case", "cases"), ("date", "dated"), ("live", "lived"),
                                 ("rule", "rules"), ("title", "titles"), ("capitalize", "capitalization")])
def test_stem_maps_inflections_of_short_e_words_together(a, b):
    assert stem(a) == stem(b)
