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
