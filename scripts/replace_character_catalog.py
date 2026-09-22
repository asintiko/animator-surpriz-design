#!/usr/bin/env python3
"""Atomically replace the active character catalog from the landing manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable
from urllib.parse import parse_qs, urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "content/data/admin/site_admin.sqlite3"
DEFAULT_MANIFEST = PROJECT_ROOT.parent / "surprizopus/data/catalogs.json"
EXPECTED_CHARACTER_COUNT = 56
MANAGED_META_KEY = "curated_character_catalog_sha256_v1"

LEGACY_SLUGS: dict[str, tuple[str, ...]] = {
    "naruto": ("naruto-sakura",),
    "digital-circus": ("pony",),
    "lol-mascot": ("lol-dolls",),
    "labubu-quad": ("trolls", "labubu"),
    "winnie-pooh": ("winnie-tigger", "winnie-the-pooh"),
    "spiderman-n1": ("spiderman", "spider-man"),
    "kuromi-melody": ("sanrio-kuromi-melody",),
    "superman-supergirl": ("superman-superwoman",),
}

CATEGORY_TAXONOMY: dict[str, tuple[str, str, int]] = {
    "superheroes": ("supergeroi", "Супергерои", 10),
    "princesses": ("skazochnye", "Принцессы", 20),
    "cartoons": ("multiki", "Мультгерои", 30),
}
TAG_TAXONOMY: dict[str, tuple[str, str, int]] = {
    "boys": ("malchikam", "Мальчикам", 10),
    "girls": ("devochkam", "Девочкам", 20),
}


@dataclass(frozen=True)
class CatalogItem:
    slug: str
    name: str
    description: str
    alt_text: str
    search_terms: str
    image_path: str
    image_filename: str
    categories: tuple[str, ...]
    sort_order: int
    cover_offset_x: int
    cover_offset_y: int
    image_zoom: int
    base_price: int
    included_items: str
    ensemble_members: tuple[str, ...]
    ensemble_included_count: int
    ensemble_extra_member_price: int


@dataclass(frozen=True)
class PlannedItem:
    item: CatalogItem
    character_id: int | None
    current_slug: str | None
    match_reason: str


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _manifest_slug(raw_item: dict[str, object]) -> str:
    query = parse_qs(urlsplit(str(raw_item.get("href") or "")).query)
    values = query.get("character") or []
    if values:
        return str(values[0]).strip().lower()
    return str(raw_item.get("id") or "").strip().lower().removeprefix("character-")


def _bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _text_values(value: object, *, field: str, slug: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = (value.strip(),)
    elif isinstance(value, list):
        values = tuple(str(item).strip() for item in value)
    else:
        raise ValueError(f"{field} must be a string or list for {slug}")
    if any(not item for item in values):
        raise ValueError(f"{field} contains an empty value for {slug}")
    return tuple(dict.fromkeys(values))


def load_manifest(manifest: Path) -> tuple[bytes, list[CatalogItem]]:
    manifest = manifest.expanduser().resolve()
    if not manifest.is_file():
        raise FileNotFoundError(f"Manifest does not exist: {manifest}")

    raw = manifest.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    raw_characters = payload.get("characters") if isinstance(payload, dict) else None
    if not isinstance(raw_characters, list):
        raise ValueError("Manifest must contain a characters list")
    if len(raw_characters) != EXPECTED_CHARACTER_COUNT:
        raise ValueError(
            f"Manifest must contain exactly {EXPECTED_CHARACTER_COUNT} character cards; "
            f"found {len(raw_characters)}"
        )

    manifest_root = manifest.parent.parent
    items: list[CatalogItem] = []
    seen_slugs: set[str] = set()
    seen_images: set[str] = set()
    for sort_order, raw_item in enumerate(raw_characters, start=1):
        if not isinstance(raw_item, dict) or raw_item.get("active") is not True:
            raise ValueError(f"All {EXPECTED_CHARACTER_COUNT} character cards must be explicitly active")

        slug = _manifest_slug(raw_item)
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError(f"Invalid character slug: {slug!r}")
        if slug in seen_slugs:
            raise ValueError(f"Duplicate character slug: {slug}")

        name = str(raw_item.get("title") or "").strip()
        description = str(raw_item.get("description") or "").strip()
        alt_text = str(raw_item.get("alt") or name).strip()
        if not name or not description or not alt_text:
            raise ValueError(f"Character content is incomplete: {slug}")

        relative_image = str(raw_item.get("image") or "").strip().lstrip("/")
        image_parts = PurePosixPath(relative_image).parts
        if (
            not relative_image.startswith("assets/img/characters/")
            or ".." in image_parts
            or PurePosixPath(relative_image).suffix.lower() != ".webp"
        ):
            raise ValueError(f"Invalid character image path for {slug}: {relative_image}")
        image_file = manifest_root / Path(*image_parts)
        if not image_file.is_file():
            raise FileNotFoundError(f"Character image does not exist: {image_file}")
        image_filename = PurePosixPath(relative_image).name
        if image_filename in seen_images:
            raise ValueError(f"Duplicate character image: {image_filename}")

        raw_categories = raw_item.get("categories") or []
        if not isinstance(raw_categories, list):
            raise ValueError(f"Character categories must be a list: {slug}")
        categories = tuple(
            dict.fromkeys(str(value).strip().lower() for value in raw_categories)
        )
        unknown_categories = set(categories) - (CATEGORY_TAXONOMY.keys() | TAG_TAXONOMY.keys())
        if unknown_categories:
            raise ValueError(
                f"Unknown categories for {slug}: {', '.join(sorted(unknown_categories))}"
            )

        image_position = raw_item.get("image_position") or {}
        if not isinstance(image_position, dict):
            image_position = {}

        ensemble_members = _text_values(
            raw_item.get("ensemble_members"), field="ensemble_members", slug=slug
        )
        if len(ensemble_members) == 1 or len(ensemble_members) > 4:
            raise ValueError(f"Character ensemble must contain 2 to 4 members: {slug}")
        ensemble_included_count = _bounded_int(
            raw_item.get("ensemble_included_count"), 2, 0, 4
        )
        ensemble_extra_member_price = _bounded_int(
            raw_item.get("ensemble_extra_member_price"), 0, 0, 10_000_000
        )
        ensemble_mode = str(raw_item.get("ensemble_mode") or "").strip()
        if not ensemble_members:
            if ensemble_mode:
                raise ValueError(f"ensemble_mode requires ensemble_members: {slug}")
            ensemble_included_count = 2
            ensemble_extra_member_price = 0
        elif len(ensemble_members) == 2:
            if (
                ensemble_mode != "fixed_pair"
                or ensemble_included_count != 2
                or ensemble_extra_member_price != 0
            ):
                raise ValueError(f"Fixed pair pricing is invalid for {slug}")
        elif (
            ensemble_mode != "choose_any"
            or ensemble_included_count != 2
            or ensemble_extra_member_price != 0
        ):
            raise ValueError(f"Selectable group pricing is invalid for {slug}")

        base_price = _bounded_int(raw_item.get("base_price"), 0, 0, 100_000_000)
        included_items = _text_values(
            raw_item.get("included_items"), field="included_items", slug=slug
        )
        service_notes = _text_values(
            raw_item.get("service_notes"), field="service_notes", slug=slug
        )
        search_fragments = (
            name,
            alt_text,
            *ensemble_members,
            *included_items,
            *service_notes,
            str(raw_item.get("costume_type") or "").strip(),
            str(raw_item.get("pricing_note") or "").strip(),
        )
        items.append(
            CatalogItem(
                slug=slug,
                name=name,
                description=description,
                alt_text=alt_text,
                search_terms=" ".join(
                    fragment for fragment in dict.fromkeys(search_fragments) if fragment
                ),
                image_path=f"/surpriz/{relative_image}",
                image_filename=image_filename,
                categories=categories,
                sort_order=sort_order,
                cover_offset_x=_bounded_int(image_position.get("x"), 50, 0, 100),
                cover_offset_y=_bounded_int(image_position.get("y"), 50, 0, 100),
                image_zoom=_bounded_int(raw_item.get("image_zoom"), 100, 100, 200),
                base_price=base_price,
                included_items=", ".join(included_items),
                ensemble_members=ensemble_members,
                ensemble_included_count=ensemble_included_count,
                ensemble_extra_member_price=ensemble_extra_member_price,
            )
        )
        seen_slugs.add(slug)
        seen_images.add(image_filename)

    if len(seen_images) != EXPECTED_CHARACTER_COUNT:
        raise ValueError(
            f"Manifest must reference exactly {EXPECTED_CHARACTER_COUNT} unique images"
        )
    return raw, items


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def validate_schema(connection: sqlite3.Connection) -> set[str]:
    required_tables = {
        "managed_characters",
        "managed_character_media",
        "managed_categories",
        "managed_tags",
        "managed_character_categories",
        "managed_character_tags",
        "managed_meta",
    }
    existing_tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    missing_tables = required_tables - existing_tables
    if missing_tables:
        raise RuntimeError(f"Database schema is incomplete: {', '.join(sorted(missing_tables))}")

    character_columns = _table_columns(connection, "managed_characters")
    required_character_columns = {
        "id",
        "name",
        "slug",
        "short_description",
        "description",
        "seo_title",
        "seo_description",
        "search_terms",
        "sort_order",
        "status",
        "entity_type",
        "hero_media_id",
        "source_path",
        "cover_offset_x",
        "cover_offset_y",
        "cover_fit",
        "base_price",
        "included_items",
        "ensemble_members",
        "ensemble_included_count",
        "ensemble_extra_member_price",
        "created_at",
        "updated_at",
    }
    missing_columns = required_character_columns - character_columns
    if missing_columns:
        raise RuntimeError(
            "managed_characters is missing columns: " + ", ".join(sorted(missing_columns))
        )
    return character_columns


def _path_filename(path: object) -> str:
    return PurePosixPath(urlsplit(str(path or "")).path).name


def _fetch_character_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT character.id, character.slug, character.name, character.status,
               character.hero_media_id, media.file_path AS hero_file_path
        FROM managed_characters AS character
        LEFT JOIN managed_character_media AS media
          ON media.id = character.hero_media_id
         AND media.character_id = character.id
        WHERE character.entity_type = 'character'
        ORDER BY character.id
        """
    ).fetchall()


def _single_match(
    candidates: Iterable[sqlite3.Row],
    *,
    slug: str,
    reason: str,
) -> sqlite3.Row | None:
    matches = list(candidates)
    if len(matches) > 1:
        ids = ", ".join(str(row["id"]) for row in matches)
        raise RuntimeError(f"Ambiguous {reason} match for {slug}: character IDs {ids}")
    return matches[0] if matches else None


def build_plan(connection: sqlite3.Connection, items: list[CatalogItem]) -> list[PlannedItem]:
    rows = _fetch_character_rows(connection)
    claimed_ids: set[int] = set()
    planned: list[PlannedItem] = []

    for item in items:
        available = [row for row in rows if int(row["id"]) not in claimed_ids]
        legacy_slugs = LEGACY_SLUGS.get(item.slug, ())
        match: sqlite3.Row | None = None
        reason = "insert"
        predicates: tuple[tuple[str, Callable[[sqlite3.Row], bool]], ...] = (
            (
                "active slug",
                lambda row: row["status"] == "active" and row["slug"] == item.slug,
            ),
            (
                "active legacy slug",
                lambda row: row["status"] == "active" and row["slug"] in legacy_slugs,
            ),
            (
                "active hero filename",
                lambda row: row["status"] == "active"
                and _path_filename(row["hero_file_path"]) == item.image_filename,
            ),
            ("slug", lambda row: row["slug"] == item.slug),
            ("legacy slug", lambda row: row["slug"] in legacy_slugs),
            (
                "hero filename",
                lambda row: _path_filename(row["hero_file_path"]) == item.image_filename,
            ),
        )
        for candidate_reason, predicate in predicates:
            match = _single_match(
                (row for row in available if predicate(row)),
                slug=item.slug,
                reason=candidate_reason,
            )
            if match is not None:
                reason = candidate_reason
                break

        character_id = int(match["id"]) if match is not None else None
        current_slug = str(match["slug"]) if match is not None else None
        if character_id is not None:
            claimed_ids.add(character_id)
        planned.append(
            PlannedItem(
                item=item,
                character_id=character_id,
                current_slug=current_slug,
                match_reason=reason,
            )
        )
    return planned


def _unique_archived_slug(connection: sqlite3.Connection, row: sqlite3.Row) -> str:
    base = f"archived-{int(row['id'])}-{str(row['slug'])}"[:180].rstrip("-")
    candidate = base
    suffix = 2
    while connection.execute(
        "SELECT 1 FROM managed_characters WHERE slug = ? AND id != ?",
        (candidate, int(row["id"])),
    ).fetchone():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _unique_staging_slug(connection: sqlite3.Connection, base: str) -> str:
    candidate = base
    suffix = 2
    while connection.execute(
        "SELECT 1 FROM managed_characters WHERE slug = ?", (candidate,)
    ).fetchone():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _outside_selected_clause(selected_ids: set[int]) -> tuple[str, tuple[int, ...]]:
    if not selected_ids:
        return "", ()
    ordered_ids = tuple(sorted(selected_ids))
    placeholders = ", ".join("?" for _ in ordered_ids)
    return f" AND id NOT IN ({placeholders})", ordered_ids


def _ensure_tag(
    connection: sqlite3.Connection,
    *,
    slug: str,
    name: str,
    sort_order: int,
    now: str,
    is_system: bool = False,
) -> int:
    row = connection.execute("SELECT id FROM managed_tags WHERE slug = ?", (slug,)).fetchone()
    if row:
        return int(row["id"])
    cursor = connection.execute(
        """
        INSERT INTO managed_tags(
            name, slug, description, is_visible, is_system, sort_order, created_at, updated_at
        ) VALUES (?, ?, '', 1, ?, ?, ?, ?)
        """,
        (name, slug, 1 if is_system else 0, sort_order, now, now),
    )
    return int(cursor.lastrowid)


def _ensure_category(
    connection: sqlite3.Connection,
    *,
    slug: str,
    name: str,
    sort_order: int,
    now: str,
    linked_tag_id: int | None = None,
    is_system: bool = False,
) -> int:
    row = connection.execute(
        "SELECT id FROM managed_categories WHERE slug = ?", (slug,)
    ).fetchone()
    if row:
        return int(row["id"])
    cursor = connection.execute(
        """
        INSERT INTO managed_categories(
            name, slug, description, is_visible, is_system, linked_tag_id,
            sort_order, created_at, updated_at
        ) VALUES (?, ?, '', 1, ?, ?, ?, ?, ?)
        """,
        (name, slug, 1 if is_system else 0, linked_tag_id, sort_order, now, now),
    )
    return int(cursor.lastrowid)


def _ensure_taxonomy(
    connection: sqlite3.Connection, now: str
) -> tuple[dict[str, int], dict[str, int]]:
    all_tag_id = _ensure_tag(
        connection, slug="all", name="all", sort_order=0, now=now, is_system=True
    )
    tag_ids = {
        key: _ensure_tag(connection, slug=slug, name=name, sort_order=order, now=now)
        for key, (slug, name, order) in TAG_TAXONOMY.items()
    }
    all_category_id = _ensure_category(
        connection,
        slug="all",
        name="Все",
        sort_order=0,
        now=now,
        linked_tag_id=all_tag_id,
        is_system=True,
    )
    category_ids = {
        key: _ensure_category(
            connection,
            slug=slug,
            name=name,
            sort_order=order,
            now=now,
            linked_tag_id=None,
        )
        for key, (slug, name, order) in CATEGORY_TAXONOMY.items()
    }
    category_ids["all"] = all_category_id
    tag_ids["all"] = all_tag_id
    return category_ids, tag_ids


def _insert_character(
    connection: sqlite3.Connection,
    *,
    staging_slug: str,
    item: CatalogItem,
    now: str,
    character_columns: set[str],
) -> int:
    columns = [
        "name",
        "slug",
        "short_description",
        "description",
        "seo_title",
        "seo_description",
        "search_terms",
        "sort_order",
        "status",
        "entity_type",
        "source_path",
        "cover_offset_x",
        "cover_offset_y",
        "cover_fit",
        "base_price",
        "included_items",
        "ensemble_members",
        "ensemble_included_count",
        "ensemble_extra_member_price",
        "created_at",
        "updated_at",
    ]
    values: list[object] = [
        item.name,
        staging_slug,
        item.description,
        item.description,
        f"{item.name} на детский праздник в Ташкенте | Surpriz",
        item.description,
        item.search_terms,
        item.sort_order,
        "active",
        "character",
        "",
        item.cover_offset_x,
        item.cover_offset_y,
        "contain",
        item.base_price,
        item.included_items,
        ", ".join(item.ensemble_members),
        item.ensemble_included_count,
        item.ensemble_extra_member_price,
        now,
        now,
    ]
    if "image_zoom" in character_columns:
        columns.append("image_zoom")
        values.append(item.image_zoom)
    placeholders = ", ".join("?" for _ in columns)
    cursor = connection.execute(
        f"INSERT INTO managed_characters({', '.join(columns)}) VALUES ({placeholders})",
        values,
    )
    return int(cursor.lastrowid)


def _update_character(
    connection: sqlite3.Connection,
    *,
    character_id: int,
    item: CatalogItem,
    now: str,
    character_columns: set[str],
) -> None:
    assignments = [
        "name = ?",
        "slug = ?",
        "short_description = ?",
        "description = ?",
        "seo_title = ?",
        "seo_description = ?",
        "search_terms = ?",
        "sort_order = ?",
        "status = 'active'",
        "entity_type = 'character'",
        "source_path = ''",
        "cover_offset_x = ?",
        "cover_offset_y = ?",
        "cover_fit = 'contain'",
        "base_price = ?",
        "included_items = ?",
        "ensemble_members = ?",
        "ensemble_included_count = ?",
        "ensemble_extra_member_price = ?",
        "updated_at = ?",
    ]
    values: list[object] = [
        item.name,
        item.slug,
        item.description,
        item.description,
        f"{item.name} на детский праздник в Ташкенте | Surpriz",
        item.description,
        item.search_terms,
        item.sort_order,
        item.cover_offset_x,
        item.cover_offset_y,
        item.base_price,
        item.included_items,
        ", ".join(item.ensemble_members),
        item.ensemble_included_count,
        item.ensemble_extra_member_price,
        now,
    ]
    if "image_zoom" in character_columns:
        assignments.insert(-1, "image_zoom = ?")
        values.insert(-1, item.image_zoom)
    values.append(character_id)
    connection.execute(
        f"UPDATE managed_characters SET {', '.join(assignments)} WHERE id = ?",
        values,
    )


def _update_media(
    connection: sqlite3.Connection,
    *,
    character_id: int,
    item: CatalogItem,
    now: str,
) -> None:
    character = connection.execute(
        "SELECT hero_media_id FROM managed_characters WHERE id = ?", (character_id,)
    ).fetchone()
    hero_media_id = int(character["hero_media_id"]) if character["hero_media_id"] else None
    media = None
    if hero_media_id is not None:
        media = connection.execute(
            "SELECT id FROM managed_character_media WHERE id = ? AND character_id = ?",
            (hero_media_id, character_id),
        ).fetchone()
    if media is None:
        media = connection.execute(
            """
            SELECT id FROM managed_character_media
            WHERE character_id = ? AND file_path LIKE ?
            ORDER BY id LIMIT 1
            """,
            (character_id, f"%/{item.image_filename}"),
        ).fetchone()

    if media is not None:
        hero_media_id = int(media["id"])
        connection.execute(
            """
            UPDATE managed_character_media
            SET media_type = 'image', file_path = ?, alt_text = ?, caption = '',
                sort_order = 0, updated_at = ?
            WHERE id = ?
            """,
            (item.image_path, item.alt_text, now, hero_media_id),
        )
    else:
        cursor = connection.execute(
            """
            INSERT INTO managed_character_media(
                character_id, media_type, file_path, alt_text, caption,
                sort_order, created_at, updated_at
            ) VALUES (?, 'image', ?, ?, '', 0, ?, ?)
            """,
            (character_id, item.image_path, item.alt_text, now, now),
        )
        hero_media_id = int(cursor.lastrowid)

    connection.execute(
        "UPDATE managed_characters SET hero_media_id = ? WHERE id = ?",
        (hero_media_id, character_id),
    )


def _replace_taxonomy(
    connection: sqlite3.Connection,
    *,
    character_id: int,
    item: CatalogItem,
    category_ids: dict[str, int],
    tag_ids: dict[str, int],
) -> None:
    connection.execute(
        "DELETE FROM managed_character_categories WHERE character_id = ?", (character_id,)
    )
    connection.execute(
        "DELETE FROM managed_character_tags WHERE character_id = ?", (character_id,)
    )
    desired_category_ids = {category_ids["all"]}
    desired_tag_ids = {tag_ids["all"]}
    for category in item.categories:
        if category in category_ids:
            desired_category_ids.add(category_ids[category])
        if category in tag_ids:
            desired_tag_ids.add(tag_ids[category])
    connection.executemany(
        "INSERT INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
        ((character_id, taxonomy_id) for taxonomy_id in sorted(desired_category_ids)),
    )
    connection.executemany(
        "INSERT INTO managed_character_tags(character_id, tag_id) VALUES (?, ?)",
        ((character_id, taxonomy_id) for taxonomy_id in sorted(desired_tag_ids)),
    )


def _set_digest(connection: sqlite3.Connection, digest: str, now: str) -> None:
    connection.execute(
        """
        INSERT INTO managed_meta(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE
        SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (MANAGED_META_KEY, digest, now),
    )


def verify_postconditions(
    connection: sqlite3.Connection,
    *,
    items: list[CatalogItem],
    expected_ids: dict[str, int],
    digest: str,
) -> None:
    rows = connection.execute(
        """
        SELECT character.id, character.slug, character.name, character.short_description,
               character.description, character.seo_title, character.seo_description,
               character.search_terms, character.sort_order, character.status,
               character.cover_offset_x, character.cover_offset_y, character.cover_fit,
               character.base_price, character.included_items, character.ensemble_members,
               character.ensemble_included_count, character.ensemble_extra_member_price,
               character.hero_media_id, media.character_id AS media_character_id,
               media.file_path, media.alt_text
        FROM managed_characters AS character
        LEFT JOIN managed_character_media AS media ON media.id = character.hero_media_id
        WHERE character.entity_type = 'character' AND character.status = 'active'
        ORDER BY character.sort_order, character.id
        """
    ).fetchall()
    if len(rows) != EXPECTED_CHARACTER_COUNT:
        raise RuntimeError(
            f"Postcondition failed: expected {EXPECTED_CHARACTER_COUNT} active characters, found {len(rows)}"
        )
    by_slug = {str(row["slug"]): row for row in rows}
    expected_slugs = {item.slug for item in items}
    if set(by_slug) != expected_slugs:
        missing = expected_slugs - set(by_slug)
        extra = set(by_slug) - expected_slugs
        raise RuntimeError(
            "Postcondition failed: active slugs differ; "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )

    for item in items:
        row = by_slug[item.slug]
        expected_content = (
            item.name,
            item.description,
            item.description,
            item.description,
            item.search_terms,
            item.sort_order,
            item.cover_offset_x,
            item.cover_offset_y,
            "contain",
            item.base_price,
            item.included_items,
            ", ".join(item.ensemble_members),
            item.ensemble_included_count,
            item.ensemble_extra_member_price,
        )
        actual_content = (
            str(row["name"]),
            str(row["short_description"]),
            str(row["description"]),
            str(row["seo_description"]),
            str(row["search_terms"]),
            int(row["sort_order"]),
            int(row["cover_offset_x"]),
            int(row["cover_offset_y"]),
            str(row["cover_fit"]),
            int(row["base_price"]),
            str(row["included_items"] or ""),
            str(row["ensemble_members"] or ""),
            int(row["ensemble_included_count"]),
            int(row["ensemble_extra_member_price"]),
        )
        if actual_content != expected_content or not str(row["seo_title"]).strip():
            raise RuntimeError(f"Postcondition failed: content differs for {item.slug}")
        if int(row["id"]) != expected_ids[item.slug]:
            raise RuntimeError(f"Postcondition failed: ID changed for {item.slug}")
        if (
            int(row["media_character_id"] or 0) != int(row["id"])
            or str(row["file_path"]) != item.image_path
            or str(row["alt_text"]) != item.alt_text
        ):
            raise RuntimeError(f"Postcondition failed: hero media differs for {item.slug}")

        actual_categories = {
            str(category_row[0])
            for category_row in connection.execute(
                """
                SELECT category.slug
                FROM managed_character_categories AS assignment
                JOIN managed_categories AS category ON category.id = assignment.category_id
                WHERE assignment.character_id = ?
                """,
                (int(row["id"]),),
            )
        }
        actual_tags = {
            str(tag_row[0])
            for tag_row in connection.execute(
                """
                SELECT tag.slug
                FROM managed_character_tags AS assignment
                JOIN managed_tags AS tag ON tag.id = assignment.tag_id
                WHERE assignment.character_id = ?
                """,
                (int(row["id"]),),
            )
        }
        expected_categories = {"all"} | {
            CATEGORY_TAXONOMY[key][0] for key in item.categories if key in CATEGORY_TAXONOMY
        }
        expected_tags = {"all"} | {
            TAG_TAXONOMY[key][0] for key in item.categories if key in TAG_TAXONOMY
        }
        if actual_categories != expected_categories or actual_tags != expected_tags:
            raise RuntimeError(f"Postcondition failed: taxonomy differs for {item.slug}")

    meta = connection.execute(
        "SELECT value FROM managed_meta WHERE key = ?", (MANAGED_META_KEY,)
    ).fetchone()
    if meta is None or str(meta["value"]) != digest:
        raise RuntimeError("Postcondition failed: managed manifest digest differs")


def replace_character_catalog(
    *,
    database: Path,
    manifest: Path,
    apply: bool = False,
    output: Callable[[str], None] = print,
) -> dict[str, int | bool | str]:
    raw_manifest, items = load_manifest(manifest)
    digest = hashlib.sha256(raw_manifest).hexdigest()
    database = database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Database does not exist: {database}")

    connection = sqlite3.connect(database, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    character_columns = validate_schema(connection)
    try:
        connection.execute("BEGIN IMMEDIATE")
        plan = build_plan(connection, items)
        selected_existing_ids = {
            planned.character_id for planned in plan if planned.character_id is not None
        }
        outside_clause, outside_params = _outside_selected_clause(selected_existing_ids)
        active_outside = int(
            connection.execute(
                f"""
                SELECT COUNT(*) FROM managed_characters
                WHERE entity_type = 'character' AND status = 'active'
                {outside_clause}
                """,
                outside_params,
            ).fetchone()[0]
        )

        output(f"Character catalog replacement plan ({'apply' if apply else 'dry-run'}):")
        for planned in plan:
            if planned.character_id is None:
                output(f"+ {planned.item.slug}: insert from {planned.item.image_filename}")
            elif planned.current_slug == planned.item.slug:
                output(
                    f"= {planned.item.slug}: update ID {planned.character_id} "
                    f"({planned.match_reason})"
                )
            else:
                output(
                    f"→ {planned.current_slug} -> {planned.item.slug}: preserve ID "
                    f"{planned.character_id} ({planned.match_reason})"
                )
        output(f"- hide {active_outside} active character rows outside the {EXPECTED_CHARACTER_COUNT}-card target")

        now = utcnow_iso()
        for character_id in sorted(selected_existing_ids):
            staging_slug = _unique_staging_slug(
                connection, f"catalog-replacement-staging-{character_id}"
            )
            connection.execute(
                "UPDATE managed_characters SET slug = ?, updated_at = ? WHERE id = ?",
                (staging_slug, now, character_id),
            )

        target_slugs = {item.slug for item in items}
        outside_rows = connection.execute(
            f"""
            SELECT id, slug, status FROM managed_characters
            WHERE entity_type = 'character' {outside_clause}
            ORDER BY id
            """,
            outside_params,
        ).fetchall()
        for row in outside_rows:
            archived_slug = (
                _unique_archived_slug(connection, row)
                if str(row["slug"]) in target_slugs
                else str(row["slug"])
            )
            connection.execute(
                """
                UPDATE managed_characters
                SET slug = ?, status = 'hidden', updated_at = ?
                WHERE id = ?
                """,
                (archived_slug, now, int(row["id"])),
            )

        category_ids, tag_ids = _ensure_taxonomy(connection, now)
        expected_ids: dict[str, int] = {}
        inserted = 0
        renamed = 0
        for planned in plan:
            character_id = planned.character_id
            if character_id is None:
                staging_slug = _unique_staging_slug(
                    connection,
                    f"catalog-replacement-new-{planned.item.sort_order}",
                )
                character_id = _insert_character(
                    connection,
                    staging_slug=staging_slug,
                    item=planned.item,
                    now=now,
                    character_columns=character_columns,
                )
                inserted += 1
            elif planned.current_slug != planned.item.slug:
                renamed += 1
            _update_character(
                connection,
                character_id=character_id,
                item=planned.item,
                now=now,
                character_columns=character_columns,
            )
            _update_media(
                connection,
                character_id=character_id,
                item=planned.item,
                now=now,
            )
            _replace_taxonomy(
                connection,
                character_id=character_id,
                item=planned.item,
                category_ids=category_ids,
                tag_ids=tag_ids,
            )
            expected_ids[planned.item.slug] = character_id

        _set_digest(connection, digest, now)
        verify_postconditions(
            connection,
            items=items,
            expected_ids=expected_ids,
            digest=digest,
        )

        summary: dict[str, int | bool | str] = {
            "applied": apply,
            "active": EXPECTED_CHARACTER_COUNT,
            "inserted": inserted,
            "renamed": renamed,
            "hidden": active_outside,
            "digest": digest,
        }
        if apply:
            connection.commit()
            verify_postconditions(
                connection,
                items=items,
                expected_ids=expected_ids,
                digest=digest,
            )
            output(
                f"Applied: {EXPECTED_CHARACTER_COUNT} active, {inserted} inserted, {renamed} renamed, "
                f"{active_outside} hidden. Postconditions verified."
            )
        else:
            connection.rollback()
            output(
                f"Dry run: {EXPECTED_CHARACTER_COUNT} active, {inserted} inserts, {renamed} renames, "
                f"{active_outside} hides would be applied. Postconditions verified; "
                "transaction rolled back."
            )
        return summary
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist the replacement. Without this flag the transaction is rolled back.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    replace_character_catalog(
        database=args.database,
        manifest=args.manifest,
        apply=args.apply,
    )


if __name__ == "__main__":
    main()
