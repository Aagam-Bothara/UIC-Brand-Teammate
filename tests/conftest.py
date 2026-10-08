import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.services.rule_engine import RuleEngine  # noqa: E402


@pytest.fixture(scope="session")
def engine():
    return RuleEngine()


def rule_ids(result, ruleset_id=None):
    return [i.rule_id for i in result.issues if ruleset_id is None or i.ruleset_id == ruleset_id]
