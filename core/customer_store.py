from __future__ import annotations

import logging
import os
import sqlite3
from collections import OrderedDict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from .catalog_store import (
    DEFAULT_EXTRA_CHARACTER_PRICE,
    DEFAULT_INCLUDED_CHARACTERS_COUNT,
    DEFAULT_SHOW_PROGRAM_DURATION_MINUTES,
    ENTITY_TYPE_CHARACTER,
    ENTITY_TYPE_SHOW_PROGRAM,
    FIXED_CAST_PROGRAM_DETAILS,
    FIXED_CAST_SHOW_PROGRAM_SLUGS,
    build_character_search_index,
    get_character_by_slug,
    get_default_show_program_duration_minutes,
    get_show_program_character_slug_map,
    list_categories,
    list_characters,
    list_characters_for_public,
)
from .config import DATA_ROOT
from .tashkent_geo import is_inside_tashkent

DB_ROOT = DATA_ROOT / "admin"
DB_PATH = DB_ROOT / "site_admin.sqlite3"
CUSTOMER_SESSION_KEY = "customer_user_id"
DEFAULT_AUTH_CHANNEL = "telegram"
SUPPORTED_AUTH_CHANNELS = ("telegram",)
SUPPORTED_PAYMENT_METHODS = ("cash", "bank")
SUPPORTED_CARD_PROVIDERS: tuple[str, ...] = ()
PAYMENT_METHOD_LABELS = {
    "cash": "Наличными диджею после праздника",
    "bank": "Переводом на карту диджею после праздника",
}
PAYMENT_METHOD_HINTS = {
    "cash": "Оплата наличными производится диджею после выполнения заказа.",
    "bank": "Оплата переводом производится на карту диджею после выполнения заказа.",
}
CARD_PROVIDER_LABELS: dict[str, str] = {}
LIFECYCLE_STATUS_LABELS = {
    "new": "Новый",
    "contacted": "Связались",
    "confirmed": "Подтвержден",
    "cancelled": "Отменен",
    "done": "Завершен",
}
ORDER_CONFIRMATION_LABELS = {
    "unconfirmed": "Не подтверждён",
    "confirmed": "Подтверждён",
}
ORDER_STATUS_LABELS = {
    **ORDER_CONFIRMATION_LABELS,
    "cancelled": "Отменён",
}
ORDER_CONFIRMATION_STATES = tuple(ORDER_CONFIRMATION_LABELS)
_PARTY_ORDER_SCHEMA_LOCK = Lock()
_PARTY_ORDER_SCHEMA_READY_PATH: Path | None = None
AVAILABILITY_BLOCKING_STATUSES = ("new", "contacted", "confirmed")
CHARACTER_BOOKING_BUFFER_MINUTES = 60
CHARACTER_BOOKING_BUFFER_BEFORE_MINUTES = 60
CHARACTER_BOOKING_BUFFER_AFTER_MINUTES = 60
BOOKING_LOCAL_TIMEZONE = timezone(timedelta(hours=5))
MIN_ORDER_LEAD_TIME_MINUTES = 1440
THEMATIC_PROGRAM_SLUGS = {
    "cryo-show",
    "bubble-show",
    "aqua-face-paint",
    *FIXED_CAST_SHOW_PROGRAM_SLUGS,
}
STANDARD_PROGRAM_REFERENCE_PRICE = 950_000
ZOOTOPIA_CHARACTER_SLUG = "zootopia"
NEPTUNE_CHARACTER_SLUG = "neptune-mermaids"
PROGRAM_SORT_ORDER = {
    "ribbon-show": 10,
    "cryo-show": 20,
    "streamer-show": 30,
    "balloon-show": 40,
    "jesters": 50,
    "neon-jesters": 60,
}
DEMO_AVAILABILITY_ENV = "SURPRIZ_DEMO_AVAILABILITY"
LOGGER = logging.getLogger(__name__)


def is_demo_availability_enabled() -> bool:
    """Expose visual sample slots only in explicitly enabled non-production runtimes."""
    enabled = os.environ.get(DEMO_AVAILABILITY_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    environment = os.environ.get("SURPRIZ_ENV", "development").strip().lower()
    return enabled and environment != "production"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def booking_local_now() -> datetime:
    return datetime.now(BOOKING_LOCAL_TIMEZONE).replace(tzinfo=None)


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


def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _reconcile_confirmation_lifecycle(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE party_orders
        SET confirmation_state = 'confirmed',
            confirmed_at = COALESCE(confirmed_at, NULLIF(updated_at, ''), NULLIF(created_at, ''))
        WHERE status = 'done'
          AND confirmation_state != 'confirmed'
        """
    )
    connection.execute(
        """
        UPDATE party_orders
        SET confirmation_state = 'unconfirmed',
            confirmed_at = NULL
        WHERE status = 'cancelled'
          AND confirmation_state != 'unconfirmed'
        """
    )
    connection.execute(
        """
        UPDATE party_orders
        SET status = 'confirmed'
        WHERE confirmation_state = 'confirmed'
          AND status IN ('new', 'contacted')
        """
    )
    connection.execute(
        """
        UPDATE party_orders
        SET status = 'new'
        WHERE confirmation_state = 'unconfirmed'
          AND status = 'confirmed'
        """
    )


def _queue_confirmation_sync(
    connection: sqlite3.Connection,
    order_id: int,
    now: str,
) -> None:
    connection.execute(
        """
        INSERT INTO admin_telegram_sync_queue(
            order_id, attempts, last_error, next_attempt_at, updated_at
        ) VALUES (?, 0, '', ?, ?)
        ON CONFLICT(order_id) DO UPDATE SET
            attempts = 0,
            last_error = '',
            next_attempt_at = excluded.next_attempt_at,
            updated_at = excluded.updated_at
        """,
        (int(order_id), now, now),
    )


def _ensure_party_order_columns() -> None:
    global _PARTY_ORDER_SCHEMA_READY_PATH
    schema_path = DB_PATH.resolve()
    if _PARTY_ORDER_SCHEMA_READY_PATH == schema_path:
        return
    with _PARTY_ORDER_SCHEMA_LOCK:
        if _PARTY_ORDER_SCHEMA_READY_PATH == schema_path:
            return
        with _get_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            statements: list[str] = []
            confirmation_state_added = False
            if not _has_column(connection, "party_orders", "program_price_snapshot"):
                statements.append("ALTER TABLE party_orders ADD COLUMN program_price_snapshot INTEGER NOT NULL DEFAULT 0")
            if not _has_column(connection, "party_orders", "total_price_snapshot"):
                statements.append("ALTER TABLE party_orders ADD COLUMN total_price_snapshot INTEGER NOT NULL DEFAULT 0")
            if not _has_column(connection, "party_orders", "duration_minutes"):
                statements.append("ALTER TABLE party_orders ADD COLUMN duration_minutes INTEGER NOT NULL DEFAULT 60")
            if not _has_column(connection, "party_orders", "location_label"):
                statements.append("ALTER TABLE party_orders ADD COLUMN location_label TEXT NOT NULL DEFAULT ''")
            if not _has_column(connection, "party_orders", "location_lat"):
                statements.append("ALTER TABLE party_orders ADD COLUMN location_lat REAL")
            if not _has_column(connection, "party_orders", "location_lng"):
                statements.append("ALTER TABLE party_orders ADD COLUMN location_lng REAL")
            if not _has_column(connection, "party_orders", "payment_provider"):
                statements.append("ALTER TABLE party_orders ADD COLUMN payment_provider TEXT NOT NULL DEFAULT ''")
            if not _has_column(connection, "party_orders", "confirmation_state"):
                statements.append(
                    "ALTER TABLE party_orders ADD COLUMN confirmation_state TEXT NOT NULL DEFAULT 'unconfirmed'"
                )
                confirmation_state_added = True
            if not _has_column(connection, "party_orders", "confirmation_changed_at"):
                statements.append("ALTER TABLE party_orders ADD COLUMN confirmation_changed_at TEXT")
            if not _has_column(connection, "party_orders", "confirmation_source"):
                statements.append("ALTER TABLE party_orders ADD COLUMN confirmation_source TEXT NOT NULL DEFAULT ''")
            if not _has_column(connection, "party_orders", "confirmation_actor"):
                statements.append("ALTER TABLE party_orders ADD COLUMN confirmation_actor TEXT NOT NULL DEFAULT ''")
            if not _has_column(connection, "party_orders", "confirmed_at"):
                statements.append("ALTER TABLE party_orders ADD COLUMN confirmed_at TEXT")

            for statement in statements:
                connection.execute(statement)

            if confirmation_state_added:
                connection.execute(
                    """
                    UPDATE party_orders
                    SET confirmation_state = CASE
                            WHEN status IN ('confirmed', 'done') THEN 'confirmed'
                            ELSE 'unconfirmed'
                        END,
                        confirmation_changed_at = COALESCE(NULLIF(updated_at, ''), NULLIF(created_at, '')),
                        confirmation_source = 'legacy-migration',
                        confirmation_actor = 'system',
                        confirmed_at = CASE
                            WHEN status IN ('confirmed', 'done')
                                THEN COALESCE(NULLIF(updated_at, ''), NULLIF(created_at, ''))
                            ELSE NULL
                        END
                    """
                )
            else:
                connection.execute(
                    """
                    UPDATE party_orders
                    SET confirmation_state = 'unconfirmed'
                    WHERE confirmation_state IS NULL
                       OR confirmation_state NOT IN ('unconfirmed', 'confirmed')
                    """
                )

            _reconcile_confirmation_lifecycle(connection)

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_party_orders_confirmation_state
                ON party_orders(confirmation_state, created_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS party_order_confirmation_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    previous_state TEXT NOT NULL,
                    confirmation_state TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    actor TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(order_id) REFERENCES party_orders(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_party_order_confirmation_events_order
                ON party_order_confirmation_events(order_id, created_at DESC, id DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS party_order_addons (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    addon_id INTEGER,
                    slug TEXT NOT NULL,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL DEFAULT 0,
                    duration_minutes INTEGER NOT NULL DEFAULT 0,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE(order_id, slug),
                    FOREIGN KEY(order_id) REFERENCES party_orders(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_party_order_addons_order
                ON party_order_addons(order_id, sort_order, id)
                """
            )
            connection.commit()
        _PARTY_ORDER_SCHEMA_READY_PATH = schema_path


def reconcile_order_confirmation_lifecycle_states() -> None:
    """Repair legacy/new state drift during a controlled cutover or rollback."""
    _ensure_party_order_columns()
    with _get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        _reconcile_confirmation_lifecycle(connection)
        now = utcnow_iso()
        order_ids = connection.execute("SELECT id FROM party_orders").fetchall()
        for row in order_ids:
            _queue_confirmation_sync(connection, int(row["id"]), now)
        connection.commit()


def _ensure_customer_block_columns() -> None:
    with _get_connection() as connection:
        statements: list[str] = []
        if not _has_column(connection, "customer_accounts", "is_blocked"):
            statements.append("ALTER TABLE customer_accounts ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0")
        if not _has_column(connection, "customer_accounts", "blocked_until"):
            statements.append("ALTER TABLE customer_accounts ADD COLUMN blocked_until TEXT")
        if not _has_column(connection, "customer_accounts", "block_reason"):
            statements.append("ALTER TABLE customer_accounts ADD COLUMN block_reason TEXT NOT NULL DEFAULT ''")
        for statement in statements:
            connection.execute(statement)
        if statements:
            connection.commit()


def count_consecutive_cancellations(customer_id: int) -> int:
    """Count how many of the most recent orders are consecutively cancelled."""
    with _get_connection() as connection:
        rows = connection.execute(
            "SELECT status FROM party_orders WHERE customer_id = ? ORDER BY created_at DESC LIMIT 10",
            (int(customer_id),),
        ).fetchall()
    count = 0
    for row in rows:
        if row["status"] == "cancelled":
            count += 1
        else:
            break
    return count


def apply_cancellation_block_if_needed(customer_id: int) -> bool:
    """Block customer for 72 h if they have 5+ consecutive cancelled orders. Returns True if block was applied."""
    _ensure_customer_block_columns()
    if get_customer_block_status(customer_id):
        return False
    if count_consecutive_cancellations(customer_id) < 5:
        return False
    blocked_until = (utcnow() + timedelta(hours=72)).isoformat()
    block_reason = (
        "Ваш аккаунт временно ограничен на 3 дня: 5 заказов подряд были отменены. "
        "Создание новых заказов недоступно до истечения блокировки. "
        "Если это ошибка — свяжитесь с нами: +998 (99) 892-65-65."
    )
    with _get_connection() as connection:
        connection.execute(
            "UPDATE customer_accounts SET is_blocked = 1, blocked_until = ?, block_reason = ?, updated_at = ? WHERE id = ?",
            (blocked_until, block_reason, utcnow_iso(), int(customer_id)),
        )
        connection.commit()
    return True


def get_customer_block_status(customer_id: int) -> dict[str, Any] | None:
    """Return block info dict if customer is currently blocked, None otherwise. Auto-lifts expired blocks."""
    _ensure_customer_block_columns()
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT is_blocked, blocked_until, block_reason FROM customer_accounts WHERE id = ? LIMIT 1",
            (int(customer_id),),
        ).fetchone()
        if not row or not row["is_blocked"]:
            return None
        blocked_until_raw = row["blocked_until"] or ""
        if blocked_until_raw:
            try:
                blocked_until_dt = datetime.fromisoformat(blocked_until_raw)
                if blocked_until_dt.tzinfo is None:
                    blocked_until_dt = blocked_until_dt.replace(tzinfo=timezone.utc)
                if utcnow() >= blocked_until_dt:
                    # Block expired — auto-lift
                    connection.execute(
                        "UPDATE customer_accounts SET is_blocked = 0, blocked_until = NULL, block_reason = '', updated_at = ? WHERE id = ?",
                        (utcnow_iso(), int(customer_id)),
                    )
                    connection.commit()
                    return None
            except ValueError:
                pass
        return {
            "block_reason": row["block_reason"],
            "blocked_until": blocked_until_raw,
        }


def format_money(value: int | None) -> str:
    amount = int(value or 0)
    return f"{amount:,}".replace(",", " ") + " сум"


def format_date_ru(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
        return parsed.strftime("%d.%m.%Y")
    except ValueError:
        return raw


def format_datetime_ru(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local_dt = parsed.astimezone(BOOKING_LOCAL_TIMEZONE)
    return local_dt.strftime("%d.%m.%Y %H:%M")


def build_map_location_url(latitude: float | None, longitude: float | None) -> str:
    if latitude is None or longitude is None:
        return ""
    return f"https://yandex.uz/maps/?ll={longitude:.6f}%2C{latitude:.6f}&z=17&pt={longitude:.6f},{latitude:.6f},pm2rdm"


def get_program_duration_minutes(program_slug: str | None) -> int:
    if not program_slug:
        return DEFAULT_SHOW_PROGRAM_DURATION_MINUTES
    program = get_character_by_slug(program_slug, include_hidden=True)
    if not program or program.get("entity_type") != ENTITY_TYPE_SHOW_PROGRAM:
        return DEFAULT_SHOW_PROGRAM_DURATION_MINUTES
    duration = int(program.get("default_duration_minutes") or 0)
    return duration if duration > 0 else get_default_show_program_duration_minutes(program.get("slug"))


def init_customer_store() -> None:
    with _get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS customer_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone_normalized TEXT NOT NULL UNIQUE,
                phone_display TEXT NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                preferred_auth_channel TEXT NOT NULL DEFAULT 'telegram',
                phone_verified_at TEXT,
                is_blocked INTEGER NOT NULL DEFAULT 0,
                blocked_until TEXT,
                block_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS party_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                public_id TEXT UNIQUE,
                customer_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                confirmation_state TEXT NOT NULL DEFAULT 'unconfirmed',
                confirmation_changed_at TEXT,
                confirmation_source TEXT NOT NULL DEFAULT '',
                confirmation_actor TEXT NOT NULL DEFAULT '',
                confirmed_at TEXT,
                program_slug TEXT NOT NULL DEFAULT '',
                program_name_snapshot TEXT NOT NULL DEFAULT '',
                program_price_snapshot INTEGER NOT NULL DEFAULT 0,
                total_price_snapshot INTEGER NOT NULL DEFAULT 0,
                celebration_date TEXT NOT NULL,
                time_from TEXT NOT NULL,
                time_to TEXT NOT NULL,
                duration_minutes INTEGER NOT NULL DEFAULT 60,
                celebrant_name TEXT NOT NULL DEFAULT '',
                celebrant_age INTEGER,
                children_count INTEGER,
                address_text TEXT NOT NULL,
                location_label TEXT NOT NULL DEFAULT '',
                location_lat REAL,
                location_lng REAL,
                yandex_map_url TEXT NOT NULL DEFAULT '',
                payment_method TEXT NOT NULL,
                payment_provider TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(customer_id) REFERENCES customer_accounts(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_party_orders_customer ON party_orders(customer_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_party_orders_date ON party_orders(celebration_date, time_from);
            CREATE INDEX IF NOT EXISTS idx_party_orders_status ON party_orders(status, created_at DESC);

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

            CREATE TABLE IF NOT EXISTS admin_telegram_sync_queue (
                order_id INTEGER PRIMARY KEY,
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                next_attempt_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_admin_tg_sync_due
            ON admin_telegram_sync_queue(next_attempt_at, order_id);

            CREATE TABLE IF NOT EXISTS party_order_characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                character_id INTEGER,
                slug TEXT NOT NULL,
                name_snapshot TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(order_id) REFERENCES party_orders(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_party_order_characters_order
            ON party_order_characters(order_id, sort_order, id);

            CREATE TABLE IF NOT EXISTS party_order_addons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL,
                addon_id INTEGER,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                price INTEGER NOT NULL DEFAULT 0,
                duration_minutes INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                UNIQUE(order_id, slug),
                FOREIGN KEY(order_id) REFERENCES party_orders(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_party_order_addons_order
            ON party_order_addons(order_id, sort_order, id);
            """
        )
        connection.commit()
    _ensure_customer_block_columns()
    _ensure_party_order_columns()


def normalize_phone_to_e164(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("998") and len(digits) == 12:
        return f"+{digits}"
    if len(digits) == 9:
        return f"+998{digits}"
    if digits.startswith("0") and len(digits) == 10:
        return f"+998{digits[1:]}"
    return ""


def normalize_phone(value: str) -> str:
    e164 = normalize_phone_to_e164(value)
    return e164[1:] if e164.startswith("+") else ""


def format_phone(phone_normalized: str) -> str:
    digits = normalize_phone(phone_normalized)
    if len(digits) != 12:
        return phone_normalized.strip()
    return f"+{digits[:3]} ({digits[3:5]}) {digits[5:8]}-{digits[8:10]}-{digits[10:12]}"


def _customer_row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "id": row["id"],
        "phone_normalized": row["phone_normalized"],
        "phone_display": row["phone_display"],
        "full_name": row["full_name"],
        "preferred_auth_channel": row["preferred_auth_channel"],
        "phone_verified_at": row["phone_verified_at"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def get_customer_by_id(customer_id: int) -> dict[str, Any] | None:
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM customer_accounts WHERE id = ? LIMIT 1",
            (customer_id,),
        ).fetchone()
    return _customer_row_to_dict(row)


def get_customer_by_phone(phone: str) -> dict[str, Any] | None:
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM customer_accounts WHERE phone_normalized = ? LIMIT 1",
            (normalized,),
        ).fetchone()
    return _customer_row_to_dict(row)


def validate_customer_auth_target(phone: str, purpose: str) -> dict[str, Any]:
    normalized_phone = normalize_phone(phone)
    if not normalized_phone:
        return {"success": False, "message": "Укажите номер в формате Узбекистана, например +998 (99) 123-45-67."}

    purpose = purpose.strip().lower()
    if purpose not in {"register", "login"}:
        return {"success": False, "message": "Неизвестный сценарий авторизации."}

    customer = get_customer_by_phone(normalized_phone)
    if purpose == "register" and customer:
        return {
            "success": False,
            "error_code": "account_exists",
            "message": "Этот номер уже зарегистрирован. Используйте вход по коду.",
        }
    if purpose == "login" and not customer:
        return {
            "success": False,
            "error_code": "account_not_found",
            "message": "Аккаунт с этим номером пока не найден. Сначала зарегистрируйтесь.",
        }

    return {
        "success": True,
        "phone_normalized": normalized_phone,
        "phone_e164": normalize_phone_to_e164(normalized_phone),
        "phone_display": format_phone(normalized_phone),
    }


def ensure_guest_customer(phone: str, full_name: str) -> dict[str, Any]:
    """Аккаунт для заказа без регистрации: находит по номеру или заводит новый
    с phone_verified_at = NULL.

    Телефон — это личность клиента, поэтому заказ с уже существующим номером
    цепляется к тому же аккаунту. Сессию покупателя вызывающий код при этом НЕ
    выдаёт: иначе любой, кто введёт чужой номер, получил бы чужую историю заказов.
    """
    normalized_phone = normalize_phone(phone)
    if not normalized_phone:
        return {"success": False, "message": "Укажите номер телефона в формате +998 XX XXX-XX-XX."}
    name = " ".join(str(full_name or "").split())[:80]
    if len(name) < 2:
        return {"success": False, "message": "Укажите имя, на которое оформляем заказ."}

    now = utcnow_iso()
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM customer_accounts WHERE phone_normalized = ? LIMIT 1",
            (normalized_phone,),
        ).fetchone()
        if row is not None:
            customer = _customer_row_to_dict(row)
            return {"success": True, "customer": customer, "created": False}

        cursor = connection.execute(
            """
            INSERT INTO customer_accounts(
                phone_normalized, phone_display, full_name, preferred_auth_channel,
                phone_verified_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                normalized_phone,
                format_phone(normalized_phone),
                name,
                DEFAULT_AUTH_CHANNEL,
                now,
                now,
            ),
        )
        connection.commit()
        created = connection.execute(
            "SELECT * FROM customer_accounts WHERE id = ? LIMIT 1",
            (int(cursor.lastrowid),),
        ).fetchone()
    return {"success": True, "customer": _customer_row_to_dict(created), "created": True}


def complete_customer_phone_auth(phone: str, purpose: str, full_name: str = "", channel: str = DEFAULT_AUTH_CHANNEL) -> dict[str, Any]:
    target = validate_customer_auth_target(phone, purpose)
    if not target["success"]:
        return target

    normalized_phone = target["phone_normalized"]
    purpose = purpose.strip().lower()
    normalized_channel = channel.strip().lower() if channel else DEFAULT_AUTH_CHANNEL
    if normalized_channel not in SUPPORTED_AUTH_CHANNELS:
        normalized_channel = DEFAULT_AUTH_CHANNEL

    with _get_connection() as connection:
        account_row = connection.execute(
            "SELECT * FROM customer_accounts WHERE phone_normalized = ? LIMIT 1",
            (normalized_phone,),
        ).fetchone()

        if account_row is None:
            if purpose == "login":
                return {"success": False, "message": "Аккаунт с этим номером не найден."}
            cursor = connection.execute(
                """
                INSERT INTO customer_accounts(
                    phone_normalized, phone_display, full_name, preferred_auth_channel,
                    phone_verified_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_phone,
                    format_phone(normalized_phone),
                    full_name.strip(),
                    normalized_channel,
                    utcnow_iso(),
                    utcnow_iso(),
                    utcnow_iso(),
                ),
            )
            account_id = int(cursor.lastrowid)
        else:
            if purpose == "register":
                return {"success": False, "message": "Этот номер уже зарегистрирован. Используйте вход по коду."}
            account_id = int(account_row["id"])
            updated_name = full_name.strip() or account_row["full_name"]
            connection.execute(
                """
                UPDATE customer_accounts
                SET full_name = ?, preferred_auth_channel = ?, phone_display = ?, phone_verified_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    updated_name,
                    normalized_channel,
                    format_phone(normalized_phone),
                    utcnow_iso(),
                    utcnow_iso(),
                    account_id,
                ),
            )

        connection.commit()

    customer = get_customer_by_id(account_id)
    return {"success": True, "message": "Номер подтверждён.", "customer": customer}


def build_time_slots(start_hour: int = 9, end_hour: int = 22, step_minutes: int = 30) -> list[dict[str, str]]:
    slots: list[dict[str, str]] = []
    current = datetime.combine(date.today(), time(hour=start_hour))
    finish = datetime.combine(date.today(), time(hour=end_hour))
    while current <= finish:
        value = current.strftime("%H:%M")
        slots.append({"value": value, "label": value})
        current += timedelta(minutes=step_minutes)
    return slots


#: Bookings stop before this date; the builder calendar offers nothing from here
#: on. Move the date to reopen the calendar.
BOOKING_CLOSED_FROM = date(2026, 12, 15)


def build_available_dates(days_ahead: int = 120) -> list[dict[str, str]]:
    today = date.today()
    return [
        {
            "value": day.isoformat(),
            "label": day.strftime("%d.%m.%Y"),
        }
        for day in (today + timedelta(days=offset) for offset in range(days_ahead))
        if day < BOOKING_CLOSED_FROM
    ]


def get_busy_dates_summary(days_ahead: int = 120) -> dict[str, Any]:
    """Return per-date booking counts + booked intervals for the next N days.
    Used by builder calendar to show badges and busy-time hints.

    Shape:
    {
      "by_date": {
        "2026-06-01": {
          "count": 2,
          "bookings": [
            {"public_id": "SRP-00001", "time_from": "14:00", "time_to": "16:00",
             "program_slug": "balloon-show", "program_name": "Шаровое шоу",
             "characters": ["Спайдермен"]},
            ...
          ]
        }
      }
    }
    """
    today = date.today().isoformat()
    horizon = (date.today() + timedelta(days=int(days_ahead))).isoformat()
    placeholders = ", ".join("?" for _ in AVAILABILITY_BLOCKING_STATUSES)
    with _get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT o.id, o.public_id, o.celebration_date, o.time_from, o.time_to, o.status,
                   o.program_slug, o.program_name_snapshot
            FROM party_orders o
            WHERE o.celebration_date >= ? AND o.celebration_date <= ?
              AND o.status IN ({placeholders})
            ORDER BY o.celebration_date ASC, o.time_from ASC
            """,
            (today, horizon, *AVAILABILITY_BLOCKING_STATUSES),
        ).fetchall()
        order_ids = [int(r["id"]) for r in rows]
        chars_by_order: dict[int, list[dict[str, str]]] = {oid: [] for oid in order_ids}
        if order_ids:
            ph = ", ".join("?" for _ in order_ids)
            char_rows = connection.execute(
                f"""
                SELECT order_id, name_snapshot, slug
                FROM party_order_characters
                WHERE order_id IN ({ph})
                ORDER BY name_snapshot
                """,
                tuple(order_ids),
            ).fetchall()
            for cr in char_rows:
                chars_by_order.setdefault(int(cr["order_id"]), []).append({
                    "slug": str(cr["slug"] or ""),
                    "name": str(cr["name_snapshot"] or cr["slug"] or "—"),
                })

    by_date: dict[str, dict[str, Any]] = {}
    for r in rows:
        d = str(r["celebration_date"])
        entry = by_date.setdefault(d, {"count": 0, "bookings": []})
        entry["count"] += 1
        characters = chars_by_order.get(int(r["id"]), [])
        entry["bookings"].append({
            "public_id": str(r["public_id"] or ""),
            "time_from": str(r["time_from"] or ""),
            "time_to": str(r["time_to"] or ""),
            "program_slug": str(r["program_slug"] or ""),
            "program_name": str(r["program_name_snapshot"] or r["program_slug"] or ""),
            "character_slugs": [c["slug"] for c in characters if c["slug"]],
            "characters": [c["name"] for c in characters],
        })
    return {"by_date": by_date}


def _demo_busy_dates_summary(
    *,
    character_slugs: set[str],
    program_slug: str,
    days_ahead: int,
    force: bool = False,
) -> dict[str, Any]:
    """Create deterministic preview-only bookings for the builder calendar.

    They never touch ``party_orders`` and are deliberately excluded from all
    server-side availability checks used when a real order is created.
    """
    if not (force or is_demo_availability_enabled()) or (not character_slugs and not program_slug):
        return {"by_date": {}}

    horizon = max(0, int(days_ahead))
    today = booking_local_now().date()
    offsets = (3, 9)
    selected_characters = sorted(character_slugs)
    character_names: list[str] = []
    for slug in selected_characters:
        character = get_character_by_slug(slug) or {}
        character_names.append(str(character.get("name") or slug))

    by_date: dict[str, dict[str, Any]] = {}
    for index, offset in enumerate(offsets):
        if offset > horizon:
            continue
        iso = (today + timedelta(days=offset)).isoformat()
        time_from, time_to = (("14:00", "15:00") if index == 0 else ("18:00", "19:00"))
        booking = {
            "public_id": "",
            "time_from": time_from,
            "time_to": time_to,
            "program_slug": program_slug,
            "program_name": "Выбранная программа" if program_slug else "",
            "character_slugs": selected_characters,
            "characters": character_names,
            "is_demo": True,
        }
        by_date[iso] = {"count": 1, "bookings": [booking]}
    return {"by_date": by_date}


def _merge_busy_date_summaries(*summaries: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for summary in summaries:
        for iso, entry in (summary.get("by_date") or {}).items():
            target = merged.setdefault(str(iso), {"count": 0, "bookings": []})
            bookings = list(entry.get("bookings") or [])
            target["bookings"].extend(bookings)
            target["count"] += int(entry.get("count") or len(bookings))
    return {"by_date": merged}


def _merge_minute_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
            continue
        merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def _capacity_blocked_intervals(
    intervals: list[tuple[int, int]],
    capacity: int,
) -> list[tuple[int, int]]:
    events: dict[int, int] = {}
    for start, end in intervals:
        if end <= start:
            continue
        events[start] = events.get(start, 0) + 1
        events[end] = events.get(end, 0) - 1

    blocked: list[tuple[int, int]] = []
    active = 0
    previous: int | None = None
    for minute in sorted(events):
        if previous is not None and minute > previous and active >= max(1, capacity):
            blocked.append((previous, minute))
        active += events[minute]
        previous = minute
    return _merge_minute_intervals(blocked)


def _peak_interval_usage(
    intervals: list[tuple[int, int]],
    *,
    window_start: int,
    window_end: int,
) -> int:
    events: dict[int, int] = {}
    for start, end in intervals:
        clipped_start = max(start, window_start)
        clipped_end = min(end, window_end)
        if clipped_end <= clipped_start:
            continue
        events[clipped_start] = events.get(clipped_start, 0) + 1
        events[clipped_end] = events.get(clipped_end, 0) - 1

    active = 0
    peak = 0
    for minute in sorted(events):
        active += events[minute]
        peak = max(peak, active)
    return peak


def _free_window_label(
    free_windows: list[tuple[int, int]],
    *,
    day_start: int,
    day_end: int,
) -> str:
    if not free_windows:
        return "Нет свободного времени"
    if free_windows == [(day_start, day_end)]:
        return "Свободно весь день"

    parts: list[str] = []
    for start, end in free_windows:
        start_label = _minutes_to_time(start)
        end_label = _minutes_to_time(end)
        if start == day_start:
            parts.append(f"до {end_label}")
        elif end == day_end:
            parts.append(f"после {start_label}")
        else:
            parts.append(f"с {start_label} до {end_label}")
    return "Свободно: " + ", ".join(parts)


def build_resource_availability_calendar(
    *,
    character_slugs: list[str] | tuple[str, ...],
    program_slug: str = "",
    days_ahead: int = 120,
    day_start_hour: int = 9,
    day_end_hour: int = 22,
    include_demo: bool = False,
) -> dict[str, Any]:
    """Return privacy-safe free windows for only the resources selected in the builder."""
    selected_characters = set(_normalize_character_slugs(list(character_slugs)))
    selected_program = str(program_slug or "").strip()
    if not selected_characters and not selected_program:
        return {"by_date": {}}

    day_start = max(0, min(24 * 60, int(day_start_hour) * 60))
    day_end = max(day_start, min(24 * 60, int(day_end_hour) * 60))
    character_capacity: dict[str, int] = {}
    for slug in selected_characters:
        character = get_character_by_slug(slug)
        character_capacity[slug] = max(1, 1 + int((character or {}).get("duplicate_count") or 0))

    source_summary = _merge_busy_date_summaries(
        get_busy_dates_summary(days_ahead),
        _demo_busy_dates_summary(
            character_slugs=selected_characters,
            program_slug=selected_program,
            days_ahead=days_ahead,
            force=include_demo,
        ),
    )
    result: dict[str, Any] = {}
    for iso, entry in (source_summary.get("by_date") or {}).items():
        resource_intervals: dict[str, list[tuple[int, int]]] = {}
        resource_capacities: dict[str, int] = {}
        relevant_bookings: list[dict[str, Any]] = []

        for booking in entry.get("bookings") or []:
            start = _time_to_minutes(str(booking.get("time_from") or ""))
            end = _time_to_minutes(str(booking.get("time_to") or ""))
            if start is None or end is None or end <= start:
                continue
            blocked_start = max(day_start, start - CHARACTER_BOOKING_BUFFER_BEFORE_MINUTES)
            blocked_end = min(day_end, end + CHARACTER_BOOKING_BUFFER_AFTER_MINUTES)
            if blocked_end <= blocked_start:
                continue

            matched = False
            # A public program is not an exclusive resource by itself. When
            # costumes are selected, only the overlapping costumes should
            # block a time window (e.g. two Standard orders can run in
            # parallel with different casts). Program-level blocking remains
            # useful only for formats that genuinely have no selectable cast.
            if (
                not selected_characters
                and selected_program
                and str(booking.get("program_slug") or "").strip() == selected_program
            ):
                key = f"program:{selected_program}"
                resource_intervals.setdefault(key, []).append((blocked_start, blocked_end))
                resource_capacities[key] = 1
                matched = True

            booked_characters = set(booking.get("character_slugs") or [])
            for slug in selected_characters & booked_characters:
                key = f"character:{slug}"
                resource_intervals.setdefault(key, []).append((blocked_start, blocked_end))
                resource_capacities[key] = character_capacity.get(slug, 1)
                matched = True

            if matched:
                relevant_bookings.append(
                    {
                        "time_from": str(booking.get("time_from") or ""),
                        "time_to": str(booking.get("time_to") or ""),
                        "blocked_from": _minutes_to_time(blocked_start),
                        "blocked_to": _minutes_to_time(blocked_end),
                        "program_slug": str(booking.get("program_slug") or ""),
                        "program_name": str(booking.get("program_name") or ""),
                        "character_slugs": list(booking.get("character_slugs") or []),
                        "characters": list(booking.get("characters") or []),
                        "is_demo": bool(booking.get("is_demo")),
                    }
                )

        blocked_intervals: list[tuple[int, int]] = []
        for key, intervals in resource_intervals.items():
            blocked_intervals.extend(
                _capacity_blocked_intervals(intervals, resource_capacities.get(key, 1))
            )
        blocked_intervals = _merge_minute_intervals(blocked_intervals)
        if not blocked_intervals:
            continue

        free_intervals: list[tuple[int, int]] = []
        cursor = day_start
        for start, end in blocked_intervals:
            if start > cursor:
                free_intervals.append((cursor, start))
            cursor = max(cursor, end)
        if cursor < day_end:
            free_intervals.append((cursor, day_end))

        result[iso] = {
            "count": len(blocked_intervals),
            "bookings": relevant_bookings,
            "is_demo": any(bool(item.get("is_demo")) for item in relevant_bookings),
            "blocked_windows": [
                {"from": _minutes_to_time(start), "to": _minutes_to_time(end)}
                for start, end in blocked_intervals
            ],
            "free_windows": [
                {"from": _minutes_to_time(start), "to": _minutes_to_time(end)}
                for start, end in free_intervals
            ],
            "free_label": _free_window_label(
                free_intervals,
                day_start=day_start,
                day_end=day_end,
            ),
        }
    return {"by_date": result}


def _format_program_age(age_from: Any, age_to: Any) -> str:
    start = _parse_positive_int(str(age_from)) if age_from not in {None, ""} else None
    end = _parse_positive_int(str(age_to)) if age_to not in {None, ""} else None
    start = start if start is not None and start > 0 else None
    end = end if end is not None and end > 0 else None
    if start is not None and end is not None:
        return f"{start}-{end} лет"
    if start is not None:
        return f"от {start} лет"
    if end is not None:
        return f"до {end} лет"
    return ""


def _attach_program_gifts(item: dict[str, Any], program_addons: list[dict[str, Any]]) -> None:
    choice_groups: dict[str, list[dict[str, Any]]] = {}
    gift_bundles: list[dict[str, Any]] = []
    paid_addons: list[dict[str, Any]] = []
    for addon in program_addons:
        addon["price_label"] = format_money(addon.get("price"))
        addon["duration_label"] = (
            f"{int(addon.get('duration_minutes') or 0)} мин"
            if int(addon.get("duration_minutes") or 0) > 0
            else ""
        )
        mode = str(addon.get("gift_mode") or "none").strip()
        if mode == "none" and addon.get("is_free_choice"):
            mode = "choice_one"
        if mode == "choice_one":
            group_key = str(addon.get("gift_group") or "default").strip() or "default"
            choice_groups.setdefault(group_key, []).append(addon)
            continue
        if mode == "bundle_all":
            gift_bundles.append(addon)
            continue
        if max(0, int(addon.get("price") or 0)) > 0:
            paid_addons.append(addon)
    item["free_choice_addons"] = [
        addon
        for addon in program_addons
        if addon.get("is_free_choice") or str(addon.get("gift_mode") or "") == "choice_one"
    ]
    item["gift_choice_groups"] = [
        {"key": key, "addons": addons} for key, addons in choice_groups.items()
    ]
    item["gift_bundles"] = gift_bundles
    item["has_gifts"] = bool(choice_groups or gift_bundles)
    item["paid_addons"] = paid_addons


def _attach_program_promotions(item: dict[str, Any]) -> None:
    try:
        from .promotion_store import list_program_promotions_for_public

        item["promotions"] = list_program_promotions_for_public(int(item.get("id") or 0))
    except Exception:
        item["promotions"] = []


def calculate_program_character_surcharge(program: dict[str, Any] | None, character_count: int) -> int:
    if not program:
        return 0
    included = max(0, int(program.get("included_characters_count") or 0))
    if character_count <= included:
        return 0
    extra_first = max(0, int(program.get("extra_character_price_3") or 0))
    extra_rest = max(0, int(program.get("extra_character_price_4_plus") or 0))
    surcharge = 0
    for index in range(included, character_count):
        surcharge += extra_first if index == included else extra_rest
    return surcharge


def calculate_ensemble_surcharge(character: dict[str, Any] | None, selected_members: list[str]) -> int:
    """Grouped-card members are priced by the selected show's character tariff."""
    del character, selected_members
    return 0


def calculate_fixed_character_surcharge(
    character: dict[str, Any] | None,
    selected_members: list[str],
) -> int:
    """Return character-specific event extras that must not scale with duration."""
    if not character:
        return 0
    slug = str(character.get("slug") or "").strip()
    base_price = max(0, int(character.get("base_price") or 0))
    if slug == ZOOTOPIA_CHARACTER_SLUG:
        return max(0, base_price - STANDARD_PROGRAM_REFERENCE_PRICE)
    if slug == NEPTUNE_CHARACTER_SLUG:
        picked = normalize_ensemble_selection(character, selected_members)
        if any(member.casefold().startswith("нептун") for member in picked):
            return base_price
    return 0


def selected_character_performers(
    character: dict[str, Any] | None,
    selected_members: list[str],
) -> list[str]:
    """Return the actual performers represented by a selected catalog card."""
    if not character:
        return []
    members = character.get("ensemble_members") or []
    if len(members) > 1:
        return normalize_ensemble_selection(character, selected_members)
    name = str(character.get("name") or "").strip()
    return [name] if name else []


def is_mascot_performer(name: str) -> bool:
    return "ростов" in str(name or "").casefold()


def validate_character_performer_rules(
    program: dict[str, Any] | None,
    selected_characters: list[dict[str, Any]],
    ensemble_selection: dict[str, list[str]],
) -> str:
    """Validate minimum cast and the speaking-host rule for closed-head costumes."""
    if not program:
        return ""
    program_slug = str(program.get("slug") or "")
    if program_slug in THEMATIC_PROGRAM_SLUGS:
        return ""

    performers = [
        performer
        for character in selected_characters
        for performer in selected_character_performers(
            character,
            ensemble_selection.get(str(character.get("slug") or ""), []),
        )
    ]
    required = max(0, int(program.get("included_characters_count") or 0))
    if len(performers) < required:
        performer_word = "персонажа" if required == 1 else "персонажей"
        return f"Для этой программы выберите минимум {required} {performer_word}."

    mascot_count = sum(1 for performer in performers if is_mascot_performer(performer))
    open_count = len(performers) - mascot_count
    if mascot_count and open_count < 2:
        return "К ростовому персонажу выберите минимум двух открытых говорящих ведущих."
    return ""


def scale_price_for_duration(
    amount: int,
    actual_duration_minutes: int,
    base_duration_minutes: int,
) -> int:
    source = max(0, int(amount or 0))
    actual = max(0, int(actual_duration_minutes or 0))
    base = max(0, int(base_duration_minutes or 0))
    if source <= 0 or base <= 0 or actual <= base:
        return source
    return (source * actual * 2 + base) // (base * 2)


def _scale_price_by_multiplier(amount: int, multiplier: float) -> int:
    source = max(0, int(amount or 0))
    factor = max(Decimal("1"), Decimal(str(multiplier or 1)))
    return int((Decimal(source) * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def count_program_character_slots(
    character: dict[str, Any] | None,
    selected_members: list[str],
) -> int:
    """Count every selected performer against the selected program's tariff."""
    if not character:
        return 0
    members = character.get("ensemble_members") or []
    if len(members) <= 1:
        return 1
    picked = len(normalize_ensemble_selection(character, selected_members))
    return picked


def calculate_order_character_surcharge(
    program: dict[str, Any] | None,
    selected_characters: list[dict[str, Any]],
    ensemble_selection: dict[str, list[str]],
    duration_multiplier: float = 1.0,
    *,
    actual_duration_minutes: int | None = None,
    base_duration_minutes: int | None = None,
) -> int:
    """Calculate duration-aware program pricing plus character-specific extras."""
    program_character_count = sum(
        count_program_character_slots(
            character,
            ensemble_selection.get(str(character.get("slug") or ""), []),
        )
        for character in selected_characters
    )
    generic_base = calculate_program_character_surcharge(program, program_character_count)
    if actual_duration_minutes is not None and base_duration_minutes is not None:
        generic_surcharge = scale_price_for_duration(
            generic_base,
            actual_duration_minutes,
            base_duration_minutes,
        )
    else:
        generic_surcharge = _scale_price_by_multiplier(generic_base, duration_multiplier)
    fixed_character_surcharge = sum(
        calculate_fixed_character_surcharge(
            character,
            ensemble_selection.get(str(character.get("slug") or ""), []),
        )
        for character in selected_characters
    )
    return generic_surcharge + fixed_character_surcharge


def normalize_ensemble_selection(character: dict[str, Any] | None, selected_members: list[str]) -> list[str]:
    """Keep only real member names, in the order declared by the character."""
    members = (character or {}).get("ensemble_members") or []
    if not members:
        return []
    wanted = {str(name or "").strip().casefold() for name in selected_members if str(name or "").strip()}
    return [member for member in members if member.casefold() in wanted]


def build_character_name_snapshot(character: dict[str, Any], selected_members: list[str]) -> str:
    """Persist the chosen performer roster for order views and Telegram notifications."""
    name = str(character.get("name") or "").strip()
    picked = normalize_ensemble_selection(character, selected_members)
    if not picked:
        return name
    selected_label = " + ".join(picked)
    fixed_surcharge = calculate_fixed_character_surcharge(character, picked)
    if fixed_surcharge > 0:
        if str(character.get("slug") or "") == ZOOTOPIA_CHARACTER_SLUG:
            return f"{selected_label} (игрушка в комплекте; +{format_money(fixed_surcharge)})"
        else:
            return f"{selected_label} (персональная доплата +{format_money(fixed_surcharge)})"
    return selected_label


def parse_ensemble_member_values(values: Any) -> dict[str, list[str]]:
    """Group form values shaped as "<character-slug>::<member name>" by character slug."""
    picks: dict[str, list[str]] = {}
    for raw in values or []:
        text = str(raw or "").strip()
        if "::" not in text:
            continue
        slug, _, member = text.partition("::")
        slug = slug.strip()
        member = member.strip()
        if not slug or not member:
            continue
        picks.setdefault(slug, []).append(member)
    return picks


def list_show_programs_for_public() -> list[dict[str, Any]]:
    from .addon_store import list_program_addons_for_public
    programs: list[dict[str, Any]] = []
    character_map = get_show_program_character_slug_map()
    for item in list_characters(status="active", entity_type=ENTITY_TYPE_SHOW_PROGRAM):
        item["is_show_program"] = True
        item["is_thematic"] = item["slug"] in THEMATIC_PROGRAM_SLUGS
        item["fixed_cast_members"] = list(
            item.get("program_cast") or FIXED_CAST_PROGRAM_DETAILS.get(str(item.get("slug") or ""), ())
        )
        item["price_label"] = format_money(item.get("base_price"))
        item["duration_label"] = f"{int(item.get('default_duration_minutes') or DEFAULT_SHOW_PROGRAM_DURATION_MINUTES)} мин"
        item["summary_text"] = (
            str(item.get("short_description") or item.get("description") or "Описание шоу-программы скоро появится.").strip()
            or "Описание шоу-программы скоро появится."
        )
        item["category_label"] = str(item.get("show_category") or "").strip()
        item["format_label"] = str(item.get("format_tags") or "").strip()
        item["age_label"] = _format_program_age(item.get("age_from"), item.get("age_to"))
        item["linked_character_slugs"] = character_map.get(str(item.get("slug") or ""), [])
        try:
            program_addons = list_program_addons_for_public(int(item.get("id") or 0))
        except Exception:
            program_addons = []
        _attach_program_gifts(item, program_addons)
        _attach_program_promotions(item)
        programs.append(item)
    return programs


def list_show_programs_grouped_for_public() -> list[dict[str, Any]]:
    """Returns show programs grouped by variant_group_slug.

    Items without a variant group become single-program groups. Items sharing
    a variant_group_slug are merged into one group with `variants` list.
    """
    flat = list_show_programs_for_public()
    groups: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for item in flat:
        group_slug = str(item.get("variant_group_slug") or "").strip()
        if not group_slug:
            single_key = f"single::{item['slug']}"
            groups[single_key] = {
                "slug": item["slug"],
                "group_slug": "",
                "name": item.get("name", ""),
                "is_group": False,
                "primary": item,
                "variants": [],
            }
            continue
        if group_slug not in groups:
            groups[group_slug] = {
                "slug": group_slug,
                "group_slug": group_slug,
                "name": item.get("variant_group_name") or item.get("name", ""),
                "is_group": True,
                "primary": item,
                "variants": [],
            }
        group = groups[group_slug]
        group["variants"].append({
            "slug": item["slug"],
            "label": item.get("variant_label") or item.get("name", ""),
            "name": item.get("name", ""),
            "short_description": str(item.get("short_description") or "").strip(),
            "description": str(item.get("description") or "").strip(),
            "summary_text": str(item.get("summary_text") or "").strip(),
            "included_items": str(item.get("included_items") or "").strip(),
            "show_category": str(item.get("show_category") or "").strip(),
            "format_tags": str(item.get("format_tags") or "").strip(),
            "age_label": str(item.get("age_label") or "").strip(),
            "price_label": item.get("price_label"),
            "duration_label": item.get("duration_label"),
            "linked_character_slugs": item.get("linked_character_slugs"),
            "free_choice_addons": item.get("free_choice_addons") or [],
            "gift_choice_groups": item.get("gift_choice_groups") or [],
            "gift_bundles": item.get("gift_bundles") or [],
            "has_gifts": bool(item.get("has_gifts")),
            "paid_addons": item.get("paid_addons") or [],
            "promotions": item.get("promotions") or [],
            "is_thematic": bool(item.get("is_thematic")),
            "fixed_cast_members": item.get("fixed_cast_members") or [],
            "duration": int(item.get("default_duration_minutes") or DEFAULT_SHOW_PROGRAM_DURATION_MINUTES),
            "price": int(item.get("base_price") or 0),
            "included_characters_count": int(item.get("included_characters_count") or DEFAULT_INCLUDED_CHARACTERS_COUNT),
            "extra_character_price_3": int(item.get("extra_character_price_3") or 0),
            "extra_character_price_4_plus": int(item.get("extra_character_price_4_plus") or 0),
        })
    # The static site only collapses a group once it holds two or more variants. A
    # lone survivor (the rest hidden) rendered here as a group card badged
    # "1 варианта", so match that rule and fall back to a plain programme.
    for group in groups.values():
        if group["is_group"] and len(group["variants"]) < 2:
            group["is_group"] = False
            group["slug"] = group["primary"]["slug"]
            group["name"] = group["primary"].get("name", "")
            group["variants"] = []
    return list(groups.values())


def list_character_groups_for_builder() -> list[dict[str, Any]]:
    groups: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    categories = [category for category in list_categories(include_hidden=False) if int(category.get("character_count") or 0) > 0]
    category_by_slug = {str(category["slug"]): category for category in categories}
    default_group_slug = "all"
    default_group_name = category_by_slug.get("all", {}).get("name") or "Все персонажи"

    for item in list_characters_for_public(entity_type=ENTITY_TYPE_CHARACTER):
        search_index = build_character_search_index(item)
        item["search_index"] = search_index["normalized"]
        item["search_compact_index"] = search_index["compact"]
        item["fixed_character_surcharge"] = calculate_fixed_character_surcharge(item, [])
        item["fixed_character_surcharge_label"] = format_money(
            item["fixed_character_surcharge"]
        )
        item["is_mascot_performer"] = is_mascot_performer(
            f"{item.get('name', '')} {item.get('search_terms', '')}"
        )
        item["has_duplicate"] = int(item.get("duplicate_count") or 0) > 0
        item["duplicate_label"] = (
            f"Есть дубликат" if int(item.get("duplicate_count") or 0) == 1
            else f"Есть {int(item.get('duplicate_count') or 0)} дубликата"
            if 1 < int(item.get("duplicate_count") or 0) < 5
            else f"Есть {int(item.get('duplicate_count') or 0)} дубликатов"
            if int(item.get("duplicate_count") or 0) >= 5
            else ""
        )
        category_slugs = [slug for slug in item.get("category_slugs", []) if slug in category_by_slug and slug != "all"]
        group_slug = category_slugs[0] if category_slugs else default_group_slug
        group_name = category_by_slug.get(group_slug, {}).get("name") or default_group_name
        groups.setdefault(group_slug, {"slug": group_slug, "name": group_name, "items": []})
        groups[group_slug]["items"].append(item)
    return list(groups.values())


def _parse_positive_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _parse_coordinate(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _time_to_minutes(value: str) -> int | None:
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except ValueError:
        return None
    return parsed.hour * 60 + parsed.minute


def _minutes_to_time(value: int) -> str:
    hours = max(0, min(23, value // 60))
    minutes = max(0, min(59, value % 60))
    return f"{hours:02d}:{minutes:02d}"


def _booking_start_datetime(celebration_date: str, time_from: str) -> datetime | None:
    try:
        parsed_date = datetime.strptime(celebration_date, "%Y-%m-%d").date()
        parsed_time = datetime.strptime(time_from, "%H:%M").time()
    except ValueError:
        return None
    return datetime.combine(parsed_date, parsed_time)


def check_booking_lead_time(
    *,
    celebration_date: str,
    time_from: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    starts_at = _booking_start_datetime(celebration_date, time_from)
    if starts_at is None:
        return {"allowed": False, "reason": "invalid_datetime", "message": "Укажите корректную дату и время праздника."}

    min_starts_at = (now or booking_local_now()).replace(second=0, microsecond=0) + timedelta(minutes=MIN_ORDER_LEAD_TIME_MINUTES)
    if starts_at < min_starts_at:
        return {
            "allowed": False,
            "reason": "lead_time",
            "message": "Бронирование доступно минимум за 24 часа до начала праздника.",
        }

    return {"allowed": True, "reason": "", "message": ""}


def _normalize_character_slugs(values: list[str] | tuple[str, ...] | None) -> list[str]:
    return list(dict.fromkeys(slug.strip() for slug in (values or []) if slug and slug.strip()))


def _character_capacity(character: dict[str, Any]) -> int:
    try:
        duplicate_count = int(character.get("duplicate_count") or 0)
    except (TypeError, ValueError):
        duplicate_count = 0
    return max(1, 1 + max(0, duplicate_count))


def _check_program_conflict(
    *,
    program_slug: str,
    celebration_date: str,
    start_minutes: int,
    end_minutes: int,
    exclude_order_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return conflicts where the same program_slug is already booked on that date,
    overlapping the requested interval (3h before / 1h after buffer).
    """
    if not program_slug:
        return []
    status_placeholders = ", ".join("?" for _ in AVAILABILITY_BLOCKING_STATUSES)
    params: list[Any] = [celebration_date, program_slug, *AVAILABILITY_BLOCKING_STATUSES]
    order_filter = ""
    if exclude_order_id is not None:
        order_filter = " AND o.id != ?"
        params.append(int(exclude_order_id))
    with _get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT o.time_from, o.time_to, o.program_name_snapshot, o.program_slug
            FROM party_orders o
            WHERE o.celebration_date = ?
              AND o.program_slug = ?
              AND o.status IN ({status_placeholders})
              {order_filter}
            ORDER BY o.time_from ASC
            """,
            tuple(params),
        ).fetchall()
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        busy_start = _time_to_minutes(row["time_from"])
        busy_end = _time_to_minutes(row["time_to"])
        if busy_start is None or busy_end is None or busy_end <= busy_start:
            continue
        blocked_start = busy_start - CHARACTER_BOOKING_BUFFER_BEFORE_MINUTES
        blocked_end = busy_end + CHARACTER_BOOKING_BUFFER_AFTER_MINUTES
        if start_minutes < blocked_end and end_minutes > blocked_start:
            conflicts.append(
                {
                    "slug": row["program_slug"],
                    "name": row["program_name_snapshot"] or row["program_slug"] or "Шоу-программа",
                    "kind": "program",
                    "capacity": 1,
                    "used": 1,
                    "duplicate_count": 0,
                    "orders": [
                        {
                            "time_from": row["time_from"],
                            "time_to": row["time_to"],
                            "blocked_from": _minutes_to_time(blocked_start),
                            "blocked_to": _minutes_to_time(blocked_end),
                        }
                    ],
                }
            )
    return conflicts


def _check_date_level_conflict(
    *,
    celebration_date: str,
    start_minutes: int,
    end_minutes: int,
    exclude_order_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return conflicts for the given date interval ignoring character selection.

    Any active booking on that date whose blocked window (3h before / 1h after)
    overlaps the requested interval counts as a conflict.
    """
    status_placeholders = ", ".join("?" for _ in AVAILABILITY_BLOCKING_STATUSES)
    params: list[Any] = [celebration_date, *AVAILABILITY_BLOCKING_STATUSES]
    order_filter = ""
    if exclude_order_id is not None:
        order_filter = " AND o.id != ?"
        params.append(int(exclude_order_id))
    with _get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT o.time_from, o.time_to
            FROM party_orders o
            WHERE o.celebration_date = ?
              AND o.status IN ({status_placeholders})
              {order_filter}
            ORDER BY o.time_from ASC
            """,
            tuple(params),
        ).fetchall()
    conflicts: list[dict[str, Any]] = []
    for row in rows:
        busy_start = _time_to_minutes(row["time_from"])
        busy_end = _time_to_minutes(row["time_to"])
        if busy_start is None or busy_end is None or busy_end <= busy_start:
            continue
        blocked_start = busy_start - CHARACTER_BOOKING_BUFFER_BEFORE_MINUTES
        blocked_end = busy_end + CHARACTER_BOOKING_BUFFER_AFTER_MINUTES
        if start_minutes < blocked_end and end_minutes > blocked_start:
            conflicts.append(
                {
                    "slug": "",
                    "name": "Бронь на эту дату",
                    "capacity": 0,
                    "used": 1,
                    "duplicate_count": 0,
                    "orders": [
                        {
                            "time_from": row["time_from"],
                            "time_to": row["time_to"],
                            "blocked_from": _minutes_to_time(blocked_start),
                            "blocked_to": _minutes_to_time(blocked_end),
                        }
                    ],
                }
            )
    return conflicts


def check_character_availability(
    *,
    character_slugs: list[str] | tuple[str, ...],
    celebration_date: str,
    time_from: str,
    time_to: str,
    program_slug: str = "",
    exclude_order_id: int | None = None,
) -> dict[str, Any]:
    selected_slugs = _normalize_character_slugs(list(character_slugs))
    try:
        datetime.strptime(celebration_date, "%Y-%m-%d").date()
    except ValueError:
        return {"success": False, "available": False, "message": "Выберите дату праздника.", "conflicts": []}

    start_minutes = _time_to_minutes(time_from)
    end_minutes = _time_to_minutes(time_to)
    if start_minutes is None or end_minutes is None or end_minutes <= start_minutes:
        return {"success": False, "available": False, "message": "Укажите корректное время праздника.", "conflicts": []}

    lead_time = check_booking_lead_time(celebration_date=celebration_date, time_from=time_from)
    if not lead_time["allowed"]:
        return {
            "success": True,
            "available": False,
            "message": lead_time["message"],
            "reason": lead_time["reason"],
            "conflicts": [],
        }

    if not selected_slugs:
        program_slug_clean = (program_slug or "").strip()
        if program_slug_clean:
            program_conflicts = _check_program_conflict(
                program_slug=program_slug_clean,
                celebration_date=celebration_date,
                start_minutes=start_minutes,
                end_minutes=end_minutes,
                exclude_order_id=exclude_order_id,
            )
            if program_conflicts:
                names = ", ".join(item["name"] for item in program_conflicts)
                return {
                    "success": True,
                    "available": False,
                    "message": f"Программа {names} уже забронирована на это время. Выберите другое время.",
                    "reason": "program_overlap",
                    "conflicts": program_conflicts,
                }
        return {"success": True, "available": True, "message": "", "conflicts": []}

    characters_by_slug: dict[str, dict[str, Any]] = {}
    missing_names: list[str] = []
    for slug in selected_slugs:
        character = get_character_by_slug(slug)
        if not character or character.get("entity_type") != ENTITY_TYPE_CHARACTER:
            missing_names.append(slug)
            continue
        characters_by_slug[slug] = character

    if missing_names:
        return {
            "success": False,
            "available": False,
            "message": "Один из выбранных персонажей больше недоступен.",
            "conflicts": [],
        }

    status_placeholders = ", ".join("?" for _ in AVAILABILITY_BLOCKING_STATUSES)
    params: list[Any] = [celebration_date, *AVAILABILITY_BLOCKING_STATUSES]
    order_filter = ""
    if exclude_order_id is not None:
        order_filter = " AND o.id != ?"
        params.append(int(exclude_order_id))

    with _get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT
                o.time_from,
                o.time_to,
                oc.slug,
                oc.name_snapshot
            FROM party_orders o
            INNER JOIN party_order_characters oc ON oc.order_id = o.id
            WHERE o.celebration_date = ?
              AND o.status IN ({status_placeholders})
              {order_filter}
            """,
            tuple(params),
        ).fetchall()

    selected_set = set(selected_slugs)
    intervals_by_slug: dict[str, list[tuple[int, int]]] = {
        slug: [] for slug in selected_slugs
    }
    details_by_slug: dict[str, list[dict[str, Any]]] = {slug: [] for slug in selected_slugs}

    for row in rows:
        slug = row["slug"]
        if slug not in selected_set:
            continue
        busy_start = _time_to_minutes(row["time_from"])
        busy_end = _time_to_minutes(row["time_to"])
        if busy_start is None or busy_end is None or busy_end <= busy_start:
            continue
        blocked_start = busy_start - CHARACTER_BOOKING_BUFFER_BEFORE_MINUTES
        blocked_end = busy_end + CHARACTER_BOOKING_BUFFER_AFTER_MINUTES
        if start_minutes < blocked_end and end_minutes > blocked_start:
            intervals_by_slug[slug].append((blocked_start, blocked_end))
            details_by_slug[slug].append(
                {
                    "time_from": row["time_from"],
                    "time_to": row["time_to"],
                    "blocked_from": _minutes_to_time(blocked_start),
                    "blocked_to": _minutes_to_time(blocked_end),
                }
            )

    conflicts: list[dict[str, Any]] = []
    for slug in selected_slugs:
        character = characters_by_slug[slug]
        capacity = _character_capacity(character)
        intervals = intervals_by_slug.get(slug, [])
        blocked_intervals = _capacity_blocked_intervals(intervals, capacity)
        has_conflict = any(
            start_minutes < blocked_end and end_minutes > blocked_start
            for blocked_start, blocked_end in blocked_intervals
        )
        if has_conflict:
            conflicts.append(
                {
                    "slug": slug,
                    "name": character["name"],
                    "capacity": capacity,
                    "used": _peak_interval_usage(
                        intervals,
                        window_start=start_minutes,
                        window_end=end_minutes,
                    ),
                    "duplicate_count": int(character.get("duplicate_count") or 0),
                    "orders": details_by_slug.get(slug, []),
                }
            )

    if conflicts:
        names = ", ".join(item["name"] for item in conflicts)
        return {
            "success": True,
            "available": False,
            "message": f"На это время уже заняты: {names}. Выберите другое время с запасом минимум 1 час.",
            "conflicts": conflicts,
        }

    return {
        "success": True,
        "available": True,
        "message": "Выбранные персонажи свободны на это время.",
        "conflicts": [],
    }


def build_character_time_slot_availability(
    *,
    character_slugs: list[str] | tuple[str, ...],
    celebration_date: str,
    duration_minutes: int,
    time_slots: list[dict[str, str]] | None = None,
    program_slug: str = "",
    exclude_order_id: int | None = None,
) -> dict[str, Any]:
    slots = time_slots or build_time_slots()
    selected_slugs = _normalize_character_slugs(list(character_slugs))
    try:
        duration = int(duration_minutes)
    except (TypeError, ValueError):
        duration = DEFAULT_SHOW_PROGRAM_DURATION_MINUTES
    duration = max(1, min(duration, 24 * 60))

    try:
        datetime.strptime(celebration_date, "%Y-%m-%d").date()
    except ValueError:
        return {"success": False, "time_slots": []}

    now = booking_local_now()
    result_slots: list[dict[str, Any]] = []
    for slot in slots:
        start_value = slot["value"]
        start_minutes = _time_to_minutes(start_value)
        if start_minutes is None or start_minutes + duration > 24 * 60:
            result_slots.append(
                {
                    "value": start_value,
                    "label": slot.get("label") or start_value,
                    "time_to": "",
                    "available": False,
                    "conflicts": [],
                }
            )
            continue

        end_value = _minutes_to_time(start_minutes + duration)
        lead_time = check_booking_lead_time(celebration_date=celebration_date, time_from=start_value, now=now)
        if not lead_time["allowed"]:
            result_slots.append(
                {
                    "value": start_value,
                    "label": slot.get("label") or start_value,
                    "time_to": end_value,
                    "available": False,
                    "reason": lead_time["reason"],
                    "conflicts": [],
                }
            )
            continue

        if not selected_slugs:
            program_conflicts = (
                _check_program_conflict(
                    program_slug=program_slug,
                    celebration_date=celebration_date,
                    start_minutes=start_minutes,
                    end_minutes=start_minutes + duration,
                    exclude_order_id=exclude_order_id,
                )
                if program_slug
                else []
            )
            result_slots.append(
                {
                    "value": start_value,
                    "label": slot.get("label") or start_value,
                    "time_to": end_value,
                    "available": not program_conflicts,
                    "reason": "program_overlap" if program_conflicts else "",
                    "conflicts": program_conflicts,
                }
            )
            continue

        availability = check_character_availability(
            character_slugs=selected_slugs,
            celebration_date=celebration_date,
            time_from=start_value,
            time_to=end_value,
            program_slug=program_slug,
            exclude_order_id=exclude_order_id,
        )
        result_slots.append(
            {
                "value": start_value,
                "label": slot.get("label") or start_value,
                "time_to": end_value,
                "available": bool(availability.get("success") and availability.get("available")),
                "reason": availability.get("reason", "characters") if not availability.get("available") else "",
                "conflicts": availability.get("conflicts", []),
            }
        )

    return {"success": True, "time_slots": result_slots}


def build_character_end_time_availability(
    *,
    character_slugs: list[str] | tuple[str, ...],
    celebration_date: str,
    time_from: str,
    time_slots: list[dict[str, str]] | None = None,
    extra_time_to: str | None = None,
    program_slug: str = "",
    exclude_order_id: int | None = None,
) -> dict[str, Any]:
    slots = list(time_slots or build_time_slots())
    if extra_time_to and not any(slot["value"] == extra_time_to for slot in slots):
        slots.append({"value": extra_time_to, "label": extra_time_to})
        slots.sort(key=lambda slot: _time_to_minutes(slot["value"]) if _time_to_minutes(slot["value"]) is not None else 9999)

    selected_slugs = _normalize_character_slugs(list(character_slugs))
    start_minutes = _time_to_minutes(time_from)
    if start_minutes is None:
        return {"success": False, "time_to_slots": []}

    try:
        datetime.strptime(celebration_date, "%Y-%m-%d").date()
    except ValueError:
        return {"success": False, "time_to_slots": []}

    lead_time = check_booking_lead_time(celebration_date=celebration_date, time_from=time_from)
    min_duration_minutes = get_program_duration_minutes(program_slug) if program_slug else 1
    min_end_minutes = start_minutes + max(1, int(min_duration_minutes))
    result_slots: list[dict[str, Any]] = []
    for slot in slots:
        end_value = slot["value"]
        end_minutes = _time_to_minutes(end_value)
        if end_minutes is None or end_minutes <= start_minutes:
            result_slots.append(
                {
                    "value": end_value,
                    "label": slot.get("label") or end_value,
                    "available": False,
                    "reason": "invalid_range",
                    "conflicts": [],
                }
            )
            continue
        if end_minutes < min_end_minutes:
            result_slots.append(
                {
                    "value": end_value,
                    "label": slot.get("label") or end_value,
                    "available": False,
                    "reason": "below_program_duration",
                    "conflicts": [],
                }
            )
            continue

        if not lead_time["allowed"]:
            result_slots.append(
                {
                    "value": end_value,
                    "label": slot.get("label") or end_value,
                    "available": False,
                    "reason": lead_time["reason"],
                    "conflicts": [],
                }
            )
            continue

        if not selected_slugs:
            program_conflicts = (
                _check_program_conflict(
                    program_slug=program_slug,
                    celebration_date=celebration_date,
                    start_minutes=start_minutes,
                    end_minutes=end_minutes,
                    exclude_order_id=exclude_order_id,
                )
                if program_slug
                else []
            )
            result_slots.append(
                {
                    "value": end_value,
                    "label": slot.get("label") or end_value,
                    "available": not program_conflicts,
                    "reason": "program_overlap" if program_conflicts else "",
                    "conflicts": program_conflicts,
                }
            )
            continue

        availability = check_character_availability(
            character_slugs=selected_slugs,
            celebration_date=celebration_date,
            time_from=time_from,
            time_to=end_value,
            program_slug=program_slug,
            exclude_order_id=exclude_order_id,
        )
        result_slots.append(
            {
                "value": end_value,
                "label": slot.get("label") or end_value,
                "available": bool(availability.get("success") and availability.get("available")),
                "reason": availability.get("reason", "characters") if not availability.get("available") else "",
                "conflicts": availability.get("conflicts", []),
            }
        )

    return {"success": True, "time_to_slots": result_slots}


def create_party_order(customer_id: int, data: dict[str, Any]) -> dict[str, Any]:
    _ensure_party_order_columns()
    block = get_customer_block_status(int(customer_id))
    if block:
        return {"success": False, "errors": {"__block__": block["block_reason"]}}
    selected_program_slug = (data.get("program_slug") or "").strip()
    selected_character_slugs = [slug.strip() for slug in data.get("character_slugs", []) if slug and slug.strip()]
    selected_character_slugs = list(dict.fromkeys(selected_character_slugs))
    celebration_date = (data.get("celebration_date") or "").strip()
    time_from = (data.get("time_from") or "").strip()
    time_to = (data.get("time_to") or "").strip()
    celebrant_name = (data.get("celebrant_name") or "").strip()
    address_text = (data.get("address_text") or "").strip()[:400]
    location_label = (data.get("map_label") or "").strip()
    location_lat = _parse_coordinate(data.get("map_lat"))
    location_lng = _parse_coordinate(data.get("map_lng"))
    map_url = ""
    if not address_text and location_label:
        address_text = location_label
    payment_method = (data.get("payment_method") or "").strip().lower()
    payment_provider = (data.get("payment_provider") or "").strip().lower()
    notes = (data.get("notes") or "").strip()[:400]
    raw_addon_slugs = data.get("addon_slugs") or []
    if isinstance(raw_addon_slugs, str):
        raw_addon_slugs = [raw_addon_slugs]
    selected_addon_slugs = list(
        dict.fromkeys(str(slug or "").strip() for slug in raw_addon_slugs if str(slug or "").strip())
    )
    free_addon_slug = (data.get("free_addon_slug") or "").strip()
    gift_choices = data.get("gift_choices") or {}
    if not isinstance(gift_choices, dict):
        gift_choices = {}

    errors: dict[str, str] = {}

    if not selected_program_slug:
        errors["program_slug"] = "Выберите шоу-программу."

    program = None
    if selected_program_slug:
        program = get_character_by_slug(selected_program_slug)
        if not program or program.get("entity_type") != ENTITY_TYPE_SHOW_PROGRAM:
            errors["program_slug"] = "Выбранная шоу-программа не найдена."
        elif selected_character_slugs and selected_program_slug in FIXED_CAST_SHOW_PROGRAM_SLUGS:
            errors["character_slugs"] = (
                "Состав артистов уже включён в эту программу; дополнительные персонажи недоступны."
            )

    program_addons: list[dict[str, Any]] = []
    selected_paid_addons: list[dict[str, Any]] = []
    gift_markers: list[str] = []
    if program:
        try:
            from .addon_store import list_program_addons_for_public

            program_addons = list_program_addons_for_public(int(program.get("id") or 0))
        except Exception:
            program_addons = []

        paid_by_slug: dict[str, dict[str, Any]] = {}
        gift_groups: dict[str, dict[str, dict[str, Any]]] = {}
        for addon in program_addons:
            slug = str(addon.get("slug") or "").strip()
            mode = str(addon.get("gift_mode") or "none").strip()
            if mode == "none" and addon.get("is_free_choice"):
                mode = "choice_one"
            if mode == "choice_one":
                group_key = str(addon.get("gift_group") or "default").strip() or "default"
                gift_groups.setdefault(group_key, {})[slug] = addon
            elif mode == "bundle_all":
                gift_markers.append(f"[Подарок: {addon.get('name', '')}]")
            elif mode == "none" and slug and max(0, int(addon.get("price") or 0)) > 0:
                paid_by_slug[slug] = addon

        invalid_paid_slugs = [slug for slug in selected_addon_slugs if slug not in paid_by_slug]
        if invalid_paid_slugs:
            errors["addon_slugs"] = "Одна из выбранных дополнительных услуг недоступна для этого шоу."
        selected_slug_set = set(selected_addon_slugs)
        selected_paid_addons = [
            paid_by_slug[str(addon.get("slug") or "")]
            for addon in program_addons
            if str(addon.get("slug") or "") in selected_slug_set
            and str(addon.get("slug") or "") in paid_by_slug
        ]

        normalized_gift_choices = {
            str(group_key or "").strip(): str(slug or "").strip()
            for group_key, slug in gift_choices.items()
            if str(group_key or "").strip() and str(slug or "").strip()
        }
        if free_addon_slug and gift_groups and not normalized_gift_choices:
            legacy_group_key = next(
                (
                    group_key
                    for group_key, addons_by_slug in gift_groups.items()
                    if free_addon_slug in addons_by_slug
                ),
                "",
            )
            if legacy_group_key:
                normalized_gift_choices[legacy_group_key] = free_addon_slug

        unknown_groups = set(normalized_gift_choices) - set(gift_groups)
        if unknown_groups:
            errors["gift_choices"] = "Выбранная группа подарков недоступна для этого шоу."

        for group_key, addons_by_slug in gift_groups.items():
            selected_gift_slug = normalized_gift_choices.get(group_key, "")
            if not selected_gift_slug:
                errors["gift_choices"] = "Выберите обязательный подарок: маски или шары."
                continue
            addon = addons_by_slug.get(selected_gift_slug)
            if not addon:
                errors["gift_choices"] = "Выбранный подарок недоступен для этого шоу."
                continue
            gift_markers.append(f"[Подарок: {addon.get('name', '')}]")

        if normalized_gift_choices and not gift_groups:
            errors["gift_choices"] = "Для выбранной программы подарки не предусмотрены."
    elif selected_addon_slugs:
        errors["addon_slugs"] = "Сначала выберите шоу-программу."
    elif free_addon_slug or gift_choices:
        errors["gift_choices"] = "Сначала выберите шоу-программу."
    for marker in gift_markers:
        if marker and marker not in notes:
            notes = f"{marker}\n{notes}".strip() if notes else marker

    ensemble_picks = parse_ensemble_member_values(data.get("ensemble_members"))

    selected_characters: list[dict[str, Any]] = []
    ensemble_selection: dict[str, list[str]] = {}
    for slug in selected_character_slugs:
        character = get_character_by_slug(slug)
        if not character or character.get("entity_type") != ENTITY_TYPE_CHARACTER:
            errors["character_slugs"] = "Один из выбранных персонажей больше недоступен."
            continue
        selected_characters.append(character)
        members = character.get("ensemble_members") or []
        if len(members) <= 1:
            continue
        picked = normalize_ensemble_selection(character, ensemble_picks.get(slug, []))
        included = max(0, int(character.get("ensemble_included_count") or 0))
        if len(picked) < min(included, len(members)):
            errors["character_slugs"] = (
                f"Для «{character['name']}» выберите минимум {included} героев из состава."
            )
            continue
        ensemble_selection[slug] = picked

    performer_rule_error = validate_character_performer_rules(
        program,
        selected_characters,
        ensemble_selection,
    )
    if performer_rule_error and "character_slugs" not in errors:
        errors["character_slugs"] = performer_rule_error

    try:
        parsed_date = datetime.strptime(celebration_date, "%Y-%m-%d").date()
    except ValueError:
        parsed_date = None
    if not parsed_date:
        errors["celebration_date"] = "Выберите дату праздника."

    start_minutes = _time_to_minutes(time_from)
    end_minutes = _time_to_minutes(time_to)
    if start_minutes is None:
        errors["time_from"] = "Укажите время начала."
    if end_minutes is None:
        errors["time_to"] = "Укажите время окончания."
    if start_minutes is not None and end_minutes is not None and end_minutes <= start_minutes:
        errors["time_to"] = "Время окончания должно быть позже времени начала."
    if parsed_date and start_minutes is not None:
        lead_time = check_booking_lead_time(celebration_date=celebration_date, time_from=time_from)
        if not lead_time["allowed"]:
            errors["time_from"] = lead_time["message"]

    if parsed_date and start_minutes is not None and end_minutes is not None and end_minutes > start_minutes:
        slugs_to_check = [character["slug"] for character in selected_characters]
        availability = check_character_availability(
            character_slugs=slugs_to_check,
            celebration_date=celebration_date,
            time_from=time_from,
            time_to=time_to,
            program_slug=selected_program_slug,
        )
        if not availability.get("success") or not availability.get("available"):
            errors["availability"] = availability.get("message") or "На это время уже есть бронь. Выберите другое время."

    if not address_text:
        errors["address_text"] = "Укажите адрес или ориентир."
    if not location_label or location_lat is None or location_lng is None:
        errors["map_location"] = "Укажите точку на карте или через геолокацию."
    elif not is_inside_tashkent(location_lat, location_lng):
        errors["map_location"] = "Выбранная точка находится за пределами зоны обслуживания в Ташкенте."

    if payment_method not in SUPPORTED_PAYMENT_METHODS:
        errors["payment_method"] = "Выберите способ оплаты."
    payment_provider = ""

    celebrant_age_raw = (data.get("celebrant_age") or "").strip()
    children_count_raw = (data.get("children_count") or "").strip()
    celebrant_age = _parse_positive_int(celebrant_age_raw)
    children_count = _parse_positive_int(children_count_raw)
    if not celebrant_name:
        errors["celebrant_name"] = "Укажите имя именинника."
    if not celebrant_age_raw:
        errors["celebrant_age"] = "Укажите возраст именинника."
    elif celebrant_age is None:
        errors["celebrant_age"] = "Возраст должен быть числом."
    elif celebrant_age < 1:
        errors["celebrant_age"] = "Возраст должен быть не менее 1 года."
    elif celebrant_age > 18:
        errors["celebrant_age"] = "Возраст не может превышать 18 лет."
    if not children_count_raw:
        errors["children_count"] = "Укажите количество детей."
    elif children_count is None:
        errors["children_count"] = "Количество детей должно быть числом."
    elif children_count < 1:
        errors["children_count"] = "Количество детей должно быть не менее 1."
    elif children_count > 100:
        errors["children_count"] = "Количество детей не может превышать 100."

    program_price_base = int(program.get("base_price") or 0) if program else 0
    duration_minutes = (
        end_minutes - start_minutes
        if start_minutes is not None and end_minutes is not None and end_minutes > start_minutes
        else get_program_duration_minutes(selected_program_slug)
    )
    program_duration_minutes = get_program_duration_minutes(selected_program_slug) if program else 0
    if (
        program
        and start_minutes is not None
        and end_minutes is not None
        and end_minutes > start_minutes
        and duration_minutes < program_duration_minutes
    ):
        errors["time_to"] = (
            f"Минимальная длительность программы — {program_duration_minutes} мин. "
            "Увеличьте время окончания."
        )

    duration_multiplier = (
        max(1.0, duration_minutes / max(1, program_duration_minutes))
        if program and program_duration_minutes > 0
        else 1.0
    )
    program_price = scale_price_for_duration(
        program_price_base,
        duration_minutes,
        program_duration_minutes,
    )
    character_surcharge = calculate_order_character_surcharge(
        program,
        selected_characters,
        ensemble_selection,
        duration_multiplier,
        actual_duration_minutes=duration_minutes,
        base_duration_minutes=program_duration_minutes,
    )
    addon_total = sum(max(0, int(addon.get("price") or 0)) for addon in selected_paid_addons)
    total_price = program_price + character_surcharge + addon_total
    if location_lat is not None and location_lng is not None:
        map_url = build_map_location_url(location_lat, location_lng)

    if errors:
        return {"success": False, "errors": errors}

    order_created_at = utcnow_iso()
    with _get_connection() as connection:
        # Serialize the final availability check with the insert. The earlier
        # check provides fast form feedback; this one closes the concurrent-POST race.
        connection.execute("BEGIN IMMEDIATE")
        final_availability = check_character_availability(
            character_slugs=[character["slug"] for character in selected_characters],
            celebration_date=celebration_date,
            time_from=time_from,
            time_to=time_to,
            program_slug=selected_program_slug,
        )
        if not final_availability.get("success") or not final_availability.get("available"):
            connection.rollback()
            return {
                "success": False,
                "errors": {
                    "availability": final_availability.get("message")
                    or "На это время уже есть бронь. Выберите другое время."
                },
            }
        cursor = connection.execute(
            """
            INSERT INTO party_orders(
                customer_id, status, confirmation_state, confirmation_changed_at,
                confirmation_source, confirmation_actor,
                program_slug, program_name_snapshot, program_price_snapshot,
                total_price_snapshot, celebration_date, time_from, time_to, duration_minutes,
                celebrant_name, celebrant_age, children_count, address_text, location_label,
                location_lat, location_lng, yandex_map_url, payment_method, payment_provider, notes,
                created_at, updated_at
            )
            VALUES (?, 'new', 'unconfirmed', ?, 'order-builder', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer_id,
                order_created_at,
                f"customer:{int(customer_id)}",
                selected_program_slug,
                program["name"] if program else "",
                program_price,
                total_price,
                celebration_date,
                time_from,
                time_to,
                duration_minutes,
                celebrant_name,
                celebrant_age,
                children_count,
                address_text,
                location_label,
                location_lat,
                location_lng,
                map_url,
                payment_method,
                payment_provider,
                notes,
                order_created_at,
                order_created_at,
            ),
        )
        order_id = int(cursor.lastrowid)
        public_id = f"SRP-{order_id:05d}"
        connection.execute(
            "UPDATE party_orders SET public_id = ?, updated_at = ? WHERE id = ?",
            (public_id, utcnow_iso(), order_id),
        )

        for sort_order, character in enumerate(selected_characters, start=1):
            picked_members = ensemble_selection.get(character["slug"]) or []
            name_snapshot = build_character_name_snapshot(character, picked_members)
            connection.execute(
                """
                INSERT INTO party_order_characters(order_id, character_id, slug, name_snapshot, sort_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    character["id"],
                    character["slug"],
                    name_snapshot,
                    sort_order,
                    utcnow_iso(),
                ),
            )

        for sort_order, addon in enumerate(selected_paid_addons, start=1):
            connection.execute(
                """
                INSERT INTO party_order_addons(
                    order_id, addon_id, slug, name, price, duration_minutes, sort_order, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    int(addon.get("id") or 0) or None,
                    str(addon.get("slug") or ""),
                    str(addon.get("name") or ""),
                    max(0, int(addon.get("price") or 0)),
                    max(0, int(addon.get("duration_minutes") or 0)),
                    sort_order,
                    order_created_at,
                ),
            )

        connection.execute(
            """
            INSERT INTO admin_telegram_delivery_queue(
                order_id, delivery_generation, attempts, last_error, next_attempt_at,
                claimed_until, claim_token, created_at, updated_at
            ) VALUES (?, ?, 0, '', ?, '', '', ?, ?)
            ON CONFLICT(order_id) DO UPDATE SET
                delivery_generation = excluded.delivery_generation,
                next_attempt_at = excluded.next_attempt_at,
                claimed_until = '',
                claim_token = '',
                updated_at = excluded.updated_at
            """,
            (order_id, uuid4().hex, order_created_at, order_created_at, order_created_at),
        )

        connection.commit()

    if selected_paid_addons:
        LOGGER.info(
            "party_order_addons_created",
            extra={
                "order_id": order_id,
                "addon_slugs": [str(addon.get("slug") or "") for addon in selected_paid_addons],
                "addon_total": addon_total,
            },
        )
    order = get_order_by_id(order_id)
    return {"success": True, "order": order}


def _order_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    character_names = [name for name in (row["character_names"] or "").split("|||") if name]
    character_slugs = [slug for slug in (row["character_slugs"] or "").split("|||") if slug]
    location_lat = row["location_lat"] if "location_lat" in row.keys() else None
    location_lng = row["location_lng"] if "location_lng" in row.keys() else None
    payment_provider = row["payment_provider"] if "payment_provider" in row.keys() else ""
    map_url = row["yandex_map_url"] or build_map_location_url(location_lat, location_lng)
    confirmation_state = (
        str(row["confirmation_state"] or "unconfirmed")
        if "confirmation_state" in row.keys()
        else "unconfirmed"
    )
    if confirmation_state not in ORDER_CONFIRMATION_LABELS:
        confirmation_state = "unconfirmed"
    confirmation_label = ORDER_CONFIRMATION_LABELS[confirmation_state]
    lifecycle_status = str(row["status"] or "new")
    display_status = (
        "cancelled"
        if lifecycle_status == "cancelled"
        else "confirmed"
        if confirmation_state == "confirmed" or lifecycle_status == "done"
        else "unconfirmed"
    )
    confirmation_changed_at = (
        str(row["confirmation_changed_at"] or "")
        if "confirmation_changed_at" in row.keys()
        else ""
    )
    return {
        "id": row["id"],
        "public_id": row["public_id"],
        "customer_id": row["customer_id"],
        "customer_phone": row["customer_phone"],
        "customer_name": row["customer_name"],
        "status": lifecycle_status,
        "display_status": display_status,
        "lifecycle_status_label": LIFECYCLE_STATUS_LABELS.get(lifecycle_status, lifecycle_status),
        "confirmation_state": confirmation_state,
        "confirmation_label": confirmation_label,
        "status_label": ORDER_STATUS_LABELS[display_status],
        "confirmation_changed_at": confirmation_changed_at,
        "confirmation_changed_at_label": format_datetime_ru(confirmation_changed_at),
        "confirmation_source": row["confirmation_source"] if "confirmation_source" in row.keys() else "",
        "confirmation_actor": row["confirmation_actor"] if "confirmation_actor" in row.keys() else "",
        "confirmed_at": row["confirmed_at"] if "confirmed_at" in row.keys() else None,
        "program_slug": row["program_slug"],
        "program_name": row["program_name_snapshot"],
        "program_price": row["program_price_snapshot"] if "program_price_snapshot" in row.keys() else 0,
        "program_price_label": format_money(
            row["program_price_snapshot"] if "program_price_snapshot" in row.keys() else 0
        ),
        "character_names": character_names,
        "character_slugs": character_slugs,
        "addons": [],
        "addon_names": [],
        "addon_total": 0,
        "addon_total_label": format_money(0),
        "total_price": row["total_price_snapshot"] if "total_price_snapshot" in row.keys() else 0,
        "total_price_label": format_money(row["total_price_snapshot"] if "total_price_snapshot" in row.keys() else 0),
        "celebration_date": row["celebration_date"],
        "celebration_date_label": format_date_ru(row["celebration_date"]),
        "time_from": row["time_from"],
        "time_to": row["time_to"],
        "duration_minutes": row["duration_minutes"] if "duration_minutes" in row.keys() else None,
        "celebrant_name": row["celebrant_name"],
        "celebrant_age": row["celebrant_age"],
        "children_count": row["children_count"],
        "address_text": row["address_text"],
        "location_label": row["location_label"] if "location_label" in row.keys() else "",
        "location_lat": location_lat,
        "location_lng": location_lng,
        "yandex_map_url": map_url,
        "payment_method": row["payment_method"],
        "payment_method_label": PAYMENT_METHOD_LABELS.get(row["payment_method"], row["payment_method"]),
        "payment_provider": payment_provider,
        "payment_provider_label": CARD_PROVIDER_LABELS.get(payment_provider, payment_provider),
        "notes": row["notes"],
        "created_at": row["created_at"],
        "created_at_label": format_datetime_ru(row["created_at"]),
        "updated_at": row["updated_at"],
        "updated_at_label": format_datetime_ru(row["updated_at"]),
    }


def _attach_order_addons(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order_ids = [int(order["id"]) for order in orders if order.get("id")]
    if not order_ids:
        return orders
    placeholders = ", ".join("?" for _ in order_ids)
    with _get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT order_id, addon_id, slug, name, price, duration_minutes, sort_order
            FROM party_order_addons
            WHERE order_id IN ({placeholders})
            ORDER BY order_id ASC, sort_order ASC, id ASC
            """,
            tuple(order_ids),
        ).fetchall()
    addons_by_order: dict[int, list[dict[str, Any]]] = {order_id: [] for order_id in order_ids}
    for row in rows:
        price = max(0, int(row["price"] or 0))
        duration_minutes = max(0, int(row["duration_minutes"] or 0))
        addons_by_order.setdefault(int(row["order_id"]), []).append(
            {
                "addon_id": row["addon_id"],
                "slug": str(row["slug"] or ""),
                "name": str(row["name"] or ""),
                "price": price,
                "price_label": format_money(price),
                "duration_minutes": duration_minutes,
                "duration_label": f"{duration_minutes} мин" if duration_minutes else "",
                "sort_order": int(row["sort_order"] or 0),
            }
        )
    for order in orders:
        addons = addons_by_order.get(int(order["id"]), [])
        addon_total = sum(int(addon["price"]) for addon in addons)
        order["addons"] = addons
        order["addon_names"] = [str(addon["name"]) for addon in addons]
        order["addon_total"] = addon_total
        order["addon_total_label"] = format_money(addon_total)
    return orders


def _list_orders(where_clause: str = "", params: tuple[Any, ...] = (), *, limit: int | None = None) -> list[dict[str, Any]]:
    _ensure_party_order_columns()
    query = """
        SELECT
            o.*,
            c.phone_display AS customer_phone,
            c.full_name AS customer_name,
            c.phone_verified_at AS customer_phone_verified_at,
            GROUP_CONCAT(oc.name_snapshot, '|||') AS character_names,
            GROUP_CONCAT(oc.slug, '|||') AS character_slugs
        FROM party_orders o
        LEFT JOIN customer_accounts c ON c.id = o.customer_id
        LEFT JOIN party_order_characters oc ON oc.order_id = o.id
    """
    if where_clause:
        query += f" {where_clause}"
    query += " GROUP BY o.id ORDER BY o.created_at DESC"
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    with _get_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return _attach_order_addons([_order_row_to_dict(row) for row in rows])


def get_order_by_id(order_id: int) -> dict[str, Any] | None:
    items = _list_orders("WHERE o.id = ?", (order_id,), limit=1)
    return items[0] if items else None


def get_order_by_public_id(public_id: str, customer_id: int | None = None) -> dict[str, Any] | None:
    params: list[Any] = [public_id]
    where = "WHERE o.public_id = ?"
    if customer_id is not None:
        where += " AND o.customer_id = ?"
        params.append(customer_id)
    items = _list_orders(where, tuple(params), limit=1)
    return items[0] if items else None


def list_customer_orders(customer_id: int) -> list[dict[str, Any]]:
    return _list_orders("WHERE o.customer_id = ?", (customer_id,))


def list_admin_orders(
    status: str = "",
    limit: int = 100,
    *,
    search: str = "",
    date_from: str = "",
    date_to: str = "",
    customer_id: int | None = None,
) -> list[dict[str, Any]]:
    where_parts: list[str] = []
    params: list[Any] = []

    if customer_id is not None:
        where_parts.append("o.customer_id = ?")
        params.append(int(customer_id))

    if status == "cancelled":
        where_parts.append("o.status = 'cancelled'")
    elif status == "unconfirmed":
        where_parts.append("o.confirmation_state = 'unconfirmed' AND o.status != 'cancelled'")
    elif status == "confirmed":
        where_parts.append("o.confirmation_state = ?")
        params.append(status)

    search_clean = (search or "").strip()
    if search_clean:
        like = f"%{search_clean}%"
        where_parts.append(
            "("
            "o.public_id LIKE ?"
            " OR c.phone_display LIKE ?"
            " OR c.phone_normalized LIKE ?"
            " OR c.full_name LIKE ?"
            " OR o.celebrant_name LIKE ?"
            ")"
        )
        params.extend([like, like, like, like, like])

    date_from_clean = (date_from or "").strip()
    if date_from_clean:
        where_parts.append("o.celebration_date >= ?")
        params.append(date_from_clean)

    date_to_clean = (date_to or "").strip()
    if date_to_clean:
        where_parts.append("o.celebration_date <= ?")
        params.append(date_to_clean)

    where_clause = ""
    if where_parts:
        where_clause = "WHERE " + " AND ".join(where_parts)
    return _list_orders(where_clause, tuple(params), limit=limit)


def get_order_summary() -> dict[str, int]:
    _ensure_party_order_columns()
    summary = {key: 0 for key in ORDER_STATUS_LABELS}
    summary["total"] = 0
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                CASE
                    WHEN status = 'cancelled' THEN 'cancelled'
                    WHEN confirmation_state = 'confirmed' OR status = 'done' THEN 'confirmed'
                    ELSE 'unconfirmed'
                END AS display_status,
                COUNT(*) AS total
            FROM party_orders
            GROUP BY display_status
            """
        ).fetchall()
    for row in rows:
        summary["total"] += int(row["total"])
        if row["display_status"] in summary:
            summary[row["display_status"]] = int(row["total"])
    return summary


def set_order_confirmation(
    order_id: int,
    confirmation_state: str,
    *,
    source: str,
    actor: str = "",
) -> dict[str, Any]:
    """Set the two-state confirmation flag without changing lifecycle ``status``."""
    normalized_state = (confirmation_state or "").strip().lower()
    if normalized_state not in ORDER_CONFIRMATION_LABELS:
        return {"success": False, "changed": False, "message": "invalid confirmation state"}

    _ensure_party_order_columns()
    source_clean = (source or "unknown").strip()[:40] or "unknown"
    actor_clean = (actor or "").strip()[:160]
    now = utcnow_iso()
    with _get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, status, confirmation_state FROM party_orders WHERE id = ? LIMIT 1",
            (int(order_id),),
        ).fetchone()
        if not row:
            connection.rollback()
            return {"success": False, "changed": False, "message": "order not found"}

        previous_state = str(row["confirmation_state"] or "unconfirmed")
        if previous_state not in ORDER_CONFIRMATION_LABELS:
            previous_state = "unconfirmed"
        previous_lifecycle = str(row["status"] or "new")
        if previous_lifecycle in {"cancelled", "done"} and previous_state != normalized_state:
            connection.rollback()
            return {
                "success": False,
                "changed": False,
                "message": "terminal order state is immutable",
            }
        next_lifecycle = previous_lifecycle
        if normalized_state == "confirmed" and previous_lifecycle in {"new", "contacted", "confirmed"}:
            next_lifecycle = "confirmed"
        elif normalized_state == "unconfirmed" and previous_lifecycle == "confirmed":
            next_lifecycle = "new"
        confirmation_changed = previous_state != normalized_state
        lifecycle_changed = previous_lifecycle != next_lifecycle
        if not confirmation_changed and not lifecycle_changed:
            connection.commit()
            return {
                "success": True,
                "changed": False,
                "order_id": int(row["id"]),
                "confirmation_state": normalized_state,
            }

        cursor = connection.execute(
            """
            UPDATE party_orders
            SET status = ?,
                confirmation_state = ?,
                confirmation_changed_at = ?,
                confirmation_source = ?,
                confirmation_actor = ?,
                confirmed_at = ?,
                updated_at = ?
            WHERE id = ? AND confirmation_state = ?
            """,
            (
                next_lifecycle,
                normalized_state,
                now,
                source_clean,
                actor_clean,
                now if normalized_state == "confirmed" else None,
                now,
                int(row["id"]),
                previous_state,
            ),
        )
        if cursor.rowcount != 1:
            connection.rollback()
            return {"success": False, "changed": False, "message": "concurrent update"}
        if confirmation_changed:
            connection.execute(
                """
                INSERT INTO party_order_confirmation_events(
                    order_id, previous_state, confirmation_state, source, actor, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(row["id"]), previous_state, normalized_state, source_clean, actor_clean, now),
            )
        _queue_confirmation_sync(connection, int(row["id"]), now)
        connection.commit()
    return {
        "success": True,
        "changed": True,
        "order_id": int(order_id),
        "confirmation_state": normalized_state,
    }


def set_order_confirmation_by_public_id(
    public_id: str,
    confirmation_state: str,
    *,
    source: str,
    actor: str = "",
) -> dict[str, Any]:
    public_id_clean = (public_id or "").strip()
    if not public_id_clean:
        return {"success": False, "changed": False, "message": "missing public id"}
    _ensure_party_order_columns()
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT id FROM party_orders WHERE public_id = ? LIMIT 1",
            (public_id_clean,),
        ).fetchone()
    if not row:
        return {"success": False, "changed": False, "message": "order not found"}
    return set_order_confirmation(
        int(row["id"]),
        confirmation_state,
        source=source,
        actor=actor,
    )


def apply_legacy_order_cancellation_by_public_id(
    public_id: str,
    *,
    source: str = "telegram-legacy",
    actor: str = "",
) -> dict[str, Any]:
    """Preserve the old Telegram ``cancel`` action as an internal cancellation.

    The admin/customer-facing confirmation vocabulary remains two-state, while
    the lifecycle cancellation releases availability and keeps anti-abuse logic.
    """
    public_id_clean = (public_id or "").strip()
    if not public_id_clean:
        return {"success": False, "changed": False, "message": "missing public id"}

    _ensure_party_order_columns()
    source_clean = (source or "telegram-legacy").strip()[:40] or "telegram-legacy"
    actor_clean = (actor or "").strip()[:160]
    now = utcnow_iso()
    customer_id = 0
    with _get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT id, customer_id, status, confirmation_state
            FROM party_orders
            WHERE public_id = ?
            LIMIT 1
            """,
            (public_id_clean,),
        ).fetchone()
        if not row:
            connection.rollback()
            return {"success": False, "changed": False, "message": "order not found"}

        order_id = int(row["id"])
        customer_id = int(row["customer_id"])
        if str(row["status"] or "") == "done":
            connection.rollback()
            return {
                "success": False,
                "changed": False,
                "message": "terminal order state is immutable",
            }
        previous_state = str(row["confirmation_state"] or "unconfirmed")
        if previous_state not in ORDER_CONFIRMATION_LABELS:
            previous_state = "unconfirmed"
        changed = str(row["status"] or "") != "cancelled" or previous_state != "unconfirmed"
        if changed:
            connection.execute(
                """
                UPDATE party_orders
                SET status = 'cancelled',
                    confirmation_state = 'unconfirmed',
                    confirmation_changed_at = ?,
                    confirmation_source = ?,
                    confirmation_actor = ?,
                    confirmed_at = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, source_clean, actor_clean, now, order_id),
            )
            if previous_state != "unconfirmed":
                connection.execute(
                    """
                    INSERT INTO party_order_confirmation_events(
                        order_id, previous_state, confirmation_state, source, actor, created_at
                    ) VALUES (?, ?, 'unconfirmed', ?, ?, ?)
                    """,
                    (order_id, previous_state, source_clean, actor_clean, now),
                )
            _queue_confirmation_sync(connection, order_id, now)
        connection.commit()

    if changed:
        apply_cancellation_block_if_needed(customer_id)
    return {
        "success": True,
        "changed": changed,
        "order_id": order_id,
        "confirmation_state": "unconfirmed",
        "lifecycle_status": "cancelled",
    }


def _sync_order_confirmation_messages(order_id: int) -> None:
    try:
        from .admin_notifications import sync_order_messages

        sync_order_messages(int(order_id))
    except Exception:
        # Telegram delivery must never roll back a persisted admin decision.
        return


def update_order_status(
    order_id: int,
    status: str,
    *,
    source: str = "admin",
    actor: str = "admin-panel",
) -> bool:
    """Admin-panel entry point for confirmation and explicit cancellation."""
    normalized_status = (status or "").strip().lower()
    if normalized_status == "cancelled":
        order = get_order_by_id(int(order_id))
        result = (
            apply_legacy_order_cancellation_by_public_id(
                str(order.get("public_id") or ""),
                source=source,
                actor=actor,
            )
            if order
            else {"success": False}
        )
    else:
        result = set_order_confirmation(
            int(order_id),
            normalized_status,
            source=source,
            actor=actor,
        )
    if result.get("success"):
        _sync_order_confirmation_messages(int(order_id))
    return bool(result.get("success"))


def set_order_status_by_public_id(public_id: str, status: str, decided_by: str = "") -> bool:
    """Compatibility entry point used by older Telegram integrations."""
    if (status or "").strip().lower() in {"cancel", "cancelled"}:
        result = apply_legacy_order_cancellation_by_public_id(
            public_id,
            source="telegram-legacy",
            actor=decided_by,
        )
        if result.get("success"):
            _sync_order_confirmation_messages(int(result.get("order_id") or 0))
        return bool(result.get("success"))
    result = set_order_confirmation_by_public_id(
        public_id,
        status,
        source="telegram",
        actor=decided_by,
    )
    if result.get("success"):
        _sync_order_confirmation_messages(int(result.get("order_id") or 0))
    return bool(result.get("success"))
