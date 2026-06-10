"""Tests for MCP server tools."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import Context

from gramax_docportal_mcp.client import GramaxAuthError, GramaxClient, GramaxError
from gramax_docportal_mcp.server import (
    gramax_ai_search,
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


@pytest.fixture
def mock_ctx_ai():
    """Context with mock GramaxClient (ai_search as real async-gen) and Settings."""
    from gramax_docportal_mcp.config import Settings

    mock_client = AsyncMock(spec=GramaxClient)
    # ai_search must yield — replace AsyncMock attribute with a real async-gen factory.
    holder: dict = {"chunks": [], "called": 0}

    async def fake_ai_search(*args, **kwargs):
        holder["called"] += 1
        for c in holder["chunks"]:
            yield c

    mock_client.ai_search = fake_ai_search

    settings = Settings(
        gramax_base_url="https://docs.example.com",
        gramax_api_token="t",  # noqa: S106
        _env_file=None,
    )

    ctx = MagicMock(spec=Context)
    ctx.lifespan_context = {
        "client": mock_client,
        "base_url": "https://docs.example.com",
        "settings": settings,
    }
    ctx.report_progress = AsyncMock()
    return ctx, mock_client, holder


class TestGramaxAiSearch:
    async def test_happy_path_returns_markdown_with_sources(self, mock_ctx_ai):
        ctx, _client, holder = mock_ctx_ai
        zwsp = "​"
        wj = "⁠"
        marker = f"{zwsp}{wj}CIT{wj}1{wj}cat/intro{wj}./intro.md{wj}{wj}{zwsp}"
        holder["chunks"] = ["Hello", f" world {marker}", "."]

        result = await gramax_ai_search(ctx, "test query")

        assert "Hello world [1](cat/intro)." in result
        assert "## Источники" in result
        assert "1. `cat/intro`" in result
        assert "https://docs.example.com/cat/intro" in result

    async def test_empty_query_returns_error_without_http(self, mock_ctx_ai):
        ctx, _client, holder = mock_ctx_ai

        result = await gramax_ai_search(ctx, "   ")

        assert "Ошибка" in result
        assert "запрос" in result
        assert holder["called"] == 0  # ai_search must NOT have been invoked

    async def test_progress_called_per_chunk(self, mock_ctx_ai):
        ctx, _client, holder = mock_ctx_ai
        holder["chunks"] = ["a", "b", "c", "d"]

        await gramax_ai_search(ctx, "q")

        assert ctx.report_progress.await_count == 4

    async def test_timeout_returns_russian_message(self, mock_ctx_ai):
        import httpx

        ctx, mock_client, _ = mock_ctx_ai

        async def fake_timeout(*args, **kwargs):
            raise httpx.ReadTimeout("timed out")
            yield  # make it an async generator

        mock_client.ai_search = fake_timeout

        result = await gramax_ai_search(ctx, "q")

        assert "Превышено время ожидания" in result
        assert "GRAMAX_AI_TIMEOUT" in result

    async def test_auth_error_propagated_as_russian(self, mock_ctx_ai):
        ctx, mock_client, _ = mock_ctx_ai

        async def fake_auth(*args, **kwargs):
            raise GramaxAuthError("Токен невалиден или истёк.")
            yield  # generator marker

        mock_client.ai_search = fake_auth

        result = await gramax_ai_search(ctx, "q")

        assert "Токен невалиден" in result

    async def test_uses_default_languages_from_settings(self, mock_ctx_ai):
        """Settings defaults applied when MCP args are None."""
        ctx, mock_client, holder = mock_ctx_ai
        holder["chunks"] = []
        captured: dict = {}

        async def capturing(*args, **kwargs):
            captured.update(kwargs)
            return
            yield  # generator marker

        mock_client.ai_search = capturing

        await gramax_ai_search(ctx, "q")

        assert captured["articles_language"] == "ru"
        assert captured["response_language"] == "ru"

    async def test_stream_disconnect_returns_partial_with_marker(self, mock_ctx_ai):
        """Spec: сетевой разрыв — отдаём накопленное + пометку в конце."""
        import httpx

        ctx, mock_client, _ = mock_ctx_ai

        async def fake_disconnect(*args, **kwargs):
            yield "Часть ответа до разрыва."
            raise httpx.RemoteProtocolError("Server disconnected")

        mock_client.ai_search = fake_disconnect

        result = await gramax_ai_search(ctx, "q")

        assert "Часть ответа до разрыва." in result
        assert "ответ оборван" in result


# AC-7: gramax_search при HTTP 500 → русское сообщение (без traceback)
class TestGramaxSearchServerErrors:
    async def test_500_returns_russian_message_no_traceback(self, mock_ctx):
        from gramax_docportal_mcp.client import GramaxServerError

        ctx, mock_client = mock_ctx
        mock_client.search.side_effect = GramaxServerError(
            "Сервер Gramax вернул ошибку 500 при запросе: поиск 'test'. "
            "Попробуйте позже или обратитесь к администратору портала."
        )

        result = await gramax_search(ctx, "test")

        assert "500" in result
        assert "Попробуйте позже" in result
        assert "Traceback" not in result
        assert "HTTPStatusError" not in result

    async def test_network_error_returns_russian_message(self, mock_ctx):
        from gramax_docportal_mcp.client import GramaxNetworkError

        ctx, mock_client = mock_ctx
        mock_client.search.side_effect = GramaxNetworkError(
            "Не удалось подключиться к Gramax при запросе: поиск 'test'. "
            "Детали: ConnectError"
        )

        result = await gramax_search(ctx, "test")

        assert "подключиться" in result
        assert "ConnectError" in result
        assert "Traceback" not in result


# AC-8: gramax_list_catalogs при HTTP 503 → русское сообщение
class TestGramaxListCatalogsServerErrors:
    async def test_503_returns_russian_message(self, mock_ctx):
        from gramax_docportal_mcp.client import GramaxServerError

        ctx, mock_client = mock_ctx
        mock_client.list_catalogs.side_effect = GramaxServerError(
            "Сервер Gramax вернул ошибку 503 при запросе: список каталогов. "
            "Попробуйте позже или обратитесь к администратору портала."
        )

        result = await gramax_list_catalogs(ctx)

        assert "503" in result
        assert "Попробуйте позже" in result
        assert "HTTPStatusError" not in result
