from __future__ import annotations

import hashlib
import io
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.backfill_character_ensembles import (
    GROUP_SPECS,
    NEPTUNE_SPEC,
    main as backfill_ensembles,
)
from scripts.replace_character_catalog import (
    EXPECTED_CHARACTER_COUNT,
    MANAGED_META_KEY,
    load_manifest,
    replace_character_catalog,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = PROJECT_ROOT.parent / "surprizopus/data/catalogs.json"


SCHEMA = """
CREATE TABLE managed_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE managed_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    is_visible INTEGER NOT NULL DEFAULT 1,
    is_system INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE managed_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    is_visible INTEGER NOT NULL DEFAULT 1,
    is_system INTEGER NOT NULL DEFAULT 0,
    linked_tag_id INTEGER,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(linked_tag_id) REFERENCES managed_tags(id) ON DELETE SET NULL
);
CREATE TABLE managed_characters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    short_description TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    seo_title TEXT NOT NULL DEFAULT '',
    seo_description TEXT NOT NULL DEFAULT '',
    search_terms TEXT NOT NULL DEFAULT '',
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    contact_phone TEXT NOT NULL DEFAULT '',
    telegram_url TEXT NOT NULL DEFAULT '',
    base_price INTEGER NOT NULL DEFAULT 0,
    default_duration_minutes INTEGER NOT NULL DEFAULT 60,
    included_characters_count INTEGER NOT NULL DEFAULT 2,
    extra_character_price_3 INTEGER NOT NULL DEFAULT 200000,
    extra_character_price_4_plus INTEGER NOT NULL DEFAULT 200000,
    sort_order INTEGER NOT NULL DEFAULT 0,
    age_from INTEGER,
    age_to INTEGER,
    show_category TEXT NOT NULL DEFAULT '',
    format_tags TEXT NOT NULL DEFAULT '',
    included_items TEXT NOT NULL DEFAULT '',
    suitable_for TEXT NOT NULL DEFAULT '',
    restrictions TEXT NOT NULL DEFAULT '',
    video_url TEXT NOT NULL DEFAULT '',
    variant_group_slug TEXT NOT NULL DEFAULT '',
    variant_group_name TEXT NOT NULL DEFAULT '',
    variant_label TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    entity_type TEXT NOT NULL DEFAULT 'character',
    hero_media_id INTEGER,
    source_path TEXT NOT NULL DEFAULT '',
    cover_offset_x INTEGER NOT NULL DEFAULT 50,
    cover_offset_y INTEGER NOT NULL DEFAULT 50,
    cover_fit TEXT NOT NULL DEFAULT 'cover',
    image_zoom INTEGER NOT NULL DEFAULT 100,
    ensemble_members TEXT NOT NULL DEFAULT '',
    ensemble_included_count INTEGER NOT NULL DEFAULT 2,
    ensemble_extra_member_price INTEGER NOT NULL DEFAULT 300000,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE managed_character_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    alt_text TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(character_id) REFERENCES managed_characters(id) ON DELETE CASCADE
);
CREATE TABLE managed_character_categories (
    character_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    PRIMARY KEY(character_id, category_id),
    FOREIGN KEY(character_id) REFERENCES managed_characters(id) ON DELETE CASCADE,
    FOREIGN KEY(category_id) REFERENCES managed_categories(id) ON DELETE CASCADE
);
CREATE TABLE managed_character_tags (
    character_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY(character_id, tag_id),
    FOREIGN KEY(character_id) REFERENCES managed_characters(id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES managed_tags(id) ON DELETE CASCADE
);
"""


class ReplaceCharacterCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "site_admin.sqlite3"
        self._create_database()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _create_database(self) -> None:
        with sqlite3.connect(self.database) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA)
            connection.execute(
                """
                INSERT INTO managed_tags(
                    id, name, slug, is_system, sort_order, created_at, updated_at
                ) VALUES (1, 'all', 'all', 1, 0, 'old', 'old')
                """
            )
            connection.execute(
                """
                INSERT INTO managed_categories(
                    id, name, slug, is_system, linked_tag_id, sort_order, created_at, updated_at
                ) VALUES (1, 'Все', 'all', 1, 1, 0, 'old', 'old')
                """
            )
            connection.execute(
                """
                INSERT INTO managed_characters(
                    id, name, slug, short_description, description, seo_title,
                    seo_description, search_terms, status, entity_type,
                    source_path, created_at, updated_at
                ) VALUES (
                    101, 'Hello Kitty', 'hello-kitty', 'wrong', 'wrong', 'wrong',
                    'wrong', 'wrong', 'active', 'character', 'legacy', 'old', 'old'
                )
                """
            )
            cursor = connection.execute(
                """
                INSERT INTO managed_character_media(
                    character_id, media_type, file_path, alt_text, caption,
                    sort_order, created_at, updated_at
                ) VALUES (
                    101, 'image', '/surpriz/assets/img/characters/lol-dolls-800.webp',
                    'wrong', 'wrong', 9, 'old', 'old'
                )
                """
            )
            legacy_media_id = int(cursor.lastrowid)
            connection.execute(
                "UPDATE managed_characters SET hero_media_id = ? WHERE id = 101",
                (legacy_media_id,),
            )
            connection.execute(
                """
                INSERT INTO managed_characters(
                    id, name, slug, status, entity_type, source_path, created_at, updated_at
                ) VALUES (
                    202, 'Legacy only', 'legacy-only', 'active', 'character',
                    'legacy', 'old', 'old'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO managed_characters(
                    id, name, slug, status, entity_type, source_path, created_at, updated_at
                ) VALUES (
                    303, 'Stale target collision', 'lol-dolls', 'hidden', 'character',
                    'legacy', 'old', 'old'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO managed_characters(
                    id, name, slug, status, entity_type, source_path, created_at, updated_at
                ) VALUES (
                    404, 'Нептун и Русалки', 'neptune-mermaids', 'hidden',
                    'character', 'legacy', 'old', 'old'
                )
                """
            )
            connection.commit()

    def _dump(self) -> str:
        with sqlite3.connect(self.database) as connection:
            return "\n".join(connection.iterdump())

    def test_manifest_has_exactly_56_active_unique_images(self) -> None:
        _, items = load_manifest(MANIFEST)

        self.assertEqual(len(items), EXPECTED_CHARACTER_COUNT)
        self.assertEqual(len({item.slug for item in items}), EXPECTED_CHARACTER_COUNT)
        self.assertEqual(
            len({item.image_filename for item in items}), EXPECTED_CHARACTER_COUNT
        )
        self.assertEqual(
            next(item.name for item in items if item.slug == "brawl-stars"),
            "Шелли, Леон и Ворон",
        )
        for item in items:
            self.assertTrue(item.image_filename.endswith("-1200.webp"))
            if not item.ensemble_members:
                self.assertEqual(item.ensemble_extra_member_price, 0)
            elif len(item.ensemble_members) == 2:
                self.assertEqual(item.ensemble_included_count, 2)
                self.assertEqual(item.ensemble_extra_member_price, 0)
            else:
                self.assertIn(len(item.ensemble_members), (3, 4))
                self.assertEqual(item.ensemble_included_count, 2)
                self.assertEqual(item.ensemble_extra_member_price, 0)

        zootopia = next(item for item in items if item.slug == "zootopia")
        self.assertEqual(zootopia.base_price, 1_050_000)
        self.assertEqual(zootopia.included_items, "Игрушка входит в комплект")
        self.assertEqual(zootopia.ensemble_members, ("Ник", "Джуди"))

        manifest_groups = {
            item.slug: (
                item.ensemble_members,
                item.ensemble_included_count,
                item.ensemble_extra_member_price,
            )
            for item in items
            if item.ensemble_members
        }
        backfill_groups = {
            slug: (
                spec.members,
                spec.included_count,
                spec.extra_member_price,
            )
            for slug, spec in GROUP_SPECS.items()
        }
        backfill_groups["neptune-mermaids"] = (
            NEPTUNE_SPEC.members,
            NEPTUNE_SPEC.included_count,
            NEPTUNE_SPEC.extra_member_price,
        )
        self.assertEqual(manifest_groups, backfill_groups)

    def test_dry_run_verifies_plan_without_mutating_database(self) -> None:
        before = self._dump()
        output: list[str] = []

        summary = replace_character_catalog(
            database=self.database,
            manifest=MANIFEST,
            apply=False,
            output=output.append,
        )

        self.assertFalse(summary["applied"])
        self.assertEqual(summary["active"], EXPECTED_CHARACTER_COUNT)
        self.assertEqual(self._dump(), before)
        self.assertIn("transaction rolled back", output[-1])

    def test_apply_preserves_id_hides_legacy_and_replaces_media_and_taxonomy(self) -> None:
        output: list[str] = []

        summary = replace_character_catalog(
            database=self.database,
            manifest=MANIFEST,
            apply=True,
            output=output.append,
        )

        self.assertTrue(summary["applied"])
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            active_count = int(
                connection.execute(
                    """
                    SELECT COUNT(*) FROM managed_characters
                    WHERE entity_type = 'character' AND status = 'active'
                    """
                ).fetchone()[0]
            )
            self.assertEqual(active_count, EXPECTED_CHARACTER_COUNT)

            hello_kitty = connection.execute(
                """
                SELECT character.id, character.name, character.short_description,
                       character.description, character.hero_media_id,
                       media.character_id AS media_character_id,
                       media.file_path, media.alt_text, media.caption, media.sort_order
                FROM managed_characters AS character
                JOIN managed_character_media AS media ON media.id = character.hero_media_id
                WHERE character.slug = 'hello-kitty'
                """
            ).fetchone()
            self.assertIsNotNone(hello_kitty)
            self.assertEqual(int(hello_kitty["id"]), 101)
            self.assertEqual(hello_kitty["name"], "Хеллоу Китти")
            self.assertEqual(hello_kitty["short_description"], hello_kitty["description"])
            self.assertEqual(int(hello_kitty["media_character_id"]), 101)
            self.assertEqual(
                hello_kitty["file_path"], "/surpriz/assets/img/characters/hello-kitty-1200.webp"
            )
            self.assertEqual(hello_kitty["alt_text"], "Хеллоу Китти")
            self.assertEqual(hello_kitty["caption"], "")
            self.assertEqual(int(hello_kitty["sort_order"]), 0)

            legacy_status = connection.execute(
                "SELECT status FROM managed_characters WHERE id = 202"
            ).fetchone()[0]
            self.assertEqual(legacy_status, "hidden")
            collision = connection.execute(
                "SELECT slug, status FROM managed_characters WHERE id = 303"
            ).fetchone()
            self.assertEqual(collision["status"], "active")
            self.assertEqual(collision["slug"], "lol-mascot")
            self.assertEqual(
                int(connection.execute(
                    "SELECT id FROM managed_characters WHERE slug = 'hello-kitty'"
                ).fetchone()[0]),
                101,
            )

            categories = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT category.slug
                    FROM managed_character_categories AS assignment
                    JOIN managed_categories AS category ON category.id = assignment.category_id
                    WHERE assignment.character_id = 101
                    """
                )
            }
            tags = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT tag.slug
                    FROM managed_character_tags AS assignment
                    JOIN managed_tags AS tag ON tag.id = assignment.tag_id
                    WHERE assignment.character_id = 101
                    """
                )
            }
            self.assertEqual(categories, {"all"})
            self.assertEqual(tags, {"all", "devochkam"})

            brawl = connection.execute(
                """
                SELECT name, description FROM managed_characters
                WHERE slug = 'brawl-stars' AND status = 'active'
                """
            ).fetchone()
            self.assertEqual(brawl["name"], "Шелли, Леон и Ворон")
            self.assertIn("Brawl Stars", brawl["description"])

            active_media_count = int(
                connection.execute(
                    """
                    SELECT COUNT(DISTINCT media.file_path)
                    FROM managed_characters AS character
                    JOIN managed_character_media AS media ON media.id = character.hero_media_id
                    WHERE character.entity_type = 'character' AND character.status = 'active'
                    """
                ).fetchone()[0]
            )
            self.assertEqual(active_media_count, EXPECTED_CHARACTER_COUNT)

            digest = connection.execute(
                "SELECT value FROM managed_meta WHERE key = ?", (MANAGED_META_KEY,)
            ).fetchone()[0]
            self.assertEqual(digest, hashlib.sha256(MANIFEST.read_bytes()).hexdigest())

        self.assertIn("Postconditions verified", output[-1])

    def test_backfill_keeps_manifest_rosters_and_program_owned_extra_pricing(self) -> None:
        replace_character_catalog(
            database=self.database,
            manifest=MANIFEST,
            apply=True,
            output=lambda _: None,
        )

        with mock.patch(
            "sys.argv",
            [
                "backfill_character_ensembles.py",
                "--database",
                str(self.database),
                "--apply",
            ],
        ), redirect_stdout(io.StringIO()):
            backfill_ensembles()

        _, manifest_items = load_manifest(MANIFEST)
        expected_groups = {
            item.slug: ", ".join(item.ensemble_members)
            for item in manifest_items
            if item.ensemble_members
        }
        with sqlite3.connect(self.database) as connection:
            connection.row_factory = sqlite3.Row
            rows = {
                str(row["slug"]): row
                for row in connection.execute(
                    f"""
                    SELECT slug, ensemble_members, ensemble_included_count,
                           ensemble_extra_member_price, base_price,
                           included_items, description, status
                    FROM managed_characters
                    WHERE slug IN ({', '.join('?' for _ in expected_groups)})
                    """,
                    tuple(expected_groups),
                )
            }

        self.assertEqual(set(rows), set(expected_groups))
        for slug, expected_members in expected_groups.items():
            with self.subTest(slug=slug):
                self.assertEqual(rows[slug]["ensemble_members"], expected_members)
                self.assertEqual(rows[slug]["ensemble_included_count"], 2)
                self.assertEqual(rows[slug]["ensemble_extra_member_price"], 0)

        self.assertEqual(rows["zootopia"]["base_price"], 1_050_000)
        self.assertEqual(rows["zootopia"]["included_items"], "Игрушка входит в комплект")
        self.assertEqual(rows["neptune-mermaids"]["status"], "active")
        self.assertEqual(rows["neptune-mermaids"]["base_price"], 25_000)


if __name__ == "__main__":
    unittest.main()
