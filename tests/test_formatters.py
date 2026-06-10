import json
import json as _json
from pathlib import Path

SEARCH_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "search_response.json"


def _load_search_fixture() -> list[dict]:
    return json.loads(SEARCH_FIXTURE_PATH.read_text(encoding="utf-8"))


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

    def test_deep_tree_truncated(self):
        from gramax_docportal_mcp.formatters import MAX_NAV_DEPTH, format_navigation

        node = {"id": f"level-{MAX_NAV_DEPTH + 1}", "title": f"Level {MAX_NAV_DEPTH + 1}"}
        for i in range(MAX_NAV_DEPTH, 0, -1):
            node = {"id": f"level-{i}", "title": f"Level {i}", "children": [node]}
        data = {"data": [node]}

        result = format_navigation("docs", data, "https://docs.example.com")
        assert "Level 1" in result
        assert f"Level {MAX_NAV_DEPTH}" in result
        assert f"Level {MAX_NAV_DEPTH + 1}" not in result


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


class TestRenderBreadcrumbTitle:
    """AC-2, AC-5: _render_breadcrumb_title — plain text, no bold, defensive str."""

    def test_list_of_fragments_plain_text_no_bold(self):
        """AC-2: list title renders as plain text without ** markers."""
        from gramax_docportal_mcp.formatters import _render_breadcrumb_title

        title = [{"type": "highlight", "text": "Настройка"}, {"type": "text", "text": " ВКС"}]
        result = _render_breadcrumb_title(title)
        assert result == "Настройка ВКС"
        assert "**" not in result

    def test_list_single_highlight_no_bold(self):
        """AC-2: single highlight fragment — plain text, no bold."""
        from gramax_docportal_mcp.formatters import _render_breadcrumb_title

        title = [{"type": "highlight", "text": "Настройки"}]
        result = _render_breadcrumb_title(title)
        assert result == "Настройки"
        assert "**" not in result

    def test_string_title_returned_as_is(self):
        """AC-5: string title passed through without exception."""
        from gramax_docportal_mcp.formatters import _render_breadcrumb_title

        result = _render_breadcrumb_title("Раздел")
        assert result == "Раздел"

    def test_empty_list_returns_empty_string(self):
        """Edge case: empty list → empty string."""
        from gramax_docportal_mcp.formatters import _render_breadcrumb_title

        result = _render_breadcrumb_title([])
        assert result == ""


class TestPropertiesIdKey:
    """AC-6, AC-7, AC-8: properties with id key, empty value, empty list."""

    def test_properties_with_id_key(self):
        """AC-6: properties with 'id' key (no 'name') render correctly."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = [
            {
                "type": "article",
                "isRecommended": False,
                "title": [{"type": "text", "text": "Test"}],
                "url": "/demo/test",
                "breadcrumbs": [],
                "catalog": {"name": "demo", "title": "Demo"},
                "items": [],
                "properties": [
                    {"id": "Category", "value": ["setup"]},
                    {"id": "Feature", "value": ["integration"]},
                ],
            }
        ]
        result = format_search_results(results, "https://example.test")
        assert "Category: setup" in result
        assert "Feature: integration" in result

    def test_properties_empty_value_list(self):
        """AC-7: property with empty value list renders without crash."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = [
            {
                "type": "article",
                "isRecommended": False,
                "title": [{"type": "text", "text": "Test"}],
                "url": "/demo/test",
                "breadcrumbs": [],
                "catalog": {"name": "demo", "title": "Demo"},
                "items": [],
                "properties": [
                    {"id": "Segment", "value": []},
                ],
            }
        ]
        result = format_search_results(results, "https://example.test")
        assert "Segment: " in result

    def test_properties_empty_renders_no_tag(self):
        """AC-8: empty properties list → no 🏷️ line in output."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = [
            {
                "type": "article",
                "isRecommended": False,
                "title": [{"type": "text", "text": "Test"}],
                "url": "/demo/test",
                "breadcrumbs": [],
                "catalog": {"name": "demo", "title": "Demo"},
                "items": [],
                "properties": [],
            }
        ]
        result = format_search_results(results, "https://example.test")
        assert "🏷️" not in result

    def test_properties_value_none_no_crash(self):
        """Edge: value=None → no crash, renders as empty string."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = [
            {
                "type": "article",
                "isRecommended": False,
                "title": [{"type": "text", "text": "Test"}],
                "url": "/demo/test",
                "breadcrumbs": [],
                "catalog": {"name": "demo", "title": "Demo"},
                "items": [],
                "properties": [{"id": "Foo", "value": None}],
            }
        ]
        # Should not raise
        result = format_search_results(results, "https://example.test")
        assert "Foo:" in result


class TestFormatSearchResultsRealFixture:
    """AC-1..AC-10: full integration test against contract fixture."""

    def test_no_exception_with_real_api_payload(self):
        """AC-1: no exception when processing fixture with list breadcrumb titles."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        # Must not raise TypeError
        output = format_search_results(results, "https://example.test")
        assert isinstance(output, str)

    def test_breadcrumb_path_plain_text_no_bold(self):
        """AC-2: path string contains plain text, no ** markers."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        output = format_search_results(results, "https://example.test")
        # The path for result 1: Demo Catalog > Настройки > Интеграции > Настройка ВКС
        assert "Настройки" in output
        assert "Интеграции" in output
        assert "Настройка ВКС" in output
        # No bold markers inside path
        assert "**Настройки**" not in output

    def test_breadcrumb_path_includes_catalog_name(self):
        """AC-3: path includes catalog title as first element."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        output = format_search_results(results, "https://example.test")
        assert "📂 Demo Catalog" in output

    def test_empty_breadcrumbs_shows_catalog_only(self):
        """AC-4: result 2 has empty breadcrumbs → path is only catalog title."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        output = format_search_results(results, "https://example.test")
        # Result 2 is isRecommended=true, title "Обзор продукта"
        # After the ⭐ Обзор продукта line, path should be just "📂 Demo Catalog"
        lines = output.splitlines()
        overview_idx = next(i for i, line in enumerate(lines) if "Обзор продукта" in line)
        path_line = lines[overview_idx + 1]
        assert path_line == "📂 Demo Catalog"

    def test_string_breadcrumb_title_no_crash(self):
        """AC-5: result 3 has string breadcrumb title → no crash, string used as-is."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        output = format_search_results(results, "https://example.test")
        # Result 3: breadcrumbs[0].title = "Раздел" (string)
        assert "Раздел" in output

    def test_properties_id_key_rendered(self):
        """AC-6: result 1 properties use 'id' key → Category: setup | Feature: integration."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        output = format_search_results(results, "https://example.test")
        assert "Category: setup" in output
        assert "Feature: integration" in output

    def test_properties_empty_value_no_crash(self):
        """AC-7: result 2 Segment has value=[] → renders Segment: (empty) without crash."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        output = format_search_results(results, "https://example.test")
        assert "Segment: " in output

    def test_empty_properties_no_tag(self):
        """AC-8: result 3 has empty properties → no 🏷️ in that result's section."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        output = format_search_results(results, "https://example.test")
        # The last result ("Устаревший формат") has empty properties
        # Find its section and ensure no 🏷️ appears between it and the next "##" or end
        lines = output.splitlines()
        legacy_idx = next(i for i, line in enumerate(lines) if "Устаревший формат" in line)
        section_lines = lines[legacy_idx:]
        # There's no next ## header, so check entire trailing section
        assert not any("🏷️" in line for line in section_lines)

    def test_recommended_result_has_star(self):
        """AC-9: isRecommended=true → ⭐ prefix in title."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        output = format_search_results(results, "https://example.test")
        assert "⭐ Обзор продукта" in output

    def test_snippet_from_top_level_paragraph_only(self):
        """AC-10: snippet from first top-level paragraph; block items ignored."""
        from gramax_docportal_mcp.formatters import format_search_results

        results = _load_search_fixture()
        output = format_search_results(results, "https://example.test")
        # Result 1 snippet: "**Настройка** выполняется через раздел"
        assert "**Настройка** выполняется через раздел" in output
        # Block content "Текст внутри блока" must NOT appear in output
        assert "Текст внутри блока" not in output


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

    def test_collapses_multiple_blank_lines(self):
        from gramax_docportal_mcp.formatters import html_to_markdown

        html = "<p>A</p><br><br><br><br><br><p>B</p>"
        result = html_to_markdown(html)
        assert "\n\n\n" not in result
        assert "A" in result
        assert "B" in result


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ai_search_response.ndjson"


def _load_fixture_chunks() -> list[str]:
    chunks: list[str] = []
    for raw_line in FIXTURE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        obj = _json.loads(line)
        if obj.get("type") == "text":
            text = obj.get("text", "")
            if text:
                chunks.append(text)
    return chunks


def test_parse_chat_stream_concatenates_no_markers():
    from gramax_docportal_mcp.formatters import parse_chat_stream

    result = parse_chat_stream(["Hello", " ", "world", "!"])

    assert result == {"text": "Hello world!", "citations": []}


def test_parse_chat_stream_empty_input():
    from gramax_docportal_mcp.formatters import parse_chat_stream

    assert parse_chat_stream([]) == {"text": "", "citations": []}


def test_parse_chat_stream_synthetic_marker():
    """Test marker built by hand from known codepoints."""
    from gramax_docportal_mcp.formatters import parse_chat_stream

    zwsp = "​"
    wj = "⁠"
    marker = f"{zwsp}{wj}CIT{wj}1{wj}cat/article{wj}./article.md{wj}{wj}{zwsp}"
    chunks = ["Some text ", marker, " more text"]

    result = parse_chat_stream(chunks)

    assert result["text"] == "Some text [1](cat/article) more text"
    assert result["citations"] == [{"n": 1, "full_id": "cat/article"}]


def test_parse_chat_stream_marker_split_across_chunks():
    """Marker may be split between NDJSON lines; concat-then-parse handles it."""
    from gramax_docportal_mcp.formatters import parse_chat_stream

    zwsp = "​"
    wj = "⁠"
    full_marker = f"{zwsp}{wj}CIT{wj}5{wj}foo/bar{wj}./bar.md{wj}{wj}{zwsp}"
    half = len(full_marker) // 2
    chunks = ["pre ", full_marker[:half], full_marker[half:], " post"]

    result = parse_chat_stream(chunks)

    assert result["text"] == "pre [5](foo/bar) post"
    assert result["citations"] == [{"n": 5, "full_id": "foo/bar"}]


def test_parse_chat_stream_real_fixture():
    """Real Gramax NDJSON: 10 markers total, 6 unique full_ids."""
    from gramax_docportal_mcp.formatters import parse_chat_stream

    chunks = _load_fixture_chunks()
    result = parse_chat_stream(chunks)

    # Citations: 10 occurrences, with N=2..5 appearing twice
    ns = [c["n"] for c in result["citations"]]
    assert sorted(ns) == [1, 2, 2, 3, 3, 4, 4, 5, 5, 6]
    full_ids = {c["full_id"] for c in result["citations"]}
    assert full_ids == {
        "commercial-knowlage/90-knowledge-base/glossary",
        "commercial-knowlage/10-products/itsm-365/support",
        "commercial-knowlage/10-products/itsm-365/outsource",
        "commercial-knowlage/10-products/itsm-365/hr",
        "commercial-knowlage/10-products/itsm-365/projects",
        "commercial-knowlage/90-knowledge-base/certifications",
    }
    # No leftover invisible chars after replacement
    assert "​" not in result["text"]
    assert "⁠" not in result["text"]
    # Inline citation present in expected place
    assert "[1](commercial-knowlage/90-knowledge-base/glossary)" in result["text"]


def test_format_ai_answer_empty_text():
    from gramax_docportal_mcp.formatters import format_ai_answer

    result = format_ai_answer({"text": "", "citations": []}, "https://docs.example.com")

    assert result == "AI не сгенерировал ответ."


def test_format_ai_answer_whitespace_only_text():
    from gramax_docportal_mcp.formatters import format_ai_answer

    result = format_ai_answer({"text": "   \n\n  ", "citations": []}, "https://docs.example.com")

    assert result == "AI не сгенерировал ответ."


def test_format_ai_answer_no_citations():
    from gramax_docportal_mcp.formatters import format_ai_answer

    result = format_ai_answer(
        {"text": "Just a plain answer.", "citations": []},
        "https://docs.example.com",
    )

    assert result == "Just a plain answer."
    assert "Источники" not in result


def test_format_ai_answer_with_citations_dedups_same_pair():
    from gramax_docportal_mcp.formatters import format_ai_answer

    parsed = {
        "text": "Foo [1](a/b) and again [1](a/b).",
        "citations": [
            {"n": 1, "full_id": "a/b"},
            {"n": 1, "full_id": "a/b"},  # exact duplicate
        ],
    }

    result = format_ai_answer(parsed, "https://docs.example.com")

    assert "## Источники" in result
    # exactly one entry for (1, a/b)
    assert result.count("`a/b`") == 1
    assert "1. `a/b`" in result
    assert "https://docs.example.com/a/b" in result


def test_format_ai_answer_keeps_distinct_n_for_same_full_id():
    """Different N to same full_id → two source rows (preserve inline-row mapping)."""
    from gramax_docportal_mcp.formatters import format_ai_answer

    parsed = {
        "text": "First [1](a/b) and second [3](a/b).",
        "citations": [
            {"n": 1, "full_id": "a/b"},
            {"n": 3, "full_id": "a/b"},
        ],
    }

    result = format_ai_answer(parsed, "https://docs.example.com")

    assert "1. `a/b`" in result
    assert "3. `a/b`" in result


def test_format_ai_answer_sorts_by_n():
    from gramax_docportal_mcp.formatters import format_ai_answer

    parsed = {
        "text": "[3](c) [1](a) [2](b)",
        "citations": [
            {"n": 3, "full_id": "c"},
            {"n": 1, "full_id": "a"},
            {"n": 2, "full_id": "b"},
        ],
    }

    result = format_ai_answer(parsed, "https://docs.example.com")

    src_block = result.split("## Источники", 1)[1]
    pos_1 = src_block.find("1. `a`")
    pos_2 = src_block.find("2. `b`")
    pos_3 = src_block.find("3. `c`")
    assert 0 <= pos_1 < pos_2 < pos_3


def test_format_ai_answer_sources_url_format():
    from gramax_docportal_mcp.formatters import format_ai_answer

    parsed = {
        "text": "[1](cat/path/article)",
        "citations": [{"n": 1, "full_id": "cat/path/article"}],
    }

    result = format_ai_answer(parsed, "https://docs.example.com")

    assert "https://docs.example.com/cat/path/article" in result
