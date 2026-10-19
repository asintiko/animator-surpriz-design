"""Site seasons (Halloween, New Year): registry, active season and character rules.

The active season is a single ``site_settings`` row. Everything seasonal on the
public site derives from it: the theme injected into every page
(``core.season_theme``), which characters are shown and in what order, and the
season block in the catalog API. Switching seasons in the admin takes effect on
the next request, no build or restart needed.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

ACTIVE_SEASON_SETTING = "active_season"
SEASON_EFFECTS_SETTING = "season_effects"
NO_SEASON = "none"


@dataclass(frozen=True)
class Season:
    id: str
    label: str
    emoji: str
    theme_color: str
    catalog_label: str
    hero_label: str
    filter_icon: str


SEASONS: dict[str, Season] = {
    "halloween": Season(
        id="halloween",
        label="Хэллоуин",
        emoji="🎃",
        theme_color="#1b0f2e",
        catalog_label="Герои Хэллоуина",
        hero_label="Герой Хэллоуина",
        filter_icon="/surpriz/assets/seasons/halloween/filter.webp",
    ),
    "new_year": Season(
        id="new_year",
        label="Новый год",
        emoji="🎄",
        theme_color="#0f2a4a",
        catalog_label="Новогодние герои",
        hero_label="Новогодний герой",
        filter_icon="/surpriz/assets/icons/categories/all-heroes.svg",
    ),
}
SEASON_CHOICES: tuple[str, ...] = (NO_SEASON, *SEASONS)


def normalize_season_id(value: Any) -> str:
    season_id = str(value or "").strip().lower().replace("-", "_")
    return season_id if season_id in SEASONS else ""


def _connection() -> sqlite3.Connection:
    # Resolved at call time so tests that patch the catalog database path work.
    from . import catalog_store

    connection = sqlite3.connect(catalog_store.DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _read_settings() -> dict[str, str]:
    try:
        with closing(_connection()) as connection:
            rows = connection.execute(
                "SELECT key, value FROM site_settings WHERE key IN (?, ?)",
                (ACTIVE_SEASON_SETTING, SEASON_EFFECTS_SETTING),
            ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(row["key"]): str(row["value"] or "") for row in rows}


def _cached_settings() -> dict[str, str]:
    """One read per request: the catalog code asks for the season many times."""
    try:
        from flask import g, has_request_context
    except ImportError:  # pragma: no cover - flask is always installed
        return _read_settings()
    if not has_request_context():
        return _read_settings()
    cached = getattr(g, "_surpriz_season_settings", None)
    if cached is None:
        cached = _read_settings()
        g._surpriz_season_settings = cached
    return cached


def active_season() -> Season | None:
    return SEASONS.get(normalize_season_id(_cached_settings().get(ACTIVE_SEASON_SETTING)))


def effects_enabled() -> bool:
    return _cached_settings().get(SEASON_EFFECTS_SETTING, "1") != "0"


def set_active_season(season_id: str, *, effects: bool | None = None) -> dict[str, Any]:
    requested = str(season_id or "").strip().lower().replace("-", "_")
    if requested not in SEASON_CHOICES:
        raise ValueError("Неизвестный сезон.")
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    values = {ACTIVE_SEASON_SETTING: requested}
    if effects is not None:
        values[SEASON_EFFECTS_SETTING] = "1" if effects else "0"
    with closing(_connection()) as connection:
        for key, value in values.items():
            connection.execute(
                """
                INSERT INTO site_settings(key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, now),
            )
        connection.commit()
    return season_state()


def season_characters() -> dict[str, list[dict[str, Any]]]:
    """Heroes assigned to each season, for the admin season card."""
    grouped: dict[str, list[dict[str, Any]]] = {season_id: [] for season_id in SEASONS}
    try:
        with closing(_connection()) as connection:
            rows = connection.execute(
                """
                SELECT id, name, slug, status, entity_type, season, season_only
                FROM managed_characters
                WHERE season != ''
                ORDER BY sort_order, name
                """
            ).fetchall()
    except sqlite3.Error:
        return grouped
    for row in rows:
        season_id = normalize_season_id(row["season"])
        if season_id:
            grouped[season_id].append(
                {
                    "id": int(row["id"]),
                    "name": str(row["name"]),
                    "slug": str(row["slug"]),
                    "status": str(row["status"]),
                    "entity_type": str(row["entity_type"]),
                    "season_only": bool(row["season_only"]),
                }
            )
    return grouped


def season_admin_payload() -> dict[str, Any]:
    return {
        **season_state(),
        "options": [
            {"id": NO_SEASON, "label": "Обычный", "emoji": "✨"},
            *({"id": season.id, "label": season.label, "emoji": season.emoji} for season in SEASONS.values()),
        ],
        "characters": season_characters(),
    }


def season_state() -> dict[str, Any]:
    settings = _read_settings()
    season = SEASONS.get(normalize_season_id(settings.get(ACTIVE_SEASON_SETTING)))
    return {
        "active": season.id if season else NO_SEASON,
        "effects": settings.get(SEASON_EFFECTS_SETTING, "1") != "0",
    }


# --- characters -----------------------------------------------------------------


def character_season_visible(character: dict[str, Any], season: Season | None) -> bool:
    """A «season only» character exists on the site only while its season is on."""
    if not character.get("season_only"):
        return True
    return season is not None and normalize_season_id(character.get("season")) == season.id


def is_seasonal_now(character: dict[str, Any], season: Season | None) -> bool:
    return season is not None and normalize_season_id(character.get("season")) == season.id


def seasonal_character_slugs(season: Season | None) -> list[str]:
    if season is None:
        return []
    try:
        with closing(_connection()) as connection:
            rows = connection.execute(
                "SELECT slug FROM managed_characters WHERE status = 'active' AND season = ? ORDER BY sort_order, name",
                (season.id,),
            ).fetchall()
    except sqlite3.Error:
        return []
    return [str(row["slug"]) for row in rows]


def season_public_payload(season: Season | None) -> dict[str, Any] | None:
    if season is None:
        return None
    return {
        "id": season.id,
        "label": season.label,
        "emoji": season.emoji,
        "catalog_label": season.catalog_label,
        "hero_label": season.hero_label,
        "effects": effects_enabled(),
    }
