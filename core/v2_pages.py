"""Surpriz v2 landing home page.

The page is assembled on the clean v2 chrome via :func:`core.v2_theme.render_v2_page`
and rendered through ``templates/site/v2_home_content.html``. Data comes from the live
stores (catalog / shows / promotions / site settings) — nothing is frozen.
"""

from __future__ import annotations

from flask import render_template

from .catalog_site import _show_program_summary
from .catalog_store import (
    ENTITY_TYPE_CHARACTER,
    ENTITY_TYPE_SHOW_PROGRAM,
    list_categories,
    list_characters_for_public,
)
from .loader import PageBundle
from .v2_theme import DEFAULT_OG_IMAGE, render_v2_page

HOME_FEATURED_CHARACTERS = 12
HOME_MARQUEE_CHARACTERS = 20
HOME_GALLERY_PHOTOS = 10
HOME_COLLAGE_CHARACTERS = 4


def _public_shows() -> list[dict]:
    """All active show programs enriched with price/duration/age labels and routes."""
    raw_shows = list_characters_for_public(entity_type=ENTITY_TYPE_SHOW_PROGRAM)
    return [_show_program_summary(item) for item in raw_shows]


def _public_characters() -> list[dict]:
    return list_characters_for_public(entity_type=ENTITY_TYPE_CHARACTER)


def _public_categories() -> list[dict]:
    return [c for c in list_categories(include_hidden=False) if c.get("slug") != "all"]


def _with_primary_category(characters: list[dict], categories: list[dict]) -> list[dict]:
    """Attach `primary_category` (first non-'all' category name) to each character."""
    name_by_slug = {str(c.get("slug") or ""): str(c.get("name") or "") for c in categories}
    for character in characters:
        primary = ""
        for slug in character.get("category_slugs") or []:
            slug = str(slug or "").strip()
            if slug and slug != "all" and name_by_slug.get(slug):
                primary = name_by_slug[slug]
                break
        character["primary_category"] = primary
    return characters


def _pick_diverse(characters: list[dict], count: int) -> list[dict]:
    """Round-robin pick across primary categories so grids look varied."""
    buckets: dict[str, list[dict]] = {}
    order: list[str] = []
    rest: list[dict] = []
    for character in characters:
        key = str(character.get("primary_category") or "").strip()
        if not key:
            rest.append(character)
            continue
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(character)

    picked: list[dict] = []
    while len(picked) < count and order:
        progressed = False
        for key in list(order):
            bucket = buckets.get(key) or []
            if not bucket:
                order.remove(key)
                continue
            picked.append(bucket.pop(0))
            progressed = True
            if len(picked) >= count:
                break
        if not progressed:
            break
    if len(picked) < count:
        picked.extend(rest[: count - len(picked)])
    return picked[:count]


def _active_promotions() -> list[dict]:
    """Promotions show up only when the admin toggle `show_promotions` is on."""
    try:
        from .admin_store import get_public_settings

        if not get_public_settings().get("show_promotions"):
            return []
    except Exception:
        return []
    try:
        return list_promotions()
    except Exception:
        return []


def build_home_page() -> PageBundle | None:
    shows = _public_shows()
    characters = _public_characters()
    if not shows and not characters:
        return None

    categories = _public_categories()
    characters = _with_primary_category(characters, categories)
    with_photos = [c for c in characters if str(c.get("hero_file_path") or "").strip()]

    collage = _pick_diverse(with_photos, HOME_COLLAGE_CHARACTERS)
    featured = _pick_diverse(with_photos, HOME_FEATURED_CHARACTERS)
    marquee = with_photos[:HOME_MARQUEE_CHARACTERS]
    gallery = with_photos[len(collage): len(collage) + HOME_GALLERY_PHOTOS] or with_photos[:HOME_GALLERY_PHOTOS]
    promotions = _active_promotions()

    og_image = DEFAULT_OG_IMAGE
    for candidate in [*shows, *with_photos]:
        path = str(candidate.get("hero_file_path") or "").strip()
        if path:
            og_image = path
            break

    content_html = render_template(
        "site/v2_home_content.html",
        shows=shows,
        characters=featured,
        characters_total=len(characters),
        categories=categories,
        collage=collage,
        marquee=marquee,
        gallery=gallery,
        shows_total=len(shows),
        promotions=promotions,
    )
    return render_v2_page(
        content_html,
        title="Детские Аниматоры в Ташкенте, заказать и собрать праздник на выезд",
        description=(
            "Студия детских праздников Surpriz в Ташкенте: шоу-программы, любимые персонажи "
            "и аниматоры с опытом 5+ лет. Оплата после праздника. Ежедневно 9:00–21:00."
        ),
        canonical_path="/",
        og_image=og_image,
        active="home",
    )
