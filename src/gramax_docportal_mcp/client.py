from __future__ import annotations

from urllib.parse import quote

import httpx


class GramaxError(Exception):
    """Base error for Gramax API."""


class GramaxAuthError(GramaxError):
    """API token expired or invalid."""


class GramaxNotFoundError(GramaxError):
    """Catalog or article not found."""


class GramaxClient:
    """Async HTTP client for Gramax Doc Portal API.

    Usage::

        async with GramaxClient(base_url, api_token) as client:
            catalogs = await client.list_catalogs()
    """

    def __init__(self, base_url: str, api_token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=30.0,
        )

    async def __aenter__(self) -> GramaxClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()

    def _check_response(self, response: httpx.Response, context: str = "") -> None:
        if response.status_code in (401, 403):
            raise GramaxAuthError(
                "Токен невалиден или истёк. "
                "Получите новый: GET /api/user/token"
            )
        if response.status_code == 404:
            raise GramaxNotFoundError(f"Ресурс не найден: {context}")
        response.raise_for_status()

    async def list_catalogs(self) -> dict:
        response = await self._client.get("/api/catalogs")
        self._check_response(response, "список каталогов")
        return response.json()

    async def get_navigation(self, catalog_id: str) -> dict:
        response = await self._client.get(f"/api/catalogs/{catalog_id}/navigation")
        self._check_response(response, f"каталог {catalog_id}")
        return response.json()

    async def get_article_html(self, catalog_id: str, article_id: str) -> str:
        encoded_id = quote(article_id, safe="")
        response = await self._client.get(
            f"/api/catalogs/{catalog_id}/articles/{encoded_id}/html"
        )
        self._check_response(response, f"статья {article_id} в каталоге {catalog_id}")
        return response.text

    async def search(
        self,
        query: str,
        *,
        catalog_name: str | None = None,
        search_type: str | None = None,
        language: str | None = None,
        resource_filter: str | None = None,
        property_filter: dict | None = None,
    ) -> list[dict]:
        params: dict = {"query": query}
        if catalog_name is not None:
            params["catalogName"] = catalog_name
        if search_type is not None:
            params["type"] = search_type
        if language is not None:
            params["articlesLanguage"] = language

        body: dict | None = None
        if resource_filter is not None or property_filter is not None:
            body = {}
            if resource_filter is not None:
                body["resourceFilter"] = resource_filter
            if property_filter is not None:
                body["propertyFilter"] = property_filter

        response = await self._client.request(
            "GET",
            "/api/search/searchCommand",
            params=params,
            json=body,
        )
        self._check_response(response, f"поиск '{query}'")
        return response.json()
