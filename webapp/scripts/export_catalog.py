from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


WEBAPP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WEBAPP_ROOT.parent
DATABASE_PATH = PROJECT_ROOT / "content" / "data" / "admin" / "site_admin.sqlite3"
OUTPUT_PATH = WEBAPP_ROOT / "src" / "data" / "catalog.generated.json"


def without_decorative_emoji(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.replace("\U0001f31f", "").split())
    if isinstance(value, list):
        return [without_decorative_emoji(item) for item in value]
    if isinstance(value, dict):
        return {key: without_decorative_emoji(item) for key, item in value.items()}
    return value


def rows(connection: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, params).fetchall()]


def grouped_ids(
    connection: sqlite3.Connection,
    query: str,
    value_key: str,
) -> dict[int, list[Any]]:
    result: dict[int, list[Any]] = defaultdict(list)
    for row in rows(connection, query):
        result[int(row["character_id"])].append(row[value_key])
    return result


def export_catalog() -> dict[str, Any]:
    connection = sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    entities = rows(
        connection,
        """
        SELECT *
        FROM managed_characters
        WHERE status = 'active'
        ORDER BY sort_order ASC, name COLLATE NOCASE ASC
        """,
    )
    media_by_entity: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in rows(
        connection,
        """
        SELECT id, character_id, media_type, file_path, alt_text, caption, sort_order
        FROM managed_character_media
        ORDER BY character_id, sort_order, id
        """,
    ):
        media_by_entity[int(item["character_id"])].append(item)

    categories_by_entity = grouped_ids(
        connection,
        """
        SELECT relation.character_id, category.slug
        FROM managed_character_categories AS relation
        JOIN managed_categories AS category ON category.id = relation.category_id
        WHERE category.is_visible = 1
        ORDER BY category.sort_order, category.name
        """,
        "slug",
    )
    tags_by_entity = grouped_ids(
        connection,
        """
        SELECT relation.character_id, tag.slug
        FROM managed_character_tags AS relation
        JOIN managed_tags AS tag ON tag.id = relation.tag_id
        WHERE tag.is_visible = 1
        ORDER BY tag.sort_order, tag.name
        """,
        "slug",
    )
    linked_characters = grouped_ids(
        connection,
        """
        SELECT relation.program_id AS character_id, character.slug
        FROM show_program_characters AS relation
        JOIN managed_characters AS character ON character.id = relation.character_id
        WHERE character.status = 'active'
        ORDER BY relation.sort_order, character.name
        """,
        "slug",
    )

    addon_map: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in rows(
        connection,
        """
        SELECT relation.program_id, addon.id, addon.name, addon.slug, addon.price,
               addon.duration_minutes, addon.image_path, addon.short_description,
               relation.is_recommended, relation.is_default, relation.is_free_choice,
               relation.gift_mode, relation.gift_group, relation.sort_order
        FROM show_program_addons AS relation
        JOIN show_addons AS addon ON addon.id = relation.addon_id
        WHERE addon.status = 'active'
        ORDER BY relation.sort_order, addon.sort_order, addon.name
        """,
    ):
        addon_map[int(item.pop("program_id"))].append(item)

    promotion_map: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in rows(
        connection,
        """
        SELECT relation.program_id, promotion.id, promotion.title, promotion.short_text,
               promotion.badge_text, promotion.tooltip_text, promotion.sort_order
        FROM show_program_promotions AS relation
        JOIN promotions AS promotion ON promotion.id = relation.promotion_id
        WHERE promotion.status = 'active'
        ORDER BY relation.sort_order, promotion.sort_order
        """,
    ):
        promotion_map[int(item.pop("program_id"))].append(item)

    for entity in entities:
        entity_id = int(entity["id"])
        entity["ensemble_members"] = [
            member.strip()
            for member in str(entity.get("ensemble_members") or "").replace(";", ",").split(",")
            if member.strip()
        ]
        entity["ensemble_included_count"] = int(entity.get("ensemble_included_count") or 2)
        entity["ensemble_extra_member_price"] = int(entity.get("ensemble_extra_member_price") or 300_000)
        entity["media"] = media_by_entity.get(entity_id, [])
        entity["categories"] = categories_by_entity.get(entity_id, [])
        entity["tags"] = tags_by_entity.get(entity_id, [])
        entity["linked_character_slugs"] = linked_characters.get(entity_id, [])
        entity["addons"] = addon_map.get(entity_id, [])
        entity["promotions"] = promotion_map.get(entity_id, [])
        hero_id = entity.get("hero_media_id")
        hero = next((item for item in entity["media"] if item["id"] == hero_id), None)
        if hero is None and entity["media"]:
            hero = entity["media"][0]
        entity["hero_file_path"] = hero["file_path"] if hero else ""

    variant_heroes = {
        entity["variant_group_slug"]: entity["hero_file_path"]
        for entity in entities
        if entity["variant_group_slug"] and entity["hero_file_path"]
    }
    for entity in entities:
        if not entity["hero_file_path"] and entity["variant_group_slug"]:
            entity["hero_file_path"] = variant_heroes.get(entity["variant_group_slug"], "")

    categories = rows(
        connection,
        """
        SELECT id, name, slug, description, is_system, sort_order
        FROM managed_categories
        WHERE is_visible = 1
        ORDER BY sort_order, name
        """,
    )
    tags = rows(
        connection,
        """
        SELECT id, name, slug, description, is_system, sort_order
        FROM managed_tags
        WHERE is_visible = 1
        ORDER BY sort_order, name
        """,
    )
    settings = {
        row["key"]: row["value"]
        for row in rows(connection, "SELECT key, value FROM site_settings ORDER BY key")
    }
    connection.close()

    characters = [item for item in entities if item["entity_type"] == "character"]
    shows = [item for item in entities if item["entity_type"] == "show_program"]
    return without_decorative_emoji({
        "generated_at": "2026-07-17",
        "source": str(DATABASE_PATH.relative_to(PROJECT_ROOT)),
        "characters": characters,
        "shows": shows,
        "categories": categories,
        "tags": tags,
        "settings": settings,
    })


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = export_catalog()
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"Exported {len(payload['characters'])} characters and "
        f"{len(payload['shows'])} shows to {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
