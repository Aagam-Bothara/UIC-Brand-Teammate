#!/usr/bin/env python3
"""Task 1.1: base AWS setup for the UIC Editorial Assistant.

Creates (idempotently, safe to re-run):
  * IAM role ``uic-editorial-lambda-role``: backend Lambda execution role
    (policy: infra/iam/lambda-execution-policy.json). It can write CloudWatch Logs, read
    ``/uic-editorial/*`` parameters, Retrieve from the guidelines Knowledge Base, and
    InvokeModel (Anthropic/Amazon models and inference profiles).
  * IAM role ``uic-editorial-kb-role``: Bedrock Knowledge Base service role
    (trust: bedrock.amazonaws.com with aws:SourceAccount and aws:SourceArn conditions; policy:
    infra/iam/kb-service-policy.json). It can read s3://<guidelines bucket>/guidelines/*,
    invoke Titan Text Embeddings V2, and read/write the S3 Vectors index.
  * SSM parameters ``/uic-editorial/region`` and ``/uic-editorial/environment``.
  * CloudWatch log group ``/uic-editorial/backend`` with 14-day retention.

The guidelines and vector bucket names in the KB role policy default to the names the later
scripts use (or the values already stored in Parameter Store). setup_knowledge_base.py
re-applies both role policies with the final names and narrows the Lambda policy to the
specific KB ARN.

Usage:
  python scripts/aws/setup_base.py [--region us-east-1] [--profile NAME] [--dry-run]
                                   [--environment dev]

Cost: IAM roles, standard SSM parameters and an empty log group are free. Logs cost
$0.50/GB ingested; 14-day retention keeps storage negligible.
"""

from __future__ import annotations

import argparse
import sys

from botocore.exceptions import ClientError

import aws_common as c


def ensure_log_group(ctx: c.Ctx, name: str = c.LOG_GROUP_NAME,
                     retention_days: int = c.LOG_RETENTION_DAYS) -> None:
    logs = ctx.client("logs")
    existing = None
    if not ctx.offline:
        resp = logs.describe_log_groups(logGroupNamePrefix=name)
        existing = next((g for g in resp.get("logGroups", []) if g["logGroupName"] == name), None)
    if existing is None:
        try:
            ctx.mutate(f"create log group {name}", logs.create_log_group,
                       logGroupName=name, tags=c.TAGS)
        except ClientError as exc:  # created concurrently
            if c.error_code(exc) != "ResourceAlreadyExistsException":
                raise
    else:
        c.ok(f"log group {name} exists")
    if existing is not None and existing.get("retentionInDays") == retention_days:
        c.ok(f"log group retention is {retention_days} days")
    else:
        ctx.mutate(f"set retention of {name} to {retention_days} days",
                   logs.put_retention_policy, logGroupName=name,
                   retentionInDays=retention_days)


def run(ctx: c.Ctx, args: argparse.Namespace) -> dict:
    c.verify_credentials(ctx)

    guidelines_bucket = (args.bucket or c.get_parameter(ctx, c.PARAM_GUIDELINES_BUCKET)
                         or c.default_guidelines_bucket(ctx.account_id, ctx.region))
    vector_bucket = (args.vector_bucket or c.get_parameter(ctx, c.PARAM_VECTOR_BUCKET)
                     or c.default_vector_bucket(ctx.account_id, ctx.region))
    kb_id = c.get_parameter(ctx, c.PARAM_KNOWLEDGE_BASE_ID)

    c.step("IAM: backend Lambda execution role")
    lambda_role_arn = c.ensure_lambda_role(ctx, kb_id)

    c.step("IAM: Bedrock Knowledge Base service role")
    kb_role_arn = c.ensure_kb_role(ctx, guidelines_bucket, vector_bucket)

    c.step(f"Parameter Store namespace {c.PARAM_PREFIX}/")
    c.ensure_parameter(ctx, c.PARAM_REGION, ctx.region, "AWS region of the UIC Editorial stack")
    c.ensure_parameter(ctx, c.PARAM_ENVIRONMENT, args.environment,
                       "Deployment environment name")

    c.step("CloudWatch Logs")
    ensure_log_group(ctx)

    result = {
        "account_id": ctx.account_id,
        "region": ctx.region,
        "lambda_role_arn": lambda_role_arn,
        "kb_role_arn": kb_role_arn,
        "log_group": c.LOG_GROUP_NAME,
    }
    c.step("Summary" + (" (dry-run, nothing changed)" if ctx.dry_run else ""))
    for key, value in result.items():
        c.log(f"  {key:16} {value}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    c.add_common_args(parser)
    parser.add_argument("--environment", default="dev",
                        help="value for /uic-editorial/environment (default: dev)")
    parser.add_argument("--bucket", default=None,
                        help="guidelines bucket name used in the KB role policy "
                             "(default: Parameter Store value or uic-editorial-guidelines-<account>-<region>)")
    parser.add_argument("--vector-bucket", default=None,
                        help="S3 Vectors bucket name used in the KB role policy "
                             "(default: uic-editorial-vectors-<account>-<region>)")
    args = parser.parse_args(argv)

    def body() -> int:
        run(c.make_context(args), args)
        return 0

    return c.run_main(body)


if __name__ == "__main__":
    sys.exit(main())
