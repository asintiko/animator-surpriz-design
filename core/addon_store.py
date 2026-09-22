from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .catalog_store import DB_PATH, ENTITY_TYPE_SHOW_PROGRAM, slugify, utcnow_iso
from .config import STATIC_ROOT

UPLOAD_ROOT = STATIC_ROOT / "admin-media" / "addons"
UPLOAD_URL_ROOT = "/admin-media/addons"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"}
ADDON_STATUSES = {"active", "hidden"}
GIFT_MODES = {"none", "choice_one", "bundle_all"}
SHOW_TARIFF_ADDONS_META_KEY = "show_tariff_addons_v1"
SHOW_TARIFF_ADDONS_VERSION = "2026-08-08-v2"
FREE_GIFT_PROGRAM_SLUGS = (
    "standard-program",
    "ribbon-show",
    "paper-ribbon-show",
    "streamer-show",
    "neon-start",
    "neon-medium",
    "neon-lux",
    "squid-game-60",
    "squid-game-90",
)
SHOW_TARIFF_ADDONS = (
    {
        "slug": "party-masks",
        "name": "Маски",
        "status": "active",
        "price": 0,
        "duration_minutes": 0,
        "type": "Подарок",
        "sort_order": 80,
        "short_description": "Бесплатный подарок на выбор для участников праздника.",
    },
    {
        "slug": "party-balloons",
        "name": "Шары",
        "status": "active",
        "price": 0,
        "duration_minutes": 0,
        "type": "Подарок",
        "sort_order": 81,
        "short_description": "Бесплатный подарок на выбор для участников праздника.",
    },
    {
        "slug": "greeting-dj",
        "name": "Диджей",
        "status": "active",
        "price": 300_000,
        "duration_minutes": 15,
        "type": "Команда",
        "sort_order": 30,
        "short_description": "Диджей для программы «Поздравлялка».",
    },
)


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _normalize_status(value: str | None) -> str:
    return value if value in ADDON_STATUSES else "hidden"


def _normalize_int(value: Any, default: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _normalize_gift_mode(value: Any) -> str:
    mode = str(value or "none").strip()
    return mode if mode in GIFT_MODES else "none"


def _ensure_unique_slug(connection: sqlite3.Connection, slug: str, *, exclude_id: int | None = None) -> str:
    base_slug = slugify(slug or "addon")
    candidate = base_slug
    suffix = 2
    while True:
        params: list[Any] = [candidate]
        query = "SELECT id FROM show_addons WHERE slug = ?"
        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)
        row = connection.execute(query, params).fetchone()
        if not row:
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row[1] == column for row in rows)


def init_addon_store() -> None:
    with _get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS show_addons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'active',
                sort_order INTEGER NOT NULL DEFAULT 0,
                image_path TEXT NOT NULL DEFAULT '',
                short_description TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                price INTEGER NOT NULL DEFAULT 0,
                cost INTEGER NOT NULL DEFAULT 0,
                duration_minutes INTEGER NOT NULL DEFAULT 0,
                type TEXT NOT NULL DEFAULT '',
                seo_title TEXT NOT NULL DEFAULT '',
                seo_description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS show_program_addons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                program_id INTEGER NOT NULL,
                addon_id INTEGER NOT NULL,
                is_recommended INTEGER NOT NULL DEFAULT 0,
                is_default INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(program_id, addon_id),
                FOREIGN KEY(program_id) REFERENCES managed_characters(id) ON DELETE CASCADE,
                FOREIGN KEY(addon_id) REFERENCES show_addons(id) ON DELETE CASCADE
            );
            """
        )
        if not _has_column(connection, "show_program_addons", "is_free_choice"):
            connection.execute(
                "ALTER TABLE show_program_addons ADD COLUMN is_free_choice INTEGER NOT NULL DEFAULT 0"
            )
        if not _has_column(connection, "show_program_addons", "gift_mode"):
            connection.execute(
                "ALTER TABLE show_program_addons ADD COLUMN gift_mode TEXT NOT NULL DEFAULT 'none'"
            )
        if not _has_column(connection, "show_program_addons", "gift_group"):
            connection.execute(
                "ALTER TABLE show_program_addons ADD COLUMN gift_group TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            """
            DELETE FROM show_program_addons
            WHERE addon_id NOT IN (SELECT id FROM show_addons)
               OR program_id NOT IN (
                    SELECT id FROM managed_characters WHERE entity_type = ?
               )
            """,
            (ENTITY_TYPE_SHOW_PROGRAM,),
        )
        connection.commit()
    sync_show_tariff_addons()


def sync_show_tariff_addons() -> dict[str, Any]:
    """Seed tariff-owned gifts and the fixed-price greeting DJ once."""
    required_program_slugs = (*FREE_GIFT_PROGRAM_SLUGS, "greeting-program")
    now = utcnow_iso()
    with _get_connection() as connection:
        has_meta = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'managed_meta'"
        ).fetchone()
        if not has_meta:
            return {"changed": False, "reason": "catalog_uninitialized", "count": 0}

        connection.execute("BEGIN IMMEDIATE")
        version_row = connection.execute(
            "SELECT value FROM managed_meta WHERE key = ? LIMIT 1",
            (SHOW_TARIFF_ADDONS_META_KEY,),
        ).fetchone()
        if version_row and str(version_row["value"]) == SHOW_TARIFF_ADDONS_VERSION:
            connection.rollback()
            return {
                "changed": False,
                "reason": "already_synced",
                "count": len(SHOW_TARIFF_ADDONS),
            }

        placeholders = ", ".join("?" for _ in required_program_slugs)
        program_rows = connection.execute(
            f"""
            SELECT id, slug
            FROM managed_characters
            WHERE entity_type = ? AND slug IN ({placeholders})
            """,
            (ENTITY_TYPE_SHOW_PROGRAM, *required_program_slugs),
        ).fetchall()
        programs_by_slug = {str(row["slug"]): int(row["id"]) for row in program_rows}
        missing_programs = [slug for slug in required_program_slugs if slug not in programs_by_slug]
        if missing_programs:
            connection.rollback()
            return {
                "changed": False,
                "reason": "programs_missing",
                "missing_program_slugs": missing_programs,
                "count": 0,
            }

        addon_ids: dict[str, int] = {}
        for addon in SHOW_TARIFF_ADDONS:
            slug = str(addon["slug"])
            connection.execute(
                """
                INSERT INTO show_addons(
                    name, slug, status, sort_order, image_path, short_description,
                    description, price, cost, duration_minutes, type, seo_title,
                    seo_description, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '', ?, ?, ?, 0, ?, ?, '', '', ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                    name = excluded.name,
                    status = excluded.status,
                    sort_order = excluded.sort_order,
                    short_description = excluded.short_description,
                    description = excluded.description,
                    price = excluded.price,
                    duration_minutes = excluded.duration_minutes,
                    type = excluded.type,
                    updated_at = excluded.updated_at
                """,
                (
                    str(addon["name"]),
                    slug,
                    str(addon["status"]),
                    int(addon["sort_order"]),
                    str(addon["short_description"]),
                    str(addon["short_description"]),
                    int(addon["price"]),
                    int(addon["duration_minutes"]),
                    str(addon["type"]),
                    now,
                    now,
                ),
            )
            addon_row = connection.execute(
                "SELECT id FROM show_addons WHERE slug = ? LIMIT 1",
                (slug,),
            ).fetchone()
            addon_ids[slug] = int(addon_row["id"])

        for program_slug in FREE_GIFT_PROGRAM_SLUGS:
            for offset, addon_slug in enumerate(("party-masks", "party-balloons")):
                connection.execute(
                    """
                    INSERT INTO show_program_addons(
                        program_id, addon_id, is_recommended, is_default,
                        is_free_choice, gift_mode, gift_group, sort_order,
                        created_at, updated_at
                    )
                    VALUES (?, ?, 0, 0, 1, 'choice_one', 'masks-or-balloons', ?, ?, ?)
                    ON CONFLICT(program_id, addon_id) DO UPDATE SET
                        is_recommended = 0,
                        is_default = 0,
                        is_free_choice = 1,
                        gift_mode = 'choice_one',
                        gift_group = 'masks-or-balloons',
                        sort_order = excluded.sort_order,
                        updated_at = excluded.updated_at
                    """,
                    (
                        programs_by_slug[program_slug],
                        addon_ids[addon_slug],
                        80 + offset,
                        now,
                        now,
                    ),
                )

        connection.execute(
            """
            INSERT INTO show_program_addons(
                program_id, addon_id, is_recommended, is_default,
                is_free_choice, gift_mode, gift_group, sort_order,
                created_at, updated_at
            )
            VALUES (?, ?, 1, 0, 0, 'none', '', 30, ?, ?)
            ON CONFLICT(program_id, addon_id) DO UPDATE SET
                is_recommended = 1,
                is_default = 0,
                is_free_choice = 0,
                gift_mode = 'none',
                gift_group = '',
                sort_order = 30,
                updated_at = excluded.updated_at
            """,
            (
                programs_by_slug["greeting-program"],
                addon_ids["greeting-dj"],
                now,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO managed_meta(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (SHOW_TARIFF_ADDONS_META_KEY, SHOW_TARIFF_ADDONS_VERSION, now),
        )
        connection.commit()

    return {"changed": True, "count": len(SHOW_TARIFF_ADDONS)}


def _row_to_addon(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "slug": row["slug"],
        "status": row["status"],
        "sort_order": _normalize_int(row["sort_order"]),
        "image_path": row["image_path"] or "",
        "short_description": row["short_description"] or "",
        "description": row["description"] or "",
        "price": _normalize_int(row["price"]),
        "cost": _normalize_int(row["cost"]),
        "duration_minutes": _normalize_int(row["duration_minutes"]),
        "type": row["type"] or "",
        "seo_title": row["seo_title"] or "",
        "seo_description": row["seo_description"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _addon_list_query(where_sql: str = "", params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    query = f"""
        SELECT
            a.*,
            COUNT(DISTINCT CASE WHEN mc.id IS NOT NULL THEN spa.program_id END) AS usage_count,
            GROUP_CONCAT(DISTINCT mc.name) AS program_names
        FROM show_addons a
        LEFT JOIN show_program_addons spa ON spa.addon_id = a.id
        LEFT JOIN managed_characters mc
            ON mc.id = spa.program_id AND mc.entity_type = ?
        {where_sql}
        GROUP BY a.id
        ORDER BY a.sort_order ASC, a.name COLLATE NOCASE ASC, a.id ASC
    """
    with _get_connection() as connection:
        rows = connection.execute(query, (ENTITY_TYPE_SHOW_PROGRAM, *params)).fetchall()

    addons: list[dict[str, Any]] = []
    for row in rows:
        addon = _row_to_addon(row)
        addon["usage_count"] = int(row["usage_count"] or 0)
        addon["program_names"] = [name for name in (row["program_names"] or "").split(",") if name]
        addons.append(addon)
    return addons


def list_addons(search: str = "", status: str = "") -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if status.strip():
        clauses.append("a.status = ?")
        params.append(_normalize_status(status.strip()))
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    addons = _addon_list_query(where_sql, tuple(params))
    query = search.strip().casefold()
    if not query:
        return addons
    return [
        addon
        for addon in addons
        if query in " ".join(
            [
                addon["name"],
                addon["slug"],
                addon["short_description"],
                addon["description"],
                addon["type"],
            ]
        ).casefold()
    ]


def list_active_addons() -> list[dict[str, Any]]:
    return list_addons(status="active")


def get_addon_by_id(addon_id: int) -> dict[str, Any] | None:
    with _get_connection() as connection:
        row = connection.execute("SELECT * FROM show_addons WHERE id = ? LIMIT 1", (addon_id,)).fetchone()
    return _row_to_addon(row) if row else None


def get_addon_by_slug(slug: str) -> dict[str, Any] | None:
    s = (slug or "").strip()
    if not s:
        return None
    with _get_connection() as connection:
        row = connection.execute("SELECT * FROM show_addons WHERE slug = ? LIMIT 1", (s,)).fetchone()
    return _row_to_addon(row) if row else None


def create_addon(data: dict[str, Any]) -> int:
    now = utcnow_iso()
    with _get_connection() as connection:
        final_slug = _ensure_unique_slug(connection, data.get("slug") or data.get("name") or "addon")
        cursor = connection.execute(
            """
            INSERT INTO show_addons(
                name, slug, status, sort_order, image_path, short_description, description,
                price, cost, duration_minutes, type, seo_title, seo_description, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("name", "").strip(),
                final_slug,
                _normalize_status(data.get("status")),
                _normalize_int(data.get("sort_order")),
                data.get("short_description", "").strip(),
                data.get("description", "").strip(),
                _normalize_int(data.get("price")),
                _normalize_int(data.get("cost")),
                _normalize_int(data.get("duration_minutes")),
                data.get("type", "").strip(),
                data.get("seo_title", "").strip(),
                data.get("seo_description", "").strip(),
                now,
                now,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def update_addon(addon_id: int, data: dict[str, Any]) -> None:
    with _get_connection() as connection:
        final_slug = _ensure_unique_slug(connection, data.get("slug") or data.get("name") or "addon", exclude_id=addon_id)
        connection.execute(
            """
            UPDATE show_addons
            SET
                name = ?,
                slug = ?,
                status = ?,
                sort_order = ?,
                short_description = ?,
                description = ?,
                price = ?,
                cost = ?,
                duration_minutes = ?,
                type = ?,
                seo_title = ?,
                seo_description = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                data.get("name", "").strip(),
                final_slug,
                _normalize_status(data.get("status")),
                _normalize_int(data.get("sort_order")),
                data.get("short_description", "").strip(),
                data.get("description", "").strip(),
                _normalize_int(data.get("price")),
                _normalize_int(data.get("cost")),
                _normalize_int(data.get("duration_minutes")),
                data.get("type", "").strip(),
                data.get("seo_title", "").strip(),
                data.get("seo_description", "").strip(),
                utcnow_iso(),
                addon_id,
            ),
        )
        connection.commit()


def update_addon_status(addon_id: int, status: str) -> bool:
    with _get_connection() as connection:
        cursor = connection.execute(
            "UPDATE show_addons SET status = ?, updated_at = ? WHERE id = ?",
            (_normalize_status(status), utcnow_iso(), addon_id),
        )
        connection.commit()
        return cursor.rowcount > 0


def delete_addon(addon_id: int) -> bool:
    with _get_connection() as connection:
        connection.execute("DELETE FROM show_program_addons WHERE addon_id = ?", (addon_id,))
        cursor = connection.execute("DELETE FROM show_addons WHERE id = ?", (addon_id,))
        connection.commit()
        return cursor.rowcount > 0


def upload_addon_image(addon_id: int, storage: FileStorage | None) -> str:
    if not storage or not storage.filename:
        return ""
    filename = secure_filename(storage.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in IMAGE_EXTENSIONS:
        return ""
    addon = get_addon_by_id(addon_id)
    if not addon:
        return ""
    target_dir = UPLOAD_ROOT / str(addon_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    final_name = f"{timestamp}-{filename}"
    target_path = target_dir / final_name
    storage.save(target_path)
    public_path = f"{UPLOAD_URL_ROOT}/{addon_id}/{final_name}"
    with _get_connection() as connection:
        connection.execute(
            "UPDATE show_addons SET image_path = ?, updated_at = ? WHERE id = ?",
            (public_path, utcnow_iso(), addon_id),
        )
        connection.commit()
    return public_path


def get_program_addon_settings(program_id: int) -> dict[int, dict[str, Any]]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT addon_id, is_recommended, is_default, is_free_choice, gift_mode, gift_group, sort_order
            FROM show_program_addons
            WHERE program_id = ?
            """,
            (program_id,),
        ).fetchall()
    return {
        int(row["addon_id"]): {
            "is_available": True,
            "is_recommended": bool(row["is_recommended"]),
            "is_default": bool(row["is_default"]),
            "is_free_choice": bool(row["is_free_choice"]) if "is_free_choice" in row.keys() else False,
            "gift_mode": _normalize_gift_mode(row["gift_mode"] if "gift_mode" in row.keys() else "none"),
            "gift_group": str(row["gift_group"] or "") if "gift_group" in row.keys() else "",
            "sort_order": _normalize_int(row["sort_order"]),
        }
        for row in rows
    }


def set_program_addons(program_id: int, selections: list[dict[str, Any]]) -> None:
    now = utcnow_iso()
    with _get_connection() as connection:
        connection.execute("DELETE FROM show_program_addons WHERE program_id = ?", (program_id,))
        seen_addon_ids: set[int] = set()
        for selection in selections:
            addon_id = _normalize_int(selection.get("addon_id"))
            if addon_id <= 0 or addon_id in seen_addon_ids:
                continue
            seen_addon_ids.add(addon_id)
            gift_mode = _normalize_gift_mode(selection.get("gift_mode"))
            connection.execute(
                """
                INSERT INTO show_program_addons(
                    program_id, addon_id, is_recommended, is_default, is_free_choice,
                    gift_mode, gift_group, sort_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    program_id,
                    addon_id,
                    1 if selection.get("is_recommended") else 0,
                    1 if selection.get("is_default") else 0,
                    1 if selection.get("is_free_choice") or gift_mode == "choice_one" else 0,
                    gift_mode,
                    str(selection.get("gift_group") or ""),
                    _normalize_int(selection.get("sort_order")),
                    now,
                    now,
                ),
            )
        connection.commit()


def list_program_addons_for_public(program_id: int) -> list[dict[str, Any]]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                a.*,
                spa.is_recommended,
                spa.is_default,
                spa.is_free_choice,
                spa.gift_mode,
                spa.gift_group,
                spa.sort_order AS link_sort_order
            FROM show_program_addons spa
            INNER JOIN show_addons a ON a.id = spa.addon_id
            WHERE spa.program_id = ? AND a.status = 'active'
            ORDER BY spa.sort_order ASC, a.sort_order ASC, a.name COLLATE NOCASE ASC
            """,
            (program_id,),
        ).fetchall()

    addons: list[dict[str, Any]] = []
    for row in rows:
        addon = _row_to_addon(row)
        addon["is_recommended"] = bool(row["is_recommended"])
        addon["is_default"] = bool(row["is_default"])
        addon["is_free_choice"] = bool(row["is_free_choice"]) if "is_free_choice" in row.keys() else False
        addon["gift_mode"] = _normalize_gift_mode(row["gift_mode"] if "gift_mode" in row.keys() else "none")
        addon["gift_group"] = str(row["gift_group"] or "") if "gift_group" in row.keys() else ""
        addon["link_sort_order"] = _normalize_int(row["link_sort_order"])
        addons.append(addon)
    return addons
