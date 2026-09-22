"""Curated ordering for characters and show programs.

The homepage carousels and the top of each catalog used to follow a slug list
hardcoded in ``catalog_site``. Admins now pick the order themselves: the slugs
they select come first in the order they picked them, everything else keeps its
usual ordering behind them, and the first entries feed the homepage carousels.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Iterable

from .catalog_store import DB_PATH, utcnow_iso

#: How many curated entries the homepage carousels show.
HOMEPAGE_SLOTS = 8

_META_KEYS = {
    "character": "featured_characters_v1",
    "show_program": "featured_shows_v1",
}

#: Kept as the starting point so the homepage looks the same until an admin
#: reorders it. Mirrors the list that used to live in catalog_site.
DEFAULT_FEATURED_CHARACTERS = (
    "kid-e-cats",
    "anna-elsa-olaf",
    "naruto",
    "among-us",
    "digital-circus",
    "paw-patrol",
    "spiderman-n1",
    "hosts-mickey-minnie",
)


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_recommendation_store() -> None:
    with _get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS managed_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        row = connection.execute(
            "SELECT value FROM managed_meta WHERE key = ? LIMIT 1",
            (_META_KEYS["character"],),
        ).fetchone()
        if not row:
            connection.execute(
                "INSERT INTO managed_meta(key, value, updated_at) VALUES (?, ?, ?)",
                (_META_KEYS["character"], json.dumps(list(DEFAULT_FEATURED_CHARACTERS)), utcnow_iso()),
            )
        connection.commit()


def _entity_key(entity_type: str) -> str:
    key = _META_KEYS.get(entity_type)
    if not key:
        raise ValueError(f"Неизвестный тип каталога: {entity_type}")
    return key


def get_featured_slugs(entity_type: str) -> list[str]:
    """Curated slugs in the order an admin arranged them."""
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT value FROM managed_meta WHERE key = ? LIMIT 1",
            (_entity_key(entity_type),),
        ).fetchone()
    if not row:
        return []
    try:
        stored = json.loads(str(row["value"]))
    except (TypeError, ValueError):
        return []
    if not isinstance(stored, list):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for item in stored:
        slug = str(item or "").strip()
        if slug and slug not in seen:
            seen.add(slug)
            ordered.append(slug)
    return ordered


def set_featured_slugs(entity_type: str, slugs: Iterable[Any]) -> list[str]:
    key = _entity_key(entity_type)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in slugs:
        slug = str(item or "").strip()
        if slug and slug not in seen:
            seen.add(slug)
            ordered.append(slug)
    with _get_connection() as connection:
        connection.execute(
            """
            INSERT INTO managed_meta(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, json.dumps(ordered), utcnow_iso()),
        )
        connection.commit()
    return ordered


def sort_by_featured(items: list[dict[str, Any]], entity_type: str) -> list[dict[str, Any]]:
    """Curated entries first in their chosen order, the rest untouched behind them."""
    featured = get_featured_slugs(entity_type)
    if not featured:
        return items
    rank = {slug: index for index, slug in enumerate(featured)}
    by_slug: dict[str, dict[str, Any]] = {}
    rest: list[dict[str, Any]] = []
    for item in items:
        slug = str(item.get("slug") or item.get("id") or "").strip()
        if slug in rank and slug not in by_slug:
            by_slug[slug] = item
        else:
            rest.append(item)
    head = [by_slug[slug] for slug in featured if slug in by_slug]
    return head + rest
