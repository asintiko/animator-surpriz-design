from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import addon_store, admin_store, catalog_store, customer_store, promotion_store


class PromotionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.db_root = self.root / "data"
        self.db_path = self.db_root / "site_admin.sqlite3"
        routes_root = self.root / "routes"
        routes_root.mkdir(parents=True)
        self.patchers = (
            patch.object(catalog_store, "DB_ROOT", self.db_root),
            patch.object(catalog_store, "DB_PATH", self.db_path),
            patch.object(catalog_store, "CHARACTER_ROUTES_ROOT", routes_root),
            patch.object(addon_store, "DB_PATH", self.db_path),
            patch.object(admin_store, "DB_PATH", self.db_path),
            patch.object(promotion_store, "DB_PATH", self.db_path),
            patch.object(customer_store, "DB_ROOT", self.db_root),
            patch.object(customer_store, "DB_PATH", self.db_path),
            patch.object(customer_store, "_PARTY_ORDER_SCHEMA_READY_PATH", None),
        )
        for current_patcher in self.patchers:
            current_patcher.start()

        catalog_store.init_catalog_store()
        addon_store.init_addon_store()
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS site_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
        promotion_store.init_promotion_store()
        self.standard = catalog_store.get_character_by_slug("standard-program", include_hidden=True)
        self.ribbon = catalog_store.get_character_by_slug("ribbon-show", include_hidden=True)

    def tearDown(self) -> None:
        for current_patcher in reversed(self.patchers):
            current_patcher.stop()
        self.temporary_directory.cleanup()

    def _enable_promotions(self, enabled: bool = True) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO site_settings(key, value, updated_at) VALUES ('show_promotions', ?, '')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("1" if enabled else "0",),
            )

    def _standard_program(self) -> dict[str, object]:
        return next(item for item in customer_store.list_show_programs_for_public() if item["slug"] == "standard-program")

    def _public_addon_slugs(self) -> set[str]:
        return {addon["slug"] for addon in addon_store.list_program_addons_for_public(int(self.standard["id"]))}

    def _face_paint_promotion(self) -> dict[str, object]:
        return next(
            item for item in promotion_store.list_promotions(include_hidden=True) if item["title"] == "Аквагрим со скидкой"
        )

    def test_seed_creates_the_two_running_standard_offers(self) -> None:
        promotions = promotion_store.list_promotions(include_hidden=True)

        self.assertEqual([item["title"] for item in promotions], ["Мини-лента шоу в подарок", "Аквагрим со скидкой"])
        self.assertTrue(all(item["is_featured"] for item in promotions))
        self.assertTrue(all(item["program_ids"] == [self.standard["id"]] for item in promotions))
        face_paint = promotions[1]
        self.assertEqual((face_paint["addon_slug"], face_paint["addon_price"], face_paint["old_price"]), ("aqua-face-paint-addon", 250_000, 575_000))

        links = addon_store.get_program_addon_settings(int(self.standard["id"]))
        gift = addon_store.get_addon_by_slug("mini-ribbon-show")
        paint = addon_store.get_addon_by_slug("aqua-face-paint-addon")
        self.assertEqual(links[int(gift["id"])]["gift_mode"], "bundle_all")
        self.assertEqual(links[int(paint["id"])]["gift_mode"], "none")
        self.assertEqual(paint["price"], 250_000)

    def test_seed_runs_once_and_never_restores_deleted_offers(self) -> None:
        for promotion in promotion_store.list_promotions(include_hidden=True):
            promotion_store.delete_promotion(promotion["id"])

        result = promotion_store.seed_current_promotions()

        self.assertEqual(result["reason"], "already_seeded")
        self.assertEqual(promotion_store.list_promotions(include_hidden=True), [])

    def test_seed_leaves_a_service_the_show_already_sells_alone(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("DELETE FROM managed_meta WHERE key = ?", (promotion_store.PROMOTIONS_SEED_META_KEY,))
            connection.execute("DELETE FROM promotions")
            connection.execute(
                "DELETE FROM show_program_addons WHERE addon_id IN "
                "(SELECT id FROM show_addons WHERE slug IN ('mini-ribbon-show', 'aqua-face-paint-addon'))"
            )
            connection.execute("DELETE FROM show_addons WHERE slug IN ('mini-ribbon-show', 'aqua-face-paint-addon')")
        own_id = addon_store.create_addon({"name": "аквагрим", "slug": "akvagrim", "status": "active", "price": 575_000})
        addon_store.set_program_addons(
            int(self.standard["id"]),
            [*({"addon_id": addon_id, **settings} for addon_id, settings in addon_store.get_program_addon_settings(int(self.standard["id"])).items()),
             {"addon_id": own_id, "gift_mode": "none"}],
        )

        result = promotion_store.seed_current_promotions()

        self.assertEqual(result["skipped"], ["Аквагрим со скидкой"])
        self.assertIsNone(addon_store.get_addon_by_slug("aqua-face-paint-addon"))
        self.assertEqual([item["title"] for item in promotion_store.list_promotions(include_hidden=True)], ["Мини-лента шоу в подарок"])

    def test_update_keeps_show_links_unless_the_payload_carries_them(self) -> None:
        promotion = promotion_store.list_promotions(include_hidden=True)[0]

        promotion_store.update_promotion(promotion["id"], {**promotion, "program_ids": None, "status": "hidden"})
        self.assertEqual(promotion_store.get_promotion_by_id(promotion["id"])["program_ids"], [self.standard["id"]])

        promotion_store.update_promotion(promotion["id"], {**promotion, "program_ids": [self.ribbon["id"], 999_999]})
        self.assertEqual(promotion_store.get_promotion_by_id(promotion["id"])["program_ids"], [self.ribbon["id"]])

    def test_partial_update_keeps_fields_it_does_not_mention(self) -> None:
        promotion = self._face_paint_promotion()

        promotion_store.update_promotion(promotion["id"], {"title": "Аквагрим дешевле", "status": "active"})
        updated = promotion_store.get_promotion_by_id(promotion["id"])

        self.assertEqual(updated["title"], "Аквагрим дешевле")
        self.assertEqual(
            (updated["is_featured"], updated["addon_id"], updated["old_price"], updated["program_ids"]),
            (True, promotion["addon_id"], 575_000, [self.standard["id"]]),
        )

    def test_featured_list_skips_unfeatured_and_unlinked_promotions(self) -> None:
        promotion_store.create_promotion({"title": "Без шоу", "badge_text": "Без шоу", "is_featured": True})
        promotion_store.create_promotion(
            {"title": "Обычная", "badge_text": "Обычная", "is_featured": False, "program_ids": [self.ribbon["id"]]}
        )

        titles = [item["title"] for item in promotion_store.list_featured_promotions_for_public()]

        self.assertEqual(titles, ["Мини-лента шоу в подарок", "Аквагрим со скидкой"])

    def test_promotion_about_a_detached_or_hidden_service_is_not_advertised(self) -> None:
        paint = addon_store.get_addon_by_slug("aqua-face-paint-addon")
        promotion_store.update_promotion(self._face_paint_promotion()["id"], {"program_ids": [self.standard["id"], self.ribbon["id"]]})

        featured = {item["title"]: item for item in promotion_store.list_featured_promotions_for_public()}
        self.assertEqual(featured["Аквагрим со скидкой"]["program_ids"], [self.standard["id"]])
        self.assertEqual(promotion_store.list_program_promotions_for_public(int(self.ribbon["id"])), [])

        addon_store.update_addon_status(int(paint["id"]), "hidden")

        self.assertNotIn("Аквагрим со скидкой", [item["title"] for item in promotion_store.list_featured_promotions_for_public()])
        self.assertEqual(
            [item["title"] for item in promotion_store.list_program_promotions_for_public(int(self.standard["id"]))],
            ["Мини-лента шоу в подарок"],
        )

    def test_promo_services_are_sold_only_while_the_offer_runs(self) -> None:
        self.assertFalse({"mini-ribbon-show", "aqua-face-paint-addon"} & self._public_addon_slugs())

        self._enable_promotions()
        self.assertTrue({"mini-ribbon-show", "aqua-face-paint-addon"} <= self._public_addon_slugs())

        promotion_store.update_promotion(self._face_paint_promotion()["id"], {"status": "hidden"})
        self.assertIn("mini-ribbon-show", self._public_addon_slugs())
        self.assertNotIn("aqua-face-paint-addon", self._public_addon_slugs())

    def test_site_switch_hides_every_promotion(self) -> None:
        self.assertEqual(self._standard_program()["promotions"], [])

        self._enable_promotions()
        program = self._standard_program()

        self.assertEqual(len(program["promotions"]), 2)
        face_paint = next(addon for addon in program["paid_addons"] if addon["slug"] == "aqua-face-paint-addon")
        self.assertEqual(face_paint["promo_badge"], "Аквагрим за 250 000")
        self.assertEqual(face_paint["promo_old_price_label"], "575 000 сум")
        ribbon_gift = next(addon for addon in program["gift_bundles"] if addon["slug"] == "mini-ribbon-show")
        self.assertEqual(ribbon_gift["promo_badge"], "Мини-лента шоу в подарок")

    def test_order_charges_the_promo_price_and_refuses_it_once_the_offer_ends(self) -> None:
        customer_store.init_customer_store()
        with sqlite3.connect(self.db_path) as connection:
            customer_id = int(
                connection.execute(
                    """
                    INSERT INTO customer_accounts(
                        phone_normalized, phone_display, full_name, preferred_auth_channel,
                        phone_verified_at, created_at, updated_at
                    ) VALUES ('998901234567', '+998 (90) 123-45-67', 'Клиент', 'telegram', '', '', '')
                    """
                ).lastrowid
            )
        form = {
            "program_slug": "standard-program",
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
            "addon_slugs": ["aqua-face-paint-addon"],
            "gift_choices": {"masks-or-balloons": "party-balloons"},
        }
        # Heroes are not part of this check; the real program row keeps its id, price and add-ons.
        program = {**self.standard, "included_characters_count": 0}

        def create() -> dict[str, object]:
            with (
                patch.object(customer_store, "get_customer_block_status", return_value=None),
                patch.object(customer_store, "get_character_by_slug", return_value=program),
                patch.object(customer_store, "check_character_availability", return_value={"success": True, "available": True}),
            ):
                return customer_store.create_party_order(customer_id, dict(form))

        self._enable_promotions()
        result = create()
        self.assertTrue(result["success"], result)
        self.assertEqual(result["order"]["addon_total"], 250_000)
        self.assertIn("[Подарок: Мини-лента шоу]", result["order"]["notes"])

        self._enable_promotions(False)
        refused = create()
        self.assertFalse(refused["success"])
        self.assertIn("addon_slugs", refused["errors"])


if __name__ == "__main__":
    unittest.main()
