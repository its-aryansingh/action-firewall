"""Central configuration. Everything is env-driven so the demo can run
in DEMO_MODE (no external keys) or fully live."""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = str(BACKEND_DIR / "mandates.db")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), extra="ignore")

    # LLM
    gemini_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    openai_transcription_model: str = "gpt-4o-mini-transcribe"
    voice_max_audio_bytes: int = 6_000_000

    # Pinecone
    pinecone_api_key: str = ""
    pinecone_index: str = "razorpay-catalog"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # Razorpay MCP
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_mcp_url: str = "https://mcp.razorpay.com/mcp"
    razorpay_mcp_token: str = ""

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_base_url: str = ""

    # App
    db_path: str = DEFAULT_DB_PATH
    frontend_origin: str = "http://localhost:3000"
    demo_mode: bool = True
    action_receipt_secret: str = ""
    payment_provider: Literal["simulated", "razorpay_mcp", "razorpay_rest"] = "simulated"
    catalog_retrieval_mode: Literal["keyword", "pinecone"] = "keyword"
    fault_injection_enabled: bool = False
    envelope_drafting_mode: Literal["deterministic", "llm", "replay"] = "replay"
    gateway_mode: Literal["demo", "external"] = "demo"

    @field_validator("db_path", mode="after")
    @classmethod
    def resolve_db_path(cls, v: str) -> str:
        p = Path(v)
        if not p.is_absolute():
            p = (BACKEND_DIR / p).resolve()
        return str(p)

    @model_validator(mode="after")
    def validate_fault_injection_safety(self) -> "Settings":
        if self.fault_injection_enabled and (self.payment_provider != "simulated" or not self.demo_mode):
            raise ValueError(
                f"Invariant 17 violation: fault_injection_enabled cannot be True when "
                f"payment_provider='{self.payment_provider}' or demo_mode={self.demo_mode}"
            )
        return self

    @property
    def mcp_auth_header(self) -> str:
        """Basic <base64(key_id:key_secret)> — the Remote MCP handshake."""
        token = self.razorpay_mcp_token
        if not token and self.razorpay_key_id and self.razorpay_key_secret:
            raw = f"{self.razorpay_key_id}:{self.razorpay_key_secret}".encode()
            token = base64.b64encode(raw).decode()
        return f"Basic {token}"


@lru_cache
def get_settings() -> Settings:
    return Settings()

