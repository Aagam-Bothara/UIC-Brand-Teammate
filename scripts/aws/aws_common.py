"""Shared helpers for the UIC Editorial Assistant AWS setup scripts (Workstream 1).

Every setup script is idempotent: it looks up each resource first and only creates or
changes what is missing or different. ``--dry-run`` prints the planned mutating calls
without making them (read-only lookups still run). If no AWS credentials are available,
``--dry-run`` falls back to an *offline* preview that assumes nothing exists yet and uses
the placeholder account id ``000000000000``.

Names here are binding for the rest of the project (see docs/API_CONTRACT.md):
Parameter Store namespace ``/uic-editorial/`` and log group ``/uic-editorial/backend``.
"""

from __future__ import annotations

import argparse
import json
import string
import sys
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import boto3
from botocore.exceptions import BotoCoreError, ClientError

REPO_ROOT = Path(__file__).resolve().parents[2]
IAM_POLICY_DIR = REPO_ROOT / "infra" / "iam"
DEFAULT_CHUNKS_DIR = REPO_ROOT / "data" / "guidelines" / "chunks"

DEFAULT_REGION = "us-east-1"
PLACEHOLDER_ACCOUNT_ID = "000000000000"

PROJECT = "uic-editorial"
TAGS = {"Project": PROJECT, "ManagedBy": "scripts/aws"}

# Parameter Store (binding names from docs/API_CONTRACT.md).
PARAM_PREFIX = "/uic-editorial"
PARAM_REGION = f"{PARAM_PREFIX}/region"
PARAM_ENVIRONMENT = f"{PARAM_PREFIX}/environment"
PARAM_GUIDELINES_BUCKET = f"{PARAM_PREFIX}/guidelines_bucket"
PARAM_KNOWLEDGE_BASE_ID = f"{PARAM_PREFIX}/knowledge_base_id"
PARAM_DATA_SOURCE_ID = f"{PARAM_PREFIX}/data_source_id"
PARAM_VECTOR_BUCKET = f"{PARAM_PREFIX}/vector_bucket"
PARAM_RAG_API_URL = f"{PARAM_PREFIX}/rag_api_url"
MANAGED_PARAMETERS = [
    PARAM_REGION,
    PARAM_ENVIRONMENT,
    PARAM_GUIDELINES_BUCKET,
    PARAM_KNOWLEDGE_BASE_ID,
    PARAM_DATA_SOURCE_ID,
    PARAM_VECTOR_BUCKET,
    PARAM_RAG_API_URL,
]

LOG_GROUP_NAME = "/uic-editorial/backend"
LOG_RETENTION_DAYS = 14

LAMBDA_ROLE_NAME = "uic-editorial-lambda-role"
LAMBDA_POLICY_NAME = "uic-editorial-lambda-policy"
KB_ROLE_NAME = "uic-editorial-kb-role"
KB_POLICY_NAME = "uic-editorial-kb-policy"

# Lambda function and HTTP API for the RAG API (deploy_rag_api.py).
RAG_API_NAME = "uic-editorial-rag-api"

GUIDELINES_PREFIX = "guidelines/"
VECTOR_INDEX_NAME = "uic-editorial-guidelines"
KB_NAME = "uic-editorial-guidelines-kb"
DATA_SOURCE_NAME = "uic-editorial-guidelines-s3"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS = 1024


class SetupError(Exception):
    """A fatal, user-facing setup problem (printed without a traceback)."""


# --------------------------------------------------------------------------- output

def log(msg: str = "") -> None:
    print(msg, flush=True)


def step(title: str) -> None:
    log(f"\n== {title} ==")


def ok(msg: str) -> None:
    log(f"  [ok]      {msg}")


def change(msg: str) -> None:
    log(f"  [change]  {msg}")


def warn(msg: str) -> None:
    log(f"  [warning] {msg}")


# --------------------------------------------------------------------------- naming

def default_guidelines_bucket(account_id: str, region: str) -> str:
    return f"uic-editorial-guidelines-{account_id}-{region}"


def default_vector_bucket(account_id: str, region: str) -> str:
    return f"uic-editorial-vectors-{account_id}-{region}"


def knowledge_base_arn(region: str, account_id: str, kb_id: str = "*") -> str:
    return f"arn:aws:bedrock:{region}:{account_id}:knowledge-base/{kb_id}"


def embedding_model_arn(region: str, model_id: str = EMBEDDING_MODEL_ID) -> str:
    return f"arn:aws:bedrock:{region}::foundation-model/{model_id}"


def vector_bucket_arn(region: str, account_id: str, bucket: str) -> str:
    return f"arn:aws:s3vectors:{region}:{account_id}:bucket/{bucket}"


def vector_index_arn(region: str, account_id: str, bucket: str, index: str) -> str:
    return f"{vector_bucket_arn(region, account_id, bucket)}/index/{index}"


def tag_list(tags: dict[str, str] | None = None) -> list[dict[str, str]]:
    return [{"Key": k, "Value": v} for k, v in (tags or TAGS).items()]


def error_code(exc: ClientError) -> str:
    return exc.response.get("Error", {}).get("Code", "")


# --------------------------------------------------------------------------- context

@dataclass
class Ctx:
    """Per-run state: region, session, account, dry-run/offline flags, cached clients."""

    region: str = DEFAULT_REGION
    dry_run: bool = False
    session: Any = None
    account_id: str = PLACEHOLDER_ACCOUNT_ID
    offline: bool = False
    _clients: dict = field(default_factory=dict)

    def client(self, name: str):
        if name not in self._clients:
            session = self.session or boto3.Session()
            self._clients[name] = session.client(name, region_name=self.region)
        return self._clients[name]

    def mutate(self, description: str, fn: Callable, /, *args, quiet: bool = False, **kwargs):
        """Run a mutating AWS call, or just announce it in dry-run mode."""
        if self.dry_run:
            if not quiet:
                log(f"  [dry-run] would {description}")
            return None
        if not quiet:
            change(description)
        return fn(*args, **kwargs)


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--region", default=DEFAULT_REGION,
                        help=f"AWS region (default: {DEFAULT_REGION})")
    parser.add_argument("--profile", default=None,
                        help="AWS named profile to use (default: standard credential chain)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print planned changes without calling mutating APIs")


def make_context(args: argparse.Namespace) -> Ctx:
    try:
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
    except BotoCoreError as exc:  # e.g. ProfileNotFound
        raise SetupError(f"Could not create an AWS session: {exc}") from exc
    return Ctx(region=args.region, dry_run=args.dry_run, session=session)


CREDENTIALS_HELP = """\
No usable AWS credentials were found ({detail}).

Log in first, then re-run this script. For example:
  aws configure                       # long-lived access keys
  aws sso login --profile <profile>   # IAM Identity Center; then pass --profile <profile>
  export AWS_PROFILE=<profile>        # or select a profile for the whole shell
Check with: aws sts get-caller-identity"""


def verify_credentials(ctx: Ctx) -> dict | None:
    """Resolve the caller identity; friendly error (or offline preview in dry-run)."""
    step("Verifying AWS credentials")
    try:
        ident = ctx.client("sts").get_caller_identity()
    except (BotoCoreError, ClientError) as exc:
        if ctx.dry_run:
            warn(f"no usable credentials ({exc.__class__.__name__}); continuing as an OFFLINE "
                 f"dry-run with placeholder account {PLACEHOLDER_ACCOUNT_ID} and assuming "
                 "no resources exist yet")
            ctx.offline = True
            ctx.account_id = PLACEHOLDER_ACCOUNT_ID
            return None
        raise SetupError(CREDENTIALS_HELP.format(detail=f"{exc.__class__.__name__}: {exc}")) from exc
    ctx.account_id = ident["Account"]
    ok(f"account {ident['Account']} as {ident['Arn']} (region {ctx.region})")
    return ident


def run_main(fn: Callable[[], int]) -> int:
    """Wrap a script's main body: SetupError -> clean message + exit code 2."""
    try:
        return fn()
    except SetupError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return 2
    except ClientError as exc:
        err = exc.response.get("Error", {})
        print(f"\nAWS ERROR during {exc.operation_name}: {err.get('Code')}: {err.get('Message')}",
              file=sys.stderr)
        return 1
    except BotoCoreError as exc:
        print(f"\nAWS ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


def wait_until(check: Callable[[], bool], *, timeout: float, interval: float,
               what: str) -> None:
    """Poll ``check`` until it returns True or ``timeout`` seconds pass."""
    deadline = time.monotonic() + timeout
    while True:
        if check():
            return
        if time.monotonic() >= deadline:
            raise SetupError(f"Timed out after {timeout:.0f}s waiting for {what}")
        time.sleep(interval)


# --------------------------------------------------------------------------- IAM policies

def render_policy(filename: str, variables: dict[str, str]) -> dict:
    """Load infra/iam/<filename> and substitute ${VAR} placeholders."""
    path = IAM_POLICY_DIR / filename
    try:
        text = string.Template(path.read_text(encoding="utf-8")).substitute(variables)
    except KeyError as exc:
        raise SetupError(f"{path} uses placeholder {exc} that was not provided") from exc
    return json.loads(text)


def lambda_policy_variables(ctx: Ctx, kb_id: str | None) -> dict[str, str]:
    return {
        "ACCOUNT_ID": ctx.account_id,
        "REGION": ctx.region,
        "PROJECT": PROJECT,
        "LOG_GROUP": LOG_GROUP_NAME,
        "PARAM_PREFIX": PARAM_PREFIX,
        # Until the KB exists we scope to this account+region's KBs; setup_knowledge_base.py
        # narrows it to the single KB ARN once the id is known.
        "KNOWLEDGE_BASE_ARN": knowledge_base_arn(ctx.region, ctx.account_id, kb_id or "*"),
    }


def kb_policy_variables(ctx: Ctx, guidelines_bucket: str, vector_bucket: str,
                        vector_index: str = VECTOR_INDEX_NAME,
                        prefix: str = GUIDELINES_PREFIX) -> dict[str, str]:
    return {
        "ACCOUNT_ID": ctx.account_id,
        "REGION": ctx.region,
        "EMBEDDING_MODEL_ID": EMBEDDING_MODEL_ID,
        "GUIDELINES_BUCKET": guidelines_bucket,
        "GUIDELINES_PREFIX": prefix,
        "VECTOR_BUCKET": vector_bucket,
        "VECTOR_INDEX": vector_index,
    }


def _as_policy_dict(doc: Any) -> dict:
    if isinstance(doc, str):
        return json.loads(urllib.parse.unquote(doc))
    return doc


def get_role(ctx: Ctx, role_name: str) -> dict | None:
    if ctx.offline:
        return None
    try:
        return ctx.client("iam").get_role(RoleName=role_name)["Role"]
    except ClientError as exc:
        if error_code(exc) == "NoSuchEntity":
            return None
        raise


def ensure_role(ctx: Ctx, role_name: str, trust_policy: dict, policy_name: str,
                policy: dict, description: str) -> str:
    """Create/update an IAM role and its single inline policy. Returns the role ARN."""
    iam = ctx.client("iam")
    role = get_role(ctx, role_name)
    if role is None:
        resp = ctx.mutate(f"create IAM role {role_name}", iam.create_role,
                          RoleName=role_name,
                          AssumeRolePolicyDocument=json.dumps(trust_policy),
                          Description=description, Tags=tag_list())
        arn = resp["Role"]["Arn"] if resp else f"arn:aws:iam::{ctx.account_id}:role/{role_name}"
        current_policy = None
    else:
        arn = role["Arn"]
        ok(f"IAM role {role_name} exists")
        if _as_policy_dict(role.get("AssumeRolePolicyDocument")) != trust_policy:
            ctx.mutate(f"update trust policy of {role_name}", iam.update_assume_role_policy,
                       RoleName=role_name, PolicyDocument=json.dumps(trust_policy))
        else:
            ok(f"trust policy of {role_name} up to date")
        try:
            current_policy = _as_policy_dict(iam.get_role_policy(
                RoleName=role_name, PolicyName=policy_name)["PolicyDocument"])
        except ClientError as exc:
            if error_code(exc) != "NoSuchEntity":
                raise
            current_policy = None

    if current_policy == policy:
        ok(f"inline policy {policy_name} up to date")
    else:
        verb = "attach" if current_policy is None else "update"
        ctx.mutate(f"{verb} inline policy {policy_name} on {role_name}", iam.put_role_policy,
                   RoleName=role_name, PolicyName=policy_name,
                   PolicyDocument=json.dumps(policy))
    return arn


def ensure_lambda_role(ctx: Ctx, kb_id: str | None = None) -> str:
    variables = lambda_policy_variables(ctx, kb_id)
    return ensure_role(
        ctx, LAMBDA_ROLE_NAME,
        render_policy("lambda-trust-policy.json", variables),
        LAMBDA_POLICY_NAME,
        render_policy("lambda-execution-policy.json", variables),
        "UIC Editorial Assistant backend Lambda execution role",
    )


def ensure_kb_role(ctx: Ctx, guidelines_bucket: str, vector_bucket: str,
                   vector_index: str = VECTOR_INDEX_NAME,
                   prefix: str = GUIDELINES_PREFIX) -> str:
    variables = kb_policy_variables(ctx, guidelines_bucket, vector_bucket, vector_index, prefix)
    return ensure_role(
        ctx, KB_ROLE_NAME,
        render_policy("kb-trust-policy.json", variables),
        KB_POLICY_NAME,
        render_policy("kb-service-policy.json", variables),
        "UIC Editorial Assistant Bedrock Knowledge Base service role",
    )


# --------------------------------------------------------------------------- Parameter Store

def get_parameter(ctx: Ctx, name: str) -> str | None:
    if ctx.offline:
        return None
    try:
        return ctx.client("ssm").get_parameter(Name=name)["Parameter"]["Value"]
    except ClientError as exc:
        if error_code(exc) == "ParameterNotFound":
            return None
        raise


def ensure_parameter(ctx: Ctx, name: str, value: str, description: str = "") -> bool:
    """Create or update a String parameter. Returns True if a change was (or would be) made."""
    ssm = ctx.client("ssm")
    current = get_parameter(ctx, name)
    if current == value:
        ok(f"parameter {name} = {value}")
        return False
    if current is None:
        ctx.mutate(f"create parameter {name} = {value}", ssm.put_parameter,
                   Name=name, Value=value, Type="String",
                   Description=description or f"UIC Editorial Assistant: {name}",
                   Tags=tag_list())
    else:
        ctx.mutate(f"update parameter {name}: {current} -> {value}", ssm.put_parameter,
                   Name=name, Value=value, Type="String", Overwrite=True)
    return True
