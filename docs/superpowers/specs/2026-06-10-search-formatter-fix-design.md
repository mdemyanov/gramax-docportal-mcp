# Bugfix: format_search_results — BUG-1 (breadcrumbs) + BUG-2 (properties)

**Дата:** 2026-06-10
**Статус:** Approved (review)
**Запрос PM:** SA-001 — исправить `format_search_results` по результатам live-теста против https://knowledge.nau.im

## Контекст

Инструмент `gramax_search` полностью неработоспособен на реальных порталах Gramax: каждый вызов
приводит к необработанному исключению в Python-слое. Юнит-тесты зелёные, потому что тестовые
фикстуры содержат `breadcrumbs[].title` как строку и `properties[].name`, что противоречит
реальному API.

Воспроизведено локально (`uv run pytest` — 4/4 pass, но `format_search_results` с реальным
payload — `TypeError: sequence item 1: expected str instance, list found`).

## Цель

Исправить два crash-бага в `format_search_results` и привести тестовые фикстуры в соответствие
с реальной формой API-ответа.

## Контракт MCP-инструмента

| Поле | Значение |
|------|----------|
| Имя | `gramax_search` (без изменений) |
| Параметры | без изменений |
| Возвращает | `str` — Markdown (без изменений) |
| Совместимость | PATCH-релиз, breaking change отсутствует |

Сигнатура публичного инструмента `gramax_search` **не меняется**.

## BUG-1: breadcrumbs — `title` является списком фрагментов

### Симптом

`TypeError: sequence item N: expected str instance, list found`

Строки `formatters.py:117-118`:
```python
path_parts = [catalog.get("title", "")] + [b.get("title", "") for b in breadcrumbs]
path = " > ".join(p for p in path_parts if p)
```

`b.get("title", "")` возвращает `list[dict]` (список фрагментов highlight/text), а не `str`.
`" > ".join()` ожидает итерируемое из строк — падает.

### Реальная форма API

```json
"breadcrumbs": [
  {"url": "/itsm365-hr/settings", "title": [{"type": "highlight", "text": "Настройки"}]},
  {"url": "/itsm365-hr/settings/integracii", "title": [{"type": "text", "text": "Интеграции"}]},
  {"url": "/itsm365-hr/settings/integracii/nastroyka-vx",
   "title": [{"type": "highlight", "text": "Настройка"}, {"type": "text", "text": " ВКС"}]}
]
```

### Решение и обоснование

Использовать вспомогательную функцию `_render_breadcrumb_title(title)`:

```
если title — list → вызвать _render_highlights(title), но без **bold**-маркеров
если title — str  → вернуть как есть (defensive, для обратной совместимости)
иначе             → вернуть ""
```

**Почему без bold для хлебных крошек:**
`_render_highlights` существующий форматирует highlight-фрагменты как `**text**`. В заголовке
результата это уместно — подсвечивает поисковое совпадение. В строке пути (`📂 Каталог > Настройки > Интеграции`) bold делает строку визуально шумной и мешает читать структуру. Хлебные крошки несут навигационную функцию, не поисковую — bold там семантически неверен.

**Реализация:** отдельная приватная функция `_render_breadcrumb_title(title: list[dict] | str) -> str`
рендерит только plain text (игнорирует тип фрагмента, конкатенирует `item.get("text", "")`).

**Defensive:** если `title` пришёл строкой (устаревший или другой endpoint) — вернуть строку
напрямую без падения.

### Ожидаемый формат строки пути

```
📂 ITSM 365 — HR > Настройки > Интеграции > Настройка ВКС
```

Никаких `**...**` внутри строки пути. Фрагменты разных типов конкатенируются как plain text.

## BUG-2: properties — ключ `id`, а не `name`

### Симптом

`KeyError: 'name'`

Строка `formatters.py:129`:
```python
props_str = " | ".join(f"{p['name']}: {', '.join(p['value'])}" for p in properties)
```

Реальный API возвращает `{"id": "HR", "value": ["yes"]}` — ключа `name` нет.

### Реальная форма API

```json
"properties": [
  {"id": "HR", "value": ["yes"]},
  {"id": "Projects", "value": ["yes"]},
  {"id": "Support", "value": ["yes"]}
]
```

### Решение

Заменить `p['name']` на `p.get('id') or p.get('name', '?')`:
- Сначала смотрим `id` (реальный API).
- Fallback на `name` (не падаем на старых форматах).
- Если оба отсутствуют — `'?'` как явный индикатор.

Защитить `value`: `p.get('value')` может быть `None` или не-список.
Безопасное получение: `v = p.get('value', [])`, затем `', '.join(v) if isinstance(v, list) else str(v)`.

### Ожидаемый формат строки properties

```
🏷️ HR: yes | Projects: yes | Support: yes
```

## Вопрос о block-сниппетах (зафиксированное решение)

Реальный API содержит в `items` элементы `type: "block"` с вложенными paragraph:

```json
{"type": "block", "order": 1, "title": [...], "items": [
  {"type": "paragraph", "order": 0, "items": [...], "score": 88.36}
], "score": 230.4}
```

Текущий `_render_snippet` берёт только верхнеуровневые paragraph.

**Решение: не менять в этом PR.** Обоснование:
1. Текущий сниппет из верхнеуровневого paragraph уже несёт полезный контекст (первый абзац статьи).
2. Заглядывание в block добавляет сложность логики выбора сниппета (по score? по порядку?).
3. Это улучшение, не bugfix — не меняет работоспособность инструмента.
4. Отдельная задача при необходимости.

## Изменения по модулям

| Модуль | Что меняется |
|--------|--------------|
| `src/gramax_docportal_mcp/formatters.py` | Новая приватная функция `_render_breadcrumb_title`; рефакторинг строк 115-118 (BUG-1); рефакторинг строк 128-129 (BUG-2) |
| `tests/fixtures/search_response.json` | Новый файл — реальная форма ответа API (3 результата, анонимизировано) |
| `tests/test_formatters.py` | Новые тесты в классе `TestFormatSearchResults` + тест `test_format_search_results_real_fixture` |

`server.py`, `client.py`, `config.py` — не затрагиваются.

## Edge cases / boundary conditions

- `breadcrumbs[].title` — список: конкатенируется как plain text, нет bold → **ожидаемо**
- `breadcrumbs[].title` — строка (обратная совместимость): возвращается as-is → **не падает**
- `breadcrumbs[].title` — отсутствует или `None`: возвращается `""`, элемент фильтруется из пути → **ожидаемо**
- `breadcrumbs = []`: путь содержит только название каталога → **ожидаемо**
- `catalog = {}` и `breadcrumbs = []`: путь пуст, строка `📂` не отображается → **ожидаемо** (уже так)
- `properties[].id` присутствует, `name` отсутствует → читает `id` → **ожидаемо**
- `properties[].name` присутствует, `id` отсутствует → читает `name` (fallback) → **не падает**
- `properties[].value` — `None` или отсутствует → `""` вместо join → **не падает**
- `properties[].value` — не список (например, строка) → `str(v)` → **не падает**
- `properties = []`: строка `🏷️` не отображается → **ожидаемо** (уже так)
- `title` результата — список с single highlight: `**текст**` → **ожидаемо**
- Breadcrumb title с несколькими фрагментами разных типов: конкатенируются без разделителя → **ожидаемо** (пример: `[{highlight,"Настройка"},{text," ВКС"}]` → `"Настройка ВКС"`)

## Контрактная фикстура

Файл: `tests/fixtures/search_response.json`

Три результата, покрывающие все edge cases:

**Результат 1** — breadcrumbs как списки + properties с `id`, есть items (paragraph + block):
```json
{
  "type": "article",
  "isRecommended": false,
  "catalog": {"name": "demo-catalog", "title": "Demo Catalog", "url": "/demo-catalog"},
  "title": [{"type": "highlight", "text": "Настройка"}, {"type": "text", "text": " интеграции"}],
  "url": "/demo-catalog/settings/setup",
  "breadcrumbs": [
    {"url": "/demo-catalog/settings", "title": [{"type": "highlight", "text": "Настройки"}]},
    {"url": "/demo-catalog/settings/integrations", "title": [{"type": "text", "text": "Интеграции"}]},
    {"url": "/demo-catalog/settings/integrations/setup",
     "title": [{"type": "highlight", "text": "Настройка"}, {"type": "text", "text": " ВКС"}]}
  ],
  "properties": [{"id": "Category", "value": ["setup"]}, {"id": "Feature", "value": ["integration"]}],
  "items": [
    {"type": "paragraph", "order": 0,
     "items": [{"type": "highlight", "text": "Настройка"}, {"type": "text", "text": " выполняется через раздел"}],
     "score": 171.04},
    {"type": "block", "order": 1, "title": [{"type": "text", "text": "Примечание"}],
     "items": [{"type": "paragraph", "order": 0,
                "items": [{"type": "text", "text": "Текст внутри блока"}], "score": 88.36}],
     "score": 230.4}
  ]
}
```

**Результат 2** — `isRecommended: true`, пустые `breadcrumbs`, многозначные `properties`:
```json
{
  "type": "article",
  "isRecommended": true,
  "catalog": {"name": "demo-catalog", "title": "Demo Catalog", "url": "/demo-catalog"},
  "title": [{"type": "text", "text": "Обзор продукта"}],
  "url": "/demo-catalog/overview",
  "breadcrumbs": [],
  "properties": [{"id": "Product", "value": ["alpha", "beta"]}, {"id": "Segment", "value": []}],
  "items": []
}
```

**Результат 3** — пустые `breadcrumbs`, пустые `properties`, breadcrumb title как строка
(defensive, для обратной совместимости):
```json
{
  "type": "article",
  "isRecommended": false,
  "catalog": {"name": "demo-catalog", "title": "Demo Catalog", "url": "/demo-catalog"},
  "title": [{"type": "text", "text": "Устаревший формат"}],
  "url": "/demo-catalog/legacy",
  "breadcrumbs": [
    {"url": "/demo-catalog/section", "title": "Раздел"}
  ],
  "properties": [],
  "items": [
    {"type": "paragraph", "order": 0,
     "items": [{"type": "text", "text": "Текст устаревшей статьи"}],
     "score": 50.0}
  ]
}
```

## Acceptance criteria

- [ ] AC-1: вызов `format_search_results` с реальным API-payload (breadcrumbs как списки) не бросает исключений
- [ ] AC-2: строка пути содержит plain text без `**bold**` маркеров: `📂 Demo Catalog > Настройки > Интеграции > Настройка ВКС`
- [ ] AC-3: строка пути включает название каталога как первый элемент
- [ ] AC-4: при пустом `breadcrumbs = []` строка пути содержит только название каталога
- [ ] AC-5: при `breadcrumbs[].title` — строка (defensive) функция возвращает строку без падения
- [ ] AC-6: `properties` с ключом `id` (без `name`) отображаются как `🏷️ Category: setup | Feature: integration`
- [ ] AC-7: `properties` с пустым `value: []` отображаются как `🏷️ Segment: ` (пустая строка значения) и не падают
- [ ] AC-8: `properties = []` — строка `🏷️` не отображается в выводе
- [ ] AC-9: `isRecommended: true` → заголовок начинается с `⭐ ` (существующее поведение не сломано)
- [ ] AC-10: сниппет берётся из первого верхнеуровневого paragraph (block-элементы игнорируются — зафиксированное решение)
- [ ] AC-11: `uv run pytest tests/test_formatters.py -v` — все тесты зелёные (включая новые)
- [ ] AC-12: `uv run ruff check .` — без ошибок
- [ ] AC-13: `uv run mypy src/` — без новых ошибок

## Бриф для Dev

**Порядок реализации:**

1. **Фикстура** — создать `tests/fixtures/search_response.json` по описанию выше (3 результата)
2. **Тесты** — добавить в `tests/test_formatters.py`:
   - `test_format_search_results_real_fixture` — загружает фикстуру, вызывает `format_search_results`, проверяет AC-1..AC-10
   - `test_breadcrumb_title_as_list` — изолированный тест `_render_breadcrumb_title` для AC-2, AC-5
   - `test_properties_id_key` — изолированный тест для AC-6..AC-8
   - Убедиться, что новые тесты **падают** на текущем коде (TDD red)
3. **Реализация** — исправить `formatters.py`:
   - Добавить `_render_breadcrumb_title(title: list[dict] | str) -> str`
   - Заменить строки 115-118 (BUG-1)
   - Заменить строки 128-129 (BUG-2)
4. **Верификация** — убедиться, что все тесты зелёные

**Команды проверки:**
- `uv run pytest tests/test_formatters.py -v` (новые + регрессия)
- `uv run pytest` (полный suite — без регрессий)
- `uv run ruff check .`
- `uv run mypy src/`

**Не делай без спросу:**
- Изменение сигнатуры `gramax_search` и других публичных инструментов
- Рефакторинг `_render_snippet` для block-сниппетов (отдельная задача)
- Изменение поведения bold в `_render_highlights` (используется для title результата — там bold остаётся)

## Открытые вопросы

- Нет. Все дизайн-решения зафиксированы выше.
