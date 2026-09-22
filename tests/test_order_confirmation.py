from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from core import admin_notifications, admin_store, customer_store


class _ClosingTestConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class OrderConfirmationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_root = Path(self.temp_dir.name)
        self.db_path = self.db_root / "site_admin.sqlite3"
        self.patchers = [
            patch.object(customer_store, "DB_ROOT", self.db_root),
            patch.object(customer_store, "DB_PATH", self.db_path),
            patch.object(admin_notifications, "DB_ROOT", self.db_root),
            patch.object(admin_notifications, "DB_PATH", self.db_path),
            patch.object(admin_store, "DB_ROOT", self.db_root),
            patch.object(admin_store, "DB_PATH", self.db_path),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, factory=_ClosingTestConnection)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_stores(self) -> None:
        customer_store.init_customer_store()
        admin_notifications.init_admin_notifications_store()

    def _seed_order(
        self,
        *,
        status: str = "new",
        public_id: str = "SRP-00001",
        phone: str = "+998901234567",
    ) -> int:
        self._init_stores()
        now = "2026-08-06T10:00:00+00:00"
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO customer_accounts(
                    phone_normalized, phone_display, full_name, preferred_auth_channel,
                    phone_verified_at, created_at, updated_at
                ) VALUES (?, ?, ?, 'telegram', ?, ?, ?)
                """,
                (phone, phone, "Тестовый клиент", now, now, now),
            )
            customer_id = int(cursor.lastrowid)
            cursor = connection.execute(
                """
                INSERT INTO party_orders(
                    public_id, customer_id, status, celebration_date, time_from, time_to,
                    address_text, payment_method, total_price_snapshot, created_at, updated_at
                ) VALUES (?, ?, ?, '2026-09-01', '14:00', '15:00', 'Тестовый адрес', 'cash', 450000, ?, ?)
                """,
                (public_id, customer_id, status, now, now),
            )
            return int(cursor.lastrowid)

    def _add_recipient(self, chat_id: str, *, active: bool = True) -> None:
        now = "2026-08-06T10:00:00+00:00"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_telegram_recipients(chat_id, label, is_active, created_at, updated_at)
                VALUES (?, 'Администратор', ?, ?, ?)
                """,
                (chat_id, 1 if active else 0, now, now),
            )

    def test_fresh_customer_schema_includes_admin_block_fields(self) -> None:
        customer_store.init_customer_store()
        with self._connect() as connection:
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(customer_accounts)")
            }
        self.assertTrue({"is_blocked", "blocked_until", "block_reason"}.issubset(columns))

    def test_notification_schema_migrates_existing_sync_and_message_rows(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE admin_telegram_order_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    public_id TEXT NOT NULL DEFAULT '',
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE admin_telegram_sync_queue (
                    order_id INTEGER PRIMARY KEY,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    next_attempt_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO admin_telegram_order_messages(
                    order_id, public_id, chat_id, message_id, created_at
                ) VALUES (1, 'SRP-00001', '123456', 10, '2026-08-06T10:00:00+00:00');
                INSERT INTO admin_telegram_sync_queue(
                    order_id, attempts, last_error, next_attempt_at, updated_at
                ) VALUES (1, 2, 'temporary', '2026-08-06T10:01:00+00:00', '2026-08-06T10:00:00+00:00');
                """
            )

        admin_notifications.init_admin_notifications_store()
        admin_notifications.init_admin_notifications_store()

        with self._connect() as connection:
            message_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(admin_telegram_order_messages)")
            }
            sync_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(admin_telegram_sync_queue)")
            }
            message = connection.execute(
                "SELECT message_id, quarantined_at, quarantine_reason FROM admin_telegram_order_messages"
            ).fetchone()
            queued = connection.execute(
                "SELECT attempts, state_version FROM admin_telegram_sync_queue"
            ).fetchone()
            dead_letter_table = connection.execute(
                """
                SELECT 1 FROM sqlite_master
                WHERE type = 'table' AND name = 'admin_telegram_sync_dead_letters'
                """
            ).fetchone()

        self.assertTrue({"quarantined_at", "quarantine_reason"}.issubset(message_columns))
        self.assertIn("state_version", sync_columns)
        self.assertEqual((message["message_id"], message["quarantined_at"], message["quarantine_reason"]), (10, "", ""))
        self.assertEqual((queued["attempts"], queued["state_version"]), (2, ""))
        self.assertIsNotNone(dead_letter_table)

    def test_notification_schema_migration_is_safe_under_concurrent_init(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE admin_telegram_order_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    public_id TEXT NOT NULL DEFAULT '',
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE admin_telegram_sync_queue (
                    order_id INTEGER PRIMARY KEY,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    next_attempt_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

        worker_count = 8
        start = threading.Barrier(worker_count)

        def migrate() -> None:
            start.wait(timeout=5)
            admin_notifications.init_admin_notifications_store()

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            list(executor.map(lambda _: migrate(), range(worker_count)))

        with self._connect() as connection:
            message_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(admin_telegram_order_messages)")
            }
            sync_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(admin_telegram_sync_queue)")
            }
        self.assertTrue(
            {"delivery_generation", "quarantined_at", "quarantine_reason"}.issubset(message_columns)
        )
        self.assertIn("state_version", sync_columns)

    def test_legacy_migration_is_idempotent_and_preserves_lifecycle(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE party_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    public_id TEXT UNIQUE,
                    customer_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'new',
                    celebration_date TEXT NOT NULL,
                    time_from TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            for index, lifecycle_status in enumerate(
                ("new", "contacted", "confirmed", "cancelled", "done"),
                start=1,
            ):
                connection.execute(
                    """
                    INSERT INTO party_orders(
                        public_id, customer_id, status, celebration_date, time_from, created_at, updated_at
                    ) VALUES (?, ?, ?, '2026-09-01', '14:00', ?, ?)
                    """,
                    (f"SRP-{index:05d}", index, lifecycle_status, f"created-{index}", f"updated-{index}"),
                )

        customer_store.init_customer_store()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, confirmation_state, confirmation_source, confirmed_at FROM party_orders ORDER BY id"
            ).fetchall()
        self.assertEqual(
            [(row["status"], row["confirmation_state"]) for row in rows],
            [
                ("new", "unconfirmed"),
                ("contacted", "unconfirmed"),
                ("confirmed", "confirmed"),
                ("cancelled", "unconfirmed"),
                ("done", "confirmed"),
            ],
        )
        self.assertTrue(all(row["confirmation_source"] == "legacy-migration" for row in rows))
        self.assertIsNotNone(rows[2]["confirmed_at"])

        with self._connect() as connection:
            connection.execute(
                """
                UPDATE party_orders
                SET confirmation_state = 'unconfirmed', confirmation_source = 'telegram'
                WHERE status = 'confirmed'
                """
            )
        customer_store.reconcile_order_confirmation_lifecycle_states()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, confirmation_state, confirmation_source FROM party_orders WHERE public_id = 'SRP-00003'"
            ).fetchone()
        self.assertEqual(row["status"], "new")
        self.assertEqual(row["confirmation_state"], "unconfirmed")
        self.assertEqual(row["confirmation_source"], "telegram")

    def test_confirmation_transitions_are_audited_and_idempotent(self) -> None:
        order_id = self._seed_order(status="new")

        first = customer_store.set_order_confirmation(
            order_id,
            "confirmed",
            source="telegram",
            actor="@operator (123456)",
        )
        second = customer_store.set_order_confirmation(
            order_id,
            "confirmed",
            source="telegram",
            actor="@operator (123456)",
        )
        self.assertTrue(first["success"])
        self.assertTrue(first["changed"])
        self.assertTrue(second["success"])
        self.assertFalse(second["changed"])

        with self._connect() as connection:
            row = connection.execute("SELECT * FROM party_orders WHERE id = ?", (order_id,)).fetchone()
            event_count = connection.execute(
                "SELECT COUNT(*) FROM party_order_confirmation_events WHERE order_id = ?",
                (order_id,),
            ).fetchone()[0]
        self.assertEqual(row["status"], "confirmed")
        self.assertEqual(row["confirmation_state"], "confirmed")
        self.assertEqual(row["confirmation_source"], "telegram")
        self.assertEqual(row["confirmation_actor"], "@operator (123456)")
        self.assertIsNotNone(row["confirmed_at"])
        self.assertEqual(event_count, 1)

        removed = customer_store.set_order_confirmation(
            order_id,
            "unconfirmed",
            source="admin",
            actor="admin-panel",
        )
        self.assertTrue(removed["changed"])
        order = customer_store.get_order_by_id(order_id)
        self.assertEqual(order["status"], "new")
        self.assertEqual(order["confirmation_state"], "unconfirmed")
        self.assertEqual(order["status_label"], "Не подтверждён")
        self.assertIsNone(order["confirmed_at"])
        self.assertEqual(
            customer_store.get_order_summary(),
            {"unconfirmed": 1, "confirmed": 0, "cancelled": 0, "total": 1},
        )

        with self._connect() as connection:
            event_count = connection.execute(
                "SELECT COUNT(*) FROM party_order_confirmation_events WHERE order_id = ?",
                (order_id,),
            ).fetchone()[0]
        self.assertEqual(event_count, 2)

    def test_admin_revenue_uses_confirmation_state_not_legacy_lifecycle(self) -> None:
        order_id = self._seed_order(status="new")
        customer_store.set_order_confirmation(
            order_id,
            "confirmed",
            source="admin",
            actor="operator (admin:1)",
        )

        revenue = admin_store.get_revenue_stats()
        customers = admin_store.get_customer_list()

        self.assertEqual(revenue["total"], 450000)
        self.assertEqual(revenue["count"], 1)
        self.assertEqual(revenue["avg"], 450000)
        # The dashboard's "сегодня" panel reads today_count; this order is seeded
        # with a fixed 2026-08-06 date, so it must not leak into today's figure.
        self.assertEqual(revenue["today_count"], 0)
        self.assertEqual(revenue["today_total"], 0)
        self.assertEqual(customers[0]["total_spent"], 450000)

    def test_new_order_records_initial_confirmation_metadata(self) -> None:
        self._init_stores()
        now = "2026-08-06T10:00:00+00:00"
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO customer_accounts(
                    phone_normalized, phone_display, full_name, preferred_auth_channel,
                    phone_verified_at, created_at, updated_at
                ) VALUES ('+998901234567', '+998 (90) 123-45-67', 'Тестовый клиент', 'telegram', ?, ?, ?)
                """,
                (now, now, now),
            )
            customer_id = int(cursor.lastrowid)

        character = {
            "id": 1,
            "slug": "hero",
            "name": "Герой",
            "entity_type": customer_store.ENTITY_TYPE_CHARACTER,
            "ensemble_members": [],
        }
        program = {
            "id": 2,
            "slug": "test-show",
            "name": "Тестовое шоу",
            "entity_type": customer_store.ENTITY_TYPE_SHOW_PROGRAM,
            "base_price": 1_000_000,
            "included_characters_count": 1,
            "extra_character_price_3": 200_000,
            "extra_character_price_4_plus": 200_000,
        }
        by_slug = {program["slug"]: program, character["slug"]: character}
        form_data = {
            "program_slug": program["slug"],
            "character_slugs": ["hero"],
            "celebration_date": "2099-09-01",
            "time_from": "14:00",
            "time_to": "15:00",
            "celebrant_name": "Ребёнок",
            "celebrant_age": "7",
            "children_count": "10",
            "address_text": "Тестовый адрес",
            "map_label": "Тестовая точка",
            "map_lat": "41.31",
            "map_lng": "69.28",
            "yandex_map_url": "javascript:alert('untrusted')",
            "payment_method": "cash",
        }
        with (
            patch.object(customer_store, "get_customer_block_status", return_value=None),
            patch.object(customer_store, "get_character_by_slug", side_effect=by_slug.get),
            patch.object(customer_store, "get_program_duration_minutes", return_value=60),
            patch.object(
                customer_store,
                "check_character_availability",
                return_value={"success": True, "available": True},
            ),
        ):
            result = customer_store.create_party_order(customer_id, form_data)

        self.assertTrue(result["success"], result)
        order = result["order"]
        self.assertEqual(order["confirmation_state"], "unconfirmed")
        self.assertEqual(order["confirmation_source"], "order-builder")
        self.assertEqual(order["confirmation_actor"], f"customer:{customer_id}")
        self.assertTrue(order["confirmation_changed_at"])
        self.assertTrue(order["yandex_map_url"].startswith("https://yandex.uz/maps/"))
        with self._connect() as connection:
            queued = connection.execute(
                "SELECT attempts, claim_token FROM admin_telegram_delivery_queue WHERE order_id = ?",
                (order["id"],),
            ).fetchone()
        self.assertIsNotNone(queued)
        self.assertEqual((queued["attempts"], queued["claim_token"]), (0, ""))

    def test_character_only_post_is_rejected_without_order_or_notification(self) -> None:
        self._init_stores()
        character = {
            "id": 1,
            "slug": "hero",
            "name": "Герой",
            "entity_type": customer_store.ENTITY_TYPE_CHARACTER,
            "ensemble_members": [],
        }
        form_data = {
            "program_slug": "",
            "character_slugs": ["hero"],
            "celebration_date": "2099-09-01",
            "time_from": "14:00",
            "time_to": "15:00",
            "celebrant_name": "Ребёнок",
            "celebrant_age": "7",
            "children_count": "10",
            "address_text": "Тестовый адрес",
            "map_label": "Тестовая точка",
            "map_lat": "41.31",
            "map_lng": "69.28",
            "payment_method": "cash",
        }
        with (
            patch.object(customer_store, "get_customer_block_status", return_value=None),
            patch.object(customer_store, "get_character_by_slug", return_value=character),
            patch.object(
                customer_store,
                "check_character_availability",
                return_value={"success": True, "available": True},
            ),
        ):
            result = customer_store.create_party_order(1, form_data)

        self.assertFalse(result["success"])
        self.assertEqual(result["errors"]["program_slug"], "Выберите шоу-программу.")
        with self._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM party_orders").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM admin_telegram_delivery_queue").fetchone()[0], 0)

    def test_group_order_roundtrip_keeps_members_count_fixed_surcharge_and_telegram_text(self) -> None:
        self._init_stores()
        now = "2026-08-06T10:00:00+00:00"
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO customer_accounts(
                    phone_normalized, phone_display, full_name, preferred_auth_channel,
                    phone_verified_at, created_at, updated_at
                ) VALUES ('+998901234568', '+998 (90) 123-45-68', 'Групповой заказ', 'telegram', ?, ?, ?)
                """,
                (now, now, now),
            )
            customer_id = int(cursor.lastrowid)

        program = {
            "id": 10,
            "slug": "test-show",
            "name": "Тестовое шоу",
            "entity_type": customer_store.ENTITY_TYPE_SHOW_PROGRAM,
            "base_price": 0,
            "included_characters_count": 2,
            "extra_character_price_3": 200_000,
            "extra_character_price_4_plus": 150_000,
        }
        trio = {
            "id": 11,
            "slug": "anna-elsa-olaf",
            "name": "Анна, Эльза и Олаф",
            "entity_type": customer_store.ENTITY_TYPE_CHARACTER,
            "ensemble_members": ["Анна", "Эльза", "Олаф"],
            "ensemble_included_count": 2,
            "ensemble_extra_member_price": 300_000,
            "duplicate_count": 0,
        }
        by_slug = {program["slug"]: program, trio["slug"]: trio}
        form_data = {
            "program_slug": program["slug"],
            "character_slugs": [trio["slug"]],
            "ensemble_members": [
                "anna-elsa-olaf::Анна",
                "anna-elsa-olaf::Эльза",
                "anna-elsa-olaf::Олаф",
            ],
            "celebration_date": "2099-09-01",
            "time_from": "14:00",
            "time_to": "16:00",
            "celebrant_name": "Ребёнок",
            "celebrant_age": "7",
            "children_count": "10",
            "address_text": "Тестовый адрес",
            "map_label": "Тестовая точка",
            "map_lat": "41.31",
            "map_lng": "69.28",
            "payment_method": "cash",
        }
        with (
            patch.object(customer_store, "get_customer_block_status", return_value=None),
            patch.object(customer_store, "get_character_by_slug", side_effect=by_slug.get),
            patch.object(customer_store, "get_program_duration_minutes", return_value=60),
            patch.object(
                customer_store,
                "check_character_availability",
                return_value={"success": True, "available": True},
            ),
        ):
            result = customer_store.create_party_order(customer_id, form_data)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["order"]["total_price"], 400_000)
        expected_name = "Анна + Эльза + Олаф"
        self.assertEqual(result["order"]["character_names"], [expected_name])
        with self._connect() as connection:
            saved = connection.execute(
                "SELECT name_snapshot FROM party_order_characters WHERE order_id = ?",
                (result["order"]["id"],),
            ).fetchone()
        self.assertEqual(saved["name_snapshot"], expected_name)
        with patch.object(admin_notifications, "ADMIN_PORTAL_BASE", "https://animator-surpriz.uz"):
            telegram = admin_notifications._format_order_message(result["order"])
        self.assertIn("Тестовое шоу (Анна + Эльза + Олаф) · 2 часа", telegram)
        self.assertNotIn("состав +300 000 сум", telegram)
        self.assertIn("/admin/orders?search=", telegram)
        self.assertNotIn("/admin/?tab=orders", telegram)

    def test_concurrent_order_posts_cannot_double_book_character(self) -> None:
        self._init_stores()
        now = "2026-08-06T10:00:00+00:00"
        with self._connect() as connection:
            customer_ids = []
            for index in range(2):
                cursor = connection.execute(
                    """
                    INSERT INTO customer_accounts(
                        phone_normalized, phone_display, full_name, preferred_auth_channel,
                        phone_verified_at, created_at, updated_at
                    ) VALUES (?, ?, ?, 'telegram', ?, ?, ?)
                    """,
                    (
                        f"99890123456{index}",
                        f"+998 (90) 123-45-6{index}",
                        f"Клиент {index + 1}",
                        now,
                        now,
                        now,
                    ),
                )
                customer_ids.append(int(cursor.lastrowid))

        character = {
            "id": 1,
            "slug": "hero",
            "name": "Единственный герой",
            "entity_type": customer_store.ENTITY_TYPE_CHARACTER,
            "ensemble_members": [],
            "duplicate_count": 0,
        }
        program = {
            "id": 2,
            "slug": "test-show",
            "name": "Тестовое шоу",
            "entity_type": customer_store.ENTITY_TYPE_SHOW_PROGRAM,
            "base_price": 1_000_000,
            "included_characters_count": 1,
            "extra_character_price_3": 200_000,
            "extra_character_price_4_plus": 200_000,
        }
        by_slug = {program["slug"]: program, character["slug"]: character}
        form_data = {
            "program_slug": program["slug"],
            "character_slugs": ["hero"],
            "celebration_date": "2099-09-01",
            "time_from": "14:00",
            "time_to": "15:00",
            "celebrant_name": "Ребёнок",
            "celebrant_age": "7",
            "children_count": "10",
            "address_text": "Тестовый адрес",
            "map_label": "Тестовая точка",
            "map_lat": "41.31",
            "map_lng": "69.28",
            "payment_method": "cash",
        }
        initial_checks = threading.Barrier(2)
        thread_state = threading.local()
        real_availability = customer_store.check_character_availability

        def synchronized_availability(**kwargs):
            call_number = getattr(thread_state, "calls", 0) + 1
            thread_state.calls = call_number
            result = real_availability(**kwargs)
            if call_number == 1:
                initial_checks.wait(timeout=5)
            return result

        with (
            patch.object(customer_store, "get_character_by_slug", side_effect=by_slug.get),
            patch.object(customer_store, "get_program_duration_minutes", return_value=60),
            patch.object(customer_store, "check_character_availability", side_effect=synchronized_availability),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            results = list(executor.map(lambda cid: customer_store.create_party_order(cid, form_data), customer_ids))

        self.assertEqual(sum(1 for result in results if result["success"]), 1)
        failed = next(result for result in results if not result["success"])
        self.assertIn("availability", failed["errors"])
        with self._connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM party_orders").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM admin_telegram_delivery_queue").fetchone()[0], 1)

    def test_new_order_delivery_outbox_skips_already_recorded_recipient(self) -> None:
        order_id = self._seed_order()
        self._add_recipient("123456")
        self._add_recipient("654321")
        admin_notifications.queue_order_notification(order_id)
        with self._connect() as connection:
            generation = connection.execute(
                "SELECT delivery_generation FROM admin_telegram_delivery_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()[0]
            connection.execute(
                """
                INSERT INTO admin_telegram_order_messages(
                    order_id, public_id, chat_id, message_id, delivery_generation, created_at
                ) VALUES (?, 'SRP-00001', '123456', 10, ?, '2026-08-06T10:00:00+00:00')
                """,
                (order_id, generation),
            )

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_send_telegram_message",
                return_value={"success": True, "result": {"message_id": 20}, "message": "ok"},
            ) as send,
        ):
            result = admin_notifications.process_pending_order_deliveries()

        self.assertEqual(result, {"processed": 1, "succeeded": 1, "failed": 0})
        send.assert_called_once()
        self.assertEqual(send.call_args.args[0], "654321")
        with self._connect() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM admin_telegram_order_messages WHERE order_id = ?",
                    (order_id,),
                ).fetchone()[0],
                2,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM admin_telegram_delivery_queue WHERE order_id = ?",
                    (order_id,),
                ).fetchone()[0],
                0,
            )

    def test_admin_resend_creates_new_generation_and_sends_to_existing_chat(self) -> None:
        order_id = self._seed_order()
        self._add_recipient("123456")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_telegram_order_messages(order_id, public_id, chat_id, message_id, created_at)
                VALUES (?, 'SRP-00001', '123456', 10, '2026-08-06T10:00:00+00:00')
                """,
                (order_id,),
            )
        queued = admin_notifications.send_order_notification({"id": order_id})
        self.assertTrue(queued["queued"])

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_send_telegram_message",
                return_value={"success": True, "result": {"message_id": 20}, "message": "ok"},
            ) as send,
        ):
            result = admin_notifications.process_pending_order_deliveries()

        self.assertEqual(result, {"processed": 1, "succeeded": 1, "failed": 0})
        send.assert_called_once()
        with self._connect() as connection:
            mappings = connection.execute(
                "SELECT message_id FROM admin_telegram_order_messages WHERE order_id = ? ORDER BY id",
                (order_id,),
            ).fetchall()
        self.assertEqual([row["message_id"] for row in mappings], [10, 20])

    def test_transient_order_lookup_error_keeps_delivery_outbox(self) -> None:
        order_id = self._seed_order()
        admin_notifications.queue_order_notification(order_id)
        with patch.object(
            customer_store,
            "get_order_by_id",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            result = admin_notifications.process_pending_order_deliveries()
        self.assertEqual(result, {"processed": 1, "succeeded": 0, "failed": 1})
        with self._connect() as connection:
            queued = connection.execute(
                "SELECT attempts, claim_token FROM admin_telegram_delivery_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        self.assertIsNotNone(queued)
        self.assertEqual((queued["attempts"], queued["claim_token"]), (1, ""))

    def test_failed_new_order_delivery_is_retried_without_losing_outbox(self) -> None:
        order_id = self._seed_order()
        self._add_recipient("123456")
        admin_notifications.queue_order_notification(order_id)
        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_send_telegram_message",
                return_value={"success": False, "message": "temporary"},
            ),
        ):
            result = admin_notifications.process_pending_order_deliveries()
        self.assertEqual(result, {"processed": 1, "succeeded": 0, "failed": 1})
        with self._connect() as connection:
            queued = connection.execute(
                "SELECT attempts, claim_token, claimed_until FROM admin_telegram_delivery_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        self.assertEqual(queued["attempts"], 1)
        self.assertEqual((queued["claim_token"], queued["claimed_until"]), ("", ""))

    def test_stale_delivery_worker_cannot_ack_newer_queue_request(self) -> None:
        order_id = self._seed_order()
        admin_notifications.queue_order_notification(order_id)
        claim = admin_notifications._claim_pending_order_deliveries(1)[0]
        admin_notifications.queue_order_notification(order_id)
        admin_notifications._clear_order_delivery(order_id, claim["claim_token"])
        with self._connect() as connection:
            queued = connection.execute(
                "SELECT claim_token FROM admin_telegram_delivery_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        self.assertIsNotNone(queued)
        self.assertEqual(queued["claim_token"], "")

    def test_state_change_during_initial_delivery_queues_card_sync(self) -> None:
        order_id = self._seed_order()
        self._add_recipient("123456")
        admin_notifications.queue_order_notification(order_id)
        sent_texts: list[str] = []

        def send_then_confirm(chat_id, text, **kwargs):
            del chat_id, kwargs
            sent_texts.append(text)
            self.assertTrue(
                customer_store.update_order_status(
                    order_id,
                    "confirmed",
                    source="admin",
                    actor="operator (admin:1)",
                )
            )
            return {"success": True, "result": {"message_id": 20}, "message": "ok"}

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(admin_notifications, "_send_telegram_message", side_effect=send_then_confirm),
        ):
            delivered = admin_notifications.process_pending_order_deliveries()

        self.assertEqual(delivered, {"processed": 1, "succeeded": 1, "failed": 0})
        self.assertIn("Не подтверждён", sent_texts[0])
        with self._connect() as connection:
            queued = connection.execute(
                "SELECT order_id FROM admin_telegram_sync_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        self.assertIsNotNone(queued)

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_edit_telegram_message",
                return_value={"success": True, "message": "ok"},
            ) as edit,
        ):
            synced = admin_notifications.process_pending_order_syncs()
        self.assertEqual(synced, {"processed": 1, "succeeded": 1, "failed": 0})
        self.assertIn("Подтверждён", edit.call_args.args[2])

    def test_sync_lookup_errors_keep_durable_retry(self) -> None:
        order_id = self._seed_order()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_telegram_order_messages(order_id, public_id, chat_id, message_id, created_at)
                VALUES (?, 'SRP-00001', '123456', 10, '2026-08-06T10:00:00+00:00')
                """,
                (order_id,),
            )
        with patch.object(
            admin_notifications,
            "_list_order_messages",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            result = admin_notifications.sync_order_messages(order_id)
        self.assertTrue(result["queued"])

        with self._connect() as connection:
            connection.execute(
                "UPDATE admin_telegram_sync_queue SET next_attempt_at = '2000-01-01T00:00:00+00:00' WHERE order_id = ?",
                (order_id,),
            )
        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                customer_store,
                "get_order_by_id",
                side_effect=sqlite3.OperationalError("database is locked"),
            ),
        ):
            retried = admin_notifications.process_pending_order_syncs()
        self.assertEqual(retried, {"processed": 1, "succeeded": 0, "failed": 1})
        with self._connect() as connection:
            queued = connection.execute(
                "SELECT attempts FROM admin_telegram_sync_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        self.assertIsNotNone(queued)
        self.assertGreaterEqual(queued["attempts"], 2)

    def test_recipient_lookup_database_error_is_retriable(self) -> None:
        self._init_stores()
        with patch.object(
            admin_notifications,
            "_get_connection",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            with self.assertRaises(sqlite3.OperationalError):
                admin_notifications._is_active_recipient_chat("123456")

    def test_admin_compatibility_entry_point_syncs_all_messages(self) -> None:
        order_id = self._seed_order()
        with patch.object(admin_notifications, "sync_order_messages") as sync:
            self.assertTrue(customer_store.update_order_status(order_id, "confirmed"))
            sync.assert_called_once_with(order_id)
            self.assertTrue(customer_store.update_order_status(order_id, "cancelled"))
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, confirmation_state FROM party_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
        self.assertEqual((row["status"], row["confirmation_state"]), ("cancelled", "unconfirmed"))

        public_order = customer_store.get_order_by_id(order_id)
        self.assertEqual(public_order["display_status"], "cancelled")
        self.assertEqual(public_order["status_label"], "Отменён")

    def test_telegram_callback_requires_active_recipient_and_toggles_idempotently(self) -> None:
        order_id = self._seed_order()
        self._add_recipient("123456")
        self._add_recipient("654321", active=False)

        def callback(chat_id: str, action: str, callback_id: str) -> dict:
            return {
                "callback_query": {
                    "id": callback_id,
                    "data": f"order:SRP-00001:{action}",
                    "from": {"id": 123456, "username": "operator"},
                    "message": {"chat": {"id": int(chat_id)}},
                }
            }

        with (
            patch.object(admin_notifications, "_answer_callback") as answer,
            patch.object(admin_notifications, "sync_order_messages") as sync,
        ):
            first = admin_notifications.handle_callback(callback("123456", "confirm", "cb-1"))
            second = admin_notifications.handle_callback(callback("123456", "confirm", "cb-2"))
            denied = admin_notifications.handle_callback(callback("654321", "unconfirm", "cb-3"))
            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertFalse(denied["success"])
            self.assertEqual(sync.call_count, 2)
            self.assertEqual(answer.call_count, 3)

        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, confirmation_state FROM party_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            event_count = connection.execute(
                "SELECT COUNT(*) FROM party_order_confirmation_events WHERE order_id = ?",
                (order_id,),
            ).fetchone()[0]
        self.assertEqual((row["status"], row["confirmation_state"]), ("confirmed", "confirmed"))
        self.assertEqual(event_count, 1)

    def test_legacy_telegram_cancel_releases_internal_lifecycle(self) -> None:
        order_id = self._seed_order(status="new")
        self._add_recipient("123456")
        update = {
            "callback_query": {
                "id": "legacy-cancel",
                "data": "order:SRP-00001:cancel",
                "from": {"id": 123456, "username": "operator"},
                "message": {"chat": {"id": 123456}},
            }
        }

        with (
            patch.object(admin_notifications, "_answer_callback"),
            patch.object(admin_notifications, "sync_order_messages"),
            patch.object(customer_store, "apply_cancellation_block_if_needed") as block_check,
        ):
            result = admin_notifications.handle_callback(update)

        self.assertTrue(result["success"])
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, confirmation_state FROM party_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
        self.assertEqual((row["status"], row["confirmation_state"]), ("cancelled", "unconfirmed"))
        block_check.assert_called_once()

    def test_terminal_order_cannot_be_reopened_or_legacy_cancelled(self) -> None:
        order_id = self._seed_order(status="done")
        with self._connect() as connection:
            connection.execute(
                "UPDATE party_orders SET confirmation_state = 'confirmed' WHERE id = ?",
                (order_id,),
            )

        changed = customer_store.set_order_confirmation(
            order_id,
            "unconfirmed",
            source="admin",
            actor="operator (admin:1)",
        )
        cancelled = customer_store.apply_legacy_order_cancellation_by_public_id(
            "SRP-00001",
            actor="@operator (123456)",
        )
        self.assertFalse(changed["success"])
        self.assertFalse(cancelled["success"])
        with self._connect() as connection:
            row = connection.execute(
                "SELECT status, confirmation_state FROM party_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
        self.assertEqual((row["status"], row["confirmation_state"]), ("done", "confirmed"))
        self.assertEqual(
            admin_notifications._build_order_keyboard("SRP-00001", order_id, "confirmed", "done"),
            {"inline_keyboard": []},
        )

    def test_repeated_cancellation_does_not_extend_existing_block(self) -> None:
        self._init_stores()
        now = "2026-08-06T10:00:00+00:00"
        with self._connect() as connection:
            customer_id = int(
                connection.execute(
                    """
                    INSERT INTO customer_accounts(
                        phone_normalized, phone_display, full_name, preferred_auth_channel,
                        phone_verified_at, created_at, updated_at
                    ) VALUES ('998901234567', '+998 (90) 123-45-67', 'Клиент', 'telegram', ?, ?, ?)
                    """,
                    (now, now, now),
                ).lastrowid
            )
            for index in range(5):
                connection.execute(
                    """
                    INSERT INTO party_orders(
                        public_id, customer_id, status, celebration_date, time_from, time_to,
                        address_text, payment_method, created_at, updated_at
                    ) VALUES (?, ?, 'cancelled', '2026-09-01', '14:00', '15:00', 'Адрес', 'cash', ?, ?)
                    """,
                    (f"SRP-C-{index}", customer_id, f"{now}-{index}", f"{now}-{index}"),
                )

        fixed_now = datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)
        with patch.object(customer_store, "utcnow", return_value=fixed_now):
            self.assertTrue(customer_store.apply_cancellation_block_if_needed(customer_id))
        with self._connect() as connection:
            first_until = connection.execute(
                "SELECT blocked_until FROM customer_accounts WHERE id = ?",
                (customer_id,),
            ).fetchone()[0]
        with patch.object(customer_store, "utcnow", return_value=fixed_now + timedelta(hours=1)):
            self.assertFalse(customer_store.apply_cancellation_block_if_needed(customer_id))
        with self._connect() as connection:
            second_until = connection.execute(
                "SELECT blocked_until FROM customer_accounts WHERE id = ?",
                (customer_id,),
            ).fetchone()[0]
        self.assertEqual(first_until, second_until)

    def test_idempotent_legacy_cancel_does_not_restore_expired_block(self) -> None:
        order_id = self._seed_order()
        with self._connect() as connection:
            customer_id = connection.execute(
                "SELECT customer_id FROM party_orders WHERE id = ?",
                (order_id,),
            ).fetchone()[0]
            public_id = connection.execute(
                "SELECT public_id FROM party_orders WHERE id = ?",
                (order_id,),
            ).fetchone()[0]
            connection.execute(
                "UPDATE party_orders SET status = 'cancelled', confirmation_state = 'unconfirmed' WHERE id = ?",
                (order_id,),
            )
            connection.execute(
                """
                UPDATE customer_accounts
                SET blocked_until = '2026-08-01T00:00:00+00:00', block_reason = 'expired'
                WHERE id = ?
                """,
                (customer_id,),
            )

        with patch.object(customer_store, "apply_cancellation_block_if_needed") as apply_block:
            result = customer_store.apply_legacy_order_cancellation_by_public_id(
                public_id,
                source="telegram",
                actor="chat:123456",
            )

        self.assertTrue(result["success"])
        self.assertFalse(result["changed"])
        apply_block.assert_not_called()

    def test_cutover_reconcile_treats_terminal_lifecycle_as_authoritative(self) -> None:
        done_order_id = self._seed_order()
        cancelled_order_id = self._seed_order(public_id="SRP-00002", phone="+998901234568")
        with self._connect() as connection:
            connection.execute(
                "UPDATE party_orders SET status = 'done', confirmation_state = 'unconfirmed', confirmed_at = NULL WHERE id = ?",
                (done_order_id,),
            )
            connection.execute(
                "UPDATE party_orders SET status = 'cancelled', confirmation_state = 'confirmed', confirmed_at = updated_at WHERE id = ?",
                (cancelled_order_id,),
            )

        customer_store.reconcile_order_confirmation_lifecycle_states()

        with self._connect() as connection:
            done = connection.execute(
                "SELECT confirmation_state, confirmed_at FROM party_orders WHERE id = ?",
                (done_order_id,),
            ).fetchone()
            cancelled = connection.execute(
                "SELECT confirmation_state, confirmed_at FROM party_orders WHERE id = ?",
                (cancelled_order_id,),
            ).fetchone()
        self.assertEqual(done["confirmation_state"], "confirmed")
        self.assertIsNotNone(done["confirmed_at"])
        self.assertEqual(cancelled["confirmation_state"], "unconfirmed")
        self.assertIsNone(cancelled["confirmed_at"])

    def test_sync_edits_every_recorded_card_without_followup_messages(self) -> None:
        order_id = self._seed_order()
        customer_store.set_order_confirmation(order_id, "confirmed", source="admin", actor="admin-panel")
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO admin_telegram_order_messages(order_id, public_id, chat_id, message_id, created_at)
                VALUES (?, 'SRP-00001', ?, ?, '2026-08-06T10:00:00+00:00')
                """,
                [(order_id, "123456", 10), (order_id, "789012", 20)],
            )

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_edit_telegram_message",
                return_value={"success": True, "message": "ok"},
            ) as edit,
            patch.object(admin_notifications, "_send_telegram_message") as send,
        ):
            result = admin_notifications.sync_order_messages(order_id)
        self.assertTrue(result["success"])
        self.assertEqual(result["updated"], 2)
        self.assertEqual(edit.call_count, 2)
        self.assertEqual(edit.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"], "order:SRP-00001:unconfirm")
        self.assertEqual(edit.call_args.kwargs["reply_markup"]["inline_keyboard"][0][1]["callback_data"], "order:SRP-00001:cancel")
        self.assertIn("Подтверждён", edit.call_args.args[2])
        send.assert_not_called()

    def test_terminal_edit_quarantines_only_the_broken_message_mapping(self) -> None:
        order_id = self._seed_order()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO admin_telegram_order_messages(order_id, public_id, chat_id, message_id, created_at)
                VALUES (?, 'SRP-00001', '123456', ?, '2026-08-06T10:00:00+00:00')
                """,
                [(order_id, 10), (order_id, 20)],
            )

        def edit_message(chat_id, message_id, text, **kwargs):
            del chat_id, text, kwargs
            if message_id == 10:
                return {
                    "success": False,
                    "message": "Telegram отверг изменение: Bad Request: message to edit not found",
                    "terminal_mapping": True,
                }
            return {"success": True, "message": "ok"}

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(admin_notifications, "_edit_telegram_message", side_effect=edit_message),
        ):
            result = admin_notifications.sync_order_messages(order_id)

        self.assertTrue(result["success"])
        self.assertEqual((result["updated"], result["quarantined"], result["failed"]), (1, 1, 0))
        self.assertFalse(result["queued"])
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT message_id, quarantined_at, quarantine_reason
                FROM admin_telegram_order_messages
                WHERE order_id = ?
                ORDER BY message_id
                """,
                (order_id,),
            ).fetchall()
            queue_count = connection.execute(
                "SELECT COUNT(*) FROM admin_telegram_sync_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()[0]
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["quarantined_at"])
        self.assertIn("message to edit not found", rows[0]["quarantine_reason"])
        self.assertEqual(rows[1]["quarantined_at"], "")
        self.assertEqual(queue_count, 0)
        self.assertEqual(
            [(message["chat_id"], message["message_id"]) for message in admin_notifications._list_order_messages(order_id)],
            [("123456", 20)],
        )

    def test_persistent_unknown_sync_failure_moves_to_dead_letter(self) -> None:
        order_id = self._seed_order()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_telegram_order_messages(order_id, public_id, chat_id, message_id, created_at)
                VALUES (?, 'SRP-00001', '123456', 10, '2026-08-06T10:00:00+00:00')
                """,
                (order_id,),
            )

        with (
            patch.object(admin_notifications, "TELEGRAM_SYNC_MAX_ATTEMPTS", 3),
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_edit_telegram_message",
                return_value={"success": False, "message": "persistent unknown failure"},
            ),
        ):
            first = admin_notifications.sync_order_messages(order_id)
            second = admin_notifications.sync_order_messages(order_id)
            third = admin_notifications.sync_order_messages(order_id)

        self.assertTrue(first["queued"])
        self.assertTrue(second["queued"])
        self.assertFalse(third["queued"])
        self.assertTrue(third["dead_lettered"])
        self.assertEqual(third["attempts"], 3)
        with self._connect() as connection:
            active_count = connection.execute(
                "SELECT COUNT(*) FROM admin_telegram_sync_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()[0]
            dead_letter = connection.execute(
                """
                SELECT attempts, last_error
                FROM admin_telegram_sync_dead_letters
                WHERE order_id = ?
                """,
                (order_id,),
            ).fetchone()
        self.assertEqual(active_count, 0)
        self.assertEqual(dead_letter["attempts"], 3)
        self.assertEqual(dead_letter["last_error"], "persistent unknown failure")
        self.assertEqual(
            admin_notifications.process_pending_order_syncs(),
            {"processed": 0, "succeeded": 0, "failed": 0},
        )

        new_version = "2099-01-01T00:00:00+00:00"
        with self._connect() as connection:
            connection.execute(
                "UPDATE party_orders SET confirmation_changed_at = ? WHERE id = ?",
                (new_version, order_id),
            )
        with (
            patch.object(admin_notifications, "TELEGRAM_SYNC_MAX_ATTEMPTS", 3),
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_edit_telegram_message",
                return_value={"success": False, "message": "persistent unknown failure"},
            ),
        ):
            restarted = admin_notifications.sync_order_messages(order_id)

        self.assertTrue(restarted["queued"])
        self.assertFalse(restarted["dead_lettered"])
        self.assertEqual(restarted["attempts"], 1)
        with self._connect() as connection:
            active = connection.execute(
                "SELECT attempts, state_version FROM admin_telegram_sync_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            dead_letter_count = connection.execute(
                "SELECT COUNT(*) FROM admin_telegram_sync_dead_letters WHERE order_id = ?",
                (order_id,),
            ).fetchone()[0]
        self.assertEqual((active["attempts"], active["state_version"]), (1, new_version))
        self.assertEqual(dead_letter_count, 0)

    def test_failed_sync_is_durable_and_retried(self) -> None:
        order_id = self._seed_order()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_telegram_order_messages(order_id, public_id, chat_id, message_id, created_at)
                VALUES (?, 'SRP-00001', '123456', 10, '2026-08-06T10:00:00+00:00')
                """,
                (order_id,),
            )

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_edit_telegram_message",
                return_value={"success": False, "message": "temporary failure"},
            ),
        ):
            failed = admin_notifications.sync_order_messages(order_id)
        self.assertTrue(failed["queued"])
        with self._connect() as connection:
            queued = connection.execute(
                "SELECT attempts FROM admin_telegram_sync_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            connection.execute(
                "UPDATE admin_telegram_sync_queue SET next_attempt_at = '2000-01-01T00:00:00+00:00' WHERE order_id = ?",
                (order_id,),
            )
        self.assertEqual(queued["attempts"], 1)

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_edit_telegram_message",
                return_value={"success": True, "message": "ok"},
            ),
        ):
            retried = admin_notifications.process_pending_order_syncs()
        self.assertEqual(retried, {"processed": 1, "succeeded": 1, "failed": 0})
        with self._connect() as connection:
            remaining = connection.execute(
                "SELECT COUNT(*) FROM admin_telegram_sync_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()[0]
        self.assertEqual(remaining, 0)

    def test_stale_concurrent_sync_never_clears_newer_state_retry(self) -> None:
        order_id = self._seed_order()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_telegram_order_messages(order_id, public_id, chat_id, message_id, created_at)
                VALUES (?, 'SRP-00001', '123456', 10, '2026-08-06T10:00:00+00:00')
                """,
                (order_id,),
            )
        older = customer_store.get_order_by_id(order_id)
        newer = dict(older)
        newer["confirmation_changed_at"] = "2099-01-01T00:00:00+00:00"
        newer["confirmation_state"] = "confirmed"

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                customer_store,
                "get_order_by_id",
                side_effect=[older, newer],
            ),
            patch.object(
                admin_notifications,
                "_edit_telegram_message",
                return_value={"success": True, "message": "ok"},
            ),
        ):
            result = admin_notifications.sync_order_messages(order_id)

        self.assertFalse(result["success"])
        self.assertTrue(result["queued"])
        with self._connect() as connection:
            queued = connection.execute(
                "SELECT next_attempt_at FROM admin_telegram_sync_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        self.assertIsNotNone(queued)

    def test_state_change_after_recheck_cannot_be_cleared_by_stale_sync(self) -> None:
        order_id = self._seed_order()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO admin_telegram_order_messages(order_id, public_id, chat_id, message_id, created_at)
                VALUES (?, 'SRP-00001', '123456', 10, '2026-08-06T10:00:00+00:00')
                """,
                (order_id,),
            )
        initial_order = customer_store.get_order_by_id(order_id)
        admin_notifications._queue_order_sync(
            order_id,
            "initial sync",
            state_version=str(initial_order.get("confirmation_changed_at") or ""),
        )
        real_clear = admin_notifications._clear_order_sync
        changed_during_ack: list[bool] = []

        def change_state_then_clear(target_order_id, markers, **kwargs):
            changed = customer_store.set_order_confirmation(
                target_order_id,
                "confirmed",
                source="admin",
                actor="concurrent-admin",
            )
            changed_during_ack.append(bool(changed.get("changed")))
            return real_clear(target_order_id, markers, **kwargs)

        with (
            patch.object(admin_notifications, "is_notifications_configured", return_value=True),
            patch.object(
                admin_notifications,
                "_edit_telegram_message",
                return_value={"success": True, "message": "ok"},
            ),
            patch.object(admin_notifications, "_clear_order_sync", side_effect=change_state_then_clear),
        ):
            result = admin_notifications.sync_order_messages(order_id)

        self.assertEqual(changed_during_ack, [True])
        self.assertFalse(result["success"])
        self.assertTrue(result["queued"])
        with self._connect() as connection:
            order = connection.execute(
                "SELECT confirmation_state, confirmation_changed_at FROM party_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            queued = connection.execute(
                "SELECT state_version, attempts FROM admin_telegram_sync_queue WHERE order_id = ?",
                (order_id,),
            ).fetchone()
        self.assertEqual(order["confirmation_state"], "confirmed")
        self.assertIsNotNone(queued)
        self.assertEqual(queued["state_version"], order["confirmation_changed_at"])
        self.assertEqual(queued["attempts"], 1)

    def test_failed_polled_update_is_retried_before_offset_advances(self) -> None:
        self._init_stores()
        update = {"update_id": 42, "message": {"chat": {"id": 123456}, "text": "/status"}}
        with patch.object(admin_notifications, "handle_callback", side_effect=RuntimeError("temporary")):
            offset, processed_all = admin_notifications._process_polled_updates([update], 0)
        self.assertEqual(offset, 0)
        self.assertFalse(processed_all)
        self.assertFalse(admin_notifications._is_update_processed(42))

        with patch.object(admin_notifications, "handle_callback", return_value={"success": True}):
            offset, processed_all = admin_notifications._process_polled_updates([update], 0)
        self.assertEqual(offset, 43)
        self.assertTrue(processed_all)
        self.assertTrue(admin_notifications._is_update_processed(42))

    def test_identical_telegram_edit_is_treated_as_synced(self) -> None:
        response = Mock()
        response.ok = False
        response.json.return_value = {"description": "Bad Request: message is not modified"}
        response.text = ""
        with (
            patch.object(admin_notifications, "_bot_token", return_value="test-token"),
            patch.object(admin_notifications.requests, "post", return_value=response) as post,
        ):
            result = admin_notifications._edit_telegram_message(
                "123456",
                10,
                "Заказ",
                reply_markup={"inline_keyboard": []},
            )
        self.assertTrue(result["success"])
        self.assertTrue(result["unchanged"])
        post.assert_called_once()

    def test_missing_telegram_message_is_a_terminal_mapping_error(self) -> None:
        response = Mock()
        response.ok = False
        response.json.return_value = {"description": "Bad Request: message to edit not found"}
        response.text = ""
        with (
            patch.object(admin_notifications, "_bot_token", return_value="test-token"),
            patch.object(admin_notifications.requests, "post", return_value=response),
        ):
            result = admin_notifications._edit_telegram_message(
                "123456",
                10,
                "Заказ",
                reply_markup={"inline_keyboard": []},
            )
        self.assertFalse(result["success"])
        self.assertTrue(result["terminal_mapping"])

    def test_network_error_never_exposes_bot_token(self) -> None:
        token = "123456:secret-token-value"
        with (
            patch.object(admin_notifications, "_bot_token", return_value=token),
            patch.object(
                admin_notifications.requests,
                "post",
                side_effect=admin_notifications.requests.ConnectionError(
                    f"failed https://api.telegram.org/bot{token}/sendMessage"
                ),
            ),
        ):
            result = admin_notifications._send_telegram_message("123456", "test")
        self.assertFalse(result["success"])
        self.assertNotIn(token, result["message"])

    def test_orders_command_uses_joined_customer_and_snapshot_price(self) -> None:
        self._seed_order()
        self._add_recipient("123456")
        with patch.object(
            admin_notifications,
            "_send_telegram_message",
            return_value={"success": True, "message": "ok"},
        ) as send:
            result = admin_notifications.handle_callback(
                {"message": {"chat": {"id": 123456}, "from": {"id": 123456}, "text": "/orders"}}
            )
        self.assertTrue(result["success"])
        sent_text = send.call_args.args[1]
        self.assertIn("Тестовый клиент", sent_text)
        self.assertIn("450 000 сум", sent_text)

    def test_command_rejects_inactive_chat_before_loading_orders(self) -> None:
        self._seed_order()
        self._add_recipient("654321", active=False)
        with (
            patch.object(
                admin_notifications,
                "_send_telegram_message",
                return_value={"success": True, "message": "ok"},
            ) as send,
            patch.object(customer_store, "list_admin_orders") as list_orders,
        ):
            result = admin_notifications.handle_callback(
                {"message": {"chat": {"id": 654321}, "from": {"id": 654321}, "text": "/orders"}}
            )
        self.assertFalse(result["success"])
        self.assertEqual(result["message"], "unauthorized chat")
        list_orders.assert_not_called()
        self.assertIn("не добавлен", send.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
