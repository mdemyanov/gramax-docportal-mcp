from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Gramax Doc Portal MCP server configuration.

    Environment variables:
        GRAMAX_BASE_URL: Portal URL (required, e.g. https://docs.example.com)
        GRAMAX_API_TOKEN: Bearer API token (required, obtained via /api/user/token)
        GRAMAX_AI_TIMEOUT: Timeout in seconds for /api/search/chat (default 120)
        GRAMAX_AI_ARTICLES_LANGUAGE: Default articles language for AI search (default "ru")
        GRAMAX_AI_RESPONSE_LANGUAGE: Default response language for AI search (default "ru")
    """

    gramax_base_url: str
    gramax_api_token: str
    gramax_ai_timeout: float = 120.0
    gramax_ai_articles_language: str = "ru"
    gramax_ai_response_language: str = "ru"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
