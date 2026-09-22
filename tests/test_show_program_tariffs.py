from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import addon_store, catalog_store, customer_store


class ShowProgramTariffTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.db_root = self.root / "data"
        self.db_path = self.db_root / "site_admin.sqlite3"
        self.routes_root = self.root / "routes"
        self.routes_root.mkdir(parents=True)
        self.patchers = (
            patch.object(catalog_store, "DB_ROOT", self.db_root),
            patch.object(catalog_store, "DB_PATH", self.db_path),
            patch.object(catalog_store, "CHARACTER_ROUTES_ROOT", self.routes_root),
            patch.object(addon_store, "DB_PATH", self.db_path),
            patch.object(customer_store, "DB_ROOT", self.db_root),
            patch.object(customer_store, "DB_PATH", self.db_path),
            patch.object(customer_store, "_PARTY_ORDER_SCHEMA_READY_PATH", None),
        )
        for current_patcher in self.patchers:
            current_patcher.start()

        catalog_store.init_catalog_store()
        addon_store.init_addon_store()

    def tearDown(self) -> None:
        for current_patcher in reversed(self.patchers):
            current_patcher.stop()
        self.temporary_directory.cleanup()

    def _show(self, slug: str) -> dict[str, object]:
        show = catalog_store.get_character_by_slug(slug, include_hidden=True)
        self.assertIsNotNone(show, slug)
        return show

    def test_catalog_contains_the_approved_prices_durations_and_extra_rates(self) -> None:
        expected = {
            "standard-program": (950_000, 60, 2, 350_000, "active"),
            "ribbon-show": (1_400_000, 60, 2, 350_000, "active"),
            "paper-ribbon-show": (1_500_000, 60, 2, 350_000, "hidden"),
            "streamer-show": (1_400_000, 60, 2, 350_000, "active"),
            "neon-start": (1_500_000, 60, 2, 0, "active"),
            "neon-medium": (1_850_000, 60, 2, 0, "active"),
            "neon-lux": (2_100_000, 60, 3, 0, "active"),
            "squid-game-60": (1_300_000, 60, 3, 0, "active"),
            "squid-game-90": (1_700_000, 90, 3, 0, "active"),
            "atmosphere-program": (450_000, 60, 1, 450_000, "active"),
            "greeting-program": (400_000, 15, 1, 250_000, "active"),
            "cryo-show": (975_000, 30, 0, 0, "hidden"),
            "bubble-show": (975_000, 30, 0, 0, "hidden"),
            "aqua-face-paint": (575_000, 60, 0, 0, "hidden"),
        }

        for slug, values in expected.items():
            with self.subTest(slug=slug):
                show = self._show(slug)
                actual = (
                    show["base_price"],
                    show["default_duration_minutes"],
                    show["included_characters_count"],
                    show["extra_character_price_3"],
                    show["status"],
                )
                self.assertEqual(actual, values)
                self.assertEqual(show["extra_character_price_4_plus"], values[3])

        for slug in ("ribbon-show", "paper-ribbon-show", "streamer-show"):
            self.assertIn("закрытом помещении", self._show(slug)["restrictions"])

        self.assertIn("2 неоновых прожектора", self._show("neon-start")["included_items"])
        self.assertIn("аквагример работает 1 час до начала", self._show("neon-medium")["included_items"])
        self.assertIn("неоновые браслеты", self._show("neon-lux")["included_items"])
        self.assertIn("фиксированный состав из 3 артистов", self._show("squid-game-60")["included_items"])
        self.assertIn("1 химик", self._show("cryo-show")["included_items"])
        self.assertIn("огромные пузыри", self._show("bubble-show")["included_items"])
        self.assertIn("10–15 рисунков", self._show("aqua-face-paint")["included_items"])
        self.assertEqual(
            catalog_store.FIXED_CAST_PROGRAM_DETAILS["neon-start"],
            ("Неоновый ведущий", "Неоновая ведущая"),
        )
        self.assertEqual(
            catalog_store.FIXED_CAST_PROGRAM_DETAILS["neon-medium"],
            ("Неоновый ведущий", "Неоновая ведущая"),
        )

        public_slugs = {
            item["slug"]
            for item in catalog_store.list_characters_for_public(
                entity_type=catalog_store.ENTITY_TYPE_SHOW_PROGRAM
            )
        }
        self.assertTrue({"standard-program", "neon-lux", "squid-game-90"}.issubset(public_slugs))
        self.assertTrue(
            {"paper-ribbon-show", "cryo-show", "bubble-show", "aqua-face-paint"}.isdisjoint(
                public_slugs
            )
        )

    def test_tariff_sync_is_idempotent_and_does_not_override_later_admin_edits(self) -> None:
        with catalog_store._get_connection() as connection:
            connection.execute(
                "UPDATE managed_characters SET base_price = 1 WHERE slug = 'standard-program'"
            )
            connection.commit()

        result = catalog_store.sync_show_program_tariffs()

        self.assertFalse(result["changed"])
        self.assertEqual(result["reason"], "already_synced")
        self.assertEqual(self._show("standard-program")["base_price"], 1)

    def test_restart_legacy_sync_preserves_managed_show_entity_types(self) -> None:
        catalog_store._sync_entity_types_from_legacy()

        for slug in ("standard-program", "neon-start", "squid-game-60"):
            with self.subTest(slug=slug):
                self.assertEqual(
                    self._show(slug)["entity_type"],
                    catalog_store.ENTITY_TYPE_SHOW_PROGRAM,
                )

    def test_legacy_cards_keep_their_ids_and_media_and_variants_reuse_approved_photos(self) -> None:
        replaced_slugs = (
            "standard-program",
            "neon-start",
            "neon-medium",
            "neon-lux",
            "atmosphere-program",
            "squid-game-60",
            "squid-game-90",
        )
        with catalog_store._get_connection() as connection:
            placeholders = ", ".join("?" for _ in replaced_slugs)
            connection.execute(
                f"DELETE FROM managed_characters WHERE slug IN ({placeholders})",
                replaced_slugs,
            )
            connection.execute(
                "DELETE FROM managed_meta WHERE key = ?",
                (catalog_store.SHOW_PROGRAM_TARIFFS_META_KEY,),
            )
            connection.commit()

        legacy_ids: dict[str, int] = {}
        for slug in ("jesters", "neon-jesters", "balloon-show"):
            legacy_ids[slug] = catalog_store.create_character(
                {
                    "name": slug,
                    "slug": slug,
                    "entity_type": catalog_store.ENTITY_TYPE_SHOW_PROGRAM,
                    "status": "active",
                    "category_ids": [],
                    "tag_ids": [],
                }
            )

        cryo_id = int(self._show("cryo-show")["id"])
        with catalog_store._get_connection() as connection:
            now = catalog_store.utcnow_iso()
            media_targets = {**legacy_ids, "cryo-show": cryo_id}
            for slug, character_id in media_targets.items():
                cursor = connection.execute(
                    """
                    INSERT INTO managed_character_media(
                        character_id, media_type, file_path, alt_text, caption,
                        sort_order, created_at, updated_at
                    ) VALUES (?, 'image', ?, ?, '', 1, ?, ?)
                    """,
                    (character_id, f"/media/{slug}.webp", slug, now, now),
                )
                connection.execute(
                    "UPDATE managed_characters SET hero_media_id = ? WHERE id = ?",
                    (int(cursor.lastrowid), character_id),
                )
            connection.commit()

        result = catalog_store.sync_show_program_tariffs()

        self.assertTrue(result["changed"])
        aliases = {
            "standard-program": "jesters",
            "neon-start": "neon-jesters",
            "atmosphere-program": "balloon-show",
        }
        for canonical_slug, legacy_slug in aliases.items():
            with self.subTest(canonical_slug=canonical_slug):
                canonical = self._show(canonical_slug)
                self.assertEqual(canonical["id"], legacy_ids[legacy_slug])
                expected_media = {
                    "standard-program": "/surpriz/assets/img/show-programs/cards/standard-program-1200.webp",
                    "neon-start": "/surpriz/assets/img/show-programs/cards/neon-start-1200.webp",
                    "atmosphere-program": "/surpriz/assets/img/show-programs/cards/atmosphere-program-1200.webp",
                }[canonical_slug]
                self.assertEqual(canonical["hero_file_path"], expected_media)
                self.assertIsNone(
                    catalog_store.get_character_by_slug(legacy_slug, include_hidden=True)
                )

        for slug in ("neon-medium", "neon-lux"):
            self.assertEqual(
                self._show(slug)["hero_file_path"],
                f"/surpriz/assets/img/show-programs/cards/{slug}-1200.webp",
            )
        for slug in ("ribbon-show", "streamer-show"):
            self.assertEqual(
                self._show(slug)["hero_file_path"],
                f"/surpriz/assets/img/show-programs/cards/{slug}-1200.webp",
            )
        for slug in ("squid-game-60", "squid-game-90"):
            self.assertEqual(
                self._show(slug)["hero_file_path"],
                "/surpriz/assets/img/characters/squid-game-1200.webp",
            )
        for slug in ("greeting-program", "cryo-show", "bubble-show", "aqua-face-paint"):
            self.assertEqual(self._show(slug)["hero_file_path"], "")

    def test_free_choice_and_greeting_dj_links_are_seeded_with_fixed_prices(self) -> None:
        for program_slug in addon_store.FREE_GIFT_PROGRAM_SLUGS:
            with self.subTest(program_slug=program_slug):
                program = self._show(program_slug)
                addons = addon_store.list_program_addons_for_public(int(program["id"]))
                gifts = [addon for addon in addons if addon["gift_mode"] == "choice_one"]
                self.assertEqual([addon["slug"] for addon in gifts], ["party-masks", "party-balloons"])
                self.assertEqual({addon["gift_group"] for addon in gifts}, {"masks-or-balloons"})
                self.assertTrue(all(addon["price"] == 0 for addon in gifts))

        greeting = self._show("greeting-program")
        greeting_addons = addon_store.list_program_addons_for_public(int(greeting["id"]))
        self.assertEqual(
            [(addon["slug"], addon["price"], addon["gift_mode"]) for addon in greeting_addons],
            [("greeting-dj", 300_000, "none")],
        )

    def test_server_totals_scale_base_and_generic_artists_but_not_fixed_extras(self) -> None:
        standard = self._show("standard-program")
        three_solo_characters = [{"slug": slug, "ensemble_members": []} for slug in ("a", "b", "c")]
        self.assertEqual(
            customer_store.scale_price_for_duration(standard["base_price"], 90, 60),
            1_425_000,
        )
        self.assertEqual(
            customer_store.calculate_order_character_surcharge(
                standard,
                three_solo_characters,
                {},
                actual_duration_minutes=90,
                base_duration_minutes=60,
            ),
            525_000,
        )

        grouped_character = {
            "slug": "trio",
            "ensemble_members": ["Анна", "Эльза", "Олаф"],
            "ensemble_included_count": 2,
            "ensemble_extra_member_price": 0,
        }
        grouped_selection = {"trio": ["Анна", "Эльза", "Олаф"]}
        self.assertEqual(
            customer_store.calculate_order_character_surcharge(
                standard,
                [grouped_character],
                grouped_selection,
                actual_duration_minutes=120,
                base_duration_minutes=60,
            ),
            700_000,
        )

    def test_order_pipeline_keeps_dj_fixed_when_greeting_duration_doubles(self) -> None:
        customer_store.init_customer_store()
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
            customer_id = int(cursor.lastrowid)
            connection.commit()

        character_ids = [
            catalog_store.create_character(
                {
                    "name": f"Персонаж {index}",
                    "slug": f"greeting-character-{index}",
                    "entity_type": catalog_store.ENTITY_TYPE_CHARACTER,
                    "status": "active",
                    "category_ids": [],
                    "tag_ids": [],
                }
            )
            for index in (1, 2)
        ]
        self.assertEqual(len(character_ids), 2)

        form = {
            "program_slug": "greeting-program",
            "character_slugs": ["greeting-character-1", "greeting-character-2"],
            "addon_slugs": ["greeting-dj", "greeting-dj"],
            "celebration_date": "2099-09-01",
            "time_from": "14:00",
            "time_to": "14:30",
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
            patch.object(
                customer_store,
                "check_character_availability",
                return_value={"success": True, "available": True},
            ),
        ):
            result = customer_store.create_party_order(customer_id, form)

        self.assertTrue(result["success"], result)
        self.assertEqual(result["order"]["total_price"], 1_600_000)
        self.assertEqual(result["order"]["addon_total"], 300_000)
        self.assertEqual([addon["slug"] for addon in result["order"]["addons"]], ["greeting-dj"])

        free_gift_form = {
            **form,
            "program_slug": "standard-program",
            "character_slugs": ["greeting-character-1", "greeting-character-2"],
            "addon_slugs": [],
            "gift_choices": {"masks-or-balloons": "party-masks"},
            "time_from": "18:00",
            "time_to": "19:00",
        }
        with (
            patch.object(customer_store, "get_customer_block_status", return_value=None),
            patch.object(
                customer_store,
                "check_character_availability",
                return_value={"success": True, "available": True},
            ),
        ):
            free_gift_result = customer_store.create_party_order(customer_id, free_gift_form)

        self.assertTrue(free_gift_result["success"], free_gift_result)
        self.assertEqual(free_gift_result["order"]["total_price"], 950_000)
        self.assertEqual(free_gift_result["order"]["addon_total"], 0)
        self.assertIn("[Подарок: Маски]", free_gift_result["order"]["notes"])

        fixed_cast_form = {
            **form,
            "program_slug": "squid-game-60",
            "character_slugs": ["greeting-character-1"],
            "addon_slugs": [],
            "time_from": "16:00",
            "time_to": "17:00",
        }
        with (
            patch.object(customer_store, "get_customer_block_status", return_value=None),
            patch.object(
                customer_store,
                "check_character_availability",
                return_value={"success": True, "available": True},
            ),
        ):
            rejected = customer_store.create_party_order(customer_id, fixed_cast_form)

        self.assertFalse(rejected["success"])
        self.assertIn("character_slugs", rejected["errors"])


if __name__ == "__main__":
    unittest.main()
