import pytest


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token-abc")

    from gramax_docportal_mcp.config import Settings

    settings = Settings()
    assert settings.gramax_base_url == "https://docs.example.com"
    assert settings.gramax_api_token == "test-token-abc"


def test_settings_requires_base_url(monkeypatch):
    monkeypatch.delenv("GRAMAX_BASE_URL", raising=False)
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token")

    from gramax_docportal_mcp.config import Settings

    with pytest.raises(Exception):
        Settings()


def test_settings_requires_api_token(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.delenv("GRAMAX_API_TOKEN", raising=False)

    from gramax_docportal_mcp.config import Settings

    with pytest.raises(Exception):
        Settings()
