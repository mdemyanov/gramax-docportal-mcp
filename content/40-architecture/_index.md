---
order: 40
title: Архитектура
---

Компоненты и границы, модели данных, контракты API, спеки-спутники к ADR.

## Спеки

Проектные спеки `gramax-docportal-mcp` в хронологическом порядке. До перехода на канон
nauta они жили в `docs/superpowers/specs/`; перенесены сюда, потому что переживают
закрытие своего эпика как ответ на вопрос «почему так устроено».

- [Gramax Doc Portal MCP Server — Design Spec](2026-04-06-gramax-mcp-design.md) — базовая
  спека сервера: 4-модульная структура, стек, контракты пяти инструментов `gramax_*`.
- [Code Review & Refactoring: gramax-docportal-mcp](2026-04-07-code-review-refactoring-design.md) —
  разбор 12 находок ревью кодовой базы v0.1.1 и план из трёх тематических PR.
- [Agent Workflow для gramax-docportal-mcp](2026-05-08-agent-workflow-design.md) — что из шаблона
  проектов переносится в этот репозиторий: команда из 4 ролей, промпты субагентов, журнал
  уроков. Описывает состояние дерева на 2026-05-08 (пути `docs/…` в тексте — исторические).
- [Gramax AI Search — Design Spec](2026-05-08-gramax-ai-search-design.md) — инструмент
  `gramax_ai_search` поверх streaming-эндпоинта `/api/search/chat`, парсер CIT-маркеров,
  блок «Источники». Решение-родитель — [ADR-001](../00-project/adr/ADR-001-streaming-ai-tool.md).
- [HTTP Error Handling — Design Spec (BUG-3)](2026-06-10-http-error-handling-design.md) — BUG-3:
  `httpx.HTTPStatusError` и сетевые ошибки не были подклассами `GramaxError` и утекали
  к MCP-клиенту английским traceback'ом.
- [Bugfix: format_search_results — BUG-1 (breadcrumbs) + BUG-2 (properties)](2026-06-10-search-formatter-fix-design.md) — BUG-1/BUG-2:
  `format_search_results` падал на реальной форме `breadcrumbs` и `properties`; фикстуры
  приведены к ответу живого API.
- [Опциональный токен / Анонимный режим — Design Spec (BUG-4)](2026-06-10-token-validation-design.md) —
  BUG-4: crash при `GRAMAX_API_TOKEN=""`. Решение-родитель —
  [ADR-002](../00-project/adr/ADR-002-optional-api-token.md).

## Правила

- Решение «почему так» — в ADR ([00-project/adr/](../00-project/adr/_index.md)); здесь — как это устроено.
- Статья-спутник ADR объявляет родителя ссылкой в шапке.
