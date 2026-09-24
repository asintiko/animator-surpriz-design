from __future__ import annotations

import re
from urllib.parse import urlencode

from flask import render_template

from .addon_store import list_program_addons_for_public
from .catalog_store import (
    ENTITY_TYPE_CHARACTER,
    ENTITY_TYPE_SHOW_PROGRAM,
    FIXED_CAST_PROGRAM_DETAILS,
    get_category_by_slug,
    get_character_by_slug,
    get_tag_by_slug,
    list_categories,
    list_characters,
    list_characters_for_public,
    list_tags,
    show_features_from_text,
)
from .config import STATIC_ROOT
from .customer_store import (
    calculate_program_character_surcharge,
    list_show_programs_for_public,
    list_show_programs_grouped_for_public,
)
from .loader import PageBundle
from .partner_store import list_partners
from .recommendation_store import HOMEPAGE_SLOTS, get_featured_slugs, sort_by_featured
from .v2_theme import PHONE_DISPLAY, PHONE_TEL, TELEGRAM_URL, _asset_version, render_v2_page

SHOW_PROGRAMS_ROUTE = "/show-programs/"
DEFAULT_OG_IMAGE = "/surpriz/assets/img/show-programs/hero-desktop.webp"
CATALOG_ITEMS_PER_PAGE = 9
FRONTEND_HOMEPAGE_CHARACTER_SLUGS = (
    "kid-e-cats",
    "anna-elsa-olaf",
    "naruto",
    "among-us",
    "digital-circus",
    "paw-patrol",
    "spiderman-n1",
    "hosts-mickey-minnie",
)
FRONTEND_CATEGORY_BY_CATALOG_SLUG = {
    "supergeroi": "superheroes",
    "skazochnye": "princesses",
    "multiki": "cartoons",
}
FRONTEND_TAG_BY_CATALOG_SLUG = {
    "supergeroi": "superheroes",
    "skazochnye": "princesses",
    "multiki": "cartoons",
    "malchikam": "boys",
    "devochkam": "girls",
}
FRONTEND_FILTER_ICONS = {
    "all": "all-heroes.svg",
    "superheroes": "superheroes.svg",
    "princesses": "princesses.svg",
    "boys": "for-boys.svg",
    "girls": "for-girls.svg",
    "cartoons": "cartoon-characters.svg",
}
FRONTEND_SHOW_IMAGE_SOURCES: dict[str, dict[str, object]] = {
    "standard-program": {"source_size": (1200, 1600), "widths": (480, 768, 1200)},
    "cryo-show": {"source_size": (1406, 2500), "widths": (480, 768, 1200)},
    "ribbon-show": {"source_size": (1200, 1600), "widths": (480, 768, 1200)},
    "streamer-show": {"source_size": (1200, 1600), "widths": (480, 768, 1200)},
    "neon-start": {"source_size": (1200, 1600), "widths": (480, 768, 1200)},
    "neon-medium": {"source_size": (1200, 1600), "widths": (480, 768, 1200)},
    "neon-lux": {"source_size": (1200, 1600), "widths": (480, 768, 1200)},
    "balloon-show": {"source_size": (1406, 2500), "widths": (480, 768, 1200)},
    "jesters": {"source_size": (1406, 2500), "widths": (480, 768, 1200)},
    "neon-jesters": {"source_size": (1406, 2500), "widths": (480, 768, 1200)},
}
FRONTEND_SHOW_IMAGE_VERSION = "af3513c76de3"
FRONTEND_CHARACTER_IMAGE_VERSION = "b970d6020c37"
_GENERATED_CHARACTER_MEDIA_RE = re.compile(
    r"^(?P<base>/media/generated/[^?#]+?)/(?P<width>\d+)\.(?:avif|webp)(?:[?#].*)?$"
)
_CURATED_CHARACTER_MEDIA_RE = re.compile(
    r"^(?P<base>/surpriz/assets/img/characters/.+?)-(?:800|1200)\.webp(?:[?#].*)?$"
)
SHOW_DETAIL_ASSET_DIR = STATIC_ROOT / "v2" / "show-detail"
_SHOW_CARD_MEDIA_RE = re.compile(
    r"^(?P<base>/surpriz/assets/img/show-programs/cards/.+?)-1200\.webp(?:[?#].*)?$"
)
SHOW_DETAIL_FEATURED_CHARACTERS = 8


def _build_page_bundle(
    *,
    route: str,
    title: str,
    description: str,
    canonical_path: str,
    content_html: str,
    og_image: str,
    active: str = "",
) -> PageBundle | None:
    """Assemble a dynamic page on the clean v2 chrome (no WP reference bundle)."""
    return render_v2_page(
        content_html,
        title=title,
        description=description,
        canonical_path=canonical_path,
        og_image=og_image,
        active=active,
        route=route,
    )


def _catalog_page_path(base_path: str, page_number: int, *, search_query: str = "") -> str:
    normalized_base = base_path if base_path.endswith("/") else f"{base_path}/"
    if page_number <= 1:
        path = normalized_base
    else:
        path = f"{normalized_base}page/{page_number}/"
    if search_query.strip():
        return f"{path}?{urlencode({'q': search_query.strip()})}"
    return path


def _format_money(value: int | None) -> str:
    amount = max(0, int(value or 0))
    return f"{amount:,}".replace(",", " ") + " сум"


def _format_duration(minutes: int | None) -> str:
    duration = int(minutes or 0)
    if duration <= 0:
        return "уточняется"
    if duration == 60:
        return "1 час"
    if duration % 60 == 0:
        return f"{duration // 60} ч"
    return f"{duration} мин"


def _format_age(age_from: object, age_to: object) -> str:
    try:
        start = int(age_from) if age_from not in {None, ""} else None
    except (TypeError, ValueError):
        start = None
    try:
        end = int(age_to) if age_to not in {None, ""} else None
    except (TypeError, ValueError):
        end = None
    start = start if start is not None and start > 0 else None
    end = end if end is not None and end > 0 else None
    if start is not None and end is not None:
        return f"{start}-{end} лет"
    if start is not None:
        return f"от {start} лет"
    if end is not None:
        return f"до {end} лет"
    return ""


def _split_show_text(value: object) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    chunks = re.split(r"[\n;]+", text)
    return [chunk.strip(" -•\t") for chunk in chunks if chunk.strip(" -•\t")]


def _frontend_character_categories(character: dict[str, object]) -> list[str]:
    categories: list[str] = []
    for slug in character.get("category_slugs") or []:
        catalog_slug = str(slug or "").strip().lower()
        if not catalog_slug or catalog_slug == "all":
            continue
        frontend_slug = FRONTEND_CATEGORY_BY_CATALOG_SLUG.get(catalog_slug, catalog_slug)
        if frontend_slug and frontend_slug not in categories:
            categories.append(frontend_slug)

    for slug in character.get("tag_slugs") or []:
        catalog_slug = str(slug or "").strip().lower()
        if not catalog_slug or catalog_slug == "all":
            continue
        frontend_slug = FRONTEND_TAG_BY_CATALOG_SLUG.get(catalog_slug, catalog_slug)
        if frontend_slug not in categories:
            categories.append(frontend_slug)

    normalized_tags = {str(tag or "").strip().lower() for tag in character.get("tag_names") or []}
    for names, frontend_slug in (({"мальчикам", "для мальчиков"}, "boys"), ({"девочкам", "для девочек"}, "girls")):
        if normalized_tags.intersection(names) and frontend_slug not in categories:
            categories.append(frontend_slug)
    return categories


def _frontend_character_image_sources(character: dict[str, object]) -> dict[str, object]:
    image = str(character.get("hero_file_path") or "").strip()
    curated = _CURATED_CHARACTER_MEDIA_RE.fullmatch(image)
    if curated:
        base = curated.group("base")
        widths = (480, 768, 1200)
        suffix = f"?v={FRONTEND_CHARACTER_IMAGE_VERSION}"
    else:
        generated = _GENERATED_CHARACTER_MEDIA_RE.fullmatch(image)
        if not generated:
            return {}
        base = generated.group("base")
        maximum_width = int(generated.group("width"))
        widths = tuple(
            sorted({width for width in (480, 768, 1280, maximum_width) if width <= maximum_width})
        )
        suffix = ""
    separator = "/" if base.startswith("/media/generated/") else "-"
    return {
        "avif": [
            {"src": f"{base}{separator}{width}.avif{suffix}", "width": width}
            for width in widths
        ],
        "webp": [
            {"src": f"{base}{separator}{width}.webp{suffix}", "width": width}
            for width in widths
        ],
        "fallback": f"{base}{separator}{widths[-1]}.webp{suffix}",
    }


def _build_frontend_character_filters() -> list[dict[str, object]]:
    filters: list[dict[str, object]] = [
        {
            "slug": "all",
            "label": "Все",
            "icon": "/surpriz/assets/icons/categories/all-heroes.svg",
        }
    ]
    used_slugs = {"all"}
    categories = list_categories(include_hidden=False)
    linked_tag_ids = {int(item["linked_tag_id"]) for item in categories if item.get("linked_tag_id")}

    def append_filter(raw_slug: object, label: object, mapping: dict[str, str]) -> None:
        catalog_slug = str(raw_slug or "").strip().lower()
        if not catalog_slug or catalog_slug == "all":
            return
        slug = mapping.get(catalog_slug, catalog_slug)
        if slug in used_slugs:
            return
        used_slugs.add(slug)
        icon = FRONTEND_FILTER_ICONS.get(slug, "all-heroes.svg")
        filters.append(
            {
                "slug": slug,
                "label": str(label or slug).strip(),
                "icon": f"/surpriz/assets/icons/categories/{icon}",
            }
        )

    for category in categories:
        append_filter(category.get("slug"), category.get("name"), FRONTEND_CATEGORY_BY_CATALOG_SLUG)
    for tag in list_tags(include_hidden=False):
        if int(tag.get("id") or 0) in linked_tag_ids:
            continue
        append_filter(tag.get("slug"), tag.get("name"), FRONTEND_TAG_BY_CATALOG_SLUG)
    return filters


def _frontend_image_position(item: dict[str, object]) -> dict[str, int]:
    def clamp(value: object) -> int:
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return 50

    return {
        "x": clamp(item.get("cover_offset_x")),
        "y": clamp(item.get("cover_offset_y")),
    }


def _frontend_mobile_image_position(item: dict[str, object]) -> dict[str, int]:
    def clamp(value: object) -> int:
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return 50

    return {
        "x": clamp(item.get("mobile_cover_offset_x")),
        "y": clamp(item.get("mobile_cover_offset_y")),
    }


def _frontend_image_zoom(item: dict[str, object]) -> int:
    try:
        return max(100, min(200, int(item.get("image_zoom") or 100)))
    except (TypeError, ValueError):
        return 100


def _frontend_mobile_image_zoom(item: dict[str, object]) -> int:
    try:
        return max(100, min(200, int(item.get("mobile_image_zoom") or 100)))
    except (TypeError, ValueError):
        return 100


def _frontend_show_image_sources(item: dict[str, object]) -> dict[str, object]:
    slug = str(item.get("slug") or "").strip()
    hero_path = str(item.get("hero_file_path") or "").strip()
    generated = _GENERATED_CHARACTER_MEDIA_RE.fullmatch(hero_path)
    if generated:
        base_path = generated.group("base")
        maximum_width = int(generated.group("width"))
        generated_widths = tuple(
            sorted({width for width in (480, 768, 1280, maximum_width) if width <= maximum_width})
        )
        config = FRONTEND_SHOW_IMAGE_SOURCES.get(slug)
        source_width, source_height = (
            config["source_size"] if config else (maximum_width, round(maximum_width * 10 / 16))
        )
        return {
            "image": f"{base_path}/{generated_widths[-1]}.webp",
            "image_width": source_width,
            "image_height": source_height,
            "image_sources": {
                image_format: [
                    {"src": f"{base_path}/{width}.{image_format}", "width": width}
                    for width in generated_widths
                ]
                for image_format in ("avif", "webp")
            },
        }
    config = FRONTEND_SHOW_IMAGE_SOURCES.get(slug)
    if not config:
        return {}
    widths = tuple(config["widths"])
    source_width, source_height = config["source_size"]
    curated_prefix = f"/surpriz/assets/img/show-programs/cards/{slug}-"
    if hero_path and not hero_path.startswith((curated_prefix, "/wp-content/")):
        return {}
    base_path = f"/surpriz/assets/img/show-programs/cards/{slug}"
    return {
        "image": f"{base_path}-{max(widths)}.webp?v={FRONTEND_SHOW_IMAGE_VERSION}",
        "image_width": source_width,
        "image_height": source_height,
        "image_sources": {
            image_format: [
                {
                    "src": f"{base_path}-{width}.{image_format}?v={FRONTEND_SHOW_IMAGE_VERSION}",
                    "width": width,
                }
                for width in widths
            ]
            for image_format in ("avif", "webp")
        },
    }


def _build_frontend_show_cards() -> list[dict[str, object]]:
    shows: list[dict[str, object]] = []
    # Same curated ordering as characters: admin picks lead, the rest follow.
    for item in sort_by_featured(list(list_show_programs_for_public()), ENTITY_TYPE_SHOW_PROGRAM):
        slug = str(item.get("slug") or "").strip()
        name = str(item.get("name") or "Шоу-программа").strip()
        included_items = _split_show_text(item.get("included_items"))
        suitable_for = _split_show_text(item.get("suitable_for"))
        restrictions = _split_show_text(item.get("restrictions"))
        card: dict[str, object] = {
            "id": slug,
            "title": name,
            "description": str(
                item.get("short_description")
                or item.get("description")
                or "Описание программы уточняется."
            ).strip(),
            "image": str(item.get("hero_file_path") or "").strip(),
            "alt": name,
            "cta_label": "Выбрать программу",
            "href": f"/party-builder/?program={slug}",
            "detail_href": str(item.get("route") or f"/show-programs/{slug}/"),
            "active": True,
            "title_color": "#21165b",
            "image_position": _frontend_image_position(item),
            "image_zoom": _frontend_image_zoom(item),
            "cover_fit": "contain" if item.get("cover_fit") == "contain" else "cover",
            "mobile_image_position": _frontend_mobile_image_position(item),
            "mobile_image_zoom": _frontend_mobile_image_zoom(item),
            "mobile_cover_fit": "contain" if item.get("mobile_cover_fit") == "contain" else "cover",
            "categories": [],
            "placements": ["homepage", "catalog", "party_builder"],
            "duration_label": str(item.get("duration_label") or "").strip(),
            "price_label": str(item.get("price_label") or "").strip(),
            "age_label": str(item.get("age_label") or "").strip(),
            "variant_group_slug": str(item.get("variant_group_slug") or "").strip(),
            "variant_group_name": str(item.get("variant_group_name") or "").strip(),
            "variant_label": str(item.get("variant_label") or "").strip(),
            "included_items": included_items,
            "suitable_for": suitable_for,
            "restrictions": restrictions,
        }
        card.update(_frontend_show_image_sources(item))
        shows.append(card)
    return shows


def build_frontend_show_payload() -> dict[str, object]:
    """Return the lightweight public payload used by the show listing page."""
    return {"version": 1, "shows": _build_frontend_show_cards()}


def build_frontend_catalog_payload() -> dict[str, object]:
    """Return the new storefront schema from the canonical catalog database."""
    # Admin-curated order: picked slugs lead in the chosen order, the first
    # HOMEPAGE_SLOTS of them also fill the homepage carousel.
    curated = get_featured_slugs(ENTITY_TYPE_CHARACTER) or list(FRONTEND_HOMEPAGE_CHARACTER_SLUGS)
    character_rows = list_characters_for_public(entity_type=ENTITY_TYPE_CHARACTER)
    character_by_slug = {str(item.get("slug") or ""): item for item in character_rows}
    ordered_slugs = [slug for slug in curated if slug in character_by_slug]
    featured = set(ordered_slugs[:HOMEPAGE_SLOTS])
    ordered_characters = [character_by_slug[slug] for slug in ordered_slugs]
    ordered_characters.extend(
        item for item in character_rows if str(item.get("slug") or "") not in set(ordered_slugs)
    )

    characters: list[dict[str, object]] = []
    for item in ordered_characters:
        slug = str(item.get("slug") or "").strip()
        name = str(item.get("name") or "Персонаж").strip()
        description = str(item.get("short_description") or item.get("description") or "").strip()
        placements = ["catalog", "party_builder"]
        if slug in featured:
            placements.insert(0, "homepage")
        characters.append(
            {
                "id": slug,
                "title": name,
                "description": description,
                "image": str(item.get("hero_file_path") or "").strip(),
                "image_sources": _frontend_character_image_sources(item),
                "alt": f"{name} на детский праздник",
                "cta_label": "Заказать героя",
                "href": f"/party-builder/?character={slug}",
                "detail_href": str(item.get("route") or f"/character/{slug}/"),
                "active": True,
                "title_color": "#21165b",
                "image_position": _frontend_image_position(item),
                "image_zoom": _frontend_image_zoom(item),
                "cover_fit": "contain" if item.get("cover_fit") == "contain" else "cover",
                "mobile_image_position": _frontend_mobile_image_position(item),
                "mobile_image_zoom": _frontend_mobile_image_zoom(item),
                "mobile_cover_fit": "contain" if item.get("mobile_cover_fit") == "contain" else "cover",
                "categories": _frontend_character_categories(item),
                "placements": placements,
            }
        )

    shows = _build_frontend_show_cards()

    return {
        "version": 3,
        "settings": {"autoplay_enabled": True, "autoplay_speed": 18},
        "filters": _build_frontend_character_filters(),
        "characters": characters,
        "shows": shows,
        "partners": [
            {
                "id": partner["slug"],
                "name": partner["name"],
                "logo": partner["logo_path"],
                "href": partner["link_url"],
            }
            for partner in list_partners(only_active=True)
        ],
    }


def _static_public_file_exists(public_path: str) -> bool:
    normalized = public_path.strip()
    if not normalized or normalized.startswith(("http://", "https://", "//")):
        return True
    if not normalized.startswith("/"):
        return False

    if normalized.startswith("/_assets/content/"):
        normalized = normalized.replace("/_assets/content/", "/wp-content/", 1)
    elif normalized.startswith("/_assets/includes/"):
        normalized = normalized.replace("/_assets/includes/", "/wp-includes/", 1)

    return (STATIC_ROOT / normalized.lstrip("/")).exists()


def _safe_show_image(public_path: object) -> str:
    candidate = str(public_path or "").strip()
    if candidate and _static_public_file_exists(candidate):
        return candidate
    return DEFAULT_OG_IMAGE


def _show_program_summary(show: dict[str, object]) -> dict[str, object]:
    item = dict(show)
    raw_image = str(item.get("hero_file_path") or "").strip()
    item["has_image"] = bool(raw_image)
    item["route"] = f"{SHOW_PROGRAMS_ROUTE}{str(item.get('slug') or '').strip()}/"
    item["hero_file_path"] = raw_image
    item["fallback_image"] = DEFAULT_OG_IMAGE
    item["summary_text"] = (
        str(item.get("short_description") or item.get("description") or "Описание шоу-программы скоро появится.").strip()
        or "Описание шоу-программы скоро появится."
    )
    item["price_label"] = f"от {_format_money(int(item.get('base_price') or 0))}"
    item["duration_label"] = _format_duration(int(item.get("default_duration_minutes") or 0))
    item["age_label"] = _format_age(item.get("age_from"), item.get("age_to"))
    item["category_label"] = str(item.get("show_category") or "").strip()
    item["format_label"] = str(item.get("format_tags") or "").strip()
    item["included_items_list"] = _split_show_text(item.get("included_items"))
    item["suitable_for_list"] = _split_show_text(item.get("suitable_for"))
    item["restrictions_list"] = _split_show_text(item.get("restrictions"))
    item["video_url"] = str(item.get("video_url") or "").strip()
    try:
        program_addons = list_program_addons_for_public(int(item.get("id") or 0))
    except Exception:
        program_addons = []
    from .customer_store import _attach_program_gifts, _attach_program_promotions

    _attach_program_gifts(item, program_addons)
    _attach_program_promotions(item)
    return item


def _show_addon_summary(addon: dict[str, object]) -> dict[str, object]:
    item = dict(addon)
    raw_image = str(item.get("image_path") or "").strip()
    item["has_image"] = bool(raw_image)
    item["image_path"] = raw_image
    item["fallback_image"] = DEFAULT_OG_IMAGE
    item["summary_text"] = (
        str(item.get("short_description") or item.get("description") or "Описание доп. услуги скоро появится.").strip()
        or "Описание доп. услуги скоро появится."
    )
    item["price_label"] = f"от {_format_money(int(item.get('price') or 0))}"
    duration = int(item.get("duration_minutes") or 0)
    item["duration_label"] = _format_duration(duration) if duration > 0 else ""
    return item


def _plural(count: int, forms: tuple[str, str, str]) -> str:
    tail = abs(count) % 100
    if 11 <= tail <= 14:
        return forms[2]
    tail %= 10
    if tail == 1:
        return forms[0]
    if 2 <= tail <= 4:
        return forms[1]
    return forms[2]


def _srcset(url_for_width, widths: list[int], image_format: str) -> str:
    return ", ".join(f"{url_for_width(width, image_format)} {width}w" for width in widths)


def _show_detail_image(path: object) -> dict[str, str] | None:
    """Responsive sources for any show or character image stored in the catalog."""
    path = str(path or "").strip()
    if not path:
        return None
    generated = _GENERATED_CHARACTER_MEDIA_RE.fullmatch(path)
    card = _SHOW_CARD_MEDIA_RE.fullmatch(path)
    if generated:
        base = generated.group("base")
        maximum_width = int(generated.group("width"))
        widths = sorted({width for width in (480, 768, 1280, maximum_width) if width <= maximum_width})

        def url_for_width(width: int, image_format: str) -> str:
            return f"{base}/{width}.{image_format}"
    elif card:
        base = card.group("base")
        widths = [480, 768, 1200]

        def url_for_width(width: int, image_format: str) -> str:
            return f"{base}-{width}.{image_format}?v={FRONTEND_SHOW_IMAGE_VERSION}"
    else:
        sources = _frontend_character_image_sources({"hero_file_path": path})
        if not sources:
            return {"src": path, "avif": "", "webp": ""}
        return {
            "src": str(sources["fallback"]),
            "avif": ", ".join(f"{item['src']} {item['width']}w" for item in sources["avif"]),
            "webp": ", ".join(f"{item['src']} {item['width']}w" for item in sources["webp"]),
        }
    return {
        "src": url_for_width(widths[-1], "webp"),
        "avif": _srcset(url_for_width, widths, "avif"),
        "webp": _srcset(url_for_width, widths, "webp"),
    }


def _show_detail_assets() -> dict[str, object]:
    """Generated 3D icons and page backgrounds, picked up only when the files exist."""

    def url(path) -> str:
        return f"/v2/show-detail/{path.relative_to(SHOW_DETAIL_ASSET_DIR).as_posix()}?v={int(path.stat().st_mtime)}"

    icons_dir = SHOW_DETAIL_ASSET_DIR / "icons"
    icons = {path.stem: url(path) for path in sorted(icons_dir.glob("*.webp"))} if icons_dir.is_dir() else {}
    backgrounds = {
        name: url(SHOW_DETAIL_ASSET_DIR / f"{name}.webp")
        for name in ("bg-desktop", "bg-mobile")
        if (SHOW_DETAIL_ASSET_DIR / f"{name}.webp").is_file()
    }
    return {"icons": icons, "backgrounds": backgrounds}


def _show_program_features(show: dict[str, object], *, skip_gift_choice: bool) -> list[dict[str, str]]:
    """Admin-edited items when present, otherwise the legacy «Что входит» text."""
    features = list(show.get("program_features") or []) or show_features_from_text(show.get("included_items"))
    if skip_gift_choice:
        # The gift has its own tile, so a «маски или шары» line would repeat it.
        features = [item for item in features if "маски или шары" not in item["text"].casefold()]
    return features


def _show_cast_members(show: dict[str, object]) -> list[str]:
    return list(show.get("program_cast") or FIXED_CAST_PROGRAM_DETAILS.get(str(show.get("slug") or ""), ()))


def _show_gift_label(show: dict[str, object]) -> str:
    for group in show.get("gift_choice_groups") or []:
        names = [str(addon.get("name") or "").strip() for addon in group.get("addons") or []]
        names = [name for name in names if name]
        if names:
            label = " или ".join(names).casefold()
            return label[0].upper() + label[1:]
    bundles = [str(addon.get("name") or "").strip() for addon in show.get("gift_bundles") or []]
    return ", ".join(name for name in bundles if name)


def _show_price_tiers(show: dict[str, object]) -> list[dict[str, object]]:
    """Price by hero count, priced exactly like the builder does it."""
    included = int(show.get("included_characters_count") or 0)
    if _show_cast_members(show) or included <= 0 or int(show.get("extra_character_price_3") or 0) <= 0:
        return []
    base_price = int(show.get("base_price") or 0)
    tiers: list[dict[str, object]] = []
    for count in range(included, included + 3):
        tiers.append(
            {
                "count": count,
                "label": f"{count} {_plural(count, ('герой', 'героя', 'героев'))}",
                "price_label": _format_money(base_price + calculate_program_character_surcharge(show, count)),
            }
        )
    return tiers


def _show_gallery(show: dict[str, object]) -> list[dict[str, object]]:
    hero_path = str(show.get("hero_file_path") or "").strip()
    paths: list[str] = [hero_path] if hero_path else []
    media = sorted(
        (item for item in show.get("media") or [] if str(item.get("media_type") or "image") == "image"),
        key=lambda item: int(item.get("sort_order") or 0),
    )
    paths.extend(str(item.get("file_path") or "").strip() for item in media)
    desktop = _frontend_image_position(show)
    mobile = _frontend_mobile_image_position(show)
    hero_style = f"--pos: {desktop['x']}% {desktop['y']}%; --pos-m: {mobile['x']}% {mobile['y']}%"
    gallery: list[dict[str, object]] = []
    for path in dict.fromkeys(path for path in paths if path):
        image = _show_detail_image(path)
        if image:
            gallery.append({**image, "style": hero_style if path == hero_path else ""})
    return gallery


def _show_variants(show: dict[str, object], candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    group = str(show.get("variant_group_slug") or "").strip()
    if not group:
        return []
    siblings = sorted(
        (item for item in candidates if str(item.get("variant_group_slug") or "").strip() == group),
        key=lambda item: (int(item.get("sort_order") or 0), str(item.get("name") or "")),
    )
    if len(siblings) < 2:
        return []
    variants: list[dict[str, object]] = []
    for item in siblings:
        slug = str(item.get("slug") or "")
        variants.append(
            {
                "slug": slug,
                "label": str(item.get("variant_label") or item.get("name") or "").strip(),
                "name": str(item.get("name") or "").strip(),
                "route": f"{SHOW_PROGRAMS_ROUTE}{slug}/",
                "is_current": slug == show.get("slug"),
                "price_label": _format_money(int(item.get("base_price") or 0)),
                "duration_label": _format_duration(int(item.get("default_duration_minutes") or 0)),
                "summary": str(item.get("short_description") or "").strip(),
                "features": _show_program_features(item, skip_gift_choice=True),
            }
        )
    return variants


def _show_cast(show: dict[str, object]) -> dict[str, object]:
    fixed = _show_cast_members(show)
    if fixed:
        count = len(fixed)
        items = [item.casefold() for item in _split_show_text(str(show.get("included_items") or "").replace(",", ";"))]
        return {
            "kind": "fixed",
            "members": list(fixed),
            "with_dj": any("диджей" in item and "дополнительн" not in item for item in items),
            "fact": fixed[0] if count == 1 else f"{count} {_plural(count, ('артист', 'артиста', 'артистов'))} в образах",
        }
    included = int(show.get("included_characters_count") or 0)
    if included > 0:
        return {
            "kind": "choice",
            "count": included,
            "fact": f"{included} {_plural(included, ('герой', 'героя', 'героев'))} на выбор",
            "note": (
                f"{included} {_plural(included, ('герой входит', 'героя входят', 'героев входят'))} в цену — "
                "выберите любых из каталога. Нажмите на героя, и конструктор откроется "
                "с этой программой и выбранным героем."
            ),
        }
    return {"kind": "none"}


_ORDINAL_HERO = {2: "Второй", 3: "Третий", 4: "Четвёртый", 5: "Пятый"}


def _show_price_note(show: dict[str, object], tiers: list[dict[str, object]]) -> str:
    if not tiers:
        return ""
    included = int(tiers[0]["count"])
    extra = _format_money(int(show.get("extra_character_price_3") or 0))
    ordinal = _ORDINAL_HERO.get(included + 1, "Следующий")
    return f"{tiers[0]['label'].capitalize()} уже в цене. {ordinal} — плюс {extra}."


def _show_variants_note(variants: list[dict[str, object]]) -> str:
    durations = {str(item["duration_label"]) for item in variants}
    if len(durations) == 1:
        return f"Все форматы длятся {durations.pop()} и отличаются наполнением — выберите тот, что подходит вашему празднику."
    return "Форматы отличаются длительностью и наполнением — выберите тот, что подходит вашему празднику."


def _show_featured_characters(show_slug: str) -> tuple[list[dict[str, object]], int]:
    rows = list_characters_for_public(entity_type=ENTITY_TYPE_CHARACTER)
    by_slug = {str(item.get("slug") or ""): item for item in rows}
    curated = get_featured_slugs(ENTITY_TYPE_CHARACTER) or list(FRONTEND_HOMEPAGE_CHARACTER_SLUGS)
    ordered = [by_slug[slug] for slug in curated if slug in by_slug]
    curated_slugs = set(curated)
    ordered.extend(item for item in rows if str(item.get("slug") or "") not in curated_slugs)
    characters: list[dict[str, object]] = []
    for item in ordered:
        image = _show_detail_image(item.get("hero_file_path"))
        if not image:
            continue
        slug = str(item.get("slug") or "")
        position = _frontend_image_position(item)
        characters.append(
            {
                "name": str(item.get("name") or "").strip(),
                "image": image,
                "position": f"{position['x']}% {position['y']}%",
                "href": f"/party-builder/?{urlencode({'program': show_slug, 'character': slug})}",
            }
        )
        if len(characters) >= SHOW_DETAIL_FEATURED_CHARACTERS:
            break
    return characters, len(rows)


def _show_faq(show: dict[str, object], tiers: list[dict[str, object]], cast: dict[str, object]) -> list[dict[str, str]]:
    name = str(show.get("name") or "")
    price = _format_money(int(show.get("base_price") or 0))
    duration = str(show.get("duration_label") or "")
    if tiers:
        extra = _format_money(int(show.get("extra_character_price_3") or 0))
        count = int(cast.get("count") or 0)
        price_answer = (
            f"{price} за {duration}, {count} {_plural(count, ('герой входит', 'героя входят', 'героев входят'))} в цену. "
            f"Следующий герой — плюс {extra}. Итоговая сумма зависит от числа героев и длительности "
            "и видна сразу в конструкторе праздника."
        )
    elif cast.get("kind") == "fixed":
        price_answer = f"{price} за {duration} — это цена за весь состав. Итоговая сумма видна сразу в конструкторе праздника."
    else:
        price_answer = f"{price} за {duration}. Итоговая сумма видна сразу в конструкторе праздника."
    return [
        {"question": f"Сколько стоит «{name}»?", "answer": price_answer},
        {"question": "Нужна ли предоплата?", "answer": "Нет. Оплата после мероприятия — наличными или переводом на карту."},
        {
            "question": "За сколько дней нужно бронировать праздник?",
            "answer": (
                "Обычно за 3–7 дней. Онлайн-бронирование доступно минимум за 24 часа до начала. "
                f"Если праздник сегодня или ночью — звоните напрямую: {PHONE_DISPLAY}."
            ),
        },
        {
            "question": "Куда вы выезжаете?",
            "answer": "Ташкент и Ташкентская область: квартиры и дома, детские сады, школы, кафе, корпоративные площадки.",
        },
    ]


def _build_variant_summary(variant: dict[str, object], summary_by_slug: dict[str, dict[str, object]]) -> dict[str, object]:
    """Combine raw variant data with the enriched summary fields used by the catalog template."""
    slug = str(variant.get("slug") or "").strip()
    enriched = summary_by_slug.get(slug) or {}
    summary_text = (
        str(variant.get("summary_text") or "").strip()
        or str(variant.get("short_description") or "").strip()
        or str(enriched.get("summary_text") or "").strip()
        or "Описание варианта скоро появится."
    )
    description_text = (
        str(variant.get("description") or "").strip()
        or str(enriched.get("description") or "").strip()
    )
    included = list(_split_show_text(variant.get("included_items") or enriched.get("included_items")))
    variant_image = str(enriched.get("hero_file_path") or "").strip()
    return {
        "slug": slug,
        "label": str(variant.get("label") or variant.get("name") or "Вариант").strip(),
        "name": str(variant.get("name") or enriched.get("name") or "").strip(),
        "route": f"{SHOW_PROGRAMS_ROUTE}{slug}/",
        "summary_text": summary_text,
        "description": description_text,
        "included_items_list": included,
        "hero_file_path": variant_image,
        "has_image": bool(variant_image),
        "price": int(variant.get("price") or enriched.get("base_price") or 0),
        "price_label": str(variant.get("price_label") or enriched.get("price_label") or "цена по запросу"),
        "duration_label": str(variant.get("duration_label") or enriched.get("duration_label") or "уточняется"),
        "age_label": str(variant.get("age_label") or enriched.get("age_label") or "").strip(),
        "category_label": str(variant.get("show_category") or enriched.get("category_label") or "").strip(),
        "format_label": str(variant.get("format_tags") or enriched.get("format_label") or "").strip(),
        "promotions": variant.get("promotions") or enriched.get("promotions") or [],
        "has_gifts": bool(variant.get("has_gifts") or enriched.get("has_gifts")),
    }


def _build_show_groups(grouped: list[dict[str, object]], summary_by_slug: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Turn customer_store groups into template-friendly cards with carousel data for multi-variant groups."""
    cards: list[dict[str, object]] = []
    for group in grouped:
        primary_raw = group.get("primary") or {}
        primary_slug = str(primary_raw.get("slug") or "").strip()
        primary_summary = summary_by_slug.get(primary_slug) or _show_program_summary(dict(primary_raw))

        if not group.get("is_group"):
            card = dict(primary_summary)
            card["is_group"] = False
            card["search_haystack"] = " ".join(
                str(part)
                for part in [
                    card.get("name"),
                    card.get("summary_text"),
                    card.get("duration_label"),
                    card.get("age_label"),
                    card.get("category_label"),
                    card.get("format_label"),
                ]
                if part
            )
            cards.append(card)
            continue

        variant_summaries = [_build_variant_summary(v, summary_by_slug) for v in group.get("variants") or []]
        if not variant_summaries:
            continue

        prices = [int(v.get("price") or 0) for v in variant_summaries if int(v.get("price") or 0) > 0]
        if prices:
            min_price = min(prices)
            max_price = max(prices)
            if min_price == max_price:
                price_range_label = f"от {_format_money(min_price)}"
            else:
                price_range_label = f"от {_format_money(min_price)} до {_format_money(max_price)}"
        else:
            price_range_label = str(primary_summary.get("price_label") or "цена по запросу")

        durations = {str(v.get("duration_label") or "").strip() for v in variant_summaries if v.get("duration_label")}
        duration_label = next(iter(durations)) if len(durations) == 1 else str(primary_summary.get("duration_label") or "")
        age_labels = {str(v.get("age_label") or "").strip() for v in variant_summaries if v.get("age_label")}
        age_label = next(iter(age_labels)) if len(age_labels) == 1 else str(primary_summary.get("age_label") or "")

        haystack_parts: list[str] = [str(group.get("name") or "")]
        for variant in variant_summaries:
            for key in ("label", "name", "summary_text", "description", "category_label", "format_label", "age_label"):
                value = variant.get(key)
                if value:
                    haystack_parts.append(str(value))
            for item in variant.get("included_items_list") or []:
                haystack_parts.append(str(item))

        cards.append({
            "is_group": True,
            "slug": str(group.get("group_slug") or group.get("slug") or ""),
            "group_slug": str(group.get("group_slug") or ""),
            "name": str(group.get("name") or primary_summary.get("name") or "Шоу-программа"),
            "primary": primary_summary,
            "variants": variant_summaries,
            "variants_count": len(variant_summaries),
            "price_range_label": price_range_label,
            "duration_label": duration_label,
            "age_label": age_label,
            "route": variant_summaries[0].get("route"),
            "has_image": bool(primary_summary.get("has_image")),
            "hero_file_path": primary_summary.get("hero_file_path") or "",
            "search_haystack": " ".join(part for part in haystack_parts if part),
        })
    return cards


def build_show_programs_page() -> PageBundle | None:
    raw_shows = list_characters_for_public(entity_type=ENTITY_TYPE_SHOW_PROGRAM)
    shows_summary = [_show_program_summary(item) for item in raw_shows]
    summary_by_slug = {str(item.get("slug") or ""): item for item in shows_summary}

    try:
        grouped = list_show_programs_grouped_for_public()
    except Exception:
        grouped = []

    show_groups = _build_show_groups(grouped, summary_by_slug)
    if not show_groups:
        show_groups = [
            {
                **item,
                "is_group": False,
                "search_haystack": " ".join(
                    str(part)
                    for part in [
                        item.get("name"),
                        item.get("summary_text"),
                        item.get("duration_label"),
                        item.get("age_label"),
                        item.get("category_label"),
                        item.get("format_label"),
                    ]
                    if part
                ),
            }
            for item in shows_summary
        ]

    description = "Выберите готовую шоу-программу для детского праздника или соберите индивидуальный вариант."
    og_image = DEFAULT_OG_IMAGE
    for card in show_groups:
        candidate = str(card.get("hero_file_path") or "").strip()
        if candidate:
            og_image = candidate
            break

    content_html = render_template(
        "site/show_programs_content.html",
        shows=show_groups,
        heading="Шоу-программы",
        description=description,
    )
    return _build_page_bundle(
        route=SHOW_PROGRAMS_ROUTE,
        title="Шоу-программы | Surpriz",
        description=description,
        canonical_path=SHOW_PROGRAMS_ROUTE,
        content_html=content_html,
        og_image=og_image,
        active="shows",
    )


def build_show_program_page(slug: str) -> PageBundle | None:
    show = get_character_by_slug(slug)
    if not show or show.get("entity_type") != ENTITY_TYPE_SHOW_PROGRAM or show.get("status") != "active":
        return None

    show = _show_program_summary(show)
    show["addons"] = [
        _show_addon_summary(addon)
        for addon in list_program_addons_for_public(int(show["id"]))
        if str(addon.get("gift_mode") or "none") == "none"
        and not addon.get("is_free_choice")
        and int(addon.get("price") or 0) > 0
    ]
    canonical_path = f"{SHOW_PROGRAMS_ROUTE}{show['slug']}/"
    description = str(show.get("seo_description") or show.get("short_description") or show.get("description") or "").strip()
    if not description:
        description = (
            f"{show['name']} — шоу-программа для детского праздника в Ташкенте. "
            "Выезд по городу и области, оплата после мероприятия."
        )
    # Город в заголовке — основной коммерческий запрос ниши; без него страница
    # конкурирует только по названию программы.
    page_title = (
        str(show.get("seo_title") or "").strip()
        or f"{show['name']} на детский праздник в Ташкенте — заказать | Surpriz"
    )

    current_group = str(show.get("variant_group_slug") or "").strip()
    related_shows: list[dict[str, object]] = []
    try:
        candidates = list_characters_for_public(entity_type=ENTITY_TYPE_SHOW_PROGRAM)
    except Exception:
        candidates = []

    # Иногда у программы пустая медиа-связь, но list-запрос находит hero
    # по hero_media_id — берём тот же путь, что показывает каталог.
    if not show.get("hero_file_path"):
        for candidate in candidates:
            if candidate.get("slug") == show.get("slug") and candidate.get("hero_file_path"):
                show["hero_file_path"] = candidate["hero_file_path"]
                show["has_image"] = True
                break

    seen_groups: set[str] = set()
    deferred: list[dict[str, object]] = []
    for candidate in candidates:
        if int(candidate.get("id") or 0) == int(show.get("id") or 0):
            continue
        candidate_group = str(candidate.get("variant_group_slug") or "").strip()
        if current_group and candidate_group == current_group:
            continue
        # Не больше одного представителя группы вариантов в «Похожих»;
        # остальные — в конец, если не хватит других шоу.
        if candidate_group and candidate_group in seen_groups:
            deferred.append(candidate)
            continue
        if candidate_group:
            seen_groups.add(candidate_group)
        related_shows.append(_show_program_summary(candidate))
        if len(related_shows) >= 3:
            break
    for candidate in deferred:
        if len(related_shows) >= 3:
            break
        related_shows.append(_show_program_summary(candidate))

    for item in related_shows:
        position = _frontend_image_position(item)
        item["image"] = _show_detail_image(item.get("hero_file_path"))
        item["image_style"] = f"object-position: {position['x']}% {position['y']}%"

    variants = _show_variants(show, candidates)
    gift_label = _show_gift_label(show)
    cast = _show_cast(show)
    price_tiers = _show_price_tiers(show)
    restrictions = list(show.get("restrictions_list") or [])
    indoor_only = any("помещени" in item.casefold() for item in restrictions)
    facts = [{"icon": "clock", "label": "Длительность", "value": show["duration_label"]}]
    if cast["kind"] != "none":
        facts.append({"icon": "users", "label": "Состав" if cast["kind"] == "fixed" else "Герои", "value": cast["fact"]})
    if gift_label:
        facts.append({"icon": "gift", "label": "Подарок", "value": gift_label})
    facts.append(
        {"icon": "home", "label": "Площадка", "value": "Только в помещении"}
        if indoor_only
        else {"icon": "map-pin", "label": "Выезд", "value": "Ташкент и область"}
    )
    featured_characters, characters_total = (
        _show_featured_characters(str(show["slug"])) if cast["kind"] == "choice" else ([], 0)
    )

    content_html = render_template(
        "site/show_program_content.html",
        show=show,
        related_shows=related_shows,
        gallery=_show_gallery(show),
        variants=variants,
        variants_note=_show_variants_note(variants) if variants else "",
        features=_show_program_features(show, skip_gift_choice=bool(gift_label)),
        gift_label=gift_label,
        facts=facts[:4],
        cast=cast,
        price_tiers=price_tiers,
        price_value=_format_money(int(show.get("base_price") or 0)),
        restrictions=restrictions,
        featured_characters=featured_characters,
        characters_total=characters_total,
        faq=_show_faq(show, price_tiers, cast),
        price_note=_show_price_note(show, price_tiers),
        characters_label=f"Все {characters_total} {_plural(characters_total, ('герой', 'героя', 'героев'))}",
        stylesheet_version=_asset_version("v2/show-detail.css"),
        assets=_show_detail_assets(),
        phone_display=PHONE_DISPLAY,
        phone_tel=PHONE_TEL,
        telegram_url=TELEGRAM_URL,
    )
    return _build_page_bundle(
        route=canonical_path,
        title=page_title,
        description=description,
        canonical_path=canonical_path,
        content_html=content_html,
        og_image=str(show.get("hero_file_path") or DEFAULT_OG_IMAGE),
        active="shows",
    )


def build_catalog_page(
    category_slug: str | None = None,
    tag_slug: str | None = None,
    *,
    page_number: int = 1,
    search_query: str = "",
) -> tuple[PageBundle | None, str | None]:
    search_query = search_query.strip()
    categories = list_categories(include_hidden=False)
    tags = [tag for tag in list_tags(include_hidden=False) if tag["slug"] != "all"]
    active_category = get_category_by_slug(category_slug) if category_slug else None
    active_tag = get_tag_by_slug(tag_slug) if tag_slug else None
    effective_category = active_category if active_category and active_category["slug"] != "all" else None
    effective_tag = active_tag if active_tag and active_tag["slug"] != "all" else None
    if search_query:
        category_slug = None
        tag_slug = None
        active_category = None
        active_tag = None
        effective_category = None
        effective_tag = None

    if category_slug and category_slug != "all":
        if not active_category or not active_category["is_visible"]:
            return None, "/catalog/"

    if tag_slug and tag_slug != "all":
        if not active_tag or not active_tag["is_visible"]:
            return None, "/catalog/"

    all_characters = list_characters_for_public(category_slug=category_slug, tag_slug=tag_slug, search=search_query)
    current_scope = effective_category or effective_tag
    scope_label = current_scope["name"] if current_scope else "Все персонажи"
    heading = "Каталог персонажей"
    if effective_tag:
        heading = f"Тег: {effective_tag['name']}"
    elif effective_category:
        heading = effective_category["name"]

    description = (
        (current_scope or {}).get("description")
        or "Подберите подходящего персонажа для детского праздника в Ташкенте. В каталоге собраны популярные герои для ярких и запоминающихся праздников."
    )
    if search_query:
        heading = "Результаты поиска"
        scope_label = f"Поиск: {search_query}"
        description = f"Показываем костюмы по запросу «{search_query}». Поиск понимает регистр, кириллицу, латиницу и слова из мини-словаря в админке."
    page_title = f"{heading} | Surpriz"
    base_path = "/catalog/"
    if effective_category:
        base_path = effective_category["route"]
    elif effective_tag:
        base_path = effective_tag["route"]

    total_items = len(all_characters)
    total_pages = max(1, (total_items + CATALOG_ITEMS_PER_PAGE - 1) // CATALOG_ITEMS_PER_PAGE)
    if page_number < 1:
        return None, _catalog_page_path(base_path, 1, search_query=search_query)
    if page_number > total_pages:
        return None, _catalog_page_path(base_path, total_pages, search_query=search_query)

    start_index = (page_number - 1) * CATALOG_ITEMS_PER_PAGE
    end_index = start_index + CATALOG_ITEMS_PER_PAGE
    characters = all_characters[start_index:end_index]
    for character in characters:
        raw_slugs = character.get("category_slugs") or []
        raw_names = character.get("category_names") or []
        if isinstance(raw_slugs, str):
            raw_slugs = raw_slugs.split(",")
        if isinstance(raw_names, str):
            raw_names = raw_names.split(",")
        character["primary_category_name"] = next(
            (
                name.strip()
                for slug, name in zip(raw_slugs, raw_names)
                if str(slug).strip() and str(slug).strip() != "all" and str(name).strip()
            ),
            "",
        )
    canonical_path = _catalog_page_path(base_path, page_number, search_query=search_query)
    if page_number > 1:
        page_title = f"{heading} | Страница {page_number} | Surpriz"

    og_image = DEFAULT_OG_IMAGE
    for character in characters:
        if character.get("hero_file_path"):
            og_image = character["hero_file_path"]
            break

    public_categories: list[dict[str, object]] = []
    for category in categories:
        category_data = dict(category)
        if category_data["slug"] == "all":
            category_data["character_count"] = total_items
        public_categories.append(category_data)

    pagination = {
        "page_number": page_number,
        "total_pages": total_pages,
        "total_items": total_items,
        "page_size": CATALOG_ITEMS_PER_PAGE,
        "pages": [
            {
                "number": number,
                "url": _catalog_page_path(base_path, number, search_query=search_query),
                "is_current": number == page_number,
            }
            for number in range(1, total_pages + 1)
        ],
        "prev_url": _catalog_page_path(base_path, page_number - 1, search_query=search_query) if page_number > 1 else "",
        "next_url": _catalog_page_path(base_path, page_number + 1, search_query=search_query) if page_number < total_pages else "",
        "start_item": start_index + 1 if total_items else 0,
        "end_item": min(end_index, total_items),
    }

    content_html = render_template(
        "site/catalog_content.html",
        heading=heading,
        description=description,
        categories=public_categories,
        tags=tags,
        characters=characters,
        active_category_slug=effective_category["slug"] if effective_category else "all",
        active_tag_slug=effective_tag["slug"] if effective_tag else "",
        active_scope_label=scope_label,
        search_query=search_query,
        pagination=pagination,
    )
    page = _build_page_bundle(
        route=canonical_path,
        title=page_title,
        description=description,
        canonical_path=canonical_path,
        content_html=content_html,
        og_image=og_image,
        active="catalog",
    )
    return page, None


def build_character_page(slug: str) -> PageBundle | None:
    character = get_character_by_slug(slug)
    if not character:
        return None

    if character["entity_type"] == ENTITY_TYPE_SHOW_PROGRAM:
        related_characters = [
            item
            for item in list_characters(status="active", entity_type=ENTITY_TYPE_SHOW_PROGRAM)
            if item["id"] != character["id"]
        ][:4]
    else:
        all_candidates = [
            item
            for item in list_characters_for_public(entity_type=ENTITY_TYPE_CHARACTER)
            if item["id"] != character["id"]
        ]
        primary_category_slug = ""
        for category in character.get("categories", []):
            slug = str(category.get("slug") or "").strip()
            if slug and slug != "all":
                primary_category_slug = slug
                break

        if primary_category_slug:
            same_category = [
                item for item in all_candidates if primary_category_slug in (item.get("category_slugs") or [])
            ]
            if len(same_category) >= 4:
                related_characters = same_category[:4]
            else:
                seen_ids = {item["id"] for item in same_category}
                fallback_items = [item for item in all_candidates if item["id"] not in seen_ids]
                related_characters = (same_category + fallback_items)[:4]
        else:
            related_characters = all_candidates[:4]
    description = character["seo_description"] or character["short_description"] or character["description"]
    page_title = character["seo_title"] or f"{character['name']} | Surpriz"
    canonical_path = character["route"]
    og_image = character.get("hero_file_path") or DEFAULT_OG_IMAGE
    # Characters are not sold on their own — the show programme sets the price, and
    # base_price on a character row is an internal surcharge for a couple of slugs.
    # Printing it as a retail price told visitors "от 25 000 сум" for a top-up.
    base_price = int(character.get("base_price") or 0)
    character["price_label"] = (
        f"от {_format_money(base_price)}"
        if character.get("is_show_program") and base_price > 0
        else ""
    )

    content_html = render_template(
        "site/character_content.html",
        character=character,
        related_characters=related_characters,
        phone_display=PHONE_DISPLAY,
        phone_tel=PHONE_TEL,
        telegram_url=TELEGRAM_URL,
    )
    return _build_page_bundle(
        route=canonical_path,
        title=page_title,
        description=description,
        canonical_path=canonical_path,
        content_html=content_html,
        og_image=og_image,
        active="shows" if character["entity_type"] == ENTITY_TYPE_SHOW_PROGRAM else "catalog",
    )
