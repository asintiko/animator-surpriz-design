"""Surpriz v2 landing pages: home, prices, contacts, about.

All pages are assembled on the clean v2 chrome via :func:`core.v2_theme.render_v2_page`
and rendered through ``templates/site/v2_*_content.html``. Data comes from the live
stores (catalog / shows / promotions / addons / site settings) — nothing is frozen.
"""

from __future__ import annotations

from flask import render_template

from .addon_store import list_active_addons
from .catalog_site import _format_money, _show_program_summary
from .catalog_store import (
    ENTITY_TYPE_CHARACTER,
    ENTITY_TYPE_SHOW_PROGRAM,
    list_categories,
    list_characters_for_public,
)
from .loader import PageBundle
from .promotion_store import list_promotions
from .v2_theme import DEFAULT_OG_IMAGE, render_v2_page

HOME_FEATURED_CHARACTERS = 12
HOME_MARQUEE_CHARACTERS = 20
HOME_GALLERY_PHOTOS = 10
HOME_COLLAGE_CHARACTERS = 4
ABOUT_PHOTOS = 3


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


def _characters_price_facts(shows: list[dict]) -> dict:
    """Facts about included/extra characters, derived from real program data."""
    included_counts = {int(s.get("included_characters_count") or 0) for s in shows if int(s.get("included_characters_count") or 0) > 0}
    extra_prices = sorted({int(s.get("extra_character_price_3") or 0) for s in shows if int(s.get("extra_character_price_3") or 0) > 0})
    included_label = ""
    if included_counts:
        value = min(included_counts)
        included_label = f"{value} персонажа" if value in {2, 3, 4} else f"{value} персонажей"
    extra_label = ""
    if extra_prices:
        extra_label = f"от {_format_money(extra_prices[0])}"
    return {
        "included_label": included_label,
        "extra_label": extra_label,
    }


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


def build_prices_page() -> PageBundle | None:
    shows = _public_shows()
    if not shows:
        return None

    for show in shows:
        base_price = int(show.get("base_price") or 0)
        show["price_exact"] = _format_money(base_price) if base_price > 0 else "уточняйте"

    facts = _characters_price_facts(shows)
    characters_total = len(_public_characters())

    addons = []
    try:
        for addon in list_active_addons():
            price = int(addon.get("price") or 0)
            addons.append(
                {
                    "name": str(addon.get("name") or "").strip(),
                    "summary": str(addon.get("short_description") or addon.get("description") or "").strip(),
                    "price_label": _format_money(price) if price > 0 else "уточняйте",
                }
            )
    except Exception:
        addons = []

    og_image = DEFAULT_OG_IMAGE
    for show in shows:
        path = str(show.get("hero_file_path") or "").strip()
        if path:
            og_image = path
            break

    content_html = render_template(
        "site/v2_prices_content.html",
        shows=shows,
        facts=facts,
        addons=addons,
        characters_total=characters_total,
    )
    return render_v2_page(
        content_html,
        title="Цены на детские праздники в Ташкенте | Surpriz",
        description=(
            "Актуальные цены студии Surpriz: шоу-программы, персонажи и дополнительные услуги. "
            "Оплата после мероприятия."
        ),
        canonical_path="/prices/",
        og_image=og_image,
        active="prices",
    )


def build_contacts_page() -> PageBundle | None:
    content_html = render_template("site/v2_contacts_content.html")
    return render_v2_page(
        content_html,
        title="Контакты студии детских праздников Surpriz — Ташкент",
        description=(
            "Свяжитесь со студией Surpriz: телефон +998 99 892-65-65, Telegram @Animator_Surpriz. "
            "Работаем ежедневно с 9:00 до 21:00, выезд по Ташкенту и области."
        ),
        canonical_path="/contacts/",
        og_image=DEFAULT_OG_IMAGE,
        active="contacts",
    )


def build_about_page() -> PageBundle | None:
    characters = _public_characters()
    shows = _public_shows()
    with_photos = [c for c in characters if str(c.get("hero_file_path") or "").strip()]
    photos = with_photos[:ABOUT_PHOTOS]

    og_image = DEFAULT_OG_IMAGE
    if with_photos:
        og_image = str(with_photos[0].get("hero_file_path") or DEFAULT_OG_IMAGE)

    content_html = render_template(
        "site/v2_about_content.html",
        photos=photos,
        characters_total=len(characters),
        shows_total=len(shows),
    )
    return render_v2_page(
        content_html,
        title="О студии Surpriz — детские праздники в Ташкенте",
        description=(
            "Surpriz — студия детских праздников в Ташкенте. Свои костюмы и реквизит, "
            "артисты с опытом 5+ лет, сотни счастливых семей."
        ),
        canonical_path="/o-nas/",
        og_image=og_image,
        active="about",
    )
