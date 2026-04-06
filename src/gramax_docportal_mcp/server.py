# src/gramax_docportal_mcp/server.py
"""Gramax Doc Portal MCP Server — search, read articles, browse catalogs."""

from __future__ import annotations

from fastmcp import FastMCP

from gramax_docportal_mcp.client import GramaxClient, GramaxError
from gramax_docportal_mcp.config import Settings
from gramax_docportal_mcp.formatters import (
    format_catalogs_list,
    format_navigation,
    format_search_results,
    html_to_markdown,
)

mcp = FastMCP(
    "Gramax",
    instructions="Search and read documentation from Gramax Doc Portal",
)

_client: GramaxClient | None = None
_base_url: str = ""


def _get_client() -> GramaxClient:
    global _client, _base_url
    if _client is None:
        settings = Settings()
        _base_url = settings.gramax_base_url.rstrip("/")
        _client = GramaxClient(
            base_url=_base_url,
            api_token=settings.gramax_api_token,
        )
    return _client


@mcp.tool()
async def gramax_list_catalogs() -> str:
    """Получить список всех каталогов документации на портале Gramax.

    Возвращает таблицу с названиями и ID каталогов.
    """
    try:
        client = _get_client()
        data = await client.list_catalogs()
        return format_catalogs_list(data)
    except GramaxError as e:
        return str(e)


@mcp.tool()
async def gramax_get_navigation(catalog_id: str) -> str:
    """Получить дерево навигации каталога: разделы, статьи, ссылки.

    Args:
        catalog_id: ID каталога (получить через gramax_list_catalogs)
    """
    try:
        client = _get_client()
        data = await client.get_navigation(catalog_id)
        return format_navigation(catalog_id, data, _base_url)
    except GramaxError as e:
        return str(e)


@mcp.tool()
async def gramax_search(
    query: str,
    catalog_name: str | None = None,
) -> str:
    """Поиск по статьям документации Gramax.

    Args:
        query: Поисковый запрос
        catalog_name: Имя каталога для поиска (без него — поиск по всем каталогам)
    """
    try:
        client = _get_client()
        results = await client.search(query, catalog_name=catalog_name)
        return format_search_results(results, _base_url)
    except GramaxError as e:
        return str(e)


@mcp.tool()
async def gramax_get_article(catalog_id: str, article_id: str) -> str:
    """Получить содержимое статьи в формате Markdown.

    Args:
        catalog_id: ID каталога
        article_id: ID статьи (получить через gramax_get_navigation или gramax_search)
    """
    try:
        client = _get_client()
        html = await client.get_article_html(catalog_id, article_id)
        return html_to_markdown(html)
    except GramaxError as e:
        return str(e)


def main():
    mcp.run()
