"""Partner logos shown in the "нам доверяют" strip on the homepage.

The four logos used to be hardcoded in the static index.html, so adding or
removing a client meant editing markup. They live in the catalog database now
and are seeded from that original markup on first run.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .catalog_store import DB_PATH, slugify, utcnow_iso

PARTNER_STATUSES = {"active", "hidden"}

SEED_PARTNERS = (
    ("Alfraganus", "/surpriz/assets/original/alphraganus-logo.png", 10),
    ("Central Park", "/surpriz/assets/original/centralpark-logo.png", 20),
    ("Neon Park", "/surpriz/assets/original/neon-park.png", 30),
    ("Eriell", "/surpriz/assets/original/eriell.png", 40),
)


def _get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_partner_store() -> None:
    with _get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS managed_partners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                logo_path TEXT NOT NULL DEFAULT '',
                link_url TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing = connection.execute("SELECT COUNT(*) AS total FROM managed_partners").fetchone()
        if not existing or int(existing["total"]) == 0:
            now = utcnow_iso()
            for name, logo_path, sort_order in SEED_PARTNERS:
                connection.execute(
                    """
                    INSERT INTO managed_partners(name, slug, logo_path, link_url, sort_order, status, created_at, updated_at)
                    VALUES (?, ?, ?, '', ?, 'active', ?, ?)
                    """,
                    (name, slugify(name), logo_path, sort_order, now, now),
                )
        connection.commit()


def _row_to_partner(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "name": str(row["name"]),
        "slug": str(row["slug"]),
        "logo_path": str(row["logo_path"] or ""),
        "link_url": str(row["link_url"] or ""),
        "sort_order": int(row["sort_order"] or 0),
        "status": str(row["status"] or "active"),
        "updated_at": str(row["updated_at"] or ""),
    }


def list_partners(*, only_active: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM managed_partners"
    if only_active:
        query += " WHERE status = 'active' AND logo_path <> ''"
    query += " ORDER BY sort_order, id"
    with _get_connection() as connection:
        return [_row_to_partner(row) for row in connection.execute(query).fetchall()]


def _unique_slug(connection: sqlite3.Connection, base: str, *, exclude_id: int | None = None) -> str:
    candidate = base or "partner"
    suffix = 2
    while True:
        row = connection.execute(
            "SELECT id FROM managed_partners WHERE slug = ? AND id IS NOT ?",
            (candidate, exclude_id),
        ).fetchone()
        if not row:
            return candidate
        candidate = f"{base}-{suffix}"
        suffix += 1


def create_partner(data: dict[str, Any]) -> dict[str, Any]:
    name = " ".join(str(data.get("name") or "").split())[:80]
    if not name:
        raise ValueError("Укажите название партнёра.")
    logo_path = str(data.get("logo_path") or "").strip()
    if not logo_path:
        raise ValueError("Загрузите логотип партнёра.")
    link_url = str(data.get("link_url") or "").strip()[:240]
    if link_url and not link_url.startswith(("https://", "http://", "/")):
        raise ValueError("Ссылка должна начинаться с https:// или /")
    status = str(data.get("status") or "active")
    if status not in PARTNER_STATUSES:
        status = "active"

    now = utcnow_iso()
    with _get_connection() as connection:
        slug = _unique_slug(connection, slugify(name))
        next_order = connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 10 AS next FROM managed_partners"
        ).fetchone()["next"]
        cursor = connection.execute(
            """
            INSERT INTO managed_partners(name, slug, logo_path, link_url, sort_order, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, slug, logo_path, link_url, int(data.get("sort_order") or next_order), status, now, now),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM managed_partners WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_partner(row)


def update_partner(partner_id: int, data: dict[str, Any]) -> dict[str, Any]:
    with _get_connection() as connection:
        current = connection.execute("SELECT * FROM managed_partners WHERE id = ?", (partner_id,)).fetchone()
        if not current:
            raise ValueError("Партнёр не найден.")
        name = " ".join(str(data.get("name", current["name"])).split())[:80] or str(current["name"])
        logo_path = str(data.get("logo_path", current["logo_path"]) or "").strip()
        link_url = str(data.get("link_url", current["link_url"]) or "").strip()[:240]
        if link_url and not link_url.startswith(("https://", "http://", "/")):
            raise ValueError("Ссылка должна начинаться с https:// или /")
        status = str(data.get("status", current["status"]) or "active")
        if status not in PARTNER_STATUSES:
            status = "active"
        sort_order = data.get("sort_order", current["sort_order"])
        try:
            sort_order = int(sort_order)
        except (TypeError, ValueError):
            sort_order = int(current["sort_order"] or 0)
        slug = _unique_slug(connection, slugify(name), exclude_id=partner_id)
        connection.execute(
            """
            UPDATE managed_partners
            SET name = ?, slug = ?, logo_path = ?, link_url = ?, sort_order = ?, status = ?, updated_at = ?
            WHERE id = ?
            """,
            (name, slug, logo_path, link_url, sort_order, status, utcnow_iso(), partner_id),
        )
        connection.commit()
        row = connection.execute("SELECT * FROM managed_partners WHERE id = ?", (partner_id,)).fetchone()
    return _row_to_partner(row)


def delete_partner(partner_id: int) -> bool:
    with _get_connection() as connection:
        cursor = connection.execute("DELETE FROM managed_partners WHERE id = ?", (partner_id,))
        connection.commit()
        return cursor.rowcount > 0
