"""Central configuration. Everything is env-driven so the demo can run
in DEMO_MODE (no external keys) or fully live."""
from typing import Literal

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
import base64


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "backend/.env"), extra="ignore")

    # LLM
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
    razorpay_mcp_url: str = "https://mcp.razorpay.com/mcp"
    razorpay_mcp_token: str = ""

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_base_url: str = ""

    # App
    db_path: str = "./mandates.db"
    frontend_origin: str = "http://localhost:3000"
    demo_mode: bool = True
    action_receipt_secret: str = ""
    payment_provider: Literal["simulated", "razorpay_mcp"] = "simulated"
    catalog_retrieval_mode: Literal["keyword", "pinecone"] = "keyword"
    fault_injection_enabled: bool = True
    envelope_drafting_mode: Literal["deterministic", "llm", "replay"] = "replay"

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
