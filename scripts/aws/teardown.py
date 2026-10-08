#!/usr/bin/env python3
"""Delete everything the scripts/aws/setup_*.py scripts created, so costs stop.

Order: RAG API (HTTP API + Lambda function) -> Knowledge Base (data sources first) -> S3 Vectors index + bucket -> guidelines
bucket (every object version and delete marker) -> SSM parameters -> log group -> IAM roles.

Nothing is deleted unless you pass ``--yes``. Without it (or with ``--dry-run``) the script
only prints what it would delete. ``--components`` limits the scope, for example
``--components kb,vectors`` drops the KB and vector store but keeps the uploaded guidelines.

Usage:
  python scripts/aws/teardown.py [--region us-east-1] [--profile NAME] [--dry-run] --yes
         [--components api,kb,vectors,s3,ssm,logs,iam] [--all-params]

Only the parameters these scripts manage are deleted. ``--all-params`` deletes every
parameter under /uic-editorial/, including ones other workstreams added.
"""

from __future__ import annotations

import argparse
import sys

from botocore.exceptions import ClientError

import aws_common as c

COMPONENTS = ["api", "kb", "vectors", "s3", "ssm", "logs", "iam"]


def _gone(ctx: c.Ctx, fn, **kwargs) -> bool:
    """True once ``fn`` reports the resource as not found.

    A ``DELETE_UNSUCCESSFUL`` status is terminal (it never turns into "not found"), so it
    raises :class:`SetupError` straight away instead of polling until the timeout.
    """
    try:
        resp = fn(**kwargs)
    except ClientError as exc:
        if c.error_code(exc) in ("ResourceNotFoundException", "NotFoundException"):
            return True
        raise
    resource = (resp or {}).get("dataSource") or (resp or {}).get("knowledgeBase") or {}
    if resource.get("status") == "DELETE_UNSUCCESSFUL":
        hint = (" (set the data source's data deletion policy to RETAIN, then re-run)"
                if "dataSourceId" in kwargs else "")
        raise c.SetupError(f"deletion of {kwargs} failed (DELETE_UNSUCCESSFUL): "
                           f"{resource.get('failureReasons')}{hint}")
    return False


def teardown_kb(ctx: c.Ctx, kb_id: str | None, timeout: float, interval: float) -> None:
    c.step("Bedrock Knowledge Base")
    if ctx.offline:
        c.warn("offline: cannot look up the Knowledge Base")
        return
    agent = ctx.client("bedrock-agent")
    ids = set()
    if kb_id:
        ids.add(kb_id)
    for page in agent.get_paginator("list_knowledge_bases").paginate():
        ids.update(kb["knowledgeBaseId"] for kb in page.get("knowledgeBaseSummaries", [])
                   if kb["name"] == c.KB_NAME)
    if not ids:
        c.ok("no Knowledge Base found")
        return
    for kid in sorted(ids):
        try:
            sources = [ds for page in agent.get_paginator("list_data_sources").paginate(
                knowledgeBaseId=kid) for ds in page.get("dataSourceSummaries", [])]
        except ClientError as exc:
            if c.error_code(exc) == "ResourceNotFoundException":
                c.ok(f"KB {kid} already deleted")
                continue
            raise
        for ds in sources:
            ds_id = ds["dataSourceId"]
            ctx.mutate(f"delete data source {ds['name']} ({ds_id}) of KB {kid}",
                       agent.delete_data_source, knowledgeBaseId=kid, dataSourceId=ds_id)
            if not ctx.dry_run:
                try:
                    c.wait_until(lambda: _gone(ctx, agent.get_data_source, knowledgeBaseId=kid,
                                               dataSourceId=ds_id),
                                 timeout=timeout, interval=interval,
                                 what=f"data source {ds_id} deletion")
                except c.SetupError as exc:
                    c.warn(f"{exc}; continuing with KB deletion")
        ctx.mutate(f"delete Knowledge Base {kid}", agent.delete_knowledge_base,
                   knowledgeBaseId=kid)
        if not ctx.dry_run:
            c.wait_until(lambda: _gone(ctx, agent.get_knowledge_base, knowledgeBaseId=kid),
                         timeout=timeout, interval=interval, what=f"KB {kid} deletion")
            c.ok(f"KB {kid} deleted")


def teardown_vectors(ctx: c.Ctx, vector_bucket: str) -> None:
    c.step(f"S3 Vectors bucket {vector_bucket}")
    if ctx.offline:
        c.warn("offline: cannot look up the vector bucket")
        return
    s3v = ctx.client("s3vectors")
    try:
        s3v.get_vector_bucket(vectorBucketName=vector_bucket)
    except ClientError as exc:
        if c.error_code(exc) == "NotFoundException":
            c.ok("not found")
            return
        raise
    for page in s3v.get_paginator("list_indexes").paginate(vectorBucketName=vector_bucket):
        for index in page.get("indexes", []):
            ctx.mutate(f"delete vector index {index['indexName']}", s3v.delete_index,
                       vectorBucketName=vector_bucket, indexName=index["indexName"])
    ctx.mutate(f"delete vector bucket {vector_bucket}", s3v.delete_vector_bucket,
               vectorBucketName=vector_bucket)


def teardown_bucket(ctx: c.Ctx, bucket: str) -> None:
    c.step(f"S3 bucket {bucket}")
    if ctx.offline:
        c.warn("offline: cannot look up the bucket")
        return
    s3 = ctx.client("s3")
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as exc:
        if c.error_code(exc) in ("404", "NoSuchBucket", "NotFound"):
            c.ok("not found")
            return
        raise
    total = 0
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
        objects = [{"Key": v["Key"], "VersionId": v["VersionId"]}
                   for v in page.get("Versions", []) + page.get("DeleteMarkers", [])]
        if objects:
            total += len(objects)
            resp = ctx.mutate(f"delete {len(objects)} object version(s)/delete marker(s)",
                              s3.delete_objects, Bucket=bucket,
                              Delete={"Objects": objects, "Quiet": True})
            errors = (resp or {}).get("Errors", [])
            if errors:
                first = errors[0]
                raise c.SetupError(
                    f"could not delete {len(errors)} object version(s) from {bucket} "
                    f"(first: {first.get('Key')}: {first.get('Code')} {first.get('Message', '')}); "
                    "the bucket was not deleted")
    if not total:
        c.ok("bucket is empty")
    ctx.mutate(f"delete bucket {bucket}", s3.delete_bucket, Bucket=bucket)


def teardown_parameters(ctx: c.Ctx, all_params: bool) -> None:
    c.step(f"Parameter Store {c.PARAM_PREFIX}/")
    if ctx.offline:
        c.warn("offline: cannot look up parameters")
        return
    ssm = ctx.client("ssm")
    if all_params:
        names = [p["Name"] for page in ssm.get_paginator("get_parameters_by_path").paginate(
            Path=c.PARAM_PREFIX, Recursive=True) for p in page.get("Parameters", [])]
    else:
        names = [n for n in c.MANAGED_PARAMETERS if c.get_parameter(ctx, n) is not None]
    if not names:
        c.ok("no parameters found")
        return
    for i in range(0, len(names), 10):
        batch = names[i:i + 10]
        ctx.mutate(f"delete parameters {', '.join(batch)}", ssm.delete_parameters, Names=batch)


def teardown_log_group(ctx: c.Ctx) -> None:
    c.step(f"Log group {c.LOG_GROUP_NAME}")
    if ctx.offline:
        c.warn("offline: cannot look up the log group")
        return
    logs = ctx.client("logs")
    groups = logs.describe_log_groups(logGroupNamePrefix=c.LOG_GROUP_NAME).get("logGroups", [])
    if not any(g["logGroupName"] == c.LOG_GROUP_NAME for g in groups):
        c.ok("not found")
        return
    ctx.mutate(f"delete log group {c.LOG_GROUP_NAME}", logs.delete_log_group,
               logGroupName=c.LOG_GROUP_NAME)


def teardown_role(ctx: c.Ctx, role_name: str) -> None:
    c.step(f"IAM role {role_name}")
    if c.get_role(ctx, role_name) is None:
        c.ok("not found" if not ctx.offline else "offline: cannot look up the role")
        return
    iam = ctx.client("iam")
    for name in iam.list_role_policies(RoleName=role_name).get("PolicyNames", []):
        ctx.mutate(f"delete inline policy {name}", iam.delete_role_policy,
                   RoleName=role_name, PolicyName=name)
    for pol in iam.list_attached_role_policies(RoleName=role_name).get("AttachedPolicies", []):
        ctx.mutate(f"detach managed policy {pol['PolicyArn']}", iam.detach_role_policy,
                   RoleName=role_name, PolicyArn=pol["PolicyArn"])
    ctx.mutate(f"delete role {role_name}", iam.delete_role, RoleName=role_name)


def teardown_api(ctx: c.Ctx) -> None:
    """Delete the RAG API's HTTP API and Lambda function (deploy_rag_api.py)."""
    c.step(f"RAG API {c.RAG_API_NAME}")
    if ctx.offline:
        c.ok("offline: cannot look up the API or function")
        return
    gw = ctx.client("apigatewayv2")
    apis, token = [], None
    while True:
        page = gw.get_apis(**({"NextToken": token} if token else {}))
        apis += [a for a in page.get("Items", []) if a.get("Name") == c.RAG_API_NAME]
        token = page.get("NextToken")
        if not token:
            break
    for api in apis:
        ctx.mutate(f"delete HTTP API {api['ApiId']}", gw.delete_api, ApiId=api["ApiId"])
    if not apis:
        c.ok("HTTP API not found")
    lam = ctx.client("lambda")
    try:
        lam.get_function(FunctionName=c.RAG_API_NAME)
    except ClientError as exc:
        if c.error_code(exc) != "ResourceNotFoundException":
            raise
        c.ok("Lambda function not found")
        return
    ctx.mutate(f"delete Lambda function {c.RAG_API_NAME}", lam.delete_function,
               FunctionName=c.RAG_API_NAME)


def parse_components(value: str) -> list[str]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    unknown = sorted(set(parts) - set(COMPONENTS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown component(s) {unknown}; choose from {COMPONENTS}")
    return parts


def run(ctx: c.Ctx, args: argparse.Namespace) -> None:
    c.verify_credentials(ctx)
    comps = args.components
    # Resolve names before the parameters that store them are deleted.
    kb_id = c.get_parameter(ctx, c.PARAM_KNOWLEDGE_BASE_ID)
    bucket = (args.bucket or c.get_parameter(ctx, c.PARAM_GUIDELINES_BUCKET)
              or c.default_guidelines_bucket(ctx.account_id, ctx.region))
    vector_bucket = (args.vector_bucket or c.get_parameter(ctx, c.PARAM_VECTOR_BUCKET)
                     or c.default_vector_bucket(ctx.account_id, ctx.region))

    if "api" in comps:
        teardown_api(ctx)
    if "kb" in comps:
        teardown_kb(ctx, kb_id, args.timeout, args.poll_interval)
    if "vectors" in comps:
        teardown_vectors(ctx, vector_bucket)
    if "s3" in comps:
        teardown_bucket(ctx, bucket)
    if "ssm" in comps:
        teardown_parameters(ctx, args.all_params)
    if "logs" in comps:
        teardown_log_group(ctx)
    if "iam" in comps:
        teardown_role(ctx, c.LAMBDA_ROLE_NAME)
        teardown_role(ctx, c.KB_ROLE_NAME)

    c.step("Done" + (" (dry-run, nothing deleted)" if ctx.dry_run else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    c.add_common_args(parser)
    parser.add_argument("--yes", action="store_true", help="actually delete (required)")
    parser.add_argument("--components", type=parse_components, default=list(COMPONENTS),
                        help=f"comma-separated subset of {','.join(COMPONENTS)} (default: all)")
    parser.add_argument("--all-params", action="store_true",
                        help=f"delete every parameter under {c.PARAM_PREFIX}/ (not just ours)")
    parser.add_argument("--bucket", default=None, help="guidelines bucket (default: from SSM)")
    parser.add_argument("--vector-bucket", default=None, help="vector bucket (default: from SSM)")
    parser.add_argument("--timeout", type=float, default=600, help="wait timeout per deletion")
    parser.add_argument("--poll-interval", type=float, default=10, help="poll interval seconds")
    args = parser.parse_args(argv)

    if not args.yes and not args.dry_run:
        c.log("Refusing to delete without --yes. Showing the plan instead (dry-run):")
        args.dry_run = True
        plan_only = True
    else:
        plan_only = False

    def body() -> int:
        run(c.make_context(args), args)
        if plan_only:
            c.log("\nNothing was deleted. Re-run with --yes to delete these resources.")
            return 1
        return 0

    return c.run_main(body)


if __name__ == "__main__":
    sys.exit(main())
