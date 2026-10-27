import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    from heat_planner.tools import prediction

    prediction._coverage.cache_clear()
    prediction.clear_tract_cache()
    yield
    prediction._coverage.cache_clear()
