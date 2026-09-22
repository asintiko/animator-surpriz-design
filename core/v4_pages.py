"""Mobile-first Surpriz catalogue concept served at ``/v4/``.

The page is intentionally standalone: it reuses the live catalogue data but
does not inherit the legacy v2/v3 layout or motion systems.
"""

from __future__ import annotations

from flask import render_template

from .catalog_site import _show_program_summary
from .catalog_store import (
    ENTITY_TYPE_CHARACTER,
    list_categories,
    list_characters_for_public,
)
from .config import STATIC_ROOT
from .customer_store import list_show_programs_grouped_for_public


_SHOW_ORDER = {
    "cryo-show": 10,
    "balloon-show": 20,
    "paper-ribbon-show": 30,
    "neon-jesters": 40,
    "jesters": 50,
}


def _asset_version(relative_path: str) -> str:
    try:
        return str(int((STATIC_ROOT / relative_path).stat().st_mtime))
    except OSError:
        return "1"


def _excerpt(value: object, limit: int = 176) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    shortened = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:—-")
    return f"{shortened}…"


def _collect_categories() -> list[dict[str, object]]:
    categories: list[dict[str, object]] = []
    for item in list_categories(include_hidden=False):
        count = int(item.get("character_count") or 0)
        if count <= 0:
            continue
        categories.append(
            {
                "name": str(item.get("name") or "").strip(),
                "slug": str(item.get("slug") or "").strip(),
                "count": count,
            }
        )
    return categories


def _collect_characters(categories: list[dict[str, object]]) -> list[dict[str, object]]:
    category_names = {str(item["slug"]): str(item["name"]) for item in categories}
    characters: list[dict[str, object]] = []
    for item in list_characters_for_public(entity_type=ENTITY_TYPE_CHARACTER):
        hero = str(item.get("hero_file_path") or "").strip()
        if not hero:
            continue
        category_slugs = [
            str(slug).strip()
            for slug in (item.get("category_slugs") or [])
            if str(slug).strip()
        ]
        primary_category = next(
            (category_names[slug] for slug in category_slugs if slug != "all" and slug in category_names),
            "Персонаж",
        )
        characters.append(
            {
                "name": str(item.get("name") or "Персонаж").strip(),
                "slug": str(item.get("slug") or "").strip(),
                "route": str(item.get("route") or "/catalog/").strip(),
                "hero": hero,
                "categories": category_slugs,
                "primary_category": primary_category,
                "cover_x": max(0, min(100, int(item.get("cover_offset_x") or 50))),
                "cover_y": max(0, min(100, int(item.get("cover_offset_y") or 50))),
                "cover_fit": "contain" if item.get("cover_fit") == "contain" else "cover",
            }
        )
    return characters


def _collect_shows() -> tuple[list[dict[str, object]], int]:
    shows: list[dict[str, object]] = []
    program_count = 0
    for group in list_show_programs_grouped_for_public():
        primary = dict(group.get("primary") or {})
        if not primary:
            continue
        summary = _show_program_summary(primary)
        variants = list(group.get("variants") or [])
        concrete_count = len(variants) if variants else 1
        program_count += concrete_count
        slug = str(summary.get("slug") or "").strip()
        shows.append(
            {
                "slug": slug,
                "name": (
                    str(group.get("name") or "").strip()
                    if group.get("is_group")
                    else str(summary.get("name") or "Шоу-программа").strip()
                ),
                "route": str(summary.get("route") or "/show-programs/").strip(),
                "hero": str(summary.get("hero_file_path") or "").strip(),
                "price": str(summary.get("price_label") or "").strip(),
                "duration": str(summary.get("duration_label") or "").strip(),
                "summary": _excerpt(summary.get("summary_text")),
                "variant_count": concrete_count,
                "builder_url": f"/party-builder/?program={slug}",
            }
        )
    shows.sort(key=lambda show: (_SHOW_ORDER.get(str(show["slug"]), 999), str(show["name"])))
    return shows, program_count


def build_v4_page() -> str:
    categories = _collect_categories()
    characters = _collect_characters(categories)
    shows, show_program_count = _collect_shows()
    return render_template(
        "site/v4/mobile_catalog.html",
        categories=categories,
        characters=characters,
        characters_preview=characters[:8],
        characters_total=len(characters),
        shows=shows,
        show_program_count=show_program_count,
        hero_image="/wp-content/uploads/2025/12/IMG_4795.jpeg",
        css_version=_asset_version("v4/v4.css"),
        js_version=_asset_version("v4/v4.js"),
    )
