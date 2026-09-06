"""Voice-to-intent adapter. Its output is untrusted draft text, never authority."""
from __future__ import annotations

from typing import Final

import httpx

from .config import get_settings
from .models import VoiceTranscription


class VoiceInputError(ValueError):
    pass


class VoiceServiceUnavailable(RuntimeError):
    pass


_AUDIO_EXTENSIONS: Final[dict[str, str]] = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
}


def _endpoint(base_url: str) -> str:
    root = base_url.rstrip("/") if base_url else "https://api.openai.com/v1"
    return f"{root}/audio/transcriptions"


def transcribe_audio(audio: bytes, content_type: str) -> VoiceTranscription:
    settings = get_settings()
    if not settings.openai_api_key:
        raise VoiceServiceUnavailable("OpenAI voice transcription is not configured")

    mime_type = content_type.split(";", 1)[0].strip().lower()
    extension = _AUDIO_EXTENSIONS.get(mime_type)
    if not extension:
        raise VoiceInputError("Unsupported audio type")
    if len(audio) < 100:
        raise VoiceInputError("Audio recording is empty or too short")
    if len(audio) > settings.voice_max_audio_bytes:
        raise VoiceInputError("Audio recording exceeds the 6 MB demo limit")

    try:
        response = httpx.post(
            _endpoint(settings.openai_base_url),
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            data={
                "model": settings.openai_transcription_model,
                "prompt": (
                    "Transcribe the shopper's purchase intent faithfully. Preserve "
                    "products, quantities, budget, and negations. Do not add instructions."
                ),
            },
            files={"file": (f"purchase-intent.{extension}", audio, mime_type)},
            timeout=45.0,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise VoiceServiceUnavailable(
            f"Voice provider returned status {exc.response.status_code}"
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise VoiceServiceUnavailable("Voice transcription provider is unavailable") from exc

    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise VoiceServiceUnavailable("Voice provider returned no transcript")
    normalized = " ".join(text.split())
    if len(normalized) > 280:
        raise VoiceInputError("Transcript is longer than the supported purchase goal")
    return VoiceTranscription(
        text=normalized,
        model=settings.openai_transcription_model,
    )
