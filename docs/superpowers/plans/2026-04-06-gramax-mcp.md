# Gramax Doc Portal MCP Server — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an MCP server that exposes Gramax documentation portal content (search, articles, navigation, catalogs) to Claude/LLM via 4 tools.

**Architecture:** Flat 4-module Python package (server, client, config, formatters) following ktalk-mcp patterns. Async httpx client talks to Gramax API, formatters convert JSON/HTML responses to Markdown for LLM consumption.

**Tech Stack:** Python 3.12+, fastmcp>=2.0.0, httpx>=0.28.0, pydantic-settings>=2.0.0, markdownify>=0.14.1, hatchling, uv, ruff

**Reference project:** `/Users/mdemyanov/Devel/ktalk-mcp/` — follow its patterns exactly.

---

## File Structure

```
gramax_docportal_mcp/
├── src/gramax_docportal_mcp/
│   ├── __init__.py          # Package version
│   ├── config.py            # Settings from env vars (base_url, api_token)
│   ├── client.py            # Async httpx client + error hierarchy
│   ├── formatters.py        # JSON→MD, HTML→MD converters
│   └── server.py            # 4 MCP tools + lazy client + main()
├── tests/
│   ├── conftest.py          # Shared fixtures
│   ├── test_config.py       # Settings validation tests
│   ├── test_client.py       # API client tests with httpx mocking
│   └── test_formatters.py   # Formatter unit tests
├── pyproject.toml           # Project metadata, deps, scripts, ruff config
├── .gitignore               # Python standard ignores
├── CLAUDE.md                # Developer documentation
└── README.md                # User documentation
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/gramax_docportal_mcp/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialize git repo**

```bash
cd /Users/mdemyanov/Devel/gramax_docportal_mcp
git init
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "gramax-docportal-mcp"
version = "0.1.0"
description = "MCP server for Gramax documentation portal — search, read articles, browse catalogs"
readme = "README.md"
license = "MIT"
requires-python = ">=3.12"
authors = [
    { name = "Maksim Demyanov", email = "mdemyanov@users.noreply.github.com" },
]
keywords = ["mcp", "gramax", "documentation", "doc-portal"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
]
dependencies = [
    "fastmcp>=2.0.0",
    "httpx>=0.28.0",
    "pydantic-settings>=2.0.0",
    "markdownify>=0.14.1",
]

[project.scripts]
gramax-docportal-mcp = "gramax_docportal_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25.0",
    "pytest-httpx>=0.35.0",
    "ruff>=0.11.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W"]
```

- [ ] **Step 3: Create .gitignore**

```
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
dist/
build/
.eggs/
*.egg
.env
.venv/
venv/
.pytest_cache/
.ruff_cache/
.mypy_cache/
```

- [ ] **Step 4: Create __init__.py**

```python
"""MCP server for Gramax documentation portal."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Create tests/conftest.py**

```python
"""Shared test fixtures for gramax-docportal-mcp."""
```

- [ ] **Step 6: Install dependencies**

```bash
cd /Users/mdemyanov/Devel/gramax_docportal_mcp
uv sync
```

- [ ] **Step 7: Verify setup**

```bash
uv run python -c "from gramax_docportal_mcp import __version__; print(__version__)"
```

Expected: `0.1.0`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore src/ tests/
git commit -m "feat: project scaffolding"
```

---

### Task 2: Config Module

**Files:**
- Create: `src/gramax_docportal_mcp/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'gramax_docportal_mcp.config'`

- [ ] **Step 3: Write implementation**

```python
# src/gramax_docportal_mcp/config.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/gramax_docportal_mcp/config.py tests/test_config.py
git commit -m "feat: config module with pydantic-settings"
```

---

### Task 3: Client Module

**Files:**
- Create: `src/gramax_docportal_mcp/client.py`
- Create: `tests/test_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_client.py
import pytest
from pytest_httpx import HTTPXMock


@pytest.fixture
def base_url():
    return "https://docs.example.com"


@pytest.fixture
def api_token():
    return "test-api-token-123"


async def test_list_catalogs(httpx_mock: HTTPXMock, base_url, api_token):
    response_data = {"data": [{"id": "docs", "title": "Gramax Docs"}]}
    httpx_mock.add_response(json=response_data)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.list_catalogs()

    assert result == response_data
    request = httpx_mock.get_request()
    assert "/api/catalogs" in str(request.url)
    assert request.headers["authorization"] == "Bearer test-api-token-123"


async def test_get_navigation(httpx_mock: HTTPXMock, base_url, api_token):
    response_data = {"data": [{"id": "getting-started", "title": "Начало работы"}]}
    httpx_mock.add_response(json=response_data)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.get_navigation("docs")

    assert result == response_data
    request = httpx_mock.get_request()
    assert "/api/catalogs/docs/navigation" in str(request.url)


async def test_get_article_html(httpx_mock: HTTPXMock, base_url, api_token):
    html_content = "<h1>Заголовок</h1><p>Текст статьи.</p>"
    httpx_mock.add_response(text=html_content)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.get_article_html("docs", "getting-started")

    assert result == html_content
    request = httpx_mock.get_request()
    assert "/api/catalogs/docs/articles/getting-started/html" in str(request.url)


async def test_get_article_html_encodes_article_id(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(text="<p>ok</p>")

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        await client.get_article_html("docs", "deploy/docker")

    request = httpx_mock.get_request()
    assert "/api/catalogs/docs/articles/deploy%2Fdocker/html" in str(request.url)


async def test_search(httpx_mock: HTTPXMock, base_url, api_token):
    response_data = [{"type": "article", "title": [{"type": "text", "text": "Токен"}]}]
    httpx_mock.add_response(json=response_data)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.search("токен", catalog_name="docs")

    assert result == response_data
    request = httpx_mock.get_request()
    url_str = str(request.url)
    assert "/api/search/searchCommand" in url_str
    assert "catalogName=docs" in url_str


async def test_search_all_catalogs(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(json=[])

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        result = await client.search("query")

    assert result == []
    request = httpx_mock.get_request()
    assert "catalogName" not in str(request.url)


async def test_error_401(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=401, text="Unauthorized")

    from gramax_docportal_mcp.client import GramaxAuthError, GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxAuthError, match="Токен невалиден"):
            await client.list_catalogs()


async def test_error_403(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=403, text="Forbidden")

    from gramax_docportal_mcp.client import GramaxAuthError, GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxAuthError, match="Токен невалиден"):
            await client.list_catalogs()


async def test_error_404(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=404, text="Not Found")

    from gramax_docportal_mcp.client import GramaxClient, GramaxNotFoundError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNotFoundError, match="не найден"):
            await client.get_navigation("bad-catalog")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_client.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/gramax_docportal_mcp/client.py
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
    ) -> list[dict]:
        params: dict = {"query": query}
        if catalog_name is not None:
            params["catalogName"] = catalog_name
        response = await self._client.get("/api/search/searchCommand", params=params)
        self._check_response(response, f"поиск '{query}'")
        return response.json()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_client.py -v
```

Expected: 10 passed

- [ ] **Step 5: Run linter**

```bash
uv run ruff check src/gramax_docportal_mcp/client.py tests/test_client.py
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/gramax_docportal_mcp/client.py tests/test_client.py
git commit -m "feat: async HTTP client with error handling"
```

---

### Task 4: Formatters Module

**Files:**
- Create: `src/gramax_docportal_mcp/formatters.py`
- Create: `tests/test_formatters.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_formatters.py


class TestFormatCatalogsList:
    def test_basic_list(self):
        from gramax_docportal_mcp.formatters import format_catalogs_list

        data = {"data": [
            {"id": "docs", "title": "Gramax Docs"},
            {"id": "api-ref", "title": "API Reference"},
        ]}
        result = format_catalogs_list(data)
        assert "# Каталоги документации" in result
        assert "docs" in result
        assert "Gramax Docs" in result
        assert "api-ref" in result
        assert "API Reference" in result
        assert "Всего: 2" in result

    def test_empty_list(self):
        from gramax_docportal_mcp.formatters import format_catalogs_list

        data = {"data": []}
        result = format_catalogs_list(data)
        assert "Каталогов не найдено" in result


class TestFormatNavigation:
    def test_flat_tree(self):
        from gramax_docportal_mcp.formatters import format_navigation

        data = {"data": [
            {"id": "getting-started", "title": "Начало работы"},
            {"id": "deploy", "title": "Развёртывание"},
        ]}
        result = format_navigation("docs", data, "https://docs.example.com")
        assert "# Навигация: docs" in result
        assert "Начало работы" in result
        assert "https://docs.example.com/docs/getting-started" in result
        assert "Развёртывание" in result
        assert "https://docs.example.com/docs/deploy" in result

    def test_nested_tree(self):
        from gramax_docportal_mcp.formatters import format_navigation

        data = {"data": [
            {
                "id": "deploy",
                "title": "Развёртывание",
                "children": [
                    {"id": "deploy/docker", "title": "Docker"},
                    {"id": "deploy/k8s", "title": "Kubernetes"},
                ],
            },
        ]}
        result = format_navigation("docs", data, "https://docs.example.com")
        assert "Развёртывание" in result
        assert "  - " in result  # indented children
        assert "Docker" in result
        assert "https://docs.example.com/docs/deploy/docker" in result

    def test_empty_navigation(self):
        from gramax_docportal_mcp.formatters import format_navigation

        data = {"data": []}
        result = format_navigation("docs", data, "https://docs.example.com")
        assert "Навигация пуста" in result


class TestFormatSearchResults:
    def test_basic_results(self):
        from gramax_docportal_mcp.formatters import format_search_results

        results = [
            {
                "type": "article",
                "title": [
                    {"type": "highlight", "text": "Токен"},
                    {"type": "text", "text": " для API"},
                ],
                "url": "/docs/api-token",
                "breadcrumbs": [
                    {"url": "/docs/server", "title": "Сервер"},
                    {"url": "/docs/server/deploy", "title": "Развёртывание"},
                ],
                "catalog": {"name": "docs", "title": "Gramax Docs"},
                "items": [
                    {
                        "type": "paragraph",
                        "order": 0,
                        "items": [
                            {"type": "text", "text": "Используйте API-"},
                            {"type": "highlight", "text": "токен"},
                            {"type": "text", "text": "."},
                        ],
                        "score": 175,
                    },
                ],
            },
        ]
        result = format_search_results(results, "https://docs.example.com")
        assert "**Токен**" in result
        assert " для API" in result
        assert "https://docs.example.com/docs/api-token" in result
        assert "Сервер" in result
        assert "Развёртывание" in result
        assert "**токен**" in result
        assert "Найдено: 1" in result

    def test_empty_results(self):
        from gramax_docportal_mcp.formatters import format_search_results

        result = format_search_results([], "https://docs.example.com")
        assert "Ничего не найдено" in result

    def test_highlight_extraction(self):
        from gramax_docportal_mcp.formatters import _render_highlights

        items = [
            {"type": "text", "text": "обычный "},
            {"type": "highlight", "text": "выделенный"},
            {"type": "text", "text": " текст"},
        ]
        result = _render_highlights(items)
        assert result == "обычный **выделенный** текст"


class TestHtmlToMarkdown:
    def test_basic_html(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        html = "<h1>Заголовок</h1><p>Текст <strong>жирный</strong> и <em>курсив</em>.</p>"
        result = html_to_markdown(html)
        assert "# Заголовок" in result
        assert "**жирный**" in result
        assert "*курсив*" in result

    def test_strips_scripts_and_styles(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        html = "<p>Текст</p><script>alert(1)</script><style>.x{}</style>"
        result = html_to_markdown(html)
        assert "Текст" in result
        assert "alert" not in result
        assert ".x{}" not in result

    def test_links_preserved(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        html = '<p>Смотри <a href="/docs/page">документацию</a>.</p>'
        result = html_to_markdown(html)
        assert "документацию" in result

    def test_empty_html(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        assert html_to_markdown("") == ""
        assert html_to_markdown("   ") == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_formatters.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

```python
# src/gramax_docportal_mcp/formatters.py
"""Converters from Gramax API responses to markdown."""

from __future__ import annotations

from markdownify import markdownify


def format_catalogs_list(data: dict) -> str:
    """Format catalogs list to markdown table."""
    catalogs = data.get("data", [])

    if not catalogs:
        return "# Каталоги документации\n\nКаталогов не найдено."

    lines = [
        "# Каталоги документации",
        "",
        "| Каталог | ID |",
        "|---------|-----|",
    ]

    for cat in catalogs:
        lines.append(f"| {cat['title']} | {cat['id']} |")

    lines.append("")
    lines.append(f"Всего: {len(catalogs)}")

    return "\n".join(lines)


def _render_tree(items: list[dict], base_url: str, catalog_id: str, depth: int = 0) -> list[str]:
    """Recursively render navigation tree to markdown lines."""
    lines: list[str] = []
    indent = "  " * depth
    for item in items:
        url = f"{base_url}/{catalog_id}/{item['id']}"
        lines.append(f"{indent}- [{item['title']}]({url})")
        children = item.get("children", [])
        if children:
            lines.extend(_render_tree(children, base_url, catalog_id, depth + 1))
    return lines


def format_navigation(catalog_id: str, data: dict, base_url: str) -> str:
    """Format catalog navigation tree to markdown."""
    items = data.get("data", [])

    if not items:
        return f"# Навигация: {catalog_id}\n\nНавигация пуста."

    lines = [f"# Навигация: {catalog_id}", ""]
    lines.extend(_render_tree(items, base_url, catalog_id))

    return "\n".join(lines)


def _render_highlights(items: list[dict]) -> str:
    """Render title/text items with highlight markers to markdown."""
    parts: list[str] = []
    for item in items:
        text = item.get("text", "")
        if item.get("type") == "highlight":
            parts.append(f"**{text}**")
        else:
            parts.append(text)
    return "".join(parts)


def _render_snippet(items: list[dict]) -> str:
    """Extract first text snippet from search result items."""
    for item in items:
        if item.get("type") == "paragraph":
            sub_items = item.get("items", [])
            if sub_items:
                return _render_highlights(sub_items)
    return ""


def format_search_results(results: list[dict], base_url: str) -> str:
    """Format search results to markdown."""
    if not results:
        return "Ничего не найдено."

    lines: list[str] = []

    for i, result in enumerate(results, 1):
        title = _render_highlights(result.get("title", []))
        url = f"{base_url}{result.get('url', '')}"

        breadcrumbs = result.get("breadcrumbs", [])
        catalog = result.get("catalog", {})
        path_parts = [catalog.get("title", "")] + [b["title"] for b in breadcrumbs]
        path = " > ".join(p for p in path_parts if p)

        lines.append(f"## {i}. {title}")
        if path:
            lines.append(f"📂 {path}")
        lines.append(f"🔗 {url}")
        lines.append("")

        snippet = _render_snippet(result.get("items", []))
        if snippet:
            lines.append(f"> {snippet}")
            lines.append("")

    lines.append(f"Найдено: {len(results)}")

    return "\n".join(lines)


def html_to_markdown(html: str) -> str:
    """Convert HTML to clean Markdown for LLM consumption."""
    if not html or not html.strip():
        return ""

    md = markdownify(
        html,
        heading_style="ATX",
        strip=["img", "script", "style"],
    )

    # Clean up excessive blank lines
    while "\n\n\n" in md:
        md = md.replace("\n\n\n", "\n\n")

    return md.strip()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_formatters.py -v
```

Expected: 10 passed

- [ ] **Step 5: Run linter**

```bash
uv run ruff check src/gramax_docportal_mcp/formatters.py tests/test_formatters.py
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/gramax_docportal_mcp/formatters.py tests/test_formatters.py
git commit -m "feat: formatters for catalogs, navigation, search, HTML→MD"
```

---

### Task 5: Server Module (MCP Tools)

**Files:**
- Create: `src/gramax_docportal_mcp/server.py`

- [ ] **Step 1: Write implementation**

```python
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
```

- [ ] **Step 2: Verify import works**

```bash
uv run python -c "from gramax_docportal_mcp.server import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run linter**

```bash
uv run ruff check src/gramax_docportal_mcp/server.py
```

Expected: no errors

- [ ] **Step 4: Run all tests**

```bash
uv run pytest -v
```

Expected: all tests pass (config + client + formatters)

- [ ] **Step 5: Commit**

```bash
git add src/gramax_docportal_mcp/server.py
git commit -m "feat: MCP server with 4 tools (list, nav, search, article)"
```

---

### Task 6: CLAUDE.md and README.md

**Files:**
- Create: `CLAUDE.md`
- Create: `README.md`

- [ ] **Step 1: Write CLAUDE.md**

```markdown
# gramax-docportal-mcp

MCP-сервер для портала документации Gramax.

## Stack

Python 3.12+, fastmcp, httpx, pydantic-settings, markdownify

## Commands

- `uv run gramax-docportal-mcp` — запуск сервера
- `uv run pytest` — тесты
- `uv run ruff check .` — линтер
- `uv run ruff check . --fix` — автоисправление

## Architecture

Плоская 4-модульная структура:

- `server.py` — 4 MCP-инструмента + точка входа
- `client.py` — async httpx обёртка для Gramax API
- `formatters.py` — JSON→Markdown, HTML→Markdown конвертеры
- `config.py` — настройки из переменных окружения

## API Reference

Gramax Doc Portal API:

- `GET /api/catalogs` — список каталогов
- `GET /api/catalogs/{id}/navigation` — дерево навигации
- `GET /api/catalogs/{id}/articles/{articleId}/html` — HTML статьи
- `GET /api/search/searchCommand?query=...&catalogName=...` — поиск

Auth: `Authorization: Bearer <token>` (получить через `GET /api/user/token`)

## Conventions

- Async everywhere
- Все сообщения об ошибках на русском
- HTML статей конвертируется в Markdown через markdownify
- article_id в URL передаётся URL-encoded
```

- [ ] **Step 2: Write README.md**

```markdown
# gramax-docportal-mcp

MCP-сервер для доступа к порталу документации [Gramax](https://gram.ax). Позволяет искать статьи, получать контент и навигацию через Claude и другие LLM.

## Инструменты

| Инструмент | Описание |
|-----------|----------|
| `gramax_list_catalogs` | Список всех каталогов документации |
| `gramax_get_navigation` | Дерево навигации каталога |
| `gramax_search` | Поиск по статьям |
| `gramax_get_article` | Содержимое статьи в Markdown |

## Установка

```bash
uv tool install gramax-docportal-mcp
```

## Настройка

Добавьте в `.mcp.json`:

```json
{
  "mcpServers": {
    "gramax": {
      "command": "uvx",
      "args": ["gramax-docportal-mcp"],
      "env": {
        "GRAMAX_BASE_URL": "https://your-portal.example.com",
        "GRAMAX_API_TOKEN": "ваш-api-токен"
      }
    }
  }
}
```

### Получение токена

Откройте в браузере (будучи залогиненным на портале):

```
https://your-portal.example.com/api/user/token
```

Токен действует 30 дней. Для кастомного срока:

```
https://your-portal.example.com/api/user/token?expiresAt=2026-12-31
```

## Переменные окружения

| Переменная | Описание | Обязательно |
|-----------|----------|:-----------:|
| `GRAMAX_BASE_URL` | URL портала документации | Да |
| `GRAMAX_API_TOKEN` | API-токен (Bearer) | Да |

## Лицензия

MIT
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: add CLAUDE.md and README.md"
```

---

### Task 7: Final Verification

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/mdemyanov/Devel/gramax_docportal_mcp
uv run pytest -v
```

Expected: all tests pass

- [ ] **Step 2: Run linter on entire project**

```bash
uv run ruff check .
```

Expected: no errors

- [ ] **Step 3: Verify CLI entry point**

```bash
uv run python -c "from gramax_docportal_mcp.server import mcp; print(f'Tools: {len(mcp._tool_manager._tools)}')"
```

Expected: `Tools: 4`

- [ ] **Step 4: Final commit if needed**

If any fixes were applied, commit them.
