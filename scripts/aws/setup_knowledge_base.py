#!/usr/bin/env python3
"""Task 1.4: Bedrock Knowledge Base over the UIC brand guidelines (S3 Vectors store).

Idempotently (safe to re-run):
  1. creates an Amazon S3 Vectors bucket (``uic-editorial-vectors-<account>-<region>``, SSE-S3)
     and a float32 / 1024-dim / cosine index ``uic-editorial-guidelines``. The index marks
     AMAZON_BEDROCK_TEXT and AMAZON_BEDROCK_METADATA as non-filterable, so the chunk text
     does not count against the 2 KB filterable-metadata limit. Our sidecar attributes
     (category, source_id, ...) stay filterable.
  2. re-applies the KB service role policy with the real bucket, prefix and index names,
  3. creates the Knowledge Base ``uic-editorial-guidelines-kb`` (Titan Text Embeddings V2,
     1024 dims, FLOAT32) and an S3 data source on s3://<guidelines bucket>/guidelines/.
     Chunking defaults to NONE because scripts/scrape_guidelines.py already writes one
     ~1,000-char chunk per file with a .metadata.json sidecar.
  4. stores ``/uic-editorial/knowledge_base_id``, ``/uic-editorial/data_source_id`` and
     ``/uic-editorial/vector_bucket``, then narrows the Lambda role's bedrock:Retrieve
     permission to this KB's ARN,
  5. starts an ingestion job and polls it until it finishes, printing the statistics,
  6. optionally runs ``--test-query "..."`` through bedrock-agent-runtime Retrieve.

Why S3 Vectors: the installed botocore supports storageConfiguration type ``S3_VECTORS``
and the ``s3vectors`` service. OpenSearch Serverless bills a minimum number of OCUs around
the clock, even when idle (about $175-350/month), which is not worth it for a few hundred
chunks.

Cost estimate for a hackathon (us-east-1, a few hundred ~1 KB chunks):
  * Titan Text Embeddings V2: $0.00002 per 1K tokens, so roughly $0.001 per full ingestion.
  * S3 Vectors: $0.06/GB-month storage (well under 10 MB here), PUT $0.20/GB, queries
    about $2.50 per million calls plus a tiny per-TB processing fee: cents at most.
  * The Knowledge Base itself has no standing charge. Total: well under $1 for the event.
    (The dominant Bedrock cost is the LLM calls made by the backend, not this script.)

Prerequisites: setup_base.py and setup_s3.py have run (roles and guidelines bucket exist).
Titan Text Embeddings V2 must be usable in the region (Bedrock console, Model access).

Usage:
  python scripts/aws/setup_knowledge_base.py [--region us-east-1] [--profile NAME] [--dry-run]
         [--no-ingest] [--test-query "how do I write the university name"] [--top-k 5]
         [--category editorial]
  python scripts/aws/setup_knowledge_base.py --query-only --test-query "..."
"""

from __future__ import annotations

import argparse
import sys
import time

from botocore.exceptions import ClientError

import aws_common as c

NON_FILTERABLE_METADATA_KEYS = ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
DRY_RUN_KB_ID = "DRYRUNKBID"
DRY_RUN_DS_ID = "DRYRUNDSID"
INGESTION_RUNNING = {"STARTING", "IN_PROGRESS", "STOPPING"}
INGESTION_FAILED = {"FAILED", "STOPPED"}
ROLE_PROPAGATION_HINTS = ("role", "assume", "permission", "not authorized", "access denied")


# --------------------------------------------------------------------------- request builders

def build_vector_index_request(vector_bucket: str, index_name: str,
                               dimensions: int = c.EMBEDDING_DIMENSIONS) -> dict:
    return {
        "vectorBucketName": vector_bucket,
        "indexName": index_name,
        "dataType": "float32",
        "dimension": dimensions,
        "distanceMetric": "cosine",
        "metadataConfiguration": {"nonFilterableMetadataKeys": list(NON_FILTERABLE_METADATA_KEYS)},
    }


def build_knowledge_base_request(*, name: str, role_arn: str, region: str, index_arn: str,
                                 dimensions: int = c.EMBEDDING_DIMENSIONS) -> dict:
    return {
        "name": name,
        "description": "UIC brand guidelines: name and boilerplate, voice and tone, brand strategy, editorial style",
        "roleArn": role_arn,
        "knowledgeBaseConfiguration": {
            "type": "VECTOR",
            "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": c.embedding_model_arn(region),
                "embeddingModelConfiguration": {
                    "bedrockEmbeddingModelConfiguration": {
                        "dimensions": dimensions,
                        "embeddingDataType": "FLOAT32",
                    }
                },
            },
        },
        "storageConfiguration": {
            "type": "S3_VECTORS",
            "s3VectorsConfiguration": {"indexArn": index_arn},
        },
        "tags": dict(c.TAGS),
    }


def build_chunking_configuration(strategy: str = "none", max_tokens: int = 300,
                                 overlap_percentage: int = 20) -> dict:
    if strategy == "none":
        return {"chunkingStrategy": "NONE"}
    if strategy == "fixed":
        return {"chunkingStrategy": "FIXED_SIZE",
                "fixedSizeChunkingConfiguration": {"maxTokens": max_tokens,
                                                   "overlapPercentage": overlap_percentage}}
    raise ValueError(f"unknown chunking strategy {strategy!r} (use 'none' or 'fixed')")


def build_data_source_request(*, kb_id: str, bucket: str, prefix: str, account_id: str,
                              name: str = c.DATA_SOURCE_NAME, chunking: str = "none") -> dict:
    return {
        "knowledgeBaseId": kb_id,
        "name": name,
        "description": f"Guideline chunks in s3://{bucket}/{prefix}",
        "dataSourceConfiguration": {
            "type": "S3",
            "s3Configuration": {
                "bucketArn": f"arn:aws:s3:::{bucket}",
                "inclusionPrefixes": [prefix],
                "bucketOwnerAccountId": account_id,
            },
        },
        "dataDeletionPolicy": "DELETE",
        "vectorIngestionConfiguration": {
            "chunkingConfiguration": build_chunking_configuration(chunking),
        },
    }


def build_retrieve_request(kb_id: str, query: str, top_k: int = 5,
                           category: str | None = None) -> dict:
    search: dict = {"numberOfResults": top_k}
    if category:
        search["filter"] = {"equals": {"key": "category", "value": category}}
    return {
        "knowledgeBaseId": kb_id,
        "retrievalQuery": {"text": query},
        "retrievalConfiguration": {"vectorSearchConfiguration": search},
    }


def format_ingestion_stats(stats: dict | None) -> list[str]:
    stats = stats or {}
    labels = [
        ("numberOfDocumentsScanned", "documents scanned"),
        ("numberOfMetadataDocumentsScanned", "metadata files scanned"),
        ("numberOfNewDocumentsIndexed", "new documents indexed"),
        ("numberOfModifiedDocumentsIndexed", "modified documents indexed"),
        ("numberOfMetadataDocumentsModified", "metadata documents modified"),
        ("numberOfDocumentsDeleted", "documents deleted"),
        ("numberOfDocumentsSkipped", "documents skipped (unchanged)"),
        ("numberOfDocumentsFailed", "documents FAILED"),
    ]
    return [f"{label:30} {stats.get(key, 0)}" for key, label in labels]


def format_retrieval_results(results: list[dict], snippet_chars: int = 240) -> list[str]:
    lines = []
    for i, item in enumerate(results, 1):
        meta = item.get("metadata") or {}
        loc = (item.get("location") or {}).get("s3Location", {}).get("uri", "?")
        text = " ".join(((item.get("content") or {}).get("text") or "").split())
        if len(text) > snippet_chars:
            text = text[:snippet_chars].rstrip() + "..."
        lines.append(f"{i}. score={item.get('score', 0):.3f}  category={meta.get('category', '?')}"
                     f"  source={meta.get('source_id', '?')}  section={meta.get('section', '-')}")
        lines.append(f"   {loc}")
        lines.append(f"   {text}")
    return lines


# --------------------------------------------------------------------------- S3 Vectors

def ensure_vector_bucket(ctx: c.Ctx, name: str) -> tuple[str, bool]:
    """Returns (vector bucket ARN, created)."""
    s3v = ctx.client("s3vectors")
    if not ctx.offline:
        try:
            arn = s3v.get_vector_bucket(vectorBucketName=name)["vectorBucket"]["vectorBucketArn"]
            c.ok(f"vector bucket {name} exists")
            return arn, False
        except ClientError as exc:
            if c.error_code(exc) != "NotFoundException":
                raise
    resp = ctx.mutate(f"create S3 Vectors bucket {name} (SSE-S3)", s3v.create_vector_bucket,
                      vectorBucketName=name, encryptionConfiguration={"sseType": "AES256"},
                      tags=dict(c.TAGS))
    arn = ((resp or {}).get("vectorBucketArn")
           or c.vector_bucket_arn(ctx.region, ctx.account_id, name))
    return arn, True


def ensure_vector_index(ctx: c.Ctx, vector_bucket: str, index_name: str,
                        dimensions: int = c.EMBEDDING_DIMENSIONS, bucket_is_new: bool = False) -> str:
    s3v = ctx.client("s3vectors")
    if not (ctx.offline or (ctx.dry_run and bucket_is_new)):
        try:
            index = s3v.get_index(vectorBucketName=vector_bucket, indexName=index_name)["index"]
            if index.get("dimension") != dimensions:
                raise c.SetupError(
                    f"Index {index_name} has dimension {index.get('dimension')} but "
                    f"{dimensions} was requested. Run teardown.py --components kb,vectors and "
                    "re-run, or pass a matching --dimensions.")
            c.ok(f"vector index {index_name} exists ({dimensions} dims, "
                 f"{index.get('distanceMetric')})")
            return index["indexArn"]
        except ClientError as exc:
            if c.error_code(exc) != "NotFoundException":
                raise
    req = build_vector_index_request(vector_bucket, index_name, dimensions)
    resp = ctx.mutate(f"create vector index {index_name} ({dimensions} dims, cosine)",
                      s3v.create_index, **req)
    if resp and resp.get("indexArn"):
        return resp["indexArn"]
    return c.vector_index_arn(ctx.region, ctx.account_id, vector_bucket, index_name)


# --------------------------------------------------------------------------- Knowledge Base

def find_knowledge_base(ctx: c.Ctx, name: str) -> dict | None:
    if ctx.offline:
        return None
    agent = ctx.client("bedrock-agent")
    for page in agent.get_paginator("list_knowledge_bases").paginate():
        for kb in page.get("knowledgeBaseSummaries", []):
            if kb["name"] == name:
                return kb
    return None


def wait_for_knowledge_base(ctx: c.Ctx, kb_id: str, timeout: float = 300,
                            interval: float = 5) -> dict:
    agent = ctx.client("bedrock-agent")
    state: dict = {}

    def check() -> bool:
        kb = agent.get_knowledge_base(knowledgeBaseId=kb_id)["knowledgeBase"]
        state["kb"] = kb
        status = kb["status"]
        if status in ("FAILED", "DELETE_UNSUCCESSFUL", "UPDATE_UNSUCCESSFUL", "DELETING"):
            raise c.SetupError(f"Knowledge Base {kb_id} is {status}: {kb.get('failureReasons')}")
        return status == "ACTIVE"

    c.wait_until(check, timeout=timeout, interval=interval, what=f"KB {kb_id} to become ACTIVE")
    return state["kb"]


def create_knowledge_base_with_retry(ctx: c.Ctx, request: dict, attempts: int = 8,
                                     delay: float = 10.0) -> dict | None:
    """create_knowledge_base, retrying while a freshly created IAM role propagates."""
    agent = ctx.client("bedrock-agent")
    for attempt in range(1, attempts + 1):
        try:
            return ctx.mutate(f"create Knowledge Base {request['name']} "
                              f"(Titan Text Embeddings V2, S3 Vectors)",
                              agent.create_knowledge_base, **request)
        except ClientError as exc:
            message = str(exc).lower()
            retryable = (c.error_code(exc) in ("ValidationException", "AccessDeniedException")
                         and any(hint in message for hint in ROLE_PROPAGATION_HINTS))
            if not retryable or attempt == attempts:
                raise
            c.warn(f"{c.error_code(exc)} (IAM changes take a few seconds to propagate); "
                   f"retrying in {delay:.0f}s [{attempt}/{attempts - 1}]")
            time.sleep(delay)
    return None


def ensure_knowledge_base(ctx: c.Ctx, *, name: str, role_arn: str, index_arn: str,
                          dimensions: int = c.EMBEDDING_DIMENSIONS, timeout: float = 300,
                          interval: float = 5, retry_delay: float = 10.0) -> tuple[str, bool]:
    """Returns (kb_id, created)."""
    existing = find_knowledge_base(ctx, name)
    if existing:
        kb_id = existing["knowledgeBaseId"]
        c.ok(f"Knowledge Base {name} exists: {kb_id} ({existing['status']})")
        kb = wait_for_knowledge_base(ctx, kb_id, timeout, interval)
        storage = kb.get("storageConfiguration", {})
        found_index = storage.get("s3VectorsConfiguration", {}).get("indexArn")
        if storage.get("type") != "S3_VECTORS" or (found_index and found_index != index_arn):
            c.warn(f"existing KB uses storage {storage.get('type')} / {found_index}, "
                   f"expected S3_VECTORS / {index_arn}")
        return kb_id, False

    request = build_knowledge_base_request(name=name, role_arn=role_arn, region=ctx.region,
                                           index_arn=index_arn, dimensions=dimensions)
    resp = create_knowledge_base_with_retry(ctx, request, delay=retry_delay)
    if resp is None:
        return DRY_RUN_KB_ID, True
    kb_id = resp["knowledgeBase"]["knowledgeBaseId"]
    c.ok(f"created Knowledge Base {kb_id}; waiting for ACTIVE")
    wait_for_knowledge_base(ctx, kb_id, timeout, interval)
    c.ok(f"Knowledge Base {kb_id} is ACTIVE")
    return kb_id, True


def find_data_source(ctx: c.Ctx, kb_id: str, name: str) -> dict | None:
    agent = ctx.client("bedrock-agent")
    for page in agent.get_paginator("list_data_sources").paginate(knowledgeBaseId=kb_id):
        for ds in page.get("dataSourceSummaries", []):
            if ds["name"] == name:
                return ds
    return None


def ensure_data_source(ctx: c.Ctx, *, kb_id: str, bucket: str, prefix: str,
                       chunking: str = "none", kb_is_new: bool = False) -> str:
    agent = ctx.client("bedrock-agent")
    if not (ctx.offline or (ctx.dry_run and kb_is_new)):
        existing = find_data_source(ctx, kb_id, c.DATA_SOURCE_NAME)
        if existing:
            c.ok(f"data source {c.DATA_SOURCE_NAME} exists: {existing['dataSourceId']} "
                 f"({existing['status']})")
            return existing["dataSourceId"]
    request = build_data_source_request(kb_id=kb_id, bucket=bucket, prefix=prefix,
                                        account_id=ctx.account_id, chunking=chunking)
    resp = ctx.mutate(f"create S3 data source {c.DATA_SOURCE_NAME} on s3://{bucket}/{prefix} "
                      f"(chunking={chunking})", agent.create_data_source, **request)
    return resp["dataSource"]["dataSourceId"] if resp else DRY_RUN_DS_ID


# --------------------------------------------------------------------------- ingestion

def start_or_attach_ingestion(ctx: c.Ctx, kb_id: str, ds_id: str) -> str:
    agent = ctx.client("bedrock-agent")
    try:
        resp = ctx.mutate("start ingestion job", agent.start_ingestion_job,
                          knowledgeBaseId=kb_id, dataSourceId=ds_id,
                          description="scripts/aws/setup_knowledge_base.py")
        return resp["ingestionJob"]["ingestionJobId"]
    except ClientError as exc:
        if c.error_code(exc) != "ConflictException":
            raise
    jobs = agent.list_ingestion_jobs(
        knowledgeBaseId=kb_id, dataSourceId=ds_id, maxResults=10,
        sortBy={"attribute": "STARTED_AT", "order": "DESCENDING"})["ingestionJobSummaries"]
    running = next((j for j in jobs if j["status"] in INGESTION_RUNNING), None)
    if running is None:
        raise c.SetupError("StartIngestionJob reported a conflict but no running job was found")
    c.ok(f"an ingestion job is already running ({running['ingestionJobId']}); following it")
    return running["ingestionJobId"]


def wait_for_ingestion(ctx: c.Ctx, kb_id: str, ds_id: str, job_id: str,
                       timeout: float = 1800, interval: float = 10) -> dict:
    agent = ctx.client("bedrock-agent")
    state: dict = {"last": None}
    started = time.monotonic()

    def check() -> bool:
        job = agent.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id,
                                      ingestionJobId=job_id)["ingestionJob"]
        state["job"] = job
        if job["status"] != state["last"]:
            c.log(f"  ingestion {job_id}: {job['status']} "
                  f"(+{time.monotonic() - started:.0f}s)")
            state["last"] = job["status"]
        return job["status"] not in INGESTION_RUNNING

    c.wait_until(check, timeout=timeout, interval=interval, what=f"ingestion job {job_id}")
    job = state["job"]
    for line in format_ingestion_stats(job.get("statistics")):
        c.log(f"    {line}")
    if job["status"] in INGESTION_FAILED:
        raise c.SetupError(f"Ingestion job {job_id} ended {job['status']}: "
                           f"{job.get('failureReasons')}")
    failed = (job.get("statistics") or {}).get("numberOfDocumentsFailed", 0)
    if failed:
        c.warn(f"{failed} document(s) failed to ingest; check the job in the Bedrock console "
               "(often a malformed .metadata.json or an empty file)")
    return job


def run_test_query(ctx: c.Ctx, kb_id: str, query: str, top_k: int = 5,
                   category: str | None = None) -> list[dict]:
    c.step(f"Test query: {query!r}" + (f" (category={category})" if category else ""))
    if ctx.dry_run:
        c.log(f"  [dry-run] would call bedrock-agent-runtime Retrieve on KB {kb_id} (top {top_k})")
        return []
    runtime = ctx.client("bedrock-agent-runtime")
    resp = runtime.retrieve(**build_retrieve_request(kb_id, query, top_k, category))
    results = resp.get("retrievalResults", [])
    if not results:
        c.warn("no results: has ingestion completed with documents indexed?")
    for line in format_retrieval_results(results):
        c.log(f"  {line}")
    return results


# --------------------------------------------------------------------------- main flow

def guidelines_bucket_exists(ctx: c.Ctx, bucket: str) -> bool:
    if ctx.offline:
        return False
    try:
        ctx.client("s3").head_bucket(Bucket=bucket)
        return True
    except ClientError:
        return False


def run(ctx: c.Ctx, args: argparse.Namespace) -> dict:
    c.verify_credentials(ctx)

    if args.query_only:
        kb_id = args.kb_id or c.get_parameter(ctx, c.PARAM_KNOWLEDGE_BASE_ID)
        if not kb_id:
            raise c.SetupError(f"No KB id: pass --kb-id or set {c.PARAM_KNOWLEDGE_BASE_ID}")
        if not args.test_query:
            raise c.SetupError("--query-only needs --test-query \"...\"")
        results = run_test_query(ctx, kb_id, args.test_query, args.top_k, args.category)
        return {"knowledge_base_id": kb_id, "results": results}

    prefix = args.prefix if args.prefix.endswith("/") else args.prefix + "/"
    bucket = (args.bucket or c.get_parameter(ctx, c.PARAM_GUIDELINES_BUCKET)
              or c.default_guidelines_bucket(ctx.account_id, ctx.region))
    vector_bucket = (args.vector_bucket or c.get_parameter(ctx, c.PARAM_VECTOR_BUCKET)
                     or c.default_vector_bucket(ctx.account_id, ctx.region))

    c.step(f"Guidelines bucket s3://{bucket}/{prefix}")
    if guidelines_bucket_exists(ctx, bucket):
        c.ok("bucket exists")
    elif ctx.dry_run:
        c.warn("bucket not found (fine for a dry-run; run setup_s3.py before the real run)")
    else:
        raise c.SetupError(f"Bucket {bucket} not found. Run scripts/aws/setup_s3.py first "
                           "(or pass --bucket).")

    c.step("S3 Vectors store")
    _, vb_created = ensure_vector_bucket(ctx, vector_bucket)
    index_arn = ensure_vector_index(ctx, vector_bucket, args.index_name, args.dimensions,
                                    bucket_is_new=vb_created)

    c.step("IAM: Knowledge Base service role")
    kb_role_arn = c.ensure_kb_role(ctx, bucket, vector_bucket, args.index_name, prefix)

    c.step(f"Bedrock Knowledge Base {c.KB_NAME}")
    kb_id, kb_created = ensure_knowledge_base(
        ctx, name=c.KB_NAME, role_arn=kb_role_arn, index_arn=index_arn,
        dimensions=args.dimensions, timeout=args.timeout, interval=args.poll_interval,
        retry_delay=args.poll_interval * 2)
    ds_id = ensure_data_source(ctx, kb_id=kb_id, bucket=bucket, prefix=prefix,
                               chunking=args.chunking, kb_is_new=kb_created)

    c.step("Parameter Store")
    c.ensure_parameter(ctx, c.PARAM_KNOWLEDGE_BASE_ID, kb_id, "Bedrock Knowledge Base id")
    c.ensure_parameter(ctx, c.PARAM_DATA_SOURCE_ID, ds_id, "Bedrock KB S3 data source id")
    c.ensure_parameter(ctx, c.PARAM_VECTOR_BUCKET, vector_bucket, "S3 Vectors bucket for the KB")

    c.step("IAM: narrow Lambda role to this Knowledge Base")
    c.ensure_lambda_role(ctx, kb_id)

    job = None
    if args.no_ingest:
        c.step("Ingestion skipped (--no-ingest)")
    else:
        c.step("Ingestion")
        if ctx.dry_run:
            c.log(f"  [dry-run] would start an ingestion job for {kb_id}/{ds_id} and poll it")
        else:
            job_id = start_or_attach_ingestion(ctx, kb_id, ds_id)
            job = wait_for_ingestion(ctx, kb_id, ds_id, job_id, args.ingest_timeout,
                                     args.poll_interval)

    if args.test_query:
        run_test_query(ctx, kb_id, args.test_query, args.top_k, args.category)

    result = {"knowledge_base_id": kb_id, "data_source_id": ds_id,
              "vector_bucket": vector_bucket, "index_arn": index_arn,
              "kb_role_arn": kb_role_arn, "guidelines": f"s3://{bucket}/{prefix}",
              "ingestion_status": job["status"] if job else None}
    c.step("Summary" + (" (dry-run, nothing changed)" if ctx.dry_run else ""))
    for key, value in result.items():
        c.log(f"  {key:18} {value}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    c.add_common_args(parser)
    parser.add_argument("--bucket", default=None,
                        help=f"guidelines bucket (default: {c.PARAM_GUIDELINES_BUCKET} or "
                             "uic-editorial-guidelines-<account>-<region>)")
    parser.add_argument("--prefix", default=c.GUIDELINES_PREFIX,
                        help=f"S3 prefix to ingest (default: {c.GUIDELINES_PREFIX})")
    parser.add_argument("--vector-bucket", default=None,
                        help="S3 Vectors bucket (default: uic-editorial-vectors-<account>-<region>)")
    parser.add_argument("--index-name", default=c.VECTOR_INDEX_NAME,
                        help=f"S3 Vectors index name (default: {c.VECTOR_INDEX_NAME})")
    parser.add_argument("--dimensions", type=int, default=c.EMBEDDING_DIMENSIONS,
                        choices=[256, 512, 1024], help="Titan V2 embedding size (default: 1024)")
    parser.add_argument("--chunking", choices=["none", "fixed"], default="none",
                        help="KB chunking: none (files are pre-chunked; default) or fixed (300 tokens)")
    parser.add_argument("--no-ingest", action="store_true", help="skip the ingestion job")
    parser.add_argument("--test-query", default=None, help="run a Retrieve with this text at the end")
    parser.add_argument("--top-k", type=int, default=5, help="results for --test-query (default 5)")
    parser.add_argument("--category", default=None,
                        choices=["name", "tone", "audience", "editorial"],
                        help="metadata filter for --test-query")
    parser.add_argument("--query-only", action="store_true",
                        help="only run --test-query against the existing KB")
    parser.add_argument("--kb-id", default=None, help="KB id for --query-only (default: SSM)")
    parser.add_argument("--timeout", type=float, default=300,
                        help="seconds to wait for the KB to become ACTIVE")
    parser.add_argument("--ingest-timeout", type=float, default=1800,
                        help="seconds to wait for ingestion (default 1800)")
    parser.add_argument("--poll-interval", type=float, default=10, help="poll interval seconds")
    args = parser.parse_args(argv)

    def body() -> int:
        run(c.make_context(args), args)
        return 0

    return c.run_main(body)


if __name__ == "__main__":
    sys.exit(main())
