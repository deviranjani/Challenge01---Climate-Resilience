import pytest
from fastapi.testclient import TestClient

from heat_planner import api, service


@pytest.fixture()
def client():
    return TestClient(api.app)


def test_index_and_static_are_served(client):
    assert "Heat Compass" in client.get("/").text
    assert client.get("/static/chat.js").headers["cache-control"] == "no-cache"
    assert client.get("/static/chat.js").status_code == 200


def test_health_and_starters(client):
    assert client.get("/api/health").json()["ok"] is True
    assert len(client.get("/api/starters").json()["suggestions"]) >= 3


def test_chat_passes_history_and_returns_result(client, monkeypatch):
    seen = {}

    def fake_run(question, history, model=None, track=None):
        seen.update(question=question, history=history, track=track)
        return {"message": "ok", "cards": [], "steps": [{"tool": "x"}], "followups": [], "stopped_early": False}

    monkeypatch.setattr(service, "run", fake_run)
    body = {"question": "hi", "track": "budget", "history": [{"role": "user", "text": "a"}, {"role": "assistant", "text": "b"}]}
    res = client.post("/api/chat", json=body)
    assert res.status_code == 200 and res.json()["message"] == "ok" and "steps" not in res.json()
    assert seen["history"][0] == {"role": "user", "text": "a"} and seen["track"] == "budget"


def test_chat_validates_input(client):
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/chat", json={"question": "x" * 1001}).status_code == 422
    assert client.post("/api/chat", json={"question": "x", "history": [{"role": "system", "text": "y"}]}).status_code == 422
    assert client.post("/api/chat", json={"question": "x", "track": "nonsense"}).status_code == 422


def test_chat_maps_agent_failure_to_503(client, monkeypatch):
    def boom(question, history, model=None, track=None):
        raise service.AgentError("model unavailable")

    monkeypatch.setattr(service, "run", boom)
    res = client.post("/api/chat", json={"question": "hi"})
    assert res.status_code == 503 and "model unavailable" in res.json()["detail"]


def test_forecast_and_history_endpoints(client, monkeypatch):
    from heat_planner import api, forecast

    monkeypatch.setattr(forecast, "get_forecast", lambda *a: {"source": "NWS", "days": [{"date": "2026-10-27", "high_f": 84}]})
    assert client.get("/api/forecast").json()["days"][0]["high_f"] == 84
    monkeypatch.setattr(api, "heat_frequency", lambda t: {"status": "ok", "threshold_f": t, "days_per_year": []})
    assert client.get("/api/history?threshold=105").json()["threshold_f"] == 105
    assert client.get("/api/history?threshold=10").status_code == 422


def test_live_socket_rejects_other_origins(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/live", headers={"origin": "https://evil.example"}):
            pass


def test_every_asset_url_carries_the_version_and_the_page_is_never_reused_stale(client):
    import re

    res = client.get("/")
    assert res.headers["cache-control"] == "no-cache"
    urls = re.findall(r'(?:src|href)="(/static/[^"]+)"', res.text)
    assert urls and all(u.endswith(f"?v={api.ASSET_VERSION}") for u in urls)
    assert client.get(urls[0]).status_code == 200  # the stamped URL still resolves
