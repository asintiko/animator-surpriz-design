from __future__ import annotations

import unittest
from unittest.mock import patch

from core.catalog_site import build_frontend_catalog_payload, build_frontend_show_payload


class FrontendCatalogPayloadTests(unittest.TestCase):
    def test_payload_uses_canonical_slugs_and_real_show_fields(self) -> None:
        character = {
            "slug": "spiderman",
            "name": "Спайдермен",
            "short_description": "Герой для праздника",
            "hero_file_path": "/wp-content/spiderman.webp",
            "route": "/character/spiderman/",
            "category_slugs": ["all", "supergeroi", "multiki"],
            "tag_names": ["Мальчикам"],
            "tag_slugs": ["malchikam"],
            "cover_offset_x": 42,
            "cover_offset_y": 61,
            "cover_fit": "contain",
            "image_zoom": 150,
            "mobile_cover_offset_x": 38,
            "mobile_cover_offset_y": 44,
            "mobile_cover_fit": "cover",
            "mobile_image_zoom": 125,
        }
        show = {
            "slug": "cryo-show",
            "name": "Крио шоу",
            "short_description": "Холодный туман и безопасные эксперименты",
            "hero_file_path": "/wp-content/cryo.webp",
            "route": "/show-programs/cryo-show/",
            "duration_label": "30 мин",
            "price_label": "1 000 000 сум",
            "age_label": "от 5 лет",
            "variant_group_slug": "science-show",
            "variant_group_name": "Научное шоу",
            "variant_label": "Крио",
            "included_items": "Туман; Научные опыты",
            "suitable_for": "Детский праздник",
            "restrictions": "",
            "cover_offset_x": 41,
            "cover_offset_y": 59,
            "cover_fit": "contain",
            "image_zoom": 135,
            "mobile_cover_offset_x": 35,
            "mobile_cover_offset_y": 28,
            "mobile_cover_fit": "cover",
            "mobile_image_zoom": 120,
        }

        with (
            patch("core.catalog_site.list_characters_for_public", return_value=[character]),
            patch("core.catalog_site.list_show_programs_for_public", return_value=[show]),
            patch("core.catalog_site.list_categories", return_value=[{"id": 1, "name": "Все", "slug": "all", "linked_tag_id": 1}, {"id": 2, "name": "Супергерои", "slug": "supergeroi", "linked_tag_id": 2}]),
            patch("core.catalog_site.list_tags", return_value=[{"id": 1, "name": "Все", "slug": "all"}, {"id": 2, "name": "Супергерои", "slug": "supergeroi"}, {"id": 3, "name": "Мальчикам", "slug": "malchikam"}]),
        ):
            payload = build_frontend_catalog_payload()

        character_card = payload["characters"][0]
        self.assertEqual(character_card["href"], "/party-builder/?character=spiderman")
        self.assertEqual(character_card["detail_href"], "/character/spiderman/")
        self.assertEqual(character_card["categories"], ["superheroes", "cartoons", "boys"])
        self.assertEqual(character_card["image"], "/wp-content/spiderman.webp")
        self.assertEqual(character_card["image_zoom"], 150)
        self.assertEqual(character_card["cover_fit"], "contain")
        self.assertEqual(character_card["mobile_image_position"], {"x": 38, "y": 44})
        self.assertEqual(character_card["mobile_image_zoom"], 125)
        self.assertEqual([item["slug"] for item in payload["filters"]], ["all", "superheroes", "boys"])

        show_card = payload["shows"][0]
        self.assertEqual(show_card["href"], "/party-builder/?program=cryo-show")
        self.assertEqual(show_card["detail_href"], "/show-programs/cryo-show/")
        self.assertEqual(show_card["duration_label"], "30 мин")
        self.assertEqual(show_card["price_label"], "1 000 000 сум")
        self.assertEqual(show_card["variant_group_slug"], "science-show")
        self.assertEqual(show_card["variant_group_name"], "Научное шоу")
        self.assertEqual(show_card["variant_label"], "Крио")
        self.assertEqual(show_card["included_items"], ["Туман", "Научные опыты"])
        self.assertEqual(show_card["cover_fit"], "contain")
        self.assertEqual(show_card["image_position"], {"x": 41, "y": 59})
        self.assertEqual(show_card["image_zoom"], 135)
        self.assertEqual(show_card["mobile_image_position"], {"x": 35, "y": 28})
        self.assertEqual(show_card["mobile_cover_fit"], "cover")
        self.assertEqual(show_card["mobile_image_zoom"], 120)
        self.assertEqual(
            show_card["image"],
            "/surpriz/assets/img/show-programs/cards/cryo-show-1200.webp?v=af3513c76de3",
        )
        self.assertEqual(show_card["image_sources"]["avif"][0]["width"], 480)
        self.assertEqual(show_card["image_sources"]["webp"][-1]["width"], 1200)
        self.assertNotIn("/wp-content/", str(show_card))

        visible_text = str(payload).lower()
        self.assertNotIn("premium", visible_text)
        self.assertNotIn("vip", visible_text)

    def test_show_payload_does_not_query_or_include_characters(self) -> None:
        show = {
            "slug": "cryo-show",
            "name": "Крио шоу",
            "hero_file_path": "/wp-content/cryo.webp",
        }
        with (
            patch("core.catalog_site.list_characters_for_public") as list_characters,
            patch("core.catalog_site.list_show_programs_for_public", return_value=[show]),
        ):
            payload = build_frontend_show_payload()

        list_characters.assert_not_called()
        self.assertNotIn("characters", payload)
        self.assertEqual([item["id"] for item in payload["shows"]], ["cryo-show"])
        self.assertNotIn("/wp-content/", str(payload["shows"]))

    def test_uploaded_custom_show_keeps_generated_responsive_media(self) -> None:
        generated_base = "/media/generated/v1-sharp035/ab/abcdef"
        show = {
            "slug": "admin-show",
            "name": "Новое шоу",
            "hero_file_path": f"{generated_base}/1920.webp",
        }
        with patch("core.catalog_site.list_show_programs_for_public", return_value=[show]):
            payload = build_frontend_show_payload()

        card = payload["shows"][0]
        self.assertEqual(card["image"], f"{generated_base}/1920.webp")
        self.assertEqual(card["image_sources"]["avif"][0]["src"], f"{generated_base}/480.avif")

    def test_custom_visible_filter_is_exposed_and_assigned_to_character(self) -> None:
        character = {
            "slug": "new-hero",
            "name": "Новый герой",
            "hero_file_path": "/surpriz/assets/img/characters/spiderman-1200.webp",
            "category_slugs": ["all", "space-party"],
            "tag_names": [],
            "tag_slugs": [],
        }
        with (
            patch("core.catalog_site.list_characters_for_public", return_value=[character]),
            patch("core.catalog_site.list_show_programs_for_public", return_value=[]),
            patch("core.catalog_site.list_categories", return_value=[{"id": 1, "name": "Все", "slug": "all", "linked_tag_id": 1}, {"id": 9, "name": "Космос", "slug": "space-party", "linked_tag_id": 9}]),
            patch("core.catalog_site.list_tags", return_value=[{"id": 1, "name": "Все", "slug": "all"}, {"id": 9, "name": "Космос", "slug": "space-party"}]),
        ):
            payload = build_frontend_catalog_payload()

        self.assertIn("space-party", payload["characters"][0]["categories"])
        self.assertEqual(payload["characters"][0]["image_sources"]["avif"][0]["width"], 480)
        self.assertEqual(payload["characters"][0]["image_sources"]["webp"][-1]["width"], 1200)
        self.assertIn({"slug": "space-party", "label": "Космос", "icon": "/surpriz/assets/icons/categories/all-heroes.svg"}, payload["filters"])

    def test_generated_admin_media_keeps_mobile_and_avif_variants(self) -> None:
        generated_base = "/media/generated/v1-sharp035/ab/abcdef"
        character = {
            "slug": "admin-hero",
            "name": "Новый герой",
            "hero_file_path": f"{generated_base}/1920.webp",
            "category_slugs": ["all"],
            "tag_names": [],
            "tag_slugs": [],
        }
        with (
            patch("core.catalog_site.list_characters_for_public", return_value=[character]),
            patch("core.catalog_site.list_show_programs_for_public", return_value=[]),
            patch("core.catalog_site.list_categories", return_value=[{"id": 1, "name": "Все", "slug": "all", "linked_tag_id": 1}]),
            patch("core.catalog_site.list_tags", return_value=[{"id": 1, "name": "Все", "slug": "all"}]),
        ):
            payload = build_frontend_catalog_payload()

        sources = payload["characters"][0]["image_sources"]
        self.assertEqual([item["width"] for item in sources["avif"]], [480, 768, 1280, 1920])
        self.assertEqual(sources["webp"][0]["src"], f"{generated_base}/480.webp")
        self.assertEqual(sources["fallback"], f"{generated_base}/1920.webp")


if __name__ == "__main__":
    unittest.main()
