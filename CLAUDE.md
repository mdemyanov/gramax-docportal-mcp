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
- `GET /api/search/searchCommand` — поиск
  - Query params: `query`, `catalogName`, `type` (`"vector"`), `articlesLanguage`
  - Body (JSON): `resourceFilter` (`"without"|"with"|"only"`), `propertyFilter` (рекурсивный фильтр с `eq`/`contains`/`isEmpty`/`and`/`or`)

Auth: `Authorization: Bearer <token>` (получить через `GET /api/user/token`)

## Conventions

- Async everywhere
- Все сообщения об ошибках на русском
- HTML статей конвертируется в Markdown через markdownify
- article_id в URL передаётся URL-encoded

## Команда и workflow

В проекте определена команда из 4 агентов: PM (orchestrator) + Researcher + SA + Dev. Карта команды, контракт вызова субагентов, канонический workflow и красные линии — в [AGENTS.md](AGENTS.md).

Для новых фич:
1. PM декомпозирует через `superpowers:brainstorming` → `writing-plans`
2. SA пишет спеку в `docs/superpowers/specs/` (+ ADR в `docs/architecture/adr/` при значимых решениях)
3. Dev реализует через `superpowers:test-driven-development`

Уроки команды — в [docs/lessons-learned.md](docs/lessons-learned.md).
