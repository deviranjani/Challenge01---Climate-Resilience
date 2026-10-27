"""Speech to text over the Gemini Live API.

The browser streams 16 kHz 16-bit mono PCM to this server; the server holds the Live session (so no
credentials reach the browser) and relays the transcript back as it forms. Only the transcript is
used: the model's own spoken reply is ignored and the session is closed as soon as the speech ends.
"""

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlparse

from google import genai
from google.genai import types

from .config import load_settings

logger = logging.getLogger(__name__)

MAX_SESSION_S = 60
FINAL_GRACE_S = 4
MAX_AUDIO_BYTES = 16000 * 2 * MAX_SESSION_S
MAX_CONCURRENT = 4
AUDIO_MIME = "audio/pcm;rate=16000"
UNAVAILABLE = "Voice input is unavailable right now. You can still type your question."

_slots = asyncio.Semaphore(MAX_CONCURRENT)


def same_origin(headers: Any) -> bool:
    """Browsers always send Origin on a WebSocket. Reject other sites so they cannot spend our Live quota."""
    origin, host = headers.get("origin"), headers.get("host")
    return bool(origin and host and urlparse(origin).netloc == host)


def make_client() -> genai.Client:
    settings = load_settings()
    return genai.Client(vertexai=True, project=settings.project_id or None, location=settings.live_location)


def _config() -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        input_audio_transcription=types.AudioTranscriptionConfig(),
    )


async def run_session(ws: Any, client: Any = None) -> None:
    """Relay one utterance: audio in, transcript out. `ws` is a Starlette WebSocket (already accepted)."""
    if _slots.locked():
        await ws.send_json({"type": "error", "message": "Voice input is busy. Try again in a moment."})
        return
    async with _slots:
        pieces: list[str] = []
        stopped = asyncio.Event()
        received = 0
        try:
            client = client or make_client()
            async with client.aio.live.connect(model=load_settings().live_model, config=_config()) as session:

                async def from_browser() -> None:
                    nonlocal received
                    while True:
                        message = await ws.receive()
                        if message["type"] == "websocket.disconnect":
                            stopped.set()
                            return
                        if message.get("bytes"):
                            received += len(message["bytes"])
                            if received > MAX_AUDIO_BYTES:
                                stopped.set()
                                return
                            await session.send_realtime_input(audio=types.Blob(data=message["bytes"], mime_type=AUDIO_MIME))
                        elif message.get("text"):
                            try:
                                kind = json.loads(message["text"]).get("type")
                            except (ValueError, AttributeError):
                                kind = None
                            if kind == "stop":
                                await session.send_realtime_input(audio_stream_end=True)
                                stopped.set()
                                return

                async def from_model() -> None:
                    while True:
                        async for reply in session.receive():
                            content = reply.server_content
                            if not content:
                                continue
                            heard = content.input_transcription
                            if heard and heard.text:
                                pieces.append(heard.text)
                                await ws.send_json({"type": "transcript", "text": "".join(pieces).strip(), "final": False})
                            # The model has started (or finished) its own reply: the speech is fully transcribed.
                            if stopped.is_set() and (content.model_turn or content.turn_complete or content.generation_complete):
                                return

                browser = asyncio.create_task(from_browser())
                model = asyncio.create_task(from_model())
                try:
                    done, _ = await asyncio.wait({browser, model}, timeout=MAX_SESSION_S, return_when=asyncio.FIRST_COMPLETED)
                    if model in done and model.exception():
                        raise model.exception()
                    if browser in done and model not in done:
                        await asyncio.wait({model}, timeout=FINAL_GRACE_S)
                        if model.done() and not model.cancelled() and model.exception():
                            raise model.exception()
                finally:
                    for task in (browser, model):
                        task.cancel()
        except Exception:
            logger.exception("live session failed")
            if not pieces:
                await _safe_send(ws, {"type": "error", "message": UNAVAILABLE})
                return
        await _safe_send(ws, {"type": "final", "text": "".join(pieces).strip()})


async def _safe_send(ws: Any, payload: dict[str, Any]) -> None:
    try:
        await ws.send_json(payload)
    except Exception:  # the browser may already have gone
        logger.debug("could not send %s", payload.get("type"))
