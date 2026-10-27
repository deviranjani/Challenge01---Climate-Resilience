import pytest
from fastapi.testclient import TestClient

from heat_planner import api, service


@pytest.fixture()
def client():
    return TestClient(api.app)


def test_index_and_static_are_served(client):
    assert "Heat Planner" in client.get("/").text
    assert client.get("/static/chat.js").status_code == 200


def test_health_and_starters(client):
    assert client.get("/api/health").json()["ok"] is True
    assert len(client.get("/api/starters").json()["suggestions"]) >= 3


def test_chat_passes_history_and_returns_result(client, monkeypatch):
    seen = {}

    def fake_run(question, history):
        seen.update(question=question, history=history)
        return {"message": "ok", "cards": [], "steps": [], "followups": [], "stopped_early": False}

    monkeypatch.setattr(service, "run", fake_run)
    body = {"question": "hi", "history": [{"role": "user", "text": "a"}, {"role": "assistant", "text": "b"}]}
    res = client.post("/api/chat", json=body)
    assert res.status_code == 200 and res.json()["message"] == "ok"
    assert seen["history"][0] == {"role": "user", "text": "a"}


def test_chat_validates_input(client):
    assert client.post("/api/chat", json={"question": ""}).status_code == 422
    assert client.post("/api/chat", json={"question": "x" * 1001}).status_code == 422
    assert client.post("/api/chat", json={"question": "x", "history": [{"role": "system", "text": "y"}]}).status_code == 422


def test_chat_maps_agent_failure_to_503(client, monkeypatch):
    def boom(question, history):
        raise service.AgentError("model unavailable")

    monkeypatch.setattr(service, "run", boom)
    res = client.post("/api/chat", json={"question": "hi"})
    assert res.status_code == 503 and "model unavailable" in res.json()["detail"]


def test_forecast_history_and_priority_endpoints(client, monkeypatch):
    from heat_planner import api, forecast

    monkeypatch.setattr(forecast, "get_forecast", lambda *a: {"source": "NWS", "days": [{"date": "2026-10-27", "high_f": 84}]})
    assert client.get("/api/forecast").json()["days"][0]["high_f"] == 84

    monkeypatch.setattr(api, "heat_frequency", lambda t: {"status": "ok", "threshold_f": t, "days_per_year": []})
    assert client.get("/api/history?threshold=105").json()["threshold_f"] == 105
    assert client.get("/api/history?threshold=10").status_code == 422

    monkeypatch.setattr(api, "rank_response_sites", lambda n: {"status": "ok", "sites": [1] * n})
    assert len(client.get("/api/priority?limit=3").json()["sites"]) == 3
    monkeypatch.setattr(api, "rank_response_sites", lambda n: {"status": "error", "message": "no model"})
    assert client.get("/api/priority").status_code == 503


def test_live_socket_rejects_other_origins(client):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/live", headers={"origin": "https://evil.example"}):
            pass
