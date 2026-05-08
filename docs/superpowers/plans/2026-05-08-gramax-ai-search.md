# Gramax AI Search — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить MCP-инструмент `gramax_ai_search`, который вызывает Gramax `/api/search/chat` (NDJSON streaming), парсит CIT-цитаты и возвращает Markdown-ответ с inline-ссылками `[N](full_id)` и блоком «Источники».

**Architecture:** Расширяем 4 существующих модуля без новых файлов: `config.py` получает три новых поля Settings, `client.py` — async-generator `ai_search()` поверх `httpx.stream()`, `formatters.py` — `parse_chat_stream()` + `format_ai_answer()`, `server.py` — новый `@mcp.tool` + расширение lifespan-контракта (добавляется `settings` в `lifespan_context`). Парсер CIT-маркеров — пост-обработка склеенного текста по реальной фикстуре `tests/fixtures/ai_search_response.ndjson`.

**Tech Stack:** Python 3.12, fastmcp ≥2.0, httpx ≥0.28 (streaming), pydantic-settings, pytest, pytest-asyncio, pytest-httpx, ruff, mypy.

**Reference docs:**
- Spec: [`docs/superpowers/specs/2026-05-08-gramax-ai-search-design.md`](../specs/2026-05-08-gramax-ai-search-design.md)
- ADR: [`docs/architecture/adr/0001-streaming-ai-tool.md`](../../architecture/adr/0001-streaming-ai-tool.md)
- Fixture: `tests/fixtures/ai_search_response.ndjson` (338 строк, 10 CIT-маркеров, 6 уникальных `(N, full_id)`)

**Unicode-константы CIT-маркера** (извлечены из реальной фикстуры — НЕ менять без перепроверки):
- `ZWSP = "​"` (Zero-Width Space) — внешняя граница маркера
- `WJ = "⁠"` (Word Joiner) — разделитель полей и закрывающая последовательность

Полная форма маркера в стриме: `<ZWSP><WJ>CIT<WJ><N><WJ><full_id><WJ><rel_path><WJ><WJ><ZWSP>`
- `N` — номер цитаты (1, 2, 3, ...)
- `full_id` — `catalog_id/article_path` без `.md`
- `rel_path` — относительный путь с `.md` (используем для отладки, в выходе не нужен)

---

## File Structure

| Файл                                             | Действие  | Ответственность                              |
|--------------------------------------------------|-----------|----------------------------------------------|
| `src/gramax_docportal_mcp/config.py`             | Изменить  | + 3 поля Settings (timeout, langs)           |
| `src/gramax_docportal_mcp/client.py`             | Изменить  | + `GramaxClient.ai_search()` async generator |
| `src/gramax_docportal_mcp/formatters.py`         | Изменить  | + `parse_chat_stream()` + `format_ai_answer()` |
| `src/gramax_docportal_mcp/server.py`             | Изменить  | + `gramax_ai_search` tool, settings в lifespan |
| `tests/fixtures/ai_search_response.ndjson`       | Создан    | Эталонная фикстура (готова в репо)           |
| `tests/test_config.py`                           | Изменить  | + 4 теста на новые поля                       |
| `tests/test_client.py`                           | Изменить  | + 6 тестов на ai_search                       |
| `tests/test_formatters.py`                       | Изменить  | + 7 тестов на парсер и форматтер             |
| `tests/test_server.py`                           | Изменить  | + 5 тестов на gramax_ai_search                |
| `pyproject.toml`                                 | Изменить  | version bump 0.2.0 → 0.3.0                    |
| `docs/architecture/adr/0001-streaming-ai-tool.md`| Изменить  | Status: Proposed → Accepted (после смока)    |

---

## Pre-flight (нулевая задача — выполняется один раз перед Task 1)

- [ ] **Pre-1: Verify fixture exists**

```bash
test -f tests/fixtures/ai_search_response.ndjson \
  && wc -l tests/fixtures/ai_search_response.ndjson
```

Expected: `338 tests/fixtures/ai_search_response.ndjson`. Если файла нет — он должен быть создан коммитом до начала плана. Не продолжай.

- [ ] **Pre-2: Verify clean baseline**

```bash
uv run pytest -q
uv run ruff check .
```

Expected: все тесты зелёные, ruff без ошибок. Если что-то падает — это не относится к этому плану, сначала почини baseline.

---

## Task 1: Settings — добавить три новых поля

**Files:**
- Modify: `src/gramax_docportal_mcp/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1.1: Write failing tests**

Append to `tests/test_config.py`:

```python
def test_settings_ai_defaults(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token")
    monkeypatch.delenv("GRAMAX_AI_TIMEOUT", raising=False)
    monkeypatch.delenv("GRAMAX_AI_ARTICLES_LANGUAGE", raising=False)
    monkeypatch.delenv("GRAMAX_AI_RESPONSE_LANGUAGE", raising=False)

    from gramax_docportal_mcp.config import Settings

    s = Settings(_env_file=None)
    assert s.gramax_ai_timeout == 120.0
    assert s.gramax_ai_articles_language == "ru"
    assert s.gramax_ai_response_language == "ru"


def test_settings_ai_timeout_from_env(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token")
    monkeypatch.setenv("GRAMAX_AI_TIMEOUT", "60")

    from gramax_docportal_mcp.config import Settings

    s = Settings(_env_file=None)
    assert s.gramax_ai_timeout == 60.0


def test_settings_ai_languages_from_env(monkeypatch):
    monkeypatch.setenv("GRAMAX_BASE_URL", "https://docs.example.com")
    monkeypatch.setenv("GRAMAX_API_TOKEN", "test-token")
    monkeypatch.setenv("GRAMAX_AI_ARTICLES_LANGUAGE", "en")
    monkeypatch.setenv("GRAMAX_AI_RESPONSE_LANGUAGE", "fr")

    from gramax_docportal_mcp.config import Settings

    s = Settings(_env_file=None)
    assert s.gramax_ai_articles_language == "en"
    assert s.gramax_ai_response_language == "fr"
```

- [ ] **Step 1.2: Run tests — verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 3 новых теста FAIL с `AttributeError` (полей ещё нет).

- [ ] **Step 1.3: Add fields to Settings**

Replace contents of `src/gramax_docportal_mcp/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Gramax Doc Portal MCP server configuration.

    Environment variables:
        GRAMAX_BASE_URL: Portal URL (required, e.g. https://docs.example.com)
        GRAMAX_API_TOKEN: Bearer API token (required, obtained via /api/user/token)
        GRAMAX_AI_TIMEOUT: Timeout in seconds for /api/search/chat (default 120)
        GRAMAX_AI_ARTICLES_LANGUAGE: Default articles language for AI search (default "ru")
        GRAMAX_AI_RESPONSE_LANGUAGE: Default response language for AI search (default "ru")
    """

    gramax_base_url: str
    gramax_api_token: str
    gramax_ai_timeout: float = 120.0
    gramax_ai_articles_language: str = "ru"
    gramax_ai_response_language: str = "ru"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

- [ ] **Step 1.4: Run tests — verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: все тесты `test_config.py` PASS (включая старые).

- [ ] **Step 1.5: Commit**

```bash
git add src/gramax_docportal_mcp/config.py tests/test_config.py
git commit -m "feat(config): add ai_timeout, ai_articles_language, ai_response_language settings"
```

---

## Task 2: GramaxClient.ai_search — скелет async generator

Минимальный happy path: метод существует, делает GET с `query` query-param, парсит NDJSON, yield-ит text-чанки.

**Files:**
- Modify: `src/gramax_docportal_mcp/client.py`
- Test: `tests/test_client.py`

- [ ] **Step 2.1: Write failing test**

Append to `tests/test_client.py`:

```python
async def test_ai_search_yields_text_chunks(httpx_mock: HTTPXMock, base_url, api_token):
    ndjson = (
        '{"type":"text","text":"hello"}\n'
        '{"type":"text","text":" world"}\n'
    )
    httpx_mock.add_response(text=ndjson)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        chunks = [c async for c in client.ai_search("test")]

    assert chunks == ["hello", " world"]
    request = httpx_mock.get_request()
    url_str = str(request.url)
    assert "/api/search/chat" in url_str
    assert "query=test" in url_str
    assert request.headers["authorization"] == "Bearer test-api-token-123"
```

- [ ] **Step 2.2: Run test — verify it fails**

```bash
uv run pytest tests/test_client.py::test_ai_search_yields_text_chunks -v
```

Expected: FAIL — `AttributeError: 'GramaxClient' object has no attribute 'ai_search'`.

- [ ] **Step 2.3: Add `ai_search` method to client**

In `src/gramax_docportal_mcp/client.py`, add `import json` at top (if not already), add `from collections.abc import AsyncIterator` after `from __future__ import annotations`. Then add this method to `GramaxClient` class (place after the existing `search` method):

```python
    async def ai_search(
        self,
        query: str,
        *,
        catalog_name: str | None = None,
        articles_language: str | None = None,
        response_language: str | None = None,
        current_article: str | None = None,
        timeout: float = 120.0,
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

        async with self._client.stream(
            "GET",
            "/api/search/chat",
            params=params,
            timeout=timeout,
        ) as response:
            self._check_response(response, f"AI-поиск '{query}'")
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "text":
                    text = obj.get("text", "")
                    if text:
                        yield text
```

- [ ] **Step 2.4: Run test — verify it passes**

```bash
uv run pytest tests/test_client.py::test_ai_search_yields_text_chunks -v
```

Expected: PASS.

- [ ] **Step 2.5: Commit**

```bash
git add src/gramax_docportal_mcp/client.py tests/test_client.py
git commit -m "feat(client): add GramaxClient.ai_search async generator (happy path)"
```

---

## Task 3: GramaxClient.ai_search — все query-params + edge cases

Расширяем покрытие: все опциональные параметры, ошибки 401/404, невалидный JSON, пустой стрим.

**Files:**
- Test: `tests/test_client.py` (add tests; импл уже умеет, тесты только подтверждают)

- [ ] **Step 3.1: Write failing tests**

Append to `tests/test_client.py`:

```python
async def test_ai_search_passes_all_params(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(text="")

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        async for _ in client.ai_search(
            "Что такое ITSM",
            catalog_name="commercial-knowlage",
            articles_language="ru",
            response_language="en",
            current_article="commercial-knowlage/intro",
        ):
            pass

    url_str = str(httpx_mock.get_request().url)
    assert "catalogName=commercial-knowlage" in url_str
    assert "articlesLanguage=ru" in url_str
    assert "responseLanguage=en" in url_str
    # currentArticle URL-encoded
    assert "currentArticle=commercial-knowlage" in url_str


async def test_ai_search_skips_invalid_json_lines(httpx_mock: HTTPXMock, base_url, api_token):
    ndjson = (
        '{"type":"text","text":"a"}\n'
        'this is not json\n'
        '\n'
        '{"type":"text","text":"b"}\n'
    )
    httpx_mock.add_response(text=ndjson)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        chunks = [c async for c in client.ai_search("q")]

    assert chunks == ["a", "b"]


async def test_ai_search_skips_non_text_chunks(httpx_mock: HTTPXMock, base_url, api_token):
    ndjson = (
        '{"type":"text","text":"a"}\n'
        '{"type":"meta","data":{}}\n'
        '{"type":"text","text":"b"}\n'
    )
    httpx_mock.add_response(text=ndjson)

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        chunks = [c async for c in client.ai_search("q")]

    assert chunks == ["a", "b"]


async def test_ai_search_empty_stream(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(text="")

    from gramax_docportal_mcp.client import GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        chunks = [c async for c in client.ai_search("q")]

    assert chunks == []


async def test_ai_search_401_raises_auth_error(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=401, text="Unauthorized")

    from gramax_docportal_mcp.client import GramaxAuthError, GramaxClient

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxAuthError, match="Токен невалиден"):
            async for _ in client.ai_search("q"):
                pass


async def test_ai_search_404_raises_not_found(httpx_mock: HTTPXMock, base_url, api_token):
    httpx_mock.add_response(status_code=404, text="Not Found")

    from gramax_docportal_mcp.client import GramaxClient, GramaxNotFoundError

    async with GramaxClient(base_url=base_url, api_token=api_token) as client:
        with pytest.raises(GramaxNotFoundError, match="не найден"):
            async for _ in client.ai_search("q", catalog_name="missing"):
                pass
```

- [ ] **Step 3.2: Run tests — verify they pass (or identify gaps)**

```bash
uv run pytest tests/test_client.py -v
```

Expected: все 6 новых тестов PASS (имплементация Task 2 уже их покрывает).

Если какой-то FAIL: посмотри сообщение об ошибке и доработай метод `ai_search`. Самое вероятное место — `_check_response` для streaming-ответа: если httpx не дал status_code до итерации, см. ниже.

> **Note:** httpx предоставляет `response.status_code`/`response.headers` сразу после открытия `client.stream()` (до чтения тела). `_check_response` уже умеет на основе status_code. Если будут проблемы — добавь явный `await response.aread()` перед `_check_response` ТОЛЬКО для error-status (`if response.status_code >= 400: await response.aread()`). Не делай этого для 200 — иначе сломаешь streaming.

- [ ] **Step 3.3: Commit**

```bash
git add tests/test_client.py src/gramax_docportal_mcp/client.py
git commit -m "test(client): cover ai_search params, malformed json, errors, empty stream"
```

---

## Task 4: parse_chat_stream — concat + extract CIT markers

Парсер пост-обрабатывает склеенные чанки: вырезает CIT-маркеры, заменяет на `[N](full_id)`, возвращает `{"text": str, "citations": list[Citation]}`.

**Files:**
- Modify: `src/gramax_docportal_mcp/formatters.py`
- Test: `tests/test_formatters.py`

- [ ] **Step 4.1: Write failing tests (concat + no markers + with markers + edge cases)**

Append to `tests/test_formatters.py`:

```python
import json as _json
from pathlib import Path

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ai_search_response.ndjson"


def _load_fixture_chunks() -> list[str]:
    chunks: list[str] = []
    for raw_line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        obj = _json.loads(line)
        if obj.get("type") == "text":
            text = obj.get("text", "")
            if text:
                chunks.append(text)
    return chunks


def test_parse_chat_stream_concatenates_no_markers():
    from gramax_docportal_mcp.formatters import parse_chat_stream

    result = parse_chat_stream(["Hello", " ", "world", "!"])

    assert result == {"text": "Hello world!", "citations": []}


def test_parse_chat_stream_empty_input():
    from gramax_docportal_mcp.formatters import parse_chat_stream

    assert parse_chat_stream([]) == {"text": "", "citations": []}


def test_parse_chat_stream_synthetic_marker():
    """Test marker built by hand from known codepoints."""
    from gramax_docportal_mcp.formatters import parse_chat_stream

    zwsp = "​"
    wj = "⁠"
    marker = f"{zwsp}{wj}CIT{wj}1{wj}cat/article{wj}./article.md{wj}{wj}{zwsp}"
    chunks = ["Some text ", marker, " more text"]

    result = parse_chat_stream(chunks)

    assert result["text"] == "Some text [1](cat/article) more text"
    assert result["citations"] == [{"n": 1, "full_id": "cat/article"}]


def test_parse_chat_stream_marker_split_across_chunks():
    """Marker may be split between NDJSON lines; concat-then-parse handles it."""
    from gramax_docportal_mcp.formatters import parse_chat_stream

    zwsp = "​"
    wj = "⁠"
    full_marker = f"{zwsp}{wj}CIT{wj}5{wj}foo/bar{wj}./bar.md{wj}{wj}{zwsp}"
    half = len(full_marker) // 2
    chunks = ["pre ", full_marker[:half], full_marker[half:], " post"]

    result = parse_chat_stream(chunks)

    assert result["text"] == "pre [5](foo/bar) post"
    assert result["citations"] == [{"n": 5, "full_id": "foo/bar"}]


def test_parse_chat_stream_real_fixture():
    """Real Gramax NDJSON: 10 markers total, 6 unique full_ids."""
    from gramax_docportal_mcp.formatters import parse_chat_stream

    chunks = _load_fixture_chunks()
    result = parse_chat_stream(chunks)

    # Citations: 10 occurrences, with N=2..5 appearing twice
    ns = [c["n"] for c in result["citations"]]
    assert sorted(ns) == [1, 2, 2, 3, 3, 4, 4, 5, 5, 6]
    full_ids = {c["full_id"] for c in result["citations"]}
    assert full_ids == {
        "commercial-knowlage/90-knowledge-base/glossary",
        "commercial-knowlage/10-products/itsm-365/support",
        "commercial-knowlage/10-products/itsm-365/outsource",
        "commercial-knowlage/10-products/itsm-365/hr",
        "commercial-knowlage/10-products/itsm-365/projects",
        "commercial-knowlage/90-knowledge-base/certifications",
    }
    # No leftover invisible chars after replacement
    assert "​" not in result["text"]
    assert "⁠" not in result["text"]
    # Inline citation present in expected place
    assert "[1](commercial-knowlage/90-knowledge-base/glossary)" in result["text"]
```

- [ ] **Step 4.2: Run tests — verify they fail**

```bash
uv run pytest tests/test_formatters.py -k parse_chat_stream -v
```

Expected: 5 тестов FAIL с `ImportError: cannot import name 'parse_chat_stream'`.

- [ ] **Step 4.3: Implement `parse_chat_stream`**

In `src/gramax_docportal_mcp/formatters.py`:

1) After existing `import re` at top, add:

```python
from typing import TypedDict


class Citation(TypedDict):
    n: int
    full_id: str


_ZWSP = "​"
_WJ = "⁠"
_CIT_PATTERN = re.compile(
    rf"{_ZWSP}{_WJ}CIT{_WJ}(\d+){_WJ}([^{_WJ}]+){_WJ}([^{_WJ}]+){_WJ}{_WJ}{_ZWSP}"
)
```

2) Append a new function (place after `html_to_markdown`):

```python
def parse_chat_stream(chunks: list[str]) -> dict:
    """Concatenate NDJSON text chunks and extract Gramax CIT citation markers.

    Returns:
        {"text": str, "citations": list[Citation]}
        - text: chunks joined with all CIT markers replaced by `[N](full_id)`.
        - citations: list of {"n": int, "full_id": str} in order of first
          appearance; duplicates kept (caller decides how to render).
    """
    raw = "".join(chunks)
    citations: list[Citation] = []

    def _replace(match: re.Match[str]) -> str:
        n = int(match.group(1))
        full_id = match.group(2)
        citations.append({"n": n, "full_id": full_id})
        return f"[{n}]({full_id})"

    text = _CIT_PATTERN.sub(_replace, raw)
    return {"text": text, "citations": citations}
```

- [ ] **Step 4.4: Run tests — verify they pass**

```bash
uv run pytest tests/test_formatters.py -k parse_chat_stream -v
```

Expected: 5 тестов PASS.

- [ ] **Step 4.5: Commit**

```bash
git add src/gramax_docportal_mcp/formatters.py tests/test_formatters.py
git commit -m "feat(formatters): add parse_chat_stream — concat + CIT marker extraction"
```

---

## Task 5: format_ai_answer — финальный markdown с блоком «Источники»

Формирует выходной markdown: основной текст + блок `## Источники` (если цитаты есть). Дедупликация по `(N, full_id)`.

**Files:**
- Modify: `src/gramax_docportal_mcp/formatters.py`
- Test: `tests/test_formatters.py`

- [ ] **Step 5.1: Write failing tests**

Append to `tests/test_formatters.py`:

```python
def test_format_ai_answer_empty_text():
    from gramax_docportal_mcp.formatters import format_ai_answer

    result = format_ai_answer({"text": "", "citations": []}, "https://docs.example.com")

    assert result == "AI не сгенерировал ответ."


def test_format_ai_answer_whitespace_only_text():
    from gramax_docportal_mcp.formatters import format_ai_answer

    result = format_ai_answer({"text": "   \n\n  ", "citations": []}, "https://docs.example.com")

    assert result == "AI не сгенерировал ответ."


def test_format_ai_answer_no_citations():
    from gramax_docportal_mcp.formatters import format_ai_answer

    result = format_ai_answer(
        {"text": "Just a plain answer.", "citations": []},
        "https://docs.example.com",
    )

    assert result == "Just a plain answer."
    assert "Источники" not in result


def test_format_ai_answer_with_citations_dedups_same_pair():
    from gramax_docportal_mcp.formatters import format_ai_answer

    parsed = {
        "text": "Foo [1](a/b) and again [1](a/b).",
        "citations": [
            {"n": 1, "full_id": "a/b"},
            {"n": 1, "full_id": "a/b"},  # exact duplicate
        ],
    }

    result = format_ai_answer(parsed, "https://docs.example.com")

    assert "## Источники" in result
    # exactly one entry for (1, a/b)
    assert result.count("`a/b`") == 1
    assert "1. `a/b`" in result
    assert "https://docs.example.com/a/b" in result


def test_format_ai_answer_keeps_distinct_n_for_same_full_id():
    """Different N to same full_id → two source rows (preserve inline-row mapping)."""
    from gramax_docportal_mcp.formatters import format_ai_answer

    parsed = {
        "text": "First [1](a/b) and second [3](a/b).",
        "citations": [
            {"n": 1, "full_id": "a/b"},
            {"n": 3, "full_id": "a/b"},
        ],
    }

    result = format_ai_answer(parsed, "https://docs.example.com")

    assert "1. `a/b`" in result
    assert "3. `a/b`" in result


def test_format_ai_answer_sorts_by_n():
    from gramax_docportal_mcp.formatters import format_ai_answer

    parsed = {
        "text": "[3](c) [1](a) [2](b)",
        "citations": [
            {"n": 3, "full_id": "c"},
            {"n": 1, "full_id": "a"},
            {"n": 2, "full_id": "b"},
        ],
    }

    result = format_ai_answer(parsed, "https://docs.example.com")

    src_block = result.split("## Источники", 1)[1]
    pos_1 = src_block.find("1. `a`")
    pos_2 = src_block.find("2. `b`")
    pos_3 = src_block.find("3. `c`")
    assert 0 <= pos_1 < pos_2 < pos_3


def test_format_ai_answer_sources_url_format():
    from gramax_docportal_mcp.formatters import format_ai_answer

    parsed = {
        "text": "[1](cat/path/article)",
        "citations": [{"n": 1, "full_id": "cat/path/article"}],
    }

    result = format_ai_answer(parsed, "https://docs.example.com")

    assert "https://docs.example.com/cat/path/article" in result
```

- [ ] **Step 5.2: Run tests — verify they fail**

```bash
uv run pytest tests/test_formatters.py -k format_ai_answer -v
```

Expected: 7 тестов FAIL — `ImportError`.

- [ ] **Step 5.3: Implement `format_ai_answer`**

Append to `src/gramax_docportal_mcp/formatters.py`:

```python
def format_ai_answer(parsed: dict, base_url: str) -> str:
    """Render parsed AI answer with optional Sources block.

    parsed: {"text": str, "citations": list[Citation]} from parse_chat_stream.
    base_url: portal URL prefix for source links.
    """
    text = parsed.get("text", "")
    citations: list[Citation] = parsed.get("citations", [])

    if not text.strip():
        return "AI не сгенерировал ответ."

    if not citations:
        return text

    # Dedup by (n, full_id), preserve order of first appearance, then sort by n
    seen: set[tuple[int, str]] = set()
    unique: list[Citation] = []
    for c in citations:
        key = (c["n"], c["full_id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    unique.sort(key=lambda c: c["n"])

    base = base_url.rstrip("/")
    lines = [text.rstrip(), "", "## Источники", ""]
    for c in unique:
        lines.append(f"{c['n']}. `{c['full_id']}`")
        lines.append(f"   {base}/{c['full_id']}")
    return "\n".join(lines)
```

- [ ] **Step 5.4: Run tests — verify they pass**

```bash
uv run pytest tests/test_formatters.py -v
```

Expected: все тесты `test_formatters.py` PASS (старые + 7 новых).

- [ ] **Step 5.5: Commit**

```bash
git add src/gramax_docportal_mcp/formatters.py tests/test_formatters.py
git commit -m "feat(formatters): add format_ai_answer with Sources block + dedup"
```

---

## Task 6: server.py — расширить lifespan + новый MCP tool

**Files:**
- Modify: `src/gramax_docportal_mcp/server.py`
- Test: `tests/test_server.py`

### Step 6a — lifespan: положить `settings` в контекст

- [ ] **Step 6.1: Modify `app_lifespan`**

In `src/gramax_docportal_mcp/server.py`, replace lifespan body:

```python
@lifespan
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Create GramaxClient on startup, close on shutdown."""
    settings = Settings()
    base_url = settings.gramax_base_url.rstrip("/")
    async with GramaxClient(base_url=base_url, api_token=settings.gramax_api_token) as client:
        yield {"client": client, "base_url": base_url, "settings": settings}
```

(Только добавили `"settings": settings` в yield-словарь. Существующие tools его игнорируют — никакого breaking change.)

- [ ] **Step 6.2: Run existing tests — verify nothing broke**

```bash
uv run pytest tests/test_server.py -v
```

Expected: все старые тесты PASS. (Они работают через `mock_ctx` fixture, которая не использует `settings` — поэтому ничего не сломается.)

### Step 6b — добавить `gramax_ai_search` tool

- [ ] **Step 6.3: Write failing tests**

Append to `tests/test_server.py`:

```python
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
        gramax_api_token="t",
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
        from gramax_docportal_mcp.server import gramax_ai_search

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
        from gramax_docportal_mcp.server import gramax_ai_search

        ctx, _client, holder = mock_ctx_ai

        result = await gramax_ai_search(ctx, "   ")

        assert "Ошибка" in result
        assert "запрос" in result
        assert holder["called"] == 0  # ai_search must NOT have been invoked

    async def test_progress_called_per_chunk(self, mock_ctx_ai):
        from gramax_docportal_mcp.server import gramax_ai_search

        ctx, _client, holder = mock_ctx_ai
        holder["chunks"] = ["a", "b", "c", "d"]

        await gramax_ai_search(ctx, "q")

        assert ctx.report_progress.await_count == 4

    async def test_timeout_returns_russian_message(self, mock_ctx_ai):
        import httpx

        from gramax_docportal_mcp.server import gramax_ai_search

        ctx, mock_client, _ = mock_ctx_ai

        async def fake_timeout(*args, **kwargs):
            raise httpx.ReadTimeout("timed out")
            yield  # make it an async generator

        mock_client.ai_search = fake_timeout

        result = await gramax_ai_search(ctx, "q")

        assert "Превышено время ожидания" in result
        assert "GRAMAX_AI_TIMEOUT" in result

    async def test_auth_error_propagated_as_russian(self, mock_ctx_ai):
        from gramax_docportal_mcp.client import GramaxAuthError
        from gramax_docportal_mcp.server import gramax_ai_search

        ctx, mock_client, _ = mock_ctx_ai

        async def fake_auth(*args, **kwargs):
            raise GramaxAuthError("Токен невалиден или истёк.")
            yield  # generator marker

        mock_client.ai_search = fake_auth

        result = await gramax_ai_search(ctx, "q")

        assert "Токен невалиден" in result

    async def test_uses_default_languages_from_settings(self, mock_ctx_ai):
        """Settings defaults applied when MCP args are None."""
        from gramax_docportal_mcp.server import gramax_ai_search

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

        from gramax_docportal_mcp.server import gramax_ai_search

        ctx, mock_client, _ = mock_ctx_ai

        async def fake_disconnect(*args, **kwargs):
            yield "Часть ответа до разрыва."
            raise httpx.RemoteProtocolError("Server disconnected")

        mock_client.ai_search = fake_disconnect

        result = await gramax_ai_search(ctx, "q")

        assert "Часть ответа до разрыва." in result
        assert "ответ оборван" in result
```

- [ ] **Step 6.4: Run tests — verify they fail**

```bash
uv run pytest tests/test_server.py::TestGramaxAiSearch -v
```

Expected: FAIL — `cannot import name 'gramax_ai_search'`.

- [ ] **Step 6.5: Implement `gramax_ai_search`**

In `src/gramax_docportal_mcp/server.py`:

1) At top of file, ensure these imports exist (add what's missing):

```python
import httpx

from gramax_docportal_mcp.client import GramaxClient, GramaxError
from gramax_docportal_mcp.config import Settings
from gramax_docportal_mcp.formatters import (
    format_ai_answer,
    format_catalogs_list,
    format_navigation,
    format_search_results,
    html_to_markdown,
    parse_chat_stream,
)
```

2) Add new tool at the end (after `gramax_get_article`):

```python
@mcp.tool()
async def gramax_ai_search(
    ctx: Context,
    query: str,
    catalog_name: str | None = None,
    articles_language: str | None = None,
    response_language: str | None = None,
    current_article: str | None = None,
) -> str:
    """AI-поиск по документации Gramax: связный ответ с ссылками на источники.

    Использовать для вопросов в свободной форме, когда нужен сгенерированный
    ответ, а не список релевантных статей. Для списка результатов —
    gramax_search.

    Args:
        query: Вопрос на естественном языке.
        catalog_name: Имя каталога для контекста (без него — по всем).
        articles_language: Язык статей в индексе ("ru", "en", ...).
            По умолчанию — из GRAMAX_AI_ARTICLES_LANGUAGE (ru).
        response_language: Язык генерируемого ответа. По умолчанию —
            из GRAMAX_AI_RESPONSE_LANGUAGE (ru).
        current_article: ID текущей статьи как контекст ("catalog_id/path").
    """
    if not query or not query.strip():
        return "Ошибка: поисковый запрос не может быть пустым."

    client: GramaxClient = ctx.lifespan_context["client"]
    base_url: str = ctx.lifespan_context["base_url"]
    settings: Settings = ctx.lifespan_context["settings"]

    chunks: list[str] = []
    try:
        async for chunk in client.ai_search(
            query,
            catalog_name=catalog_name,
            articles_language=articles_language or settings.gramax_ai_articles_language,
            response_language=response_language or settings.gramax_ai_response_language,
            current_article=current_article,
            timeout=settings.gramax_ai_timeout,
        ):
            chunks.append(chunk)
            await ctx.report_progress(progress=len(chunks))
    except httpx.TimeoutException:
        return (
            f"Превышено время ожидания AI-ответа "
            f"({settings.gramax_ai_timeout:.0f}s). "
            "Попробуйте сузить запрос или увеличить GRAMAX_AI_TIMEOUT."
        )
    except (httpx.RemoteProtocolError, httpx.ReadError):
        # Сетевой разрыв в середине стрима — отдаём накопленное с пометкой.
        parsed = parse_chat_stream(chunks)
        partial = format_ai_answer(parsed, base_url)
        return f"{partial}\n\n_(ответ оборван: соединение разорвано)_"
    except GramaxError as e:
        return str(e)

    parsed = parse_chat_stream(chunks)
    return format_ai_answer(parsed, base_url)
```

- [ ] **Step 6.6: Run all tests**

```bash
uv run pytest -v
```

Expected: всё зелёное (старые + новые).

- [ ] **Step 6.7: Run linter**

```bash
uv run ruff check .
```

Expected: без ошибок. Если есть — почини точечно.

- [ ] **Step 6.8: Commit**

```bash
git add src/gramax_docportal_mcp/server.py tests/test_server.py
git commit -m "feat(server): add gramax_ai_search MCP tool with citations"
```

---

## Task 7: Manual smoke test against real Gramax

Этот шаг — проверка на реальном API. Если у тебя нет валидного `GRAMAX_API_TOKEN`, попроси PM/owner — без него этот шаг не выполняется и Acceptance не считается полным. Запиши результат в commit message.

- [ ] **Step 7.1: Create `.env` with real credentials (gitignored)**

```bash
cat > .env <<'ENV'
GRAMAX_BASE_URL=https://knowledge.nau.im
GRAMAX_API_TOKEN=<insert real token here>
ENV
# Verify .env in .gitignore
grep -E '^\.env$|^\.env\b' .gitignore || echo ".env" >> .gitignore
```

- [ ] **Step 7.2: Run server in stdio + manual MCP call (или через mcp-inspector)**

```bash
uv run gramax-docportal-mcp
```

Через MCP Inspector / Claude Code вызвать:
- `gramax_ai_search(query="Что такое ITSM", catalog_name="commercial-knowlage")` — ожидаем markdown с inline-цитатами и блоком «Источники» (URL должны кликаться в Gramax UI).
- `gramax_ai_search(query="")` — ожидаем русскую ошибку валидации.
- Установить `GRAMAX_AI_TIMEOUT=2`, перезапустить, повторить большой запрос — ожидаем русское сообщение про timeout.

- [ ] **Step 7.3: Решить URL `.md` суффикс по факту проверки**

Спека отмечает: «Gramax в CIT-маркере отдаёт article-path без `.md`». Если URL `<base_url>/<full_id>` НЕ открывается в Gramax UI, а с суффиксом `.md` — открывается, добавь нормализацию в `format_ai_answer`:

```python
url_path = c["full_id"] if c["full_id"].endswith(".md") else f"{c['full_id']}.md"
lines.append(f"   {base}/{url_path}")
```

И обнови соответствующий тест `test_format_ai_answer_sources_url_format`. Если URL без `.md` работает — ничего не трогай.

- [ ] **Step 7.4: Если потребовалось менять URL — повторить тесты + commit**

```bash
uv run pytest -v && uv run ruff check .
git add src/gramax_docportal_mcp/formatters.py tests/test_formatters.py
git commit -m "fix(formatters): append .md to source URLs to match Gramax UI"
```

Если изменений не было — этот коммит пропускается.

---

## Task 8: Version bump + ADR Accepted + final verification

- [ ] **Step 8.1: Bump version in `pyproject.toml`**

In `pyproject.toml`, change line `version = "0.2.0"` → `version = "0.3.0"`.

- [ ] **Step 8.2: Mark ADR as Accepted**

In `docs/architecture/adr/0001-streaming-ai-tool.md`, change `**Status:** Proposed` → `**Status:** Accepted`.

- [ ] **Step 8.3: Run full verification**

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src/
```

Expected: всё зелёное, mypy без ошибок.

> Если mypy жалуется на `Citation` TypedDict — убедись, что импортирован из `formatters.py`. Если жалуется на `parse_chat_stream` (`dict` без типов) — оставь как есть (для совместимости с возвратом `format_ai_answer`).

- [ ] **Step 8.4: Commit**

```bash
git add pyproject.toml docs/architecture/adr/0001-streaming-ai-tool.md
git commit -m "$(cat <<'EOF'
chore: bump 0.2.0 → 0.3.0 + ADR-0001 Accepted

New MCP tool: gramax_ai_search (additive, non-breaking).
Verified manually against Gramax API.
EOF
)"
```

- [ ] **Step 8.5: Push (optional — only if user asked to publish)**

Если пользователь просил `git push` — выполнить. Иначе остановиться, оставить локально.

---

## Acceptance Verification Checklist

После всех тасков, прогнать вручную и поставить галочки:

- [ ] `uv run pytest` — все тесты PASS, не менее 29 новых тестов добавлено (3 config + 7 client + 12 formatters + 7 server).
- [ ] `uv run ruff check .` — без ошибок.
- [ ] `uv run mypy src/` — без ошибок.
- [ ] Manual smoke: `gramax_ai_search(query="Что такое ITSM", catalog_name="commercial-knowlage")` возвращает Markdown с `[N](full_id)` и блоком «Источники».
- [ ] Manual smoke: пустой query → русская ошибка без HTTP.
- [ ] Manual smoke: `GRAMAX_AI_TIMEOUT=2` + длинный запрос → русское сообщение про timeout.
- [ ] `pyproject.toml` `version = "0.3.0"`.
- [ ] ADR-0001 `Status: Accepted`.
- [ ] CHANGELOG/release notes (если в проекте есть) — обновлены. (В этом репо CHANGELOG отсутствует — пропускается.)
- [ ] Не сломаны существующие 4 MCP tools (проверить любой из них через MCP Inspector).

---

## Notes for the executing agent

- **Не амендь чужие коммиты.** Каждая задача = отдельный коммит. Если pre-commit hook валит — разбирайся и делай новый коммит, не `--amend`.
- **Не объединяй задачи.** Даже если кажется, что Task 4+5 «логически одно» — они отдельные. Так PM-агент сможет легко откатить точечный шаг.
- **TDD строго:** test first, run-and-see-fail, then impl, then run-and-see-pass. Не пиши имплементацию до failing test.
- **Не изобретай форматов:** константы `_ZWSP`/`_WJ` и regex pattern — извлечены из реальной фикстуры. Если поменяешь — поломаются тесты.
- **Файлы из спеки не трогай:** не редактируй `docs/superpowers/specs/...` и `docs/architecture/adr/0001-...` пока не дойдёшь до Task 8 (там — только смена статуса ADR).
- **Не добавляй новых зависимостей.** Всё, что нужно, уже в `pyproject.toml`.
