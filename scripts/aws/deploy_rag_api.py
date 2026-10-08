#!/usr/bin/env python3
"""Deploy the integrated UIC Editorial Assistant backend to AWS Lambda behind an API Gateway HTTP API.

The deployed app is ``backend/api/main.py`` (Task I.3): WS1 retrieval (``/api/rag/*``), WS2 rule
engine + scoring (``/api/rules*``, ``/api/audiences``) and the orchestrator with the Bedrock
rewrite/chat (``/api/analyze``, ``/api/llm/refine``). Function/API keep their original
``uic-editorial-rag-api`` names so the URL stays stable.

Creates or updates (idempotently, safe to re-run):
  * Lambda package: backend/ + rulesets/ (WS2 rule files) + data/guidelines/ (local-search
    fallback) + requirements-lambda.txt built for the Lambda runtime (manylinux wheels, arm64).
    boto3 comes from the runtime.
  * Lambda function ``uic-editorial-rag-api`` (python3.13, arm64) running
    ``backend.api.lambda_app.handler`` as ``uic-editorial-lambda-role``. Logs go to the
    ``/uic-editorial/backend`` log group. ``UIC_KB_ID``, ``UIC_MODEL_FAST`` and
    ``UIC_MODEL_QUALITY`` are set from Parameter Store at deploy time so cold starts skip SSM.
  * HTTP API ``uic-editorial-rag-api`` with a ``$default`` route proxying everything to the
    function (payload format 2.0, auto-deployed ``$default`` stage), plus the Lambda invoke
    permission for that API.
  * SSM parameter ``/uic-editorial/rag_api_url`` with the API's base URL.
Then smoke-tests ``GET /api/rag/health`` (skip with ``--no-smoke-test``).

Run after setup_base.py (role + log group) and, for Bedrock retrieval, setup_knowledge_base.py.
Code is only re-uploaded when the package hash changes.

Usage:
  python scripts/aws/deploy_rag_api.py [--region us-east-1] [--profile NAME] [--dry-run]
                                       [--cors-origins ORIGINS] [--no-smoke-test]

Cost: Lambda and HTTP API are pay-per-request (free tier covers a hackathon); idle cost is $0.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from botocore.exceptions import ClientError

import aws_common as c

FUNCTION_NAME = c.RAG_API_NAME
API_NAME = c.RAG_API_NAME
HANDLER = "backend.api.lambda_app.handler"
RUNTIME = "python3.13"
RUNTIME_PYTHON_VERSION = "3.13"
ARCHITECTURE = "arm64"
PIP_PLATFORM = "manylinux2014_aarch64"
MEMORY_MB = 1536  # more memory = more CPU: faster cold start + rule engine
TIMEOUT_S = 29  # API Gateway's integration timeout
PERMISSION_SID = "allow-apigateway-invoke"
PARAM_MODEL_FAST = f"{c.PARAM_PREFIX}/model_fast"
PARAM_MODEL_QUALITY = f"{c.PARAM_PREFIX}/model_quality"
LAMBDA_REQUIREMENTS = c.REPO_ROOT / "requirements-lambda.txt"

# Repo paths bundled into the package (relative to the repo root).
SOURCE_DIRS = ["backend"]
# rulesets/ sits next to backend/ so RuleEngine's default path (<root>/rulesets) resolves.
DATA_DIRS = ["rulesets", "data/guidelines/chunks"]
DATA_FILES = ["data/guidelines/guidelines_manifest.json"]
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}

# Fixed timestamp so identical inputs give a byte-identical zip (stable CodeSha256).
ZIP_DATE = (2020, 1, 1, 0, 0, 0)


# --------------------------------------------------------------------------- packaging

def _included(path: Path) -> bool:
    return not (EXCLUDE_PARTS & set(path.parts)) and path.suffix not in EXCLUDE_SUFFIXES


def package_files(repo_root: Path = c.REPO_ROOT) -> list[tuple[Path, str]]:
    """(source path, archive name) for the app code and guideline data, sorted."""
    files: list[tuple[Path, str]] = []
    for f in DATA_FILES:
        if not (repo_root / f).is_file():
            raise c.SetupError(f"{repo_root / f} not found; run `python -m scripts.scrape_guidelines` first")
    for d in SOURCE_DIRS + DATA_DIRS:
        root = repo_root / d
        if not root.is_dir():
            raise c.SetupError(f"{root} not found")
        for p in root.rglob("*"):
            rel = p.relative_to(repo_root)
            if p.is_file() and _included(rel):
                files.append((p, rel.as_posix()))
    for f in DATA_FILES:
        p = repo_root / f
        if not p.is_file():
            raise c.SetupError(f"{p} not found; run `python -m scripts.scrape_guidelines` first")
        files.append((p, f))
    return sorted(files, key=lambda t: t[1])


def install_dependencies(target: Path, requirements: Path = LAMBDA_REQUIREMENTS) -> None:
    """pip-install Lambda-compatible (manylinux, arm64) wheels into ``target``."""
    cmd = [sys.executable, "-m", "pip", "install", "--quiet", "--disable-pip-version-check",
           "--target", str(target), "--platform", PIP_PLATFORM, "--implementation", "cp",
           "--python-version", RUNTIME_PYTHON_VERSION, "--only-binary=:all:",
           "--requirement", str(requirements)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise c.SetupError(f"pip install for the Lambda package failed:\n{result.stderr.strip()}")


def dependency_files(deps_dir: Path) -> list[tuple[Path, str]]:
    files = []
    for p in deps_dir.rglob("*"):
        rel = p.relative_to(deps_dir)
        if p.is_file() and _included(rel) and rel.parts[0] != "bin":
            files.append((p, rel.as_posix()))
    return sorted(files, key=lambda t: t[1])


def write_zip(files: list[tuple[Path, str]], out: Path) -> None:
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, name in files:
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, src.read_bytes())


def code_sha256(data: bytes) -> str:
    """Lambda's CodeSha256 format: base64 of the SHA-256 digest."""
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def build_package(work_dir: Path) -> bytes:
    deps = work_dir / "deps"
    install_dependencies(deps)
    files = dependency_files(deps) + package_files()
    out = work_dir / "rag_api.zip"
    write_zip(files, out)
    return out.read_bytes()


# --------------------------------------------------------------------------- Lambda

def function_environment(kb_id: str | None, cors_origins: str, model_fast: str | None = None,
                         model_quality: str | None = None) -> dict[str, str]:
    env = {"UIC_RAG_BACKEND": "auto", "UIC_LOG_LEVEL": "INFO", "UIC_CORS_ORIGINS": cors_origins}
    if kb_id:
        env["UIC_KB_ID"] = kb_id
    if model_fast:
        env["UIC_MODEL_FAST"] = model_fast
    if model_quality:
        env["UIC_MODEL_QUALITY"] = model_quality
    return env


def function_config(role_arn: str, env: dict[str, str]) -> dict:
    return {
        "Role": role_arn,
        "Handler": HANDLER,
        "Runtime": RUNTIME,
        "Timeout": TIMEOUT_S,
        "MemorySize": MEMORY_MB,
        "Environment": {"Variables": env},
        "LoggingConfig": {"LogFormat": "Text", "LogGroup": c.LOG_GROUP_NAME},
    }


def config_drift(current: dict, desired: dict) -> list[str]:
    """Names of settings in ``desired`` that differ from get_function's Configuration."""
    drift = []
    for key, want in desired.items():
        have = current.get(key)
        if key == "Environment":
            have = (have or {}).get("Variables", {})
            want = want["Variables"]
        elif key == "LoggingConfig":
            have = {k: (have or {}).get(k) for k in want}
        if have != want:
            drift.append(key)
    return drift


def get_function(ctx: c.Ctx) -> dict | None:
    if ctx.offline:
        return None
    try:
        return ctx.client("lambda").get_function(FunctionName=FUNCTION_NAME)["Configuration"]
    except ClientError as exc:
        if c.error_code(exc) == "ResourceNotFoundException":
            return None
        raise


def _create_function(ctx: c.Ctx, config: dict, zip_bytes: bytes) -> dict:
    lam = ctx.client("lambda")
    kwargs = dict(FunctionName=FUNCTION_NAME, Code={"ZipFile": zip_bytes},
                  Architectures=[ARCHITECTURE], Description="UIC Editorial Assistant integrated "
                  "backend API", Tags=c.TAGS, **config)
    # A just-created/updated role can take a few seconds to become assumable by Lambda.
    for attempt in range(6):
        try:
            return lam.create_function(**kwargs)
        except ClientError as exc:
            msg = str(exc).lower()
            if (c.error_code(exc) == "InvalidParameterValueException"
                    and "role" in msg and attempt < 5):
                c.log(f"  role not assumable yet; retrying in 5s ({attempt + 1}/5)")
                time.sleep(5)
                continue
            raise
    raise AssertionError("unreachable")


def ensure_function(ctx: c.Ctx, config: dict, zip_bytes: bytes) -> str:
    """Create or update the function; returns its ARN."""
    c.step(f"Lambda function {FUNCTION_NAME}")
    lam = ctx.client("lambda")
    current = get_function(ctx)
    if current is None:
        created = ctx.mutate(f"create Lambda function {FUNCTION_NAME} ({RUNTIME}, {ARCHITECTURE}, "
                             f"{len(zip_bytes) / 1e6:.1f} MB)", _create_function, ctx, config,
                             zip_bytes)
        if created is None:  # dry-run
            return f"arn:aws:lambda:{ctx.region}:{ctx.account_id}:function:{FUNCTION_NAME}"
        lam.get_waiter("function_active_v2").wait(FunctionName=FUNCTION_NAME)
        c.ok("function is Active")
        return created["FunctionArn"]

    if current.get("Architectures") != [ARCHITECTURE]:
        raise c.SetupError(f"{FUNCTION_NAME} exists with architectures "
                           f"{current.get('Architectures')}; delete it or change ARCHITECTURE")
    if current.get("CodeSha256") == code_sha256(zip_bytes):
        c.ok("code unchanged")
    else:
        ctx.mutate("upload new function code", lam.update_function_code,
                   FunctionName=FUNCTION_NAME, ZipFile=zip_bytes)
        if not ctx.dry_run:
            lam.get_waiter("function_updated_v2").wait(FunctionName=FUNCTION_NAME)
    drift = config_drift(current, config)
    if drift:
        ctx.mutate(f"update function configuration ({', '.join(drift)})",
                   lam.update_function_configuration, FunctionName=FUNCTION_NAME, **config)
        if not ctx.dry_run:
            lam.get_waiter("function_updated_v2").wait(FunctionName=FUNCTION_NAME)
    else:
        c.ok("configuration up to date")
    return current["FunctionArn"]


# --------------------------------------------------------------------------- API Gateway

def find_api(ctx: c.Ctx) -> dict | None:
    if ctx.offline:
        return None
    gw = ctx.client("apigatewayv2")
    token = None
    while True:
        page = gw.get_apis(**({"NextToken": token} if token else {}))
        for api in page.get("Items", []):
            if api.get("Name") == API_NAME:
                return api
        token = page.get("NextToken")
        if not token:
            return None


def ensure_api(ctx: c.Ctx, function_arn: str) -> tuple[str, str]:
    """Create the HTTP API (quick create: $default route + stage → Lambda). Returns (id, url)."""
    c.step(f"HTTP API {API_NAME}")
    api = find_api(ctx)
    if api is None:
        api = ctx.mutate(f"create HTTP API {API_NAME} ($default route → {FUNCTION_NAME})",
                         ctx.client("apigatewayv2").create_api, Name=API_NAME,
                         ProtocolType="HTTP", Target=function_arn, Tags=c.TAGS)
        if api is None:  # dry-run
            return "DRYRUNAPI", f"https://DRYRUNAPI.execute-api.{ctx.region}.amazonaws.com"
    else:
        c.ok(f"HTTP API exists ({api['ApiId']})")
    return api["ApiId"], api["ApiEndpoint"]


def ensure_invoke_permission(ctx: c.Ctx, api_id: str) -> None:
    c.step("Lambda invoke permission for API Gateway")
    source_arn = f"arn:aws:execute-api:{ctx.region}:{ctx.account_id}:{api_id}/*/*"
    if not ctx.offline:
        try:
            policy = json.loads(ctx.client("lambda").get_policy(FunctionName=FUNCTION_NAME)["Policy"])
            for stmt in policy.get("Statement", []):
                cond = stmt.get("Condition", {}).get("ArnLike", {}).get("AWS:SourceArn")
                if stmt.get("Sid") == PERMISSION_SID and cond == source_arn:
                    c.ok("permission already granted")
                    return
                if stmt.get("Sid") == PERMISSION_SID:  # stale (e.g. API was recreated)
                    ctx.mutate("remove stale invoke permission",
                               ctx.client("lambda").remove_permission,
                               FunctionName=FUNCTION_NAME, StatementId=PERMISSION_SID)
        except ClientError as exc:
            if c.error_code(exc) != "ResourceNotFoundException":
                raise
    ctx.mutate(f"allow {source_arn} to invoke {FUNCTION_NAME}",
               ctx.client("lambda").add_permission, FunctionName=FUNCTION_NAME,
               StatementId=PERMISSION_SID, Action="lambda:InvokeFunction",
               Principal="apigateway.amazonaws.com", SourceArn=source_arn)


# --------------------------------------------------------------------------- smoke test

def smoke_test(url: str, attempts: int = 5) -> dict:
    """GET <url>/api/rag/health; retries briefly while a fresh deployment propagates."""
    c.step("Smoke test")
    last = None
    for i in range(attempts):
        try:
            with urllib.request.urlopen(f"{url}/api/rag/health", timeout=30) as resp:
                body = json.loads(resp.read())
            c.ok(f"GET /api/rag/health → {body}")
            return body
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(3 * (i + 1))
    raise c.SetupError(f"health check failed at {url}/api/rag/health: {last}")


# --------------------------------------------------------------------------- main

def run(ctx: c.Ctx, args: argparse.Namespace) -> dict:
    c.verify_credentials(ctx)
    kb_id = None if ctx.offline else c.get_parameter(ctx, c.PARAM_KNOWLEDGE_BASE_ID)
    if not kb_id:
        c.warn("no /uic-editorial/knowledge_base_id; the API will serve local search only")
    model_fast = None if ctx.offline else c.get_parameter(ctx, PARAM_MODEL_FAST)
    model_quality = None if ctx.offline else c.get_parameter(ctx, PARAM_MODEL_QUALITY)
    if not (model_fast and model_quality):
        c.warn("no /uic-editorial/model_fast|model_quality; the app will use its built-in default models")
    role_arn = c.ensure_lambda_role(ctx, kb_id)

    c.step("Building Lambda package")
    with tempfile.TemporaryDirectory(prefix="uic-rag-lambda-") as tmp:
        zip_bytes = build_package(Path(tmp))
    c.ok(f"{len(zip_bytes) / 1e6:.1f} MB, CodeSha256 {code_sha256(zip_bytes)}")

    config = function_config(role_arn, function_environment(kb_id, args.cors_origins, model_fast,
                                                            model_quality))
    function_arn = ensure_function(ctx, config, zip_bytes)
    api_id, url = ensure_api(ctx, function_arn)
    ensure_invoke_permission(ctx, api_id)

    c.step("Parameter Store")
    c.ensure_parameter(ctx, c.PARAM_RAG_API_URL, url, "Base URL of the Workstream 1 RAG API")

    health = None
    if not ctx.dry_run and not args.no_smoke_test:
        health = smoke_test(url)

    c.step("Summary" + (" (dry-run, nothing changed)" if ctx.dry_run else ""))
    for k, v in [("function", FUNCTION_NAME), ("api_id", api_id), ("url", url),
                 ("docs", f"{url}/docs"), ("knowledge_base_id", kb_id),
                 ("model_fast", model_fast), ("model_quality", model_quality),
                 ("backend", (health or {}).get("backend"))]:
        c.log(f"  {k:<18} {v}")
    return {"function_arn": function_arn, "api_id": api_id, "url": url, "health": health}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    c.add_common_args(parser)
    parser.add_argument("--cors-origins", default="*",
                        help="comma-separated allowed browser origins (default: *)")
    parser.add_argument("--no-smoke-test", action="store_true",
                        help="skip the GET /api/rag/health check after deploying")
    args = parser.parse_args(argv)

    def body() -> int:
        run(c.make_context(args), args)
        return 0

    return c.run_main(body)


if __name__ == "__main__":
    sys.exit(main())
