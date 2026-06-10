# Gramax Doc Portal MCP Server — Design Spec

## Цель

MCP-сервер для взаимодействия с порталом документации Gramax. Позволяет из Claude/LLM:
- искать статьи в одном или нескольких каталогах
- получать контент статей в Markdown
- просматривать структуру каталогов и навигацию
- получать кликабельные ссылки на статьи

## Стек

- Python 3.12+
- fastmcp >= 2.0.0
- httpx >= 0.28.0
- pydantic-settings >= 2.0.0
- markdownify >= 0.14.1
- Сборка: hatchling
- Пакетный менеджер: uv
- Линтер: ruff

## Архитектура

Плоская 4-модульная структура (паттерн ktalk-mcp):

```
gramax_docportal_mcp/
├── src/gramax_docportal_mcp/
│   ├── __init__.py          # версия пакета
│   ├── server.py            # 4 MCP-инструмента + main()
│   ├── client.py            # async httpx обёртка для Gramax API
│   ├── config.py            # pydantic-settings (base_url, token)
│   └── formatters.py        # HTML→Markdown, форматирование результатов
├── tests/
│   ├── conftest.py
│   ├── test_client.py
│   ├── test_config.py
│   └── test_formatters.py
├── pyproject.toml
├── CLAUDE.md
├── README.md
└── .gitignore
```

### Модули

**config.py** — конфигурация через переменные окружения:
```python
class Settings(BaseSettings):
    gramax_base_url: str          # URL портала, обязательно
    gramax_api_token: str         # Bearer-токен, обязательно

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

**client.py** — async HTTP-клиент:
```python
class GramaxClient:
    def __init__(self, base_url: str, api_token: str):
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=30.0,
        )
```

Методы:
- `list_catalogs()` → `GET /api/catalogs` → `dict`
- `get_navigation(catalog_id)` → `GET /api/catalogs/{id}/navigation` → `dict`
- `get_article_html(catalog_id, article_id)` → `GET /api/catalogs/{id}/articles/{article_id}/html` → `str`
- `search(query, catalog_name=None)` → `GET /api/search/searchCommand?query=...` → `list[dict]`

**formatters.py** — преобразование данных:
- `format_catalogs_list(data: dict) -> str` — markdown-таблица каталогов
- `format_navigation(catalog_id: str, data: dict, base_url: str) -> str` — дерево навигации с URL
- `format_search_results(results: list, base_url: str) -> str` — результаты поиска с хайлайтами и breadcrumbs
- `html_to_markdown(html: str) -> str` — конвертация HTML→Markdown через markdownify

**server.py** — MCP-инструменты + точка входа.

## API Gramax Doc Portal

### Аутентификация

Токен передаётся через заголовок `Authorization: Bearer <token>`.

Получение токена: `GET https://{portal_url}/api/user/token?expiresAt=YYYY-MM-DD`
- Требует аутентифицированного пользователя (cookie)
- По умолчанию 30 дней, максимум 1 год

### Эндпоинты

| Метод | Путь | Описание | Ответ |
|-------|------|----------|-------|
| GET | `/api/catalogs` | Список каталогов | `{data: [{id, title}]}` |
| GET | `/api/catalogs/{id}/navigation` | Дерево навигации | `{data: [{id, title, children?}]}` |
| GET | `/api/catalogs/{id}/articles/{articleId}/html` | HTML статьи | `text/html` |
| GET | `/api/search/searchCommand?query=...&catalogName=...` | Поиск по статьям | `[{type, refPath, title, items, url, breadcrumbs, catalog}]` |

### Типы данных (из исходников Gramax)

```typescript
type CatalogRef = { id: string; title: string };
type CatalogList = { data: CatalogRef[] };
type ArticleRef = { id: string; title: string; children?: ArticleRef[] };
type CatalogNavigation = { data: ArticleRef[] };
```

Поисковый результат содержит:
- `type` — "article"
- `title` — массив `[{type: "text"|"highlight", text: "..."}]`
- `items` — фрагменты с хайлайтами и score
- `url` — относительный путь к статье
- `breadcrumbs` — путь в навигации `[{url, title}]`
- `catalog` — `{name, title, url}`

## MCP-инструменты

### 1. `gramax_list_catalogs`

Параметры: нет

Выход: markdown-таблица каталогов с ID и названием.

### 2. `gramax_get_navigation`

Параметры:
- `catalog_id: str` — ID каталога

Выход: markdown-дерево с отступами, каждый элемент содержит название и полный URL.

### 3. `gramax_search`

Параметры:
- `query: str` — поисковый запрос
- `catalog_name: str | None = None` — имя каталога (если не указано — поиск по всем)

Выход: markdown-список найденных статей с:
- заголовком
- breadcrumbs (путь в навигации)
- полным URL
- фрагментами текста с выделением найденных слов

### 4. `gramax_get_article`

Параметры:
- `catalog_id: str` — ID каталога
- `article_id: str` — ID статьи

Выход: содержимое статьи, сконвертированное из HTML в Markdown.

Примечание: `article_id` передаётся в URL-encoded виде (как в исходниках Gramax). Клиент сам выполняет `urllib.parse.quote(article_id)` перед отправкой запроса.

## Обработка ошибок

```python
class GramaxError(Exception): pass
class GramaxAuthError(GramaxError): ...   # 401/403
class GramaxNotFoundError(GramaxError): ... # 404
```

- 401/403 → "Токен невалиден или истёк. Получите новый: GET /api/user/token"
- 404 → "Каталог/статья не найден(а): {id}"
- Все ошибки ловятся в тулах и возвращаются как строки

## Форматирование

### Ссылки

Полные URL формируются из `base_url` + относительный путь из API.

Пример: `base_url=https://docs.example.com`, `url=/docs/deploy` → `https://docs.example.com/docs/deploy`

### Поиск

Хайлайты из search API (`type: "highlight"`) конвертируются в **bold** markdown.
Breadcrumbs отображаются через ` > ` разделитель.

### HTML → Markdown

Используется `markdownify` с параметрами:
- `strip=["img", "script", "style"]` — убрать ненужные элементы
- `heading_style="ATX"` — заголовки через `#`

## Конфигурация запуска

Env-переменные:
- `GRAMAX_BASE_URL` — URL портала (обязательно)
- `GRAMAX_API_TOKEN` — Bearer-токен (обязательно)

`.mcp.json`:
```json
{
  "mcpServers": {
    "gramax": {
      "command": "uvx",
      "args": ["gramax-docportal-mcp"],
      "env": {
        "GRAMAX_BASE_URL": "https://docs.example.com",
        "GRAMAX_API_TOKEN": "..."
      }
    }
  }
}
```

## Тестирование

- `test_config.py` — загрузка настроек из env, валидация обязательных полей
- `test_client.py` — моки httpx, проверка URL/заголовков, обработка ошибок
- `test_formatters.py` — unit-тесты форматирования каталогов, навигации, поиска, HTML→MD

Зависимости для тестов: pytest, pytest-asyncio, pytest-httpx, ruff

## Верификация

1. `uv run pytest` — все тесты проходят
2. `uv run ruff check .` — нет ошибок линтера
3. Ручная проверка: запустить сервер, подключить к Claude Code через `.mcp.json`, выполнить каждый инструмент
