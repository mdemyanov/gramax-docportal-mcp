# src/gramax_docportal_mcp/server.py
"""Gramax Doc Portal MCP Server — search, read articles, browse catalogs."""

from __future__ import annotations

from fastmcp import Context, FastMCP
from fastmcp.server.lifespan import lifespan

from gramax_docportal_mcp.client import GramaxClient, GramaxError
from gramax_docportal_mcp.config import Settings
from gramax_docportal_mcp.formatters import (
    format_catalogs_list,
    format_navigation,
    format_search_results,
    html_to_markdown,
)


@lifespan
async def app_lifespan(server):
    """Create GramaxClient on startup, close on shutdown."""
    settings = Settings()
    base_url = settings.gramax_base_url.rstrip("/")
    async with GramaxClient(base_url=base_url, api_token=settings.gramax_api_token) as client:
        yield {"client": client, "base_url": base_url}


mcp = FastMCP(
    "Gramax",
    instructions="Search and read documentation from Gramax Doc Portal",
    lifespan=app_lifespan,
)


@mcp.tool()
async def gramax_list_catalogs(ctx: Context) -> str:
    """Получить список всех каталогов документации на портале Gramax.

    Возвращает таблицу с названиями и ID каталогов.
    """
    try:
        client = ctx.lifespan_context["client"]
        data = await client.list_catalogs()
        return format_catalogs_list(data)
    except GramaxError as e:
        return str(e)


@mcp.tool()
async def gramax_get_navigation(ctx: Context, catalog_id: str) -> str:
    """Получить дерево навигации каталога: разделы, статьи, ссылки.

    Args:
        catalog_id: ID каталога (получить через gramax_list_catalogs)
    """
    try:
        client = ctx.lifespan_context["client"]
        base_url = ctx.lifespan_context["base_url"]
        data = await client.get_navigation(catalog_id)
        return format_navigation(catalog_id, data, base_url)
    except GramaxError as e:
        return str(e)


@mcp.tool()
async def gramax_search(
    ctx: Context,
    query: str,
    catalog_name: str | None = None,
    search_type: str | None = None,
    language: str | None = None,
    resource_filter: str | None = None,
    property_filter: dict | None = None,
) -> str:
    """Поиск по статьям документации Gramax.

    Args:
        query: Поисковый запрос (авто-раскладка RU/EN и транслитерация)
        catalog_name: Имя каталога для поиска (без него — поиск по всем каталогам)
        search_type: Тип поиска — "vector" для семантического, без значения — полнотекстовый
        language: Язык статей: "ru", "en", "es", "zh", "fr", "de", "ja" и др.
        resource_filter: Фильтр ресурсов: "without" — только статьи,
            "only" — только файлы, "with" — всё (по умолчанию)
        property_filter: Фильтр по свойствам статей. Примеры:
            {"op": "eq", "key": "Продукт", "value": "NSD"}
            {"op": "contains", "key": "Сегмент",
             "list": ["Enterprise", "SMB"]}
            {"op": "and", "filters": [
             {"op": "eq", "key": "Тип контента", "value": "Кейс"},
             {"op": "eq", "key": "Отрасль", "value": "Логистика"}
            ]}
    """
    try:
        client = ctx.lifespan_context["client"]
        base_url = ctx.lifespan_context["base_url"]
        results = await client.search(
            query,
            catalog_name=catalog_name,
            search_type=search_type,
            language=language,
            resource_filter=resource_filter,
            property_filter=property_filter,
        )
        return format_search_results(results, base_url)
    except GramaxError as e:
        return str(e)


@mcp.tool()
async def gramax_get_article(ctx: Context, catalog_id: str, article_id: str) -> str:
    """Получить содержимое статьи в формате Markdown.

    Args:
        catalog_id: ID каталога
        article_id: ID статьи (получить через gramax_get_navigation или gramax_search)
    """
    try:
        client = ctx.lifespan_context["client"]
        html = await client.get_article_html(catalog_id, article_id)
        return html_to_markdown(html)
    except GramaxError as e:
        return str(e)


def main():
    mcp.run()
