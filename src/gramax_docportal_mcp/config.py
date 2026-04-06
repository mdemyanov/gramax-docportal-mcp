from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Gramax Doc Portal MCP server configuration.

    Environment variables:
        GRAMAX_BASE_URL: Portal URL (required, e.g. https://docs.example.com)
        GRAMAX_API_TOKEN: Bearer API token (required, obtained via /api/user/token)
    """

    gramax_base_url: str
    gramax_api_token: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
