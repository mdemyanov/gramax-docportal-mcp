# Agent Workflow для gramax-docportal-mcp

**Дата:** 2026-05-08
**Статус:** Approved (brainstorming)
**Источник:** адаптация шаблона `/Users/mdemyanov/knowlage/project_template`

## Контекст

Проект `gramax-docportal-mcp` — Python MCP-сервер v0.2.0 для интеграции с порталом документации Gramax. Узкая 4-модульная структура (`server.py` / `client.py` / `formatters.py` / `config.py`), один разработчик, базовый GitHub-flow на `main`.

Шаблон `project_template` ориентирован на внутренние делевери- и документационные проекты Naumen на основе Gramax (артефакты в `content/`, публикация в Gramax, ветки `private`/`public`, 11 ролей, профили, overlays). Для код-библиотеки бо́льшая часть инфраструктуры шаблона нерелевантна.

Эта спека описывает, **что именно из шаблона переносится** в текущий проект, чтобы дальнейшее развитие шло через дисциплинированный агентный workflow с минимальными накладными расходами.

## Цель

Перенести из шаблона:
- Карту команды агентов (AGENTS.md) — 4 роли вместо 11
- Промпты 4 субагентов (PM, Researcher, SA, Dev) в `.claude/agents/`, адаптированные под Python MCP
- Журнал уроков (`docs/lessons-learned.md`)
- Структуру для ADR (`docs/architecture/`)
- Обновлённый CLAUDE.md со ссылкой на AGENTS.md

НЕ переносить: `content/`, профили, overlays, валидаторы, `init.sh`, `.doc-root.yaml`, ветки `private`/`public`, slash-команды (отложены), роли BA/QA-author/QA-runner/DevOps/Tech-writer/DevSecOps/Compliance.

## Архитектура решения

### Команда (4 роли)

| Имя | Описание | Где | Модель | Промпт |
|-----|----------|-----|--------|--------|
| pm | Координатор: декомпозиция, маршрутизация, ревью | main | Opus | (живёт в main-context) |
| researcher | Сбор контекста: Gramax API, fastmcp, MCP spec, аналоги | subagent | Sonnet | `.claude/agents/researcher-agent.md` |
| sa | Архитектор: дизайн модулей, контракты, ADR | subagent | Sonnet | `.claude/agents/sa-agent.md` |
| dev | TDD-разработчик (совмещает QA-author + runner) | subagent | Sonnet | `.claude/agents/dev-agent.md` |

Кандидат №1 на добавление в будущем — DevOps (релизы PyPI, GHA, semver).

### Канонический поток

```
PM (декомпозиция)
  → Researcher (если незнаком домен/API; опц.)
  → SA (спека в docs/superpowers/specs/ + ADR в docs/architecture/adr/)
  → Dev (TDD: красный → зелёный → рефакторинг)
  → PM (lessons-learned + commit/PR)
```

Под капотом каждая фаза опирается на встроенные superpowers:
- PM использует `superpowers:brainstorming` и `superpowers:writing-plans`
- SA пишет в стандартное место `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`
- Dev обязан использовать `superpowers:test-driven-development`
- Перед claim "готово" — `superpowers:verification-before-completion`

### Контракт вызова субагента

При запуске любой роли (через Task tool или `@<role>-agent` mention) передавай:

1. **Цель** одной фразой
2. **Входные файлы** — пути к контексту (спека, ADR, код)
3. **Ожидаемый артефакт** — какой файл должен появиться/измениться
4. **Критерии приёмки** — как проверить, что задача выполнена

Субагент НЕ ищет контекст «вокруг» — работает по явно переданному скопу.

### Self-improvement

- `docs/lessons-learned.md` — append-only журнал (формат: дата, контекст, урок)
- Субагенты сохраняют находки в auto-memory (типы: `reference`, `project`, `feedback`)

## Файлы

### Создаются (8)

| Файл | Назначение | Размер |
|------|------------|--------|
| `AGENTS.md` | Карта команды, контракт вызова, workflow, красные линии | ~80 стр. |
| `.claude/agents/pm-agent.md` | Промпт PM | ~110 стр. |
| `.claude/agents/researcher-agent.md` | Промпт Researcher | ~80 стр. |
| `.claude/agents/sa-agent.md` | Промпт SA | ~120 стр. |
| `.claude/agents/dev-agent.md` | Промпт Dev | ~90 стр. |
| `docs/lessons-learned.md` | Append-only журнал, заголовок + формат записи | ~20 стр. |
| `docs/architecture/README.md` | Описание папки: ADR, design-notes | ~15 стр. |
| `docs/architecture/adr/0000-template.md` | Шаблон ADR (Context / Decision / Consequences) | ~25 стр. |

### Меняется (1)

- `CLAUDE.md` — добавляется блок «Команда и workflow» (5-10 строк) со ссылкой на AGENTS.md.

### Не трогается

- `src/`, `tests/`, `pyproject.toml`, `uv.lock` — код не меняется
- `docs/superpowers/specs/`, `docs/superpowers/plans/` — уже работают
- `README.md` — это user-facing, агентный workflow туда не нужен

### Создаётся on-demand

- `docs/research/` — папка появляется при первой задаче researcher (агент сам создаёт нужный путь). Не предсоздаём.

## Адаптация промптов

Промпты копируются из `template/.claude/plugins/project/agents/<role>-agent.md` и адаптируются:

### pm-agent.md

- Команда — 4 роли вместо 10 (researcher / sa / dev)
- Артефакты переориентированы: `docs/superpowers/specs/`, `docs/architecture/adr/`, `src/gramax_docportal_mcp/`
- Удалено: pipelines (project-planning / ba-acceptance / critical-path), worktree-ритуал, soft-suggest opt-in (DevSecOps / Compliance / Tech-writer), упоминания `content/`
- Шаблон декомпозиции: коды задач `RES-NNN`, `SA-NNN`, `DEV-NNN`
- MoSCoW (Must / Should / Could / Won't) — оставлено
- Красные линии переписаны под Python-MCP

### researcher-agent.md

- Структура research-выжимки и правила цитирования — без изменений
- Источники: Gramax API (`https://gram.ax/api/...`), fastmcp docs, MCP spec, существующие MCP-сервера (для аналогии), httpx / markdownify changelogs
- Артефакт: `docs/research/<topic>.md`
- Триггеры: незнакомый эндпоинт Gramax API, новая версия fastmcp, аналоги в экосистеме MCP

### sa-agent.md

- Структура ADR (Context → Decision → Consequences), правило ≤150 строк, целостность ADR-цепочки — без изменений
- Артефакты: `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` + `docs/architecture/adr/NNNN-<topic>.md`
- Контекст архитектуры: 4-модульная структура; YAGNI на разбиение модулей
- Опирается на существующий contract: async, ошибки на русском, fastmcp-tools, MCP-protocol совместимость

### dev-agent.md

- TDD-цепочка обязательна (через `superpowers:test-driven-development`)
- Команды проверки: `uv run pytest`, `uv run ruff check .`, `uv run mypy src/`
- Совмещён QA-author/runner: Dev сам пишет failing tests, потом проходит
- Mock-политика: httpx-mock — ок; целиком mock client.py — нет (без обоснования)
- Красные линии: НЕ менять `pyproject.toml` без bump-rationale, НЕ ломать MCP-инструменты, НЕ публиковать токены в тестах (использовать `monkeypatch`/env-fixture)

## Красные линии (общие, для AGENTS.md)

- НЕ принимай DEV-задачу без предшествующего SA-артефакта (спека или ADR)
- НЕ публикуй секреты (`.env`, `GRAMAX_API_TOKEN`, GitHub PAT)
- НЕ меняй версию в `pyproject.toml` без bump-rationale в commit message
- НЕ ломай обратную совместимость инструментов (`gramax_*`) без MAJOR-bump
- pytest + ruff + mypy зелёные перед commit

## Out of scope

- DevOps-агент, QA-агенты раздельные, BA, Tech-writer, DevSecOps, Compliance — не делаем
- Slash-команды (`/pm`, `/sa`, `/dev`, `/research`) — следующая итерация
- `content/`, профили, валидаторы, `init.sh` — не нужны для код-проекта
- Перенос документов в Gramax — не делаем (open-source на GitHub)
- Изменения в `src/` или `tests/` — это спека про процесс, не про фичи

## Testability

Это документация и промпты — нет автотестов. Проверка через smoke-сценарии:

1. **Smoke 1 — структура.** `find AGENTS.md .claude/agents docs/lessons-learned.md docs/architecture -type f` показывает все 8 файлов; ссылки внутри AGENTS.md и CLAUDE.md ведут на существующие пути.
2. **Smoke 2 — субагенты загружаются.** Запустить любого агента через Task tool с тестовой задачей «перечисли свои красные линии». Если ответ по делу — frontmatter и discoverability ОК.
3. **Smoke 3 — workflow end-to-end** на учебной фиче (необязателен в этой итерации; станет первой настоящей фичей на новом процессе).

## Risks / open questions

- **Subagents discovery:** project-level `.claude/agents/` должен подхватываться и в Claude Code CLI, и в VSCode-расширении. Если не подхватится — fallback на `~/.claude/agents/`.
- **Frontmatter `model:`** в Claude Code subagents может быть нестабильным синтаксисом. Если упадёт — убрать `model:` (унаследует от родителя).

## Будущие итерации

1. Добавить slash-команды (`/pm`, `/sa`, `/dev`, `/research`) — ~80 строк суммарно
2. Добавить DevOps-агента — когда настанет регулярный релизный цикл (PyPI / GHA)
3. Возможно — `pipelines/release` для автоматизации semver-bump → CHANGELOG → tag → publish
