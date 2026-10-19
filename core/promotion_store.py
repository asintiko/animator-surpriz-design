from __future__ import annotations

import sqlite3
from typing import Any

from .catalog_store import DB_PATH, ENTITY_TYPE_SHOW_PROGRAM, SHOW_FEATURE_ICONS, utcnow_iso

PROMOTION_STATUSES = {"active", "hidden"}
PROMOTIONS_SEED_META_KEY = "promotions_seed_v1"
PROMOTIONS_SEED_VERSION = "2026-10-06"
SEED_PROGRAM_SLUG = "standard-program"
SEED_ADDONS = (
    {
        "slug": "mini-ribbon-show",
        "name": "Мини-лента шоу",
        "price": 0,
        "type": "Подарок",
        "gift_mode": "bundle_all",
        "short_description": "Короткое лента-шоу в финале праздника — в подарок к программе «Стандарт».",
    },
    {
        "slug": "aqua-face-paint-addon",
        "name": "Аквагрим",
        "price": 250_000,
        "type": "Мастер",
        "gift_mode": "none",
        "short_description": "Аквагример рисует яркие образы детям прямо на празднике.",
    },
)
SEED_PROMOTIONS = (
    {
        "title": "Мини-лента шоу в подарок",
        "badge_text": "Мини-лента шоу в подарок",
        "short_text": "Закажите программу «Стандарт» — мини-лента шоу будет в подарок.",
        "tooltip_text": "",
        "addon_slug": "mini-ribbon-show",
        "old_price": 0,
        "sort_order": 10,
    },
    {
        "title": "Аквагрим со скидкой",
        "badge_text": "Аквагрим за 250 000",
        "short_text": "К программе «Стандарт» аквагрим за 250 000 сум вместо 575 000.",
        "tooltip_text": "",
        "addon_slug": "aqua-face-paint-addon",
        "old_price": 575_000,
        "sort_order": 20,
    },
)


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_promotion_store() -> None:
    with _get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                short_text TEXT NOT NULL DEFAULT '',
                badge_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS show_program_promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                program_id INTEGER NOT NULL,
                promotion_id INTEGER NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(program_id, promotion_id),
                FOREIGN KEY(program_id) REFERENCES managed_characters(id) ON DELETE CASCADE,
                FOREIGN KEY(promotion_id) REFERENCES promotions(id) ON DELETE CASCADE
            );
            """
        )
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(promotions)").fetchall()
        }
        additions = {
            "tooltip_text": "TEXT NOT NULL DEFAULT ''",
            "is_featured": "INTEGER NOT NULL DEFAULT 0",
            "addon_id": "INTEGER",
            "old_price": "INTEGER NOT NULL DEFAULT 0",
            "icon": "TEXT NOT NULL DEFAULT ''",
        }
        for column, definition in additions.items():
            if column in columns:
                continue
            try:
                connection.execute(f"ALTER TABLE promotions ADD COLUMN {column} {definition}")
            except sqlite3.OperationalError as error:
                # Several gunicorn workers migrate at once; the loser sees the column already added.
                if "duplicate column" not in str(error).lower():
                    raise
        connection.commit()
    seed_current_promotions()


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _row_to_promotion(row: sqlite3.Row) -> dict[str, Any]:
    keys = row.keys()
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "short_text": row["short_text"],
        "badge_text": row["badge_text"] or row["title"],
        "tooltip_text": row["tooltip_text"] or "",
        "status": row["status"],
        "sort_order": int(row["sort_order"] or 0),
        "is_featured": bool(row["is_featured"]),
        "addon_id": int(row["addon_id"]) if row["addon_id"] else None,
        "addon_slug": str(row["addon_slug"] or "") if "addon_slug" in keys else "",
        "addon_name": str(row["addon_name"] or "") if "addon_name" in keys else "",
        "addon_price": _int(row["addon_price"]) if "addon_price" in keys else 0,
        "old_price": _int(row["old_price"]),
        "icon": str(row["icon"] or "") if "icon" in keys else "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# Joined with the add-on so every surface can show «Аквагрим 250 000 вместо 575 000»
# without a second lookup; a hidden add-on drops out of the promotion.
_PROMOTION_SELECT = """
    SELECT p.*,
           a.slug AS addon_slug,
           a.name AS addon_name,
           a.price AS addon_price
    FROM promotions p
    LEFT JOIN show_addons a ON a.id = p.addon_id AND a.status = 'active'
"""


def _attach_programs(
    connection: sqlite3.Connection,
    promotions: list[dict[str, Any]],
    *,
    only_active: bool,
) -> list[dict[str, Any]]:
    if not promotions:
        return promotions
    query = """
        SELECT spp.promotion_id, mc.id, mc.slug, mc.name, mc.status
        FROM show_program_promotions spp
        INNER JOIN managed_characters mc ON mc.id = spp.program_id
        WHERE mc.entity_type = ?
    """
    if only_active:
        query += " AND mc.status = 'active'"
    query += " ORDER BY spp.sort_order ASC, mc.sort_order ASC, mc.name COLLATE NOCASE ASC"
    by_promotion: dict[int, list[dict[str, Any]]] = {}
    for row in connection.execute(query, (ENTITY_TYPE_SHOW_PROGRAM,)).fetchall():
        by_promotion.setdefault(int(row["promotion_id"]), []).append(
            {
                "id": int(row["id"]),
                "slug": str(row["slug"]),
                "name": str(row["name"]),
                "status": str(row["status"]),
                "route": f"/show-programs/{row['slug']}/",
            }
        )
    for promotion in promotions:
        programs = by_promotion.get(promotion["id"], [])
        promotion["programs"] = programs
        promotion["program_ids"] = [program["id"] for program in programs]
        promotion["program_names"] = [program["name"] for program in programs]
    return promotions


def list_promotions(*, include_hidden: bool = False) -> list[dict[str, Any]]:
    with _get_connection() as connection:
        query = _PROMOTION_SELECT
        if not include_hidden:
            query += " WHERE p.status = 'active'"
        query += " ORDER BY p.sort_order ASC, p.title COLLATE NOCASE ASC"
        promotions = [_row_to_promotion(row) for row in connection.execute(query).fetchall()]
        return _attach_programs(connection, promotions, only_active=not include_hidden)


def _offered_addon_links(connection: sqlite3.Connection) -> set[tuple[int, int]]:
    rows = connection.execute(
        """
        SELECT spa.program_id, spa.addon_id
        FROM show_program_addons spa
        INNER JOIN show_addons a ON a.id = spa.addon_id
        WHERE a.status = 'active'
        """
    ).fetchall()
    return {(int(row["program_id"]), int(row["addon_id"])) for row in rows}


def list_featured_promotions_for_public() -> list[dict[str, Any]]:
    """Active promotions marked as main, each with the active shows it applies to.

    A promotion about an add-on only lists the shows that actually sell that add-on,
    so a hidden or detached add-on never gets advertised.
    """
    promotions = [promotion for promotion in list_promotions() if promotion["is_featured"]]
    if any(promotion["addon_id"] for promotion in promotions):
        with _get_connection() as connection:
            offered = _offered_addon_links(connection)
        for promotion in promotions:
            addon_id = promotion["addon_id"]
            if not addon_id:
                continue
            programs = [
                program
                for program in promotion["programs"]
                if promotion["addon_slug"] and (program["id"], addon_id) in offered
            ]
            promotion["programs"] = programs
            promotion["program_ids"] = [program["id"] for program in programs]
            promotion["program_names"] = [program["name"] for program in programs]
    return [promotion for promotion in promotions if promotion["programs"]]


def get_promotion_by_id(promotion_id: int) -> dict[str, Any] | None:
    with _get_connection() as connection:
        row = connection.execute(_PROMOTION_SELECT + " WHERE p.id = ?", (promotion_id,)).fetchone()
        if not row:
            return None
        return _attach_programs(connection, [_row_to_promotion(row)], only_active=False)[0]


def _promotion_values(payload: dict[str, Any]) -> tuple[Any, ...]:
    status = payload.get("status") if payload.get("status") in PROMOTION_STATUSES else "active"
    addon_id = _int(payload.get("addon_id"))
    # Empty means «по смыслу»: the show page picks gift / face paint / sparkles itself.
    icon = str(payload.get("icon") or "").strip()
    if icon not in SHOW_FEATURE_ICONS:
        icon = ""
    return (
        str(payload.get("title") or "").strip(),
        str(payload.get("short_text") or "").strip(),
        str(payload.get("badge_text") or payload.get("title") or "").strip(),
        str(payload.get("tooltip_text") or "").strip(),
        status,
        _int(payload.get("sort_order")),
        1 if payload.get("is_featured") else 0,
        addon_id or None,
        _int(payload.get("old_price")),
        icon,
    )


def _program_ids(payload: dict[str, Any]) -> list[int] | None:
    raw = payload.get("program_ids")
    if not isinstance(raw, list):
        return None
    return list(dict.fromkeys(_int(value) for value in raw if _int(value) > 0))


def _replace_promotion_programs(connection: sqlite3.Connection, promotion_id: int, program_ids: list[int]) -> None:
    now = utcnow_iso()
    connection.execute("DELETE FROM show_program_promotions WHERE promotion_id = ?", (promotion_id,))
    for index, program_id in enumerate(program_ids):
        connection.execute(
            """
            INSERT INTO show_program_promotions(program_id, promotion_id, sort_order, created_at, updated_at)
            SELECT id, ?, ?, ?, ? FROM managed_characters WHERE id = ? AND entity_type = ?
            """,
            (promotion_id, index, now, now, program_id, ENTITY_TYPE_SHOW_PROGRAM),
        )


def create_promotion(payload: dict[str, Any]) -> int:
    now = utcnow_iso()
    with _get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO promotions(
                title, short_text, badge_text, tooltip_text, status, sort_order,
                is_featured, addon_id, old_price, icon, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*_promotion_values(payload), now, now),
        )
        promotion_id = int(cursor.lastrowid)
        program_ids = _program_ids(payload)
        if program_ids is not None:
            _replace_promotion_programs(connection, promotion_id, program_ids)
        connection.commit()
        return promotion_id


def update_promotion(promotion_id: int, payload: dict[str, Any]) -> None:
    """Update the fields present in the payload; show links change only with `program_ids`."""
    current = get_promotion_by_id(promotion_id)
    if not current:
        return
    payload = {**current, "program_ids": None, **payload}
    with _get_connection() as connection:
        connection.execute(
            """
            UPDATE promotions
            SET title = ?, short_text = ?, badge_text = ?, tooltip_text = ?, status = ?, sort_order = ?,
                is_featured = ?, addon_id = ?, old_price = ?, icon = ?, updated_at = ?
            WHERE id = ?
            """,
            (*_promotion_values(payload), utcnow_iso(), promotion_id),
        )
        program_ids = _program_ids(payload)
        if program_ids is not None:
            _replace_promotion_programs(connection, promotion_id, program_ids)
        connection.commit()


def delete_promotion(promotion_id: int) -> None:
    with _get_connection() as connection:
        connection.execute("DELETE FROM promotions WHERE id = ?", (promotion_id,))
        connection.commit()


def set_program_promotions(program_id: int, promotion_ids: list[int]) -> None:
    now = utcnow_iso()
    with _get_connection() as connection:
        connection.execute("DELETE FROM show_program_promotions WHERE program_id = ?", (program_id,))
        for index, promotion_id in enumerate(promotion_ids):
            if promotion_id <= 0:
                continue
            connection.execute(
                """
                INSERT INTO show_program_promotions(program_id, promotion_id, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (program_id, promotion_id, index, now, now),
            )
        connection.commit()


def get_program_promotion_ids(program_id: int) -> list[int]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT promotion_id
            FROM show_program_promotions
            WHERE program_id = ?
            ORDER BY sort_order ASC, promotion_id ASC
            """,
            (program_id,),
        ).fetchall()
    return [int(row["promotion_id"]) for row in rows]


def list_program_promotions_for_public(program_id: int) -> list[dict[str, Any]]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT p.*,
                   a.slug AS addon_slug,
                   a.name AS addon_name,
                   a.price AS addon_price
            FROM show_program_promotions spp
            INNER JOIN promotions p ON p.id = spp.promotion_id
            LEFT JOIN show_addons a ON a.id = p.addon_id AND a.status = 'active'
            WHERE spp.program_id = ? AND p.status = 'active'
              AND (
                p.addon_id IS NULL
                OR EXISTS (
                    SELECT 1 FROM show_program_addons spa
                    WHERE spa.program_id = spp.program_id AND spa.addon_id = a.id
                )
              )
            ORDER BY p.is_featured DESC, p.sort_order ASC, spp.sort_order ASC, p.title COLLATE NOCASE ASC
            """,
            (program_id,),
        ).fetchall()
    return [_row_to_promotion(row) for row in rows]


def list_promotions_by_program_slug(slug: str) -> list[dict[str, Any]]:
    with _get_connection() as connection:
        row = connection.execute(
            """
            SELECT id FROM managed_characters
            WHERE slug = ? AND entity_type = ? AND status = 'active'
            LIMIT 1
            """,
            (slug, ENTITY_TYPE_SHOW_PROGRAM),
        ).fetchone()
    if not row:
        return []
    return list_program_promotions_for_public(int(row["id"]))


def seed_current_promotions() -> dict[str, Any]:
    """Create the two running «Стандарт» offers once; later admin edits are never overwritten."""
    now = utcnow_iso()
    with _get_connection() as connection:
        ready = connection.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = 'table' AND name IN ('managed_meta', 'show_addons', 'show_program_addons')
            """
        ).fetchone()[0]
        if ready < 3:
            return {"changed": False, "reason": "catalog_uninitialized"}

        connection.execute("BEGIN IMMEDIATE")
        done = connection.execute(
            "SELECT 1 FROM managed_meta WHERE key = ? LIMIT 1", (PROMOTIONS_SEED_META_KEY,)
        ).fetchone()
        if done:
            connection.rollback()
            return {"changed": False, "reason": "already_seeded"}

        program = connection.execute(
            "SELECT id FROM managed_characters WHERE slug = ? AND entity_type = ? LIMIT 1",
            (SEED_PROGRAM_SLUG, ENTITY_TYPE_SHOW_PROGRAM),
        ).fetchone()
        if not program:
            connection.rollback()
            return {"changed": False, "reason": "program_missing"}
        program_id = int(program["id"])

        linked_names = {
            str(row["name"]).casefold(): str(row["slug"])
            for row in connection.execute(
                """
                SELECT a.name, a.slug
                FROM show_program_addons spa
                INNER JOIN show_addons a ON a.id = spa.addon_id
                WHERE spa.program_id = ? AND a.status = 'active'
                """,
                (program_id,),
            ).fetchall()
        }
        addons_by_slug = {str(addon["slug"]): addon for addon in SEED_ADDONS}
        addon_ids: dict[str, int] = {}
        skipped: list[str] = []
        for index, promotion in enumerate(SEED_PROMOTIONS):
            addon = addons_by_slug[promotion["addon_slug"]]
            existing_slug = linked_names.get(str(addon["name"]).casefold())
            title_taken = connection.execute(
                "SELECT 1 FROM promotions WHERE title = ? LIMIT 1", (promotion["title"],)
            ).fetchone()
            # The show already sells this service under another card, or the offer
            # was set up by hand: leave the owner's setup alone instead of doubling it.
            if title_taken or (existing_slug and existing_slug != addon["slug"]):
                skipped.append(promotion["title"])
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO show_addons(
                    name, slug, status, sort_order, image_path, short_description,
                    description, price, cost, duration_minutes, type, seo_title,
                    seo_description, created_at, updated_at
                )
                VALUES (?, ?, 'active', ?, '', ?, '', ?, 0, 0, ?, '', '', ?, ?)
                """,
                (
                    addon["name"],
                    addon["slug"],
                    10 + index,
                    addon["short_description"],
                    addon["price"],
                    addon["type"],
                    now,
                    now,
                ),
            )
            addon_id = int(
                connection.execute("SELECT id FROM show_addons WHERE slug = ?", (addon["slug"],)).fetchone()["id"]
            )
            addon_ids[addon["slug"]] = addon_id
            connection.execute(
                """
                INSERT OR IGNORE INTO show_program_addons(
                    program_id, addon_id, is_recommended, is_default, is_free_choice,
                    gift_mode, gift_group, sort_order, created_at, updated_at
                )
                VALUES (?, ?, ?, 0, 0, ?, '', ?, ?, ?)
                """,
                (
                    program_id,
                    addon_id,
                    1 if addon["gift_mode"] == "none" else 0,
                    addon["gift_mode"],
                    50 + index,
                    now,
                    now,
                ),
            )
            cursor = connection.execute(
                """
                INSERT INTO promotions(
                    title, short_text, badge_text, tooltip_text, status, sort_order,
                    is_featured, addon_id, old_price, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'active', ?, 1, ?, ?, ?, ?)
                """,
                (
                    promotion["title"],
                    promotion["short_text"],
                    promotion["badge_text"],
                    promotion["tooltip_text"],
                    promotion["sort_order"],
                    addon_id,
                    promotion["old_price"],
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO show_program_promotions(program_id, promotion_id, sort_order, created_at, updated_at)
                VALUES (?, ?, 0, ?, ?)
                """,
                (program_id, int(cursor.lastrowid), now, now),
            )

        connection.execute(
            """
            INSERT INTO managed_meta(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (PROMOTIONS_SEED_META_KEY, PROMOTIONS_SEED_VERSION, now),
        )
        connection.commit()
    return {"changed": True, "program_id": program_id, "addon_ids": addon_ids, "skipped": skipped}
