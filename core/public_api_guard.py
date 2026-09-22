from __future__ import annotations

import hashlib
import ipaddress
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import NamedTuple

from .config import DATA_ROOT


DB_ROOT = DATA_ROOT / "admin"
DB_PATH = DB_ROOT / "site_admin.sqlite3"

_TABLE_NAME = "public_api_request_events"
_DEFAULT_BUSY_TIMEOUT_MS = 5_000
_DEFAULT_CLEANUP_BATCH_SIZE = 500
_MAX_BUCKET_BYTES = 256


class PublicAPIRequestDecision(NamedTuple):
    allowed: bool
    retry_after: int


def _environment_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


def _positive_int(name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _bucket_key(bucket: str) -> str:
    if not isinstance(bucket, str):
        raise ValueError("bucket must be a string")
    normalized = bucket.strip()
    if not normalized:
        raise ValueError("bucket cannot be empty")
    if len(normalized.encode("utf-8")) > _MAX_BUCKET_BYTES:
        raise ValueError(f"bucket cannot exceed {_MAX_BUCKET_BYTES} UTF-8 bytes")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError("bucket cannot contain control characters")
    return _identifier_key("bucket", normalized)


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
    return _identifier_key("client-ip", canonical_ip)


def _identifier_key(namespace: str, value: str) -> str:
    return hashlib.sha256(f"public-api-guard\0{namespace}\0{value}".encode("utf-8")).hexdigest()


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    busy_timeout_ms = _environment_int(
        "PUBLIC_API_GUARD_DB_BUSY_TIMEOUT_MS",
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


def _retry_after(oldest_timestamp: float, window_seconds: int, now: float) -> int:
    return max(1, math.ceil(oldest_timestamp + window_seconds - now))


class PublicAPIRequestLimiter:
    def __init__(
        self,
        db_path: str | Path = DB_PATH,
        *,
        cleanup_batch_size: int | None = None,
    ) -> None:
        self.db_path = Path(db_path)
        configured_batch_size = (
            _environment_int(
                "PUBLIC_API_GUARD_CLEANUP_BATCH_SIZE",
                _DEFAULT_CLEANUP_BATCH_SIZE,
            )
            if cleanup_batch_size is None
            else cleanup_batch_size
        )
        self.cleanup_batch_size = _positive_int("cleanup_batch_size", configured_batch_size)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        connection = _connect(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bucket_key TEXT NOT NULL,
                    ip_key TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_public_api_request_bucket_ip_created
                ON {_TABLE_NAME}(bucket_key, ip_key, created_at)
                """
            )
            connection.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_public_api_request_bucket_created
                ON {_TABLE_NAME}(bucket_key, created_at)
                """
            )
            connection.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_public_api_request_expires
                ON {_TABLE_NAME}(expires_at)
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
        bucket: str,
        client_ip: str | None,
        per_ip_limit: int,
        global_limit: int,
        window_seconds: int,
        *,
        now: float | None = None,
    ) -> PublicAPIRequestDecision:
        bucket_identifier = _bucket_key(bucket)
        ip_identifier = _ip_key(client_ip)
        per_ip_limit = _positive_int("per_ip_limit", per_ip_limit)
        global_limit = _positive_int("global_limit", global_limit)
        window_seconds = _positive_int("window_seconds", window_seconds)
        timestamp = time.time() if now is None else float(now)
        if not math.isfinite(timestamp):
            raise ValueError("now must be a finite Unix timestamp")

        window_start = timestamp - window_seconds
        connection = _connect(self.db_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                f"""
                DELETE FROM {_TABLE_NAME}
                WHERE id IN (
                    SELECT id
                    FROM {_TABLE_NAME}
                    WHERE expires_at <= ?
                    ORDER BY expires_at, id
                    LIMIT ?
                )
                """,
                (timestamp, self.cleanup_batch_size),
            )

            retry_after_values: list[int] = []
            ip_count, oldest_ip_event = connection.execute(
                f"""
                SELECT COUNT(*), MIN(created_at)
                FROM {_TABLE_NAME}
                WHERE bucket_key = ? AND ip_key = ? AND created_at > ?
                """,
                (bucket_identifier, ip_identifier, window_start),
            ).fetchone()
            if int(ip_count) >= per_ip_limit:
                retry_after_values.append(
                    _retry_after(float(oldest_ip_event), window_seconds, timestamp)
                )

            global_count, oldest_global_event = connection.execute(
                f"""
                SELECT COUNT(*), MIN(created_at)
                FROM {_TABLE_NAME}
                WHERE bucket_key = ? AND created_at > ?
                """,
                (bucket_identifier, window_start),
            ).fetchone()
            if int(global_count) >= global_limit:
                retry_after_values.append(
                    _retry_after(float(oldest_global_event), window_seconds, timestamp)
                )

            if retry_after_values:
                connection.commit()
                return PublicAPIRequestDecision(False, max(retry_after_values))

            connection.execute(
                f"""
                INSERT INTO {_TABLE_NAME}(bucket_key, ip_key, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    bucket_identifier,
                    ip_identifier,
                    timestamp,
                    timestamp + window_seconds,
                ),
            )
            connection.commit()
            return PublicAPIRequestDecision(True, 0)
        except Exception:
            _rollback(connection)
            raise
        finally:
            connection.close()


def consume_public_api_request(
    bucket: str,
    client_ip: str | None,
    per_ip_limit: int,
    global_limit: int,
    window_seconds: int,
    *,
    db_path: str | Path | None = None,
    cleanup_batch_size: int | None = None,
    now: float | None = None,
) -> PublicAPIRequestDecision:
    limiter = PublicAPIRequestLimiter(
        DB_PATH if db_path is None else db_path,
        cleanup_batch_size=cleanup_batch_size,
    )
    return limiter.consume(
        bucket,
        client_ip,
        per_ip_limit,
        global_limit,
        window_seconds,
        now=now,
    )
