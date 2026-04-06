"""Converters from Gramax API responses to markdown."""

from __future__ import annotations

from bs4 import BeautifulSoup
from markdownify import markdownify


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
        lines.append(f"| {cat['title']} | {cat['id']} |")

    lines.append("")
    lines.append(f"Всего: {len(catalogs)}")

    return "\n".join(lines)


def _render_tree(items: list[dict], base_url: str, catalog_id: str, depth: int = 0) -> list[str]:
    """Recursively render navigation tree to markdown lines."""
    lines: list[str] = []
    indent = "  " * depth
    for item in items:
        url = f"{base_url}/{catalog_id}/{item['id']}"
        lines.append(f"{indent}- [{item['title']}]({url})")
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
        path_parts = [catalog.get("title", "")] + [b["title"] for b in breadcrumbs]
        path = " > ".join(p for p in path_parts if p)

        lines.append(f"## {i}. {title}")
        if path:
            lines.append(f"📂 {path}")
        lines.append(f"🔗 {url}")
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
    while "\n\n\n" in md:
        md = md.replace("\n\n\n", "\n\n")

    return md.strip()
