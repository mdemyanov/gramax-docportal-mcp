"""Shared test fixtures for gramax-docportal-mcp."""

import pytest


@pytest.fixture
def base_url():
    return "https://docs.example.com"


@pytest.fixture
def api_token():
    return "test-api-token-123"
