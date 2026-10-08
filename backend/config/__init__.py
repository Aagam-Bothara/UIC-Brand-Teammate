"""Workstream 1 settings (formerly backend/config.py; moved here because Workstream 3 added the
``backend/config`` package — ``backend.config.exceptions`` lives alongside).

Application settings for the UIC Editorial Assistant backend.

Resolution order for every setting (see docs/API_CONTRACT.md, "Configuration"):

    1. environment variable
    2. AWS SSM Parameter Store (only for settings that define a parameter name)
    3. built-in default

SSM lookups are lazy, cached per parameter name, and failure tolerant: missing
credentials, a missing parameter, access denied or any network error resolve to
``None`` (and therefore fall through to the default) instead of crashing the app.
This keeps local development and unit tests working without AWS access.

Usage::

    from backend.config import get_settings
    settings = get_settings()
    settings.kb_id  # -> "ABCDEFGHIJ" or None

Tests call ``reset_settings()`` after changing the environment.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from backend.logging_utils import get_logger

logger = get_logger(__name__)

# --- names (binding: docs/API_CONTRACT.md) -----------------------------------

ENV_REGION = "AWS_REGION"
ENV_KB_ID = "UIC_KB_ID"
ENV_GUIDELINES_BUCKET = "UIC_GUIDELINES_BUCKET"
ENV_RAG_BACKEND = "UIC_RAG_BACKEND"
ENV_LOG_GROUP = "UIC_LOG_GROUP"
# Not part of the contract table; optional override for the local guidelines dir.
ENV_GUIDELINES_DIR = "UIC_GUIDELINES_DIR"
# Set to "0"/"false" to skip SSM entirely (e.g. offline dev, CI).
ENV_SSM_ENABLED = "UIC_SSM_ENABLED"

SSM_PREFIX = "/uic-editorial"
SSM_KB_ID = f"{SSM_PREFIX}/knowledge_base_id"
SSM_GUIDELINES_BUCKET = f"{SSM_PREFIX}/guidelines_bucket"

# Bedrock models for the rewrite / chat services (SPEC "Models: Adaptive"). Resolved by
# get_model_settings(): env var > SSM parameter > default below.
ENV_MODEL_FAST = "UIC_MODEL_FAST"
ENV_MODEL_QUALITY = "UIC_MODEL_QUALITY"
SSM_MODEL_FAST = f"{SSM_PREFIX}/model_fast"
SSM_MODEL_QUALITY = f"{SSM_PREFIX}/model_quality"
DEFAULT_MODEL_FAST = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
DEFAULT_MODEL_QUALITY = "us.anthropic.claude-sonnet-5"

DEFAULT_REGION = "us-east-1"
DEFAULT_RAG_BACKEND = "auto"
DEFAULT_LOG_GROUP = "/uic-editorial/backend"

VALID_RAG_BACKENDS = ("auto", "bedrock", "local")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/config/__init__.py -> repo root
DEFAULT_GUIDELINES_DIR = REPO_ROOT / "data" / "guidelines"


# --- SSM ----------------------------------------------------------------------

_ssm_cache: dict[str, str | None] = {}
_ssm_lock = threading.Lock()
# Set (to the error name) when SSM is unreachable for *every* parameter: no/invalid
# credentials or no network. Further lookups are skipped instead of each re-probing the
# credential chain (IMDS) / endpoint, which cost ~2 s per parameter on a laptop without creds.
_ssm_unavailable: str | None = None

# botocore errors that are not specific to one parameter.
_SSM_GLOBAL_ERRORS = frozenset({
    "NoCredentialsError", "PartialCredentialsError", "ProfileNotFound", "NoRegionError",
    "SSOTokenLoadError", "UnauthorizedSSOTokenError", "TokenRetrievalError", "SSOError",
    "CredentialRetrievalError", "InvalidConfigError",
    "EndpointConnectionError", "ConnectTimeoutError", "ConnectionClosedError",
    "UnrecognizedClientException", "InvalidClientTokenId", "ExpiredTokenException", "ExpiredToken",
})


def _ssm_enabled() -> bool:
    return os.environ.get(ENV_SSM_ENABLED, "1").strip().lower() not in ("0", "false", "no", "off")


def get_ssm_parameter(name: str, region: str | None = None) -> str | None:
    """Return the value of SSM parameter ``name`` or ``None``.

    Never raises: any failure (no credentials, ParameterNotFound, AccessDenied,
    network error, botocore not configured) is logged at debug/warning level and
    yields ``None``. Results, including misses, are cached for the process
    lifetime; call :func:`reset_settings` to clear. A credentials / connectivity
    failure disables further SSM lookups until :func:`reset_settings`.
    """
    global _ssm_unavailable
    with _ssm_lock:
        if name in _ssm_cache:
            return _ssm_cache[name]

    value: str | None = None
    if _ssm_enabled() and _ssm_unavailable is None:
        try:
            import boto3
            from botocore.config import Config as BotoConfig

            client = boto3.client(
                "ssm",
                region_name=region or os.environ.get(ENV_REGION) or DEFAULT_REGION,
                config=BotoConfig(connect_timeout=2, read_timeout=3, retries={"max_attempts": 1}),
            )
            resp = client.get_parameter(Name=name, WithDecryption=True)
            raw = resp.get("Parameter", {}).get("Value")
            value = raw.strip() if isinstance(raw, str) and raw.strip() else None
            logger.info("ssm parameter resolved", extra={"event": "ssm_lookup", "parameter": name, "found": value is not None})
        except Exception as exc:  # noqa: BLE001 - deliberately failure tolerant
            err = getattr(exc, "response", None)
            code = err.get("Error", {}).get("Code") if isinstance(err, dict) else None
            if (code or type(exc).__name__) in _SSM_GLOBAL_ERRORS:
                _ssm_unavailable = code or type(exc).__name__
            logger.debug(
                "ssm parameter unavailable",
                extra={"event": "ssm_lookup", "parameter": name, "found": False,
                       "error": code or type(exc).__name__},
            )
            value = None

    with _ssm_lock:
        _ssm_cache[name] = value
    return value


# --- settings -----------------------------------------------------------------


def _env(name: str) -> str | None:
    val = os.environ.get(name)
    if val is None:
        return None
    val = val.strip()
    return val or None


@dataclass(frozen=True)
class Settings:
    aws_region: str
    kb_id: str | None
    guidelines_bucket: str | None
    rag_backend: str
    log_group: str
    guidelines_dir: Path

    def as_dict(self) -> dict:
        return {
            "aws_region": self.aws_region,
            "kb_id": self.kb_id,
            "guidelines_bucket": self.guidelines_bucket,
            "rag_backend": self.rag_backend,
            "log_group": self.log_group,
            "guidelines_dir": str(self.guidelines_dir),
        }


def load_settings() -> Settings:
    """Resolve settings now (uncached). Prefer :func:`get_settings`."""
    region = _env(ENV_REGION) or DEFAULT_REGION

    kb_id = _env(ENV_KB_ID) or get_ssm_parameter(SSM_KB_ID, region)
    bucket = _env(ENV_GUIDELINES_BUCKET) or get_ssm_parameter(SSM_GUIDELINES_BUCKET, region)

    backend = (_env(ENV_RAG_BACKEND) or DEFAULT_RAG_BACKEND).lower()
    if backend not in VALID_RAG_BACKENDS:
        logger.warning(
            "invalid UIC_RAG_BACKEND, using auto",
            extra={"event": "config_invalid", "setting": ENV_RAG_BACKEND, "value": backend},
        )
        backend = DEFAULT_RAG_BACKEND

    guidelines_dir = Path(_env(ENV_GUIDELINES_DIR) or DEFAULT_GUIDELINES_DIR)

    return Settings(
        aws_region=region,
        kb_id=kb_id,
        guidelines_bucket=bucket,
        rag_backend=backend,
        log_group=_env(ENV_LOG_GROUP) or DEFAULT_LOG_GROUP,
        guidelines_dir=guidelines_dir,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings (FastAPI-dependency friendly)."""
    return load_settings()


@dataclass(frozen=True)
class ModelSettings:
    """Bedrock model / inference-profile ids: ``fast`` (Haiku) and ``quality`` (Sonnet)."""

    fast: str
    quality: str


@lru_cache(maxsize=1)
def get_model_settings() -> ModelSettings:
    """Model ids: ``UIC_MODEL_FAST`` / ``UIC_MODEL_QUALITY`` > SSM ``/uic-editorial/model_*`` > defaults.

    Kept separate from :class:`Settings` so RAG-only code paths never pay for the extra SSM
    lookups. The deploy script sets both env vars on the Lambda, so cold starts skip SSM.
    """
    region = _env(ENV_REGION) or DEFAULT_REGION
    fast = _env(ENV_MODEL_FAST) or get_ssm_parameter(SSM_MODEL_FAST, region) or DEFAULT_MODEL_FAST
    quality = (_env(ENV_MODEL_QUALITY) or get_ssm_parameter(SSM_MODEL_QUALITY, region)
               or DEFAULT_MODEL_QUALITY)
    return ModelSettings(fast=fast, quality=quality)


def reset_settings() -> None:
    """Clear the settings cache and the SSM cache (for tests / config reloads)."""
    global _ssm_unavailable
    get_settings.cache_clear()
    get_model_settings.cache_clear()
    with _ssm_lock:
        _ssm_cache.clear()
        _ssm_unavailable = None
