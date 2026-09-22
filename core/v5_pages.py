"""Final Surpriz V5 concept served at ``/v5/``.

The page is standalone so it can be reviewed without changing the current
public homepage. It uses the canonical catalogue stores and shared brand
contact constants from the production Flask site.
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
from .v2_theme import (
    FAVICON_URL,
    INSTAGRAM_URL,
    LOGO_URL,
    PHONE_DISPLAY,
    PHONE_TEL,
    TELEGRAM_URL,
)


_SHOW_ORDER = {
    "cryo-show": 10,
    "balloon-show": 20,
    "paper-ribbon-show": 30,
    "streamer-show": 40,
    "ribbon-show": 50,
    "neon-jesters": 60,
    "jesters": 70,
}


_PROOF_FRAMES = (
    {
        "image": "/wp-content/uploads/2025/10/шаровое-1.webp",
        "title": "Шаровое шоу",
        "alt": "Дети участвуют в Шаровом шоу студии Сюрприз",
        "position": "50% 56%",
    },
    {
        "image": "/wp-content/uploads/2025/10/1F5A0328-1.webp",
        "title": "Лента-шоу",
        "alt": "Ребёнок и Человек-паук на Лента-шоу студии Сюрприз",
        "position": "50% 48%",
    },
    {
        "image": "/wp-content/uploads/2025/10/IMG_5029.webp",
        "title": "Серпантин-шоу",
        "alt": "Дети и артисты среди серебряного серпантина на празднике",
        "position": "50% 50%",
    },
)


def _asset_version(relative_path: str) -> str:
    try:
        return str(int((STATIC_ROOT / relative_path).stat().st_mtime))
    except OSError:
        return "1"


def _excerpt(value: object, limit: int = 170) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    shortened = text[: limit + 1].rsplit(" ", 1)[0].rstrip(" ,.;:—-")
    return f"{shortened}…"


def _cover_offset(value: object) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 50


def _collect_categories() -> list[dict[str, object]]:
    categories: list[dict[str, object]] = []
    for item in list_categories(include_hidden=False):
        count = int(item.get("character_count") or 0)
        slug = str(item.get("slug") or "").strip()
        name = str(item.get("name") or "").strip()
        if count <= 0 or not slug or not name:
            continue
        categories.append({"name": name, "slug": slug, "count": count})
    return categories


def _collect_characters(categories: list[dict[str, object]]) -> list[dict[str, object]]:
    category_names = {str(item["slug"]): str(item["name"]) for item in categories}
    characters: list[dict[str, object]] = []
    for item in list_characters_for_public(entity_type=ENTITY_TYPE_CHARACTER):
        hero = str(item.get("hero_file_path") or "").strip()
        route = str(item.get("route") or "").strip()
        if not hero or not route:
            continue
        category_slugs = [
            str(slug).strip()
            for slug in (item.get("category_slugs") or [])
            if str(slug).strip()
        ]
        primary_category = next(
            (
                category_names[slug]
                for slug in category_slugs
                if slug != "all" and slug in category_names
            ),
            "Персонаж",
        )
        characters.append(
            {
                "name": str(item.get("name") or "Персонаж").strip(),
                "slug": str(item.get("slug") or "").strip(),
                "route": route,
                "hero": hero,
                "categories": category_slugs,
                "primary_category": primary_category,
                "cover_x": _cover_offset(item.get("cover_offset_x")),
                "cover_y": _cover_offset(item.get("cover_offset_y")),
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
        route = str(summary.get("route") or "").strip()
        hero = str(summary.get("hero_file_path") or "").strip()
        if not slug or not route or not hero:
            continue
        shows.append(
            {
                "slug": slug,
                "name": (
                    str(group.get("name") or "").strip()
                    if group.get("is_group")
                    else str(summary.get("name") or "Шоу-программа").strip()
                ),
                "route": route,
                "hero": hero,
                "price": str(summary.get("price_label") or "Цена по запросу").strip(),
                "duration": str(summary.get("duration_label") or "").strip(),
                "summary": _excerpt(summary.get("summary_text")),
                "variant_count": concrete_count,
                "builder_url": f"/party-builder/?program={slug}",
            }
        )
    shows.sort(key=lambda show: (_SHOW_ORDER.get(str(show["slug"]), 999), str(show["name"])))
    return shows, program_count


def build_v5_page() -> str:
    categories = _collect_categories()
    characters = _collect_characters(categories)
    shows, show_program_count = _collect_shows()
    return render_template(
        "site/v5/home.html",
        categories=categories,
        characters=characters,
        characters_preview=characters[:10],
        characters_total=len(characters),
        shows=shows,
        show_program_count=show_program_count,
        show_group_count=len(shows),
        proof_frames=_PROOF_FRAMES,
        hero_image="/wp-content/uploads/2025/12/IMG_4795.jpeg",
        logo_url=LOGO_URL,
        favicon_url=FAVICON_URL,
        phone_display=PHONE_DISPLAY,
        phone_tel=PHONE_TEL,
        telegram_url=TELEGRAM_URL,
        instagram_url=INSTAGRAM_URL,
        css_version=_asset_version("v5/v5.css"),
        js_version=_asset_version("v5/v5.js"),
    )
