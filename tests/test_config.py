import pytest


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token-abc")

    from gramax_docportal_mcp.config import Settings

    settings = Settings(_env_file=None)
    assert settings.gramax_base_url == "https://docs.example.com"
    assert settings.gramax_api_token == "test-token-abc"


def test_settings_requires_base_url(monkeypatch):
    monkeypatch.delenv("GRAMAX_BASE_URL", raising=False)
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token")

    from gramax_docportal_mcp.config import Settings

    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_token_optional_when_absent(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.delenv("GRAMAX_API_TOKEN", raising=False)

    from gramax_docportal_mcp.config import Settings

    settings = Settings(_env_file=None)
    assert settings.gramax_api_token is None


def test_settings_token_empty_string_normalizes_to_none(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "")

    from gramax_docportal_mcp.config import Settings

    settings = Settings(_env_file=None)
    assert settings.gramax_api_token is None


def test_settings_token_whitespace_normalizes_to_none(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "   ")

    from gramax_docportal_mcp.config import Settings

    settings = Settings(_env_file=None)
    assert settings.gramax_api_token is None


def test_settings_token_strips_whitespace(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", " abc123 ")

    from gramax_docportal_mcp.config import Settings

    settings = Settings(_env_file=None)
    assert settings.gramax_api_token == "abc123"


def test_settings_ai_defaults(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token")
    monkeypatch.delenv("GRAMAX_AI_TIMEOUT", raising=False)
    monkeypatch.delenv("GRAMAX_AI_ARTICLES_LANGUAGE", raising=False)
    monkeypatch.delenv("GRAMAX_AI_RESPONSE_LANGUAGE", raising=False)

    from gramax_docportal_mcp.config import Settings

    s = Settings(_env_file=None)
    assert s.gramax_ai_timeout == 120.0
    assert s.gramax_ai_articles_language == "ru"
    assert s.gramax_ai_response_language == "ru"


def test_settings_ai_timeout_from_env(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token")
    monkeypatch.setenv("GRAMAX_AI_TIMEOUT", "60")

    from gramax_docportal_mcp.config import Settings

    s = Settings(_env_file=None)
    assert s.gramax_ai_timeout == 60.0


def test_settings_ai_languages_from_env(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token")
    monkeypatch.setenv("GRAMAX_AI_ARTICLES_LANGUAGE", "en")
    monkeypatch.setenv("GRAMAX_AI_RESPONSE_LANGUAGE", "fr")

    from gramax_docportal_mcp.config import Settings

    s = Settings(_env_file=None)
    assert s.gramax_ai_articles_language == "en"
    assert s.gramax_ai_response_language == "fr"
