# gramax-docportal-mcp

MCP-сервер для доступа к порталу документации [Gramax](https://gram.ax). Позволяет искать статьи, получать контент и навигацию через Claude и другие LLM.

## Инструменты

| Инструмент | Описание |
|-----------|----------|
| `gramax_list_catalogs` | Список всех каталогов документации |
| `gramax_get_navigation` | Дерево навигации каталога |
| `gramax_search` | Поиск по статьям (фильтры по свойствам, языку, семантический поиск) |
| `gramax_get_article` | Содержимое статьи в Markdown |

## Установка

```bash
uv tool install gramax-docportal-mcp
```

## Настройка

Добавьте в `.mcp.json`:

```json
{
  "mcpServers": {
    "gramax": {
      "command": "uvx",
      "args": ["gramax-docportal-mcp"],
      "env": {
        "GRAMAX_BASE_URL": "https://your-portal.example.com",
        "GRAMAX_API_TOKEN": "ваш-api-токен"
      }
    }
  }
}
```

### Получение токена

Откройте в браузере (будучи залогиненным на портале):

```
https://your-portal.example.com/api/user/token
```

Токен действует 30 дней. Для кастомного срока:

```
https://your-portal.example.com/api/user/token?expiresAt=2026-12-31
```

## Переменные окружения

| Переменная | Описание | Обязательно |
|-----------|----------|:-----------:|
| `GRAMAX_BASE_URL` | URL портала документации | Да |
| `GRAMAX_API_TOKEN` | API-токен (Bearer) | Да |

## Расширенный поиск

`gramax_search` поддерживает дополнительные параметры для точной фильтрации:

| Параметр | Описание |
|----------|----------|
| `catalog_name` | Ограничить поиск одним каталогом |
| `search_type` | `"vector"` — семантический поиск (по умолчанию — полнотекстовый) |
| `language` | Язык статей: `"ru"`, `"en"`, `"de"`, `"zh"` и др. |
| `resource_filter` | `"without"` — только статьи, `"only"` — только файлы |
| `property_filter` | Фильтр по свойствам статей (Продукт, Сегмент, Отрасль и др.) |

### Примеры property_filter

```json
{"op": "eq", "key": "Продукт", "value": "NSD"}

{"op": "contains", "key": "Сегмент", "list": ["Enterprise", "SMB"]}

{"op": "and", "filters": [
  {"op": "eq", "key": "Тип контента", "value": "Кейс"},
  {"op": "eq", "key": "Отрасль", "value": "Логистика"}
]}
```

В результатах поиска отображаются метаданные статей (🏷️) и рекомендованные результаты (⭐).

## Лицензия

MIT
