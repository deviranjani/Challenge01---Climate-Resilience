import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    from heat_planner import areas, modeling, tracts

    def clear():
        modeling._coverage.cache_clear()
        modeling.clear_tract_cache()
        tracts.clear_cache()
        areas._names.clear()
        areas._zips.clear()

    clear()
    yield
    clear()
