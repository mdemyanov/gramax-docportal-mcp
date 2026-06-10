"""Converters from Gramax API responses to markdown."""

from __future__ import annotations

import re
from typing import TypedDict

from bs4 import BeautifulSoup
from markdownify import markdownify


class Citation(TypedDict):
    n: int
    full_id: str


class ParsedAnswer(TypedDict):
    text: str
    citations: list[Citation]


_ZWSP = "​"
_WJ = "⁠"
_CIT_PATTERN = re.compile(
    rf"{_ZWSP}{_WJ}CIT{_WJ}(\d+){_WJ}([^{_WJ}]+){_WJ}([^{_WJ}]+){_WJ}{_WJ}{_ZWSP}"
)

MAX_NAV_DEPTH = 20


def format_catalogs_list(data: dict) -> str:
    """Format catalogs list to markdown table."""
    catalogs = data.get("data", [])

    if not catalogs:
        return "# Каталоги документации\n\nКаталогов не найдено."

    lines = [
        "# Каталоги документации",
        "",
        "| Каталог | ID |",
        "|---------|-----|",
    ]

    for cat in catalogs:
        lines.append(f"| {cat.get('title', '—')} | {cat.get('id', '—')} |")

    lines.append("")
    lines.append(f"Всего: {len(catalogs)}")

    return "\n".join(lines)


def _render_tree(items: list[dict], base_url: str, catalog_id: str, depth: int = 0) -> list[str]:
    """Recursively render navigation tree to markdown lines."""
    if depth >= MAX_NAV_DEPTH:
        return []
    lines: list[str] = []
    indent = "  " * depth
    for item in items:
        url = f"{base_url}/{catalog_id}/{item.get('id', '')}"
        lines.append(f"{indent}- [{item.get('title', '—')}]({url})")
        children = item.get("children", [])
        if children:
            lines.extend(_render_tree(children, base_url, catalog_id, depth + 1))
    return lines


def format_navigation(catalog_id: str, data: dict, base_url: str) -> str:
    """Format catalog navigation tree to markdown."""
    items = data.get("data", [])

    if not items:
        return f"# Навигация: {catalog_id}\n\nНавигация пуста."

    lines = [f"# Навигация: {catalog_id}", ""]
    lines.extend(_render_tree(items, base_url, catalog_id))

    return "\n".join(lines)


def _render_highlights(items: list[dict]) -> str:
    """Render title/text items with highlight markers to markdown."""
    parts: list[str] = []
    for item in items:
        text = item.get("text", "")
        if item.get("type") == "highlight":
            parts.append(f"**{text}**")
        else:
            parts.append(text)
    return "".join(parts)


def _render_breadcrumb_title(title: list[dict] | str) -> str:
    """Render breadcrumb title as plain text without bold markers.

    - list[dict]: concatenate item["text"] values (ignore type — no bold for breadcrumbs)
    - str: return as-is (defensive, for backward-compatible string titles)
    - anything else: return empty string
    """
    if isinstance(title, str):
        return title
    if isinstance(title, list):
        return "".join(item.get("text", "") for item in title)
    return ""


def _render_snippet(items: list[dict]) -> str:
    """Extract first text snippet from search result items."""
    for item in items:
        if item.get("type") == "paragraph":
            sub_items = item.get("items", [])
            if sub_items:
                return _render_highlights(sub_items)
    return ""


def format_search_results(results: list[dict], base_url: str) -> str:
    """Format search results to markdown."""
    if not results:
        return "Ничего не найдено."

    lines: list[str] = []

    for i, result in enumerate(results, 1):
        title = _render_highlights(result.get("title", []))
        url = f"{base_url}{result.get('url', '')}"

        breadcrumbs = result.get("breadcrumbs", [])
        catalog = result.get("catalog", {})
        path_parts = [catalog.get("title", "")] + [
            _render_breadcrumb_title(b.get("title", "")) for b in breadcrumbs
        ]
        path = " > ".join(p for p in path_parts if p)

        recommended = "⭐ " if result.get("isRecommended") else ""
        lines.append(f"## {i}. {recommended}{title}")
        if path:
            lines.append(f"📂 {path}")
        lines.append(f"🔗 {url}")

        properties = result.get("properties", [])
        if properties:
            prop_parts: list[str] = []
            for p in properties:
                name = p.get("id") or p.get("name", "?")
                v = p.get("value", [])
                value_str = ", ".join(v) if isinstance(v, list) else str(v)
                prop_parts.append(f"{name}: {value_str}")
            props_str = " | ".join(prop_parts)
            lines.append(f"🏷️ {props_str}")
        lines.append("")

        snippet = _render_snippet(result.get("items", []))
        if snippet:
            lines.append(f"> {snippet}")
            lines.append("")

    lines.append(f"Найдено: {len(results)}")

    return "\n".join(lines)


def html_to_markdown(html: str) -> str:
    """Convert HTML to clean Markdown for LLM consumption."""
    if not html or not html.strip():
        return ""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    md = markdownify(
        str(soup),
        heading_style="ATX",
        strip=["img"],
    )

    # Clean up excessive blank lines
    md = re.sub(r"\n{3,}", "\n\n", md)

    return md.strip()


def parse_chat_stream(chunks: list[str]) -> ParsedAnswer:
    """Concatenate NDJSON text chunks and extract Gramax CIT citation markers.

    Returns:
        ParsedAnswer with text (chunks joined, CIT-маркеры заменены на [N](full_id))
        and citations (list of {"n": int, "full_id": str} в порядке появления; дубли сохранены).
    """
    raw = "".join(chunks)
    citations: list[Citation] = []

    def _replace(match: re.Match[str]) -> str:
        n = int(match.group(1))
        full_id = match.group(2)
        citations.append({"n": n, "full_id": full_id})
        return f"[{n}]({full_id})"

    text = _CIT_PATTERN.sub(_replace, raw)
    return {"text": text, "citations": citations}


def format_ai_answer(parsed: ParsedAnswer, base_url: str) -> str:
    """Render parsed AI answer with optional Sources block.

    parsed: ParsedAnswer from parse_chat_stream.
    base_url: portal URL prefix for source links.
    """
    text = parsed["text"]
    citations = parsed["citations"]

    if not text.strip():
        return "AI не сгенерировал ответ."

    if not citations:
        return text

    # Dedup by (n, full_id), preserve order of first appearance, then sort by n
    seen: set[tuple[int, str]] = set()
    unique: list[Citation] = []
    for c in citations:
        key = (c["n"], c["full_id"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    unique.sort(key=lambda c: c["n"])

    base = base_url.rstrip("/")
    # Gramax UI принимает full_id без .md (smoke против knowledge.nau.im, 2026-05-08).
    lines = [text.rstrip(), "", "## Источники", ""]
    for c in unique:
        lines.append(f"{c['n']}. `{c['full_id']}`")
        lines.append(f"   {base}/{c['full_id']}")
    return "\n".join(lines)
