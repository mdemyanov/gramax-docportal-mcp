# AGENTS.md — gramax-docportal-mcp

Карта команды AI-агентов для развития MCP-сервера. Адаптация шаблона `project_template` под Python-библиотеку.

## Каталог ролей

| Имя | Описание | Где исполняется | Модель | Промпт |
|-----|----------|-----------------|--------|--------|
| pm | Координатор: декомпозиция, маршрутизация, ревью | main | Opus | (живёт в main-context) |
| researcher | Сбор контекста: Gramax API, fastmcp, MCP-spec, аналоги | subagent | Sonnet | `.claude/agents/researcher-agent.md` |
| sa | Архитектор: дизайн модулей, контракты, ADR | subagent | Sonnet | `.claude/agents/sa-agent.md` |
| dev | TDD-разработчик (совмещает QA-author + runner) | subagent | Sonnet | `.claude/agents/dev-agent.md` |

**Почему так:** PM-координация живёт в main-context, чтобы не раздувать контекст субагентов. Ролевая работа выносится в субагенты на более дешёвой модели — экономия LLM-бюджета. DevOps/Tech-writer/QA отдельно — не делаем; в библиотеке этого пока мало (см. секцию «Будущие итерации» в спеке).

## Контракт вызова субагента

При запуске любой роли (через Task tool или `@<role>-agent` mention) передавай:

1. **Цель** одной фразой.
2. **Входные файлы** — пути к контексту (спека, ADR, код, тесты).
3. **Ожидаемый артефакт** — какой файл должен появиться/измениться.
4. **Критерии приёмки** — как проверить, что задача выполнена.

Пример корректного prompt'а для `dev-agent`:

```
Цель: реализовать gramax_get_attachments по спеке.
Входы:
  docs/superpowers/specs/2026-05-15-attachments-design.md,
  docs/architecture/adr/0001-attachments-tool.md,
  tests/test_attachments.py (failing stubs).
Артефакт: src/gramax_docportal_mcp/server.py (+ client.py если нужен новый эндпоинт).
Критерии: pytest зелёный, ruff/mypy чистые, AC из спеки покрыты, не сломаны существующие инструменты.
```

Субагент **не ищет контекст «вокруг»** — работает по явно переданному скопу.

(Полные prompt'ы — в `.claude/agents/<role>-agent.md`.)

## Канонический workflow

```
PM (декомпозиция)
  → Researcher (если незнаком домен/API; опц.)
  → SA (спека в docs/superpowers/specs/ + ADR в docs/architecture/adr/, если значимое решение)
  → Dev (TDD: красный → зелёный → рефакторинг)
  → PM (lessons + commit/PR)
```

Под капотом каждая фаза опирается на встроенные superpowers:

| Фаза | Скилл |
|------|-------|
| PM уточняет неоднозначность | `superpowers:brainstorming` |
| PM/SA пишут план реализации | `superpowers:writing-plans` |
| Dev реализует по плану | `superpowers:test-driven-development` |
| Любой агент перед claim "готово" | `superpowers:verification-before-completion` |
| Dev при баге | `superpowers:systematic-debugging` |

## Self-improvement

- `docs/lessons-learned.md` — append-only журнал.
- Субагенты сохраняют находки в auto-memory (типы: `reference`, `project`, `feedback`).
- PM при декомпозиции новой фичи скользит по последним ~10 записям lessons.

## Красные линии

- НЕ принимай DEV-задачу без предшествующего SA-артефакта (спека или ADR).
- НЕ публикуй секреты (`.env`, `GRAMAX_API_TOKEN`, GitHub PAT).
- НЕ меняй версию в `pyproject.toml` без bump-rationale в commit message.
- НЕ ломай обратную совместимость инструментов (`gramax_*`) без MAJOR-bump (semver).
- pytest + ruff + mypy зелёные перед commit.
- НЕ хардкодь URL портала в тестах — только через env / fixture.

## Формат отчёта PM

После декомпозиции PM выдаёт перечень задач:

```markdown
## Фича: [Название]
**Контекст:** [зачем, какую проблему]
**MoSCoW:** Must | Should | Could | Won't

### Задачи
- [ ] RES-001: [исследовать X] → docs/research/[slug].md  *(опц.)*
- [ ] SA-001: [дизайн Y, зависит от RES-001] → docs/superpowers/specs/[date]-[slug]-design.md (+ ADR)
- [ ] DEV-001: [реализация, зависит от SA-001] → src/gramax_docportal_mcp/<file> + tests/<file>

### Зависимости / Риски / GO-критерии
```

## Out of scope

- Роли BA, QA-author, QA-runner, DevOps, Tech-writer, DevSecOps, Compliance — не делаем (см. спеку).
- Slash-команды (`/pm`, `/sa`, `/dev`, `/research`) — следующая итерация.
- `content/`, профили, overlays, валидаторы — не нужны для код-проекта.
- Перенос документации в Gramax — нет (open-source на GitHub).
