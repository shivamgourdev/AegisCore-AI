"""Application configuration loaded from environment variables.

Never log secrets. All sensitive values are read from env via pydantic-settings.
"""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_INSECURE_DEFAULTS = {
    "secret_key": "change-me-in-production",
    "encryption_key": "change-me-32-byte-base64-key",
}


# Load .env from project root (parent of backend/), not CWD.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_PROJECT_ROOT / ".env"), env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    app_name: str = "AegisCore AI"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    api_v1_prefix: str = "/api/v1"
    backend_cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Security ---
    secret_key: str = Field(default="change-me-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # --- Encryption (AES-256-GCM for Gmail OAuth tokens at rest) ---
    encryption_key: str = Field(default="change-me-32-byte-base64-key")

    # --- Database (PostgreSQL) ---
    database_url: str = Field(
        default="postgresql+psycopg2://aegis:aegis@localhost:5432/aegis_db"
    )
    database_echo: bool = False

    # --- Redis (broker / cache / rate limit) ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # --- ChromaDB (vectors) ---
    chroma_persist_directory: str = "./data/chroma"
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    # --- Ollama (local LLM / embeddings) ---
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "phi3.5:3.8b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_vision_model: str = "llava:7b"

    # --- Cloud AI API (public inference fallback) ---
    cloud_ai_provider: str = "gemini"
    cloud_ai_api_key: str = ""
    cloud_ai_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    cloud_ai_model: str = "gemini-1.5-flash"

    # --- Gmail OAuth2 (per-user, draft-only mode works without credentials) ---
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/v1/auth/gmail/callback"
    gmail_scopes: str = "https://www.googleapis.com/auth/gmail.send"
    gmail_consent_type: str = "internal"

    # --- File storage ---
    upload_max_size_mb: int = 50
    upload_dir: str = "./data/uploads"

    # --- Quotas (adjustable; free-tier limits unverified) ---
    max_docs_per_user: int = 100
    max_upload_size_mb: int = 50
    max_email_sends_per_day: int = 10
    max_ai_tokens_per_day: int = 1000

    # --- Rate limiting ---
    rate_limit_requests_per_minute: int = 60
    enable_rate_limiting: bool = False

    # --- RAG / Document processing ---
    rag_chunk_size: int = 512
    rag_chunk_overlap: int = 50
    rag_top_k: int = 20
    rag_rerank_top_k: int = 8
    rag_enable_reranking: bool = True
    rag_embedding_model: str = "nomic-embed-text"
    rag_llm_model: str = "phi3.5:3.8b"

    # --- Feature flags ---
    enable_vision_local: bool = False
    enable_draft_only_mode: bool = True
    enable_public_inference: bool = False

    @model_validator(mode="after")
    def _validate_production_secrets(self) -> "Settings":
        """Reject insecure default secrets in production without printing them."""
        if self.app_env == "production":
            for field_name, insecure_value in _INSECURE_DEFAULTS.items():
                actual = getattr(self, field_name)
                if actual == insecure_value:
                    raise ValueError(
                        f"{field_name} must not use the insecure default in production. "
                        f"Set {field_name} via environment variable before starting."
                    )
        return self

    @property
    def rate_limiting_enabled(self) -> bool:
        """Rate limiting is on by default in production; off by default in development."""
        if self.app_env == "production":
            return True
        return self.enable_rate_limiting


settings = Settings()
