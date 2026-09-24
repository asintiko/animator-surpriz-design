"""Storage for the Google Calendar integration.

The module only talks to SQLite and has no imports from other ``core`` stores,
so ``customer_store`` can use it to enqueue calendar pushes inside its own
transactions and to read imported busy blocks for availability checks.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from .config import DATA_ROOT

DB_ROOT = DATA_ROOT / "admin"
DB_PATH = DB_ROOT / "site_admin.sqlite3"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS google_calendar_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_calendar_events (
    event_key TEXT PRIMARY KEY,
    calendar_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    html_link TEXT NOT NULL DEFAULT '',
    start_local TEXT NOT NULL,
    end_local TEXT NOT NULL,
    all_day INTEGER NOT NULL DEFAULT 0,
    program_slugs TEXT NOT NULL DEFAULT '[]',
    program_names TEXT NOT NULL DEFAULT '[]',
    character_slugs TEXT NOT NULL DEFAULT '[]',
    character_names TEXT NOT NULL DEFAULT '[]',
    match_status TEXT NOT NULL DEFAULT 'unmatched',
    order_public_id TEXT NOT NULL DEFAULT '',
    blocks_time INTEGER NOT NULL DEFAULT 0,
    blocks_all INTEGER NOT NULL DEFAULT 0,
    google_updated TEXT NOT NULL DEFAULT '',
    synced_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_google_calendar_events_range
ON google_calendar_events(blocks_time, start_local, end_local);

CREATE TABLE IF NOT EXISTS google_calendar_event_overrides (
    event_key TEXT PRIMARY KEY,
    ignored INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_calendar_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase TEXT NOT NULL,
    normalized TEXT NOT NULL UNIQUE,
    entity_slug TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_calendar_order_queue (
    order_id INTEGER PRIMARY KEY,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    next_attempt_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_calendar_order_events (
    order_id INTEGER PRIMARY KEY,
    calendar_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    html_link TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    generation INTEGER NOT NULL DEFAULT 0,
    synced_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_calendar_locks (
    name TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""

#: Imported events are stored as local Tashkent wall-clock strings.
LOCAL_DATETIME_FORMAT = "%Y-%m-%dT%H:%M"
DAY_END_LABEL = "23:59"


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def get_connection() -> sqlite3.Connection:
    DB_ROOT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, factory=_ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def ensure_schema(connection: sqlite3.Connection) -> None:
    """Create the integration tables on an already open connection.

    ``executescript`` would commit an open transaction, so the statements are
    executed one by one and callers stay in control of their transaction.
    """
    for statement in SCHEMA_SQL.split(";"):
        if statement.strip():
            connection.execute(statement)


def init_google_calendar_store() -> None:
    with get_connection() as connection:
        ensure_schema(connection)
        connection.commit()


# --- settings -----------------------------------------------------------------


def get_settings(keys: Iterable[str] | None = None) -> dict[str, str]:
    try:
        with get_connection() as connection:
            rows = connection.execute("SELECT key, value FROM google_calendar_settings").fetchall()
    except sqlite3.OperationalError:
        return {}
    values = {str(row["key"]): str(row["value"] or "") for row in rows}
    if keys is None:
        return values
    return {key: values.get(key, "") for key in keys}


def get_setting(key: str) -> str:
    return get_settings([key]).get(key, "")


def set_settings(values: dict[str, Any]) -> None:
    if not values:
        return
    now = utcnow_iso()
    with get_connection() as connection:
        ensure_schema(connection)
        for key, value in values.items():
            connection.execute(
                """
                INSERT INTO google_calendar_settings(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (str(key), "" if value is None else str(value), now),
            )
        connection.commit()


# --- order push queue -----------------------------------------------------------


def enqueue_order_sync(connection: sqlite3.Connection, order_id: int, now: str) -> None:
    """Queue an order for a calendar push inside the caller's transaction."""
    ensure_schema(connection)
    connection.execute(
        """
        INSERT INTO google_calendar_order_queue(order_id, attempts, last_error, next_attempt_at, updated_at)
        VALUES (?, 0, '', ?, ?)
        ON CONFLICT(order_id) DO UPDATE SET
            attempts = 0,
            last_error = '',
            next_attempt_at = excluded.next_attempt_at,
            updated_at = excluded.updated_at
        """,
        (int(order_id), now, now),
    )


def enqueue_orders(order_ids: Iterable[int]) -> int:
    now = utcnow_iso()
    count = 0
    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for order_id in order_ids:
            enqueue_order_sync(connection, int(order_id), now)
            count += 1
        connection.commit()
    return count


def list_due_orders(limit: int) -> list[int]:
    # Queue timestamps come with microseconds (customer_store), so compare
    # against a full-precision "now" to keep the ISO strings ordered.
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    with get_connection() as connection:
        ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT order_id FROM google_calendar_order_queue
            WHERE next_attempt_at <= ?
            ORDER BY next_attempt_at ASC, order_id ASC
            LIMIT ?
            """,
            (now, max(1, int(limit))),
        ).fetchall()
    return [int(row["order_id"]) for row in rows]


def complete_order_sync(order_id: int, queued_at: str | None = None) -> None:
    """Drop a processed queue row unless the order was re-queued meanwhile."""
    with get_connection() as connection:
        if queued_at:
            connection.execute(
                "DELETE FROM google_calendar_order_queue WHERE order_id = ? AND updated_at = ?",
                (int(order_id), queued_at),
            )
        else:
            connection.execute("DELETE FROM google_calendar_order_queue WHERE order_id = ?", (int(order_id),))
        connection.commit()


def get_queue_row(order_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM google_calendar_order_queue WHERE order_id = ?",
            (int(order_id),),
        ).fetchone()
    return dict(row) if row else None


def defer_order_sync(order_id: int, error: str, *, max_delay_seconds: int = 3600) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with get_connection() as connection:
        row = connection.execute(
            "SELECT attempts FROM google_calendar_order_queue WHERE order_id = ?",
            (int(order_id),),
        ).fetchone()
        attempts = int(row["attempts"] or 0) + 1 if row else 1
        delay = min(max_delay_seconds, 30 * (2 ** min(attempts - 1, 10)))
        connection.execute(
            """
            UPDATE google_calendar_order_queue
            SET attempts = ?, last_error = ?, next_attempt_at = ?, updated_at = ?
            WHERE order_id = ?
            """,
            (
                attempts,
                str(error or "")[:400],
                (now + timedelta(seconds=delay)).isoformat(),
                now.isoformat(),
                int(order_id),
            ),
        )
        connection.commit()


def queue_stats() -> dict[str, Any]:
    try:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS pending,
                       SUM(CASE WHEN attempts > 0 THEN 1 ELSE 0 END) AS failing,
                       MAX(CASE WHEN attempts > 0 THEN last_error ELSE '' END) AS last_error
                FROM google_calendar_order_queue
                """
            ).fetchone()
    except sqlite3.OperationalError:
        return {"pending": 0, "failing": 0, "last_error": ""}
    return {
        "pending": int(row["pending"] or 0),
        "failing": int(row["failing"] or 0),
        "last_error": str(row["last_error"] or ""),
    }


# --- pushed order events --------------------------------------------------------


def get_order_event(order_id: int) -> dict[str, Any] | None:
    with get_connection() as connection:
        ensure_schema(connection)
        row = connection.execute(
            "SELECT * FROM google_calendar_order_events WHERE order_id = ?",
            (int(order_id),),
        ).fetchone()
    return dict(row) if row else None


def save_order_event(
    order_id: int,
    *,
    calendar_id: str,
    event_id: str,
    html_link: str,
    content_hash: str,
    generation: int,
) -> None:
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO google_calendar_order_events(
                order_id, calendar_id, event_id, html_link, content_hash, generation, synced_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                calendar_id = excluded.calendar_id,
                event_id = excluded.event_id,
                html_link = excluded.html_link,
                content_hash = excluded.content_hash,
                generation = excluded.generation,
                synced_at = excluded.synced_at
            """,
            (int(order_id), calendar_id, event_id, html_link, content_hash, int(generation), utcnow_iso()),
        )
        connection.commit()


def delete_order_event(order_id: int) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM google_calendar_order_events WHERE order_id = ?", (int(order_id),))
        connection.commit()


def list_order_event_ids(calendar_id: str) -> set[str]:
    with get_connection() as connection:
        ensure_schema(connection)
        rows = connection.execute(
            "SELECT event_id FROM google_calendar_order_events WHERE calendar_id = ?",
            (calendar_id,),
        ).fetchall()
    return {str(row["event_id"]) for row in rows}


def get_order_event_links(order_ids: Iterable[int]) -> dict[int, str]:
    ids = [int(order_id) for order_id in order_ids]
    if not ids:
        return {}
    placeholders = ", ".join("?" for _ in ids)
    try:
        with get_connection() as connection:
            rows = connection.execute(
                f"SELECT order_id, html_link FROM google_calendar_order_events WHERE order_id IN ({placeholders})",
                tuple(ids),
            ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {int(row["order_id"]): str(row["html_link"] or "") for row in rows}


# --- imported events ------------------------------------------------------------


def replace_imported_events(rows: list[dict[str, Any]]) -> None:
    """Swap the imported calendar snapshot atomically."""
    now = utcnow_iso()
    with get_connection() as connection:
        ensure_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM google_calendar_events")
        for row in rows:
            connection.execute(
                """
                INSERT OR REPLACE INTO google_calendar_events(
                    event_key, calendar_id, event_id, summary, html_link, start_local, end_local,
                    all_day, program_slugs, program_names, character_slugs, character_names,
                    match_status, order_public_id, blocks_time, blocks_all, google_updated, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["event_key"],
                    row["calendar_id"],
                    row["event_id"],
                    str(row.get("summary") or "")[:300],
                    str(row.get("html_link") or ""),
                    row["start_local"],
                    row["end_local"],
                    1 if row.get("all_day") else 0,
                    json.dumps(list(row.get("program_slugs") or []), ensure_ascii=False),
                    json.dumps(list(row.get("program_names") or []), ensure_ascii=False),
                    json.dumps(list(row.get("character_slugs") or []), ensure_ascii=False),
                    json.dumps(list(row.get("character_names") or []), ensure_ascii=False),
                    str(row.get("match_status") or "unmatched"),
                    str(row.get("order_public_id") or ""),
                    1 if row.get("blocks_time") else 0,
                    1 if row.get("blocks_all") else 0,
                    str(row.get("google_updated") or ""),
                    now,
                ),
            )
        connection.commit()


def clear_imported_events() -> None:
    with get_connection() as connection:
        ensure_schema(connection)
        connection.execute("DELETE FROM google_calendar_events")
        connection.commit()


def _json_list(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _imported_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "event_key": str(row["event_key"]),
        "calendar_id": str(row["calendar_id"]),
        "event_id": str(row["event_id"]),
        "summary": str(row["summary"] or ""),
        "html_link": str(row["html_link"] or ""),
        "start_local": str(row["start_local"]),
        "end_local": str(row["end_local"]),
        "all_day": bool(row["all_day"]),
        "program_slugs": _json_list(row["program_slugs"]),
        "program_names": _json_list(row["program_names"]),
        "character_slugs": _json_list(row["character_slugs"]),
        "character_names": _json_list(row["character_names"]),
        "match_status": str(row["match_status"] or ""),
        "order_public_id": str(row["order_public_id"] or ""),
        "blocks_time": bool(row["blocks_time"]),
        "blocks_all": bool(row["blocks_all"]),
    }


def list_imported_events(*, from_local: str = "", limit: int = 300) -> list[dict[str, Any]]:
    params: list[Any] = []
    where = ""
    if from_local:
        where = "WHERE end_local > ?"
        params.append(from_local)
    try:
        with get_connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM google_calendar_events {where} ORDER BY start_local ASC, event_key ASC LIMIT ?",
                (*params, max(1, int(limit))),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [_imported_row_to_dict(row) for row in rows]


def imported_event_stats() -> dict[str, int]:
    stats = {"total": 0, "matched": 0, "unmatched": 0, "free": 0, "own": 0, "ignored": 0, "blocking": 0}
    try:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT match_status, COUNT(*) AS total, SUM(blocks_time) AS blocking
                FROM google_calendar_events
                GROUP BY match_status
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return stats
    for row in rows:
        status = str(row["match_status"] or "")
        stats["total"] += int(row["total"] or 0)
        stats["blocking"] += int(row["blocking"] or 0)
        if status in stats:
            stats[status] = int(row["total"] or 0)
    return stats


def _parse_local(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, LOCAL_DATETIME_FORMAT)
    except (TypeError, ValueError):
        return None


def split_local_range_by_day(start: datetime, end: datetime) -> list[tuple[str, str, str]]:
    """Split a local interval into ``(iso_date, time_from, time_to)`` day slices.

    The site works with same-day ``HH:MM`` windows, so a slice that runs until
    midnight ends at ``23:59``.
    """
    slices: list[tuple[str, str, str]] = []
    if end <= start:
        return slices
    day = start.date()
    while True:
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        slice_start = max(start, day_start)
        slice_end = min(end, day_end)
        if slice_end > slice_start:
            time_to = DAY_END_LABEL if slice_end == day_end else slice_end.strftime("%H:%M")
            slices.append((day.isoformat(), slice_start.strftime("%H:%M"), time_to))
        if end <= day_end:
            break
        day += timedelta(days=1)
    return slices


def fetch_busy_blocks(
    connection: sqlite3.Connection,
    date_from: date | str,
    date_to: date | str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return calendar blocks that close time on the site, grouped by date.

    Each block mimics the booking shape used by the availability code:
    ``time_from``/``time_to`` plus the recognised program and character slugs.
    ``blocks_all`` marks an event that closes the whole interval for everyone.
    Free-text summaries never leave this module: they may hold client data.
    """
    first = date.fromisoformat(str(date_from)) if not isinstance(date_from, date) else date_from
    last_value = date_to if date_to is not None else first
    last = date.fromisoformat(str(last_value)) if not isinstance(last_value, date) else last_value
    window_start = datetime.combine(first, datetime.min.time())
    window_end = datetime.combine(last + timedelta(days=1), datetime.min.time())
    try:
        rows = connection.execute(
            """
            SELECT * FROM google_calendar_events
            WHERE blocks_time = 1 AND start_local < ? AND end_local > ?
            ORDER BY start_local ASC
            """,
            (window_end.strftime(LOCAL_DATETIME_FORMAT), window_start.strftime(LOCAL_DATETIME_FORMAT)),
        ).fetchall()
    except sqlite3.OperationalError:
        return {}

    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        item = _imported_row_to_dict(row)
        start = _parse_local(item["start_local"])
        end = _parse_local(item["end_local"])
        if start is None or end is None:
            continue
        for iso, time_from, time_to in split_local_range_by_day(max(start, window_start), min(end, window_end)):
            by_date.setdefault(iso, []).append(
                {
                    "source": "google_calendar",
                    "event_key": item["event_key"],
                    "time_from": time_from,
                    "time_to": time_to,
                    "program_slugs": item["program_slugs"],
                    "program_slug": item["program_slugs"][0] if item["program_slugs"] else "",
                    "program_name": ", ".join(item["program_names"]),
                    "program_names": item["program_names"],
                    "character_slugs": item["character_slugs"],
                    "characters": item["character_names"],
                    "blocks_all": item["blocks_all"],
                }
            )
    return by_date


# --- overrides & aliases --------------------------------------------------------


def list_ignored_event_keys() -> set[str]:
    try:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT event_key FROM google_calendar_event_overrides WHERE ignored = 1"
            ).fetchall()
    except sqlite3.OperationalError:
        return set()
    return {str(row["event_key"]) for row in rows}


def set_event_ignored(event_key: str, ignored: bool) -> None:
    with get_connection() as connection:
        ensure_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        if ignored:
            connection.execute(
                """
                INSERT INTO google_calendar_event_overrides(event_key, ignored, updated_at) VALUES (?, 1, ?)
                ON CONFLICT(event_key) DO UPDATE SET ignored = 1, updated_at = excluded.updated_at
                """,
                (event_key, utcnow_iso()),
            )
        else:
            connection.execute("DELETE FROM google_calendar_event_overrides WHERE event_key = ?", (event_key,))
        connection.commit()


def list_aliases() -> list[dict[str, Any]]:
    try:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT id, phrase, normalized, entity_slug, created_at FROM google_calendar_aliases ORDER BY phrase COLLATE NOCASE"
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(row) for row in rows]


def add_alias(phrase: str, normalized: str, entity_slug: str) -> dict[str, Any]:
    with get_connection() as connection:
        ensure_schema(connection)
        connection.execute(
            """
            INSERT INTO google_calendar_aliases(phrase, normalized, entity_slug, created_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(normalized) DO UPDATE SET phrase = excluded.phrase, entity_slug = excluded.entity_slug
            """,
            (phrase, normalized, entity_slug, utcnow_iso()),
        )
        connection.commit()
        row = connection.execute(
            "SELECT id, phrase, normalized, entity_slug, created_at FROM google_calendar_aliases WHERE normalized = ?",
            (normalized,),
        ).fetchone()
    return dict(row) if row else {}


def delete_alias(alias_id: int) -> bool:
    with get_connection() as connection:
        cursor = connection.execute("DELETE FROM google_calendar_aliases WHERE id = ?", (int(alias_id),))
        connection.commit()
    return cursor.rowcount > 0


# --- worker lease -------------------------------------------------------------


def claim_lease(name: str, owner: str, ttl_seconds: int) -> bool:
    """Let exactly one background worker run the periodic sync at a time."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with get_connection() as connection:
        ensure_schema(connection)
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT owner, expires_at FROM google_calendar_locks WHERE name = ?",
            (name,),
        ).fetchone()
        if row and str(row["owner"]) != owner and str(row["expires_at"]) > now.isoformat():
            connection.rollback()
            return False
        connection.execute(
            """
            INSERT INTO google_calendar_locks(name, owner, expires_at) VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET owner = excluded.owner, expires_at = excluded.expires_at
            """,
            (name, owner, (now + timedelta(seconds=int(ttl_seconds))).isoformat()),
        )
        connection.commit()
    return True


def release_lease(name: str, owner: str) -> None:
    with get_connection() as connection:
        connection.execute("DELETE FROM google_calendar_locks WHERE name = ? AND owner = ?", (name, owner))
        connection.commit()
