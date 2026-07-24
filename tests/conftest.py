"""
Test config: run fully OFFLINE and deterministically.

Disable the Pioneer judge/guard by clearing their env before backend import, so
no test hits the network. The heuristic + retrieval + router + API + learning
loop are all exercised locally. The live degraded-judge path is covered by the
manual smoke test (scripts/smoke.sh), not the unit suite.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Must be set before backend.config.Settings() is first constructed.
os.environ["PIONEER_API_KEY"] = ""
os.environ["PIONEER_GLIGUARD_API_KEY"] = ""
os.environ["PIONEER_BASE_URL"] = ""
os.environ["FIREVOLV_STORE"] = "memory"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client():
    from backend.main import app
    from backend.memory import get_store
    get_store().reset()
    c = TestClient(app)
    yield c
    get_store().reset()
