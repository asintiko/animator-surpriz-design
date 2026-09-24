from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, Response, send_file

from core import catalog_store, seasons
from core.catalog_site import build_frontend_catalog_payload
from core.season_theme import decorate_html, register_season_theme

HALLOWEEN = seasons.SEASONS["halloween"]

PAGE = """<!doctype html>
<html lang="ru">
  <head>
    <meta name="theme-color" content="#f8f5f0" />
    <link rel="icon" type="image/png" href="favicon.png" />
    <meta property="og:image" content="https://animator-surpriz.uz/surpriz/assets/img/show-programs/hero-desktop.webp" />
  </head>
  <body>
    <source type="image/avif" srcset="основа.avif?v=ed1ec21c92a5" />
    <source media="(max-width: 767px)" srcset="mobile.webp?v=405c6c203487" />
    <img src="/surpriz/assets/original/logo.png" alt="" />
    <img src="/surpriz/assets/img/characters/hero-mobile.webp" alt="" />
    <main style="--sd-bg: url('/v2/show-detail/bg-desktop.webp?v=17')"></main>
  </body>
</html>"""


class SeasonDatabaseCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "site.sqlite3"
        with sqlite3.connect(self.db_path) as connection:
            connection.executescript(
                """
                CREATE TABLE site_settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
                CREATE TABLE managed_characters (
                    id INTEGER PRIMARY KEY, name TEXT, slug TEXT, status TEXT, entity_type TEXT,
                    sort_order INTEGER DEFAULT 0, season TEXT NOT NULL DEFAULT '', season_only INTEGER NOT NULL DEFAULT 0
                );
                INSERT INTO managed_characters(name, slug, status, entity_type, season, season_only) VALUES
                    ('Пираты', 'pirates', 'active', 'character', 'halloween', 1),
                    ('Руми и Джину', 'rumi-jinu', 'active', 'character', 'halloween', 0),
                    ('Черновик', 'draft-hero', 'draft', 'character', 'halloween', 0),
                    ('Эльза', 'elsa', 'active', 'character', '', 0);
                """
            )
        self.db_patch = patch.object(catalog_store, "DB_PATH", self.db_path)
        self.db_patch.start()

    def tearDown(self) -> None:
        self.db_patch.stop()
        self.temp_dir.cleanup()


class SeasonStateTests(SeasonDatabaseCase):
    def test_no_season_by_default_and_effects_on(self) -> None:
        self.assertIsNone(seasons.active_season())
        self.assertTrue(seasons.effects_enabled())
        self.assertEqual(seasons.season_state(), {"active": "none", "effects": True})

    def test_switching_seasons_and_effects(self) -> None:
        self.assertEqual(seasons.set_active_season("halloween", effects=False), {"active": "halloween", "effects": False})
        self.assertIs(seasons.active_season(), HALLOWEEN)
        self.assertFalse(seasons.effects_enabled())

        seasons.set_active_season("new-year")
        self.assertEqual(seasons.season_state(), {"active": "new_year", "effects": False})

        seasons.set_active_season("none")
        self.assertIsNone(seasons.active_season())

    def test_unknown_season_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            seasons.set_active_season("easter")
        self.assertIsNone(seasons.active_season())

    def test_seasonal_slugs_skip_unpublished_heroes(self) -> None:
        self.assertEqual(seasons.seasonal_character_slugs(HALLOWEEN), ["pirates", "rumi-jinu"])
        self.assertEqual(seasons.seasonal_character_slugs(None), [])

    def test_admin_payload_groups_heroes_by_season(self) -> None:
        payload = seasons.season_admin_payload()
        self.assertEqual([option["id"] for option in payload["options"]], ["none", "halloween", "new_year"])
        halloween = {item["slug"]: item for item in payload["characters"]["halloween"]}
        self.assertEqual(set(halloween), {"pirates", "rumi-jinu", "draft-hero"})
        self.assertTrue(halloween["pirates"]["season_only"])
        self.assertEqual(payload["characters"]["new_year"], [])

    def test_missing_table_means_no_season(self) -> None:
        with patch.object(catalog_store, "DB_PATH", Path(self.temp_dir.name) / "missing" / "db.sqlite3"):
            self.assertIsNone(seasons.active_season())


class CharacterVisibilityTests(unittest.TestCase):
    def test_season_only_heroes_exist_only_in_their_season(self) -> None:
        pirates = {"season": "halloween", "season_only": True}
        rumi = {"season": "halloween", "season_only": False}
        regular = {"season": "", "season_only": False}
        new_year = seasons.SEASONS["new_year"]

        self.assertFalse(seasons.character_season_visible(pirates, None))
        self.assertFalse(seasons.character_season_visible(pirates, new_year))
        self.assertTrue(seasons.character_season_visible(pirates, HALLOWEEN))
        self.assertTrue(seasons.character_season_visible(rumi, None))
        self.assertTrue(seasons.character_season_visible(regular, HALLOWEEN))

        self.assertTrue(seasons.is_seasonal_now(rumi, HALLOWEEN))
        self.assertFalse(seasons.is_seasonal_now(rumi, new_year))
        self.assertFalse(seasons.is_seasonal_now(regular, HALLOWEEN))

    def _public_list(self, season):
        items = [
            {"slug": "elsa", "name": "Эльза", "entity_type": "character", "season": "", "season_only": False, "source_path": ""},
            {"slug": "pirates", "name": "Пираты", "entity_type": "character", "season": "halloween", "season_only": True, "source_path": ""},
            {"slug": "rumi-jinu", "name": "Руми и Джину", "entity_type": "character", "season": "halloween", "season_only": False, "source_path": ""},
        ]
        with (
            patch.object(catalog_store, "_character_list_query", return_value=[dict(item) for item in items]),
            patch.object(catalog_store, "get_legacy_catalog_context", return_value={"category_slug": "", "category_name": ""}),
            patch.object(catalog_store, "_character_public_sort_key", side_effect=lambda item: (0, 0, item["name"])),
            patch.object(seasons, "active_season", return_value=season),
        ):
            return catalog_store.list_characters_for_public()

    def test_public_list_hides_off_season_heroes(self) -> None:
        self.assertEqual([item["slug"] for item in self._public_list(None)], ["rumi-jinu", "elsa"])

    def test_public_list_puts_seasonal_heroes_first(self) -> None:
        listed = self._public_list(HALLOWEEN)
        self.assertEqual([item["slug"] for item in listed], ["pirates", "rumi-jinu", "elsa"])
        self.assertEqual([item["is_seasonal"] for item in listed], [True, True, False])


class SeasonValuesTests(unittest.TestCase):
    def test_season_only_needs_a_season(self) -> None:
        self.assertEqual(catalog_store._season_values({"season": "halloween", "season_only": True}), ("halloween", 1))
        self.assertEqual(catalog_store._season_values({"season": "halloween", "season_only": "0"}), ("halloween", 0))
        self.assertEqual(catalog_store._season_values({"season": "", "season_only": True}), ("", 0))
        self.assertEqual(catalog_store._season_values({"season": "summer", "season_only": True}), ("", 0))


class SeasonThemeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.landing_root = Path(self.temp_dir.name)
        season_dir = self.landing_root / "assets" / "seasons" / "halloween"
        (season_dir / "sprites").mkdir(parents=True)
        for name in ("season.css", "home-desktop.avif", "home-mobile.webp", "logo.webp", "favicon.png", "detail-bg-desktop.webp", "sprites/spider.webp"):
            (season_dir / name).write_bytes(name.encode())
        (self.landing_root / "assets" / "seasons" / "season.js").write_text("/* js */")
        (self.landing_root / "assets" / "seasons" / "season.css").write_text("/* css */")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def decorate(self, html: str = PAGE, *, effects: bool = True) -> str:
        with patch.object(seasons, "seasonal_character_slugs", return_value=["rumi-jinu"]):
            return decorate_html(html, HALLOWEEN, self.landing_root, effects=effects)

    def test_marks_html_and_links_season_assets(self) -> None:
        html = self.decorate(effects=False)
        self.assertIn('<html lang="ru" data-season="halloween" data-season-effects="off">', html)
        self.assertIn('<meta name="theme-color" content="#1b0f2e" />', html)
        self.assertNotIn("#f8f5f0", html)
        shared = html.index('href="/surpriz/assets/seasons/season.css?v=')
        self.assertLess(shared, html.index('href="/surpriz/assets/seasons/halloween/season.css?v='))
        self.assertRegex(html, r'<script src="/surpriz/assets/seasons/season\.js\?v=[0-9a-f]{12}" defer></script>')
        self.assertLess(html.index('id="surpriz-season"'), html.index("</head>"))

    def test_season_json_is_safe_inline(self) -> None:
        html = self.decorate()
        start = html.index('id="surpriz-season">') + len('id="surpriz-season">')
        payload = json.loads(html[start : html.index("</script>", start)])
        self.assertEqual(payload["id"], "halloween")
        self.assertEqual(payload["characters"], ["rumi-jinu"])
        self.assertEqual(list(payload["sprites"]), ["spider"])
        self.assertTrue(payload["effects"])

    def test_swaps_only_existing_seasonal_images(self) -> None:
        html = self.decorate()
        self.assertRegex(html, r'srcset="/surpriz/assets/seasons/halloween/home-desktop\.avif\?v=[0-9a-f]{12}"')
        self.assertRegex(html, r'srcset="/surpriz/assets/seasons/halloween/home-mobile\.webp\?v=[0-9a-f]{12}"')
        self.assertRegex(html, r'src="/surpriz/assets/seasons/halloween/logo\.webp\?v=[0-9a-f]{12}"')
        self.assertRegex(html, r'href="/surpriz/assets/seasons/halloween/favicon\.png\?v=[0-9a-f]{12}"')
        self.assertRegex(html, r"url\('/surpriz/assets/seasons/halloween/detail-bg-desktop\.webp\?v=[0-9a-f]{12}'\)")
        # No seasonal file: the regular image stays.
        self.assertNotIn("основа.avif", html)
        self.assertIn('src="/surpriz/assets/img/characters/hero-mobile.webp"', html)
        # Absolute URLs for crawlers are left alone.
        self.assertIn("https://animator-surpriz.uz/surpriz/assets/img/show-programs/hero-desktop.webp", html)

    def test_decorating_twice_is_a_no_op(self) -> None:
        once = self.decorate()
        self.assertEqual(self.decorate(once), once)

    def test_hook_applies_to_public_html_only(self) -> None:
        app = Flask(__name__)
        register_season_theme(app, self.landing_root)

        @app.get("/")
        def home():
            response = Response(PAGE, mimetype="text/html")
            response.surpriz_conditional = True
            return response

        @app.get("/admin/")
        def admin():
            return Response(PAGE, mimetype="text/html")

        client = app.test_client()
        with patch.object(seasons, "active_season", return_value=None):
            plain = client.get("/")
        self.assertNotIn(b"data-season", plain.data)
        self.assertTrue(plain.headers.get("ETag"))

        with (
            patch.object(seasons, "active_season", return_value=HALLOWEEN),
            patch.object(seasons, "effects_enabled", return_value=True),
            patch.object(seasons, "seasonal_character_slugs", return_value=[]),
        ):
            themed = client.get("/")
            self.assertIn('data-season="halloween"'.encode(), themed.data)
            self.assertNotEqual(themed.headers["ETag"], plain.headers["ETag"])
            self.assertEqual(client.get("/", headers={"If-None-Match": themed.headers["ETag"]}).status_code, 304)
            # A cached regular page is not reused once the season is on.
            self.assertEqual(client.get("/", headers={"If-None-Match": plain.headers["ETag"]}).status_code, 200)
            self.assertNotIn(b"data-season", client.get("/admin/").data)


class SeasonHookStreamTests(unittest.TestCase):
    def test_streamed_files_are_not_buffered(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        page = Path(temp_dir.name) / "page.html"
        page.write_text(PAGE, encoding="utf-8")
        app = Flask(__name__)
        register_season_theme(app, Path(temp_dir.name))

        @app.get("/file")
        def file_page():
            return send_file(page, mimetype="text/html")

        with (
            patch.object(seasons, "active_season", return_value=HALLOWEEN),
            patch.object(seasons, "seasonal_character_slugs", return_value=[]),
        ):
            response = app.test_client().get("/file")
            self.assertNotIn(b"data-season", response.data)
            response.close()


class SeasonCatalogPayloadTests(unittest.TestCase):
    def test_seasonal_heroes_lead_and_get_a_filter(self) -> None:
        def character(slug: str, seasonal: bool) -> dict:
            return {
                "slug": slug,
                "name": slug,
                "category_slugs": ["all", "multiki"],
                "tag_slugs": [],
                "is_seasonal": seasonal,
            }

        rows = [character("elsa", False), character("spiderman", False), character("rumi-jinu", True)]
        with (
            patch("core.catalog_site.list_characters_for_public", return_value=rows),
            patch("core.catalog_site.list_show_programs_for_public", return_value=[]),
            patch("core.catalog_site.get_featured_slugs", return_value=["elsa", "spiderman"]),
            patch("core.catalog_site.HOMEPAGE_SLOTS", 2),
            patch("core.catalog_site.list_categories", return_value=[{"id": 1, "name": "Все", "slug": "all", "linked_tag_id": None}]),
            patch("core.catalog_site.list_tags", return_value=[]),
            patch("core.catalog_site.list_partners", return_value=[]),
            patch.object(seasons, "active_season", return_value=HALLOWEEN),
            patch.object(seasons, "effects_enabled", return_value=True),
        ):
            payload = build_frontend_catalog_payload()

        cards = payload["characters"]
        self.assertEqual([card["id"] for card in cards], ["rumi-jinu", "elsa", "spiderman"])
        self.assertEqual([card["seasonal"] for card in cards], [True, False, False])
        self.assertEqual([card["id"] for card in cards if "homepage" in card["placements"]], ["rumi-jinu", "elsa"])
        self.assertEqual(cards[0]["categories"][-1], "season-halloween")
        self.assertEqual(payload["filters"][1]["slug"], "season-halloween")
        self.assertEqual(payload["filters"][1]["label"], "Герои Хэллоуина")
        self.assertEqual(payload["season"]["id"], "halloween")

    def test_no_season_keeps_the_regular_payload(self) -> None:
        with (
            patch("core.catalog_site.list_characters_for_public", return_value=[]),
            patch("core.catalog_site.list_show_programs_for_public", return_value=[]),
            patch("core.catalog_site.list_categories", return_value=[]),
            patch("core.catalog_site.list_tags", return_value=[]),
            patch("core.catalog_site.list_partners", return_value=[]),
            patch.object(seasons, "active_season", return_value=None),
        ):
            payload = build_frontend_catalog_payload()
        self.assertIsNone(payload["season"])
        self.assertEqual([item["slug"] for item in payload["filters"]], ["all"])


if __name__ == "__main__":
    unittest.main()
