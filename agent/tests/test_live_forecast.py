import asyncio
import json
from types import SimpleNamespace

import pytest

from heat_planner import forecast, live


def content(**kw):
    base = dict(input_transcription=None, model_turn=None, turn_complete=False, generation_complete=False)
    return SimpleNamespace(server_content=SimpleNamespace(**{**base, **kw}))


class FakeSession:
    def __init__(self, texts):
        self.texts, self.audio, self.ended = texts, [], asyncio.Event()

    async def send_realtime_input(self, audio=None, audio_stream_end=None):
        if audio is not None:
            self.audio.append(audio.data)
        if audio_stream_end:
            self.ended.set()

    async def receive(self):
        for t in self.texts:
            yield content(input_transcription=SimpleNamespace(text=t))
        await self.ended.wait()
        yield content(turn_complete=True)


class FakeClient:
    def __init__(self, session=None, fail=False):
        self.session, self.fail = session, fail
        self.aio = SimpleNamespace(live=SimpleNamespace(connect=self.connect))

    def connect(self, model, config):
        client = self

        class Ctx:
            async def __aenter__(self):
                if client.fail:
                    raise RuntimeError("no access")
                return client.session

            async def __aexit__(self, *a):
                return False

        return Ctx()


class FakeWS:
    def __init__(self, messages):
        self.inbox, self.sent = list(messages), []

    async def receive(self):
        return self.inbox.pop(0) if self.inbox else {"type": "websocket.disconnect"}

    async def send_json(self, payload):
        self.sent.append(payload)


def audio(n=3):
    return [{"type": "websocket.receive", "bytes": b"\x00\x01" * 100} for _ in range(n)]


STOP = {"type": "websocket.receive", "text": json.dumps({"type": "stop"})}


def test_same_origin_only():
    assert live.same_origin({"origin": "https://app.run.app", "host": "app.run.app"})
    assert not live.same_origin({"origin": "https://evil.example", "host": "app.run.app"})
    assert not live.same_origin({"host": "app.run.app"})


def test_transcript_is_relayed_then_finalised():
    session = FakeSession(["Where should ", "we send trucks?"])
    ws = FakeWS(audio() + [STOP])
    asyncio.run(live.run_session(ws, FakeClient(session)))
    kinds = [m["type"] for m in ws.sent]
    assert kinds[-1] == "final" and ws.sent[-1]["text"] == "Where should we send trucks?"
    assert "transcript" in kinds and len(session.audio) == 3


def test_a_live_failure_becomes_a_plain_message():
    ws = FakeWS(audio())
    asyncio.run(live.run_session(ws, FakeClient(fail=True)))
    assert ws.sent == [{"type": "error", "message": live.UNAVAILABLE}]


def test_forecast_pairs_each_day_with_its_night_low():
    props = {"periods": [
        {"name": "This Afternoon", "startTime": "2026-10-27T12:00:00-05:00", "isDaytime": True, "temperature": 84, "shortForecast": "Sunny", "probabilityOfPrecipitation": {"value": 3}},
        {"name": "Tonight", "startTime": "2026-10-27T18:00:00-05:00", "isDaytime": False, "temperature": 63, "shortForecast": "Clear", "probabilityOfPrecipitation": {"value": 1}},
        {"name": "Wednesday", "startTime": "2026-10-28T06:00:00-05:00", "isDaytime": True, "temperature": 88, "shortForecast": "Sunny", "probabilityOfPrecipitation": {"value": None}},
    ]}
    days = forecast.parse_periods(props)
    assert [d["high_f"] for d in days] == [84, 88]
    assert days[0]["low_f"] == 63 and days[1]["low_f"] is None
    assert days[0]["date"] == "2026-10-27" and days[1]["precip_pct"] is None


def test_forecast_failure_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(forecast, "_cache", {})

    def boom(url):
        raise forecast.ToolError("The National Weather Service forecast is unavailable right now.")

    monkeypatch.setattr(forecast, "_get_json", boom)
    with pytest.raises(forecast.ToolError, match="unavailable"):
        forecast.get_forecast()
