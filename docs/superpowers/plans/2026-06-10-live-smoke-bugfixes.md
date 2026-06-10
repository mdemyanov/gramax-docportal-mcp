# План: исправление багов по итогам live smoke-теста (v0.3.1)

**Дата:** 2026-06-10
**Источник:** живой smoke-тест всех 5 MCP-инструментов против https://knowledge.nau.im (8/10 PASS).
**Релиз:** PATCH v0.3.0 → v0.3.1. Публичные сигнатуры `gramax_*` не меняются — MAJOR не нужен.
**Поток:** SA → DEV (researcher не нужен, факты собраны).

## Найденные баги

### BUG-1 (critical): `format_search_results` падает на breadcrumbs
- `src/gramax_docportal_mcp/formatters.py:115-118`
- Реальный API: `breadcrumbs[].title` — список фрагментов `[{"type": "highlight"|"text", "text": "..."}]`, не строка.
- Эффект: `TypeError: sequence item 1: expected str instance, list found` на каждом полнотекстовом поиске → `gramax_search` полностью неработоспособен.
- Подсказка: в formatters.py уже есть `_render_highlights(items)` для этой структуры.

### BUG-2 (critical, замаскирован BUG-1): properties — KeyError `name`
- `src/gramax_docportal_mcp/formatters.py:128-129`
- Реальный API: `properties: [{"id": "HR", "value": ["yes"]}]` — ключ `id`, не `name`.

### BUG-3 (major): 5xx утекают как необработанный `httpx.HTTPStatusError`
- `src/gramax_docportal_mcp/client.py:45-53` — `_check_response` мапит только 401/403/404, дальше `raise_for_status()`.
- Все инструменты ловят только `GramaxError` → MCP-клиент получает английский ToolError вместо русского сообщения.
- Воспроизведено: vector-поиск (`type=vector`) на портале возвращает 500.

### BUG-4 (minor): пустой `GRAMAX_API_TOKEN` роняет httpx
- Пустая строка проходит pydantic-валидацию → заголовок `Bearer ` → `LocalProtocolError: Illegal header value`.
- Дизайн-развилка: портал отвечает анонимно (200 без Authorization), а невалидный токен даёт 401 даже на публичные эндпоинты → кандидат на опциональный токен / анонимный режим (ADR-0002).

### Корневая причина зелёных тестов при сломанном поиске
- Фикстуры tests/ не соответствуют реальным формам API (breadcrumbs.title строкой, properties.name).

## Декомпозиция (PM)

| Фича | MoSCoW | Задачи | Зависимости |
|------|--------|--------|-------------|
| 1. Починка `format_search_results` (BUG-1+2) | Must | SA-001 → DEV-001 | — |
| 2. Русификация 5xx (BUG-3) | Must | SA-002 → DEV-002 | — |
| 3. Валидация/опциональность токена (BUG-4) | Should | SA-003 (+ возможен ADR-0002) → DEV-003 | — |
| 4. Контрактные фикстуры по реальным ответам | Should | SA-004 → DEV-004 | SA-004 после SA-001/002; DEV-004 после DEV-001/002 |

- SA-001/002/003 — параллельно; DEV-001/002 — параллельно.
- PR-стратегия: один Must = один PR (PR#1 поиск, PR#2 5xx, PR#3 токен, PR#4 фикстуры — или фикстуры в составе PR#1/#2 по решению SA-004).
- Красная линия: DEV не отдавать без SA-артефакта в `docs/superpowers/specs/`.

## GO-критерии релиза v0.3.1

- [ ] pytest + ruff (+ mypy) зелёные
- [ ] Повторный live smoke против knowledge.nau.im: `gramax_search` (fulltext) PASS; vector → русское сообщение об ошибке
- [ ] bump-rationale в commit message, запись в CHANGELOG
- [ ] Known issue в README: токен просрочен, `GET /api/user/token` требует браузерную сессию (автообновления нет)

## Что работает (регрессий не вносить)

`gramax_list_catalogs`, `gramax_get_navigation`, `gramax_get_article`, `gramax_ai_search` (анонимно), валидация пустых аргументов, обработка 401/404.
