from __future__ import annotations

import html
import os
import sqlite3
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import requests

from .config import DATA_ROOT
from .customer_store import format_date_ru

# Use the canonical admin DB (content/data/admin/site_admin.sqlite3) — same as catalog_store/customer_store.
DB_ROOT = DATA_ROOT / "admin"
DB_PATH = DB_ROOT / "site_admin.sqlite3"

TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_NOTIFY_TIMEOUT = 8
TELEGRAM_SYNC_MAX_ATTEMPTS = 8
ADMIN_PORTAL_BASE = os.environ.get("ADMIN_PORTAL_BASE", "").rstrip("/")

TERMINAL_TELEGRAM_EDIT_ERRORS = (
    "message to edit not found",
    "message not found",
    "message can't be edited",
    "message cannot be edited",
    "message can not be edited",
    "chat not found",
    "bot was blocked by the user",
    "user is deactivated",
    "bot was kicked from",
    "group chat was deactivated",
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _get_connection() -> sqlite3.Connection:
    DB_ROOT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, factory=_ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def init_admin_notifications_store() -> None:
    with _get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS admin_telegram_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL UNIQUE,
                label TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_telegram_order_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                public_id TEXT NOT NULL DEFAULT '',
                chat_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                delivery_generation TEXT NOT NULL DEFAULT '',
                quarantined_at TEXT NOT NULL DEFAULT '',
                quarantine_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            DROP INDEX IF EXISTS idx_admin_tg_msg_order_chat;
            CREATE INDEX IF NOT EXISTS idx_admin_tg_msg_order ON admin_telegram_order_messages(order_id);
            CREATE TABLE IF NOT EXISTS admin_telegram_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_telegram_processed_updates (
                update_id INTEGER PRIMARY KEY,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_telegram_sync_queue (
                order_id INTEGER PRIMARY KEY,
                state_version TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                next_attempt_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_admin_tg_sync_due
            ON admin_telegram_sync_queue(next_attempt_at, order_id);
            CREATE TABLE IF NOT EXISTS admin_telegram_sync_dead_letters (
                order_id INTEGER PRIMARY KEY,
                state_version TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL,
                last_error TEXT NOT NULL DEFAULT '',
                dead_lettered_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_telegram_delivery_queue (
                order_id INTEGER PRIMARY KEY,
                delivery_generation TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                next_attempt_at TEXT NOT NULL,
                claimed_until TEXT NOT NULL DEFAULT '',
                claim_token TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES party_orders(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_admin_tg_delivery_due
            ON admin_telegram_delivery_queue(next_attempt_at, claimed_until, order_id);
            """
        )
        connection.execute("BEGIN IMMEDIATE")
        message_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(admin_telegram_order_messages)")
        }
        if "delivery_generation" not in message_columns:
            connection.execute(
                "ALTER TABLE admin_telegram_order_messages "
                "ADD COLUMN delivery_generation TEXT NOT NULL DEFAULT ''"
            )
        if "quarantined_at" not in message_columns:
            connection.execute(
                "ALTER TABLE admin_telegram_order_messages "
                "ADD COLUMN quarantined_at TEXT NOT NULL DEFAULT ''"
            )
        if "quarantine_reason" not in message_columns:
            connection.execute(
                "ALTER TABLE admin_telegram_order_messages "
                "ADD COLUMN quarantine_reason TEXT NOT NULL DEFAULT ''"
            )
        sync_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(admin_telegram_sync_queue)")
        }
        if "state_version" not in sync_columns:
            connection.execute(
                "ALTER TABLE admin_telegram_sync_queue "
                "ADD COLUMN state_version TEXT NOT NULL DEFAULT ''"
            )
        delivery_columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(admin_telegram_delivery_queue)")
        }
        if "delivery_generation" not in delivery_columns:
            connection.execute(
                "ALTER TABLE admin_telegram_delivery_queue "
                "ADD COLUMN delivery_generation TEXT NOT NULL DEFAULT ''"
            )
            connection.execute(
                """
                UPDATE admin_telegram_delivery_queue
                SET delivery_generation = lower(hex(randomblob(16)))
                WHERE delivery_generation = ''
                """
            )
        connection.commit()


def _record_order_message(
    order_id: int,
    public_id: str,
    chat_id: str,
    message_id: int,
    delivery_generation: str = "",
) -> None:
    if not order_id or not message_id:
        return
    now = _utcnow_iso()
    with _get_connection() as connection:
        connection.execute(
            """
            INSERT INTO admin_telegram_order_messages(
                order_id, public_id, chat_id, message_id, delivery_generation, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(order_id),
                str(public_id or ""),
                str(chat_id),
                int(message_id),
                str(delivery_generation or ""),
                now,
            ),
        )
        connection.commit()


def _list_order_messages(order_id: int) -> list[dict[str, Any]]:
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT chat_id, message_id, delivery_generation
            FROM admin_telegram_order_messages
            WHERE order_id = ?
              AND quarantined_at = ''
            """,
            (int(order_id),),
        ).fetchall()
    return [
        {
            "chat_id": str(row["chat_id"]),
            "message_id": int(row["message_id"]),
            "delivery_generation": str(row["delivery_generation"] or ""),
        }
        for row in rows
    ]


def _quarantine_order_message(order_id: int, chat_id: str, message_id: int, reason: str) -> None:
    now = _utcnow_iso()
    with _get_connection() as connection:
        connection.execute(
            """
            UPDATE admin_telegram_order_messages
            SET quarantined_at = ?, quarantine_reason = ?
            WHERE order_id = ?
              AND chat_id = ?
              AND message_id = ?
              AND quarantined_at = ''
            """,
            (
                now,
                str(reason or "Terminal Telegram edit error")[:500],
                int(order_id),
                str(chat_id),
                int(message_id),
            ),
        )
        connection.commit()


def queue_order_notification(order_id: int) -> None:
    """Put a new-order card into the durable delivery outbox without blocking HTTP."""
    normalized_order_id = int(order_id)
    now = _utcnow_iso()
    delivery_generation = uuid4().hex
    with _get_connection() as connection:
        connection.execute(
            """
            INSERT INTO admin_telegram_delivery_queue(
                order_id, delivery_generation, attempts, last_error, next_attempt_at,
                claimed_until, claim_token, created_at, updated_at
            ) VALUES (?, ?, 0, '', ?, '', '', ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                delivery_generation = excluded.delivery_generation,
                attempts = 0,
                last_error = '',
                next_attempt_at = excluded.next_attempt_at,
                claimed_until = '',
                claim_token = '',
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (normalized_order_id, delivery_generation, now, now, now),
        )
        connection.commit()


def _claim_pending_order_deliveries(limit: int) -> list[dict[str, Any]]:
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    now = now_dt.isoformat()
    claimed_until = (now_dt + timedelta(minutes=2)).isoformat()
    claim_token = uuid4().hex
    with _get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        rows = connection.execute(
            """
            SELECT order_id, delivery_generation
            FROM admin_telegram_delivery_queue
            WHERE next_attempt_at <= ?
              AND (claimed_until = '' OR claimed_until <= ?)
            ORDER BY next_attempt_at ASC, order_id ASC
            LIMIT ?
            """,
            (now, now, max(1, min(100, int(limit)))),
        ).fetchall()
        order_ids = [int(row["order_id"]) for row in rows]
        generations = {
            int(row["order_id"]): str(row["delivery_generation"] or "")
            for row in rows
        }
        if order_ids:
            connection.executemany(
                """
                UPDATE admin_telegram_delivery_queue
                SET claimed_until = ?, claim_token = ?, updated_at = ?
                WHERE order_id = ?
                  AND (claimed_until = '' OR claimed_until <= ?)
                """,
                [(claimed_until, claim_token, now, order_id, now) for order_id in order_ids],
            )
        connection.commit()
    return [
        {
            "order_id": order_id,
            "claim_token": claim_token,
            "delivery_generation": generations[order_id],
        }
        for order_id in order_ids
    ]


def _defer_order_delivery(order_id: int, claim_token: str, error: str) -> None:
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    with _get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT attempts
            FROM admin_telegram_delivery_queue
            WHERE order_id = ? AND claim_token = ?
            """,
            (int(order_id), str(claim_token)),
        ).fetchone()
        if not row:
            connection.rollback()
            return
        attempts = int(row["attempts"] or 0) + 1
        retry_delay = min(1800, 15 * (2 ** min(attempts - 1, 7)))
        connection.execute(
            """
            UPDATE admin_telegram_delivery_queue
            SET attempts = ?, last_error = ?, next_attempt_at = ?,
                claimed_until = '', claim_token = '', updated_at = ?
            WHERE order_id = ? AND claim_token = ?
            """,
            (
                attempts,
                str(error or "delivery failed")[:500],
                (now_dt + timedelta(seconds=retry_delay)).isoformat(),
                now_dt.isoformat(),
                int(order_id),
                str(claim_token),
            ),
        )
        connection.commit()


def _clear_order_delivery(order_id: int, claim_token: str) -> None:
    with _get_connection() as connection:
        connection.execute(
            "DELETE FROM admin_telegram_delivery_queue WHERE order_id = ? AND claim_token = ?",
            (int(order_id), str(claim_token)),
        )
        connection.commit()


def _queue_order_sync(
    order_id: int,
    error: str,
    *,
    immediate: bool = False,
    state_version: str = "",
) -> dict[str, Any]:
    if not order_id:
        return {"queued": False, "dead_lettered": False, "attempts": 0}
    now = datetime.now(timezone.utc).replace(microsecond=0)
    normalized_order_id = int(order_id)
    normalized_version = str(state_version or "")
    normalized_error = str(error or "sync failed")[:500]
    with _get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT state_version, attempts FROM admin_telegram_sync_queue WHERE order_id = ?",
            (normalized_order_id,),
        ).fetchone()
        dead_letter = connection.execute(
            """
            SELECT state_version, attempts
            FROM admin_telegram_sync_dead_letters
            WHERE order_id = ?
            """,
            (normalized_order_id,),
        ).fetchone()

        if not normalized_version:
            if row:
                normalized_version = str(row["state_version"] or "")
            elif dead_letter:
                normalized_version = str(dead_letter["state_version"] or "")

        if dead_letter and str(dead_letter["state_version"] or "") == normalized_version:
            attempts = int(dead_letter["attempts"] or TELEGRAM_SYNC_MAX_ATTEMPTS)
            connection.execute(
                "DELETE FROM admin_telegram_sync_queue WHERE order_id = ?",
                (normalized_order_id,),
            )
            connection.commit()
            return {"queued": False, "dead_lettered": True, "attempts": attempts}

        if dead_letter:
            connection.execute(
                "DELETE FROM admin_telegram_sync_dead_letters WHERE order_id = ?",
                (normalized_order_id,),
            )

        same_version = row and str(row["state_version"] or "") == normalized_version
        attempts = int(row["attempts"] or 0) + 1 if same_version else 1
        if attempts >= TELEGRAM_SYNC_MAX_ATTEMPTS:
            connection.execute(
                """
                INSERT INTO admin_telegram_sync_dead_letters(
                    order_id, state_version, attempts, last_error, dead_lettered_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(order_id) DO UPDATE SET
                    state_version = excluded.state_version,
                    attempts = excluded.attempts,
                    last_error = excluded.last_error,
                    dead_lettered_at = excluded.dead_lettered_at,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_order_id,
                    normalized_version,
                    attempts,
                    normalized_error,
                    now.isoformat(),
                    now.isoformat(),
                ),
            )
            connection.execute(
                "DELETE FROM admin_telegram_sync_queue WHERE order_id = ?",
                (normalized_order_id,),
            )
            connection.commit()
            return {"queued": False, "dead_lettered": True, "attempts": attempts}

        retry_delay = 0 if immediate else min(900, 15 * (2 ** min(attempts - 1, 6)))
        next_attempt_at = (now + timedelta(seconds=retry_delay)).isoformat()
        connection.execute(
            """
            INSERT INTO admin_telegram_sync_queue(
                order_id, state_version, attempts, last_error, next_attempt_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                state_version = excluded.state_version,
                attempts = excluded.attempts,
                last_error = excluded.last_error,
                next_attempt_at = excluded.next_attempt_at,
                updated_at = excluded.updated_at
            """,
            (
                normalized_order_id,
                normalized_version,
                attempts,
                normalized_error,
                next_attempt_at,
                now.isoformat(),
            ),
        )
        connection.commit()
    return {"queued": True, "dead_lettered": False, "attempts": attempts}


def _get_order_sync_markers(order_id: int) -> dict[str, dict[str, Any] | None]:
    normalized_order_id = int(order_id)
    with _get_connection() as connection:
        queued = connection.execute(
            """
            SELECT state_version, attempts, last_error, next_attempt_at, updated_at
            FROM admin_telegram_sync_queue
            WHERE order_id = ?
            """,
            (normalized_order_id,),
        ).fetchone()
        dead_letter = connection.execute(
            """
            SELECT state_version, attempts, last_error, dead_lettered_at, updated_at
            FROM admin_telegram_sync_dead_letters
            WHERE order_id = ?
            """,
            (normalized_order_id,),
        ).fetchone()
    return {
        "queue": dict(queued) if queued else None,
        "dead_letter": dict(dead_letter) if dead_letter else None,
    }


def _clear_order_sync(
    order_id: int,
    markers: dict[str, dict[str, Any] | None],
    *,
    expected_state_version: str | None = None,
) -> dict[str, Any]:
    if not order_id:
        return {"cleared": True, "queued": False, "dead_lettered": False, "attempts": 0}
    normalized_order_id = int(order_id)
    with _get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        state_matches = True
        current_state_version: str | None = None
        if expected_state_version is not None:
            order = connection.execute(
                "SELECT confirmation_changed_at FROM party_orders WHERE id = ?",
                (normalized_order_id,),
            ).fetchone()
            current_state_version = str(order["confirmation_changed_at"] or "") if order else None
            state_matches = bool(
                order
                and current_state_version == str(expected_state_version or "")
            )

        queue_marker = markers.get("queue")
        if state_matches and queue_marker:
            connection.execute(
                """
                DELETE FROM admin_telegram_sync_queue
                WHERE order_id = ?
                  AND state_version = ?
                  AND attempts = ?
                  AND last_error = ?
                  AND next_attempt_at = ?
                  AND updated_at = ?
                """,
                (
                    normalized_order_id,
                    str(queue_marker.get("state_version") or ""),
                    int(queue_marker.get("attempts") or 0),
                    str(queue_marker.get("last_error") or ""),
                    str(queue_marker.get("next_attempt_at") or ""),
                    str(queue_marker.get("updated_at") or ""),
                ),
            )

        dead_letter_marker = markers.get("dead_letter")
        if state_matches and dead_letter_marker:
            connection.execute(
                """
                DELETE FROM admin_telegram_sync_dead_letters
                WHERE order_id = ?
                  AND state_version = ?
                  AND attempts = ?
                  AND last_error = ?
                  AND dead_lettered_at = ?
                  AND updated_at = ?
                """,
                (
                    normalized_order_id,
                    str(dead_letter_marker.get("state_version") or ""),
                    int(dead_letter_marker.get("attempts") or 0),
                    str(dead_letter_marker.get("last_error") or ""),
                    str(dead_letter_marker.get("dead_lettered_at") or ""),
                    str(dead_letter_marker.get("updated_at") or ""),
                ),
            )

        queued = connection.execute(
            "SELECT attempts FROM admin_telegram_sync_queue WHERE order_id = ?",
            (normalized_order_id,),
        ).fetchone()
        dead_letter = connection.execute(
            "SELECT attempts FROM admin_telegram_sync_dead_letters WHERE order_id = ?",
            (normalized_order_id,),
        ).fetchone()
        connection.commit()
    pending = queued or dead_letter
    return {
        "cleared": state_matches and not pending,
        "state_matches": state_matches,
        "current_state_version": current_state_version,
        "queued": queued is not None,
        "dead_lettered": dead_letter is not None,
        "attempts": int(pending["attempts"] or 0) if pending else 0,
    }


def get_setting(key: str) -> str:
    try:
        with _get_connection() as connection:
            row = connection.execute(
                "SELECT value FROM admin_telegram_settings WHERE key = ?",
                (str(key),),
            ).fetchone()
        return str(row["value"]) if row else ""
    except Exception:
        return ""


def set_setting(key: str, value: str) -> None:
    now = _utcnow_iso()
    with _get_connection() as connection:
        connection.execute(
            """
            INSERT INTO admin_telegram_settings(key, value, updated_at) VALUES(?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (str(key), str(value or "").strip(), now),
        )
        connection.commit()


def _bot_token() -> str:
    return (
        get_setting("bot_token")
        or os.environ.get("TELEGRAM_NOTIFY_BOT_TOKEN", "").strip()
        or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    )


def is_notifications_configured() -> bool:
    return bool(_bot_token())


def bot_token_masked() -> str:
    """Return the configured bot token masked: keep first 8 + last 4 chars, replace middle with stars.
    If empty, return empty string."""
    token = _bot_token()
    if not token:
        return ""
    if len(token) <= 12:
        return "*" * len(token)
    return token[:8] + "*" * (len(token) - 12) + token[-4:]


def gateway_token_masked() -> str:
    """Mask Telegram Gateway access token (DB-stored) for display in admin UI."""
    token = (get_setting("telegram_gateway_token") or os.environ.get("TELEGRAM_GATEWAY_TOKEN", "")).strip()
    if not token:
        return ""
    if len(token) <= 12:
        return "*" * len(token)
    return token[:8] + "*" * (len(token) - 12) + token[-4:]


def list_recipients(active_only: bool = False) -> list[dict[str, Any]]:
    with _get_connection() as connection:
        query = "SELECT id, chat_id, label, is_active, created_at, updated_at FROM admin_telegram_recipients"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY created_at ASC"
        rows = connection.execute(query).fetchall()
    return [
        {
            "id": int(row["id"]),
            "chat_id": str(row["chat_id"]),
            "label": str(row["label"] or ""),
            "is_active": bool(row["is_active"]),
            "created_at": str(row["created_at"] or ""),
            "created_at_label": format_date_ru(str(row["created_at"] or "")[:10]),
            "updated_at": str(row["updated_at"] or ""),
            "updated_at_label": format_date_ru(str(row["updated_at"] or "")[:10]),
        }
        for row in rows
    ]


def _is_active_recipient_chat(chat_id: str) -> bool:
    chat_id_clean = str(chat_id or "").strip()
    if not chat_id_clean:
        return False
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM admin_telegram_recipients WHERE chat_id = ? AND is_active = 1 LIMIT 1",
            (chat_id_clean,),
        ).fetchone()
    return row is not None


def add_recipient(chat_id: str, label: str = "") -> dict[str, Any]:
    chat_id_clean = (chat_id or "").strip()
    label_clean = (label or "").strip()
    if not chat_id_clean:
        return {"success": False, "message": "Укажите Telegram chat_id."}
    if not _is_valid_chat_id(chat_id_clean):
        return {"success": False, "message": "Некорректный chat_id. Это должно быть число (например, 123456789)."}

    now = _utcnow_iso()
    try:
        with _get_connection() as connection:
            connection.execute(
                """
                INSERT INTO admin_telegram_recipients (chat_id, label, is_active, created_at, updated_at)
                VALUES (?, ?, 1, ?, ?)
                """,
                (chat_id_clean, label_clean, now, now),
            )
            connection.commit()
    except sqlite3.IntegrityError:
        return {"success": False, "message": "Этот chat_id уже добавлен."}
    return {"success": True, "message": "Получатель добавлен."}


def delete_recipient(recipient_id: int) -> dict[str, Any]:
    with _get_connection() as connection:
        cursor = connection.execute(
            "DELETE FROM admin_telegram_recipients WHERE id = ?",
            (int(recipient_id),),
        )
        connection.commit()
    if cursor.rowcount == 0:
        return {"success": False, "message": "Получатель не найден."}
    return {"success": True, "message": "Получатель удалён."}


def toggle_recipient(recipient_id: int, is_active: bool) -> dict[str, Any]:
    now = _utcnow_iso()
    with _get_connection() as connection:
        cursor = connection.execute(
            "UPDATE admin_telegram_recipients SET is_active = ?, updated_at = ? WHERE id = ?",
            (1 if is_active else 0, now, int(recipient_id)),
        )
        connection.commit()
    if cursor.rowcount == 0:
        return {"success": False, "message": "Получатель не найден."}
    return {"success": True, "message": "Статус обновлён."}


def _is_valid_chat_id(value: str) -> bool:
    candidate = value.strip()
    if candidate.startswith("-"):
        candidate = candidate[1:]
    return candidate.isdigit() and 5 <= len(candidate) <= 16


def _send_telegram_message(chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _bot_token()
    if not token:
        return {"success": False, "message": "Telegram-бот не настроен (TELEGRAM_NOTIFY_BOT_TOKEN не задан)."}
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    body: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    try:
        response = requests.post(
            url,
            json=body,
            timeout=TELEGRAM_NOTIFY_TIMEOUT,
        )
    except requests.RequestException:
        return {"success": False, "message": "Сеть Telegram недоступна."}

    if not response.ok:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        description = str(payload.get("description") or response.text or "ошибка").strip()
        return {"success": False, "message": f"Telegram отверг сообщение: {description}"}
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return {
        "success": True,
        "message": "Сообщение отправлено.",
        "result": payload.get("result") or {},
    }


def _send_telegram_location(chat_id: str, latitude: float, longitude: float) -> dict[str, Any]:
    token = _bot_token()
    if not token:
        return {"success": False, "message": "Telegram-бот не настроен."}
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendLocation"
    try:
        response = requests.post(
            url,
            json={"chat_id": chat_id, "latitude": float(latitude), "longitude": float(longitude)},
            timeout=TELEGRAM_NOTIFY_TIMEOUT,
        )
    except requests.RequestException:
        return {"success": False, "message": "Сеть Telegram недоступна."}
    if not response.ok:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        description = str(payload.get("description") or response.text or "ошибка").strip()
        return {"success": False, "message": f"Telegram отверг геопозицию: {description}"}
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return {"success": True, "message": "Гео отправлено.", "result": payload.get("result") or {}}


def _is_terminal_telegram_edit_error(description: str) -> bool:
    normalized = str(description or "").strip().lower()
    return any(marker in normalized for marker in TERMINAL_TELEGRAM_EDIT_ERRORS)


def _edit_telegram_message(chat_id: str, message_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _bot_token()
    if not token:
        return {"success": False, "message": "Telegram-бот не настроен."}
    url = f"{TELEGRAM_API_BASE}/bot{token}/editMessageText"
    body: dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": int(message_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        body["reply_markup"] = reply_markup
    try:
        response = requests.post(url, json=body, timeout=TELEGRAM_NOTIFY_TIMEOUT)
    except requests.RequestException:
        return {"success": False, "message": "Сеть Telegram недоступна."}
    if not response.ok:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        description = str(payload.get("description") or response.text or "ошибка").strip()
        if "message is not modified" in description.lower():
            return {"success": True, "message": "Сообщение уже синхронизировано.", "unchanged": True}
        return {
            "success": False,
            "message": f"Telegram отверг изменение: {description}",
            "terminal_mapping": _is_terminal_telegram_edit_error(description),
        }
    return {"success": True, "message": "Сообщение обновлено."}


def _answer_callback(callback_query_id: str, text: str = "") -> dict[str, Any]:
    token = _bot_token()
    if not token or not callback_query_id:
        return {"success": False, "message": "Нет токена или callback id."}
    url = f"{TELEGRAM_API_BASE}/bot{token}/answerCallbackQuery"
    try:
        response = requests.post(
            url,
            json={"callback_query_id": callback_query_id, "text": text or "Готово"},
            timeout=TELEGRAM_NOTIFY_TIMEOUT,
        )
    except requests.RequestException:
        return {"success": False, "message": "Сеть Telegram недоступна."}
    return {"success": response.ok}


def send_test_message(chat_id: str) -> dict[str, Any]:
    return _send_telegram_message(
        chat_id,
        "✅ Surpriz: тестовое уведомление. Если вы получили это, бот работает.",
    )


def _escape_html(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _format_order_message(order: dict[str, Any]) -> str:
    escape = _escape_html
    public_id = escape(order.get("public_id") or "")
    program = escape(order.get("program_name") or "—")
    raw_date = str(order.get("celebration_date") or "")
    month_names = (
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    try:
        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d")
        celebration_date = f"{parsed_date.day} {month_names[parsed_date.month - 1]}"
    except ValueError:
        celebration_date = str(order.get("celebration_date_label") or format_date_ru(raw_date) or "—")
    time_from = str(order.get("time_from") or "").replace(":", ".")
    duration_minutes = int(order.get("duration_minutes") or 0)
    if duration_minutes and duration_minutes % 60 == 0:
        hours = duration_minutes // 60
        duration_label = f"{hours} час" if hours == 1 else f"{hours} часа"
    elif duration_minutes > 60:
        duration_label = f"{duration_minutes // 60} час {duration_minutes % 60} минут"
    else:
        duration_label = f"{duration_minutes} минут" if duration_minutes else ""
    address = escape(order.get("address_text") or "—")
    map_url = escape(order.get("yandex_map_url"))
    customer_phone = escape(order.get("customer_phone") or order.get("customer_phone_display") or "—")
    customer_name = escape(str(order.get("customer_name") or "").strip() or "Без имени")
    # Заказ можно оформить без регистрации, поэтому номер бывает непроверенным —
    # менеджеру это важно знать до звонка.
    phone_note = "" if order.get("customer_phone_verified_at") else " · номер не подтверждён"
    total_label = escape(order.get("total_price_label") or "—")
    notes_full = str(order.get("notes") or "")
    characters = order.get("character_names") or []
    roster: list[str] = []
    import re as _re
    for character in characters:
        raw_character = str(character or "").strip()
        match = _re.search(r"\d+\s+артист(?:а|ов)?:\s*([^;)]+)", raw_character)
        if match:
            roster.extend(part.strip() for part in match.group(1).split(",") if part.strip())
        elif raw_character:
            roster.append(raw_character.split(" (", 1)[0].strip())
    characters_label = " + ".join(escape(item) for item in roster)
    celebrant_name = escape(order.get("celebrant_name")).strip()
    celebrant_age = order.get("celebrant_age")
    children_count = order.get("children_count")
    status_label = escape(order.get("status_label") or order.get("confirmation_label") or "Не подтверждён")

    bonus_label = ""
    gift_labels = _re.findall(r"\[Подарок:\s*([^\]]+)\]", notes_full)
    m = _re.search(r"\[Бонус:\s*([^\]]+)\]", notes_full)
    if m:
        bonus_label = escape(m.group(1).strip())
    gift_labels = [escape(item) for item in gift_labels]
    notes = escape(_re.sub(r"\[(?:Бонус|Подарок):\s*[^\]]+\]\s*", "", notes_full).strip())

    program_line = program
    if characters_label:
        program_line += f" ({characters_label})"
    if duration_label:
        program_line += f" · {duration_label}"
    age_label = ""
    if celebrant_age not in (None, ""):
        age_label = f" {escape(celebrant_age)} года"

    lines = [
        f"📅 <b>{escape(celebration_date)} в {escape(time_from or '—')}</b>",
        f"<b>Программа:</b> {program_line}",
        f"<b>Сумма:</b> {total_label}",
        f"<b>Именинник(ца):</b> {celebrant_name or '—'}{age_label}",
        f"<b>Кол-во детей:</b> {escape(children_count) if children_count not in (None, '') else '—'}",
        f"<b>Адрес:</b> {address}" + (f" · <a href=\"{map_url}\">Локация</a>" if map_url else ""),
        f"<b>Комментарий к заказу:</b> {notes or '—'}",
    ]
    gifts = [label for label in [bonus_label, *gift_labels] if label]
    if gifts:
        lines.append(f"<b>Бонус:</b> {', '.join(gifts)}")
    lines.extend([
        "",
        "<b>Контакты:</b>",
        f"{customer_name} · <code>{customer_phone}</code>{phone_note}",
        "",
        f"Заказ {public_id} · {status_label}",
    ])
    if ADMIN_PORTAL_BASE:
        public_id = str(order.get("public_id") or "")
        portal_url = escape(f"{ADMIN_PORTAL_BASE}/admin/orders?search={quote(public_id, safe='')}")
        lines.extend(["", f"<a href=\"{portal_url}\">Открыть в админке</a>"])
    return "\n".join(lines)


def _build_order_keyboard(
    public_id: str,
    order_id: int,
    confirmation_state: str = "unconfirmed",
    lifecycle_status: str = "",
) -> dict[str, Any]:
    if lifecycle_status in {"cancelled", "done"}:
        return {"inline_keyboard": []}
    pid = str(public_id or order_id or "")
    if confirmation_state == "confirmed":
        button = {"text": "↩️ Снять подтверждение", "callback_data": f"order:{pid}:unconfirm"}
    else:
        button = {"text": "✅ Подтвердить", "callback_data": f"order:{pid}:confirm"}
    reject_button = {"text": "❌ Отклонить", "callback_data": f"order:{pid}:cancel"}
    return {
        "inline_keyboard": [
            [button, reject_button]
        ]
    }


def _deliver_order_notification(
    order: dict[str, Any],
    delivery_generation: str,
) -> dict[str, Any]:
    """Deliver one queued order, skipping chats whose card is already recorded."""
    if not is_notifications_configured():
        return {"success": False, "message": "Бот не настроен.", "delivered": 0, "failed": 0}

    recipients = list_recipients(active_only=True)
    if not recipients:
        return {"success": False, "message": "Нет активных получателей.", "delivered": 0, "failed": 0}

    text = _format_order_message(order)
    public_id = str(order.get("public_id") or "")
    order_id = int(order.get("id") or 0)
    captured_state_version = (
        str(order.get("confirmation_changed_at") or ""),
        str(order.get("status") or ""),
    )
    keyboard = _build_order_keyboard(
        public_id,
        order_id,
        str(order.get("confirmation_state") or "unconfirmed"),
        str(order.get("status") or ""),
    )
    raw_lat = order.get("location_lat") if order.get("location_lat") is not None else order.get("map_lat")
    raw_lng = order.get("location_lng") if order.get("location_lng") is not None else order.get("map_lng")
    try:
        lat_value = float(raw_lat) if raw_lat not in (None, "") else None
        lng_value = float(raw_lng) if raw_lng not in (None, "") else None
    except (TypeError, ValueError):
        lat_value = lng_value = None

    delivered_chats = {
        message["chat_id"]
        for message in _list_order_messages(order_id)
        if message["delivery_generation"] == delivery_generation
    }
    pending_recipients = [
        recipient
        for recipient in recipients
        if str(recipient["chat_id"]) not in delivered_chats
    ]
    if not pending_recipients:
        return {
            "success": True,
            "message": f"Все {len(recipients)} получателей уже уведомлены.",
            "delivered": 0,
            "failed": 0,
            "already_delivered": len(recipients),
        }

    def _send_card(recipient: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        result = _send_telegram_message(recipient["chat_id"], text, reply_markup=keyboard)
        if result.get("success") and lat_value is not None and lng_value is not None:
            try:
                _send_telegram_location(recipient["chat_id"], lat_value, lng_value)
            except Exception:
                pass
        return recipient, result

    delivered = 0
    failed = 0
    last_error = ""
    worker_count = min(6, len(pending_recipients))
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="tg-delivery") as executor:
        futures = [executor.submit(_send_card, recipient) for recipient in pending_recipients]
        for future in as_completed(futures):
            try:
                recipient, result = future.result()
            except Exception:
                failed += 1
                last_error = "Неожиданная ошибка Telegram delivery."
                continue
            if not result.get("success"):
                failed += 1
                last_error = str(result.get("message") or "Telegram delivery failed")
                print(
                    f"[tg-notify] delivery deferred for chat_id={recipient['chat_id']}",
                    flush=True,
                )
                continue
            tg_result = result.get("result") or {}
            message_id = tg_result.get("message_id")
            if not order_id or not message_id:
                failed += 1
                last_error = "Telegram не вернул message_id."
                continue
            try:
                _record_order_message(
                    order_id,
                    public_id,
                    recipient["chat_id"],
                    int(message_id),
                    delivery_generation,
                )
            except sqlite3.Error:
                failed += 1
                last_error = "Не удалось сохранить доставленное сообщение."
                continue
            delivered += 1

    success = failed == 0
    sync_queued = False
    if delivered:
        try:
            from .customer_store import get_order_by_id

            latest_order = get_order_by_id(order_id)
        except (ImportError, sqlite3.Error, RuntimeError):
            latest_order = None
            queue_result = _queue_order_sync(
                order_id,
                "Order recheck failed after delivery",
                immediate=True,
            )
            sync_queued = bool(queue_result["queued"])
        if latest_order:
            latest_state_version = (
                str(latest_order.get("confirmation_changed_at") or ""),
                str(latest_order.get("status") or ""),
            )
            if latest_state_version != captured_state_version:
                queue_result = _queue_order_sync(
                    order_id,
                    "Order state changed during delivery",
                    immediate=True,
                    state_version=latest_state_version[0],
                )
                sync_queued = bool(queue_result["queued"])
    message = f"Отправлено {delivered} из {len(pending_recipients)}."
    if failed and last_error:
        message += f" Последняя ошибка: {last_error}"
    return {
        "success": success,
        "message": message,
        "delivered": delivered,
        "failed": failed,
        "already_delivered": len(delivered_chats),
        "sync_queued": sync_queued,
    }


def send_order_notification(order: dict[str, Any]) -> dict[str, Any]:
    """Compatibility/admin entry point: enqueue immediately; the bot worker delivers."""
    order_id = int(order.get("id") or 0)
    if not order_id:
        return {"success": False, "message": "Заказ не найден.", "delivered": 0, "failed": 1}
    queue_order_notification(order_id)
    return {
        "success": True,
        "message": "Уведомление поставлено в очередь Telegram.",
        "delivered": 0,
        "failed": 0,
        "queued": True,
    }


def process_pending_order_deliveries(limit: int = 12) -> dict[str, int]:
    """Claim and deliver due new-order cards with retry and stale-worker protection."""
    succeeded = 0
    failed = 0
    processed = 0
    for _ in range(max(1, min(100, int(limit)))):
        claimed = _claim_pending_order_deliveries(1)
        if not claimed:
            break
        item = claimed[0]
        processed += 1
        order_id = int(item["order_id"])
        claim_token = str(item["claim_token"])
        delivery_generation = str(item["delivery_generation"])
        try:
            from .customer_store import get_order_by_id

            order = get_order_by_id(order_id)
        except (ImportError, sqlite3.Error, RuntimeError) as exc:
            _defer_order_delivery(
                order_id,
                claim_token,
                f"Order lookup failed: {type(exc).__name__}",
            )
            failed += 1
            continue
        if not order:
            _clear_order_delivery(order_id, claim_token)
            succeeded += 1
            continue
        result = _deliver_order_notification(order, delivery_generation)
        if result.get("success"):
            _clear_order_delivery(order_id, claim_token)
            succeeded += 1
        else:
            _defer_order_delivery(order_id, claim_token, str(result.get("message") or "delivery failed"))
            failed += 1
    return {"processed": processed, "succeeded": succeeded, "failed": failed}


def sync_order_messages(order_id: int) -> dict[str, Any]:
    """Edit every delivered Telegram card to the persisted confirmation state."""
    normalized_order_id = int(order_id)
    try:
        sync_markers = _get_order_sync_markers(normalized_order_id)
        messages = _list_order_messages(normalized_order_id)
    except sqlite3.Error as exc:
        message = f"Message lookup failed: {type(exc).__name__}"
        queue_result = _queue_order_sync(normalized_order_id, message)
        return {
            "success": False,
            "updated": 0,
            "failed": 0,
            "message": "Синхронизация поставлена в очередь.",
            **queue_result,
        }
    if not messages:
        clear_result = _clear_order_sync(normalized_order_id, sync_markers)
        return {
            "success": bool(clear_result["cleared"]),
            "updated": 0,
            "failed": 0,
            "message": "Нет сообщений для обновления.",
            "queued": bool(clear_result["queued"]),
            "dead_lettered": bool(clear_result["dead_lettered"]),
            "attempts": int(clear_result["attempts"]),
        }
    if not is_notifications_configured():
        message = "Бот не настроен. Синхронизация поставлена в очередь."
        queue_result = _queue_order_sync(normalized_order_id, message)
        return {
            "success": False,
            "updated": 0,
            "failed": len(messages),
            "message": message,
            **queue_result,
        }

    try:
        from .customer_store import get_order_by_id

        order = get_order_by_id(normalized_order_id)
    except (ImportError, sqlite3.Error, RuntimeError) as exc:
        message = f"Order lookup failed: {type(exc).__name__}"
        queue_result = _queue_order_sync(normalized_order_id, message)
        return {
            "success": False,
            "updated": 0,
            "failed": len(messages),
            "message": "Синхронизация поставлена в очередь.",
            **queue_result,
        }
    if not order:
        clear_result = _clear_order_sync(normalized_order_id, sync_markers)
        return {
            "success": False,
            "updated": 0,
            "failed": len(messages),
            "message": "Заказ не найден.",
            "queued": bool(clear_result["queued"]),
            "dead_lettered": bool(clear_result["dead_lettered"]),
            "attempts": int(clear_result["attempts"]),
        }

    text = _format_order_message(order)
    captured_version = str(order.get("confirmation_changed_at") or "")
    keyboard = _build_order_keyboard(
        str(order.get("public_id") or ""),
        int(order.get("id") or 0),
        str(order.get("confirmation_state") or "unconfirmed"),
        str(order.get("status") or ""),
    )
    unique_messages = list({
        (message["chat_id"], int(message["message_id"])): message
        for message in messages
    }.values())
    updated = 0
    quarantined = 0
    failures: list[str] = []
    worker_count = min(6, len(unique_messages))
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="tg-sync") as executor:
        futures = {
            executor.submit(
                _edit_telegram_message,
                message["chat_id"],
                message["message_id"],
                text,
                reply_markup=keyboard,
            ): message
            for message in unique_messages
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception:
                result = {"success": False, "message": "Неожиданная ошибка Telegram sync."}
            if result.get("success"):
                updated += 1
            elif result.get("terminal_mapping"):
                message = futures[future]
                try:
                    _quarantine_order_message(
                        normalized_order_id,
                        message["chat_id"],
                        message["message_id"],
                        str(result.get("message") or "Terminal Telegram edit error"),
                    )
                except sqlite3.Error as exc:
                    failures.append(f"Message quarantine failed: {type(exc).__name__}")
                else:
                    quarantined += 1
            else:
                failures.append(str(result.get("message") or "Telegram sync failed"))
    failed = len(failures)
    try:
        latest_order = get_order_by_id(normalized_order_id)
    except (sqlite3.Error, RuntimeError):
        latest_order = None
    latest_version = str((latest_order or {}).get("confirmation_changed_at") or "")
    state_changed_during_sync = not latest_order or latest_version != captured_version
    queue_result = {"queued": False, "dead_lettered": False, "attempts": 0}
    if state_changed_during_sync:
        queue_result = _queue_order_sync(
            normalized_order_id,
            "Order state changed during Telegram sync",
            immediate=True,
            state_version=latest_version,
        )
    elif failed:
        queue_result = _queue_order_sync(
            normalized_order_id,
            failures[0],
            state_version=captured_version,
        )
    else:
        clear_result = _clear_order_sync(
            normalized_order_id,
            sync_markers,
            expected_state_version=captured_version,
        )
        if not clear_result["cleared"]:
            state_changed_during_sync = True
            if not clear_result["state_matches"]:
                queue_result = _queue_order_sync(
                    normalized_order_id,
                    "Order state changed before Telegram sync acknowledgement",
                    immediate=True,
                    state_version=str(clear_result["current_state_version"] or ""),
                )
            else:
                queue_result = {
                    "queued": bool(clear_result["queued"]),
                    "dead_lettered": bool(clear_result["dead_lettered"]),
                    "attempts": int(clear_result["attempts"]),
                }
    return {
        "success": failed == 0 and not state_changed_during_sync,
        "updated": updated,
        "quarantined": quarantined,
        "failed": failed,
        "message": f"Обновлено {updated}, исключено {quarantined} из {len(unique_messages)}.",
        **queue_result,
    }


def process_pending_order_syncs(limit: int = 12) -> dict[str, int]:
    now = _utcnow_iso()
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT order_id
            FROM admin_telegram_sync_queue
            WHERE next_attempt_at <= ?
            ORDER BY next_attempt_at ASC, order_id ASC
            LIMIT ?
            """,
            (now, max(1, min(100, int(limit)))),
        ).fetchall()

    succeeded = 0
    failed = 0
    for row in rows:
        result = sync_order_messages(int(row["order_id"]))
        if result.get("success"):
            succeeded += 1
        else:
            failed += 1
    return {"processed": len(rows), "succeeded": succeeded, "failed": failed}


def update_order_messages_status(
    order_id: int,
    public_id: str = "",
    status_label: str = "",
    decided_by: str = "",
) -> None:
    """Compatibility wrapper for older callers."""
    del public_id, status_label, decided_by
    sync_order_messages(order_id)


def handle_callback(update: dict[str, Any]) -> dict[str, Any]:
    """Process Telegram update — message commands or callback_query for orders."""
    # Plain text message handler (commands + chitchat)
    if "message" in update:
        return _handle_message(update["message"])

    callback = update.get("callback_query") or {}
    if not callback:
        return {"success": False, "message": "no callback"}
    data = str(callback.get("data") or "")
    callback_id = str(callback.get("id") or "")
    from_user = callback.get("from") or {}
    callback_chat = (callback.get("message") or {}).get("chat") or {}
    callback_chat_id = str(callback_chat.get("id") or "")
    if not _is_active_recipient_chat(callback_chat_id):
        _answer_callback(callback_id, "Нет доступа")
        return {"success": False, "message": "unauthorized chat"}

    user_label = (
        (from_user.get("username") and f"@{from_user['username']}")
        or str(from_user.get("first_name") or "admin")
    )
    user_id = str(from_user.get("id") or "").strip()
    actor = f"{user_label} ({user_id})" if user_id else user_label

    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "order":
        _answer_callback(callback_id, "Неизвестная команда")
        return {"success": False, "message": "bad data"}
    public_id, action = parts[1], parts[2]
    if action not in {"confirm", "unconfirm", "cancel"}:
        _answer_callback(callback_id, "Неизвестное действие")
        return {"success": False, "message": "bad action"}

    try:
        from .customer_store import (
            apply_legacy_order_cancellation_by_public_id,
            set_order_confirmation_by_public_id,
        )
    except ImportError:
        _answer_callback(callback_id, "Сервис недоступен")
        return {"success": False, "message": "store missing"}

    confirmation_state = "confirmed" if action == "confirm" else "unconfirmed"
    if action == "cancel":
        result = apply_legacy_order_cancellation_by_public_id(
            public_id,
            source="telegram-legacy",
            actor=actor,
        )
    else:
        result = set_order_confirmation_by_public_id(
            public_id,
            confirmation_state,
            source="telegram",
            actor=actor,
        )
    if not result.get("success"):
        terminal = result.get("message") == "terminal order state is immutable"
        _answer_callback(callback_id, "Завершённый заказ нельзя изменить" if terminal else "Заказ не найден")
        return {"success": False, "message": result.get("message") or "order not found"}

    if action == "cancel":
        label = "🚫 Заказ отменён" if result.get("changed") else "Заказ уже отменён"
    else:
        label = "✅ Подтверждён" if confirmation_state == "confirmed" else "↩️ Подтверждение снято"
    if action != "cancel" and not result.get("changed"):
        label = "Уже подтверждён" if confirmation_state == "confirmed" else "Уже не подтверждён"
    _answer_callback(callback_id, f"{label}: {public_id}")
    sync_order_messages(int(result.get("order_id") or 0))
    if result.get("changed"):
        # The order is already queued for Google Calendar in the same
        # transaction; wake the sync thread so the event appears right away.
        _wake_calendar_sync()
    return {
        "success": True,
        "changed": bool(result.get("changed")),
        "message": f"{public_id} → {confirmation_state}",
    }


def _wake_calendar_sync() -> None:
    try:
        from .google_calendar import wake_worker

        wake_worker()
    except Exception:
        return


def _start_calendar_sync() -> None:
    try:
        from .google_calendar import start_worker_in_background

        start_worker_in_background()
    except Exception as exc:
        print(f"[gcal] worker not started after {type(exc).__name__}", flush=True)


def _handle_message(message: dict[str, Any]) -> dict[str, Any]:
    """Reply to text messages: handle commands /start /help /orders /status, plus polite chitchat."""
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return {"success": False, "message": "no chat"}
    if not _is_active_recipient_chat(chat_id):
        _send_telegram_message(
            chat_id,
            "⛔️ Этот chat_id не добавлен в список активных получателей Surpriz. "
            f"Передайте администратору: <code>{html.escape(chat_id)}</code>",
        )
        return {"success": False, "message": "unauthorized chat"}

    text = str(message.get("text") or "").strip()
    text_lower = text.lower()
    from_user = message.get("from") or {}
    name = _escape_html(from_user.get("first_name") or "друг").strip()

    # Recognise commands
    if text.startswith("/start"):
        reply = (
            f"👋 Привет, <b>{name}</b>!\n\n"
            "Я — бот Surpriz. Буду присылать тебе новые заказы с кнопками "
            "<b>Подтвердить</b>, <b>Снять подтверждение</b> и <b>Отклонить</b>.\n\n"
            "Команды:\n"
            "/help — помощь\n"
            "/orders — последние 5 заказов\n"
            "/status — статус бота\n\n"
            f"Твой <code>chat_id</code>: <code>{chat_id}</code>"
        )
        _send_telegram_message(chat_id, reply)
        return {"success": True}

    if text.startswith("/help"):
        reply = (
            "<b>Surpriz bot — помощь</b>\n\n"
            "🎉 Когда клиент создаёт заказ на сайте, я пришлю карточку с:\n"
            "  • Программой и персонажами\n"
            "  • Датой и временем\n"
            "  • Контактами клиента\n"
            "  • Адресом\n"
            "  • Суммой и способом оплаты\n\n"
            "Под карточкой можно подтвердить заказ, снять подтверждение или отклонить заказ. "
            "Изменение сразу появится в админке.\n\n"
            "<b>Команды:</b>\n"
            "/start — приветствие\n"
            "/orders — последние 5 заказов\n"
            "/status — статус бота"
        )
        _send_telegram_message(chat_id, reply)
        return {"success": True}

    if text.startswith("/orders"):
        try:
            from .customer_store import list_admin_orders

            rows = list_admin_orders(limit=5)
            if not rows:
                _send_telegram_message(chat_id, "Заказов пока нет.")
                return {"success": True}
            lines = ["<b>Последние 5 заказов:</b>", ""]
            status_emoji = {"unconfirmed": "🕓", "confirmed": "✅"}
            for r in rows:
                state = str(r.get("confirmation_state") or "unconfirmed")
                emoji = status_emoji.get(state, "•")
                pid = html.escape(str(r.get("public_id") or ""))
                name_o = html.escape(str(r.get("customer_name") or "—"))
                date = format_date_ru(str(r.get("celebration_date") or "")) or "—"
                tm = f"{r.get('time_from') or ''}–{r.get('time_to') or ''}".strip("–")
                price = int(r.get("total_price") or 0)
                lines.append(
                    f"{emoji} <b>{pid}</b> · {name_o}\n   {date} {tm} · {price:,} сум".replace(",", " ")
                )
            _send_telegram_message(chat_id, "\n\n".join(lines))
        except Exception:
            _send_telegram_message(chat_id, "Не удалось загрузить заказы. Попробуйте ещё раз позже.")
        return {"success": True}

    if text.startswith("/status"):
        recipients = list_recipients(active_only=True)
        active = sum(1 for r in recipients if r.get("is_active"))
        reply = (
            "<b>📊 Статус Surpriz Bot</b>\n\n"
            f"✅ Бот онлайн\n"
            f"👥 Активных получателей: {active}\n"
            f"🆔 Твой chat_id: <code>{chat_id}</code>"
        )
        _send_telegram_message(chat_id, reply)
        return {"success": True}

    # Chitchat
    if any(g in text_lower for g in ("привет", "здравств", "hello", "hi ", "hey")):
        _send_telegram_message(chat_id, f"Привет, <b>{name}</b>! 👋\nНапиши /help чтобы увидеть что я умею.")
        return {"success": True}
    if any(g in text_lower for g in ("спасибо", "thanks", "thx", "благодар")):
        _send_telegram_message(chat_id, "Всегда пожалуйста! 🤝")
        return {"success": True}
    if any(g in text_lower for g in ("пока", "до свид", "bye", "до встреч")):
        _send_telegram_message(chat_id, "До встречи! 👋")
        return {"success": True}
    if "?" in text or any(g in text_lower for g in ("как", "что", "когда", "где")):
        _send_telegram_message(
            chat_id,
            "Я простой бот для уведомлений. По общим вопросам — звони менеджеру: "
            "<a href=\"tel:+998998926565\">+998 99 892‑65‑65</a>\n\n"
            "Или жми /help",
        )
        return {"success": True}

    # Fallback
    _send_telegram_message(
        chat_id,
        "Не понял. 🤔\nПопробуй /help — там список команд.",
    )
    return {"success": True}


# === Long-polling fallback (when no public webhook is reachable) ===

_POLLING_THREAD: "object | None" = None
_POLLING_STOP = False


def _is_update_processed(update_id: int) -> bool:
    if not update_id:
        return False
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT 1 FROM admin_telegram_processed_updates WHERE update_id = ? LIMIT 1",
            (int(update_id),),
        ).fetchone()
    return row is not None


def _mark_update_processed(update_id: int) -> None:
    if not update_id:
        return
    with _get_connection() as connection:
        connection.execute(
            "INSERT OR IGNORE INTO admin_telegram_processed_updates(update_id, created_at) VALUES(?, ?)",
            (int(update_id), _utcnow_iso()),
        )
        connection.commit()


def _process_polled_updates(updates: list[dict[str, Any]], offset: int) -> tuple[int, bool]:
    current_offset = int(offset)
    for update in updates:
        update_id = int(update.get("update_id", 0))
        if _is_update_processed(update_id):
            current_offset = max(current_offset, update_id + 1)
            continue
        try:
            handle_callback(update)
            _mark_update_processed(update_id)
        except Exception as exc:
            print(f"[tg-poll] update deferred after {type(exc).__name__}", flush=True)
            return current_offset, False
        current_offset = max(current_offset, update_id + 1)
    return current_offset, True


def _poll_loop() -> None:
    """Background long-poll loop. Auto-handles updates via handle_callback.
    If no token configured at start, idle and re-check periodically (token may be set later via admin UI)."""
    global _POLLING_STOP
    offset = 0
    backoff = 1
    import time as _time
    while not _POLLING_STOP:
        token = _bot_token()
        if not token:
            _time.sleep(5)
            continue
        try:
            try:
                process_pending_order_deliveries()
            except Exception as exc:
                print(f"[tg-delivery] retry deferred after {type(exc).__name__}", flush=True)
            try:
                process_pending_order_syncs()
            except Exception as exc:
                print(f"[tg-sync] retry deferred after {type(exc).__name__}", flush=True)
            url = f"{TELEGRAM_API_BASE}/bot{token}/getUpdates"
            response = requests.get(
                url,
                params={"offset": offset, "timeout": 25, "allowed_updates": '["message","callback_query"]'},
                timeout=30,
            )
            if response.ok:
                payload = response.json()
                offset, processed_all = _process_polled_updates(payload.get("result", []), offset)
                if processed_all:
                    backoff = 1
                else:
                    backoff = min(backoff * 2, 60)
                    _time.sleep(backoff)
            else:
                backoff = min(backoff * 2, 60)
                _time.sleep(backoff)
        except Exception as exc:
            print(f"[tg-poll] loop deferred after {type(exc).__name__}", flush=True)
            backoff = min(backoff * 2, 60)
            _time.sleep(backoff)


def start_polling_in_background() -> None:
    """Start long-poll in a daemon thread (no-op if no token or already running)."""
    global _POLLING_THREAD
    if os.environ.get("TELEGRAM_POLLING_MODE", "background").strip().lower() in {"external", "disabled"}:
        return
    if _POLLING_THREAD is not None:
        return
    _start_calendar_sync()
    if not _bot_token():
        return
    import threading
    t = threading.Thread(target=_poll_loop, name="tg-poll", daemon=True)
    t.start()
    _POLLING_THREAD = t


def run_polling_forever() -> None:
    """Run Telegram polling in one blocking process."""
    global _POLLING_STOP
    init_admin_notifications_store()
    # The Telegram worker is the one long-running background process in
    # production, so it also hosts the Google Calendar sync thread.
    _start_calendar_sync()
    _POLLING_STOP = False
    _poll_loop()


def stop_polling() -> None:
    global _POLLING_STOP
    _POLLING_STOP = True


if __name__ == "__main__":
    run_polling_forever()
