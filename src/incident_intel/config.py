"""Central configuration for the whole platform.

Every setting is read from environment variables, or from a local `.env` file
(see `.env.example`). Code never hard-codes secrets or URLs; it asks for
`get_settings()` instead. This is the "12-factor app" config principle.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings. Pydantic validates types and fills in defaults.

    An environment variable named like the field (upper-case) overrides the
    default, e.g. `LLM_MODEL=llama3.1:8b` overrides `llm_model`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "Incident Intelligence Platform"
    environment: str = "local"
    log_level: str = "INFO"

    # --- LLM (any OpenAI-compatible endpoint: Ollama, Groq, Gemini, ...) ---
    llm_provider: str = "ollama"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"  # Ollama ignores the key, but the client needs a value
    llm_model: str = "qwen3:8b"
    embedding_model: str = "nomic-embed-text"


@lru_cache
def get_settings() -> Settings:
    """Return one shared Settings object (created once, then cached)."""
    return Settings()
