# HTTP Error Handling — Design Spec (BUG-3)

**Дата:** 2026-06-10
**Статус:** Approved (review)
**Тип:** Bugfix / PATCH-релиз
**BUG-трекер:** BUG-3

## Контекст

Live-тест против https://knowledge.nau.im выявил, что `GET /api/search/searchCommand?type=vector`
возвращает HTTP 500. В этой ситуации MCP-клиент получает необработанный английский traceback
вместо русского сообщения, потому что `httpx.HTTPStatusError` (бросаемый
`response.raise_for_status()`) не является подклассом `GramaxError` и пролетает мимо
`except GramaxError` во всех пяти инструментах.

Та же категория дыр затрагивает:

- Сетевые ошибки (`httpx.ConnectError`, `httpx.ConnectTimeout`, DNS-fail) во всех инструментах
  кроме `gramax_ai_search` (там ловится только `httpx.TimeoutException`).
- `httpx.TimeoutException` в четырёх не-streaming инструментах (timeout=30s не ловится).
- `response.json()` при невалидном JSON-теле → `json.JSONDecodeError` утекает из `client.py`.

## Цель

Перехватить все предсказуемые HTTP/сетевые/парсинговые ошибки **в одном месте** — в
`client.py` — и превратить их в подклассы `GramaxError` с русскими сообщениями. Все пять
инструментов получают корректное поведение без изменений в `server.py`, кроме одного
точечного исправления для streaming-случая `gramax_ai_search`.

## Архитектурное решение: маппинг на уровне клиента

Альтернативы:

1. **try/except в каждом из 5 инструментов server.py** — дублирование, легко пропустить
   при добавлении нового инструмента.
2. **Централизованный маппинг в `_check_response` + новый `except` в каждом публичном методе
   `client.py`** — единая точка для HTTP-кодов плюс одно место для сетевых ошибок.
3. **Декоратор на методах `GramaxClient`** — излишняя сложность для 4 методов.

Выбран вариант 2: `_check_response` расширяется обработкой 5xx, добавляется
`_safe_json()` для `json.JSONDecodeError`, а каждый публичный метод оборачивается в
`try/except` для сетевых ошибок. Это следует принципу YAGNI и сохраняет плоскую структуру.

Решение не является архитектурно значимым (нет новых зависимостей, нет breaking change),
поэтому отдельный ADR не создаётся.

## Изменения по модулям

| Модуль | Что меняется |
|--------|--------------|
| `client.py` | Новые исключения `GramaxServerError`, `GramaxNetworkError`. Расширение `_check_response` (5xx → `GramaxServerError`). Новый метод `_safe_json()`. Обёртка публичных методов в `try/except (httpx.TimeoutException, httpx.NetworkError)` → `GramaxNetworkError`. |
| `server.py` | Без изменений в инструментах. Единственное изменение: импорт `GramaxNetworkError` не нужен — все новые исключения — подклассы `GramaxError`, которую уже ловят все инструменты. Для `gramax_ai_search`: добавить `except GramaxError` рядом с уже существующими `except httpx.TimeoutException` / `except (httpx.RemoteProtocolError, httpx.ReadError)` — они остаются для streaming-специфики (частичный ответ), но `GramaxServerError` (5xx до начала стрима) теперь тоже будет правильно перехвачен блоком `except GramaxError`. |
| `formatters.py` | Без изменений. |
| `config.py` | Без изменений. |

## Иерархия исключений (после изменений)

```
GramaxError                 # базовое исключение (уже существует)
├── GramaxAuthError         # 401, 403 (уже существует)
├── GramaxNotFoundError     # 404 (уже существует)
├── GramaxServerError       # 5xx (новое)
└── GramaxNetworkError      # таймаут, ConnectError, DNS-fail, json.JSONDecodeError (новое)
```

`GramaxServerError` и `GramaxNetworkError` экспортируются из `client.py` наравне с
существующими исключениями.

## Контракт `_check_response` (после изменений)

```python
def _check_response(self, response: httpx.Response, context: str = "") -> None:
    if response.status_code in (401, 403):
        raise GramaxAuthError(
            "Токен невалиден или истёк. Получите новый: GET /api/user/token"
        )
    if response.status_code == 404:
        raise GramaxNotFoundError(f"Ресурс не найден: {context}")
    if response.status_code >= 500:
        raise GramaxServerError(
            f"Сервер Gramax вернул ошибку {response.status_code} при запросе: {context}. "
            "Попробуйте позже или обратитесь к администратору портала."
        )
    response.raise_for_status()  # 4xx кроме 401/403/404
```

Оставшийся `response.raise_for_status()` покрывает прочие 4xx (400, 405, 429 и т.д.).
Их не заворачиваем в `GramaxError` — они сигнализируют об ошибке вызова со стороны клиента
и встречаются редко. Если в будущем понадобится — отдельный bugfix.

**Особенность streaming (`ai_search`):** при `httpx.stream(...)` заголовки приходят до тела,
поэтому `_check_response` вызывается внутри `async with self._client.stream(...)` **до**
`response.aiter_lines()` — как сделано сейчас. Для не-200 ответов httpx не читает тело
автоматически. `response.status_code` доступен сразу из заголовков, поэтому ни `aread()`,
ни `raise_for_status()` не требуют предварительного чтения тела. Текущее поведение
корректно — достаточно добавить ветку 5xx в `_check_response`.

## Контракт `_safe_json` (новый приватный метод)

```python
def _safe_json(self, response: httpx.Response, context: str = "") -> Any:
    try:
        return response.json()
    except Exception:
        raise GramaxNetworkError(
            f"Gramax вернул нечитаемый ответ при запросе: {context}. "
            "Возможно, сервер перегружен или вернул HTML вместо JSON."
        )
```

Заменяет прямой вызов `response.json()` во всех публичных методах: `list_catalogs`,
`get_navigation`, `search`. Метод `get_article_html` использует `response.text` — не меняется.

## Обёртка сетевых ошибок в публичных методах

Каждый из четырёх не-streaming методов (`list_catalogs`, `get_navigation`,
`get_article_html`, `search`) оборачивается:

```python
except httpx.TimeoutException:
    raise GramaxNetworkError(
        f"Превышено время ожидания ответа от Gramax при запросе: {context}. "
        "Проверьте доступность портала или увеличьте таймаут."
    )
except httpx.NetworkError as e:
    raise GramaxNetworkError(
        f"Не удалось подключиться к Gramax при запросе: {context}. "
        f"Проверьте сетевое подключение и адрес портала. Детали: {type(e).__name__}"
    ) from e
```

Значение `context` для каждого метода:

| Метод | context |
|-------|---------|
| `list_catalogs` | `"список каталогов"` |
| `get_navigation(catalog_id)` | `f"навигация каталога {catalog_id}"` |
| `get_article_html(catalog_id, article_id)` | `f"статья {article_id} в каталоге {catalog_id}"` |
| `search(query, ...)` | `f"поиск '{query}'"` |

Для `ai_search` — без изменений: сетевые ошибки внутри streaming-итерации уже ловятся
в `server.py` (`httpx.TimeoutException`, `httpx.RemoteProtocolError`, `httpx.ReadError`).
`httpx.ConnectError` (до начала стрима) перехватывается новой обёрткой в `ai_search`
как `GramaxNetworkError`, которую затем поймает `except GramaxError` в `server.py`.

## Русские тексты ошибок (полные)

| Класс | Ситуация | Текст сообщения |
|-------|----------|-----------------|
| `GramaxServerError` | 500 на searchCommand | `"Сервер Gramax вернул ошибку 500 при запросе: поиск 'query'. Попробуйте позже или обратитесь к администратору портала."` |
| `GramaxServerError` | 503 на get_navigation | `"Сервер Gramax вернул ошибку 503 при запросе: навигация каталога docs. Попробуйте позже или обратитесь к администратору портала."` |
| `GramaxNetworkError` | ConnectError | `"Не удалось подключиться к Gramax при запросе: список каталогов. Проверьте сетевое подключение и адрес портала. Детали: ConnectError"` |
| `GramaxNetworkError` | TimeoutException (не-stream) | `"Превышено время ожидания ответа от Gramax при запросе: статья intro в каталоге docs. Проверьте доступность портала или увеличьте таймаут."` |
| `GramaxNetworkError` | json.JSONDecodeError | `"Gramax вернул нечитаемый ответ при запросе: поиск 'query'. Возможно, сервер перегружен или вернул HTML вместо JSON."` |

## Edge Cases

- **5xx на streaming до начала тела:** `_check_response` поднимает `GramaxServerError`
  внутри `async with stream(...)` — httpx корректно закрывает соединение при выходе из
  контекстного менеджера через исключение. `server.py` ловит через `except GramaxError`.
- **ConnectError внутри `ai_search` (до stream-итерации):** поднимается до входа в
  `async with stream(...)`, попадает в новую обёртку `ai_search` → `GramaxNetworkError`
  → `except GramaxError` в `server.py`.
- **ConnectError внутри стрима (после начала чтения):** это `httpx.ReadError` /
  `httpx.RemoteProtocolError`, которые уже обрабатываются в `server.py` (частичный ответ).
  Не трогаем.
- **429 Too Many Requests:** остаётся как `httpx.HTTPStatusError` (из `raise_for_status()`).
  Не в scope этого bugfix.
- **Пустое тело 200 на JSON-эндпоинте:** `_safe_json` поднимает `GramaxNetworkError`.
- **Несколько разных 5xx кодов (501, 502, 503, 504):** все покрываются условием
  `status_code >= 500` с кодом в тексте сообщения.

## Acceptance Criteria

- [ ] AC-1: `client.search(query, search_type="vector")` при HTTP 500 бросает
  `GramaxServerError` с русским текстом, содержащим `"500"` и контекст поиска.
- [ ] AC-2: `client.search(...)` при HTTP 503 бросает `GramaxServerError` с `"503"`.
- [ ] AC-3: `client.list_catalogs()` при `httpx.ConnectError` бросает
  `GramaxNetworkError` с русским текстом.
- [ ] AC-4: `client.get_article_html(...)` при `httpx.TimeoutException` бросает
  `GramaxNetworkError` с русским текстом.
- [ ] AC-5: `client.search(...)` при невалидном JSON в теле ответа бросает
  `GramaxNetworkError` с русским текстом.
- [ ] AC-6: `client.ai_search(...)` при HTTP 500 (до начала стрима) бросает
  `GramaxServerError`, которая в `server.py gramax_ai_search` перехватывается
  блоком `except GramaxError` и возвращает русское сообщение.
- [ ] AC-7: `gramax_search(...)` при HTTP 500 возвращает русское сообщение (без traceback).
- [ ] AC-8: `gramax_list_catalogs()` при HTTP 503 возвращает русское сообщение.
- [ ] AC-9: Все существующие тесты (`uv run pytest`) проходят без изменений.
- [ ] AC-10: `uv run ruff check .` и `uv run mypy src/` без ошибок.
- [ ] AC-11: `GramaxServerError` и `GramaxNetworkError` — подклассы `GramaxError`
  (все пять инструментов ловят без изменений сигнатуры).

## Бриф для Dev

**Порядок реализации (TDD):**

1. **Fixtures** — добавить в `tests/test_client.py`:
   - мок HTTP 500 для `search` через `httpx_mock.add_response(status_code=500)`
   - мок HTTP 503 для `get_navigation`
   - мок `httpx.ConnectError` для `list_catalogs`
   - мок `httpx.TimeoutException` для `get_article_html`
   - мок 200 с невалидным JSON для `search`
   - мок HTTP 500 для `ai_search` (streaming)
2. **Исключения** — добавить `GramaxServerError` и `GramaxNetworkError` в `client.py`
   (после `GramaxNotFoundError`).
3. **`_check_response`** — добавить ветку `status_code >= 500`.
4. **`_safe_json`** — добавить приватный метод, заменить `response.json()` в
   `list_catalogs`, `get_navigation`, `search`.
5. **Обёртки сетевых ошибок** — `try/except` в `list_catalogs`, `get_navigation`,
   `get_article_html`, `search` и в начале `ai_search` (до `async with stream(...)`).
6. **Запустить тесты** — убедиться, что новые тесты зелёные, старые не сломаны.

**Важно для `ai_search`:** обёртка `try/except (httpx.TimeoutException, httpx.NetworkError)`
должна охватывать вызов `async with self._client.stream(...)` — то есть `ConnectError`
до установки соединения. Ошибки внутри итерации (`ReadError`, `RemoteProtocolError`)
уже ловятся в `server.py` и трогать их не нужно.

**Не трогай:**
- Сигнатуры публичных инструментов `gramax_*` (PATCH-релиз, breaking change недопустим).
- Обработку `httpx.TimeoutException` / `httpx.RemoteProtocolError` / `httpx.ReadError`
  в `server.py gramax_ai_search` — она специфична для streaming и остаётся.
- Разбиение модулей.

**Команды проверки:**

```bash
uv run pytest tests/test_client.py -v        # новые тесты
uv run pytest                                 # полный suite без регрессий
uv run ruff check .
uv run mypy src/
```

## Версионирование

PATCH-релиз: `0.3.x → 0.3.1` (bugfix, нет новых публичных инструментов, нет breaking change).

## Открытые вопросы

- Прочие 4xx (400, 405, 429): не в scope. Если нужно — отдельный тикет.
- Логирование ошибок (structured logging): не в scope, YAGNI.
