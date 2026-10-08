"""Tests for backend.config: env -> SSM Parameter Store -> default resolution."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import boto3
import pytest
from botocore.exceptions import NoCredentialsError
from moto import mock_aws

from backend import config
from backend.config import (DEFAULT_GUIDELINES_DIR, SSM_GUIDELINES_BUCKET, SSM_KB_ID, get_settings,
                            get_ssm_parameter, load_settings, reset_settings)
from backend.logging_utils import get_logger

ENV_VARS = ["AWS_REGION", "UIC_KB_ID", "UIC_GUIDELINES_BUCKET", "UIC_RAG_BACKEND", "UIC_LOG_GROUP",
            "UIC_GUIDELINES_DIR", "UIC_SSM_ENABLED"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # Fake credentials so nothing can ever reach real AWS.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    reset_settings()
    yield
    reset_settings()


def _put(name: str, value: str) -> None:
    boto3.client("ssm", region_name="us-east-1").put_parameter(Name=name, Value=value, Type="String")


@mock_aws
def test_defaults_when_nothing_configured():
    s = load_settings()
    assert s.aws_region == "us-east-1"
    assert s.kb_id is None
    assert s.guidelines_bucket is None
    assert s.rag_backend == "auto"
    assert s.log_group == "/uic-editorial/backend"
    assert s.guidelines_dir == DEFAULT_GUIDELINES_DIR


@mock_aws
def test_ssm_used_when_env_missing():
    _put(SSM_KB_ID, "KBFROMSSM1")
    _put(SSM_GUIDELINES_BUCKET, "uic-guidelines-bucket")
    s = load_settings()
    assert s.kb_id == "KBFROMSSM1"
    assert s.guidelines_bucket == "uic-guidelines-bucket"


@mock_aws
def test_env_takes_precedence_over_ssm(monkeypatch):
    _put(SSM_KB_ID, "KBFROMSSM1")
    monkeypatch.setenv("UIC_KB_ID", "KBFROMENV1")
    monkeypatch.setenv("UIC_GUIDELINES_BUCKET", "env-bucket")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    monkeypatch.setenv("UIC_RAG_BACKEND", "Local")
    monkeypatch.setenv("UIC_LOG_GROUP", "/custom/group")
    s = load_settings()
    assert s.kb_id == "KBFROMENV1"
    assert s.guidelines_bucket == "env-bucket"
    assert s.aws_region == "us-west-2"
    assert s.rag_backend == "local"
    assert s.log_group == "/custom/group"


@mock_aws
def test_blank_env_value_falls_through_to_ssm(monkeypatch):
    _put(SSM_KB_ID, "KBFROMSSM1")
    monkeypatch.setenv("UIC_KB_ID", "   ")
    assert load_settings().kb_id == "KBFROMSSM1"


def test_ssm_failure_is_tolerated_and_cached():
    fake = mock.MagicMock()
    fake.get_parameter.side_effect = NoCredentialsError()
    with mock.patch("boto3.client", return_value=fake) as client_factory:
        assert get_ssm_parameter(SSM_KB_ID) is None
        assert get_ssm_parameter(SSM_KB_ID) is None  # cached miss: no second call
        assert client_factory.call_count == 1
        s = load_settings()
    assert s.kb_id is None


@mock_aws
def test_ssm_hits_are_cached_until_reset():
    _put(SSM_KB_ID, "KB1")
    assert get_ssm_parameter(SSM_KB_ID) == "KB1"
    boto3.client("ssm", region_name="us-east-1").put_parameter(Name=SSM_KB_ID, Value="KB2", Type="String",
                                                               Overwrite=True)
    assert get_ssm_parameter(SSM_KB_ID) == "KB1"
    reset_settings()
    assert get_ssm_parameter(SSM_KB_ID) == "KB2"


def test_ssm_can_be_disabled(monkeypatch):
    monkeypatch.setenv("UIC_SSM_ENABLED", "0")
    with mock.patch("boto3.client") as client_factory:
        assert get_ssm_parameter(SSM_KB_ID) is None
        client_factory.assert_not_called()


@mock_aws
def test_invalid_backend_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("UIC_RAG_BACKEND", "elasticsearch")
    assert load_settings().rag_backend == "auto"


@mock_aws
def test_get_settings_is_cached_and_resettable(monkeypatch):
    first = get_settings()
    monkeypatch.setenv("UIC_KB_ID", "KBNEW")
    assert get_settings() is first
    reset_settings()
    assert get_settings().kb_id == "KBNEW"


def test_guidelines_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv("UIC_SSM_ENABLED", "0")
    monkeypatch.setenv("UIC_GUIDELINES_DIR", str(tmp_path))
    assert load_settings().guidelines_dir == Path(tmp_path)


def test_logger_emits_single_line_json(capsys):
    get_logger("test").info("hello", extra={"event": "unit_test", "latency_ms": 1.5, "backend": "local"})
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    record = json.loads(lines[-1])
    assert record["message"] == "hello"
    assert record["event"] == "unit_test"
    assert record["latency_ms"] == 1.5
    assert record["backend"] == "local"
    assert record["level"] == "INFO"
    assert "timestamp" in record


def test_module_exposes_contract_names():
    assert config.SSM_KB_ID == "/uic-editorial/knowledge_base_id"
    assert config.SSM_GUIDELINES_BUCKET == "/uic-editorial/guidelines_bucket"


# --- QA regression tests -----------------------------------------------------------------------


def test_ssm_credentials_failure_skips_remaining_lookups():
    """Without credentials each lookup used to re-probe the credential chain (~2 s each on a laptop)."""
    fake = mock.MagicMock()
    fake.get_parameter.side_effect = NoCredentialsError()
    with mock.patch("boto3.client", return_value=fake) as client_factory:
        s = load_settings()
        assert s.kb_id is None and s.guidelines_bucket is None
        assert client_factory.call_count == 1
        reset_settings()  # re-enables SSM
        load_settings()
        assert client_factory.call_count == 2


def test_ssm_parameter_specific_error_does_not_disable_ssm():
    from botocore.exceptions import ClientError

    fake = mock.MagicMock()
    fake.get_parameter.side_effect = [
        ClientError({"Error": {"Code": "ParameterNotFound", "Message": "x"}}, "GetParameter"),
        {"Parameter": {"Value": "bucket-from-ssm"}},
    ]
    with mock.patch("boto3.client", return_value=fake):
        s = load_settings()
    assert s.kb_id is None and s.guidelines_bucket == "bucket-from-ssm"


def test_ssm_client_has_short_timeouts():
    fake = mock.MagicMock()
    fake.get_parameter.return_value = {"Parameter": {"Value": "KB"}}
    with mock.patch("boto3.client", return_value=fake) as client_factory:
        get_ssm_parameter(SSM_KB_ID)
    cfg = client_factory.call_args.kwargs["config"]
    assert cfg.connect_timeout <= 3 and cfg.read_timeout <= 5


def test_logger_extra_cannot_clobber_core_fields_and_no_duplicate_handlers(capsys):
    import logging

    for _ in range(3):
        log = get_logger("dup")
    assert sum(1 for h in logging.getLogger("uic").handlers if getattr(h, "_uic_json_handler", False)) == 1
    log.warning("hi", extra={"level": "spoof", "logger": "spoof", "timestamp": "spoof", "event": "e"})
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["level"] == "WARNING" and record["logger"] == "uic.dup" and record["timestamp"] != "spoof"
    assert record["extra_level"] == "spoof" and record["event"] == "e"


def test_logger_serializes_non_json_values(capsys):
    get_logger("ser").info("x", extra={"path": Path("/tmp/a"), "items": {1, 2}, "obj": object()})
    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["path"] == "/tmp/a"
