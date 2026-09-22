"""Wipe customer-facing data so the site starts from a clean slate.

Removes visitor statistics, customer accounts and every order. Keeps the
catalog, media, partners, curated ordering, site settings, admin accounts and
Telegram configuration — everything an admin set up stays in place.

Run with --dry-run first; it prints what would go. Nothing is deleted without
--apply, and --apply refuses to run unless a backup path is given.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.catalog_store import DB_PATH  # noqa: E402

#: Emptied completely. Order matters only for readability — foreign keys are off
#: for this connection, and every table here is customer data.
CUSTOMER_TABLES = (
    "party_order_addons",
    "party_order_characters",
    "party_order_confirmation_events",
    "party_orders",
    "customer_accounts",
    "visit_events",
    "login_attempts",
    "public_api_request_events",
    "telegram_otp_send_events",
    "admin_telegram_order_messages",
    "admin_telegram_delivery_queue",
    "admin_telegram_sync_queue",
    "admin_telegram_sync_dead_letters",
    "admin_telegram_processed_updates",
)

#: Never touched, listed so the intent is auditable.
PRESERVED = (
    "managed_characters",
    "managed_character_media",
    "managed_categories",
    "managed_tags",
    "managed_partners",
    "managed_meta",
    "site_settings",
    "admins",
    "admin_telegram_settings",
    "admin_telegram_recipients",
    "show_addons",
    "show_program_addons",
    "managed_character_categories",
    "managed_character_tags",
)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table,),
    ).fetchone()
    return row is not None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="actually delete the rows")
    parser.add_argument("--backup", type=Path, help="where to write the pre-wipe SQLite copy (required with --apply)")
    parser.add_argument("--database", type=Path, default=DB_PATH)
    args = parser.parse_args()

    database = args.database
    if not database.exists():
        print(f"Базы нет: {database}")
        return 1

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row

    print(f"База: {database}")
    print(f"{'таблица':<40}{'строк':>10}")
    total = 0
    counts: dict[str, int] = {}
    for table in CUSTOMER_TABLES:
        if not _table_exists(connection, table):
            print(f"{table:<40}{'нет':>10}")
            continue
        count = int(connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])
        counts[table] = count
        total += count
        print(f"{table:<40}{count:>10}")
    print(f"{'ИТОГО К УДАЛЕНИЮ':<40}{total:>10}")

    print("\nсохраняется без изменений:")
    for table in PRESERVED:
        if _table_exists(connection, table):
            count = int(connection.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"])
            print(f"  {table:<38}{count:>10}")

    if not args.apply:
        print("\nэто предпросмотр — запустите с --apply --backup <путь>, чтобы удалить")
        connection.close()
        return 0

    if not args.backup:
        print("\n--apply требует --backup: без резервной копии удаление не выполняется")
        connection.close()
        return 2

    args.backup.parent.mkdir(parents=True, exist_ok=True)
    connection.close()
    shutil.copy2(database, args.backup)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{database}{suffix}")
        if sidecar.exists():
            shutil.copy2(sidecar, Path(f"{args.backup}{suffix}"))
    print(f"\nрезервная копия: {args.backup}")

    connection = sqlite3.connect(database)
    for table in counts:
        connection.execute(f"DELETE FROM {table}")
    for sequence in ("party_orders", "customer_accounts"):
        connection.execute("DELETE FROM sqlite_sequence WHERE name = ?", (sequence,))
    connection.commit()
    connection.execute("VACUUM")
    connection.close()
    print(f"удалено строк: {total}; счётчики заказов и клиентов сброшены")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
