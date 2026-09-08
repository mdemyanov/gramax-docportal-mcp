from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Gramax Doc Portal MCP server configuration.

    Environment variables:
        GRAMAX_BASE_URL: Portal URL (required, e.g. https://docs.example.com)
        GRAMAX_API_TOKEN: Bearer API token (optional; omit for public portals)
        GRAMAX_AI_TIMEOUT: Timeout in seconds for /api/search/chat (default 120)
        GRAMAX_AI_ARTICLES_LANGUAGE: Articles language for AI search (no default —
            see the note below; set it only if your portal needs it)
        GRAMAX_AI_RESPONSE_LANGUAGE: Default response language for AI search (default "ru")

    Note on GRAMAX_AI_ARTICLES_LANGUAGE: on some portals a non-empty
    articlesLanguage zeroes the result set out — knowledge.nau.im returned
    0/6 answers with citation markers with it against 6/6 without it, and
    full-text search dropped from 19/50 hits to 0 (measured 2026-09-08).
    Hence no default: the parameter is sent only when a caller asks for it.
    """

    gramax_base_url: str
    gramax_api_token: str | None = None
    gramax_ai_timeout: float = 120.0
    gramax_ai_articles_language: str | None = None
    gramax_ai_response_language: str = "ru"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("gramax_api_token", mode="before")
    @classmethod
    def _normalize_token(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None
