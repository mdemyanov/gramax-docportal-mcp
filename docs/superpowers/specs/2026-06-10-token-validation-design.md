# Опциональный токен / Анонимный режим — Design Spec (BUG-4)

**Дата:** 2026-06-10
**Статус:** Approved (review)
**Тип:** Bugfix / PATCH-релиз
**BUG-трекер:** BUG-4

## Контекст

Live-тест против https://knowledge.nau.im выявил два взаимосвязанных сценария:

1. **Crash при пустом токене.** Если `GRAMAX_API_TOKEN=""` (пустая строка), pydantic-settings
   принимает значение как валидное (тип `str`). Клиент формирует заголовок `"Bearer "` — httpx
   бросает `LocalProtocolError: Illegal header value b'Bearer '`. Ошибка не перехватывается
   `GramaxError` и утекает к MCP-клиенту как необработанный traceback.

2. **Реальный портал публичный.** https://knowledge.nau.im отдаёт 200 без токена авторизации.
   При этом невалидный или просроченный токен даёт 401 даже на публичные эндпоинты. Токен
   получается через браузерную сессию (`GET /api/user/token`), автообновления нет. Пользователи
   без токена обязаны были задавать `GRAMAX_API_TOKEN=""` — и немедленно ловили crash.

Переменная задекларирована в `config.py` как `gramax_api_token: str` (обязательная).
Это противоречит реальному использованию портала.

## Цель

Сделать токен опциональным: если не задан или задан пустой строкой/whitespace —
заголовок `Authorization` не отправляется (анонимный режим). Пользователи с валидным
токеном не замечают изменения. Crash при пустом токене устранён.

## Контракт MCP-инструмента

| Поле | Значение |
|------|----------|
| Имена | `gramax_search`, `gramax_get_article`, `gramax_list_catalogs`, `gramax_get_navigation`, `gramax_ai_search` — все без изменений |
| Параметры | без изменений |
| Возвращает | без изменений |
| Ошибки | без изменений (401 от сервера уже покрыт BUG-3 HTTP-error-handling) |
| Совместимость | PATCH-релиз; ослабление требования к окружению, breaking change отсутствует |

Сигнатуры всех публичных инструментов `gramax_*` **не меняются**.

## Изменения по модулям

| Модуль | Что меняется |
|--------|--------------|
| `config.py` | `gramax_api_token: str` → `gramax_api_token: str \| None = None`; добавить `@field_validator` для нормализации (пустая строка / whitespace → `None`, непустая строка — strip) |
| `client.py` | Сигнатура `__init__`: `api_token: str` → `api_token: str \| None`; заголовок `Authorization` добавляется только если `api_token` непустой |
| `server.py` | Передача `settings.gramax_api_token` в `GramaxClient` остаётся; тип расширяется до `str \| None` — структурных изменений нет |
| `README.md` | Столбец «Обязательно» для `GRAMAX_API_TOKEN`: `Да` → `Нет`; уточнить описание и добавить заметку про публичные порталы |

`formatters.py` — не затрагивается.

## Детальный дизайн

### config.py

```python
gramax_api_token: str | None = None

@field_validator("gramax_api_token", mode="before")
@classmethod
def _normalize_token(cls, v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None
```

Поведение по значению:
- `GRAMAX_API_TOKEN` не задан → `None`
- `GRAMAX_API_TOKEN=""` → `None`
- `GRAMAX_API_TOKEN="   "` → `None`
- `GRAMAX_API_TOKEN=" abc123 "` → `"abc123"`
- `GRAMAX_API_TOKEN="abc123"` → `"abc123"`

### client.py

```python
def __init__(self, base_url: str, api_token: str | None) -> None:
    headers: dict[str, str] = {}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    self._client = httpx.AsyncClient(
        base_url=base_url, headers=headers, timeout=30.0
    )
```

Если `api_token` равен `None` или пустой строке (defensive) — заголовок не добавляется.

### server.py

Lifespan передаёт `settings.gramax_api_token` (тип `str | None`) — без изменений в логике.

## Edge cases / boundary conditions

- `api_token=None` → нет заголовка `Authorization`, запрос уходит как анонимный → **ожидаемо**
- `api_token=""` → нет заголовка (defensive на уровне клиента, дублирует логику config) → **не падает**
- `api_token="  "` (только whitespace) → `_normalize_token` возвращает `None` → нет заголовка → **ожидаемо**
- `api_token=" abc123 "` → strip → `"abc123"` → заголовок `Bearer abc123` → **ожидаемо**
- `api_token="valid_token"` → заголовок `Bearer valid_token` → поведение без изменений → **не сломано**
- Портал вернул 401 при анонимном запросе → уже обрабатывается BUG-3 (`GramaxError` с русским сообщением)

## Acceptance criteria

- [ ] AC-1: `Settings()` без переменной `GRAMAX_API_TOKEN` в окружении не бросает исключения; `settings.gramax_api_token is None`
- [ ] AC-2: `Settings(gramax_api_token="")` → `gramax_api_token is None`; `Settings(gramax_api_token="   ")` → `gramax_api_token is None`
- [ ] AC-3: `Settings(gramax_api_token=" abc123 ")` → `gramax_api_token == "abc123"`
- [ ] AC-4: `GramaxClient(base_url=..., api_token=None)` — httpx-клиент не содержит заголовка `Authorization`, запросы выполняются без исключений
- [ ] AC-5: `GramaxClient(base_url=..., api_token="")` — аналогично AC-4 (defensive)
- [ ] AC-6: `GramaxClient(base_url=..., api_token="valid")` — заголовок `Authorization: Bearer valid` присутствует (регрессия)
- [ ] AC-7: `README.md` обновлён: `GRAMAX_API_TOKEN` помечен как необязательный, добавлена заметка про публичные порталы
- [ ] AC-8: `uv run pytest` — все тесты зелёные без регрессий; `uv run ruff check .` — без ошибок; `uv run mypy src/` — без новых ошибок
- [ ] AC-9: сигнатуры всех инструментов `gramax_*` не изменены

## Бриф для Dev

**Порядок реализации:**

1. **Тесты `tests/test_config.py`**
   - Переименовать `test_settings_requires_api_token` → `test_settings_token_optional_when_absent`
     (assert `settings.gramax_api_token is None`, без проверки на исключение)
   - Добавить: `test_settings_token_empty_string_normalizes_to_none` (AC-2)
   - Добавить: `test_settings_token_whitespace_normalizes_to_none` (AC-2)
   - Добавить: `test_settings_token_strips_whitespace` (AC-3)
   - Убедиться, что новые тесты **падают** на текущем коде (TDD red)

2. **Тесты `tests/test_client.py`**
   - Добавить `test_list_catalogs_anonymous`: `GramaxClient(api_token=None)` — в перехваченном
     httpx-запросе отсутствует заголовок `authorization` (AC-4)
   - Добавить `test_empty_string_token_no_header`: `GramaxClient(api_token="")` — аналогично (AC-5)
   - Существующие тесты с непустым токеном — не трогать (AC-6 / AC-8 регрессия)

3. **Реализация `config.py`** — изменить тип и добавить валидатор (AC-1..AC-3)

4. **Реализация `client.py`** — изменить сигнатуру `__init__` и логику заголовка (AC-4..AC-6)

5. **`README.md`** — обновить таблицу переменных и раздел про получение токена (AC-7)

6. **Верификация** — убедиться, что все тесты зелёные

**Команды проверки:**
- `uv run pytest tests/test_config.py tests/test_client.py -v`
- `uv run pytest` (полный suite — без регрессий)
- `uv run ruff check .`
- `uv run mypy src/`

**Не делай без спросу:**
- Изменение сигнатур публичных инструментов `gramax_*`
- Добавление нового middleware аутентификации или рефакторинг `GramaxClient` под DI
- Изменение поведения BUG-3 HTTP-error-handling (отдельная задача)

## Открытые вопросы

- Нет. Все дизайн-решения зафиксированы выше. ADR-0002 документирует выбор между вариантами.
