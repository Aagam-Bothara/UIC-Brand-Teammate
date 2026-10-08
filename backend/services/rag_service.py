"""Retrieval over the UIC brand guidelines (Workstream 1, Task 1.5).

Two interchangeable backends behind one interface (see docs/API_CONTRACT.md):

* ``bedrock`` - Amazon Bedrock Knowledge Base via ``bedrock-agent-runtime.retrieve``.
  Category filtering uses the ``category`` metadata attribute from each chunk's
  ``.metadata.json`` sidecar.
* ``local``   - pure-Python BM25 over ``data/guidelines/guidelines_manifest.json``.
  Needs no AWS access; used for development, tests and as the fallback.

``auto`` (the default) picks bedrock when a Knowledge Base id is configured and
otherwise local. In auto mode a Bedrock failure falls back to local for that call
(and opens a short circuit breaker so a Bedrock outage does not add retry latency
to every subsequent call). An explicit ``bedrock`` backend raises
:class:`RAGServiceError` instead.

The FastAPI layer should obtain the service through :func:`get_rag_service`.
"""

from __future__ import annotations

import json
import math
import random
import re
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from backend.config import get_settings
from backend.logging_utils import get_logger

logger = get_logger(__name__)

# --- contract constants ---------------------------------------------------------

CATEGORIES: tuple[str, ...] = ("name", "tone", "audience", "editorial")

RULESET_CATEGORIES: dict[str, tuple[str, ...]] = {
    "brand": ("name", "editorial"),
    "accessibility": ("editorial",),
    "content": ("editorial", "audience"),
    "reading_level": ("tone", "audience"),
    "audience_tone": ("tone", "audience"),
}

# SPEC 1 audiences / channels, with vocabulary used to expand query hints.
AUDIENCE_HINTS: dict[str, str] = {
    "students": "students prospective current undergraduate graduate",
    "faculty": "faculty researchers scholars academic colleagues",
    "staff": "staff employees colleagues campus community",
}

# Fallback metadata for when a Bedrock result lacks sidecar attributes.
SOURCE_DEFAULTS: dict[str, dict[str, str]] = {
    "name-boilerplate": {"category": "name", "title": "Name and boilerplate",
                         "url": "https://brand.uic.edu/messaging/name-and-boilerplate/"},
    "voice-tone": {"category": "tone", "title": "Voice and tone",
                   "url": "https://brand.uic.edu/messaging/voice-and-tone/"},
    "brand-strategy": {"category": "audience", "title": "Brand strategy",
                       "url": "https://brand.uic.edu/messaging/brand-strategy/"},
    "editorial-style": {"category": "editorial", "title": "Editorial and style guide",
                        "url": "https://brand.uic.edu/messaging/editorial-and-style-guide/"},
}

MANIFEST_NAME = "guidelines_manifest.json"

MAX_QUERY_CHARS = 1000
MAX_TEXT_CHARS = 40000  # ~5,000 words (SPEC FR-1)
MIN_TOP_K, MAX_TOP_K = 1, 20
MAX_HINT_CHARS = 200  # audience / channel

VALID_BACKENDS = ("auto", "bedrock", "local")

# Bedrock retry policy (on top of botocore's adaptive retry mode).
MAX_ATTEMPTS = 3
BACKOFF_BASE_S = 0.25
BACKOFF_CAP_S = 4.0
# No retry is started once this much time has passed since the first attempt (keeps one call
# well inside the API Gateway 29 s limit / NFR-1 10 s analysis budget).
RETRY_BUDGET_S = 6.0
BEDROCK_CONNECT_TIMEOUT_S = 3
BEDROCK_READ_TIMEOUT_S = 6
RETRYABLE_ERROR_CODES = frozenset({
    "ThrottlingException", "Throttling", "TooManyRequestsException",
    "ServiceUnavailableException", "ServiceUnavailable", "ServiceQuotaExceededException",
    "InternalServerException", "InternalServerError", "InternalFailure",
    "BadGatewayException", "DependencyFailedException", "ModelNotReadyException",
    "RequestTimeout", "RequestTimeoutException",
})
NON_RETRYABLE_ERROR_CODES = frozenset({
    "AccessDeniedException", "AccessDenied", "ResourceNotFoundException",
    "ValidationException", "UnrecognizedClientException", "ExpiredTokenException",
})

# Auto mode: after a Bedrock failure, go straight to local for this long.
BEDROCK_COOLDOWN_S = 30.0
# How often to re-check for a missing manifest (the scraper may produce it later).
MANIFEST_RETRY_S = 30.0

# retrieve_for_text budget
MAX_SUBQUERIES = 24
MAX_SENTENCE_QUERY_CHARS = 300
BEDROCK_PARALLELISM = 8


class RAGServiceError(Exception):
    """The retrieval backend failed (after retries) or is misconfigured."""


@dataclass
class GuidelineChunk:
    chunk_id: str
    text: str
    score: float  # higher = more relevant; 0..1
    source_id: str
    source_title: str
    source_url: str
    category: str
    section: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Guideline = GuidelineChunk  # SPEC 1 name for the result type


# --- text processing ---------------------------------------------------------------

STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been before being below
between both but by can could did do does doing down during each few for from further had has have
having he her here hers herself him himself his how i if in into is it its itself just me more most
my myself no nor not now of off on once only or other our ours ourselves out over own same she should
so some such than that the their theirs them themselves then there these they this those through to
too under until up very was we were what when where which while who whom why will with would you your
yours yourself yourselves also may might must shall us via per etc vs e g ie eg let s t re ll ve d m
""".split())

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def stem(word: str) -> str:
    """Very light suffix-stripping stemmer (plural, -ing, -ed, -ly, -ation...).

    Not linguistically exact; only needs to map query and document variants of
    the same word to the same token (capitalize/capitalized/capitalization).
    """
    w = word
    if len(w) <= 3 or w.isdigit():
        return w
    # plurals
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("sses"):
        w = w[:-2]
    elif w.endswith(("ches", "shes", "xes", "zes")) or (w.endswith("ses") and len(w) > 4):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    # derivational
    for suffix, repl, min_len in (("ization", "iz", 8), ("ibility", "ibl", 8), ("ability", "abl", 8),
                                  ("ation", "at", 8), ("ness", "", 6), ("ment", "", 7), ("ful", "", 6)):
        if w.endswith(suffix) and len(w) >= min_len:
            w = w[: -len(suffix)] + repl
            break
    # inflectional
    for suffix, min_len in (("ing", 6), ("ed", 5), ("ly", 6)):
        if w.endswith(suffix) and len(w) >= min_len:
            w = w[: -len(suffix)]
            if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "lsz":
                w = w[:-1]  # running -> run, stopped -> stop
            break
    if w.endswith("e") and len(w) > 3:  # name/named, case/cases, date/dated -> same stem
        w = w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    """Lowercase, split, drop stopwords and 1-char tokens, light-stem."""
    text = text.lower().replace("’", "'").replace("‘", "'")
    out: list[str] = []
    for raw in _TOKEN_RE.findall(text):
        if raw.endswith("'s"):
            raw = raw[:-2]
        raw = raw.replace("'", "")
        if len(raw) < 2 or raw in STOPWORDS:
            continue
        out.append(stem(raw))
    return out


class BM25Index:
    """Okapi BM25 over a fixed list of token lists.

    Scores are normalized to 0..1 by dividing the raw score by its theoretical
    upper bound for the query (``sum(idf(t) * (k1 + 1))`` over the distinct query
    terms), then taking the square root to spread the distribution into a
    cosine-similarity-like range. Query terms that never occur in the corpus count
    toward the bound with the maximum idf (df = 0): otherwise a query whose
    distinctive words are absent ("alt text images" -> only "text" known) would get
    inflated scores. The result is comparable across queries (needed when merging
    sub-query results), rewards query-term coverage, and never saturates.
    """

    def __init__(self, docs: list[list[str]], k1: float = 1.2, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.n = len(docs)
        self.tfs = [Counter(d) for d in docs]
        self.lens = [len(d) for d in docs]
        self.avgdl = (sum(self.lens) / self.n) if self.n else 0.0
        df: Counter[str] = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        self.idf = {t: math.log(1.0 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.unknown_idf = math.log(1.0 + (self.n + 0.5) / 0.5)  # idf of a term with df = 0

    def score(self, query_tokens: list[str], doc_ids: list[int] | None = None) -> list[tuple[int, float]]:
        distinct = list(dict.fromkeys(query_tokens))
        terms = [t for t in distinct if t in self.idf]
        if not terms or not self.n:
            return []
        upper = sum(self.idf.get(t, self.unknown_idf) for t in distinct) * (self.k1 + 1)
        k1, b, avgdl = self.k1, self.b, self.avgdl or 1.0
        results: list[tuple[int, float]] = []
        for i in (range(self.n) if doc_ids is None else doc_ids):
            tf, dl = self.tfs[i], self.lens[i]
            raw = 0.0
            for t in terms:
                f = tf.get(t)
                if f:
                    raw += self.idf[t] * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avgdl))
            if raw > 0:
                results.append((i, min(1.0, math.sqrt(raw / upper))))
        results.sort(key=lambda x: (-x[1], x[0]))
        return results


# --- local backend ---------------------------------------------------------------------


class _Snapshot:
    """One immutable, fully built index. Swapped atomically on (re)load so concurrent
    readers never see chunks from one manifest paired with a BM25 index of another."""

    __slots__ = ("sources", "chunks", "bm25", "by_category")

    def __init__(self, sources: list[dict], chunks: list[dict], bm25: BM25Index | None,
                 by_category: dict[str, list[int]]) -> None:
        self.sources, self.chunks, self.bm25, self.by_category = sources, chunks, bm25, by_category


_EMPTY_SNAPSHOT = _Snapshot([], [], None, {})


class _LocalIndex:
    """Manifest-backed chunk store + BM25 index. Lazy, thread-safe, reloadable.

    A missing manifest is retried at most every ``MANIFEST_RETRY_S``. Once loaded, the
    manifest's mtime/size is re-checked at the same interval and the index rebuilt when
    the scraper has rewritten it; a failed reload keeps serving the last good index.
    """

    def __init__(self, guidelines_dir: Path) -> None:
        self.dir = Path(guidelines_dir)
        self.manifest_path = self.dir / MANIFEST_NAME
        self._lock = threading.Lock()
        self._snap: _Snapshot = _EMPTY_SNAPSHOT
        self._loaded = False
        self._last_attempt = 0.0
        self._signature: tuple[int, int] | None = None
        self.error: str | None = None

    # Read-only views of the current snapshot (kept for callers / tests).
    @property
    def sources(self) -> list[dict]:
        return self._snap.sources

    @property
    def chunks(self) -> list[dict]:
        return self._snap.chunks

    @property
    def bm25(self) -> BM25Index | None:
        return self._snap.bm25

    @property
    def by_category(self) -> dict[str, list[int]]:
        return self._snap.by_category

    def _stat_signature(self) -> tuple[int, int] | None:
        try:
            st = self.manifest_path.stat()
        except OSError:
            return None
        return st.st_mtime_ns, st.st_size

    def ensure_loaded(self) -> bool:
        now = time.monotonic()
        if self._loaded and now - self._last_attempt < MANIFEST_RETRY_S:
            return True
        with self._lock:
            now = time.monotonic()
            if self._last_attempt and now - self._last_attempt < MANIFEST_RETRY_S:
                return self._loaded
            self._last_attempt = now
            signature = self._stat_signature()
            if self._loaded and (signature is None or signature == self._signature):
                return True  # unchanged (or briefly missing while being rewritten): keep serving
            try:
                self._snap = self._load()
                self._signature = signature
                self._loaded = True
                self.error = None
            except FileNotFoundError:
                if not self._loaded:
                    self.error = f"manifest not found: {self.manifest_path}"
                logger.warning("guidelines manifest missing; local RAG is degraded",
                               extra={"event": "rag_manifest_missing", "path": str(self.manifest_path)})
            except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
                if not self._loaded:
                    self.error = f"manifest unreadable: {type(exc).__name__}: {exc}"
                logger.warning("guidelines manifest unreadable; local RAG is degraded"
                               + (" (keeping previous index)" if self._loaded else ""),
                               extra={"event": "rag_manifest_invalid", "path": str(self.manifest_path),
                                      "error": str(exc)})
        return self._loaded

    def _load(self) -> _Snapshot:
        t0 = time.perf_counter()
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"manifest must be a JSON object, got {type(data).__name__}")
        sources = [dict(s) for s in (data.get("sources") or []) if isinstance(s, dict)]
        chunks: list[dict] = []
        for raw in data.get("chunks") or []:
            if not isinstance(raw, dict):
                raise ValueError(f"manifest chunk entries must be objects, got {type(raw).__name__}")
            text = raw.get("text")
            if not text and raw.get("path"):
                p = self.dir / raw["path"]
                text = p.read_text(encoding="utf-8") if p.exists() else ""
            if not text or not raw.get("chunk_id"):
                continue
            sid = raw.get("source_id", "")
            defaults = SOURCE_DEFAULTS.get(sid, {})
            chunks.append({
                "chunk_id": raw["chunk_id"],
                "text": text,
                "source_id": sid,
                "title": raw.get("title") or defaults.get("title", sid),
                "url": raw.get("url") or defaults.get("url", ""),
                "category": raw.get("category") or defaults.get("category", ""),
                "section": raw.get("section") or None,
            })
        # Index title + section (section counted twice as a light field boost) + body.
        docs = [tokenize(f"{c['title']} {c['section'] or ''} {c['section'] or ''} {c['text']}") for c in chunks]
        by_cat: dict[str, list[int]] = {}
        for i, c in enumerate(chunks):
            by_cat.setdefault(c["category"], []).append(i)
        logger.info("guidelines manifest loaded",
                    extra={"event": "rag_manifest_loaded", "path": str(self.manifest_path),
                           "chunk_count": len(chunks), "source_count": len(sources),
                           "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
        return _Snapshot(sources, chunks, BM25Index(docs), by_cat)

    def search(self, query: str, top_k: int, category: str | None) -> list[GuidelineChunk]:
        loaded = self.ensure_loaded()
        snap = self._snap  # one consistent snapshot for the whole search
        if not loaded or snap.bm25 is None:
            logger.warning("local retrieval skipped: no guidelines loaded",
                           extra={"event": "rag_local_unavailable", "error": self.error})
            return []
        doc_ids = None if category is None else snap.by_category.get(category, [])
        hits = snap.bm25.score(tokenize(query), doc_ids)[:top_k]
        out = []
        for i, s in hits:
            c = snap.chunks[i]
            out.append(GuidelineChunk(chunk_id=c["chunk_id"], text=c["text"], score=round(s, 4),
                                      source_id=c["source_id"], source_title=c["title"],
                                      source_url=c["url"], category=c["category"], section=c["section"]))
        return out


# --- bedrock backend ---------------------------------------------------------------------


def _error_code(exc: Exception) -> tuple[str, int | None]:
    resp = getattr(exc, "response", None)
    if isinstance(resp, dict):
        code = resp.get("Error", {}).get("Code", "") or ""
        status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
        return code, status
    return type(exc).__name__, None


def _is_retryable(exc: Exception) -> bool:
    from botocore.exceptions import (ConnectionClosedError, ConnectTimeoutError,
                                     EndpointConnectionError, ReadTimeoutError)

    if isinstance(exc, (EndpointConnectionError, ConnectTimeoutError, ReadTimeoutError, ConnectionClosedError)):
        return True
    code, status = _error_code(exc)
    if code in NON_RETRYABLE_ERROR_CODES:
        return False
    if code in RETRYABLE_ERROR_CODES:
        return True
    return status is not None and (status >= 500 or status == 429)


class _BedrockRetriever:
    def __init__(self, kb_id: str, region: str, sleep: Callable[[float], None] = time.sleep,
                 may_retry: Callable[[], bool] = lambda: True) -> None:
        self.kb_id = kb_id
        self.region = region
        self._client = None
        self._lock = threading.Lock()
        self._sleep = sleep
        self._may_retry = may_retry  # False -> give up now (auto mode: circuit breaker opened)

    @property
    def client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    import boto3
                    from botocore.config import Config

                    # Retries are done by _call_with_retry (jitter, time budget, breaker-aware);
                    # botocore keeps adaptive client-side rate limiting but makes one attempt,
                    # otherwise the two retry layers multiply (3 x 3 attempts x 10 s timeouts).
                    self._client = boto3.client(
                        "bedrock-agent-runtime",
                        region_name=self.region,
                        config=Config(retries={"mode": "adaptive", "total_max_attempts": 1},
                                      connect_timeout=BEDROCK_CONNECT_TIMEOUT_S,
                                      read_timeout=BEDROCK_READ_TIMEOUT_S),
                    )
        return self._client

    def search(self, query: str, top_k: int, category: str | None) -> list[GuidelineChunk]:
        vector_cfg: dict[str, Any] = {"numberOfResults": top_k}
        if category:
            vector_cfg["filter"] = {"equals": {"key": "category", "value": category}}
        kwargs = {
            "knowledgeBaseId": self.kb_id,
            "retrievalQuery": {"text": query},
            "retrievalConfiguration": {"vectorSearchConfiguration": vector_cfg},
        }
        resp = self._call_with_retry(kwargs)
        return self._map_results(resp.get("retrievalResults") or [])

    def _call_with_retry(self, kwargs: dict) -> dict:
        from botocore.exceptions import BotoCoreError, ClientError

        last: Exception | None = None
        started = time.monotonic()
        attempts = 0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempts = attempt
            try:
                return self.client.retrieve(**kwargs)
            except (ClientError, BotoCoreError) as exc:
                last = exc
                code, status = _error_code(exc)
                if not _is_retryable(exc):
                    raise RAGServiceError(f"Bedrock retrieve failed ({code or type(exc).__name__}): {exc}") from exc
                if attempt == MAX_ATTEMPTS:
                    break
                delay = random.uniform(0, min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2 ** attempt))  # full jitter
                if time.monotonic() - started + delay >= RETRY_BUDGET_S or not self._may_retry():
                    break
                logger.warning("bedrock retrieve retrying",
                               extra={"event": "rag_bedrock_retry", "attempt": attempt, "error": code,
                                      "http_status": status, "delay_s": round(delay, 3)})
                self._sleep(delay)
        code, _ = _error_code(last) if last else ("", None)
        raise RAGServiceError(f"Bedrock retrieve failed after {attempts} attempts ({code}): {last}") from last

    @staticmethod
    def _map_results(results: list[dict]) -> list[GuidelineChunk]:
        out: dict[str, GuidelineChunk] = {}
        for r in results:
            text = (r.get("content") or {}).get("text") or ""
            if not text:
                continue
            meta = r.get("metadata") or {}
            uri = ((r.get("location") or {}).get("s3Location") or {}).get("uri") or str(
                meta.get("x-amz-bedrock-kb-source-uri", ""))
            chunk_id = ""
            if uri:
                name = uri.rstrip("/").rsplit("/", 1)[-1]
                chunk_id = name[:-3] if name.endswith(".md") else name
            chunk_id = chunk_id or str(meta.get("x-amz-bedrock-kb-chunk-id") or "") \
                or f"bedrock-{abs(hash(text)) % 10**10}"
            # Sidecar metadata missing (not ingested): "<source_id>-<NNN>" still names the source.
            source_id = str(meta.get("source_id") or "") or (
                chunk_id.rsplit("-", 1)[0] if chunk_id.rsplit("-", 1)[0] in SOURCE_DEFAULTS else "")
            defaults = SOURCE_DEFAULTS.get(source_id, {})
            try:
                score = max(0.0, min(1.0, float(r.get("score") or 0.0)))
            except (TypeError, ValueError):
                score = 0.0
            chunk = GuidelineChunk(
                chunk_id=chunk_id,
                text=text,
                score=round(score, 4),
                source_id=source_id,
                source_title=str(meta.get("title") or defaults.get("title", source_id)),
                source_url=str(meta.get("url") or defaults.get("url") or uri),
                category=str(meta.get("category") or defaults.get("category", "")),
                section=(str(meta["section"]) if meta.get("section") else None),
            )
            # If the KB re-chunked a file, several hits can share a chunk_id: keep the best.
            if chunk_id not in out or out[chunk_id].score < chunk.score:
                out[chunk_id] = chunk
        return sorted(out.values(), key=lambda c: -c.score)


# --- query building for retrieve_for_text ---------------------------------------------------

# (pattern on the draft, guideline query, target categories)
_TOPIC_RULES: list[tuple[re.Pattern, str, tuple[str, ...]]] = [
    (re.compile(r"\bUIC\b|University of Illinois|\bUI Chicago\b|\bU of I\b|\buniversity\b", re.I),
     "university name usage UIC University of Illinois Chicago", ("name", "editorial")),
    (re.compile(r"click here|read more|learn more|\bhere\b|https?://|www\.", re.I),
     "descriptive link text accessibility", ("editorial",)),
    (re.compile(r"\b(image|photo|picture|graphic|video|infographic|chart)s?\b", re.I),
     "alt text images video captions accessibility", ("editorial",)),
    (re.compile(r"\b(Jan|Feb|Mar|Apr|Aug|Sept?|Oct|Nov|Dec)\.?\s+\d|\b(January|February|March|April|May|June|July|"
                r"August|September|October|November|December)\b|\b\d{1,2}(:\d\d)?\s*(a\.?m\.?|p\.?m\.?)", re.I),
     "dates and times style months a.m. p.m.", ("editorial",)),
    (re.compile(r"\d+\s*%|\bpercent\b|\b\d{2,}\b"), "numbers numerals percent style", ("editorial",)),
    (re.compile(r"\b(Dr|Prof)\.|\bprofessor\b|\bchancellor\b|\bdean\b|\bprovost\b|\bpresident\b", re.I),
     "academic titles capitalization", ("editorial",)),
    (re.compile(r"\b(bachelor|master|doctorate|Ph\.?D|B\.?A|B\.?S|M\.?B\.?A)\b", re.I),
     "academic degrees abbreviations", ("editorial",)),
    (re.compile(r"!|\b[A-Z]{4,}\b"), "tone exclamation points all caps", ("tone", "editorial")),
    (re.compile(r"\b(he or she|he/she|s/he|chairman|freshm[ae]n|guys|mankind|manpower|ladies and gentlemen)\b", re.I),
     "inclusive language gender-neutral terms pronouns", ("editorial",)),
    (re.compile(r"\b(disabled|handicapp?ed|wheelchair|blind|deaf|suffers? from|special needs|mental illness)\b", re.I),
     "disability person-first language", ("editorial",)),
    (re.compile(r"\b(minorit(y|ies)|illegal alien|hispanic|latin[oax]|african american|international students?|"
                r"first-generation)\b", re.I),
     "race ethnicity identity terminology", ("editorial",)),
    # Bounded repeats: an unbounded ``[\w.+-]+@`` is O(n^2) on long runs without "@" (5 s on 40k chars).
    (re.compile(r"[\w.+-]{1,64}@[\w-]{1,63}\.\w+|\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}"),
     "phone numbers email addresses format", ("editorial",)),
    (re.compile(r"\b(about uic|boilerplate|research university|public research|chicago's only)\b", re.I),
     "UIC boilerplate description", ("name",)),
]

_RULESET_QUERIES: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "brand": [("university name usage UIC University of Illinois Chicago", ("name",)),
              ("UIC boilerplate description", ("name",)),
              ("capitalization punctuation style", ("editorial",))],
    "accessibility": [("accessibility alt text descriptive link text", ("editorial",)),
                      ("headings plain language accessible formatting", ("editorial",)),
                      ("inclusive language disability", ("editorial",))],
    "content": [("clear concise writing style", ("editorial",)),
                ("key messages for audiences", ("audience",)),
                ("headlines headings", ("editorial",))],
    "reading_level": [("plain language short sentences readability", ("tone",)),
                      ("conversational tone clear simple words", ("tone",)),
                      ("audience reading level", ("audience",))],
    "audience_tone": [("brand attributes voice and tone", ("tone",)),
                      ("key audiences messaging", ("audience",))],
}

_CHANNEL_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"e-?mail|newsletter", re.I), "email subject line clear call to action"),
    (re.compile(r"social|twitter|instagram|facebook|linkedin|tiktok|\bx\b", re.I), "social media posts hashtags"),
    (re.compile(r"web|site|page|online|blog", re.I), "website writing headings scannable link text"),
    (re.compile(r"print|brochure|flyer|poster|magazine", re.I), "print publications"),
    (re.compile(r"press|news|release|media", re.I), "news release style"),
]


def _audience_hint(audience: str) -> str:
    """Expand a SPEC audience (Students/Faculty/Staff) into query vocabulary."""
    key = audience.strip().lower()
    for name, hint in AUDIENCE_HINTS.items():
        if name in key or key.rstrip("s") == name.rstrip("s"):
            return hint
    return audience


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'\u201c])|\n+")


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    return cut[:space] if space > limit // 2 else cut


def _key_terms(text: str, n: int = 12) -> str:
    words = [w for w in re.findall(r"[a-z][a-z'-]{2,}", text.lower()) if w not in STOPWORDS]
    counts = Counter(words)
    first: dict[str, int] = {}
    for i, w in enumerate(words):
        first.setdefault(w, i)
    ranked = sorted(counts, key=lambda w: (-counts[w], first[w]))[:n]
    return " ".join(ranked)


# --- service -----------------------------------------------------------------------------


class RAGService:
    """Guideline retrieval. See module docstring and docs/API_CONTRACT.md."""

    def __init__(self, backend: str | None = None, *, kb_id: str | None = None,
                 region: str | None = None, guidelines_dir: str | Path | None = None) -> None:
        settings = None

        def _settings():
            nonlocal settings
            if settings is None:
                settings = get_settings()
            return settings

        mode = (backend or _settings().rag_backend or "auto").strip().lower()
        if mode not in VALID_BACKENDS:
            raise ValueError(f"backend must be one of {VALID_BACKENDS}, got {backend!r}")
        self.mode = mode

        if kb_id is None and mode != "local":
            kb_id = _settings().kb_id
        self.kb_id: str | None = kb_id or None
        self.region: str = region or _settings().aws_region
        self.guidelines_dir = Path(guidelines_dir) if guidelines_dir is not None else _settings().guidelines_dir

        if mode == "bedrock" and not self.kb_id:
            raise RAGServiceError("backend 'bedrock' requested but no Knowledge Base id is configured "
                                  "(set UIC_KB_ID or /uic-editorial/knowledge_base_id)")

        # configured_backend: what this instance is set up to use (fixed).
        # backend: what actually served the most recent call *made by the current thread*
        # ("local" after an auto-mode fallback). The API reads ``service.backend`` right after a
        # call in the same threadpool thread, so concurrent requests never see each other's value.
        # last_backend: the most recent call in any thread (reported by health()).
        self.configured_backend: str = (
            "bedrock" if (mode == "bedrock" or (mode == "auto" and self.kb_id)) else "local")
        self._thread_state = threading.local()
        self.last_backend: str = self.configured_backend
        self._local = _LocalIndex(self.guidelines_dir)
        self._bedrock = _BedrockRetriever(self.kb_id, self.region) if self.configured_backend == "bedrock" else None
        self._bedrock_down_until = 0.0
        self._sleep = time.sleep  # tests may override; propagated to the bedrock retriever
        if self._bedrock is not None:
            self._bedrock._sleep = lambda s: self._sleep(s)
            # In auto mode, an in-flight call stops retrying once another call opened the breaker.
            self._bedrock._may_retry = lambda: not (self.mode == "auto"
                                                    and time.monotonic() < self._bedrock_down_until)

        logger.info("rag service initialised",
                    extra={"event": "rag_init", "mode": mode, "backend": self.backend,
                           "kb_id": self.kb_id, "region": self.region,
                           "guidelines_dir": str(self.guidelines_dir)})

    # -- validation ------------------------------------------------------------------

    @staticmethod
    def _validate_top_k(top_k: Any) -> int:
        if isinstance(top_k, bool) or not isinstance(top_k, int):
            raise ValueError("top_k must be an integer")
        if not MIN_TOP_K <= top_k <= MAX_TOP_K:
            raise ValueError(f"top_k must be between {MIN_TOP_K} and {MAX_TOP_K}")
        return top_k

    @staticmethod
    def _validate_category(category: Any) -> str | None:
        if category is None:
            return None
        if not isinstance(category, str) or category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        return category

    @staticmethod
    def _validate_text(value: Any, name: str, max_len: int) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if not value.strip():
            raise ValueError(f"{name} must not be empty")
        if len(value) > max_len:
            raise ValueError(f"{name} must be at most {max_len} characters")
        return value.strip()

    @staticmethod
    def _validate_hint(value: Any, name: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(f"{name} must be a string")
        if len(value) > MAX_HINT_CHARS:  # same limit as the HTTP layer (contract: audience max 200)
            raise ValueError(f"{name} must be at most {MAX_HINT_CHARS} characters")
        return " ".join(value.split()) or None

    # -- core retrieval --------------------------------------------------------------

    def retrieve(self, query: str, top_k: int = 5, category: str | None = None) -> list[GuidelineChunk]:
        query = self._validate_text(query, "query", MAX_QUERY_CHARS)
        top_k = self._validate_top_k(top_k)
        category = self._validate_category(category)
        t0 = time.perf_counter()
        results, used = self._search(query, top_k, category)
        self._record_backend({used})
        logger.info("rag retrieve", extra={
            "event": "rag_retrieve", "backend": used, "top_k": top_k, "category": category,
            "query_chars": len(query), "result_count": len(results),
            "top_score": results[0].score if results else None,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
        return results

    @property
    def backend(self) -> str:
        """The backend that served this thread's most recent call (``configured_backend`` before any)."""
        return getattr(self._thread_state, "backend", self.configured_backend)

    def _record_backend(self, used: set[str]) -> str:
        """Set ``backend``/``last_backend`` to what served the call ("local" if any part fell back)."""
        actual = ("local" if "local" in used else "bedrock") if used else self.configured_backend
        self._thread_state.backend = self.last_backend = actual
        return actual

    def _consistent(self, outcomes: list[tuple[list[GuidelineChunk], str]],
                    searches: list[tuple[str, int, str | None]]) -> list[tuple[list[GuidelineChunk], str]]:
        """If Bedrock failed part-way through a multi-query call (auto mode), re-run the sub-queries
        Bedrock did serve on the local index: Bedrock (cosine) and BM25 scores are not comparable,
        so one merged ranking must come from a single backend."""
        if {used for _, used in outcomes} != {"bedrock", "local"}:
            return outcomes
        return [(res, used) if used == "local" else (self._local.search(q, k, c), "local")
                for (res, used), (q, k, c) in zip(outcomes, searches)]

    def _search(self, query: str, top_k: int, category: str | None) -> tuple[list[GuidelineChunk], str]:
        """Dispatch to a backend (no validation). Returns (results, backend actually used)."""
        if self._bedrock is None:
            return self._local.search(query, top_k, category), "local"
        if self.mode == "auto" and time.monotonic() < self._bedrock_down_until:
            return self._local.search(query, top_k, category), "local"
        try:
            return self._bedrock.search(query, top_k, category), "bedrock"
        except Exception as exc:  # noqa: BLE001
            err = exc if isinstance(exc, RAGServiceError) else RAGServiceError(f"Bedrock retrieve failed: {exc}")
            if self.mode != "auto":
                logger.error("bedrock retrieve failed", extra={"event": "rag_bedrock_error", "error": str(exc)})
                if err is exc:
                    raise
                raise err from exc
            self._bedrock_down_until = time.monotonic() + BEDROCK_COOLDOWN_S
            logger.warning("bedrock retrieve failed; falling back to local backend",
                           extra={"event": "rag_fallback", "backend": "local", "error": str(exc),
                                  "cooldown_s": BEDROCK_COOLDOWN_S})
            return self._local.search(query, top_k, category), "local"

    # -- draft-level retrieval -------------------------------------------------------

    @staticmethod
    def categories_for_rulesets(rulesets: list[str] | None) -> list[str]:
        if not rulesets:
            return list(CATEGORIES)
        cats: set[str] = set()
        for rs in rulesets:
            mapped = RULESET_CATEGORIES.get(str(rs).strip().lower())
            if mapped is None:
                return list(CATEGORIES)
            cats.update(mapped)
        return [c for c in CATEGORIES if c in cats]

    def build_queries(self, text: str, audience: str | None = None, channel: str | None = None,
                      rulesets: list[str] | None = None) -> list[tuple[str, str]]:
        """Return de-duplicated ``(query, category)`` pairs for a draft, most specific first."""
        active = self.categories_for_rulesets(rulesets)
        all_active = tuple(active)
        lowered = [str(r).strip().lower() for r in (rulesets or [])]
        # (query, target categories, generic?) - generic queries fall back to every active
        # category when their preferred targets are not active; topical ones are skipped.
        planned: list[tuple[str, tuple[str, ...], bool]] = []

        # 1. guideline topics triggered by patterns in the draft (most specific)
        for pattern, query, cats in _TOPIC_RULES:
            if pattern.search(text):
                planned.append((query, cats, False))
        # 2. the lede (subject line / headline / first sentence)
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(text) if len(s.strip()) > 15]
        if sentences:
            planned.append((_clip(sentences[0], MAX_SENTENCE_QUERY_CHARS), all_active, True))
        # 3. audience / channel hints (explicit request parameters: placed before the ruleset
        #    queries so the MAX_SUBQUERIES budget never silently drops them)
        if audience:
            planned.append((f"writing for {audience} {_audience_hint(audience)} audience messaging tone",
                            ("audience", "tone"), True))
        if channel:
            hint = next((h for p, h in _CHANNEL_HINTS if p.search(channel)), "")
            planned.append((_clip(f"{channel} {hint}".strip(), 200), ("tone", "editorial"), True))
        # 4. ruleset-specific queries (one generic probe per ruleset when none/unknown given),
        #    interleaved round-robin so a truncated budget drops each ruleset's least important
        #    queries rather than whole rulesets.
        per_ruleset = [_RULESET_QUERIES.get(rs, []) for rs in dict.fromkeys(lowered)]
        if not lowered or any(r not in RULESET_CATEGORIES for r in lowered):
            per_ruleset.append([qs[0] for qs in _RULESET_QUERIES.values()])
        for rank in range(max((len(qs) for qs in per_ruleset), default=0)):
            planned.extend((qs[rank][0], qs[rank][1], False) for qs in per_ruleset if rank < len(qs))
        # 5. other sentences that tripped a topic rule, then 6. the draft's key terms
        flagged = [s for s in sentences[1:] if any(p.search(s) for p, _, _ in _TOPIC_RULES)]
        for s in flagged[:2]:
            planned.append((_clip(s, MAX_SENTENCE_QUERY_CHARS), all_active, True))
        terms = _key_terms(text)
        if terms:
            planned.append((terms, all_active, True))

        pairs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for query, cats, generic in planned:
            targets = [c for c in cats if c in active] or (list(active) if generic else [])
            for cat in targets:
                key = (query.lower(), cat)
                if key not in seen and query.strip():
                    seen.add(key)
                    pairs.append((query, cat))
        return pairs[:MAX_SUBQUERIES]

    def retrieve_for_text(self, text: str, audience: str | None = None, channel: str | None = None,
                          rulesets: list[str] | None = None, top_k: int = 8) -> list[GuidelineChunk]:
        text = self._validate_text(text, "text", MAX_TEXT_CHARS)
        top_k = self._validate_top_k(top_k)
        audience = self._validate_hint(audience, "audience")
        channel = self._validate_hint(channel, "channel")
        if rulesets is not None and (not isinstance(rulesets, (list, tuple))
                                     or not all(isinstance(r, str) for r in rulesets)):
            raise ValueError("rulesets must be a list of strings")

        t0 = time.perf_counter()
        pairs = self.build_queries(text, audience, channel, list(rulesets) if rulesets else None)
        per_query_k = max(3, min(top_k, 5))

        # Explicit bedrock mode: the first failure fails the whole request, so sub-queries still
        # queued behind it are skipped instead of each running (and retrying) to completion.
        failures: list[Exception] = []

        def run(pair: tuple[str, str]) -> tuple[list[GuidelineChunk], str]:
            if failures:
                return [], "bedrock"
            try:
                return self._search(pair[0], per_query_k, pair[1])
            except Exception as exc:  # noqa: BLE001 - re-raised below
                failures.append(exc)
                return [], "bedrock"

        if self._bedrock is not None and len(pairs) > 1:
            with ThreadPoolExecutor(max_workers=min(BEDROCK_PARALLELISM, len(pairs))) as pool:
                outcomes = list(pool.map(run, pairs))
        else:
            outcomes = [run(p) for p in pairs]
        if failures:
            raise failures[0]
        outcomes = self._consistent(outcomes, [(q, per_query_k, c) for q, c in pairs])

        best: dict[str, GuidelineChunk] = {}
        backends_used: set[str] = set()
        for results, used in outcomes:
            backends_used.add(used)
            for c in results:
                if c.chunk_id not in best or best[c.chunk_id].score < c.score:
                    best[c.chunk_id] = c

        ranked = sorted(best.values(), key=lambda c: (-c.score, c.chunk_id))
        # Light diversity: make sure each category that produced hits contributes its best
        # chunk (when top_k allows), then fill the rest by score.
        picked: list[GuidelineChunk] = []
        seen_cats: set[str] = set()
        for c in ranked:
            if c.category not in seen_cats and len(picked) < top_k:
                picked.append(c)
                seen_cats.add(c.category)
        for c in ranked:
            if len(picked) >= top_k:
                break
            if c not in picked:
                picked.append(c)
        picked.sort(key=lambda c: (-c.score, c.chunk_id))

        actual = self._record_backend(backends_used)
        logger.info("rag retrieve_for_text", extra={
            "event": "rag_retrieve_for_text", "backend": actual,
            "text_chars": len(text), "rulesets": rulesets, "query_count": len(pairs),
            "candidate_count": len(best), "result_count": len(picked), "top_k": top_k,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
        return picked

    def retrieve_guidelines(self, query: str, audience: str | None = None,
                            top_k: int = 5) -> list[Guideline]:
        """SPEC 1 interface: audience-aware retrieval across all categories.

        Runs the plain query and an audience-hinted variant across all categories,
        plus an ``audience``-category probe for that audience; de-duplicates by
        chunk_id (max score) and returns ``top_k`` by score, guaranteeing that the
        best audience-category chunk is included when one matched.
        """
        query = self._validate_text(query, "query", MAX_QUERY_CHARS)
        top_k = self._validate_top_k(top_k)
        audience = self._validate_hint(audience, "audience")
        t0 = time.perf_counter()

        searches: list[tuple[str, int, str | None]] = [(query, top_k, None)]
        if audience:
            hint = _audience_hint(audience)
            searches.append((_clip(f"{query} for {audience} {hint}", MAX_QUERY_CHARS), top_k, None))
            searches.append((_clip(f"{audience} {hint} audience key messages {query}", MAX_QUERY_CHARS),
                             1, "audience"))
        outcomes = self._consistent([self._search(q, k, c) for q, k, c in searches], searches)

        best: dict[str, GuidelineChunk] = {}
        for results, _ in outcomes:
            for c in results:
                if c.chunk_id not in best or best[c.chunk_id].score < c.score:
                    best[c.chunk_id] = c
        ranked = sorted(best.values(), key=lambda c: (-c.score, c.chunk_id))
        picked = ranked[:top_k]
        if audience and outcomes[-1][0]:
            aud = best[outcomes[-1][0][0].chunk_id]
            if aud not in picked:
                picked = picked[: top_k - 1] + [aud]

        actual = self._record_backend({used for _, used in outcomes})
        logger.info("rag retrieve_guidelines", extra={
            "event": "rag_retrieve_guidelines", "backend": actual, "top_k": top_k,
            "audience": audience, "query_chars": len(query), "result_count": len(picked),
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
        return picked

    # -- metadata ----------------------------------------------------------------------

    def list_sources(self) -> list[dict]:
        if not self._local.ensure_loaded():
            return []
        return [dict(s) for s in self._local.sources]

    def health(self) -> dict:
        """Report whether the configured backend can serve requests.

        ``degraded`` means:
        * local backend: the manifest is missing, unreadable, or has no chunks
          (retrieval returns ``[]``);
        * bedrock in auto mode: Bedrock failed recently and calls are being served by
          the local fallback, or no local fallback is available (manifest missing),
          so a Bedrock outage would leave nothing to serve from.
        ``reason`` explains a degraded status and is ``None`` when ok. Health does not
        call AWS (cheap enough for frequent probes).
        """
        loaded = self._local.ensure_loaded()
        chunk_count = len(self._local.chunks) if loaded else 0
        local_ok = loaded and chunk_count > 0
        local_reason = self._local.error or ("guidelines manifest has no chunks" if loaded else
                                             "guidelines manifest not loaded")
        reason: str | None = None
        if self.configured_backend == "local":
            if not local_ok:
                reason = local_reason
        elif self.mode == "auto":
            if time.monotonic() < self._bedrock_down_until:
                reason = ("bedrock unavailable; serving from local fallback" if local_ok
                          else f"bedrock unavailable and no local fallback ({local_reason})")
            elif not local_ok:
                reason = f"no local fallback available ({local_reason})"
        return {"status": "degraded" if reason else "ok", "backend": self.configured_backend,
                "kb_id": self.kb_id, "chunk_count": chunk_count, "reason": reason,
                "last_backend": self.last_backend}


# --- singleton accessor (FastAPI dependency) ---------------------------------------------

_service: RAGService | None = None
_service_lock = threading.Lock()


def get_rag_service() -> RAGService:
    """Process-wide RAGService built from settings. Use as ``Depends(get_rag_service)``."""
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                _service = RAGService()
    return _service


def reset_rag_service() -> None:
    """Drop the singleton (tests / config reload)."""
    global _service
    with _service_lock:
        _service = None
