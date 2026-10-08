"""Tests for scripts/aws/deploy_rag_api.py and backend/api/lambda_app.py. No real AWS: moto only."""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import boto3
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "aws"))

import aws_common as c  # noqa: E402
import deploy_rag_api as d  # noqa: E402
import teardown  # noqa: E402
from moto import mock_aws  # noqa: E402

REGION = "us-east-1"


@pytest.fixture(autouse=True)
def fake_aws_env(monkeypatch):
    for var in ("AWS_PROFILE", "AWS_DEFAULT_PROFILE", "AWS_SESSION_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_CONFIG_FILE", "/dev/null")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/dev/null")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("UIC_SSM_ENABLED", "0")


@pytest.fixture
def ctx():
    with mock_aws():
        ctx = c.Ctx(region=REGION, session=boto3.Session(region_name=REGION))
        ctx.account_id = "123456789012"
        yield ctx


def tiny_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("backend/api/lambda_app.py", "handler = None\n")
    return buf.getvalue()


def lambda_role(ctx) -> str:
    trust = {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Action": "sts:AssumeRole",
             "Principal": {"Service": "lambda.amazonaws.com"}}]}
    return ctx.client("iam").create_role(RoleName=c.LAMBDA_ROLE_NAME,
                                         AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]


# --------------------------------------------------------------------------- packaging

def test_package_files_bundle_code_and_guidelines_without_caches():
    names = [name for _, name in d.package_files()]
    assert "backend/api/lambda_app.py" in names
    assert "backend/services/rag_service.py" in names
    assert "data/guidelines/guidelines_manifest.json" in names
    assert any(n.startswith("data/guidelines/chunks/") for n in names)
    assert not any("__pycache__" in n or n.endswith(".pyc") for n in names)
    assert not any(n.startswith("data/guidelines/raw/") for n in names)
    assert names == sorted(names)


def test_package_files_requires_manifest(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "data/guidelines/chunks").mkdir(parents=True)
    with pytest.raises(c.SetupError, match="scrape_guidelines"):
        d.package_files(tmp_path)


def test_write_zip_is_deterministic(tmp_path):
    files = d.package_files()[:5]
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    d.write_zip(files, a)
    d.write_zip(files, b)
    assert d.code_sha256(a.read_bytes()) == d.code_sha256(b.read_bytes())


def test_dependency_files_skip_bin_and_caches(tmp_path):
    for rel in ("fastapi/__init__.py", "bin/fastapi", "fastapi/__pycache__/x.pyc"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    assert [n for _, n in d.dependency_files(tmp_path)] == ["fastapi/__init__.py"]


# --------------------------------------------------------------------------- config

def test_function_environment_sets_kb_only_when_known():
    assert "UIC_KB_ID" not in d.function_environment(None, "*")
    assert d.function_environment("KB123", "*")["UIC_KB_ID"] == "KB123"


def test_config_drift():
    desired = d.function_config("arn:role", d.function_environment("KB1", "*"))
    current = {**desired, "Environment": {"Variables": dict(desired["Environment"]["Variables"])},
               "LoggingConfig": {**desired["LoggingConfig"], "ApplicationLogLevel": None}}
    assert d.config_drift(current, desired) == []
    current["Environment"]["Variables"]["UIC_KB_ID"] = "OLD"
    current["MemorySize"] = 128
    assert d.config_drift(current, desired) == ["MemorySize", "Environment"]


# --------------------------------------------------------------------------- AWS (moto)

def test_ensure_function_creates_then_is_idempotent(ctx, capsys):
    config = d.function_config(lambda_role(ctx), d.function_environment("KB1", "*"))
    arn = d.ensure_function(ctx, config, tiny_zip())
    fn = ctx.client("lambda").get_function(FunctionName=d.FUNCTION_NAME)["Configuration"]
    assert fn["FunctionArn"] == arn
    assert fn["Handler"] == d.HANDLER and fn["Architectures"] == ["arm64"]
    assert fn["Environment"]["Variables"]["UIC_KB_ID"] == "KB1"
    capsys.readouterr()
    assert d.ensure_function(ctx, config, tiny_zip()) == arn
    assert "code unchanged" in capsys.readouterr().out


def test_ensure_function_updates_drifted_environment(ctx):
    role = lambda_role(ctx)
    d.ensure_function(ctx, d.function_config(role, d.function_environment("KB1", "*")), tiny_zip())
    d.ensure_function(ctx, d.function_config(role, d.function_environment("KB2", "*")), tiny_zip())
    fn = ctx.client("lambda").get_function(FunctionName=d.FUNCTION_NAME)["Configuration"]
    assert fn["Environment"]["Variables"]["UIC_KB_ID"] == "KB2"


def test_dry_run_creates_nothing(ctx):
    ctx.dry_run = True
    config = d.function_config(lambda_role(ctx), d.function_environment(None, "*"))
    arn = d.ensure_function(ctx, config, tiny_zip())
    api_id, url = d.ensure_api(ctx, arn)
    d.ensure_invoke_permission(ctx, api_id)
    assert ctx.client("lambda").list_functions()["Functions"] == []
    assert ctx.client("apigatewayv2").get_apis()["Items"] == []
    assert url.startswith("https://")


def test_ensure_api_and_permission_idempotent(ctx):
    config = d.function_config(lambda_role(ctx), d.function_environment(None, "*"))
    arn = d.ensure_function(ctx, config, tiny_zip())
    api_id, url = d.ensure_api(ctx, arn)
    assert d.ensure_api(ctx, arn) == (api_id, url)
    assert len(ctx.client("apigatewayv2").get_apis()["Items"]) == 1
    d.ensure_invoke_permission(ctx, api_id)
    d.ensure_invoke_permission(ctx, api_id)
    policy = json.loads(ctx.client("lambda").get_policy(FunctionName=d.FUNCTION_NAME)["Policy"])
    stmts = [s for s in policy["Statement"] if s["Sid"] == d.PERMISSION_SID]
    assert len(stmts) == 1
    assert stmts[0]["Condition"]["ArnLike"]["AWS:SourceArn"].endswith(f":{api_id}/*/*")


def test_teardown_api_removes_function_and_api(ctx):
    config = d.function_config(lambda_role(ctx), d.function_environment(None, "*"))
    api_id, _ = d.ensure_api(ctx, d.ensure_function(ctx, config, tiny_zip()))
    teardown.teardown_api(ctx)
    assert ctx.client("lambda").list_functions()["Functions"] == []
    assert ctx.client("apigatewayv2").get_apis()["Items"] == []
    teardown.teardown_api(ctx)  # already gone: no error


def test_rag_api_url_is_a_managed_parameter():
    assert c.PARAM_RAG_API_URL in c.MANAGED_PARAMETERS
    assert "api" in teardown.COMPONENTS


# --------------------------------------------------------------------------- Lambda handler

def _event(method: str, path: str, body: dict | None = None, origin: str | None = None) -> dict:
    headers = {"content-type": "application/json", "host": "abc.execute-api.us-east-1.amazonaws.com"}
    if origin:
        headers["origin"] = origin
    return {"version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
            "headers": headers, "isBase64Encoded": False,
            "body": json.dumps(body) if body is not None else None,
            "requestContext": {"http": {"method": method, "path": path, "sourceIp": "1.2.3.4",
                                        "protocol": "HTTP/1.1", "userAgent": "pytest"},
                               "stage": "$default", "requestId": "r", "domainName": "abc",
                               "accountId": "1", "apiId": "abc", "routeKey": "$default",
                               "timeEpoch": 0, "time": ""}}


def test_lambda_handler_serves_rag_routes():
    from backend.api.lambda_app import handler

    resp = handler(_event("GET", "/api/rag/health", origin="https://x.amplifyapp.com"), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"])["status"] in {"ok", "degraded"}
    assert resp["headers"]["access-control-allow-origin"] == "*"
    resp = handler(_event("POST", "/api/rag/retrieve", {"query": ""}), None)
    assert resp["statusCode"] == 422


def test_cors_origins_parsing(monkeypatch):
    from backend.api import lambda_app

    monkeypatch.delenv(lambda_app.ENV_CORS_ORIGINS, raising=False)
    assert lambda_app.cors_origins() == ["*"]
    monkeypatch.setenv(lambda_app.ENV_CORS_ORIGINS, " https://a.com, ,https://b.com ")
    assert lambda_app.cors_origins() == ["https://a.com", "https://b.com"]


def test_package_bundles_rulesets_for_the_rule_engine():
    names = [name for _, name in d.package_files()]
    assert "rulesets/brand.json" in names and "backend/api/main.py" in names
    assert "backend/services/rewrite_service.py" in names


def test_function_environment_sets_models_when_known():
    env = d.function_environment("KB1", "*", "fast-id", "quality-id")
    assert env["UIC_MODEL_FAST"] == "fast-id" and env["UIC_MODEL_QUALITY"] == "quality-id"
    assert "UIC_MODEL_FAST" not in d.function_environment(None, "*")
