"""Tests for MCP server tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import Context

from gramax_docportal_mcp.client import GramaxAuthError, GramaxClient, GramaxError
from gramax_docportal_mcp.server import (
    gramax_get_article,
    gramax_get_navigation,
    gramax_list_catalogs,
    gramax_search,
)


@pytest.fixture
def mock_ctx():
    """Create a mock Context with a mock GramaxClient in lifespan_context."""
    mock_client = AsyncMock(spec=GramaxClient)
    ctx = MagicMock(spec=Context)
    ctx.lifespan_context = {
        "client": mock_client,
        "base_url": "https://docs.example.com",
    }
    return ctx, mock_client


class TestGramaxListCatalogs:
    async def test_returns_formatted_catalogs(self, mock_ctx):
        ctx, mock_client = mock_ctx
        mock_client.list_catalogs.return_value = {
            "data": [{"id": "docs", "title": "Gramax Docs"}]
        }

        result = await gramax_list_catalogs(ctx)

        assert "Gramax Docs" in result
        assert "docs" in result
        mock_client.list_catalogs.assert_awaited_once()

    async def test_returns_error_on_gramax_error(self, mock_ctx):
        ctx, mock_client = mock_ctx
        mock_client.list_catalogs.side_effect = GramaxError("Ошибка сети")

        result = await gramax_list_catalogs(ctx)

        assert "Ошибка сети" in result


class TestGramaxGetNavigation:
    async def test_returns_formatted_navigation(self, mock_ctx):
        ctx, mock_client = mock_ctx
        mock_client.get_navigation.return_value = {
            "data": [{"id": "intro", "title": "Введение"}]
        }

        result = await gramax_get_navigation(ctx, "docs")

        assert "Введение" in result
        assert "https://docs.example.com/docs/intro" in result
        mock_client.get_navigation.assert_awaited_once_with("docs")

    async def test_empty_catalog_id_returns_error(self, mock_ctx):
        ctx, _ = mock_ctx

        result = await gramax_get_navigation(ctx, "")

        assert "Ошибка" in result
        assert "catalog_id" in result

    async def test_returns_error_on_gramax_error(self, mock_ctx):
        ctx, mock_client = mock_ctx
        mock_client.get_navigation.side_effect = GramaxError("Каталог не найден")

        result = await gramax_get_navigation(ctx, "bad-id")

        assert "Каталог не найден" in result


class TestGramaxSearch:
    async def test_returns_formatted_results(self, mock_ctx):
        ctx, mock_client = mock_ctx
        mock_client.search.return_value = [
            {
                "type": "article",
                "title": [{"type": "text", "text": "Результат"}],
                "url": "/docs/result",
                "breadcrumbs": [],
                "catalog": {"name": "docs", "title": "Docs"},
                "items": [],
            }
        ]

        result = await gramax_search(ctx, "запрос")

        assert "Результат" in result
        assert "Найдено: 1" in result
        mock_client.search.assert_awaited_once_with(
            "запрос",
            catalog_name=None,
            search_type=None,
            language=None,
            resource_filter=None,
            property_filter=None,
        )

    async def test_passes_all_filters(self, mock_ctx):
        ctx, mock_client = mock_ctx
        mock_client.search.return_value = []

        await gramax_search(
            ctx,
            "test",
            catalog_name="docs",
            search_type="vector",
            language="ru",
            resource_filter="without",
            property_filter={"op": "eq", "key": "K", "value": "V"},
        )

        mock_client.search.assert_awaited_once_with(
            "test",
            catalog_name="docs",
            search_type="vector",
            language="ru",
            resource_filter="without",
            property_filter={"op": "eq", "key": "K", "value": "V"},
        )

    async def test_empty_query_returns_error(self, mock_ctx):
        ctx, _ = mock_ctx

        result = await gramax_search(ctx, "")

        assert "Ошибка" in result
        assert "запрос" in result

    async def test_returns_error_on_gramax_error(self, mock_ctx):
        ctx, mock_client = mock_ctx
        mock_client.search.side_effect = GramaxAuthError(
            "Токен невалиден или истёк."
        )

        result = await gramax_search(ctx, "test")

        assert "Токен невалиден" in result


class TestGramaxGetArticle:
    async def test_returns_markdown_content(self, mock_ctx):
        ctx, mock_client = mock_ctx
        mock_client.get_article_html.return_value = (
            "<h1>Заголовок</h1><p>Текст.</p>"
        )

        result = await gramax_get_article(ctx, "docs", "intro")

        assert "# Заголовок" in result
        assert "Текст" in result
        mock_client.get_article_html.assert_awaited_once_with("docs", "intro")

    async def test_empty_catalog_id_returns_error(self, mock_ctx):
        ctx, _ = mock_ctx

        result = await gramax_get_article(ctx, "", "intro")

        assert "Ошибка" in result
        assert "catalog_id" in result

    async def test_empty_article_id_returns_error(self, mock_ctx):
        ctx, _ = mock_ctx

        result = await gramax_get_article(ctx, "docs", "  ")

        assert "Ошибка" in result
        assert "article_id" in result

    async def test_returns_error_on_gramax_error(self, mock_ctx):
        ctx, mock_client = mock_ctx
        mock_client.get_article_html.side_effect = GramaxError("Не найдено")

        result = await gramax_get_article(ctx, "docs", "missing")

        assert "Не найдено" in result
