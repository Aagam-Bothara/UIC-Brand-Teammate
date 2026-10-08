"""Regenerate Workstream 2 mock responses in tests/mocks/ from the real rule engine.

    python scripts/generate_rules_mocks.py

Other workstreams (frontend, orchestrator) can build against these files
before the live API is available. Rerun after changing any ruleset.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from backend.api.rules_routes import app  # noqa: E402

MOCKS = ROOT / "tests" / "mocks"

SAMPLE_TEXT = (
    "Hey guys! UIC is hosting New Student Orientation at the University of Illinois at Chicago "
    "on October 15th at 3:00 PM in order to welcome everyone to campus. CLICK HERE to RSVP. "
    "See the attached flyer for details.\n\n"
    "The University utilizes numerous resources to facilitate the matriculation process, and "
    "it is recommended that participants obtain sufficient documentation prior to the "
    "aforementioned program. Send an e-mail to the OSA with questions."
)


def write(name, data):
    path = MOCKS / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}")


def main():
    MOCKS.mkdir(parents=True, exist_ok=True)
    client = TestClient(app)

    write("rules_list_response.json", client.get("/api/rules").json())
    write("audiences_response.json", client.get("/api/audiences").json())

    request = {"text": SAMPLE_TEXT, "audience": "students", "channel": "email"}
    write("rules_check_request.json", request)
    write("rules_check_response.json", client.post("/api/rules/check", json=request).json())

    clean = {
        "text": "The University of Illinois Chicago welcomes new students on Oct. 15 at 3 p.m. "
                "Come to Student Center East. Meet your advisers and make new friends.",
        "audience": "students",
        "channel": "email",
    }
    write("rules_check_response_clean.json", client.post("/api/rules/check", json=clean).json())


if __name__ == "__main__":
    main()
