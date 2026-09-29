from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from core import admin_notifications, catalog_store, customer_store, google_calendar_store

CHARACTERS = {
    "paw-patrol": {"id": 1, "slug": "paw-patrol", "name": "Скай и Гонщик", "entity_type": "character", "duplicate_count": 0},
    "deadpool": {"id": 2, "slug": "deadpool", "name": "Дэдпул", "entity_type": "character", "duplicate_count": 0},
}


def _catalog_lookup(slug: str, include_hidden: bool = False) -> dict[str, Any] | None:
    item = CHARACTERS.get(slug)
    return dict(item) if item else None


class EnsembleMemberParsingTests(unittest.TestCase):
    def test_lists_and_list_literals_become_clean_names(self) -> None:
        cases = [
            (["Скай", "Гонщик"], ["Скай", "Гонщик"]),
            ("['Скай', 'Гонщик']", ["Скай", "Гонщик"]),
            ('["[\'Скай\'", "\'Гонщик\']"]', ["Скай", "Гонщик"]),
            ("Анна, Эльза\nОлаф (ростовой)", ["Анна", "Эльза", "Олаф (ростовой)"]),
            # Re-saved several times: every save escaped the quotes once more.
            ('[\'[\\\'["[\\\\\\\'Анна\\\\\\\'"\\\'\', \'\\\'"\\\\\\\'Эльза\\\\\\\'"\\\'\', \'\\\'"\\\\\\\'Олаф (ростовой)\\\\\\\']"]\\\']\']', ["Анна", "Эльза", "Олаф (ростовой)"]),
            ("", []),
            (None, []),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(catalog_store.parse_ensemble_members(value), expected)

    def test_saving_an_entity_dict_back_keeps_the_roster(self) -> None:
        # The crop editor saves get_character_by_id() back as-is, with members as a list.
        members, included, _price = catalog_store._normalize_ensemble_fields(
            {"ensemble_members": ["Скай", "Гонщик"], "ensemble_included_count": 2}, "character"
        )
        self.assertEqual((members, included), ("Скай, Гонщик", 2))

    def test_stored_list_literal_rosters_are_rewritten(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE managed_characters (id INTEGER PRIMARY KEY, ensemble_members TEXT)")
        connection.execute("INSERT INTO managed_characters VALUES (1, ?), (2, ?)", ("['Скай', 'Гонщик']", "Анна, Эльза"))
        catalog_store._repair_ensemble_member_values(connection)
        rows = [row["ensemble_members"] for row in connection.execute("SELECT ensemble_members FROM managed_characters ORDER BY id")]
        self.assertEqual(rows, ["Скай, Гонщик", "Анна, Эльза"])

    def test_order_roster_snapshot_is_cleaned(self) -> None:
        clean = customer_store.clean_character_name_snapshot
        self.assertEqual(clean('[\'[\\\'["[\\\\\\\'Анна\\\\\\\'"\\\'\' + \'\\\'"\\\\\\\'Эльза\\\\\\\'"\\\'\''), "Анна + Эльза")
        self.assertEqual(clean("['Скай' + 'Гонщик']"), "Скай + Гонщик")
        self.assertEqual(clean("['Ник' + 'Джуди'] (игрушка в комплекте; +300 000 сум)"), "Ник + Джуди (игрушка в комплекте; +300 000 сум)")
        self.assertEqual(clean("Скай + Гонщик"), "Скай + Гонщик")

    def test_age_is_declined_in_the_order_card(self) -> None:
        self.assertEqual(
            [admin_notifications._years_word(age) for age in (1, 3, 5, 9, 11, 21, 22)],
            ["год", "года", "лет", "лет", "лет", "год", "года"],
        )


class RescheduleTextTests(unittest.TestCase):
    def _parse(self, text: str) -> tuple[str, str, str | None]:
        return admin_notifications.parse_reschedule_text(
            text, today=date(2026, 9, 29), current_date="2026-10-05", current_time="12:00"
        )

    def test_supported_formats(self) -> None:
        self.assertEqual(self._parse("06.10 15:00"), ("2026-10-06", "15:00", None))
        self.assertEqual(self._parse("6 октября в 15:30"), ("2026-10-06", "15:30", None))
        self.assertEqual(self._parse("15.00 06.10"), ("2026-10-06", "15:00", None))
        self.assertEqual(self._parse("завтра 12:00"), ("2026-09-30", "12:00", None))
        self.assertEqual(self._parse("на 16:30"), ("2026-10-05", "16:30", None))
        self.assertEqual(self._parse("в 17"), ("2026-10-05", "17:00", None))
        self.assertEqual(self._parse("07.10"), ("2026-10-07", "12:00", None))
        self.assertEqual(self._parse("06.10 15:00-16:00"), ("2026-10-06", "15:00", "16:00"))
        self.assertEqual(self._parse("5.01 10:00"), ("2027-01-05", "10:00", None))
        self.assertEqual(self._parse("12.12.2026 11:00"), ("2026-12-12", "11:00", None))

    def test_rejects_text_without_date_or_time(self) -> None:
        with self.assertRaises(ValueError):
            self._parse("перенесите пожалуйста")
        with self.assertRaises(ValueError):
            self._parse("31.02 10:00")


class _TempDatabase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = root / "site_admin.sqlite3"
        self.patchers = [
            patch.object(customer_store, "DB_ROOT", root),
            patch.object(customer_store, "DB_PATH", self.db_path),
            patch.object(admin_notifications, "DB_ROOT", root),
            patch.object(admin_notifications, "DB_PATH", self.db_path),
            patch.object(google_calendar_store, "DB_ROOT", root),
            patch.object(google_calendar_store, "DB_PATH", self.db_path),
            patch.object(customer_store, "get_character_by_slug", _catalog_lookup),
        ]
        for patcher in self.patchers:
            patcher.start()
        customer_store.init_customer_store()
        admin_notifications.init_admin_notifications_store()
        self.day = (date.today() + timedelta(days=5)).isoformat()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _seed_order(self, public_id: str, character: str, time_from: str, time_to: str, *, status: str = "new") -> int:
        now = "2026-09-20T10:00:00+00:00"
        with self._connect() as connection:
            customer = connection.execute("SELECT id FROM customer_accounts LIMIT 1").fetchone()
            customer_id = customer["id"] if customer else connection.execute(
                """
                INSERT INTO customer_accounts(phone_normalized, phone_display, full_name, created_at, updated_at)
                VALUES ('+998330126334', '+998 (33) 012-63-34', 'Татьяна', ?, ?)
                """,
                (now, now),
            ).lastrowid
            order_id = connection.execute(
                """
                INSERT INTO party_orders(
                    public_id, customer_id, status, program_slug, program_name_snapshot, celebration_date,
                    time_from, time_to, duration_minutes, celebrant_name, celebrant_age, children_count,
                    address_text, payment_method, total_price_snapshot, created_at, updated_at
                ) VALUES (?, ?, ?, 'standard-program', 'Стандарт', ?, ?, ?, 60, 'Каролина', 9, 15,
                          'Ташкент', 'cash', 950000, ?, ?)
                """,
                (public_id, customer_id, status, self.day, time_from, time_to, now, now),
            ).lastrowid
            connection.execute(
                "INSERT INTO party_order_characters(order_id, slug, name_snapshot, sort_order, created_at) VALUES (?, ?, ?, 1, ?)",
                (order_id, character, CHARACTERS[character]["name"], now),
            )
            connection.commit()
        return int(order_id)


class RescheduleOrderTests(_TempDatabase):
    def test_moves_order_keeps_duration_and_queues_syncs(self) -> None:
        order_id = self._seed_order("SRP-00009", "paw-patrol", "12:00", "13:00")
        result = customer_store.reschedule_order(order_id, celebration_date=self.day, time_from="15:30", actor="@manager")
        self.assertTrue(result["success"], result)
        order = customer_store.get_order_by_id(order_id)
        self.assertEqual((order["time_from"], order["time_to"]), ("15:30", "16:30"))
        with self._connect() as connection:
            event = connection.execute("SELECT * FROM party_order_reschedule_events").fetchone()
            self.assertEqual((event["previous_time_from"], event["time_from"], event["actor"]), ("12:00", "15:30", "@manager"))
            self.assertIsNotNone(connection.execute("SELECT 1 FROM admin_telegram_sync_queue WHERE order_id = ?", (order_id,)).fetchone())
            self.assertIsNotNone(connection.execute("SELECT 1 FROM google_calendar_order_queue WHERE order_id = ?", (order_id,)).fetchone())

    def test_conflict_with_another_order_needs_force_but_own_slot_does_not(self) -> None:
        order_id = self._seed_order("SRP-00009", "paw-patrol", "12:00", "13:00")
        self._seed_order("SRP-00010", "paw-patrol", "16:00", "17:00")

        self.assertTrue(customer_store.reschedule_order(order_id, celebration_date=self.day, time_from="12:30")["success"])
        conflict = customer_store.reschedule_order(order_id, celebration_date=self.day, time_from="16:30")
        self.assertEqual(conflict["reason"], "conflict")
        self.assertEqual(conflict["target"]["time_to"], "17:30")
        forced = customer_store.reschedule_order(order_id, celebration_date=self.day, time_from="16:30", force=True)
        self.assertTrue(forced["success"])
        self.assertTrue(forced["forced"])

    def test_rejects_past_overnight_and_terminal_orders(self) -> None:
        order_id = self._seed_order("SRP-00009", "paw-patrol", "12:00", "13:00")
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        self.assertEqual(customer_store.reschedule_order(order_id, celebration_date=yesterday, time_from="12:00")["reason"], "past")
        self.assertEqual(customer_store.reschedule_order(order_id, celebration_date=self.day, time_from="23:30")["reason"], "overnight")
        # A manager may move a party to tomorrow: no 24 h lead time for rescheduling.
        tomorrow = (datetime.now() + timedelta(hours=26)).date().isoformat()
        self.assertTrue(customer_store.reschedule_order(order_id, celebration_date=tomorrow, time_from="10:00")["success"])
        done_id = self._seed_order("SRP-00011", "deadpool", "12:00", "13:00", status="done")
        self.assertEqual(customer_store.reschedule_order(done_id, celebration_date=self.day, time_from="15:00")["reason"], "terminal")

    def test_broken_roster_snapshots_are_repaired_on_startup(self) -> None:
        order_id = self._seed_order("SRP-00009", "paw-patrol", "12:00", "13:00")
        with self._connect() as connection:
            connection.execute("UPDATE party_order_characters SET name_snapshot = ? WHERE order_id = ?", ("['Скай' + 'Гонщик']", order_id))
            connection.commit()
        with patch.object(customer_store, "_PARTY_ORDER_SCHEMA_READY_PATH", None):
            customer_store.init_customer_store()
        self.assertEqual(customer_store.get_order_by_id(order_id)["character_names"], ["Скай + Гонщик"])
        text = admin_notifications._format_order_message(customer_store.get_order_by_id(order_id))
        self.assertIn("Стандарт (Скай + Гонщик)", text)
        self.assertIn("Каролина 9 лет", text)


class TelegramRescheduleFlowTests(_TempDatabase):
    CHAT = "555"

    def setUp(self) -> None:
        super().setUp()
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO admin_telegram_recipients(chat_id, label, is_active, created_at, updated_at) VALUES (?, 'Менеджеры', 1, 'x', 'x')",
                (self.CHAT,),
            )
            connection.commit()
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.answers: list[str] = []

        def send(chat_id: str, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
            self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
            return {"success": True, "result": {"message_id": 1000 + len(self.sent)}}

        def edit(chat_id: str, message_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> dict[str, Any]:
            self.edited.append({"message_id": message_id, "text": text, "reply_markup": reply_markup})
            return {"success": True}

        self.flow_patchers = [
            patch.object(admin_notifications, "_send_telegram_message", send),
            patch.object(admin_notifications, "_edit_telegram_message", edit),
            patch.object(admin_notifications, "_answer_callback", lambda _cid, text="": self.answers.append(text) or {"success": True}),
            patch.object(admin_notifications, "sync_order_messages", lambda order_id: {"success": True}),
            patch.object(admin_notifications, "_wake_calendar_sync", lambda: None),
        ]
        for patcher in self.flow_patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.flow_patchers):
            patcher.stop()
        super().tearDown()

    def _callback(self, data: str, message_id: int = 1) -> dict[str, Any]:
        return admin_notifications.handle_callback(
            {
                "callback_query": {
                    "id": "cb",
                    "data": data,
                    "from": {"id": 7, "username": "manager"},
                    "message": {"message_id": message_id, "chat": {"id": int(self.CHAT)}},
                }
            }
        )

    def _reply(self, text: str, to_message_id: int) -> dict[str, Any]:
        return admin_notifications.handle_callback(
            {
                "message": {
                    "chat": {"id": int(self.CHAT)},
                    "from": {"id": 7, "username": "manager", "first_name": "Менеджер"},
                    "text": text,
                    "reply_to_message": {"message_id": to_message_id},
                }
            }
        )

    def test_card_offers_reschedule_button(self) -> None:
        keyboard = admin_notifications._build_order_keyboard("SRP-00009", 9, "unconfirmed", "new")
        self.assertEqual(keyboard["inline_keyboard"][1][0]["callback_data"], "order:SRP-00009:reschedule")
        self.assertEqual(admin_notifications._build_order_keyboard("SRP-00009", 9, "confirmed", "cancelled"), {"inline_keyboard": []})

    def test_manager_moves_order_by_replying_to_the_bot(self) -> None:
        order_id = self._seed_order("SRP-00009", "paw-patrol", "12:00", "13:00")
        self.assertTrue(self._callback("order:SRP-00009:reschedule")["success"])
        prompt = self.sent[-1]
        self.assertTrue(prompt["reply_markup"]["force_reply"])
        self.assertIn("Перенос заказа SRP-00009", prompt["text"])

        target = datetime.strptime(self.day, "%Y-%m-%d")
        result = self._reply(f"{target:%d.%m} 15:00", 1000 + len(self.sent))
        self.assertTrue(result["success"], result)
        order = customer_store.get_order_by_id(order_id)
        self.assertEqual((order["time_from"], order["time_to"]), ("15:00", "16:00"))
        self.assertIn("перенесён", self.sent[-1]["text"])
        self.assertIn("+998 (33) 012-63-34", self.sent[-1]["text"])

    def test_conflict_asks_before_forcing_and_cancel_word_stops(self) -> None:
        order_id = self._seed_order("SRP-00009", "paw-patrol", "12:00", "13:00")
        self._seed_order("SRP-00010", "paw-patrol", "16:00", "17:00")
        self._callback("order:SRP-00009:reschedule")
        self._reply("в 16:30", 1000 + len(self.sent))
        warning = self.sent[-1]
        self.assertIn("пересечение", warning["text"])
        force_data = warning["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
        self.assertEqual(customer_store.get_order_by_id(order_id)["time_from"], "12:00")

        self.assertTrue(self._callback(force_data, message_id=1000 + len(self.sent))["success"])
        self.assertEqual(customer_store.get_order_by_id(order_id)["time_from"], "16:30")
        self.assertIn("несмотря на пересечение", self.edited[-1]["text"])

        self._callback("order:SRP-00009:reschedule")
        self._reply("отмена", 1000 + len(self.sent))
        self.assertIn("отменён", self.sent[-1]["text"])
        self.assertEqual(customer_store.get_order_by_id(order_id)["time_from"], "16:30")

    def test_unreadable_reply_asks_again(self) -> None:
        self._seed_order("SRP-00009", "paw-patrol", "12:00", "13:00")
        self._callback("order:SRP-00009:reschedule")
        first_prompt = 1000 + len(self.sent)
        self._reply("когда-нибудь потом", first_prompt)
        self.assertIn("Не нашёл дату или время", self.sent[-1]["text"])
        self.assertTrue(self.sent[-1]["reply_markup"]["force_reply"])
        # The new prompt is the one to answer now.
        self.assertIsNotNone(admin_notifications._find_reschedule_session(self.CHAT, 1000 + len(self.sent)))


if __name__ == "__main__":
    unittest.main()
