

class TestFormatCatalogsList:
    def test_basic_list(self):
        from gramax_docportal_mcp.formatters import format_catalogs_list

        data = {"data": [
            {"id": "docs", "title": "Gramax Docs"},
            {"id": "api-ref", "title": "API Reference"},
        ]}
        result = format_catalogs_list(data)
        assert "# Каталоги документации" in result
        assert "docs" in result
        assert "Gramax Docs" in result
        assert "api-ref" in result
        assert "API Reference" in result
        assert "Всего: 2" in result

    def test_empty_list(self):
        from gramax_docportal_mcp.formatters import format_catalogs_list

        data = {"data": []}
        result = format_catalogs_list(data)
        assert "Каталогов не найдено" in result

    def test_missing_keys_in_catalog(self):
        from gramax_docportal_mcp.formatters import format_catalogs_list

        data = {"data": [
            {"id": "docs"},  # no title
            {"title": "API Reference"},  # no id
            {},  # no keys at all
        ]}
        result = format_catalogs_list(data)
        assert "# Каталоги документации" in result
        assert "Всего: 3" in result


class TestFormatNavigation:
    def test_flat_tree(self):
        from gramax_docportal_mcp.formatters import format_navigation

        data = {"data": [
            {"id": "getting-started", "title": "Начало работы"},
            {"id": "deploy", "title": "Развёртывание"},
        ]}
        result = format_navigation("docs", data, "https://docs.example.com")
        assert "# Навигация: docs" in result
        assert "Начало работы" in result
        assert "https://docs.example.com/docs/getting-started" in result
        assert "Развёртывание" in result
        assert "https://docs.example.com/docs/deploy" in result

    def test_nested_tree(self):
        from gramax_docportal_mcp.formatters import format_navigation

        data = {"data": [
            {
                "id": "deploy",
                "title": "Развёртывание",
                "children": [
                    {"id": "deploy/docker", "title": "Docker"},
                    {"id": "deploy/k8s", "title": "Kubernetes"},
                ],
            },
        ]}
        result = format_navigation("docs", data, "https://docs.example.com")
        assert "Развёртывание" in result
        assert "  - " in result  # indented children
        assert "Docker" in result
        assert "https://docs.example.com/docs/deploy/docker" in result

    def test_empty_navigation(self):
        from gramax_docportal_mcp.formatters import format_navigation

        data = {"data": []}
        result = format_navigation("docs", data, "https://docs.example.com")
        assert "Навигация пуста" in result

    def test_missing_keys_in_nav_items(self):
        from gramax_docportal_mcp.formatters import format_navigation

        data = {"data": [
            {"title": "No ID Item"},  # no id
            {"id": "no-title"},  # no title
        ]}
        result = format_navigation("docs", data, "https://docs.example.com")
        assert "# Навигация: docs" in result
        assert "No ID Item" in result


class TestFormatSearchResults:
    def test_basic_results(self):
        from gramax_docportal_mcp.formatters import format_search_results

        results = [
            {
                "type": "article",
                "title": [
                    {"type": "highlight", "text": "Токен"},
                    {"type": "text", "text": " для API"},
                ],
                "url": "/docs/api-token",
                "breadcrumbs": [
                    {"url": "/docs/server", "title": "Сервер"},
                    {"url": "/docs/server/deploy", "title": "Развёртывание"},
                ],
                "catalog": {"name": "docs", "title": "Gramax Docs"},
                "items": [
                    {
                        "type": "paragraph",
                        "order": 0,
                        "items": [
                            {"type": "text", "text": "Используйте API-"},
                            {"type": "highlight", "text": "токен"},
                            {"type": "text", "text": "."},
                        ],
                        "score": 175,
                    },
                ],
            },
        ]
        result = format_search_results(results, "https://docs.example.com")
        assert "**Токен**" in result
        assert " для API" in result
        assert "https://docs.example.com/docs/api-token" in result
        assert "Сервер" in result
        assert "Развёртывание" in result
        assert "**токен**" in result
        assert "Найдено: 1" in result

    def test_recommended_and_properties(self):
        from gramax_docportal_mcp.formatters import format_search_results

        results = [
            {
                "type": "article",
                "isRecommended": True,
                "title": [{"type": "text", "text": "NSD"}],
                "url": "/docs/nsd",
                "breadcrumbs": [],
                "catalog": {"name": "docs", "title": "Docs"},
                "items": [],
                "properties": [
                    {"name": "Продукт", "value": ["NSD"]},
                    {"name": "Сегмент", "value": ["Enterprise"]},
                ],
            },
            {
                "type": "article",
                "isRecommended": False,
                "title": [{"type": "text", "text": "Other"}],
                "url": "/docs/other",
                "breadcrumbs": [],
                "catalog": {"name": "docs", "title": "Docs"},
                "items": [],
                "properties": [],
            },
        ]
        result = format_search_results(results, "https://docs.example.com")
        assert "⭐ NSD" in result
        assert "⭐ Other" not in result
        assert "Продукт: NSD" in result
        assert "Сегмент: Enterprise" in result

    def test_empty_results(self):
        from gramax_docportal_mcp.formatters import format_search_results

        result = format_search_results([], "https://docs.example.com")
        assert "Ничего не найдено" in result

    def test_highlight_extraction(self):
        from gramax_docportal_mcp.formatters import _render_highlights

        items = [
            {"type": "text", "text": "обычный "},
            {"type": "highlight", "text": "выделенный"},
            {"type": "text", "text": " текст"},
        ]
        result = _render_highlights(items)
        assert result == "обычный **выделенный** текст"


class TestHtmlToMarkdown:
    def test_basic_html(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        html = "<h1>Заголовок</h1><p>Текст <strong>жирный</strong> и <em>курсив</em>.</p>"
        result = html_to_markdown(html)
        assert "# Заголовок" in result
        assert "**жирный**" in result
        assert "*курсив*" in result

    def test_strips_scripts_and_styles(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        html = "<p>Текст</p><script>alert(1)</script><style>.x{}</style>"
        result = html_to_markdown(html)
        assert "Текст" in result
        assert "alert" not in result
        assert ".x{}" not in result

    def test_links_preserved(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        html = '<p>Смотри <a href="/docs/page">документацию</a>.</p>'
        result = html_to_markdown(html)
        assert "документацию" in result

    def test_empty_html(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        assert html_to_markdown("") == ""
        assert html_to_markdown("   ") == ""
