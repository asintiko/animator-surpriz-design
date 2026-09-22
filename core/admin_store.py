from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup
from werkzeug.security import check_password_hash, generate_password_hash

from .catalog_store import get_catalog_summary, init_catalog_store
from .config import DATA_ROOT, FORMS_ROOT, ROUTES_ROOT

DB_ROOT = DATA_ROOT / "admin"
DB_PATH = DB_ROOT / "site_admin.sqlite3"
MAX_LOGIN_ATTEMPTS = 3
LOGIN_LOCK_MINUTES = 15
VISITOR_ID_SALT_SETTING = "visitor_id_salt"
VISITOR_SESSION_TIMEOUT_MINUTES = 30
VISITOR_EVENT_RETENTION_DAYS = 180
SQLITE_BUSY_TIMEOUT_SECONDS = 5.0
ADMIN_LOCAL_TIMEZONE = timezone(timedelta(hours=5))
DEFAULT_PARTY_BUILDER_SETTINGS: dict[str, int] = {
    "party_included_characters": 2,
    "party_extra_character_3_price": 200_000,
    "party_extra_character_4_plus_price": 200_000,
}

DEFAULT_SETTINGS: dict[str, bool] = {
    "new_year_season_enabled": False,
    "show_new_year_menu_link": False,
    "show_home_new_year_showcase": False,
    "show_snow": False,
    "show_promotions": False,
    "hide_easter_egg": False,
    "picker_enabled": False,
}
SKIPPED_ROUTE_DIRS = {"page", "errors"}
CATALOG_KIND_TO_DIR = {
    "character": "character",
    "category": "character-category",
    "tag": "character-tag",
}
TITLE_BLACKLIST = {
    "персонажи",
    "повод мероприятия",
    "похожие персонажи",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat()


def _local_day_start_utc_iso() -> str:
    local_now = utcnow().astimezone(ADMIN_LOCAL_TIMEZONE)
    return local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()


def _get_connection(*, timeout_seconds: float = SQLITE_BUSY_TIMEOUT_SECONDS) -> sqlite3.Connection:
    DB_ROOT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=timeout_seconds)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {max(0, int(timeout_seconds * 1000))}")
    return connection


def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _add_column_if_missing(connection: sqlite3.Connection, column: str, definition: str) -> None:
    if _has_column(connection, "visit_events", column):
        return
    try:
        connection.execute(f"ALTER TABLE visit_events ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError as error:
        if "duplicate column name" not in str(error).lower():
            raise


def _ensure_visitor_salt(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT value FROM site_settings WHERE key = ? LIMIT 1",
        (VISITOR_ID_SALT_SETTING,),
    ).fetchone()
    if row and str(row["value"]).strip():
        return str(row["value"])

    candidate = secrets.token_hex(32)
    connection.execute(
        """
        INSERT INTO site_settings(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO NOTHING
        """,
        (VISITOR_ID_SALT_SETTING, candidate, utcnow_iso()),
    )
    row = connection.execute(
        "SELECT value FROM site_settings WHERE key = ? LIMIT 1",
        (VISITOR_ID_SALT_SETTING,),
    ).fetchone()
    return str(row["value"]) if row else candidate


def _visitor_digest(source: str, salt: str) -> str:
    key = salt.encode("utf-8")[:64]
    digest = hashlib.blake2b(source.encode("utf-8"), key=key, digest_size=16).hexdigest()
    return f"v1_{digest}"


def _build_visitor_id(
    *,
    salt: str,
    visitor_id: str = "",
    remote_addr: str = "",
    user_agent: str = "",
    legacy_row_id: int | None = None,
) -> str:
    supplied_id = str(visitor_id or "").strip()
    if supplied_id:
        source = f"anonymous-id\0{supplied_id}"
    elif remote_addr or user_agent:
        source = f"request-fingerprint\0{remote_addr}\0{user_agent}"
    else:
        source = f"legacy-row\0{legacy_row_id if legacy_row_id is not None else secrets.token_hex(16)}"
    return _visitor_digest(source, salt)


def _ensure_visit_event_columns(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(connection, "visitor_id", "TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(connection, "customer_id", "INTEGER")
    _add_column_if_missing(connection, "referrer", "TEXT NOT NULL DEFAULT ''")

    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_visit_events_visitor
        ON visit_events(visitor_id, visited_at DESC);

        CREATE INDEX IF NOT EXISTS idx_visit_events_customer
        ON visit_events(customer_id, visited_at DESC);
        """
    )

    salt = _ensure_visitor_salt(connection)
    legacy_rows = connection.execute(
        """
        SELECT id, remote_addr, user_agent
        FROM visit_events
        WHERE visitor_id IS NULL OR visitor_id = ''
        """
    ).fetchall()
    if legacy_rows:
        connection.executemany(
            "UPDATE visit_events SET visitor_id = ? WHERE id = ?",
            [
                (
                    _build_visitor_id(
                        salt=salt,
                        remote_addr=str(row["remote_addr"] or ""),
                        user_agent=str(row["user_agent"] or ""),
                        legacy_row_id=int(row["id"]),
                    ),
                    int(row["id"]),
                )
                for row in legacy_rows
            ],
        )

    ip_rows = connection.execute(
        "SELECT id, remote_addr FROM visit_events WHERE remote_addr IS NOT NULL AND remote_addr != ''"
    ).fetchall()
    connection.executemany(
        "UPDATE visit_events SET remote_addr = ? WHERE id = ?",
        [(_mask_ip(str(row["remote_addr"] or "")), int(row["id"])) for row in ip_rows],
    )
    connection.execute(
        "UPDATE visit_events SET user_agent = substr(user_agent, 1, 320) WHERE length(user_agent) > 320"
    )
    retention_cutoff = (utcnow() - timedelta(days=VISITOR_EVENT_RETENTION_DAYS)).isoformat()
    connection.execute(
        "DELETE FROM visit_events WHERE datetime(visited_at) < datetime(?)",
        (retention_cutoff,),
    )


def _ensure_default_settings(connection: sqlite3.Connection) -> None:
    for key, value in DEFAULT_SETTINGS.items():
        connection.execute(
            """
            INSERT INTO site_settings(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO NOTHING
            """,
            (key, "1" if value else "0", utcnow_iso()),
        )


def _ensure_default_admin(connection: sqlite3.Connection) -> None:
    existing = connection.execute(
        "SELECT id FROM admins ORDER BY id ASC LIMIT 1",
    ).fetchone()
    if existing:
        return

    username = os.getenv("SURPRIZ_ADMIN_USERNAME", "").strip().lower()
    password = os.getenv("SURPRIZ_ADMIN_PASSWORD", "")
    bootstrap_requested = os.getenv("SURPRIZ_ADMIN_BOOTSTRAP", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    credentials_supplied = bool(username or password)
    if not bootstrap_requested and not credentials_supplied:
        raise RuntimeError(
            "Admin storage is empty. Configure SURPRIZ_ADMIN_USERNAME and "
            "SURPRIZ_ADMIN_PASSWORD before starting the application."
        )
    if not username or not password:
        raise RuntimeError(
            "Admin bootstrap requires both SURPRIZ_ADMIN_USERNAME and "
            "SURPRIZ_ADMIN_PASSWORD."
        )

    connection.execute(
        """
        INSERT INTO admins(username, password_hash, is_active, created_at, updated_at)
        VALUES (?, ?, 1, ?, ?)
        """,
        (
            username,
            generate_password_hash(password),
            utcnow_iso(),
            utcnow_iso(),
        ),
    )


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _fallback_title(meta: dict[str, Any], slug: str) -> str:
    title = _clean_text(str(meta.get("title", "")))
    if "|" in title:
        title = title.split("|", 1)[0].strip()
    if title:
        return title
    return slug.replace("-", " ").strip().title()


def _extract_entity_title(kind: str, bundle_root: Path, meta: dict[str, Any], slug: str) -> str:
    content_path = bundle_root / "content.html"
    if content_path.exists():
        soup = BeautifulSoup(content_path.read_text(encoding="utf-8-sig"), "html.parser")
        if kind == "character":
            heading = soup.select_one("h1")
            if heading:
                title = _clean_text(heading.get_text(" ", strip=True))
                if title:
                    return title
        else:
            candidates: list[str] = []
            for selector in (
                ".woocommerce-products-header__title.page-title",
                ".woocommerce-products-header__title",
                "h1.page-title",
                "h1",
                "h2",
            ):
                for element in soup.select(selector):
                    title = _clean_text(element.get_text(" ", strip=True))
                    if not title or title.lower() in TITLE_BLACKLIST:
                        continue
                    candidates.append(title)
            if candidates:
                return candidates[-1]

    return _fallback_title(meta, slug)


def sync_catalog_entities() -> dict[str, int]:
    counts = {"character": 0, "category": 0, "tag": 0}
    synced_at = utcnow_iso()

    with _get_connection() as connection:
        for kind, directory_name in CATALOG_KIND_TO_DIR.items():
            root = ROUTES_ROOT / directory_name
            if not root.exists():
                continue

            for entry in sorted(root.iterdir()):
                if not entry.is_dir() or entry.name in SKIPPED_ROUTE_DIRS:
                    continue

                meta_path = entry / "meta.json"
                if not meta_path.exists():
                    continue

                meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
                route = str(meta.get("route", "")).strip()
                if not route:
                    continue

                title = _extract_entity_title(kind, entry, meta, entry.name)
                connection.execute(
                    """
                    INSERT INTO catalog_entities(kind, slug, route, title, source_path, synced_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(route) DO UPDATE SET
                        kind = excluded.kind,
                        slug = excluded.slug,
                        title = excluded.title,
                        source_path = excluded.source_path,
                        synced_at = excluded.synced_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        kind,
                        entry.name,
                        route,
                        title,
                        str(entry.relative_to(ROUTES_ROOT)).replace("\\", "/"),
                        synced_at,
                        synced_at,
                        synced_at,
                    ),
                )
                counts[kind] += 1

        connection.commit()

    return counts


def init_admin_store() -> None:
    with _get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                failed_attempts INTEGER NOT NULL DEFAULT 0,
                locked_until TEXT,
                updated_at TEXT NOT NULL,
                UNIQUE(username, ip_address)
            );

            CREATE TABLE IF NOT EXISTS site_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS visit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                remote_addr TEXT,
                user_agent TEXT,
                visitor_id TEXT NOT NULL DEFAULT '',
                customer_id INTEGER,
                referrer TEXT NOT NULL DEFAULT '',
                visited_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_visit_events_visited_at ON visit_events(visited_at);
            CREATE INDEX IF NOT EXISTS idx_visit_events_path ON visit_events(path);

            CREATE TABLE IF NOT EXISTS catalog_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                slug TEXT NOT NULL,
                route TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                source_path TEXT NOT NULL,
                synced_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        _ensure_default_settings(connection)
        _ensure_party_builder_settings(connection)
        _ensure_default_admin(connection)
        _ensure_visit_event_columns(connection)
        connection.commit()

    init_catalog_store()


def _ensure_party_builder_settings(connection: sqlite3.Connection) -> None:
    for key, value in DEFAULT_PARTY_BUILDER_SETTINGS.items():
        connection.execute(
            """
            INSERT INTO site_settings(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO NOTHING
            """,
            (key, str(value), utcnow_iso()),
        )


def get_party_builder_settings() -> dict[str, int]:
    settings = DEFAULT_PARTY_BUILDER_SETTINGS.copy()
    if not DB_PATH.exists():
        return settings
    with _get_connection() as connection:
        rows = connection.execute(
            "SELECT key, value FROM site_settings WHERE key LIKE 'party_%'"
        ).fetchall()
    for row in rows:
        key = str(row["key"])
        if key not in settings:
            continue
        try:
            settings[key] = max(0, int(row["value"]))
        except (TypeError, ValueError):
            pass
    return settings


def get_public_settings() -> dict[str, bool]:
    settings = DEFAULT_SETTINGS.copy()
    if not DB_PATH.exists():
        return settings

    with _get_connection() as connection:
        rows = connection.execute("SELECT key, value FROM site_settings").fetchall()

    for row in rows:
        key = str(row["key"])
        if key in DEFAULT_PARTY_BUILDER_SETTINGS or key == VISITOR_ID_SALT_SETTING:
            # Builder numbers and the private visitor salt are not public boolean flags.
            continue
        settings[key] = row["value"] == "1"
    return settings


def update_public_settings(values: dict[str, bool]) -> dict[str, bool]:
    current = get_public_settings()
    current.update(values)
    updated_at = utcnow_iso()

    with _get_connection() as connection:
        for key, value in current.items():
            if key in DEFAULT_PARTY_BUILDER_SETTINGS or key == VISITOR_ID_SALT_SETTING:
                # Never coerce builder numbers or the private visitor salt to booleans.
                continue
            connection.execute(
                """
                INSERT INTO site_settings(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, "1" if value else "0", updated_at),
            )
        connection.commit()

    return current


def apply_new_year_preset(enabled: bool) -> dict[str, bool]:
    preset = {
        "new_year_season_enabled": enabled,
        "show_new_year_menu_link": enabled,
        "show_home_new_year_showcase": enabled,
        "show_snow": enabled,
        "show_promotions": enabled,
    }
    return update_public_settings(preset)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _get_attempt_row(connection: sqlite3.Connection, username: str, ip_address: str) -> sqlite3.Row | None:
    row = connection.execute(
        """
        SELECT username, ip_address, failed_attempts, locked_until
        FROM login_attempts
        WHERE username = ? AND ip_address = ?
        LIMIT 1
        """,
        (username, ip_address),
    ).fetchone()

    locked_until = _parse_iso(row["locked_until"]) if row else None
    if row and locked_until and locked_until <= utcnow():
        connection.execute(
            "DELETE FROM login_attempts WHERE username = ? AND ip_address = ?",
            (username, ip_address),
        )
        connection.commit()
        return None

    return row


def get_login_attempt_state(username: str, ip_address: str) -> dict[str, Any]:
    normalized_username = username.strip().lower()
    with _get_connection() as connection:
        row = _get_attempt_row(connection, normalized_username, ip_address)

    if not row:
        return {
            "failed_attempts": 0,
            "remaining_attempts": MAX_LOGIN_ATTEMPTS,
            "is_locked": False,
            "locked_until": None,
        }

    failed_attempts = int(row["failed_attempts"])
    locked_until = row["locked_until"]
    return {
        "failed_attempts": failed_attempts,
        "remaining_attempts": max(0, MAX_LOGIN_ATTEMPTS - failed_attempts),
        "is_locked": bool(locked_until),
        "locked_until": locked_until,
    }


def authenticate_admin(username: str, password: str, ip_address: str) -> dict[str, Any]:
    normalized_username = username.strip().lower()
    with _get_connection() as connection:
        attempt_row = _get_attempt_row(connection, normalized_username, ip_address)
        if attempt_row and attempt_row["locked_until"]:
            return {
                "success": False,
                "message": "Вход временно заблокирован после 3 неудачных попыток. Попробуйте позже.",
                "remaining_attempts": 0,
                "admin": None,
            }

        admin = connection.execute(
            """
            SELECT id, username, password_hash, is_active
            FROM admins
            WHERE username = ? AND is_active = 1
            LIMIT 1
            """,
            (normalized_username,),
        ).fetchone()

        if admin and check_password_hash(admin["password_hash"], password):
            connection.execute(
                "DELETE FROM login_attempts WHERE username = ? AND ip_address = ?",
                (normalized_username, ip_address),
            )
            connection.commit()
            return {
                "success": True,
                "message": "",
                "remaining_attempts": MAX_LOGIN_ATTEMPTS,
                "admin": {"id": admin["id"], "username": admin["username"]},
            }

        failed_attempts = int(attempt_row["failed_attempts"]) + 1 if attempt_row else 1
        locked_until = None
        if failed_attempts >= MAX_LOGIN_ATTEMPTS:
            locked_until = (utcnow() + timedelta(minutes=LOGIN_LOCK_MINUTES)).isoformat()

        connection.execute(
            """
            INSERT INTO login_attempts(username, ip_address, failed_attempts, locked_until, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(username, ip_address) DO UPDATE SET
                failed_attempts = excluded.failed_attempts,
                locked_until = excluded.locked_until,
                updated_at = excluded.updated_at
            """,
            (normalized_username, ip_address, failed_attempts, locked_until, utcnow_iso()),
        )
        connection.commit()

    remaining_attempts = max(0, MAX_LOGIN_ATTEMPTS - failed_attempts)
    if remaining_attempts == 0:
        message = "Попытки входа закончились. Вход заблокирован на 15 минут."
    else:
        message = f"Неверный логин или пароль. Осталось попыток: {remaining_attempts}."

    return {
        "success": False,
        "message": message,
        "remaining_attempts": remaining_attempts,
        "admin": None,
    }


def get_admin_by_id(admin_id: int) -> dict[str, Any] | None:
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT id, username FROM admins WHERE id = ? AND is_active = 1 LIMIT 1",
            (admin_id,),
        ).fetchone()

    if not row:
        return None
    return {"id": row["id"], "username": row["username"]}


def _is_sqlite_lock_error(error: sqlite3.OperationalError) -> bool:
    message = str(error).lower()
    return "locked" in message or "busy" in message


def _sanitize_path(value: str) -> str:
    path = str(value or "").strip()
    return (path or "/")[:500]


def _sanitize_referrer(value: str, *, site_host: str = "") -> str:
    referrer = str(value or "").strip()
    if not referrer:
        return ""
    try:
        parsed = urlsplit(referrer)
    except ValueError:
        return ""
    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        return ""
    if parsed.netloc:
        hostname = parsed.hostname or ""
        if not hostname:
            return ""
        normalized_site_host = str(site_host or "").split(":", 1)[0].lower().removeprefix("www.")
        if normalized_site_host and hostname.lower().removeprefix("www.") == normalized_site_host:
            return ""
        try:
            port = parsed.port
        except ValueError:
            port = None
        netloc = f"{hostname}:{port}" if port else hostname
        cleaned = urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", "", ""))
    else:
        cleaned = parsed.path or ""
    return cleaned[:500]


def _normalize_customer_id(customer_id: int | str | None) -> int | None:
    try:
        normalized = int(customer_id) if customer_id not in {None, ""} else None
    except (TypeError, ValueError):
        return None
    return normalized if normalized and normalized > 0 else None


def log_visit(
    path: str,
    remote_addr: str = "",
    user_agent: str = "",
    *,
    visitor_id: str = "",
    customer_id: int | str | None = None,
    referrer: str = "",
    site_host: str = "",
) -> None:
    """Persist a page view without ever exposing storage errors to the public request."""
    for attempt in range(2):
        try:
            with _get_connection(timeout_seconds=0.35) as connection:
                salt = _ensure_visitor_salt(connection)
                privacy_safe_id = _build_visitor_id(
                    salt=salt,
                    visitor_id=visitor_id,
                    remote_addr=str(remote_addr or ""),
                    user_agent=str(user_agent or ""),
                )
                connection.execute(
                    """
                    INSERT INTO visit_events(
                        path,
                        remote_addr,
                        user_agent,
                        visitor_id,
                        customer_id,
                        referrer,
                        visited_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _sanitize_path(path),
                        _mask_ip(remote_addr),
                        str(user_agent or "")[:320],
                        privacy_safe_id,
                        _normalize_customer_id(customer_id),
                        _sanitize_referrer(referrer, site_host=site_host),
                        utcnow_iso(),
                    ),
                )
                connection.commit()
            return
        except sqlite3.OperationalError as error:
            if not _is_sqlite_lock_error(error):
                raise
            if attempt == 0:
                time.sleep(0.025)


def _count_form_submissions() -> int:
    target = FORMS_ROOT / "elementor_forms.jsonl"
    if not target.exists():
        return 0

    with target.open("r", encoding="utf-8") as stream:
        return sum(1 for _ in stream)


def _mask_ip(value: str | None) -> str:
    raw_value = str(value or "").strip().split("%", 1)[0]
    if not raw_value:
        return "—"
    if "×" in raw_value or raw_value.endswith(":…"):
        return raw_value[:64]
    try:
        address = ipaddress.ip_address(raw_value)
    except ValueError:
        return "—"
    if isinstance(address, ipaddress.IPv4Address):
        first, second, *_ = str(address).split(".")
        return f"{first}.{second}.×.×"
    hextets = address.exploded.split(":")
    return f"{hextets[0]}:{hextets[1]}:…"


def _visitor_display_id(visitor_id: str | None) -> str:
    normalized = str(visitor_id or "").removeprefix("v1_")
    return f"VIS-{normalized[:8].upper()}" if normalized else "VIS-UNKNOWN"


def _parse_user_agent(value: str | None) -> dict[str, str]:
    user_agent = str(value or "")
    lowered = user_agent.lower()

    if any(marker in lowered for marker in ("bot", "crawler", "spider", "slurp")):
        return {"browser": "Робот", "device": "Сканер / бот"}

    if "edg/" in lowered:
        browser = "Edge"
    elif "opr/" in lowered or "opera" in lowered:
        browser = "Opera"
    elif "firefox/" in lowered or "fxios/" in lowered:
        browser = "Firefox"
    elif "crios/" in lowered or "chrome/" in lowered:
        browser = "Chrome"
    elif "safari/" in lowered:
        browser = "Safari"
    else:
        browser = "Другой браузер" if user_agent else "Не определён"

    if "ipad" in lowered or ("android" in lowered and "mobile" not in lowered):
        device = "Планшет"
    elif "iphone" in lowered:
        device = "iPhone"
    elif "android" in lowered and "mobile" in lowered:
        device = "Android-смартфон"
    elif "windows" in lowered:
        device = "Компьютер · Windows"
    elif "macintosh" in lowered or "mac os x" in lowered:
        device = "Компьютер · macOS"
    elif "linux" in lowered:
        device = "Компьютер · Linux"
    else:
        device = "Устройство не определено"

    return {"browser": browser, "device": device}


def _format_admin_datetime(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local_value = parsed.astimezone(ADMIN_LOCAL_TIMEZONE)
    return local_value.strftime("%d.%m.%Y, %H:%M")


def _format_referrer(value: str | None) -> str:
    cleaned = _sanitize_referrer(str(value or ""))
    if not cleaned:
        return "Прямой заход"
    parsed = urlsplit(cleaned)
    if parsed.netloc:
        label = f"{parsed.netloc}{parsed.path if parsed.path != '/' else ''}"
    else:
        label = parsed.path
    return label if len(label) <= 90 else f"{label[:87]}…"


def _empty_dashboard_visit_stats() -> dict[str, Any]:
    return {
        "total_page_views": 0,
        "unique_visitors": 0,
        "today_page_views": 0,
        "today_unique_visitors": 0,
        "top_pages": [],
        "recent_visits": [],
    }


def get_dashboard_stats() -> dict[str, Any]:
    day_start = _local_day_start_utc_iso()

    visit_stats = _empty_dashboard_visit_stats()
    try:
        with _get_connection() as connection:
            visit_stats["total_page_views"] = connection.execute(
                "SELECT COUNT(*) FROM visit_events"
            ).fetchone()[0]
            visit_stats["unique_visitors"] = connection.execute(
                """
                SELECT COUNT(DISTINCT NULLIF(visitor_id, ''))
                FROM visit_events
                """
            ).fetchone()[0]
            visit_stats["today_page_views"] = connection.execute(
                "SELECT COUNT(*) FROM visit_events WHERE visited_at >= ?",
                (day_start,),
            ).fetchone()[0]
            visit_stats["today_unique_visitors"] = connection.execute(
                """
                SELECT COUNT(DISTINCT NULLIF(visitor_id, ''))
                FROM visit_events
                WHERE visited_at >= ?
                """,
                (day_start,),
            ).fetchone()[0]
            top_pages_rows = connection.execute(
                """
                SELECT path, COUNT(*) AS visit_count
                FROM visit_events
                GROUP BY path
                ORDER BY visit_count DESC, path ASC
                LIMIT 8
                """
            ).fetchall()
            recent_visits_rows = connection.execute(
                """
                SELECT path, remote_addr, visitor_id, visited_at
                FROM visit_events
                ORDER BY visited_at DESC, id DESC
                LIMIT 10
                """
            ).fetchall()
            visit_stats["top_pages"] = [
                {"path": row["path"], "visit_count": row["visit_count"]}
                for row in top_pages_rows
            ]
            visit_stats["recent_visits"] = [
                {
                    "path": row["path"],
                    "visitor": _visitor_display_id(row["visitor_id"]),
                    "masked_ip": _mask_ip(row["remote_addr"]),
                    "visited_at": _format_admin_datetime(row["visited_at"]),
                }
                for row in recent_visits_rows
            ]
    except sqlite3.OperationalError as error:
        if not _is_sqlite_lock_error(error):
            raise

    try:
        catalog_counts = get_catalog_summary()
    except sqlite3.OperationalError as error:
        if not _is_sqlite_lock_error(error):
            raise
        catalog_counts = {"character": 0, "category": 0, "tag": 0}

    return {
        **visit_stats,
        "form_submissions": _count_form_submissions(),
        "catalog_counts": catalog_counts,
        "latest_catalog_sync": None,
    }


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _empty_visitor_report(*, page: int, per_page: int, unavailable: bool = False) -> dict[str, Any]:
    return {
        "items": [],
        "summary": {
            "visitors": 0,
            "sessions": 0,
            "page_views": 0,
            "today": 0,
            "identified": 0,
        },
        "pagination": {
            "page": page,
            "pages": 1,
            "per_page": per_page,
            "total": 0,
            "has_previous": False,
            "has_next": False,
        },
        "unavailable": unavailable,
    }


def list_admin_visitors(search: str = "", page: int = 1, per_page: int = 30) -> dict[str, Any]:
    normalized_page = max(1, int(page or 1))
    normalized_per_page = max(1, min(100, int(per_page or 30)))
    normalized_search = str(search or "").strip()[:120]
    searchable_id = normalized_search.removeprefix("VIS-").removeprefix("vis-")
    day_start = _local_day_start_utc_iso()

    visitor_cte = """
        WITH visits AS (
            SELECT
                id,
                path,
                remote_addr,
                user_agent,
                visited_at,
                customer_id,
                referrer,
                CASE
                    WHEN visitor_id IS NOT NULL AND visitor_id != '' THEN visitor_id
                    ELSE printf('legacy_%d', id)
                END AS visitor_key
            FROM visit_events
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY visitor_key ORDER BY visited_at ASC, id ASC
                ) AS first_rank,
                ROW_NUMBER() OVER (
                    PARTITION BY visitor_key ORDER BY visited_at DESC, id DESC
                ) AS last_rank,
                LAG(visited_at) OVER (
                    PARTITION BY visitor_key ORDER BY visited_at ASC, id ASC
                ) AS previous_visit
            FROM visits
        ),
        first_referrers AS (
            SELECT visitor_key, referrer
            FROM (
                SELECT
                    visitor_key,
                    referrer,
                    ROW_NUMBER() OVER (
                        PARTITION BY visitor_key ORDER BY visited_at ASC, id ASC
                    ) AS referrer_rank
                FROM visits
                WHERE referrer IS NOT NULL AND referrer != ''
            )
            WHERE referrer_rank = 1
        ),
        latest_customers AS (
            SELECT visitor_key, customer_id
            FROM (
                SELECT
                    visitor_key,
                    customer_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY visitor_key ORDER BY visited_at DESC, id DESC
                    ) AS customer_rank
                FROM visits
                WHERE customer_id IS NOT NULL
            )
            WHERE customer_rank = 1
        ),
        aggregated AS (
            SELECT
                ranked.visitor_key,
                COUNT(*) AS page_views,
                SUM(
                    CASE
                        WHEN previous_visit IS NULL
                            OR (julianday(visited_at) - julianday(previous_visit)) * 1440.0 >= ?
                        THEN 1 ELSE 0
                    END
                ) AS session_count,
                MIN(visited_at) AS first_seen,
                MAX(visited_at) AS last_seen,
                MAX(CASE WHEN first_rank = 1 THEN path END) AS first_path,
                MAX(CASE WHEN last_rank = 1 THEN path END) AS last_path,
                MAX(CASE WHEN last_rank = 1 THEN remote_addr END) AS latest_remote_addr,
                MAX(CASE WHEN last_rank = 1 THEN user_agent END) AS latest_user_agent,
                first_referrers.referrer AS first_referrer,
                latest_customers.customer_id AS customer_id
            FROM ranked
            LEFT JOIN first_referrers
                ON first_referrers.visitor_key = ranked.visitor_key
            LEFT JOIN latest_customers
                ON latest_customers.visitor_key = ranked.visitor_key
            GROUP BY ranked.visitor_key
        )
    """

    try:
        with _get_connection() as connection:
            has_customer_accounts = _table_exists(connection, "customer_accounts")
            connection.execute(
                "CREATE TEMP TABLE admin_visitor_report AS "
                + visitor_cte
                + "SELECT * FROM aggregated",
                (VISITOR_SESSION_TIMEOUT_MINUTES,),
            )
            if has_customer_accounts:
                account_columns = """
                    ca.id AS linked_customer_id,
                    ca.full_name AS customer_name,
                    ca.phone_display AS customer_phone
                """
                account_join = "LEFT JOIN customer_accounts AS ca ON ca.id = report.customer_id"
                identified_expression = "SUM(CASE WHEN ca.id IS NOT NULL THEN 1 ELSE 0 END)"
            else:
                account_columns = """
                    NULL AS linked_customer_id,
                    NULL AS customer_name,
                    NULL AS customer_phone
                """
                account_join = ""
                identified_expression = "0"

            summary_row = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS visitors,
                    COALESCE(SUM(report.session_count), 0) AS sessions,
                    COALESCE(SUM(report.page_views), 0) AS page_views,
                    COALESCE(SUM(CASE WHEN report.last_seen >= ? THEN 1 ELSE 0 END), 0) AS today,
                    COALESCE({identified_expression}, 0) AS identified
                FROM admin_visitor_report AS report
                {account_join}
                """,
                (day_start,),
            ).fetchone()

            search_clauses: list[str] = []
            search_params: list[str] = []
            if normalized_search:
                like_value = f"%{normalized_search}%"
                id_like_value = f"%{searchable_id}%"
                search_clauses.extend(
                    [
                        "report.visitor_key LIKE ?",
                        "report.first_path LIKE ?",
                        "report.last_path LIKE ?",
                        "report.first_referrer LIKE ?",
                        "report.latest_user_agent LIKE ?",
                    ]
                )
                search_params.extend([id_like_value, like_value, like_value, like_value, like_value])
                if has_customer_accounts:
                    search_clauses.extend(["ca.full_name LIKE ?", "ca.phone_display LIKE ?"])
                    search_params.extend([like_value, like_value])
            search_sql = f"WHERE {' OR '.join(search_clauses)}" if search_clauses else ""

            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM admin_visitor_report AS report
                    {account_join}
                    {search_sql}
                    """,
                    search_params,
                ).fetchone()[0]
            )
            pages = max(1, math.ceil(total / normalized_per_page))
            normalized_page = min(normalized_page, pages)
            offset = (normalized_page - 1) * normalized_per_page

            rows = connection.execute(
                f"""
                SELECT
                    report.*,
                    {account_columns}
                FROM admin_visitor_report AS report
                {account_join}
                {search_sql}
                ORDER BY report.last_seen DESC, report.visitor_key ASC
                LIMIT ? OFFSET ?
                """,
                [
                    *search_params,
                    normalized_per_page,
                    offset,
                ],
            ).fetchall()
    except sqlite3.OperationalError as error:
        if not _is_sqlite_lock_error(error):
            raise
        return _empty_visitor_report(
            page=normalized_page,
            per_page=normalized_per_page,
            unavailable=True,
        )

    items: list[dict[str, Any]] = []
    for row in rows:
        environment = _parse_user_agent(row["latest_user_agent"])
        linked_customer_id = row["linked_customer_id"]
        customer = None
        if linked_customer_id is not None:
            customer = {
                "id": int(linked_customer_id),
                "name": str(row["customer_name"] or ""),
                "phone": str(row["customer_phone"] or ""),
            }
        items.append(
            {
                "display_id": _visitor_display_id(row["visitor_key"]),
                "first_seen": str(row["first_seen"] or ""),
                "first_seen_label": _format_admin_datetime(row["first_seen"]),
                "last_seen": str(row["last_seen"] or ""),
                "last_seen_label": _format_admin_datetime(row["last_seen"]),
                "page_views": int(row["page_views"] or 0),
                "sessions": int(row["session_count"] or 0),
                "first_path": str(row["first_path"] or "/"),
                "last_path": str(row["last_path"] or "/"),
                "referrer": _format_referrer(row["first_referrer"]),
                "has_referrer": bool(row["first_referrer"]),
                "masked_ip": _mask_ip(row["latest_remote_addr"]),
                "browser": environment["browser"],
                "device": environment["device"],
                "customer": customer,
            }
        )

    return {
        "items": items,
        "summary": {
            "visitors": int(summary_row["visitors"] or 0),
            "sessions": int(summary_row["sessions"] or 0),
            "page_views": int(summary_row["page_views"] or 0),
            "today": int(summary_row["today"] or 0),
            "identified": int(summary_row["identified"] or 0),
        },
        "pagination": {
            "page": normalized_page,
            "pages": pages,
            "per_page": normalized_per_page,
            "total": total,
            "has_previous": normalized_page > 1,
            "has_next": normalized_page < pages,
        },
        "unavailable": False,
    }


def get_popular_programs(limit: int = 5) -> list[dict[str, Any]]:
    """Top programs by number of non-cancelled orders."""
    if not DB_PATH.exists():
        return []
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT program_name_snapshot AS name, program_slug AS slug, COUNT(*) AS order_count
            FROM party_orders
            WHERE status != 'cancelled' AND program_name_snapshot != ''
            GROUP BY program_slug, program_name_snapshot
            ORDER BY order_count DESC, name ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [{"name": r["name"], "slug": r["slug"], "order_count": r["order_count"]} for r in rows]


def get_popular_characters(limit: int = 5) -> list[dict[str, Any]]:
    """Top characters by number of non-cancelled orders they appeared in."""
    if not DB_PATH.exists():
        return []
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT poc.name_snapshot AS name, poc.slug, COUNT(DISTINCT poc.order_id) AS order_count
            FROM party_order_characters poc
            JOIN party_orders po ON po.id = poc.order_id
            WHERE po.status != 'cancelled' AND poc.name_snapshot != ''
            GROUP BY poc.slug, poc.name_snapshot
            ORDER BY order_count DESC, name ASC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    return [{"name": r["name"], "slug": r["slug"], "order_count": r["order_count"]} for r in rows]


def get_revenue_stats() -> dict[str, Any]:
    """Totals for confirmed orders, plus the same figures limited to today.

    The dashboard's "сегодня" panel used the all-time count, so two confirmed
    test orders from May and June read as today's activity.
    """
    empty = {"total": 0, "count": 0, "avg": 0, "today_count": 0, "today_total": 0}
    if not DB_PATH.exists():
        return empty
    with _get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS order_count,
                COALESCE(SUM(total_price_snapshot), 0) AS total_revenue,
                COALESCE(AVG(total_price_snapshot), 0) AS avg_revenue
            FROM party_orders
            WHERE confirmation_state = 'confirmed' AND total_price_snapshot > 0
            """
        ).fetchone()
        today = connection.execute(
            """
            SELECT
                COUNT(*) AS order_count,
                COALESCE(SUM(total_price_snapshot), 0) AS total_revenue
            FROM party_orders
            WHERE confirmation_state = 'confirmed'
              AND total_price_snapshot > 0
              AND date(created_at) = date('now', 'localtime')
            """
        ).fetchone()
    return {
        "total": int(row["total_revenue"] or 0),
        "count": int(row["order_count"] or 0),
        "avg": int(row["avg_revenue"] or 0),
        "today_count": int(today["order_count"] or 0),
        "today_total": int(today["total_revenue"] or 0),
    }


def get_customer_list() -> list[dict[str, Any]]:
    """All customers with aggregated order stats."""
    if not DB_PATH.exists():
        return []
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                ca.id,
                ca.phone_display,
                ca.full_name,
                ca.created_at,
                ca.is_blocked,
                ca.blocked_until,
                ca.block_reason,
                COUNT(po.id) AS order_count,
                COALESCE(SUM(CASE WHEN po.confirmation_state = 'confirmed' THEN po.total_price_snapshot ELSE 0 END), 0) AS total_spent,
                MAX(po.created_at) AS last_order_at,
                SUM(CASE WHEN po.status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled_count
            FROM customer_accounts ca
            LEFT JOIN party_orders po ON po.customer_id = ca.id
            GROUP BY ca.id
            ORDER BY last_order_at DESC NULLS LAST, ca.created_at DESC
            """
        ).fetchall()
    return [
        {
            "id": r["id"],
            "phone": r["phone_display"],
            "name": r["full_name"] or "",
            "order_count": r["order_count"] or 0,
            "total_spent": r["total_spent"] or 0,
            "cancelled_count": r["cancelled_count"] or 0,
            "last_order_at": r["last_order_at"] or "",
            "created_at": r["created_at"],
            "is_blocked": bool(r["is_blocked"]),
            "blocked_until": r["blocked_until"] or "",
            "block_reason": r["block_reason"] or "",
        }
        for r in rows
    ]


def unblock_customer(customer_id: int) -> bool:
    """Manually lift a block from a customer account."""
    if not DB_PATH.exists():
        return False
    with _get_connection() as connection:
        result = connection.execute(
            "UPDATE customer_accounts SET is_blocked=0, blocked_until=NULL, block_reason='', updated_at=? WHERE id=?",
            (utcnow_iso(), int(customer_id)),
        )
        connection.commit()
    return result.rowcount > 0


def list_catalog_entities(kind: str | None = None, search: str = "") -> list[dict[str, Any]]:
    query = """
        SELECT id, kind, slug, route, title, source_path, synced_at
        FROM catalog_entities
    """
    clauses: list[str] = []
    params: list[str] = []

    if kind:
        clauses.append("kind = ?")
        params.append(kind)

    normalized_search = search.strip()
    if normalized_search:
        clauses.append("(title LIKE ? OR slug LIKE ? OR route LIKE ?)")
        like_value = f"%{normalized_search}%"
        params.extend([like_value, like_value, like_value])

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY kind ASC, title COLLATE NOCASE ASC"

    with _get_connection() as connection:
        rows = connection.execute(query, params).fetchall()

    return [
        {
            "id": row["id"],
            "kind": row["kind"],
            "slug": row["slug"],
            "route": row["route"],
            "title": row["title"],
            "source_path": row["source_path"],
            "synced_at": row["synced_at"],
        }
        for row in rows
    ]
