from __future__ import annotations

import sqlite3
from typing import Any

from .catalog_store import DB_PATH, ENTITY_TYPE_SHOW_PROGRAM, utcnow_iso

PROMOTION_STATUSES = {"active", "hidden"}


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
        if "tooltip_text" not in columns:
            connection.execute(
                "ALTER TABLE promotions ADD COLUMN tooltip_text TEXT NOT NULL DEFAULT ''"
            )
        connection.commit()


def _row_to_promotion(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "short_text": row["short_text"],
        "badge_text": row["badge_text"] or row["title"],
        "tooltip_text": row["tooltip_text"] or "",
        "status": row["status"],
        "sort_order": int(row["sort_order"] or 0),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_promotions(*, include_hidden: bool = False) -> list[dict[str, Any]]:
    with _get_connection() as connection:
        query = "SELECT * FROM promotions"
        if not include_hidden:
            query += " WHERE status = 'active'"
        query += " ORDER BY sort_order ASC, title COLLATE NOCASE ASC"
        rows = connection.execute(query).fetchall()
    return [_row_to_promotion(row) for row in rows]


def get_promotion_by_id(promotion_id: int) -> dict[str, Any] | None:
    with _get_connection() as connection:
        row = connection.execute("SELECT * FROM promotions WHERE id = ?", (promotion_id,)).fetchone()
    return _row_to_promotion(row) if row else None


def create_promotion(payload: dict[str, Any]) -> int:
    now = utcnow_iso()
    status = payload.get("status") if payload.get("status") in PROMOTION_STATUSES else "active"
    with _get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO promotions(
                title,
                short_text,
                badge_text,
                tooltip_text,
                status,
                sort_order,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(payload.get("title") or "").strip(),
                str(payload.get("short_text") or "").strip(),
                str(payload.get("badge_text") or payload.get("title") or "").strip(),
                str(payload.get("tooltip_text") or "").strip(),
                status,
                int(payload.get("sort_order") or 0),
                now,
                now,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def update_promotion(promotion_id: int, payload: dict[str, Any]) -> None:
    now = utcnow_iso()
    status = payload.get("status") if payload.get("status") in PROMOTION_STATUSES else "active"
    with _get_connection() as connection:
        connection.execute(
            """
            UPDATE promotions
            SET title = ?, short_text = ?, badge_text = ?, tooltip_text = ?, status = ?, sort_order = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                str(payload.get("title") or "").strip(),
                str(payload.get("short_text") or "").strip(),
                str(payload.get("badge_text") or payload.get("title") or "").strip(),
                str(payload.get("tooltip_text") or "").strip(),
                status,
                int(payload.get("sort_order") or 0),
                now,
                promotion_id,
            ),
        )
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
            SELECT p.*
            FROM show_program_promotions spp
            INNER JOIN promotions p ON p.id = spp.promotion_id
            WHERE spp.program_id = ? AND p.status = 'active'
            ORDER BY spp.sort_order ASC, p.sort_order ASC, p.title COLLATE NOCASE ASC
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
