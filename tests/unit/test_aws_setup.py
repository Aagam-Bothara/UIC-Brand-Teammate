"""Tests for scripts/aws (Workstream 1 AWS setup). No real AWS: moto + botocore Stubber only."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import boto3
import pytest
from botocore.stub import ANY, Stubber

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "aws"))

import aws_common as c  # noqa: E402
import setup_base  # noqa: E402
import setup_knowledge_base as kbs  # noqa: E402
import setup_s3  # noqa: E402
import teardown  # noqa: E402

from moto import mock_aws  # noqa: E402

ACCOUNT = "123456789012"  # moto's default account
REGION = "us-east-1"
BUCKET = f"uic-editorial-guidelines-{ACCOUNT}-{REGION}"
VECTOR_BUCKET = f"uic-editorial-vectors-{ACCOUNT}-{REGION}"


# --------------------------------------------------------------------------- fixtures

@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch):
    """Fake credentials, isolated from any real ~/.aws config, and no IMDS lookups."""
    for var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_SESSION_TOKEN",
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI", "AWS_CONTAINER_CREDENTIALS_FULL_URI"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_CONFIG_FILE", "/dev/null")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/dev/null")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")


@pytest.fixture
def aws():
    with mock_aws():
        yield


@pytest.fixture
def chunks_dir(tmp_path):
    d = tmp_path / "chunks"
    d.mkdir()
    for sid, cat in (("editorial-style", "editorial"), ("voice-tone", "voice")):
        (d / f"{sid}-001.md").write_text(f"# {sid} — Intro\n\nSome guideline text.\n")
        (d / f"{sid}-001.md.metadata.json").write_text(json.dumps({"metadataAttributes": {
            "source_id": sid, "category": cat, "title": sid, "url": "https://brand.uic.edu/",
            "section": "Intro"}}))
    (d / ".DS_Store").write_text("junk")
    return d


def make_ctx(region=REGION, dry_run=False) -> c.Ctx:
    ctx = c.Ctx(region=region, dry_run=dry_run, session=boto3.Session(region_name=region))
    return ctx


def iam_policy(role, name):
    doc = boto3.client("iam").get_role_policy(RoleName=role, PolicyName=name)["PolicyDocument"]
    return c._as_policy_dict(doc)


def statement(policy, sid):
    return next(s for s in policy["Statement"] if s["Sid"] == sid)


def param(name):
    return boto3.client("ssm").get_parameter(Name=name)["Parameter"]["Value"]


# --------------------------------------------------------------------------- policy templates

def test_all_policy_templates_render_to_valid_json():
    ctx = make_ctx()
    ctx.account_id = ACCOUNT
    lam = c.lambda_policy_variables(ctx, None)
    kb = c.kb_policy_variables(ctx, BUCKET, VECTOR_BUCKET)
    for name, variables in [("lambda-trust-policy.json", lam), ("lambda-execution-policy.json", lam),
                            ("kb-trust-policy.json", kb), ("kb-service-policy.json", kb)]:
        doc = c.render_policy(name, variables)
        assert doc["Version"] == "2012-10-17"
        assert "${" not in json.dumps(doc)


def test_render_policy_missing_variable_is_setup_error():
    with pytest.raises(c.SetupError):
        c.render_policy("kb-service-policy.json", {"ACCOUNT_ID": ACCOUNT})


# --------------------------------------------------------------------------- setup_base

def test_setup_base_creates_roles_params_and_log_group(aws):
    assert setup_base.main(["--region", REGION]) == 0
    iam = boto3.client("iam")

    lam_role = iam.get_role(RoleName=c.LAMBDA_ROLE_NAME)["Role"]
    trust = c._as_policy_dict(lam_role["AssumeRolePolicyDocument"])
    assert trust["Statement"][0]["Principal"] == {"Service": "lambda.amazonaws.com"}

    lam = iam_policy(c.LAMBDA_ROLE_NAME, c.LAMBDA_POLICY_NAME)
    ssm_stmt = statement(lam, "ReadAppConfigFromParameterStore")
    assert f"arn:aws:ssm:{REGION}:{ACCOUNT}:parameter/uic-editorial/*" in ssm_stmt["Resource"]
    assert set(ssm_stmt["Action"]) == {"ssm:GetParameter", "ssm:GetParameters",
                                       "ssm:GetParametersByPath"}
    assert statement(lam, "RetrieveFromGuidelinesKnowledgeBase")["Resource"] == \
        f"arn:aws:bedrock:{REGION}:{ACCOUNT}:knowledge-base/*"
    assert f"arn:aws:logs:{REGION}:{ACCOUNT}:log-group:/uic-editorial/backend:*" in \
        statement(lam, "WriteBackendLogGroup")["Resource"]
    assert "bedrock:InvokeModel" in statement(lam, "InvokeAnthropicAndAmazonModels")["Action"]

    kb_role = iam.get_role(RoleName=c.KB_ROLE_NAME)["Role"]
    kb_trust = c._as_policy_dict(kb_role["AssumeRolePolicyDocument"])["Statement"][0]
    assert kb_trust["Principal"] == {"Service": "bedrock.amazonaws.com"}
    assert kb_trust["Condition"]["StringEquals"] == {"aws:SourceAccount": ACCOUNT}

    kb = iam_policy(c.KB_ROLE_NAME, c.KB_POLICY_NAME)
    assert statement(kb, "InvokeEmbeddingModel")["Resource"] == \
        f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0"
    assert statement(kb, "ReadGuidelineDocuments")["Resource"] == \
        f"arn:aws:s3:::{BUCKET}/guidelines/*"
    assert statement(kb, "ListGuidelinesBucket")["Resource"] == f"arn:aws:s3:::{BUCKET}"
    assert statement(kb, "ReadWriteS3VectorsIndex")["Resource"] == (
        f"arn:aws:s3vectors:{REGION}:{ACCOUNT}:bucket/{VECTOR_BUCKET}/index/{c.VECTOR_INDEX_NAME}")

    assert param("/uic-editorial/region") == REGION
    assert param("/uic-editorial/environment") == "dev"

    groups = boto3.client("logs").describe_log_groups(
        logGroupNamePrefix="/uic-editorial/backend")["logGroups"]
    assert [g["logGroupName"] for g in groups] == ["/uic-editorial/backend"]
    assert groups[0]["retentionInDays"] == 14


def test_setup_base_is_idempotent(aws, capsys):
    assert setup_base.main([]) == 0
    capsys.readouterr()
    assert setup_base.main([]) == 0
    out = capsys.readouterr().out
    assert "[change]" not in out
    assert "IAM role uic-editorial-lambda-role exists" in out
    assert "inline policy uic-editorial-kb-policy up to date" in out
    assert len(boto3.client("iam").list_roles()["Roles"]) == 2


def test_setup_base_repairs_drift(aws):
    logs = boto3.client("logs")
    logs.create_log_group(logGroupName=c.LOG_GROUP_NAME)
    logs.put_retention_policy(logGroupName=c.LOG_GROUP_NAME, retentionInDays=3)
    boto3.client("ssm").put_parameter(Name=c.PARAM_ENVIRONMENT, Value="old", Type="String")
    assert setup_base.main(["--environment", "hackathon"]) == 0
    assert logs.describe_log_groups(logGroupNamePrefix=c.LOG_GROUP_NAME)[
        "logGroups"][0]["retentionInDays"] == 14
    assert param(c.PARAM_ENVIRONMENT) == "hackathon"


def test_setup_base_narrows_lambda_policy_once_kb_id_known(aws):
    boto3.client("ssm").put_parameter(Name=c.PARAM_KNOWLEDGE_BASE_ID, Value="KB123ABCDE",
                                      Type="String")
    assert setup_base.main([]) == 0
    lam = iam_policy(c.LAMBDA_ROLE_NAME, c.LAMBDA_POLICY_NAME)
    assert statement(lam, "RetrieveFromGuidelinesKnowledgeBase")["Resource"] == \
        f"arn:aws:bedrock:{REGION}:{ACCOUNT}:knowledge-base/KB123ABCDE"


def test_setup_base_dry_run_changes_nothing(aws, capsys):
    assert setup_base.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "[dry-run] would create IAM role uic-editorial-lambda-role" in out
    assert boto3.client("iam").list_roles()["Roles"] == []
    assert boto3.client("ssm").describe_parameters()["Parameters"] == []
    assert boto3.client("logs").describe_log_groups()["logGroups"] == []


def test_missing_credentials_gives_friendly_error(monkeypatch, capsys):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    assert setup_base.main([]) == 2
    err = capsys.readouterr().err
    assert "No usable AWS credentials" in err and "aws sso login" in err


def test_missing_credentials_dry_run_is_offline_preview(monkeypatch, capsys):
    monkeypatch.delenv("AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY")
    assert setup_base.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "OFFLINE dry-run" in out
    assert "arn:aws:iam::000000000000:role/uic-editorial-kb-role" in out


# --------------------------------------------------------------------------- setup_s3

def run_s3(chunks_dir, *extra):
    return setup_s3.main(["--region", REGION, "--source-dir", str(chunks_dir), *extra])


def test_setup_s3_bucket_configuration_and_param(aws, chunks_dir):
    assert run_s3(chunks_dir) == 0
    s3 = boto3.client("s3")
    assert s3.get_bucket_versioning(Bucket=BUCKET)["Status"] == "Enabled"
    pab = s3.get_public_access_block(Bucket=BUCKET)["PublicAccessBlockConfiguration"]
    assert all(pab[k] for k in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy",
                                "RestrictPublicBuckets"))
    rule = s3.get_bucket_encryption(Bucket=BUCKET)["ServerSideEncryptionConfiguration"]["Rules"][0]
    assert rule["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"
    assert param(c.PARAM_GUIDELINES_BUCKET) == BUCKET


def test_setup_s3_uploads_with_content_types(aws, chunks_dir):
    assert run_s3(chunks_dir) == 0
    s3 = boto3.client("s3")
    keys = sorted(o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"])
    assert keys == [
        "guidelines/editorial-style-001.md",
        "guidelines/editorial-style-001.md.metadata.json",
        "guidelines/voice-tone-001.md",
        "guidelines/voice-tone-001.md.metadata.json",
    ]  # .DS_Store skipped
    md = s3.head_object(Bucket=BUCKET, Key="guidelines/voice-tone-001.md")
    assert md["ContentType"] == "text/markdown; charset=utf-8"
    sidecar = s3.head_object(Bucket=BUCKET, Key="guidelines/voice-tone-001.md.metadata.json")
    assert sidecar["ContentType"] == "application/json"
    body = s3.get_object(Bucket=BUCKET, Key="guidelines/voice-tone-001.md.metadata.json")["Body"]
    assert json.loads(body.read())["metadataAttributes"]["category"] == "voice"


def test_setup_s3_skips_unchanged_and_reuploads_changed(aws, chunks_dir):
    assert run_s3(chunks_dir) == 0
    ctx = make_ctx()
    first = setup_s3.upload_directory(ctx, BUCKET, chunks_dir)
    assert (first["uploaded"], first["skipped"]) == (0, 4)

    (chunks_dir / "voice-tone-001.md").write_text("# changed\n")
    second = setup_s3.upload_directory(ctx, BUCKET, chunks_dir)
    assert (second["uploaded"], second["skipped"]) == (1, 3)
    body = boto3.client("s3").get_object(Bucket=BUCKET, Key="guidelines/voice-tone-001.md")["Body"]
    assert body.read() == b"# changed\n"


def test_setup_s3_rerun_is_idempotent(aws, chunks_dir, capsys):
    assert run_s3(chunks_dir) == 0
    capsys.readouterr()
    assert run_s3(chunks_dir) == 0
    out = capsys.readouterr().out
    assert "[change]" not in out
    assert "uploaded 0, skipped 4 unchanged" in out


def test_setup_s3_stale_objects(aws, chunks_dir, capsys):
    assert run_s3(chunks_dir) == 0
    (chunks_dir / "voice-tone-001.md").unlink()
    (chunks_dir / "voice-tone-001.md.metadata.json").unlink()
    ctx = make_ctx()
    kept = setup_s3.upload_directory(ctx, BUCKET, chunks_dir)
    assert kept["stale"] == 2 and kept["deleted"] == 0
    assert "--delete-stale" in capsys.readouterr().out
    removed = setup_s3.upload_directory(ctx, BUCKET, chunks_dir, delete_stale=True)
    assert removed["deleted"] == 2
    keys = [o["Key"] for o in boto3.client("s3").list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert not any(k.startswith("guidelines/voice-tone") for k in keys)


def test_setup_s3_non_us_east_1_region(aws, chunks_dir):
    assert setup_s3.main(["--region", "us-west-2", "--source-dir", str(chunks_dir)]) == 0
    bucket = f"uic-editorial-guidelines-{ACCOUNT}-us-west-2"
    loc = boto3.client("s3", region_name="us-west-2").get_bucket_location(Bucket=bucket)
    assert loc["LocationConstraint"] == "us-west-2"


def test_setup_s3_dry_run_creates_nothing(aws, chunks_dir, capsys):
    assert run_s3(chunks_dir, "--dry-run") == 0
    out = capsys.readouterr().out
    assert "would upload 4" in out
    assert boto3.client("s3").list_buckets()["Buckets"] == []
    assert boto3.client("ssm").describe_parameters()["Parameters"] == []


def test_setup_s3_missing_chunks_dir_warns(aws, tmp_path, capsys):
    assert setup_s3.main(["--source-dir", str(tmp_path / "nope")]) == 0
    assert "scrape_guidelines.py" in capsys.readouterr().out
    assert param(c.PARAM_GUIDELINES_BUCKET) == BUCKET


def test_validate_sidecars_reports_problems(chunks_dir):
    (chunks_dir / "orphan-001.md").write_text("# no sidecar")
    (chunks_dir / "voice-tone-001.md.metadata.json").write_text("{not json")
    problems = setup_s3.validate_sidecars(setup_s3.collect_files(chunks_dir))
    assert any("orphan-001.md: missing" in p for p in problems)
    assert any("voice-tone-001.md.metadata.json: invalid JSON" in p for p in problems)
    assert not any("editorial-style" in p for p in problems)


def test_content_type_for():
    assert setup_s3.content_type_for("a.md") == "text/markdown; charset=utf-8"
    assert setup_s3.content_type_for("a.md.metadata.json") == "application/json"


# --------------------------------------------------------------------------- KB request builders

INDEX_ARN = f"arn:aws:s3vectors:{REGION}:{ACCOUNT}:bucket/{VECTOR_BUCKET}/index/{c.VECTOR_INDEX_NAME}"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/{c.KB_ROLE_NAME}"
NOW = dt.datetime(2026, 10, 8, tzinfo=dt.timezone.utc)


def test_build_knowledge_base_request():
    req = kbs.build_knowledge_base_request(name=c.KB_NAME, role_arn=ROLE_ARN, region=REGION,
                                           index_arn=INDEX_ARN)
    vec = req["knowledgeBaseConfiguration"]["vectorKnowledgeBaseConfiguration"]
    assert req["knowledgeBaseConfiguration"]["type"] == "VECTOR"
    assert vec["embeddingModelArn"] == \
        "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
    assert vec["embeddingModelConfiguration"]["bedrockEmbeddingModelConfiguration"] == \
        {"dimensions": 1024, "embeddingDataType": "FLOAT32"}
    assert req["storageConfiguration"] == {"type": "S3_VECTORS",
                                           "s3VectorsConfiguration": {"indexArn": INDEX_ARN}}


def test_build_data_source_request_and_chunking():
    req = kbs.build_data_source_request(kb_id="KB1234ABCD", bucket=BUCKET, prefix="guidelines/",
                                        account_id=ACCOUNT)
    s3cfg = req["dataSourceConfiguration"]["s3Configuration"]
    assert s3cfg == {"bucketArn": f"arn:aws:s3:::{BUCKET}", "inclusionPrefixes": ["guidelines/"],
                     "bucketOwnerAccountId": ACCOUNT}
    assert req["vectorIngestionConfiguration"]["chunkingConfiguration"] == \
        {"chunkingStrategy": "NONE"}
    fixed = kbs.build_chunking_configuration("fixed")
    assert fixed["chunkingStrategy"] == "FIXED_SIZE"
    with pytest.raises(ValueError):
        kbs.build_chunking_configuration("semantic")


def test_build_vector_index_request():
    req = kbs.build_vector_index_request(VECTOR_BUCKET, "idx", 512)
    assert (req["dataType"], req["dimension"], req["distanceMetric"]) == ("float32", 512, "cosine")
    assert "AMAZON_BEDROCK_TEXT" in req["metadataConfiguration"]["nonFilterableMetadataKeys"]


def test_build_retrieve_request_with_category_filter():
    req = kbs.build_retrieve_request("KB1234ABCD", "university name", 3, "editorial")
    assert req["retrievalQuery"] == {"text": "university name"}
    assert req["retrievalConfiguration"]["vectorSearchConfiguration"] == {
        "numberOfResults": 3, "filter": {"equals": {"key": "category", "value": "editorial"}}}
    assert "filter" not in kbs.build_retrieve_request("KB1234ABCD", "q")[
        "retrievalConfiguration"]["vectorSearchConfiguration"]


def test_format_helpers():
    lines = kbs.format_ingestion_stats({"numberOfDocumentsScanned": 125,
                                        "numberOfNewDocumentsIndexed": 120})
    assert any("documents scanned" in l and "125" in l for l in lines)
    out = kbs.format_retrieval_results([{
        "content": {"text": "Use University of Illinois Chicago " * 20}, "score": 0.81234,
        "location": {"s3Location": {"uri": "s3://b/guidelines/x.md"}},
        "metadata": {"category": "editorial", "source_id": "editorial-style", "section": "Name"}}])
    assert out[0].startswith("1. score=0.812  category=editorial")
    assert out[1].strip() == "s3://b/guidelines/x.md"
    assert out[2].endswith("...")


# --------------------------------------------------------------------------- KB with Stubber

def stubbed(ctx, service):
    client = boto3.client(service, region_name=REGION)
    ctx._clients[service] = client
    stub = Stubber(client)
    stub.activate()
    return stub


def kb_body(kb_id="KB1234ABCD", status="ACTIVE"):
    return {"knowledgeBase": {
        "knowledgeBaseId": kb_id, "name": c.KB_NAME, "status": status, "roleArn": ROLE_ARN,
        "knowledgeBaseArn": f"arn:aws:bedrock:{REGION}:{ACCOUNT}:knowledge-base/{kb_id}",
        "knowledgeBaseConfiguration": {"type": "VECTOR"},
        "storageConfiguration": {"type": "S3_VECTORS",
                                 "s3VectorsConfiguration": {"indexArn": INDEX_ARN}},
        "createdAt": NOW, "updatedAt": NOW}}


def test_ensure_knowledge_base_creates_and_waits():
    ctx = make_ctx()
    ctx.account_id = ACCOUNT
    stub = stubbed(ctx, "bedrock-agent")
    req = kbs.build_knowledge_base_request(name=c.KB_NAME, role_arn=ROLE_ARN, region=REGION,
                                           index_arn=INDEX_ARN)
    stub.add_response("list_knowledge_bases", {"knowledgeBaseSummaries": []}, {})
    stub.add_response("create_knowledge_base", kb_body(status="CREATING"),
                      req)
    stub.add_response("get_knowledge_base", kb_body(status="CREATING"), {"knowledgeBaseId": "KB1234ABCD"})
    stub.add_response("get_knowledge_base", kb_body(), {"knowledgeBaseId": "KB1234ABCD"})
    kb_id, created = kbs.ensure_knowledge_base(ctx, name=c.KB_NAME, role_arn=ROLE_ARN,
                                               index_arn=INDEX_ARN, interval=0, retry_delay=0)
    assert (kb_id, created) == ("KB1234ABCD", True)
    stub.assert_no_pending_responses()


def test_ensure_knowledge_base_reuses_existing():
    ctx = make_ctx()
    stub = stubbed(ctx, "bedrock-agent")
    stub.add_response("list_knowledge_bases", {"knowledgeBaseSummaries": [
        {"knowledgeBaseId": "OTHER12345", "name": "something-else", "status": "ACTIVE", "updatedAt": NOW},
        {"knowledgeBaseId": "KB9999ABCD", "name": c.KB_NAME, "status": "ACTIVE", "updatedAt": NOW}]}, {})
    stub.add_response("get_knowledge_base", kb_body("KB9999ABCD"), {"knowledgeBaseId": "KB9999ABCD"})
    assert kbs.ensure_knowledge_base(ctx, name=c.KB_NAME, role_arn=ROLE_ARN, index_arn=INDEX_ARN,
                                     interval=0) == ("KB9999ABCD", False)
    stub.assert_no_pending_responses()


def test_create_knowledge_base_retries_while_role_propagates():
    ctx = make_ctx()
    stub = stubbed(ctx, "bedrock-agent")
    req = kbs.build_knowledge_base_request(name=c.KB_NAME, role_arn=ROLE_ARN, region=REGION,
                                           index_arn=INDEX_ARN)
    stub.add_client_error("create_knowledge_base", "ValidationException",
                          "Unable to assume role arn:aws:iam::123456789012:role/x")
    stub.add_response("create_knowledge_base", kb_body(status="CREATING"))
    resp = kbs.create_knowledge_base_with_retry(ctx, req, delay=0)
    assert resp["knowledgeBase"]["knowledgeBaseId"] == "KB1234ABCD"

    stub.add_client_error("create_knowledge_base", "ValidationException", "Name already used")
    with pytest.raises(Exception, match="Name already used"):
        kbs.create_knowledge_base_with_retry(ctx, req, delay=0)


def test_ensure_data_source_create_and_existing():
    ctx = make_ctx()
    ctx.account_id = ACCOUNT
    stub = stubbed(ctx, "bedrock-agent")
    req = kbs.build_data_source_request(kb_id="KB1234ABCD", bucket=BUCKET, prefix="guidelines/",
                                        account_id=ACCOUNT)
    stub.add_response("list_data_sources", {"dataSourceSummaries": []}, {"knowledgeBaseId": "KB1234ABCD"})
    stub.add_response("create_data_source", {"dataSource": {
        "knowledgeBaseId": "KB1234ABCD", "dataSourceId": "DS1234ABCD", "name": c.DATA_SOURCE_NAME,
        "status": "AVAILABLE", "dataSourceConfiguration": req["dataSourceConfiguration"],
        "createdAt": NOW, "updatedAt": NOW}}, req)
    assert kbs.ensure_data_source(ctx, kb_id="KB1234ABCD", bucket=BUCKET, prefix="guidelines/") == "DS1234ABCD"

    stub.add_response("list_data_sources", {"dataSourceSummaries": [
        {"knowledgeBaseId": "KB1234ABCD", "dataSourceId": "DS1234ABCD", "name": c.DATA_SOURCE_NAME,
         "status": "AVAILABLE", "updatedAt": NOW}]}, {"knowledgeBaseId": "KB1234ABCD"})
    assert kbs.ensure_data_source(ctx, kb_id="KB1234ABCD", bucket=BUCKET, prefix="guidelines/") == "DS1234ABCD"
    stub.assert_no_pending_responses()


def job(status, stats=None):
    body = {"knowledgeBaseId": "KB1234ABCD", "dataSourceId": "DS1234ABCD", "ingestionJobId": "JOB1234ABC",
            "status": status, "startedAt": NOW, "updatedAt": NOW}
    if stats:
        body["statistics"] = stats
    return {"ingestionJob": body}


def test_ingestion_start_and_poll_until_complete(capsys):
    ctx = make_ctx()
    stub = stubbed(ctx, "bedrock-agent")
    ids = {"knowledgeBaseId": "KB1234ABCD", "dataSourceId": "DS1234ABCD"}
    stub.add_response("start_ingestion_job", job("STARTING"),
                      {**ids, "description": ANY})
    stub.add_response("get_ingestion_job", job("IN_PROGRESS"), {**ids, "ingestionJobId": "JOB1234ABC"})
    stub.add_response("get_ingestion_job", job("COMPLETE", {
        "numberOfDocumentsScanned": 125, "numberOfNewDocumentsIndexed": 125}),
        {**ids, "ingestionJobId": "JOB1234ABC"})
    job_id = kbs.start_or_attach_ingestion(ctx, "KB1234ABCD", "DS1234ABCD")
    result = kbs.wait_for_ingestion(ctx, "KB1234ABCD", "DS1234ABCD", job_id, timeout=5, interval=0)
    assert result["status"] == "COMPLETE"
    out = capsys.readouterr().out
    assert "IN_PROGRESS" in out and "COMPLETE" in out and "125" in out
    stub.assert_no_pending_responses()


def test_ingestion_attaches_to_running_job_on_conflict():
    ctx = make_ctx()
    stub = stubbed(ctx, "bedrock-agent")
    stub.add_client_error("start_ingestion_job", "ConflictException", "job already running")
    stub.add_response("list_ingestion_jobs", {"ingestionJobSummaries": [
        {"knowledgeBaseId": "KB1234ABCD", "dataSourceId": "DS1234ABCD", "ingestionJobId": "JOB0000ABC",
         "status": "IN_PROGRESS", "startedAt": NOW, "updatedAt": NOW}]})
    assert kbs.start_or_attach_ingestion(ctx, "KB1234ABCD", "DS1234ABCD") == "JOB0000ABC"


def test_ingestion_failure_raises():
    ctx = make_ctx()
    stub = stubbed(ctx, "bedrock-agent")
    failed = job("FAILED")
    failed["ingestionJob"]["failureReasons"] = ["AccessDenied on s3"]
    stub.add_response("get_ingestion_job", failed)
    with pytest.raises(c.SetupError, match="AccessDenied on s3"):
        kbs.wait_for_ingestion(ctx, "KB1234ABCD", "DS1234ABCD", "JOB1234ABC", timeout=5, interval=0)


def test_run_test_query_prints_results(capsys):
    ctx = make_ctx()
    stub = stubbed(ctx, "bedrock-agent-runtime")
    stub.add_response("retrieve", {"retrievalResults": [{
        "content": {"text": "Write University of Illinois Chicago on first reference."},
        "location": {"type": "S3", "s3Location": {"uri": f"s3://{BUCKET}/guidelines/e-1.md"}},
        "score": 0.77, "metadata": {"category": "editorial", "source_id": "editorial-style"}}]},
        kbs.build_retrieve_request("KB1234ABCD", "university name", 5, "editorial"))
    results = kbs.run_test_query(ctx, "KB1234ABCD", "university name", 5, "editorial")
    assert len(results) == 1
    assert "score=0.770  category=editorial" in capsys.readouterr().out


def test_vector_store_with_moto(aws):
    ctx = make_ctx()
    ctx.account_id = ACCOUNT
    arn, created = kbs.ensure_vector_bucket(ctx, VECTOR_BUCKET)
    assert created and arn.endswith(f"bucket/{VECTOR_BUCKET}")
    assert kbs.ensure_vector_bucket(ctx, VECTOR_BUCKET)[1] is False
    index_arn = kbs.ensure_vector_index(ctx, VECTOR_BUCKET, c.VECTOR_INDEX_NAME)
    assert index_arn == INDEX_ARN
    assert kbs.ensure_vector_index(ctx, VECTOR_BUCKET, c.VECTOR_INDEX_NAME) == INDEX_ARN
    with pytest.raises(c.SetupError, match="dimension"):
        kbs.ensure_vector_index(ctx, VECTOR_BUCKET, c.VECTOR_INDEX_NAME, dimensions=256)


def test_setup_knowledge_base_end_to_end(aws, chunks_dir, monkeypatch):
    """setup_base + setup_s3 under moto, then the KB script with a stubbed bedrock-agent."""
    assert setup_base.main([]) == 0
    assert setup_s3.main(["--source-dir", str(chunks_dir)]) == 0

    ctx = make_ctx()
    stub = stubbed(ctx, "bedrock-agent")
    stub.add_response("list_knowledge_bases", {"knowledgeBaseSummaries": []}, {})
    stub.add_response("create_knowledge_base", kb_body(status="CREATING"))
    stub.add_response("get_knowledge_base", kb_body(), {"knowledgeBaseId": "KB1234ABCD"})
    stub.add_response("list_data_sources", {"dataSourceSummaries": []}, {"knowledgeBaseId": "KB1234ABCD"})
    stub.add_response("create_data_source", {"dataSource": {
        "knowledgeBaseId": "KB1234ABCD", "dataSourceId": "DS1234ABCD", "name": c.DATA_SOURCE_NAME,
        "status": "AVAILABLE", "dataSourceConfiguration": {"type": "S3"},
        "createdAt": NOW, "updatedAt": NOW}})
    stub.add_response("start_ingestion_job", job("STARTING"))
    stub.add_response("get_ingestion_job", job("COMPLETE", {"numberOfDocumentsScanned": 2}))
    monkeypatch.setattr(c, "make_context", lambda args: ctx)

    assert kbs.main(["--poll-interval", "0"]) == 0
    stub.assert_no_pending_responses()

    assert param(c.PARAM_KNOWLEDGE_BASE_ID) == "KB1234ABCD"
    assert param(c.PARAM_DATA_SOURCE_ID) == "DS1234ABCD"
    assert param(c.PARAM_VECTOR_BUCKET) == VECTOR_BUCKET
    lam = iam_policy(c.LAMBDA_ROLE_NAME, c.LAMBDA_POLICY_NAME)
    assert statement(lam, "RetrieveFromGuidelinesKnowledgeBase")["Resource"] == \
        f"arn:aws:bedrock:{REGION}:{ACCOUNT}:knowledge-base/KB1234ABCD"
    index = boto3.client("s3vectors").get_index(vectorBucketName=VECTOR_BUCKET,
                                                indexName=c.VECTOR_INDEX_NAME)["index"]
    assert index["dimension"] == 1024


def test_setup_knowledge_base_requires_bucket(aws):
    assert kbs.main(["--no-ingest"]) == 2


# --------------------------------------------------------------------------- teardown

def test_teardown_requires_yes(aws, chunks_dir):
    assert setup_base.main([]) == 0
    assert teardown.main(["--components", "iam"]) == 1
    assert len(boto3.client("iam").list_roles()["Roles"]) == 2


def test_teardown_removes_base_and_bucket(aws, chunks_dir):
    assert setup_base.main([]) == 0
    assert setup_s3.main(["--source-dir", str(chunks_dir)]) == 0
    (chunks_dir / "voice-tone-001.md").write_text("v2")  # create a second object version
    assert setup_s3.main(["--source-dir", str(chunks_dir)]) == 0
    boto3.client("ssm").put_parameter(Name="/uic-editorial/other_team", Value="x", Type="String")
    ctx = make_ctx()
    ctx.account_id = ACCOUNT
    kbs.ensure_vector_bucket(ctx, VECTOR_BUCKET)
    kbs.ensure_vector_index(ctx, VECTOR_BUCKET, c.VECTOR_INDEX_NAME)

    assert teardown.main(["--yes", "--components", "vectors,s3,ssm,logs,iam"]) == 0

    assert boto3.client("iam").list_roles()["Roles"] == []
    assert boto3.client("s3").list_buckets()["Buckets"] == []
    assert boto3.client("logs").describe_log_groups()["logGroups"] == []
    remaining = [p["Name"] for p in boto3.client("ssm").describe_parameters()["Parameters"]]
    assert remaining == ["/uic-editorial/other_team"]  # only our own parameters are deleted
    assert boto3.client("s3vectors").list_vector_buckets()["vectorBuckets"] == []


def test_teardown_rejects_unknown_component():
    with pytest.raises(SystemExit):
        teardown.main(["--components", "kb,nope"])


# --------------------------------------------------------------------------- QA regressions

def test_setup_s3_rerun_reuses_bucket_from_parameter_store(aws, chunks_dir):
    """A bucket chosen once with --bucket is reused on re-runs (e.g. via setup_all.sh)."""
    assert run_s3(chunks_dir, "--bucket", "my-custom-guidelines") == 0
    assert run_s3(chunks_dir) == 0
    assert [b["Name"] for b in boto3.client("s3").list_buckets()["Buckets"]] == ["my-custom-guidelines"]
    assert param(c.PARAM_GUIDELINES_BUCKET) == "my-custom-guidelines"


def test_delete_stale_does_not_count_failed_deletes(tmp_path, capsys):
    ctx = make_ctx()
    stub = stubbed(ctx, "s3")
    stub.add_response("list_objects_v2", {"Contents": [{"Key": "guidelines/old.md", "ETag": '"x"'}],
                                          "IsTruncated": False})
    stub.add_response("delete_objects", {"Errors": [{"Key": "guidelines/old.md", "Code": "AccessDenied",
                                                     "Message": "denied"}]})
    stats = setup_s3.upload_directory(ctx, BUCKET, tmp_path, delete_stale=True)
    assert (stats["stale"], stats["deleted"]) == (1, 0)
    assert "could not delete guidelines/old.md: AccessDenied" in capsys.readouterr().out


def test_teardown_bucket_stops_when_object_deletes_fail():
    ctx = make_ctx()
    stub = stubbed(ctx, "s3")
    stub.add_response("head_bucket", {})
    stub.add_response("list_object_versions", {"Versions": [
        {"Key": "guidelines/a.md", "VersionId": "v1"}], "IsTruncated": False})
    stub.add_response("delete_objects", {"Errors": [{"Key": "guidelines/a.md", "VersionId": "v1",
                                                     "Code": "AccessDenied", "Message": "denied"}]})
    with pytest.raises(c.SetupError, match="AccessDenied"):
        teardown.teardown_bucket(ctx, BUCKET)
    stub.assert_no_pending_responses()  # delete_bucket was never attempted


def test_wait_for_knowledge_base_update_unsuccessful_fails_fast():
    ctx = make_ctx()
    stub = stubbed(ctx, "bedrock-agent")
    body = kb_body(status="UPDATE_UNSUCCESSFUL")
    body["knowledgeBase"]["failureReasons"] = ["role cannot read index"]
    stub.add_response("get_knowledge_base", body)
    with pytest.raises(c.SetupError, match="UPDATE_UNSUCCESSFUL"):
        kbs.wait_for_knowledge_base(ctx, "KB1234ABCD", timeout=60, interval=0)


def test_teardown_data_source_delete_unsuccessful_fails_fast(capsys):
    ctx = make_ctx()
    stub = stubbed(ctx, "bedrock-agent")
    stub.add_response("list_knowledge_bases", {"knowledgeBaseSummaries": []})
    stub.add_response("list_data_sources", {"dataSourceSummaries": [
        {"knowledgeBaseId": "KB1234ABCD", "dataSourceId": "DS1234ABCD", "name": c.DATA_SOURCE_NAME,
         "status": "AVAILABLE", "updatedAt": NOW}]})
    stub.add_response("delete_data_source", {"knowledgeBaseId": "KB1234ABCD", "dataSourceId": "DS1234ABCD",
                                             "status": "DELETING"})
    stub.add_response("get_data_source", {"dataSource": {
        "knowledgeBaseId": "KB1234ABCD", "dataSourceId": "DS1234ABCD", "name": c.DATA_SOURCE_NAME,
        "status": "DELETE_UNSUCCESSFUL", "dataSourceConfiguration": {"type": "S3"},
        "failureReasons": ["index not found"], "createdAt": NOW, "updatedAt": NOW}})
    stub.add_response("delete_knowledge_base", {"knowledgeBaseId": "KB1234ABCD", "status": "DELETING"})
    stub.add_client_error("get_knowledge_base", "ResourceNotFoundException")
    teardown.teardown_kb(ctx, "KB1234ABCD", timeout=60, interval=0)
    out = capsys.readouterr().out
    assert "DELETE_UNSUCCESSFUL" in out and "RETAIN" in out
    stub.assert_no_pending_responses()


READ_ONLY_PREFIXES = ("Get", "List", "Describe", "Head")


@pytest.fixture
def recorded_calls(monkeypatch):
    """Record every AWS operation made through Ctx clients."""
    calls: list[str] = []
    original = c.Ctx.client

    def client(self, name):
        new = name not in self._clients
        cl = original(self, name)
        if new:
            cl.meta.events.register(
                "before-call", lambda model, **_: calls.append(f"{name}:{model.name}"))
        return cl

    monkeypatch.setattr(c.Ctx, "client", client)
    return calls


@pytest.mark.parametrize("existing", [False, True])
def test_dry_run_never_calls_mutating_apis(aws, chunks_dir, recorded_calls, existing):
    if existing:
        assert setup_base.main([]) == 0
        assert run_s3(chunks_dir) == 0
        (chunks_dir / "voice-tone-001.md").write_text("changed")
        boto3.client("ssm").put_parameter(Name=c.PARAM_ENVIRONMENT, Value="drift", Type="String",
                                          Overwrite=True)
        recorded_calls.clear()
    assert setup_base.main(["--dry-run"]) == 0
    assert run_s3(chunks_dir, "--dry-run", "--delete-stale") == 0
    assert kbs.main(["--dry-run", "--test-query", "university name"]) == 0
    assert teardown.main(["--dry-run"]) == 0
    assert teardown.main([]) == 1  # no --yes: plan only
    assert recorded_calls, "expected read-only lookups to be recorded"
    mutating = [x for x in recorded_calls if not x.split(":")[1].startswith(READ_ONLY_PREFIXES)]
    assert mutating == []


def _offline_env() -> dict:
    """No credentials at all, so nothing can reach AWS."""
    import os
    return {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
            "AWS_CONFIG_FILE": "/dev/null", "AWS_SHARED_CREDENTIALS_FILE": "/dev/null",
            "AWS_EC2_METADATA_DISABLED": "true"}


def test_setup_all_sh_help_and_args(tmp_path):
    import subprocess
    script = str(REPO_ROOT / "scripts" / "aws" / "setup_all.sh")
    help_out = subprocess.run(["bash", script, "--help"], capture_output=True, text=True,
                              env=_offline_env(), cwd=tmp_path)
    assert help_out.returncode == 0
    assert "teardown.py --region REGION --yes" in help_out.stdout
    bad = subprocess.run(["bash", script, "--bogus"], capture_output=True, text=True,
                         env=_offline_env(), cwd=tmp_path)
    assert bad.returncode == 2 and "unknown argument" in bad.stderr


def test_setup_all_sh_offline_dry_run_from_any_cwd(tmp_path):
    import subprocess
    script = str(REPO_ROOT / "scripts" / "aws" / "setup_all.sh")
    res = subprocess.run(["bash", script, "--region=us-west-2", "--dry-run", "--test-query=uic name"],
                         capture_output=True, text=True, env=_offline_env(), cwd=tmp_path, timeout=120)
    assert res.returncode == 0, res.stderr
    assert res.stdout.count("OFFLINE dry-run") == 4  # base, s3, kb, rag api
    assert "Test query: 'uic name'" in res.stdout
    assert "uic-editorial-guidelines-000000000000-us-west-2" in res.stdout


def test_validate_sidecars_reads_utf8_regardless_of_locale(chunks_dir, monkeypatch):
    """Sidecars contain non-ASCII text; reading them must not depend on the locale encoding."""
    (chunks_dir / "voice-tone-001.md.metadata.json").write_text(json.dumps(
        {"metadataAttributes": {"section": "Here’s how — “quotes”"}}, ensure_ascii=False),
        encoding="utf-8")
    original = Path.read_text

    def ascii_locale_read_text(self, encoding=None, errors=None, **kw):  # simulate LC_ALL=C
        return original(self, encoding=encoding or "ascii", errors=errors, **kw)

    monkeypatch.setattr(Path, "read_text", ascii_locale_read_text)
    assert setup_s3.validate_sidecars(setup_s3.collect_files(chunks_dir)) == []


@pytest.fixture
def guidelines_with_orphans(tmp_path):
    """Copy of the fixture guidelines dir plus chunk files the manifest does not list."""
    import shutil
    root = tmp_path / "guidelines"
    shutil.copytree(REPO_ROOT / "tests" / "fixtures" / "guidelines", root)
    (root / "chunks" / "old-source-009.md").write_text("# Old — gone\n\nstale text", encoding="utf-8")
    (root / "chunks" / "old-source-009.md.metadata.json").write_text(
        '{"metadataAttributes": {"category": "name"}}', encoding="utf-8")
    return root


def test_setup_s3_uploads_only_manifest_chunks(aws, guidelines_with_orphans, capsys):
    root = guidelines_with_orphans
    manifest = json.loads((root / "guidelines_manifest.json").read_text(encoding="utf-8"))
    expected = sorted(f"guidelines/{Path(ch['path']).name}{suffix}"
                      for ch in manifest["chunks"] for suffix in ("", ".metadata.json"))
    assert run_s3(root / "chunks") == 0
    out = capsys.readouterr().out
    assert "old-source-009.md: on disk but not in guidelines_manifest.json" in out
    keys = sorted(o["Key"] for o in boto3.client("s3").list_objects_v2(Bucket=BUCKET)["Contents"])
    assert keys == expected


def test_setup_s3_delete_stale_removes_objects_not_in_manifest(aws, guidelines_with_orphans):
    root = guidelines_with_orphans
    assert run_s3(root / "chunks") == 0
    s3 = boto3.client("s3")
    s3.put_object(Bucket=BUCKET, Key="guidelines/old-source-009.md", Body=b"stale")  # earlier upload
    assert run_s3(root / "chunks", "--delete-stale") == 0
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"]]
    assert "guidelines/old-source-009.md" not in keys and keys


def test_setup_s3_explicit_missing_manifest_is_error(aws, chunks_dir, tmp_path):
    assert run_s3(chunks_dir, "--manifest", str(tmp_path / "nope.json")) == 2


def test_select_files_without_manifest_uploads_everything(chunks_dir):
    files, problems = setup_s3.select_files(chunks_dir, chunks_dir.parent / "guidelines_manifest.json")
    assert len(files) == 4 and any("uploading every chunk file" in p for p in problems)
