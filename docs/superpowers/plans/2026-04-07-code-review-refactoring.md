# Code Review Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 12 issues found during code review: resource leak, unsafe dict access, missing dependency, unbounded recursion, missing server tests, CI gaps, input validation, and tooling improvements.

**Architecture:** Three independent PR groups. PR 1 (Safety & Correctness) and PR 3 (CI & DX) can execute in parallel. PR 2 (Server Tests & Validation) depends on PR 1. Each PR is independently mergeable.

**Tech Stack:** Python 3.12+, fastmcp 2.x (`@lifespan`, `Context`), httpx, pytest, pytest-asyncio, pytest-httpx, ruff, mypy

**Spec:** `docs/superpowers/specs/2026-04-07-code-review-refactoring-design.md`

---

## PR 1: Safety & Correctness

### Task 1: Add beautifulsoup4 to dependencies

**Files:**
- Modify: `pyproject.toml:20-25`

- [ ] **Step 1: Add beautifulsoup4 to dependencies**

In `pyproject.toml`, add `beautifulsoup4` to the `dependencies` list:

```toml
dependencies = [
    "fastmcp>=2.0.0",
    "httpx>=0.28.0",
    "pydantic-settings>=2.0.0",
    "markdownify>=0.14.1",
    "beautifulsoup4>=4.9",
]
```

- [ ] **Step 2: Sync dependencies**

Run: `uv sync --dev`
Expected: resolves without errors (beautifulsoup4 already installed transitively)

- [ ] **Step 3: Verify import works**

Run: `uv run python -c "from bs4 import BeautifulSoup; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "fix: add beautifulsoup4 as explicit dependency

It was imported directly in formatters.py but only available
transitively through markdownify."
```

---

### Task 2: Safe dict access in formatters.py

**Files:**
- Modify: `src/gramax_docportal_mcp/formatters.py:24,37-38,93`
- Test: `tests/test_formatters.py`

- [ ] **Step 1: Write failing test for malformed catalog data**

Add to `tests/test_formatters.py` at the end of `TestFormatCatalogsList`:

```python
    def test_missing_keys_in_catalog(self):
        from gramax_docportal_mcp.formatters import format_catalogs_list

        data = {"data": [
            {"id": "docs"},  # no title
            {"title": "API Reference"},  # no id
            {},  # no keys at all
        ]}
        result = format_catalogs_list(data)
        assert "# Каталоги документации" in result
        assert "Всего: 3" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_formatters.py::TestFormatCatalogsList::test_missing_keys_in_catalog -v`
Expected: FAIL with `KeyError: 'title'`

- [ ] **Step 3: Fix format_catalogs_list**

In `src/gramax_docportal_mcp/formatters.py`, change line 24:

```python
# Before:
        lines.append(f"| {cat['title']} | {cat['id']} |")
# After:
        lines.append(f"| {cat.get('title', '—')} | {cat.get('id', '—')} |")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_formatters.py::TestFormatCatalogsList -v`
Expected: all PASS

- [ ] **Step 5: Write failing test for malformed navigation data**

Add to `tests/test_formatters.py` at the end of `TestFormatNavigation`:

```python
    def test_missing_keys_in_nav_items(self):
        from gramax_docportal_mcp.formatters import format_navigation

        data = {"data": [
            {"title": "No ID Item"},  # no id
            {"id": "no-title"},  # no title
        ]}
        result = format_navigation("docs", data, "https://docs.example.com")
        assert "# Навигация: docs" in result
        assert "No ID Item" in result
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_formatters.py::TestFormatNavigation::test_missing_keys_in_nav_items -v`
Expected: FAIL with `KeyError: 'id'`

- [ ] **Step 7: Fix _render_tree**

In `src/gramax_docportal_mcp/formatters.py`, change lines 37-38:

```python
# Before:
        url = f"{base_url}/{catalog_id}/{item['id']}"
        lines.append(f"{indent}- [{item['title']}]({url})")
# After:
        url = f"{base_url}/{catalog_id}/{item.get('id', '')}"
        lines.append(f"{indent}- [{item.get('title', '—')}]({url})")
```

- [ ] **Step 8: Run test to verify it passes**

Run: `uv run pytest tests/test_formatters.py::TestFormatNavigation -v`
Expected: all PASS

- [ ] **Step 9: Fix unsafe breadcrumb access in format_search_results**

In `src/gramax_docportal_mcp/formatters.py`, change line 93:

```python
# Before:
        path_parts = [catalog.get("title", "")] + [b["title"] for b in breadcrumbs]
# After:
        path_parts = [catalog.get("title", "")] + [b.get("title", "") for b in breadcrumbs]
```

- [ ] **Step 10: Run all formatter tests**

Run: `uv run pytest tests/test_formatters.py -v`
Expected: all PASS

- [ ] **Step 11: Commit**

```bash
git add src/gramax_docportal_mcp/formatters.py tests/test_formatters.py
git commit -m "fix: use safe dict access in formatters

Replace dict['key'] with dict.get('key', default) to prevent
KeyError on malformed API responses."
```

---

### Task 3: Add recursion depth limit to _render_tree

**Files:**
- Modify: `src/gramax_docportal_mcp/formatters.py:32-42`
- Test: `tests/test_formatters.py`

- [ ] **Step 1: Write failing test for deep tree truncation**

Add to `tests/test_formatters.py` at the end of `TestFormatNavigation`:

```python
    def test_deep_tree_truncated(self):
        from gramax_docportal_mcp.formatters import format_navigation, MAX_NAV_DEPTH

        # Build a tree deeper than MAX_NAV_DEPTH
        node = {"id": f"level-{MAX_NAV_DEPTH + 1}", "title": f"Level {MAX_NAV_DEPTH + 1}"}
        for i in range(MAX_NAV_DEPTH, 0, -1):
            node = {"id": f"level-{i}", "title": f"Level {i}", "children": [node]}
        data = {"data": [node]}

        result = format_navigation("docs", data, "https://docs.example.com")
        assert "Level 1" in result
        assert f"Level {MAX_NAV_DEPTH}" in result
        assert f"Level {MAX_NAV_DEPTH + 1}" not in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_formatters.py::TestFormatNavigation::test_deep_tree_truncated -v`
Expected: FAIL with `ImportError: cannot import name 'MAX_NAV_DEPTH'`

- [ ] **Step 3: Add MAX_NAV_DEPTH constant and depth check**

In `src/gramax_docportal_mcp/formatters.py`, add the constant after the imports (after line 6) and modify the function:

```python
MAX_NAV_DEPTH = 20
```

Then modify `_render_tree` (lines 32-42):

```python
def _render_tree(items: list[dict], base_url: str, catalog_id: str, depth: int = 0) -> list[str]:
    """Recursively render navigation tree to markdown lines."""
    lines: list[str] = []
    if depth >= MAX_NAV_DEPTH:
        return lines
    indent = "  " * depth
    for item in items:
        url = f"{base_url}/{catalog_id}/{item.get('id', '')}"
        lines.append(f"{indent}- [{item.get('title', '—')}]({url})")
        children = item.get("children", [])
        if children:
            lines.extend(_render_tree(children, base_url, catalog_id, depth + 1))
    return lines
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_formatters.py::TestFormatNavigation -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/gramax_docportal_mcp/formatters.py tests/test_formatters.py
git commit -m "fix: add recursion depth limit to navigation tree rendering

Prevents RecursionError on deeply nested or malformed API responses.
Default limit: 20 levels."
```

---

### Task 4: Replace while loop with regex for blank line cleanup

**Files:**
- Modify: `src/gramax_docportal_mcp/formatters.py:1-6,136-137`
- Test: `tests/test_formatters.py`

- [ ] **Step 1: Write test for excessive blank lines**

Add to `tests/test_formatters.py` at the end of `TestHtmlToMarkdown`:

```python
    def test_collapses_multiple_blank_lines(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        html = "<p>A</p><br><br><br><br><br><p>B</p>"
        result = html_to_markdown(html)
        assert "\n\n\n" not in result
        assert "A" in result
        assert "B" in result
```

- [ ] **Step 2: Run test to verify it passes (current behavior already handles this)**

Run: `uv run pytest tests/test_formatters.py::TestHtmlToMarkdown::test_collapses_multiple_blank_lines -v`
Expected: PASS (the while loop already works, we're just optimizing it)

- [ ] **Step 3: Replace while loop with regex**

In `src/gramax_docportal_mcp/formatters.py`:

Add `import re` after line 3 (after `from __future__ import annotations`):

```python
from __future__ import annotations

import re

from bs4 import BeautifulSoup
```

Replace lines 136-137:

```python
# Before:
    while "\n\n\n" in md:
        md = md.replace("\n\n\n", "\n\n")
# After:
    md = re.sub(r"\n{3,}", "\n\n", md)
```

- [ ] **Step 4: Run all tests to verify no regression**

Run: `uv run pytest tests/test_formatters.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/gramax_docportal_mcp/formatters.py tests/test_formatters.py
git commit -m "refactor: use regex for blank line normalization

Single-pass re.sub replaces multi-pass while loop."
```

---

### Task 5: Replace global client with fastmcp lifespan

**Files:**
- Modify: `src/gramax_docportal_mcp/server.py`

- [ ] **Step 1: Run existing tests to confirm green baseline**

Run: `uv run pytest -v`
Expected: all PASS

- [ ] **Step 2: Rewrite server.py with lifespan pattern**

Replace the entire content of `src/gramax_docportal_mcp/server.py`:

```python
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
```

- [ ] **Step 3: Run existing tests**

Run: `uv run pytest -v`
Expected: all PASS (existing tests don't test server.py directly)

- [ ] **Step 4: Run lint**

Run: `uv run ruff check .`
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add src/gramax_docportal_mcp/server.py
git commit -m "fix: replace global client with fastmcp lifespan

Use @lifespan decorator to properly manage GramaxClient lifecycle.
Client is created on server startup and closed on shutdown via
async context manager. Tool functions receive client through
ctx.lifespan_context instead of global state."
```

---

## PR 2: Server Tests & Input Validation

### Task 6: Move shared fixtures to conftest.py

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/test_client.py:1-12`

- [ ] **Step 1: Add shared fixtures to conftest.py**

Replace content of `tests/conftest.py`:

```python
"""Shared test fixtures for gramax-docportal-mcp."""

import pytest


@pytest.fixture
def base_url():
    return "https://docs.example.com"


@pytest.fixture
def api_token():
    return "test-api-token-123"
```

- [ ] **Step 2: Remove duplicate fixtures from test_client.py**

Remove lines 5-12 from `tests/test_client.py` (the `base_url` and `api_token` fixtures):

```python
# Remove these lines:
@pytest.fixture
def base_url():
    return "https://docs.example.com"


@pytest.fixture
def api_token():
    return "test-api-token-123"
```

The file should start with:

```python
import pytest
from pytest_httpx import HTTPXMock


async def test_list_catalogs(httpx_mock: HTTPXMock, base_url, api_token):
```

- [ ] **Step 3: Run tests to verify fixtures work**

Run: `uv run pytest tests/test_client.py -v`
Expected: all 11 tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_client.py
git commit -m "refactor: move shared fixtures to conftest.py

Eliminates duplication of base_url and api_token fixtures."
```

---

### Task 7: Add input validation to server tools

**Files:**
- Modify: `src/gramax_docportal_mcp/server.py`

- [ ] **Step 1: Add validation guard clauses**

In `src/gramax_docportal_mcp/server.py`, add validation at the beginning of three tool functions.

For `gramax_get_navigation`, add after the docstring:

```python
@mcp.tool()
async def gramax_get_navigation(ctx: Context, catalog_id: str) -> str:
    """..."""
    if not catalog_id or not catalog_id.strip():
        return "Ошибка: catalog_id не может быть пустым."
    try:
        ...
```

For `gramax_search`, add after the docstring:

```python
@mcp.tool()
async def gramax_search(ctx: Context, query: str, ...) -> str:
    """..."""
    if not query or not query.strip():
        return "Ошибка: поисковый запрос не может быть пустым."
    try:
        ...
```

For `gramax_get_article`, add after the docstring:

```python
@mcp.tool()
async def gramax_get_article(ctx: Context, catalog_id: str, article_id: str) -> str:
    """..."""
    if not catalog_id or not catalog_id.strip():
        return "Ошибка: catalog_id не может быть пустым."
    if not article_id or not article_id.strip():
        return "Ошибка: article_id не может быть пустым."
    try:
        ...
```

- [ ] **Step 2: Run lint**

Run: `uv run ruff check .`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add src/gramax_docportal_mcp/server.py
git commit -m "feat: add input validation to MCP tools

Return clear Russian error messages for empty required parameters
instead of sending meaningless HTTP requests."
```

---

### Task 8: Write server tool tests

**Files:**
- Create: `tests/test_server.py`

- [ ] **Step 1: Create test_server.py with test fixtures and list_catalogs tests**

Create `tests/test_server.py`:

```python
"""Tests for MCP server tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastmcp import Context

from gramax_docportal_mcp.client import GramaxClient, GramaxError, GramaxAuthError
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
```

- [ ] **Step 2: Run server tests**

Run: `uv run pytest tests/test_server.py -v`
Expected: all PASS (14 tests)

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS (existing + new)

- [ ] **Step 4: Commit**

```bash
git add tests/test_server.py
git commit -m "test: add comprehensive tests for MCP server tools

14 tests covering all 4 tools: happy paths, error handling,
input validation, and filter passthrough."
```

---

## PR 3: CI & DX Improvements

### Task 9: Add CI workflow for push/PR

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test-and-lint:
    name: Test & Lint (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --dev

      - name: Lint
        run: uv run ruff check .

      - name: Test
        run: uv run pytest -v
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add test and lint workflow on push/PR

Runs tests on Python 3.12 and 3.13 matrix.
Complements the release-only publish workflow."
```

---

### Task 10: Add .env.example

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create .env.example**

Create `.env.example`:

```
# Gramax Doc Portal MCP Server configuration
# Copy this file to .env and fill in the values

# URL портала документации Gramax
GRAMAX_BASE_URL=https://your-portal.example.com

# API-токен (получить: GET /api/user/token)
GRAMAX_API_TOKEN=your-api-token-here
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: add .env.example template

Documents required environment variables for new developers."
```

---

### Task 11: Expand ruff rules

**Files:**
- Modify: `pyproject.toml:52-53`

- [ ] **Step 1: Update ruff configuration**

In `pyproject.toml`, replace the `[tool.ruff.lint]` section:

```toml
[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "S", "C901", "ASYNC"]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101"]
```

Rules added:
- `UP` — pyupgrade (modern Python patterns)
- `S` — flake8-bandit (security checks)
- `C901` — McCabe complexity
- `ASYNC` — async best practices

- [ ] **Step 2: Run ruff to check for violations**

Run: `uv run ruff check .`
Expected: Check output — may have new violations from `UP` or `S` rules.

- [ ] **Step 3: Fix or suppress any violations**

If violations appear, fix them. Common ones:
- `UP035`: deprecated imports — use modern equivalents
- `S105/S106`: hardcoded password — add `# noqa: S105` to test fixtures if needed

Run: `uv run ruff check . --fix` for auto-fixable issues, then review manually.

- [ ] **Step 4: Run tests to ensure no regression**

Run: `uv run pytest -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml
# Also add any source files that were modified by ruff --fix
git commit -m "chore: expand ruff rules with UP, S, C901, ASYNC

Adds pyupgrade, security, complexity, and async linting.
Tests are excluded from S101 (assert) checks."
```

---

### Task 12: Add mypy type checking

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add mypy to dev dependencies**

In `pyproject.toml`, add mypy to the dev dependency group:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25.0",
    "pytest-httpx>=0.35.0",
    "ruff>=0.11.0",
    "mypy>=1.10",
]
```

- [ ] **Step 2: Add mypy configuration**

Add to `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

- [ ] **Step 3: Install mypy**

Run: `uv sync --dev`
Expected: mypy installed successfully

- [ ] **Step 4: Run mypy and fix issues**

Run: `uv run mypy src/`

Fix any type errors. Common expected issues:
- `client.py`: Return types `dict` should be `dict[str, Any]` — add `from typing import Any`
- `formatters.py`: Same for `list[dict]` → `list[dict[str, Any]]`
- `server.py`: The `app_lifespan` generator type may need annotation

Fix each issue. For example, in `client.py`:
```python
from typing import Any

async def list_catalogs(self) -> dict[str, Any]:
    ...
```

- [ ] **Step 5: Add mypy step to CI workflow**

In `.github/workflows/ci.yml`, add after the Test step:

```yaml
      - name: Type check
        run: uv run mypy src/
```

- [ ] **Step 6: Run full suite**

Run: `uv run pytest -v && uv run ruff check . && uv run mypy src/`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .github/workflows/ci.yml
# Also add any source files modified for type fixes
git commit -m "chore: add mypy type checking to CI

Configured with disallow_untyped_defs. Fixed type annotations
to pass mypy checks."
```

---

## Final Verification

### Task 13: Full suite verification and cleanup

- [ ] **Step 1: Run all checks**

```bash
uv run ruff check .
uv run pytest -v
uv run mypy src/
```

Expected: all green

- [ ] **Step 2: Verify server starts**

```bash
# Set test env vars
export GRAMAX_BASE_URL=https://example.com
export GRAMAX_API_TOKEN=test-token
uv run gramax-docportal-mcp &
# Should start without errors. Kill with Ctrl+C or kill %1
```

- [ ] **Step 3: Review all changes**

Run: `git diff main --stat`

Verify no unintended file changes.
