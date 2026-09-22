from __future__ import annotations

import hashlib
import ipaddress
import math
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from .config import DATA_ROOT


DB_ROOT = DATA_ROOT / "admin"
DB_PATH = DB_ROOT / "site_admin.sqlite3"

_TABLE_NAME = "telegram_otp_send_events"
_DEFAULT_PHONE_LIMIT = 3
_DEFAULT_PHONE_WINDOW_SECONDS = 600
_DEFAULT_IP_LIMIT = 10
_DEFAULT_IP_WINDOW_SECONDS = 600
_DEFAULT_GLOBAL_LIMIT = 30
_DEFAULT_GLOBAL_WINDOW_SECONDS = 60
_DEFAULT_RESEND_COOLDOWN_SECONDS = 60
_DEFAULT_CLEANUP_BATCH_SIZE = 500
_DEFAULT_BUSY_TIMEOUT_MS = 5_000


def _environment_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


@dataclass(frozen=True, slots=True)
class TelegramOTPRateLimitPolicy:
    phone_limit: int = _DEFAULT_PHONE_LIMIT
    phone_window_seconds: int = _DEFAULT_PHONE_WINDOW_SECONDS
    ip_limit: int = _DEFAULT_IP_LIMIT
    ip_window_seconds: int = _DEFAULT_IP_WINDOW_SECONDS
    global_limit: int = _DEFAULT_GLOBAL_LIMIT
    global_window_seconds: int = _DEFAULT_GLOBAL_WINDOW_SECONDS
    resend_cooldown_seconds: int = _DEFAULT_RESEND_COOLDOWN_SECONDS
    cleanup_batch_size: int = _DEFAULT_CLEANUP_BATCH_SIZE

    def __post_init__(self) -> None:
        positive_fields = (
            "phone_limit",
            "phone_window_seconds",
            "ip_limit",
            "ip_window_seconds",
            "global_limit",
            "global_window_seconds",
            "cleanup_batch_size",
        )
        for field_name in positive_fields:
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be greater than zero")
        if self.resend_cooldown_seconds < 0:
            raise ValueError("resend_cooldown_seconds cannot be negative")

    @classmethod
    def from_environment(cls) -> TelegramOTPRateLimitPolicy:
        return cls(
            phone_limit=_environment_int("TELEGRAM_OTP_PHONE_LIMIT", _DEFAULT_PHONE_LIMIT),
            phone_window_seconds=_environment_int(
                "TELEGRAM_OTP_PHONE_WINDOW_SECONDS",
                _DEFAULT_PHONE_WINDOW_SECONDS,
            ),
            ip_limit=_environment_int("TELEGRAM_OTP_IP_LIMIT", _DEFAULT_IP_LIMIT),
            ip_window_seconds=_environment_int(
                "TELEGRAM_OTP_IP_WINDOW_SECONDS",
                _DEFAULT_IP_WINDOW_SECONDS,
            ),
            global_limit=_environment_int("TELEGRAM_OTP_GLOBAL_LIMIT", _DEFAULT_GLOBAL_LIMIT),
            global_window_seconds=_environment_int(
                "TELEGRAM_OTP_GLOBAL_WINDOW_SECONDS",
                _DEFAULT_GLOBAL_WINDOW_SECONDS,
            ),
            resend_cooldown_seconds=_environment_int(
                "TELEGRAM_OTP_RESEND_COOLDOWN_SECONDS",
                _DEFAULT_RESEND_COOLDOWN_SECONDS,
                minimum=0,
            ),
            cleanup_batch_size=_environment_int(
                "TELEGRAM_OTP_CLEANUP_BATCH_SIZE",
                _DEFAULT_CLEANUP_BATCH_SIZE,
            ),
        )


class RateLimitDecision(NamedTuple):
    allowed: bool
    retry_after: int


def _identifier_key(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def _phone_key(phone_e164: str) -> str:
    digits = "".join(character for character in str(phone_e164) if character in "0123456789")
    if not 8 <= len(digits) <= 15:
        raise ValueError("phone_e164 must contain between 8 and 15 digits")
    return _identifier_key("phone", digits)


def _ip_key(client_ip: str | None) -> str:
    raw_ip = str(client_ip or "").strip()
    try:
        address = ipaddress.ip_address(raw_ip.split("%", 1)[0])
    except ValueError:
        canonical_ip = "unknown"
    else:
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        canonical_ip = address.compressed
    return _identifier_key("ip", canonical_ip)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    busy_timeout_ms = _environment_int(
        "TELEGRAM_OTP_DB_BUSY_TIMEOUT_MS",
        _DEFAULT_BUSY_TIMEOUT_MS,
    )
    connection = sqlite3.connect(
        db_path,
        timeout=busy_timeout_ms / 1_000,
        isolation_level=None,
    )
    connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
    return connection


def _rollback(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.rollback()


class TelegramOTPRateLimiter:
    def __init__(
        self,
        db_path: str | Path = DB_PATH,
        *,
        policy: TelegramOTPRateLimitPolicy | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        self.policy = policy or TelegramOTPRateLimitPolicy.from_environment()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        connection = _connect(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_key TEXT NOT NULL,
                    ip_key TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_telegram_otp_phone_created
                ON {_TABLE_NAME}(phone_key, created_at)
                """
            )
            connection.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_telegram_otp_ip_created
                ON {_TABLE_NAME}(ip_key, created_at)
                """
            )
            connection.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_telegram_otp_created
                ON {_TABLE_NAME}(created_at)
                """
            )
            connection.commit()
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()

    def consume(
        self,
        phone_e164: str,
        client_ip: str | None,
        *,
        now: float | None = None,
    ) -> RateLimitDecision:
        timestamp = time.time() if now is None else float(now)
        if not math.isfinite(timestamp):
            raise ValueError("now must be a finite Unix timestamp")

        phone_key = _phone_key(phone_e164)
        ip_key = _ip_key(client_ip)
        policy = self.policy
        retention_seconds = max(
            policy.phone_window_seconds,
            policy.ip_window_seconds,
            policy.global_window_seconds,
            policy.resend_cooldown_seconds,
        )

        connection = _connect(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"""
                DELETE FROM {_TABLE_NAME}
                WHERE id IN (
                    SELECT id
                    FROM {_TABLE_NAME}
                    WHERE created_at <= ?
                    ORDER BY created_at, id
                    LIMIT ?
                )
                """,
                (timestamp - retention_seconds, policy.cleanup_batch_size),
            )

            retry_after_values: list[int] = []

            if policy.resend_cooldown_seconds:
                latest_phone_event = connection.execute(
                    f"""
                    SELECT MAX(created_at)
                    FROM {_TABLE_NAME}
                    WHERE phone_key = ? AND created_at > ?
                    """,
                    (phone_key, timestamp - policy.resend_cooldown_seconds),
                ).fetchone()[0]
                if latest_phone_event is not None:
                    retry_after_values.append(
                        _retry_after(
                            float(latest_phone_event),
                            policy.resend_cooldown_seconds,
                            timestamp,
                        )
                    )

            phone_count, oldest_phone_event = connection.execute(
                f"""
                SELECT COUNT(*), MIN(created_at)
                FROM {_TABLE_NAME}
                WHERE phone_key = ? AND created_at > ?
                """,
                (phone_key, timestamp - policy.phone_window_seconds),
            ).fetchone()
            if int(phone_count) >= policy.phone_limit:
                retry_after_values.append(
                    _retry_after(
                        float(oldest_phone_event),
                        policy.phone_window_seconds,
                        timestamp,
                    )
                )

            ip_count, oldest_ip_event = connection.execute(
                f"""
                SELECT COUNT(*), MIN(created_at)
                FROM {_TABLE_NAME}
                WHERE ip_key = ? AND created_at > ?
                """,
                (ip_key, timestamp - policy.ip_window_seconds),
            ).fetchone()
            if int(ip_count) >= policy.ip_limit:
                retry_after_values.append(
                    _retry_after(
                        float(oldest_ip_event),
                        policy.ip_window_seconds,
                        timestamp,
                    )
                )

            global_count, oldest_global_event = connection.execute(
                f"""
                SELECT COUNT(*), MIN(created_at)
                FROM {_TABLE_NAME}
                WHERE created_at > ?
                """,
                (timestamp - policy.global_window_seconds,),
            ).fetchone()
            if int(global_count) >= policy.global_limit:
                retry_after_values.append(
                    _retry_after(
                        float(oldest_global_event),
                        policy.global_window_seconds,
                        timestamp,
                    )
                )

            if retry_after_values:
                connection.commit()
                return RateLimitDecision(False, max(retry_after_values))

            connection.execute(
                f"""
                INSERT INTO {_TABLE_NAME}(phone_key, ip_key, created_at)
                VALUES (?, ?, ?)
                """,
                (phone_key, ip_key, timestamp),
            )
            connection.commit()
            return RateLimitDecision(True, 0)
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()


def _retry_after(oldest_timestamp: float, window_seconds: int, now: float) -> int:
    return max(1, math.ceil(oldest_timestamp + window_seconds - now))


def consume_telegram_otp_send(
    phone_e164: str,
    client_ip: str | None,
    *,
    db_path: str | Path | None = None,
    policy: TelegramOTPRateLimitPolicy | None = None,
    now: float | None = None,
) -> RateLimitDecision:
    limiter = TelegramOTPRateLimiter(
        DB_PATH if db_path is None else db_path,
        policy=policy,
    )
    return limiter.consume(phone_e164, client_ip, now=now)
