# Code Review & Refactoring: gramax-docportal-mcp

**Дата:** 2026-04-07
**Статус:** Draft
**Автор:** Code Review Agent

## Контекст

Проект gramax-docportal-mcp (v0.1.1, Alpha) — MCP-сервер для портала документации Gramax.
388 строк исходного кода в 4 модулях, 387 строк тестов. Стек: Python 3.12+, fastmcp, httpx,
pydantic-settings, markdownify, beautifulsoup4.

Проведено ревью кодовой базы, выявлены 12 проблем разного приоритета. Проект имеет хорошую
архитектуру и конвенции, но содержит критические баги (resource leak, unsafe dict access),
пробелы в тестовом покрытии (server.py не покрыт) и недостаточную CI-инфраструктуру.

## Подход

Три тематических PR, каждый независимо мержится и тестируется:

```
PR 1 (Safety)  ─────────────►  PR 2 (Tests + Validation)
PR 3 (CI/DX)  ──────────────►  (независимо от PR 1)
```

PR 1 и PR 3 разрабатываются параллельно. PR 2 зависит от PR 1.

---

## PR 1: Safety & Correctness

### 1.1 Resource leak — замена глобального клиента на lifespan

**Проблема:** `server.py:22-35` — `GramaxClient` создаётся глобально через `_get_client()`, 
но `httpx.AsyncClient.aclose()` никогда не вызывается. Это утечка ресурсов (connection pool).

**Решение:** Использовать `@lifespan` декоратор из `fastmcp.server.lifespan`. Клиент создаётся 
при старте сервера и корректно закрывается при остановке через `async with`.

**Файл:** `src/gramax_docportal_mcp/server.py`

Было:
```python
_client: GramaxClient | None = None
_base_url: str = ""

def _get_client() -> GramaxClient:
    global _client, _base_url
    if _client is None:
        settings = Settings()
        _base_url = settings.gramax_base_url.rstrip("/")
        _client = GramaxClient(base_url=_base_url, api_token=settings.gramax_api_token)
    return _client

@mcp.tool()
async def gramax_list_catalogs() -> str:
    client = _get_client()
    data = await client.list_catalogs()
    return format_catalogs_list(data)
```

Стало:
```python
from fastmcp import Context
from fastmcp.server.lifespan import lifespan

@lifespan
async def app_lifespan(server):
    settings = Settings()
    base_url = settings.gramax_base_url.rstrip("/")
    async with GramaxClient(base_url=base_url, api_token=settings.gramax_api_token) as client:
        yield {"client": client, "base_url": base_url}

mcp = FastMCP("Gramax", instructions="...", lifespan=app_lifespan)

@mcp.tool()
async def gramax_list_catalogs(ctx: Context) -> str:
    client = ctx.lifespan_context["client"]
    data = await client.list_catalogs()
    return format_catalogs_list(data)
```

Все 4 tool-функции получают `ctx: Context` параметр и извлекают клиент через
`ctx.lifespan_context["client"]` и base_url через `ctx.lifespan_context["base_url"]`.

Удаляются: `_client`, `_base_url`, `_get_client()`.

### 1.2 beautifulsoup4 не в зависимостях

**Проблема:** `formatters.py:5` — `from bs4 import BeautifulSoup` — прямой импорт, 
но `beautifulsoup4` не объявлен в `pyproject.toml`. Работает транзитивно через markdownify,
но это хрупко — markdownify может убрать зависимость в будущей версии.

**Решение:** Добавить `"beautifulsoup4>=4.9"` в `dependencies` в `pyproject.toml`.

### 1.3 Unsafe dict access в formatters.py

**Проблема:** Три места, где `dict['key']` вместо `dict.get('key', default)`:

- Строка 24: `cat['title']` и `cat['id']` — упадёт, если API вернёт неполный объект каталога
- Строка 37-38: `item['id']` и `item['title']` — упадёт в навигационном дереве
- Строка 93: `b["title"]` — упадёт в breadcrumbs поисковых результатов

**Решение:** Заменить на `.get()` с fallback-значениями:
```python
# Строка 24
lines.append(f"| {cat.get('title', '???')} | {cat.get('id', '???')} |")

# Строка 37-38
url = f"{base_url}/{catalog_id}/{item.get('id', '')}"
lines.append(f"{indent}- [{item.get('title', '???')}]({url})")

# Строка 93
path_parts = [catalog.get("title", "")] + [b.get("title", "") for b in breadcrumbs]
```

### 1.4 Unbounded recursion в _render_tree

**Проблема:** `formatters.py:32-42` — `_render_tree()` рекурсивно обходит дерево без
ограничения глубины. Мальформленный API-ответ с бесконечно вложенным деревом вызовет
`RecursionError`.

**Решение:** Добавить константу `MAX_NAV_DEPTH = 20` и проверку глубины:
```python
MAX_NAV_DEPTH = 20

def _render_tree(items: list[dict], base_url: str, catalog_id: str, depth: int = 0) -> list[str]:
    lines: list[str] = []
    if depth >= MAX_NAV_DEPTH:
        return lines
    indent = "  " * depth
    for item in items:
        # ...
```

### 1.5 Inefficient blank line cleanup

**Проблема:** `formatters.py:136-137` — `while "\n\n\n"` loop многопроходный.

**Решение:** Однопроходная замена через regex:
```python
import re
# ...
md = re.sub(r"\n{3,}", "\n\n", md)
```

### Тесты для PR 1

Добавить в `tests/test_formatters.py`:
- Тест на malformed response (отсутствующие ключи `title`/`id` в каталогах)
- Тест на глубокое дерево навигации (проверка truncation на MAX_NAV_DEPTH)
- Тест на regex-замену множественных переносов строк

**Файлы, затрагиваемые PR 1:**
- `src/gramax_docportal_mcp/server.py` (lifespan, Context)
- `src/gramax_docportal_mcp/formatters.py` (safe access, recursion limit, regex)
- `pyproject.toml` (beautifulsoup4 dep)
- `tests/test_formatters.py` (новые тесты)

---

## PR 2: Server Tests & Input Validation

### 2.1 Тесты MCP-инструментов

**Проблема:** 4 MCP-инструмента в `server.py` полностью не покрыты тестами.

**Стратегия:** Прямой вызов tool-функций с mock Context. Это проще и быстрее, чем
поднимать полный MCP-сервер для тестов.

**Файл:** `tests/test_server.py` (новый)

```python
from unittest.mock import AsyncMock, MagicMock
from fastmcp import Context
from gramax_docportal_mcp.client import GramaxClient, GramaxError, GramaxAuthError
from gramax_docportal_mcp.server import (
    gramax_list_catalogs,
    gramax_get_navigation,
    gramax_search,
    gramax_get_article,
)

@pytest.fixture
def mock_ctx():
    mock_client = AsyncMock(spec=GramaxClient)
    ctx = MagicMock(spec=Context)
    ctx.lifespan_context = {"client": mock_client, "base_url": "https://example.com"}
    return ctx, mock_client
```

**Покрытие тестов:**
- `gramax_list_catalogs` — happy path + GramaxError
- `gramax_get_navigation` — happy path + пустой catalog_id + GramaxError
- `gramax_search` — happy path с фильтрами + пустой query + GramaxError
- `gramax_get_article` — happy path + GramaxAuthError + GramaxNotFoundError

### 2.2 Input validation

**Проблема:** MCP-инструменты не валидируют входные данные. Пустой `catalog_id` или `query`
приведёт к бессмысленному HTTP-запросу.

**Решение:** Guard clauses в начале каждой tool-функции:
```python
@mcp.tool()
async def gramax_get_navigation(ctx: Context, catalog_id: str) -> str:
    if not catalog_id or not catalog_id.strip():
        return "Ошибка: catalog_id не может быть пустым."
    # ...

@mcp.tool()
async def gramax_search(ctx: Context, query: str, ...) -> str:
    if not query or not query.strip():
        return "Ошибка: поисковый запрос не может быть пустым."
    # ...

@mcp.tool()
async def gramax_get_article(ctx: Context, catalog_id: str, article_id: str) -> str:
    if not catalog_id or not catalog_id.strip():
        return "Ошибка: catalog_id не может быть пустым."
    if not article_id or not article_id.strip():
        return "Ошибка: article_id не может быть пустым."
    # ...
```

### 2.3 Общие fixtures в conftest.py

**Проблема:** `tests/conftest.py` пустой, хотя `base_url` и `api_token` дублируются 
в `test_client.py`.

**Решение:** Перенести в `conftest.py`:
```python
import pytest

@pytest.fixture
def base_url() -> str:
    return "https://gramax.example.com"

@pytest.fixture
def api_token() -> str:
    return "test-token-12345"
```

**Файлы, затрагиваемые PR 2:**
- `tests/test_server.py` (новый файл)
- `src/gramax_docportal_mcp/server.py` (guard clauses)
- `tests/conftest.py` (общие fixtures)
- `tests/test_client.py` (удалить дублированные fixtures)

---

## PR 3: CI & DX Improvements

### 3.1 CI pipeline на push/PR

**Проблема:** Тесты и линтинг запускаются только при публикации релиза, не на push/PR.

**Решение:** Новый workflow `.github/workflows/ci.yml`:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test-and-lint:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: uv sync --dev
      - run: uv run ruff check .
      - run: uv run pytest -v
```

### 3.2 .env.example

**Проблема:** Нет шаблона для переменных окружения — разработчики должны читать README.

**Решение:** Создать `.env.example`:
```
GRAMAX_BASE_URL=https://your-portal.example.com
GRAMAX_API_TOKEN=your-api-token-here
```

### 3.3 Расширение правил ruff

**Проблема:** `pyproject.toml` — только базовые правила `["E", "F", "I", "N", "W"]`.

**Решение:** Расширить:
```toml
select = ["E", "F", "I", "N", "W", "UP", "S", "C901", "ASYNC"]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["S101"]  # Allow assert in tests
```

Правила:
- `UP` — pyupgrade (современные Python-паттерны)
- `S` — flake8-bandit (безопасность)
- `C901` — McCabe complexity
- `ASYNC` — async best practices

После добавления правил запустить `uv run ruff check .` и исправить нарушения или
добавить точечные `# noqa` с обоснованием.

### 3.4 Type checking с mypy

**Проблема:** Хорошие type annotations (~90% покрытие), но нет проверки в CI.

**Решение:** Добавить mypy в dev-зависимости и настроить:
```toml
[dependency-groups]
dev = [
    # ... existing ...
    "mypy>=1.10",
]

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

Добавить шаг в CI workflow:
```yaml
- run: uv run mypy src/
```

Начать с умеренно строгого режима (`disallow_untyped_defs`), не `strict`, чтобы
избежать массовых правок в первом проходе.

**Файлы, затрагиваемые PR 3:**
- `.github/workflows/ci.yml` (новый файл)
- `.env.example` (новый файл)
- `pyproject.toml` (ruff rules, mypy config, mypy dep)

---

## Риски и митигации

| Риск | Митигация |
|------|-----------|
| Lifespan ломает `mcp.run()` | Тест: `uv run gramax-docportal-mcp` вручную перед мержем PR 1 |
| Новые ruff-правила — много нарушений | Запустить `ruff check .` после добавления; фиксить или `noqa` |
| mypy strict отвергает код | Начать с нестрогого; ужесточать позже |
| Тесты server.py — flaky из-за async | Mock Context, без реальных сетевых вызовов |
| pyproject.toml конфликт между PR 1 и PR 3 | PR 1 меняет только `dependencies`, PR 3 — `[tool.ruff]`, `[tool.mypy]`, `dev`. Разные секции, конфликт маловероятен. При мерже — resolve вручную |

## Верификация

1. **PR 1:** `uv run pytest -v` (все тесты, включая новые для formatters) + ручной запуск `uv run gramax-docportal-mcp`
2. **PR 2:** `uv run pytest -v` (новые тесты server.py проходят) + проверка валидации (пустые строки)
3. **PR 3:** `uv run ruff check .` + `uv run mypy src/` + проверка CI workflow через push в branch
