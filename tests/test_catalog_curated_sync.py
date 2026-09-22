from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import catalog_store


class CuratedCatalogSyncTests(unittest.TestCase):
    def test_catalog_upload_images_are_validated_and_synced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_root = root / "db"
            db_path = db_root / "site_admin.sqlite3"
            routes_root = root / "routes"
            routes_root.mkdir(parents=True)
            manifest_path = root / "landing" / "data" / "catalogs.json"
            image_root = root / "landing" / "assets" / "img" / "catalogs"
            image_root.mkdir(parents=True)
            manifest_path.parent.mkdir(parents=True)

            characters = []
            for index in range(8):
                slug = f"catalog-hero-{index + 1}"
                image = f"assets/img/catalogs/{slug}.webp"
                (root / "landing" / image).write_bytes(b"webp")
                characters.append(
                    {
                        "id": f"character-{slug}",
                        "title": f"Герой {index + 1}",
                        "description": f"Описание {index + 1}",
                        "image": image,
                        "alt": f"Герой {index + 1}",
                        "href": f"/party-builder/?character={slug}",
                        "active": True,
                        "image_position": {"x": 50, "y": 50},
                        "categories": ["superheroes"],
                    }
                )
            manifest_path.write_text(
                json.dumps({"version": 2, "characters": characters, "shows": []}),
                encoding="utf-8",
            )

            self.assertEqual(
                catalog_store.validate_curated_character_catalog(manifest_path),
                {"valid": True, "count": 8},
            )
            with (
                patch.object(catalog_store, "DB_ROOT", db_root),
                patch.object(catalog_store, "DB_PATH", db_path),
                patch.object(catalog_store, "CHARACTER_ROUTES_ROOT", routes_root),
            ):
                catalog_store.init_catalog_store()
                catalog_store.sync_curated_character_catalog(manifest_path)
                active = catalog_store.list_characters_for_public(
                    entity_type=catalog_store.ENTITY_TYPE_CHARACTER
                )

            self.assertEqual(active[0]["hero_file_path"], "/surpriz/assets/img/catalogs/catalog-hero-1.webp")

    def test_sync_seeds_curated_set_without_hiding_admin_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_root = root / "db"
            db_path = db_root / "site_admin.sqlite3"
            routes_root = root / "routes"
            routes_root.mkdir(parents=True)
            manifest_path = root / "landing" / "data" / "catalogs.json"
            image_root = root / "landing" / "assets" / "img" / "characters"
            image_root.mkdir(parents=True)
            manifest_path.parent.mkdir(parents=True)

            characters = []
            for index in range(8):
                slug = f"hero-{index + 1}"
                image = f"assets/img/characters/{slug}-800.webp"
                (root / "landing" / image).write_bytes(b"webp")
                characters.append(
                    {
                        "id": f"character-{slug}",
                        "title": f"Герой {index + 1}",
                        "description": f"Описание {index + 1}",
                        "image": image,
                        "alt": f"Герой {index + 1}",
                        "href": f"/party-builder/?character={slug}",
                        "active": True,
                        "image_position": {"x": 50, "y": 50},
                        "categories": ["superheroes", "boys"],
                    }
                )
            manifest_path.write_text(
                json.dumps({"version": 2, "characters": characters, "shows": []}),
                encoding="utf-8",
            )

            with (
                patch.object(catalog_store, "DB_ROOT", db_root),
                patch.object(catalog_store, "DB_PATH", db_path),
                patch.object(catalog_store, "CHARACTER_ROUTES_ROOT", routes_root),
            ):
                catalog_store.init_catalog_store()
                now = catalog_store.utcnow_iso()
                with catalog_store._get_connection() as connection:
                    legacy = connection.execute(
                        """
                        INSERT INTO managed_characters(
                            name, slug, status, entity_type, source_path, created_at, updated_at
                        ) VALUES ('Старый герой', 'legacy-hero', 'active', 'character', '', ?, ?)
                        """,
                        (now, now),
                    )
                    connection.execute(
                        """
                        INSERT INTO managed_characters(
                            name, slug, status, entity_type, source_path, created_at, updated_at
                        ) VALUES ('Шоу', 'test-show', 'active', 'show_program', '', ?, ?)
                        """,
                        (now, now),
                    )
                    connection.execute(
                        """
                        INSERT INTO managed_character_media(
                            character_id, media_type, file_path, alt_text, caption,
                            sort_order, created_at, updated_at
                        ) VALUES (?, 'image', '/wp-content/old.webp', 'Старый герой', '', 0, ?, ?)
                        """,
                        (int(legacy.lastrowid), now, now),
                    )
                    connection.commit()

                result = catalog_store.sync_curated_character_catalog(manifest_path)
                self.assertTrue(result["changed"])
                self.assertEqual(result["count"], 8)

                active = catalog_store.list_characters_for_public(
                    entity_type=catalog_store.ENTITY_TYPE_CHARACTER
                )
                self.assertEqual(
                    [item["slug"] for item in active],
                    [f"hero-{i}" for i in range(1, 9)] + ["legacy-hero"],
                )
                self.assertEqual(active[0]["hero_file_path"], "/surpriz/assets/img/characters/hero-1-800.webp")
                self.assertEqual(active[0]["cover_fit"], "contain")
                self.assertIn("supergeroi", active[0]["category_slugs"])
                self.assertIn("Мальчикам", active[0]["tag_names"])

                legacy_row = catalog_store.get_character_by_slug("legacy-hero", include_hidden=True)
                self.assertEqual(legacy_row["status"], "active")
                show_row = catalog_store.get_character_by_slug("test-show")
                self.assertEqual(show_row["status"], "active")

                second = catalog_store.sync_curated_character_catalog(manifest_path)
                self.assertFalse(second["changed"])
                self.assertEqual(second["reason"], "already_synced")

    def test_manifest_refresh_preserves_admin_status_taxonomy_and_new_character(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_root = root / "db"
            db_path = db_root / "site_admin.sqlite3"
            routes_root = root / "routes"
            routes_root.mkdir(parents=True)
            manifest_path = root / "landing" / "data" / "catalogs.json"
            image_root = root / "landing" / "assets" / "img" / "characters"
            image_root.mkdir(parents=True)
            manifest_path.parent.mkdir(parents=True)

            characters = []
            for index in range(8):
                slug = f"hero-{index + 1}"
                image = f"assets/img/characters/{slug}.webp"
                (root / "landing" / image).write_bytes(b"webp")
                characters.append(
                    {
                        "id": f"character-{slug}",
                        "title": f"Герой {index + 1}",
                        "description": f"Описание {index + 1}",
                        "image": image,
                        "alt": f"Герой {index + 1}",
                        "href": f"/party-builder/?character={slug}",
                        "active": True,
                        "image_position": {"x": 50, "y": 50},
                        "categories": ["superheroes"],
                    }
                )

            def write_manifest(version: int) -> None:
                manifest_path.write_text(
                    json.dumps({"version": version, "characters": characters, "shows": []}),
                    encoding="utf-8",
                )

            write_manifest(1)
            with (
                patch.object(catalog_store, "DB_ROOT", db_root),
                patch.object(catalog_store, "DB_PATH", db_path),
                patch.object(catalog_store, "CHARACTER_ROUTES_ROOT", routes_root),
            ):
                catalog_store.init_catalog_store()
                catalog_store.sync_curated_character_catalog(manifest_path)
                now = catalog_store.utcnow_iso()
                with catalog_store._get_connection() as connection:
                    hero = connection.execute(
                        "SELECT id FROM managed_characters WHERE slug = 'hero-1'"
                    ).fetchone()
                    connection.execute(
                        "UPDATE managed_characters SET status = 'hidden', name = 'Имя из админки' WHERE id = ?",
                        (int(hero["id"]),),
                    )
                    category = connection.execute(
                        """
                        INSERT INTO managed_categories(
                            name, slug, description, is_visible, is_system, sort_order, created_at, updated_at
                        ) VALUES ('Новый фильтр', 'admin-filter', '', 1, 0, 99, ?, ?)
                        """,
                        (now, now),
                    )
                    connection.execute(
                        "INSERT INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
                        (int(hero["id"]), int(category.lastrowid)),
                    )
                    curated_category = connection.execute(
                        "SELECT id FROM managed_categories WHERE slug = 'supergeroi'"
                    ).fetchone()
                    connection.execute(
                        "DELETE FROM managed_character_categories WHERE character_id = ? AND category_id = ?",
                        (int(hero["id"]), int(curated_category["id"])),
                    )
                    connection.execute(
                        """
                        INSERT INTO managed_characters(
                            name, slug, status, entity_type, source_path, created_at, updated_at
                        ) VALUES ('Герой из админки', 'admin-hero', 'active', 'character', '', ?, ?)
                        """,
                        (now, now),
                    )
                    connection.commit()

                write_manifest(2)
                result = catalog_store.sync_curated_character_catalog(manifest_path)
                self.assertTrue(result["changed"])

                hero = catalog_store.get_character_by_slug("hero-1", include_hidden=True)
                self.assertEqual(hero["status"], "hidden")
                self.assertEqual(hero["name"], "Имя из админки")
                with catalog_store._get_connection() as connection:
                    assigned_categories = {
                        str(row["slug"])
                        for row in connection.execute(
                            """
                            SELECT category.slug
                            FROM managed_categories AS category
                            JOIN managed_character_categories AS assignment
                              ON assignment.category_id = category.id
                            WHERE assignment.character_id = ?
                            """,
                            (int(hero["id"]),),
                        ).fetchall()
                    }
                self.assertIn("admin-filter", assigned_categories)
                self.assertNotIn("supergeroi", assigned_categories)
                admin_hero = catalog_store.get_character_by_slug("admin-hero", include_hidden=True)
                self.assertEqual(admin_hero["status"], "active")

    def test_taxonomy_edit_preserves_explicit_category_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            db_root = root / "db"
            db_path = db_root / "site_admin.sqlite3"
            routes_root = root / "routes"
            routes_root.mkdir(parents=True)
            with (
                patch.object(catalog_store, "DB_ROOT", db_root),
                patch.object(catalog_store, "DB_PATH", db_path),
                patch.object(catalog_store, "CHARACTER_ROUTES_ROOT", routes_root),
            ):
                catalog_store.init_catalog_store()
                category_id = catalog_store.create_category("Космос", "space", "", True)
                character_id = catalog_store.create_character(
                    {
                        "name": "Космический герой",
                        "slug": "space-hero",
                        "entity_type": "character",
                        "status": "active",
                        "category_ids": [category_id],
                        "tag_ids": [],
                    }
                )
                catalog_store.create_tag("Новый независимый тег", "new-tag", "", True)

                character = catalog_store.get_character_by_id(character_id)
                self.assertIn(category_id, character["category_ids"])


if __name__ == "__main__":
    unittest.main()
