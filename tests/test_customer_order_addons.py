from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core import addon_store, customer_store


class CustomerOrderAddonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.db_path = Path(self.temporary_directory.name) / "site_admin.sqlite3"
        self.patches = (
            patch.object(customer_store, "DB_PATH", self.db_path),
            patch.object(customer_store, "DB_ROOT", self.db_path.parent),
            patch.object(customer_store, "_PARTY_ORDER_SCHEMA_READY_PATH", None),
            patch.object(addon_store, "DB_PATH", self.db_path),
        )
        for current_patch in self.patches:
            current_patch.start()

        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "CREATE TABLE managed_characters(id INTEGER PRIMARY KEY, entity_type TEXT NOT NULL)"
            )
            connection.executemany(
                "INSERT INTO managed_characters(id, entity_type) VALUES (?, ?)",
                [
                    (10, customer_store.ENTITY_TYPE_SHOW_PROGRAM),
                    (11, customer_store.ENTITY_TYPE_SHOW_PROGRAM),
                ],
            )
            connection.commit()

        customer_store.init_customer_store()
        addon_store.init_addon_store()
        now = "2026-08-07T10:00:00+00:00"
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO customer_accounts(
                    phone_normalized, phone_display, full_name, preferred_auth_channel,
                    phone_verified_at, created_at, updated_at
                ) VALUES ('998901234567', '+998 (90) 123-45-67', 'Клиент', 'telegram', ?, ?, ?)
                """,
                (now, now, now),
            )
            self.customer_id = int(cursor.lastrowid)
            connection.commit()

        self.popcorn_id = addon_store.create_addon(
            {
                "name": "Попкорн",
                "slug": "popcorn",
                "status": "active",
                "price": 200_000,
                "duration_minutes": 15,
            }
        )
        self.gift_id = addon_store.create_addon(
            {"name": "Шарики", "slug": "balloons", "status": "active", "price": 90_000}
        )
        self.bundle_id = addon_store.create_addon(
            {"name": "Наклейки", "slug": "stickers", "status": "active", "price": 40_000}
        )
        self.unlinked_id = addon_store.create_addon(
            {"name": "Фотограф", "slug": "photo", "status": "active", "price": 300_000}
        )
        self.hidden_id = addon_store.create_addon(
            {"name": "Скрытая", "slug": "hidden", "status": "hidden", "price": 500_000}
        )
        addon_store.set_program_addons(
            10,
            [
                {"addon_id": self.popcorn_id, "gift_mode": "none", "sort_order": 3},
                {
                    "addon_id": self.gift_id,
                    "gift_mode": "choice_one",
                    "gift_group": "default",
                    "sort_order": 4,
                },
                {"addon_id": self.bundle_id, "gift_mode": "bundle_all", "sort_order": 5},
                {"addon_id": self.hidden_id, "gift_mode": "none", "sort_order": 6},
            ],
        )

        self.program = {
            "id": 10,
            "slug": "cryo-show",
            "name": "Крио шоу",
            "entity_type": customer_store.ENTITY_TYPE_SHOW_PROGRAM,
            "base_price": 1_000_000,
            "included_characters_count": 2,
            "extra_character_price_3": 200_000,
            "extra_character_price_4_plus": 200_000,
        }

    def tearDown(self) -> None:
        for current_patch in reversed(self.patches):
            current_patch.stop()
        self.temporary_directory.cleanup()

    def _form(self, **updates: object) -> dict[str, object]:
        data: dict[str, object] = {
            "program_slug": "cryo-show",
            "character_slugs": [],
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
        data.update(updates)
        return data

    def _create(self, **updates: object) -> dict[str, object]:
        with (
            patch.object(customer_store, "get_customer_block_status", return_value=None),
            patch.object(customer_store, "get_character_by_slug", return_value=self.program),
            patch.object(customer_store, "get_program_duration_minutes", return_value=60),
            patch.object(
                customer_store,
                "check_character_availability",
                return_value={"success": True, "available": True},
            ),
        ):
            return customer_store.create_party_order(self.customer_id, self._form(**updates))

    def test_paid_addon_is_deduped_priced_once_and_kept_as_a_snapshot(self) -> None:
        result = self._create(
            addon_slugs=["popcorn", "popcorn"],
            gift_choices={"default": "balloons"},
        )

        self.assertTrue(result["success"], result)
        order = result["order"]
        self.assertEqual(order["total_price"], 1_200_000)
        self.assertEqual(order["addon_total"], 200_000)
        self.assertEqual(order["addon_total_label"], "200 000 сум")
        self.assertEqual([addon["slug"] for addon in order["addons"]], ["popcorn"])
        self.assertIn("[Подарок: Шарики]", order["notes"])
        self.assertIn("[Подарок: Наклейки]", order["notes"])

        current = addon_store.get_addon_by_id(self.popcorn_id)
        addon_store.update_addon(
            self.popcorn_id,
            {**current, "name": "Попкорн XL", "price": 999_000},
        )
        reread = customer_store.get_order_by_id(order["id"])
        self.assertEqual(reread["total_price"], 1_200_000)
        self.assertEqual(reread["addons"][0]["name"], "Попкорн")
        self.assertEqual(reread["addons"][0]["price"], 200_000)

        with sqlite3.connect(self.db_path) as connection:
            snapshot = connection.execute(
                "SELECT addon_id, slug, name, price, duration_minutes, sort_order FROM party_order_addons"
            ).fetchone()
        self.assertEqual(snapshot, (self.popcorn_id, "popcorn", "Попкорн", 200_000, 15, 1))

    def test_hidden_unlinked_and_gift_addons_cannot_be_ordered_as_paid(self) -> None:
        for slug in ("hidden", "photo", "balloons", "stickers", "missing"):
            with self.subTest(slug=slug):
                result = self._create(addon_slugs=[slug])
                self.assertFalse(result["success"])
                self.assertIn("addon_slugs", result["errors"])

        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM party_orders").fetchone()[0], 0)

    def test_free_gift_choice_must_match_the_selected_show_and_is_not_charged(self) -> None:
        missing = self._create()
        self.assertFalse(missing["success"])
        self.assertEqual(
            missing["errors"]["gift_choices"],
            "Выберите обязательный подарок: маски или шары.",
        )

        valid = self._create(gift_choices={"default": "balloons"})
        self.assertTrue(valid["success"], valid)
        self.assertEqual(valid["order"]["total_price"], 1_000_000)
        self.assertEqual(valid["order"]["addon_total"], 0)
        self.assertEqual(valid["order"]["addons"], [])

        invalid_slug = self._create(gift_choices={"default": "photo"})
        self.assertFalse(invalid_slug["success"])
        self.assertIn("gift_choices", invalid_slug["errors"])

        invalid_group = self._create(gift_choices={"other": "balloons"})
        self.assertFalse(invalid_group["success"])
        self.assertIn("gift_choices", invalid_group["errors"])


if __name__ == "__main__":
    unittest.main()
