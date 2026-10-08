#!/usr/bin/env python3
"""Task 1.3: S3 bucket for the guideline chunks the Bedrock Knowledge Base ingests.

Idempotently (safe to re-run):
  * creates the bucket (default ``uic-editorial-guidelines-<account_id>-<region>``),
  * enables versioning, blocks all public access, sets default SSE-S3 (AES256) encryption,
  * uploads the chunks listed in data/guidelines/guidelines_manifest.json (``*.md`` and their
    ``*.md.metadata.json`` Bedrock sidecars) under the ``guidelines/`` prefix with correct
    content types, so the KB indexes exactly what the local backend serves. Chunk files on
    disk that the manifest does not list are reported and not uploaded (without a manifest,
    every chunk file is uploaded). Files whose MD5 already matches the object's ETag are
    skipped. ``--delete-stale`` removes objects under the prefix that are not part of that
    upload set, which keeps re-chunked guidelines from leaving orphan chunks in the KB.
  * stores the bucket name in ``/uic-editorial/guidelines_bucket``.

Run scripts/scrape_guidelines.py first so the chunks exist. After re-uploading, re-run
setup_knowledge_base.py (or just start an ingestion job) so the KB picks up the changes.

Usage:
  python scripts/aws/setup_s3.py [--region us-east-1] [--profile NAME] [--dry-run]
                                 [--bucket NAME] [--source-dir DIR] [--manifest FILE]
                                 [--delete-stale]

Cost: a few hundred small objects cost well under $0.01/month in S3 Standard.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from botocore.exceptions import ClientError

import aws_common as c

CONTENT_TYPES = {
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
}
UPLOAD_SUFFIXES = (".md", ".md.metadata.json")
SIDECAR_SUFFIX = ".metadata.json"
MANIFEST_NAME = "guidelines_manifest.json"
SHOW_FIRST_PROBLEMS = 20


def content_type_for(path: str | Path) -> str:
    return CONTENT_TYPES.get(Path(path).suffix.lower(), "application/octet-stream")


def md5_hex(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def collect_files(source_dir: Path) -> list[tuple[Path, str]]:
    """Return [(local_path, relative_posix_path)] for every chunk/sidecar under source_dir."""
    files = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        rel = path.relative_to(source_dir).as_posix()
        if rel.endswith(UPLOAD_SUFFIXES):
            files.append((path, rel))
        else:
            c.warn(f"skipping {rel}: not a .md chunk or .md.metadata.json sidecar")
    return files


def validate_sidecars(files: list[tuple[Path, str]]) -> list[str]:
    """Check every chunk has a well-formed Bedrock metadata sidecar. Returns problems."""
    rels = {rel for _, rel in files}
    problems = []
    for path, rel in files:
        if rel.endswith(".md") and f"{rel}.metadata.json" not in rels:
            problems.append(f"{rel}: missing {Path(rel).name}.metadata.json sidecar")
        elif rel.endswith(".md.metadata.json"):
            if rel[: -len(".metadata.json")] not in rels:
                problems.append(f"{rel}: sidecar without a matching chunk")
            try:
                attrs = json.loads(path.read_text(encoding="utf-8")).get("metadataAttributes")
                if not isinstance(attrs, dict):
                    problems.append(f"{rel}: no 'metadataAttributes' object")
            except (ValueError, AttributeError) as exc:
                problems.append(f"{rel}: invalid JSON ({exc})")
    return problems


def manifest_files(manifest_path: Path, source_dir: Path) -> set[str]:
    """Relative paths (chunk + sidecar, relative to source_dir) of every manifest chunk.

    Manifest chunk ``path`` values are relative to the manifest's directory
    (e.g. ``chunks/editorial-style-001.md``), see docs/API_CONTRACT.md.
    """
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        chunks = data["chunks"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise c.SetupError(f"Cannot read chunk list from {manifest_path}: {exc}") from exc
    base, src = manifest_path.parent.resolve(), source_dir.resolve()
    wanted: set[str] = set()
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        rel = chunk.get("path") or (f"chunks/{chunk['chunk_id']}.md" if chunk.get("chunk_id") else None)
        if not rel:
            continue
        try:
            rel_to_src = (base / rel).resolve().relative_to(src).as_posix()
        except ValueError:
            continue  # listed outside source_dir: not ours to upload
        wanted.update({rel_to_src, rel_to_src + SIDECAR_SUFFIX})
    return wanted


def select_files(source_dir: Path, manifest_path: Path | None,
                 required: bool = False) -> tuple[list[tuple[Path, str]], list[str]]:
    """Files to upload (manifest-listed chunks + sidecars) and problems to report.

    Without a manifest every chunk file under source_dir is selected (with a warning), unless
    ``required`` (an explicit --manifest) makes a missing manifest an error.
    """
    files = collect_files(source_dir)
    if manifest_path is None or not manifest_path.is_file():
        if required:
            raise c.SetupError(f"Manifest {manifest_path} not found")
        return files, [f"no {MANIFEST_NAME} found next to {source_dir}; uploading every chunk file"]
    wanted = manifest_files(manifest_path, source_dir)
    selected = [(path, rel) for path, rel in files if rel in wanted]
    orphans = sorted(rel for _, rel in files if rel not in wanted)
    on_disk = {rel for _, rel in files}
    missing = sorted(rel for rel in wanted if rel not in on_disk and not rel.endswith(SIDECAR_SUFFIX))
    problems = [f"{rel}: on disk but not in {manifest_path.name}; not uploading it" for rel in orphans]
    problems += [f"{rel}: listed in {manifest_path.name} but missing on disk" for rel in missing]
    return selected, problems


def ensure_bucket(ctx: c.Ctx, bucket: str) -> None:
    s3 = ctx.client("s3")
    exists = False
    if not ctx.offline:
        try:
            s3.head_bucket(Bucket=bucket)
            exists = True
        except ClientError as exc:
            code = c.error_code(exc)
            if code in ("403", "AccessDenied", "Forbidden"):
                raise c.SetupError(
                    f"Bucket {bucket} exists but is not accessible (owned by another account?). "
                    "Pass --bucket with a different name.") from exc
            if code not in ("404", "NoSuchBucket", "NotFound"):
                raise
    if exists:
        c.ok(f"bucket {bucket} exists")
    else:
        kwargs = {"Bucket": bucket}
        if ctx.region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": ctx.region}
        ctx.mutate(f"create bucket s3://{bucket} in {ctx.region}", s3.create_bucket, **kwargs)
        ctx.mutate(f"tag bucket {bucket}", s3.put_bucket_tagging, Bucket=bucket,
                   Tagging={"TagSet": c.tag_list()})

    configure_bucket(ctx, bucket, known_new=not exists)


def configure_bucket(ctx: c.Ctx, bucket: str, known_new: bool = False) -> None:
    s3 = ctx.client("s3")
    check = not (known_new or ctx.offline)

    # Versioning
    status = s3.get_bucket_versioning(Bucket=bucket).get("Status") if check else None
    if status == "Enabled":
        c.ok("versioning enabled")
    else:
        ctx.mutate("enable versioning", s3.put_bucket_versioning, Bucket=bucket,
                   VersioningConfiguration={"Status": "Enabled"})

    # Block public access
    want_pab = {"BlockPublicAcls": True, "IgnorePublicAcls": True,
                "BlockPublicPolicy": True, "RestrictPublicBuckets": True}
    current_pab = None
    if check:
        try:
            current_pab = s3.get_public_access_block(Bucket=bucket)[
                "PublicAccessBlockConfiguration"]
        except ClientError as exc:
            if c.error_code(exc) != "NoSuchPublicAccessBlockConfiguration":
                raise
    if current_pab == want_pab:
        c.ok("all public access blocked")
    else:
        ctx.mutate("block all public access", s3.put_public_access_block, Bucket=bucket,
                   PublicAccessBlockConfiguration=want_pab)

    # Default encryption (SSE-S3)
    algorithm = None
    if check:
        try:
            rules = s3.get_bucket_encryption(Bucket=bucket)[
                "ServerSideEncryptionConfiguration"]["Rules"]
            algorithm = rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
        except ClientError as exc:
            if c.error_code(exc) != "ServerSideEncryptionConfigurationNotFoundError":
                raise
    if algorithm == "AES256":
        c.ok("default encryption SSE-S3 (AES256)")
    else:
        ctx.mutate("set default encryption to SSE-S3 (AES256)", s3.put_bucket_encryption,
                   Bucket=bucket, ServerSideEncryptionConfiguration={"Rules": [
                       {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})


def list_remote(ctx: c.Ctx, bucket: str, prefix: str) -> dict[str, str]:
    """Map key -> ETag (without quotes) for objects under prefix."""
    if ctx.offline:
        return {}
    s3 = ctx.client("s3")
    remote = {}
    try:
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                remote[obj["Key"]] = obj["ETag"].strip('"')
    except ClientError as exc:
        if c.error_code(exc) == "NoSuchBucket":  # dry-run of a bucket that does not exist yet
            return {}
        raise
    return remote


SHOW_FIRST_UPLOADS = 5


def upload_directory(ctx: c.Ctx, bucket: str, source_dir: Path,
                     prefix: str = c.GUIDELINES_PREFIX, delete_stale: bool = False,
                     verbose: bool = False, files: list[tuple[Path, str]] | None = None) -> dict:
    """Sync ``files`` (default: every chunk file in source_dir) to s3://bucket/prefix.

    Objects under the prefix that are not in ``files`` are stale. Returns counts.
    """
    s3 = ctx.client("s3")
    files = collect_files(source_dir) if files is None else files
    remote = list_remote(ctx, bucket, prefix)
    stats = {"uploaded": 0, "skipped": 0, "deleted": 0, "stale": 0, "total": len(files)}
    local_keys = set()
    for path, rel in files:
        key = prefix + rel
        local_keys.add(key)
        ctype = content_type_for(path)
        if remote.get(key) == md5_hex(path):
            head = s3.head_object(Bucket=bucket, Key=key)
            if head.get("ContentType") == ctype:
                stats["skipped"] += 1
                continue
        quiet = not verbose and stats["uploaded"] >= SHOW_FIRST_UPLOADS
        ctx.mutate(f"upload {rel} -> s3://{bucket}/{key} ({ctype})", s3.put_object,
                   Bucket=bucket, Key=key, Body=path.read_bytes(), ContentType=ctype,
                   quiet=quiet)
        stats["uploaded"] += 1

    stale = sorted(set(remote) - local_keys)
    stats["stale"] = len(stale)
    if stale and delete_stale:
        for i in range(0, len(stale), 1000):
            batch = stale[i:i + 1000]
            resp = ctx.mutate(f"delete {len(batch)} stale object(s) under s3://{bucket}/{prefix}",
                              s3.delete_objects, Bucket=bucket,
                              Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True})
            errors = (resp or {}).get("Errors", [])
            for err in errors[:5]:
                c.warn(f"could not delete {err.get('Key')}: {err.get('Code')} {err.get('Message', '')}")
            stats["deleted"] += len(batch) - len(errors)
    elif stale:
        c.warn(f"{len(stale)} object(s) under {prefix} are not in the local upload set "
               "(they will stay in the KB); re-run with --delete-stale to remove them")
    if not verbose and stats["uploaded"] > SHOW_FIRST_UPLOADS:
        c.log(f"  ... and {stats['uploaded'] - SHOW_FIRST_UPLOADS} more file(s) (--verbose lists all)")
    verb = "would upload" if ctx.dry_run else "uploaded"
    c.ok(f"{verb} {stats['uploaded']}, skipped {stats['skipped']} unchanged, "
         f"{stats['total']} local file(s)")
    return stats


def run(ctx: c.Ctx, args: argparse.Namespace) -> dict:
    c.verify_credentials(ctx)
    # Same resolution as setup_base.py / setup_knowledge_base.py / teardown.py, so a re-run
    # without --bucket keeps using a previously chosen bucket instead of creating the default.
    bucket = (args.bucket or c.get_parameter(ctx, c.PARAM_GUIDELINES_BUCKET)
              or c.default_guidelines_bucket(ctx.account_id, ctx.region))
    prefix = args.prefix if args.prefix.endswith("/") else args.prefix + "/"
    source_dir = Path(args.source_dir)

    c.step(f"S3 bucket {bucket}")
    ensure_bucket(ctx, bucket)

    c.step(f"Uploading {source_dir} -> s3://{bucket}/{prefix}")
    stats = {"uploaded": 0, "skipped": 0, "deleted": 0, "stale": 0, "total": 0}
    if not source_dir.is_dir() or not any(source_dir.iterdir()):
        c.warn(f"{source_dir} is missing or empty. Run `python scripts/scrape_guidelines.py` "
               "first, then re-run this script (the KB will have nothing to ingest).")
    else:
        manifest = Path(args.manifest) if args.manifest else source_dir.parent / MANIFEST_NAME
        files, problems = select_files(source_dir, manifest, required=bool(args.manifest))
        problems += validate_sidecars(files)
        for problem in problems[:SHOW_FIRST_PROBLEMS]:
            c.warn(problem)
        if len(problems) > SHOW_FIRST_PROBLEMS:
            c.warn(f"... and {len(problems) - SHOW_FIRST_PROBLEMS} more problem(s)")
        stats = upload_directory(ctx, bucket, source_dir, prefix, args.delete_stale,
                                 args.verbose, files=files)

    c.step("Parameter Store")
    c.ensure_parameter(ctx, c.PARAM_GUIDELINES_BUCKET, bucket,
                       "S3 bucket holding guideline chunks for the Bedrock KB")

    c.step("Summary" + (" (dry-run, nothing changed)" if ctx.dry_run else ""))
    c.log(f"  bucket   s3://{bucket}/{prefix}")
    c.log(f"  files    {stats}")
    return {"bucket": bucket, "prefix": prefix, **stats}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    c.add_common_args(parser)
    parser.add_argument("--bucket", default=None,
                        help=f"bucket name (default: {c.PARAM_GUIDELINES_BUCKET} or "
                             "uic-editorial-guidelines-<account>-<region>)")
    parser.add_argument("--source-dir", default=str(c.DEFAULT_CHUNKS_DIR),
                        help="local chunks directory (default: data/guidelines/chunks)")
    parser.add_argument("--manifest", default=None,
                        help=f"manifest listing the chunks to upload (default: {MANIFEST_NAME} "
                             "in the parent of --source-dir; without one every chunk is uploaded)")
    parser.add_argument("--prefix", default=c.GUIDELINES_PREFIX,
                        help=f"key prefix in the bucket (default: {c.GUIDELINES_PREFIX})")
    parser.add_argument("--delete-stale", action="store_true",
                        help="delete objects under the prefix that no longer exist locally")
    parser.add_argument("--verbose", action="store_true", help="list every uploaded file")
    args = parser.parse_args(argv)

    def body() -> int:
        run(c.make_context(args), args)
        return 0

    return c.run_main(body)


if __name__ == "__main__":
    sys.exit(main())
