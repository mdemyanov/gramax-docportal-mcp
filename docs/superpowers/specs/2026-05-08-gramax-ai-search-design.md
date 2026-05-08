# Gramax AI Search — Design Spec

**Date:** 2026-05-08
**Status:** Approved (brainstormed)
**Owner:** PM → SA → Dev

## Цель

Добавить MCP-инструмент `gramax_ai_search`, который превращает естественно-языковой вопрос в связный ответ ассистента Gramax (RAG) с inline-ссылками на статьи-источники. Пользователь Claude Desktop / Code должен получать ответ напрямую, а LLM-агент при необходимости — углубляться в статьи через `gramax_get_article`.

Текущий `gramax_search` остаётся без изменений: он возвращает список статей; новый инструмент возвращает сгенерированный AI-ответ.

## Контекст

Gramax Doc Portal предоставляет эндпоинт `/api/search/chat`, который:
- принимает вопрос + контекст каталога/языков/текущей статьи как query-параметры;
- возвращает streaming `application/x-ndjson`, где каждая строка — `{"type":"text","text":"..."}`;
- встраивает в текст маркеры цитат, разделённые невидимыми символами Unicode (zero-width space + word joiner / invisible separator), формат: `<ZW>CIT<ZW>N<ZW><catalog>/<article_path><ZW><relative_path><ZW><ZW>`;
- может генерировать ответ десятки секунд (LLM на стороне Gramax).

Существующий `client.GramaxClient` использует общий `httpx.AsyncClient(timeout=30.0)` — для chat этого мало.

## API Reference (новый эндпоинт)

```
GET /api/search/chat
  ?query=<str>
  &catalogName=<str>
  &articlesLanguage=<lang_code>
  &responseLanguage=<lang_code>
  &currentArticle=<catalog_id/article_path>

Headers:
  Authorization: Bearer <token>
  Accept: application/x-ndjson

Response: 200 OK, Content-Type: application/x-ndjson
  Тело — NDJSON, по строке на чанк:
    {"type":"text","text":"<chunk>"}
  В text-чанках встречаются маркеры цитат (см. ниже).
```

Пример ответа (фрагмент после декодирования NDJSON, текст склеен):

```
## Что такое ITSM
- ITSM​⁠CIT⁠1⁠commercial-knowlage/90-knowledge-base/glossary⁠./../../90-knowledge-base/glossary.md⁠⁠​ — управление IT-услугами…
- На платформе Naumen SMP реализованы решения ITSM 365​⁠CIT⁠2⁠commercial-knowlage/10-products/itsm-365/support⁠./...⁠⁠​:
  - **ITSM 365 Support** — сервис-деск…
```

## Контракт MCP-инструмента

```python
@mcp.tool()
async def gramax_ai_search(
    ctx: Context,
    query: str,
    catalog_name: str | None = None,
    articles_language: str | None = None,
    response_language: str | None = None,
    current_article: str | None = None,
) -> str:
    """AI-поиск по документации Gramax: связный ответ с ссылками на источники.

    Использовать для вопросов в свободной форме, когда нужен сгенерированный
    ответ, а не список релевантных статей. Для списка результатов —
    gramax_search.

    Args:
        query: Вопрос на естественном языке.
        catalog_name: Имя каталога для контекста (без него — по всем).
        articles_language: Язык статей в индексе ("ru", "en", ...). Default — из env.
        response_language: Язык генерируемого ответа. Default — из env.
        current_article: ID текущей статьи как контекст ("catalog_id/path").
    """
```

**Возвращает:** Markdown следующей структуры:

```markdown
<основной_текст_с_inline_цитатами_[N](full_id)>

## Источники

1. `<full_id>`
   <base_url>/<full_id>
2. ...
```

Где `full_id` — строка вида `catalog_id/article_path` (как её отдаёт сам Gramax внутри CIT-маркера; cм. формат маркера ниже). При пустом теле / отсутствии цитат блок `## Источники` опускается.

> **Note для DEV:** Gramax в CIT-маркере отдаёт article-path **без расширения `.md`**, тогда как `gramax_get_article` принимает `article_id` как есть. Перед коммитом проверить на реальной фикстуре, кликается ли URL вида `<base_url>/<full_id>` в Gramax UI; если требуется `.md`-суффикс — добавить его в `format_ai_answer`. Решение принимается на стадии DEV-001 после получения реального ответа.

### Параметры — мэппинг на API

| MCP-параметр         | Query-param      | Default                                  |
|----------------------|------------------|------------------------------------------|
| `query`              | `query`          | — (обязательный, валидация на пустоту)   |
| `catalog_name`       | `catalogName`    | пропускается, если `None`                |
| `articles_language`  | `articlesLanguage` | `Settings.gramax_ai_articles_language` |
| `response_language`  | `responseLanguage` | `Settings.gramax_ai_response_language` |
| `current_article`    | `currentArticle` | пропускается, если `None`                |

### Ошибки

- `query.strip() == ""` → `"Ошибка: поисковый запрос не может быть пустым."` (без HTTP-вызова).
- 401/403 → `GramaxAuthError` → русское сообщение про токен (как у других tools).
- 404 → `GramaxNotFoundError` → `"Каталог не найден: <catalog_name>"` (если `catalogName` задан).
- `httpx.ReadTimeout` / `httpx.TimeoutException` → `"Превышено время ожидания AI-ответа (<N>s). Попробуйте сузить запрос или увеличить GRAMAX_AI_TIMEOUT."`
- Прерывание стрима / разрыв соединения (`httpx.RemoteProtocolError`, `httpx.ReadError`) → возвращаем накопленную часть + парсинг цитат + пометку в конце: `_(ответ оборван: соединение разорвано)_`.
- Невалидный JSON в строке стрима — пропускаем строку, продолжаем читать (защита от мусора, не валим весь ответ).

## Архитектура

Расширяем существующие 4 модуля без введения новых файлов.

```
server.py      + gramax_ai_search(...)
client.py      + GramaxClient.ai_search(...) — async generator чанков
formatters.py  + parse_chat_stream() + format_ai_answer()
config.py      + gramax_ai_timeout, gramax_ai_articles_language, gramax_ai_response_language
```

### config.py

```python
class Settings(BaseSettings):
    gramax_base_url: str
    gramax_api_token: str
    gramax_ai_timeout: float = 120.0
    gramax_ai_articles_language: str = "ru"
    gramax_ai_response_language: str = "ru"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

Env-переменные: `GRAMAX_AI_TIMEOUT`, `GRAMAX_AI_ARTICLES_LANGUAGE`, `GRAMAX_AI_RESPONSE_LANGUAGE`.

### client.py

```python
async def ai_search(
    self,
    query: str,
    *,
    catalog_name: str | None = None,
    articles_language: str | None = None,
    response_language: str | None = None,
    current_article: str | None = None,
    timeout: float = 120.0,
) -> AsyncIterator[str]:
    """Yield text chunks from /api/search/chat NDJSON stream."""
    params = {"query": query}
    if catalog_name is not None:
        params["catalogName"] = catalog_name
    if articles_language is not None:
        params["articlesLanguage"] = articles_language
    if response_language is not None:
        params["responseLanguage"] = response_language
    if current_article is not None:
        params["currentArticle"] = current_article

    async with self._client.stream(
        "GET", "/api/search/chat",
        params=params,
        timeout=timeout,
    ) as response:
        self._check_response(response, f"AI-поиск '{query}'")
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "text":
                text = obj.get("text", "")
                if text:
                    yield text
```

Замечание: `_check_response` для streaming — вызываем после получения headers, до чтения тела. У httpx headers доступны до итерации `aiter_lines()`.

### formatters.py

#### Парсер CIT-маркеров

Маркеры используют невидимые Unicode-символы как разделители. Точные коды извлекаются из эталонной фикстуры (см. «Тестовая фикстура» ниже) — код парсера пишем по фикстуре, не по гипотезам.

Обобщённый формат маркера:
```
<ZWSP><SEP>CIT<SEP><N><SEP><catalog>/<article_path><SEP><relative_path><SEP><SEP><ZWSP>
```

Алгоритм:
1. Накопить все text-чанки в одну строку `raw`.
2. Регулярное выражение по точным разделителям выделяет все маркеры:
   ```
   pattern = re.compile(
       f"{ZWSP}{SEP}CIT{SEP}(\\d+){SEP}([^{SEP}]+){SEP}([^{SEP}]+){SEP}{SEP}{ZWSP}"
   )
   ```
3. Каждое совпадение → запись `(N: int, full_id: str)`, где `full_id = "catalog_id/article_path"`.
4. Заменить совпадения в тексте на `[N](full_id)`.
5. Дедупликация: если один и тот же `full_id` встречается с разными `N` — оставляем первое попадание; в ответе все вхождения мапятся в одну запись блока «Источники» (но inline-номера остаются как отдают сами Gramax).

```python
class Citation(TypedDict):
    n: int       # номер цитаты как его проставил Gramax (1, 2, 3, ...)
    full_id: str # "catalog_id/article_path" — как в CIT-маркере, дальше идёт в URL и в gramax_get_article (после возможной нормализации с .md)


def parse_chat_stream(chunks: list[str]) -> dict:
    """Concatenate chunks and extract citations.

    Returns:
        {"text": str, "citations": list[Citation]}
    """
```

В replace используем `full_id` единым, не разделяем на `catalog_id` и `article_path` — это упрощает и парсер, и форматтер. Если в будущем понадобится разделение для других tools, оно делается тривиально через `full_id.split("/", 1)`.

#### Сборка финального ответа

```python
def format_ai_answer(parsed: dict, base_url: str) -> str:
    """Render parsed AI answer with Sources block."""
```

Логика:
- Если `parsed["text"].strip() == ""` → `"AI не сгенерировал ответ."`.
- Если цитат нет — вернуть текст без блока «Источники».
- Иначе:
  ```
  <text>

  ## Источники

  N. `<full_id>`
     <base_url>/<full_id>
  ```
  Каждая уникальная пара `(N, full_id)` — одна строка. Сортировка по `N` возрастанию. Если разные `N` указывают на один `full_id` — это нормально, оставляем как есть (иначе нарушится соответствие inline-номера со строкой «Источников»). Стоимость дубля строки в блоке «Источники» ниже стоимости развалившегося маппинга.

### server.py

```python
@mcp.tool()
async def gramax_ai_search(ctx: Context, query: str, ...) -> str:
    if not query or not query.strip():
        return "Ошибка: поисковый запрос не может быть пустым."
    try:
        client: GramaxClient = ctx.lifespan_context["client"]
        base_url: str = ctx.lifespan_context["base_url"]
        settings: Settings = ctx.lifespan_context["settings"]

        chunks: list[str] = []
        async for chunk in client.ai_search(
            query,
            catalog_name=catalog_name,
            articles_language=articles_language or settings.gramax_ai_articles_language,
            response_language=response_language or settings.gramax_ai_response_language,
            current_article=current_article,
            timeout=settings.gramax_ai_timeout,
        ):
            chunks.append(chunk)
            await ctx.report_progress(progress=len(chunks))

        parsed = parse_chat_stream(chunks)
        return format_ai_answer(parsed, base_url)
    except GramaxError as e:
        return str(e)
    except httpx.TimeoutException:
        return (
            f"Превышено время ожидания AI-ответа "
            f"({settings.gramax_ai_timeout:.0f}s). "
            "Попробуйте сузить запрос или увеличить GRAMAX_AI_TIMEOUT."
        )
```

`app_lifespan` теперь кладёт в `lifespan_context` ещё и `settings` (используется только новым tool, остальные не трогаем):

```python
yield {"client": client, "base_url": base_url, "settings": settings}
```

## Поток данных

```
Claude → MCP gramax_ai_search(query, ...)
   ↓
server.py: валидация → client.ai_search() (async generator)
   ↓
client.py: httpx.stream(GET /api/search/chat) → aiter_lines() → json.loads → yield text
   ↓
server.py: накопление chunks[] + ctx.report_progress(N)
   ↓
formatters.parse_chat_stream(chunks) → {"text": ..., "citations": [...]}
   ↓
formatters.format_ai_answer(parsed, base_url) → markdown
   ↓
return → Claude
```

## Тестирование (TDD)

### Тестовая фикстура

В `tests/fixtures/ai_search_response.ndjson` сохранить эталонный декодированный ответ из примера, предоставленного PM (base64 → NDJSON). Эта фикстура — источник истины для парсера: точные коды zero-width разделителей и формат маркера извлекаются из неё, не из гипотез о Unicode.

### test_config.py

- `gramax_ai_timeout` дефолт = 120.0
- `gramax_ai_articles_language` дефолт = "ru"
- `gramax_ai_response_language` дефолт = "ru"
- env-override работает (`GRAMAX_AI_TIMEOUT=60` → 60.0)

### test_client.py

Через `pytest-httpx`:
- happy path: GET с правильными query-params, получаем NDJSON фикстуру → yield-ит ожидаемые text-чанки в порядке.
- передача всех опциональных параметров формирует правильный URL.
- 401 → `GramaxAuthError`; 404 → `GramaxNotFoundError`.
- невалидная JSON-строка в потоке — пропускается, остальные чанки yield-ятся.
- пустой стрим — возвращает 0 чанков без ошибки.
- timeout прокидывается в `httpx.stream(..., timeout=...)`.

### test_formatters.py

- `parse_chat_stream(["a", "b", "c"])` → `{"text": "abc", "citations": []}`.
- `parse_chat_stream(<chunks с CIT-маркером>)` → корректно извлекает `(N, catalog_id, article_id)`, заменяет на `[N](article_id)`.
- маркер на стыке двух чанков (склеивается после concat) — обрабатывается корректно.
- два вхождения с одинаковым `(N, full_id)` — две inline-ссылки в теле, **одна** строка в «Источниках»; разные `N` к одному `full_id` — две строки в «Источниках» (соответствие inline-номера ↔ строки сохраняется).
- маркеров нет → `citations == []`.
- `format_ai_answer({"text": "", "citations": []}, base_url)` → `"AI не сгенерировал ответ."`.
- цитаты есть → блок `## Источники` присутствует, URL правильный.
- цитат нет → блок «Источники» отсутствует.

### test_server.py

Через мок `GramaxClient.ai_search`:
- happy path: вернёт ожидаемый markdown с inline-ссылками и блоком «Источники».
- пустой query → строка-ошибка без HTTP-вызова.
- `httpx.ReadTimeout` → русское сообщение про timeout.
- `GramaxAuthError` пробрасывается → русское сообщение про токен.
- `ctx.report_progress` вызывается ровно `len(chunks)` раз.

## Нефункциональные требования

| Аспект        | Требование                                                                 |
|---------------|----------------------------------------------------------------------------|
| Timeout       | 120s default, настраиваемый через env                                      |
| Конкурентность| Один stream на инструмент-вызов; никакого пула                             |
| Память        | Аккумуляция всего ответа в `list[str]` — допустимо (ответ < 100 КБ)        |
| Логи          | По умолчанию никаких (как и в существующих tools)                          |
| Зависимости   | Без новых: `httpx.stream` уже есть, `json.loads` стандартный               |

## Совместимость и версионирование

- Новый MCP-инструмент → **minor bump**: `pyproject.toml` `version = "0.3.0"`.
- Существующие tools не меняются, breaking-change нет.
- Lifespan-контракт расширяется ключом `settings` — внутреннее изменение, на публичные tools не влияет.

## Связанные документы

- ADR-0001: Streaming AI tool — accumulate vs progress vs streaming-resource.
- Базовая спека: `docs/superpowers/specs/2026-04-06-gramax-mcp-design.md`.

## Acceptance Criteria

1. `uv run pytest` — все новые тесты зелёные, существующие не сломаны.
2. `uv run ruff check .` — без ошибок.
3. Ручная проверка через MCP-клиент:
   - вызов `gramax_ai_search(query="Что такое ITSM", catalog_name="commercial-knowlage")` возвращает markdown с inline-ссылками `[N](...)` и блоком «Источники»;
   - таймаут 5s в env даёт русское сообщение об ошибке;
   - пустой `query` даёт русскую ошибку валидации без HTTP.
4. Версия в `pyproject.toml` = `0.3.0`, в commit message bump-rationale.
5. ADR-0001 переведён в `Status: Accepted`.
