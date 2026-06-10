from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import httpx


class GramaxError(Exception):
    """Base error for Gramax API."""


class GramaxAuthError(GramaxError):
    """API token expired or invalid."""


class GramaxNotFoundError(GramaxError):
    """Catalog or article not found."""


class GramaxServerError(GramaxError):
    """Gramax server returned a 5xx error."""


class GramaxNetworkError(GramaxError):
    """Network error: timeout, connection failure, or invalid response."""


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
        if response.status_code >= 500:
            raise GramaxServerError(
                f"Сервер Gramax вернул ошибку {response.status_code} при запросе: {context}. "
                "Попробуйте позже или обратитесь к администратору портала."
            )
        response.raise_for_status()  # 4xx кроме 401/403/404

    def _safe_json(self, response: httpx.Response, context: str = "") -> Any:
        try:
            return response.json()
        except Exception:
            raise GramaxNetworkError(
                f"Gramax вернул нечитаемый ответ при запросе: {context}. "
                "Возможно, сервер перегружен или вернул HTML вместо JSON."
            )

    async def list_catalogs(self) -> dict[str, Any]:
        try:
            response = await self._client.get("/api/catalogs")
        except httpx.TimeoutException:
            raise GramaxNetworkError(
                "Превышено время ожидания ответа от Gramax при запросе: список каталогов. "
                "Проверьте доступность портала или увеличьте таймаут."
            )
        except httpx.NetworkError as e:
            raise GramaxNetworkError(
                "Не удалось подключиться к Gramax при запросе: список каталогов. "
                f"Проверьте сетевое подключение и адрес портала. Детали: {type(e).__name__}"
            ) from e
        self._check_response(response, "список каталогов")
        result: dict[str, Any] = self._safe_json(response, "список каталогов")
        return result

    async def get_navigation(self, catalog_id: str) -> dict[str, Any]:
        context = f"навигация каталога {catalog_id}"
        try:
            response = await self._client.get(f"/api/catalogs/{catalog_id}/navigation")
        except httpx.TimeoutException:
            raise GramaxNetworkError(
                f"Превышено время ожидания ответа от Gramax при запросе: {context}. "
                "Проверьте доступность портала или увеличьте таймаут."
            )
        except httpx.NetworkError as e:
            raise GramaxNetworkError(
                f"Не удалось подключиться к Gramax при запросе: {context}. "
                f"Проверьте сетевое подключение и адрес портала. Детали: {type(e).__name__}"
            ) from e
        self._check_response(response, context)
        result: dict[str, Any] = self._safe_json(response, context)
        return result

    async def get_article_html(self, catalog_id: str, article_id: str) -> str:
        encoded_id = quote(article_id, safe="")
        context = f"статья {article_id} в каталоге {catalog_id}"
        try:
            response = await self._client.get(
                f"/api/catalogs/{catalog_id}/articles/{encoded_id}/html"
            )
        except httpx.TimeoutException:
            raise GramaxNetworkError(
                f"Превышено время ожидания ответа от Gramax при запросе: {context}. "
                "Проверьте доступность портала или увеличьте таймаут."
            )
        except httpx.NetworkError as e:
            raise GramaxNetworkError(
                f"Не удалось подключиться к Gramax при запросе: {context}. "
                f"Проверьте сетевое подключение и адрес портала. Детали: {type(e).__name__}"
            ) from e
        self._check_response(response, context)
        return response.text

    async def search(
        self,
        query: str,
        *,
        catalog_name: str | None = None,
        search_type: str | None = None,
        language: str | None = None,
        resource_filter: str | None = None,
        property_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"query": query}
        if catalog_name is not None:
            params["catalogName"] = catalog_name
        if search_type is not None:
            params["type"] = search_type
        if language is not None:
            params["articlesLanguage"] = language

        body: dict[str, Any] | None = None
        if resource_filter is not None or property_filter is not None:
            body = {}
            if resource_filter is not None:
                body["resourceFilter"] = resource_filter
            if property_filter is not None:
                body["propertyFilter"] = property_filter

        context = f"поиск '{query}'"
        try:
            response = await self._client.request(
                "GET",
                "/api/search/searchCommand",
                params=params,
                json=body,
            )
        except httpx.TimeoutException:
            raise GramaxNetworkError(
                f"Превышено время ожидания ответа от Gramax при запросе: {context}. "
                "Проверьте доступность портала или увеличьте таймаут."
            )
        except httpx.NetworkError as e:
            raise GramaxNetworkError(
                f"Не удалось подключиться к Gramax при запросе: {context}. "
                f"Проверьте сетевое подключение и адрес портала. Детали: {type(e).__name__}"
            ) from e
        self._check_response(response, context)
        result: list[dict[str, Any]] = self._safe_json(response, context)
        return result

    @staticmethod
    def _parse_chat_line(line: str) -> str:
        """Extract text from a single NDJSON line; return empty string to skip."""
        if not line.strip():
            return ""
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return ""
        if obj.get("type") == "text":
            text = obj.get("text", "")
            return text if isinstance(text, str) else ""
        return ""

    async def ai_search(
        self,
        query: str,
        *,
        catalog_name: str | None = None,
        articles_language: str | None = None,
        response_language: str | None = None,
        current_article: str | None = None,
        timeout: float = 120.0,  # noqa: ASYNC109 — timeout прокидывается в httpx, использовать asyncio.timeout здесь нельзя из-за streaming
    ) -> AsyncIterator[str]:
        """Yield text chunks from /api/search/chat NDJSON stream."""
        params: dict[str, str] = {"query": query}
        if catalog_name is not None:
            params["catalogName"] = catalog_name
        if articles_language is not None:
            params["articlesLanguage"] = articles_language
        if response_language is not None:
            params["responseLanguage"] = response_language
        if current_article is not None:
            params["currentArticle"] = current_article

        context = f"AI-поиск '{query}'"
        try:
            async with self._client.stream(
                "GET",
                "/api/search/chat",
                params=params,
                timeout=timeout,
            ) as response:
                self._check_response(response, context)
                async for line in response.aiter_lines():
                    text = self._parse_chat_line(line)
                    if text:
                        yield text
        except GramaxError:
            raise
        except httpx.NetworkError as e:
            raise GramaxNetworkError(
                f"Не удалось подключиться к Gramax при запросе: {context}. "
                f"Проверьте сетевое подключение и адрес портала. Детали: {type(e).__name__}"
            ) from e
