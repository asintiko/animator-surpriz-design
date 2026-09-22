from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from webapp.adapter import app as adapter_app


class AdminEntityRoundTripTest(unittest.TestCase):
    def test_crop_round_trip_persists_and_clamps_image_zoom(self) -> None:
        state = {
            "id": 7,
            "name": "Тестовый герой",
            "slug": "test-hero",
            "entity_type": "character",
            "status": "active",
            "cover_offset_x": 50,
            "cover_offset_y": 50,
            "cover_fit": "cover",
            "image_zoom": 100,
            "mobile_cover_offset_x": 50,
            "mobile_cover_offset_y": 50,
            "mobile_cover_fit": "cover",
            "mobile_image_zoom": 100,
            "categories": ["all"],
            "tags": ["all"],
        }

        def update_character(_entity_id: int, values: dict) -> None:
            state.update(values)

        with (
            patch.dict(os.environ, {"SURPRIZ_ADMIN_SECRET": "test-secret", "SURPRIZ_ADAPTER_TOKEN": "test-token"}),
            patch.multiple(
                adapter_app,
                _initialize_idempotency_database=lambda: None,
                init_customer_store=lambda: None,
                _ensure_customer_admin_columns=lambda: None,
                init_addon_store=lambda: None,
                init_promotion_store=lambda: None,
                init_admin_notifications_store=lambda: None,
                get_admin_by_id=lambda _admin_id: {"id": 1, "username": "admin"},
                get_character_by_id=lambda entity_id: dict(state) if entity_id == 7 else None,
                update_character=update_character,
            ),
        ):
            application = adapter_app.create_app()
            application.config.update(TESTING=True)
            client = application.test_client()
            with client.session_transaction() as session:
                session[adapter_app.ADMIN_SESSION_KEY] = 1
            headers = {"X-Adapter-Token": "test-token"}

            saved = client.post(
                "/api/v2/admin/entities/7/crop",
                headers=headers,
                json={
                    "cover_offset_x": 35,
                    "cover_offset_y": 62,
                    "cover_fit": "cover",
                    "image_zoom": 150,
                    "mobile_cover_offset_x": 28,
                    "mobile_cover_offset_y": 74,
                    "mobile_cover_fit": "contain",
                    "mobile_image_zoom": 125,
                },
            )
            self.assertEqual(saved.status_code, 200)
            after = client.get("/api/v2/admin/entities/7", headers=headers)
            self.assertEqual(after.get_json()["entity"]["image_zoom"], 150)
            self.assertEqual(after.get_json()["entity"]["mobile_cover_offset_x"], 28)
            self.assertEqual(after.get_json()["entity"]["mobile_cover_offset_y"], 74)
            self.assertEqual(after.get_json()["entity"]["mobile_cover_fit"], "contain")
            self.assertEqual(after.get_json()["entity"]["mobile_image_zoom"], 125)

            client.post(
                "/api/v2/admin/entities/7/crop",
                headers=headers,
                json={"image_zoom": 99},
            )
            below = client.get("/api/v2/admin/entities/7", headers=headers)
            self.assertEqual(below.get_json()["entity"]["image_zoom"], 100)

            client.post(
                "/api/v2/admin/entities/7/crop",
                headers=headers,
                json={"image_zoom": 201},
            )
            above = client.get("/api/v2/admin/entities/7", headers=headers)
            self.assertEqual(above.get_json()["entity"]["image_zoom"], 200)

    def test_reads_saves_and_rereads_canonical_ensemble_without_a_rebuild(self) -> None:
        categories = [
            {"id": 1, "name": "Все", "slug": "all", "description": "", "is_visible": True, "is_system": True, "sort_order": 0}
        ]
        tags = [
            {"id": 1, "name": "Все", "slug": "all", "description": "", "is_visible": True, "is_system": True, "sort_order": 0}
        ]
        state = {
            "id": 7,
            "name": "Анна, Эльза и Олаф",
            "slug": "anna-elsa-olaf",
            "entity_type": "character",
            "status": "active",
            "ensemble_members": [],
            "ensemble_included_count": 2,
            "ensemble_extra_member_price": 300_000,
            "categories": categories,
            "tags": tags,
        }

        def update_character(_entity_id: int, values: dict) -> None:
            state.update(values)
            state["ensemble_members"] = [
                member.strip()
                for member in str(values.get("ensemble_members") or "").splitlines()
                if member.strip()
            ]

        def create_category(name: str, slug: str, description: str, is_visible: bool, **_kwargs) -> int:
            category_id = len(categories) + 1
            categories.append(
                {
                    "id": category_id,
                    "name": name,
                    "slug": slug,
                    "description": description,
                    "is_visible": is_visible,
                    "is_system": False,
                    "sort_order": category_id,
                }
            )
            return category_id

        def fail_create_character(_values: dict) -> int:
            self.fail("Malformed one-member group reached canonical creation")

        with (
            patch.dict(os.environ, {"SURPRIZ_ADMIN_SECRET": "test-secret", "SURPRIZ_ADAPTER_TOKEN": "test-token"}),
            patch.multiple(
                adapter_app,
                _initialize_idempotency_database=lambda: None,
                init_customer_store=lambda: None,
                _ensure_customer_admin_columns=lambda: None,
                init_addon_store=lambda: None,
                init_promotion_store=lambda: None,
                init_admin_notifications_store=lambda: None,
                get_admin_by_id=lambda _admin_id: {"id": 1, "username": "admin"},
                get_character_by_id=lambda entity_id: dict(state) if entity_id == 7 else None,
                list_characters=lambda **_kwargs: [dict(state)],
                list_categories=lambda *_args, **_kwargs: [dict(item) for item in categories],
                list_tags=lambda *_args, **_kwargs: [dict(item) for item in tags],
                create_category=create_category,
                create_character=fail_create_character,
                update_character=update_character,
            ),
        ):
            application = adapter_app.create_app()
            application.config.update(TESTING=True)
            client = application.test_client()
            with client.session_transaction() as session:
                session[adapter_app.ADMIN_SESSION_KEY] = 1
            headers = {"X-Adapter-Token": "test-token"}

            before = client.get("/api/v2/admin/entities/7", headers=headers)
            self.assertEqual(before.status_code, 200)
            self.assertEqual(before.get_json()["entity"]["ensemble_members"], [])

            taxonomy_before = client.get("/api/v2/admin/section/taxonomy", headers=headers)
            self.assertEqual([item["slug"] for item in taxonomy_before.get_json()["categories"]], ["all"])
            taxonomy_saved = client.post(
                "/api/v2/admin/section/taxonomy",
                headers=headers,
                json={
                    "action": "create",
                    "taxonomy": "category",
                    "name": "Супергерои",
                    "slug": "superheroes",
                    "description": "",
                    "is_visible": True,
                },
            )
            self.assertEqual(taxonomy_saved.status_code, 201)
            taxonomy_after = client.get("/api/v2/admin/section/taxonomy", headers=headers)
            self.assertEqual(
                [item["slug"] for item in taxonomy_after.get_json()["categories"]],
                ["all", "superheroes"],
            )

            listing = client.get("/api/v2/admin/entities?entity_type=character", headers=headers)
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.get_json()["items"][0]["id"], 7)
            self.assertNotIn("ensemble_members", listing.get_json()["items"][0])

            saved = client.post(
                "/api/v2/admin/entities/7",
                headers=headers,
                json={
                    "name": state["name"],
                    "entity_type": "character",
                    "categories": ["all"],
                    "tags": ["all"],
                    "ensemble_members": "Анна\nЭльза\nОлаф",
                    "ensemble_included_count": 2,
                    "ensemble_extra_member_price": 300_000,
                },
            )
            self.assertEqual(saved.status_code, 200)

            after = client.get("/api/v2/admin/entities/7", headers=headers)
            self.assertEqual(after.status_code, 200)
            self.assertEqual(after.get_json()["entity"]["ensemble_members"], ["Анна", "Эльза", "Олаф"])
            self.assertEqual(after.get_json()["entity"]["ensemble_included_count"], 2)
            self.assertEqual(after.get_json()["entity"]["ensemble_extra_member_price"], 300_000)

            malformed = client.post(
                "/api/v2/admin/entities",
                headers=headers,
                json={
                    "name": "Неполная группа",
                    "entity_type": "character",
                    "ensemble_members": "Только один",
                    "ensemble_included_count": 2,
                    "ensemble_extra_member_price": 300_000,
                },
            )
            self.assertEqual(malformed.status_code, 400)
            self.assertIn("минимум два", malformed.get_json()["message"])

    def test_show_addon_link_settings_round_trip_and_unrelated_save_preserves_them(self) -> None:
        state = {
            "id": 10,
            "name": "Крио шоу",
            "slug": "cryo-show",
            "entity_type": "show_program",
            "status": "active",
            "categories": [],
            "tags": [],
        }
        active_addons = [
            {
                "id": 21,
                "name": "Попкорн",
                "slug": "popcorn",
                "status": "active",
                "price": 200_000,
                "duration_minutes": 15,
                "sort_order": 0,
                "image_path": "",
                "short_description": "",
            }
        ]
        settings = {
            21: {
                "is_available": True,
                "is_recommended": True,
                "is_default": False,
                "is_free_choice": False,
                "gift_mode": "none",
                "gift_group": "",
                "sort_order": 3,
            }
        }
        save_calls: list[list[dict]] = []

        def update_character(_entity_id: int, values: dict) -> None:
            state.update(values)

        def set_program_addons(_program_id: int, selections: list[dict]) -> None:
            save_calls.append(selections)
            settings.clear()
            for selection in selections:
                addon_id = int(selection["addon_id"])
                settings[addon_id] = {
                    "is_available": True,
                    "is_recommended": bool(selection.get("is_recommended")),
                    "is_default": bool(selection.get("is_default")),
                    "is_free_choice": bool(selection.get("is_free_choice")),
                    "gift_mode": str(selection.get("gift_mode") or "none"),
                    "gift_group": str(selection.get("gift_group") or ""),
                    "sort_order": int(selection.get("sort_order") or 0),
                }

        with (
            patch.dict(os.environ, {"SURPRIZ_ADMIN_SECRET": "test-secret", "SURPRIZ_ADAPTER_TOKEN": "test-token"}),
            patch.multiple(
                adapter_app,
                _initialize_idempotency_database=lambda: None,
                init_customer_store=lambda: None,
                _ensure_customer_admin_columns=lambda: None,
                init_addon_store=lambda: None,
                init_promotion_store=lambda: None,
                init_admin_notifications_store=lambda: None,
                get_admin_by_id=lambda _admin_id: {"id": 1, "username": "admin"},
                get_character_by_id=lambda entity_id: dict(state) if entity_id == 10 else None,
                update_character=update_character,
                list_categories=lambda *_args, **_kwargs: [],
                list_tags=lambda *_args, **_kwargs: [],
                list_active_addons=lambda: [dict(item) for item in active_addons],
                get_program_addon_settings=lambda _program_id: {key: dict(value) for key, value in settings.items()},
                set_program_addons=set_program_addons,
            ),
        ):
            application = adapter_app.create_app()
            application.config.update(TESTING=True)
            client = application.test_client()
            with client.session_transaction() as session:
                session[adapter_app.ADMIN_SESSION_KEY] = 1
            headers = {"X-Adapter-Token": "test-token"}

            before = client.get("/api/v2/admin/entities/10", headers=headers).get_json()["entity"]
            self.assertTrue(before["addons"][0]["is_available"])
            self.assertEqual(before["addons"][0]["sort_order"], 3)

            unrelated = client.post(
                "/api/v2/admin/entities/10",
                headers=headers,
                json={"name": "Крио шоу — новое имя", "entity_type": "show_program"},
            )
            self.assertEqual(unrelated.status_code, 200)
            self.assertEqual(save_calls, [])
            self.assertEqual(settings[21]["sort_order"], 3)

            saved = client.post(
                "/api/v2/admin/entities/10",
                headers=headers,
                json={
                    "name": state["name"],
                    "entity_type": "show_program",
                    "addons": [
                        {
                            "id": 21,
                            "is_available": True,
                            "is_recommended": False,
                            "is_default": True,
                            "gift_mode": "choice_one",
                            "gift_group": "kids",
                            "sort_order": 8,
                        }
                    ],
                },
            )
            self.assertEqual(saved.status_code, 200)
            after = client.get("/api/v2/admin/entities/10", headers=headers).get_json()["entity"]
            self.assertEqual(after["addons"][0]["gift_mode"], "choice_one")
            self.assertEqual(after["addons"][0]["gift_group"], "kids")
            self.assertTrue(after["addons"][0]["is_default"])
            self.assertEqual(after["addons"][0]["sort_order"], 8)


if __name__ == "__main__":
    unittest.main()
