from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app import voice
from app.config import get_settings
from app.main import app


def test_voice_route_is_draft_only_and_sends_extension_bearing_audio(
    monkeypatch,
):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-never-sent-to-browser")
    monkeypatch.setenv("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")
    get_settings.cache_clear()
    captured: dict[str, object] = {}

    def fake_post(url, *, headers, data, files, timeout):
        captured.update(
            {"url": url, "headers": headers, "data": data, "files": files, "timeout": timeout}
        )
        return httpx.Response(
            200,
            json={"text": "Buy pasta, tomato sauce, and cheese under six hundred rupees."},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(voice.httpx, "post", fake_post)
    with TestClient(app) as client:
        response = client.post(
            "/voice/transcribe",
            content=b"0" * 512,
            headers={"Content-Type": "audio/webm;codecs=opus"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "text": "Buy pasta, tomato sauce, and cheese under six hundred rupees.",
        "provider": "openai",
        "model": "gpt-4o-mini-transcribe",
        "draft_only": True,
    }
    upload = captured["files"]
    assert isinstance(upload, dict)
    assert upload["file"][0] == "purchase-intent.webm"
    assert captured["headers"] == {"Authorization": "Bearer test-key-never-sent-to-browser"}


def test_voice_route_fails_closed_without_server_key():
    with TestClient(app) as client:
        response = client.post(
            "/voice/transcribe",
            content=b"0" * 512,
            headers={"Content-Type": "audio/webm"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "OpenAI voice transcription is not configured"


def test_voice_route_rejects_unsupported_media_before_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    def should_not_call_provider(*args, **kwargs):
        raise AssertionError("provider must not receive unsupported input")

    monkeypatch.setattr(voice.httpx, "post", should_not_call_provider)
    with TestClient(app) as client:
        response = client.post(
            "/voice/transcribe",
            content=b"0" * 512,
            headers={"Content-Type": "text/plain"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unsupported audio type"


def test_voice_provider_error_does_not_expose_response_body(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    get_settings.cache_clear()

    def fake_post(url, **kwargs):
        return httpx.Response(
            401,
            json={"error": {"message": "sensitive upstream diagnostic"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(voice.httpx, "post", fake_post)
    with TestClient(app) as client:
        response = client.post(
            "/voice/transcribe",
            content=b"0" * 512,
            headers={"Content-Type": "audio/webm"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Voice provider returned status 401"
    assert "sensitive" not in response.text
