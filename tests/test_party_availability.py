from __future__ import annotations

import sqlite3
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from core import customer_panel
from core import customer_store


class PartyAvailabilityTests(unittest.TestCase):
    def test_admin_preview_overlays_fake_windows_in_time_choices_only(self) -> None:
        busy_dates = {
            "by_date": {
                "2099-08-10": {
                    "is_demo": True,
                    "blocked_windows": [{"from": "11:00", "to": "16:00"}],
                }
            }
        }
        start_slots = [
            {"value": "10:00", "time_to": "11:00", "available": True, "conflicts": []},
            {"value": "12:00", "time_to": "13:00", "available": True, "conflicts": []},
            {"value": "16:00", "time_to": "17:00", "available": True, "conflicts": []},
        ]
        end_slots = [
            {"value": "11:00", "available": True, "conflicts": []},
            {"value": "12:00", "available": True, "conflicts": []},
            {"value": "16:00", "available": True, "conflicts": []},
        ]

        customer_panel._apply_demo_preview_to_time_slots(
            start_slots,
            busy_dates=busy_dates,
            celebration_date="2099-08-10",
        )
        customer_panel._apply_demo_preview_to_time_slots(
            end_slots,
            busy_dates=busy_dates,
            celebration_date="2099-08-10",
            fixed_time_from="10:00",
        )

        self.assertEqual([slot["available"] for slot in start_slots], [True, False, True])
        self.assertEqual([slot["available"] for slot in end_slots], [True, False, False])
        self.assertEqual(start_slots[1]["reason"], "demo")
        self.assertEqual(start_slots[1]["conflicts"][0]["name"], "Демо-бронь")

    def test_demo_bookings_are_preview_only_and_disabled_in_production(self) -> None:
        with (
            patch.dict(os.environ, {"SURPRIZ_ENV": "development", "SURPRIZ_DEMO_AVAILABILITY": "1"}, clear=False),
            patch.object(customer_store, "get_busy_dates_summary", return_value={"by_date": {}}),
            patch.object(customer_store, "get_character_by_slug", return_value={"name": "Дэдпул", "duplicate_count": 0}),
        ):
            calendar = customer_store.build_resource_availability_calendar(
                character_slugs=["deadpool"],
                program_slug="",
            )

        self.assertEqual(len(calendar["by_date"]), 2)
        self.assertTrue(all(entry["is_demo"] for entry in calendar["by_date"].values()))
        self.assertTrue(all(entry["bookings"][0]["is_demo"] for entry in calendar["by_date"].values()))

        with (
            patch.dict(os.environ, {"SURPRIZ_ENV": "production", "SURPRIZ_DEMO_AVAILABILITY": "1"}, clear=False),
            patch.object(customer_store, "get_busy_dates_summary", return_value={"by_date": {}}),
            patch.object(customer_store, "get_character_by_slug", return_value={"name": "Дэдпул", "duplicate_count": 0}),
        ):
            production_calendar = customer_store.build_resource_availability_calendar(
                character_slugs=["deadpool"],
                program_slug="",
            )
            admin_preview_calendar = customer_store.build_resource_availability_calendar(
                character_slugs=["deadpool"],
                program_slug="",
                include_demo=True,
            )

        self.assertEqual(production_calendar, {"by_date": {}})
        self.assertEqual(len(admin_preview_calendar["by_date"]), 2)
        self.assertTrue(all(entry["is_demo"] for entry in admin_preview_calendar["by_date"].values()))

    def test_deadpool_booking_exposes_free_windows_with_operational_buffers(self) -> None:
        summary = {
            "by_date": {
                "2099-08-10": {
                    "count": 2,
                    "bookings": [
                        {
                            "time_from": "14:00",
                            "time_to": "15:00",
                            "program_slug": "",
                            "program_name": "",
                            "character_slugs": ["deadpool"],
                            "characters": ["Дэдпул"],
                        },
                        {
                            "time_from": "12:00",
                            "time_to": "13:00",
                            "program_slug": "",
                            "program_name": "",
                            "character_slugs": ["spiderman"],
                            "characters": ["Человек-паук"],
                        },
                    ],
                }
            }
        }
        with (
            patch.object(customer_store, "get_busy_dates_summary", return_value=summary),
            patch.object(
                customer_store,
                "get_character_by_slug",
                return_value={"slug": "deadpool", "duplicate_count": 0},
            ),
        ):
            calendar = customer_store.build_resource_availability_calendar(
                character_slugs=["deadpool"]
            )

        entry = calendar["by_date"]["2099-08-10"]
        self.assertEqual(entry["blocked_windows"], [{"from": "13:00", "to": "16:00"}])
        self.assertEqual(
            entry["free_windows"],
            [{"from": "09:00", "to": "13:00"}, {"from": "16:00", "to": "22:00"}],
        )
        self.assertEqual(entry["free_label"], "Свободно: до 13:00, после 16:00")
        self.assertEqual(len(entry["bookings"]), 1)
        self.assertNotIn("public_id", entry["bookings"][0])

    def test_start_and_end_slot_boundaries_match_blocked_window(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_root = Path(temporary_directory)
            db_path = db_root / "site_admin.sqlite3"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE party_orders (
                    id INTEGER PRIMARY KEY,
                    public_id TEXT,
                    celebration_date TEXT,
                    time_from TEXT,
                    time_to TEXT,
                    status TEXT
                );
                CREATE TABLE party_order_characters (
                    order_id INTEGER,
                    slug TEXT,
                    name_snapshot TEXT
                );
                """
            )
            connection.execute(
                """
                INSERT INTO party_orders(id, public_id, celebration_date, time_from, time_to, status)
                VALUES (1, 'SRP-1', '2099-08-10', '14:00', '15:00', 'confirmed')
                """
            )
            connection.execute(
                "INSERT INTO party_order_characters(order_id, slug, name_snapshot) VALUES (1, 'deadpool', 'Дэдпул')"
            )
            connection.execute(
                """
                INSERT INTO party_orders(id, public_id, celebration_date, time_from, time_to, status)
                VALUES (2, 'SRP-2', '2099-08-10', '17:00', '18:00', 'cancelled')
                """
            )
            connection.execute(
                "INSERT INTO party_order_characters(order_id, slug, name_snapshot) VALUES (2, 'deadpool', 'Дэдпул')"
            )
            connection.commit()
            connection.close()

            character = {
                "slug": "deadpool",
                "name": "Дэдпул",
                "entity_type": customer_store.ENTITY_TYPE_CHARACTER,
                "duplicate_count": 0,
            }
            with (
                patch.object(customer_store, "DB_ROOT", db_root),
                patch.object(customer_store, "DB_PATH", db_path),
                patch.object(customer_store, "get_character_by_slug", return_value=character),
            ):
                starts = customer_store.build_character_time_slot_availability(
                    character_slugs=["deadpool"],
                    celebration_date="2099-08-10",
                    duration_minutes=60,
                    time_slots=[
                        {"value": "10:00", "label": "10:00"},
                        {"value": "10:30", "label": "10:30"},
                        {"value": "15:30", "label": "15:30"},
                        {"value": "16:00", "label": "16:00"},
                    ],
                )["time_slots"]
                ends = customer_store.build_character_end_time_availability(
                    character_slugs=["deadpool"],
                    celebration_date="2099-08-10",
                    time_from="09:00",
                    time_slots=[
                        {"value": "11:00", "label": "11:00"},
                        {"value": "11:30", "label": "11:30"},
                    ],
                )["time_to_slots"]

        self.assertEqual([slot["available"] for slot in starts], [True, True, False, True])
        self.assertEqual([slot["available"] for slot in ends], [True, True])
        blocked_order = starts[2]["conflicts"][0]["orders"][0]
        self.assertNotIn("order_id", blocked_order)
        self.assertEqual(blocked_order["blocked_from"], "13:00")
        self.assertEqual(blocked_order["blocked_to"], "16:00")

    def test_capacity_uses_peak_concurrency_instead_of_total_overlaps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_root = Path(temporary_directory)
            db_path = db_root / "site_admin.sqlite3"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE party_orders (
                    id INTEGER PRIMARY KEY,
                    public_id TEXT,
                    celebration_date TEXT,
                    time_from TEXT,
                    time_to TEXT,
                    status TEXT
                );
                CREATE TABLE party_order_characters (
                    order_id INTEGER,
                    slug TEXT,
                    name_snapshot TEXT
                );
                """
            )
            for order in (
                (1, "SRP-FIRST", "12:00", "13:00"),
                (2, "SRP-SECOND", "18:00", "19:00"),
            ):
                connection.execute(
                    """
                    INSERT INTO party_orders(
                        id, public_id, celebration_date, time_from, time_to, status
                    ) VALUES (?, ?, '2099-08-10', ?, ?, 'confirmed')
                    """,
                    order,
                )
                connection.execute(
                    """
                    INSERT INTO party_order_characters(order_id, slug, name_snapshot)
                    VALUES (?, 'hero', 'Герой')
                    """,
                    (order[0],),
                )
            connection.commit()
            connection.close()

            character = {
                "slug": "hero",
                "name": "Герой",
                "entity_type": customer_store.ENTITY_TYPE_CHARACTER,
                "duplicate_count": 1,
            }
            with (
                patch.object(customer_store, "DB_ROOT", db_root),
                patch.object(customer_store, "DB_PATH", db_path),
                patch.object(customer_store, "get_character_by_slug", return_value=character),
            ):
                result = customer_store.check_character_availability(
                    character_slugs=["hero"],
                    celebration_date="2099-08-10",
                    time_from="13:30",
                    time_to="15:30",
                )

        self.assertTrue(result["success"])
        self.assertTrue(result["available"])
        self.assertEqual(result["conflicts"], [])

    def test_program_conflicts_do_not_expose_order_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_root = Path(temporary_directory)
            db_path = db_root / "site_admin.sqlite3"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE party_orders (
                    id INTEGER PRIMARY KEY,
                    public_id TEXT,
                    celebration_date TEXT,
                    time_from TEXT,
                    time_to TEXT,
                    status TEXT,
                    program_slug TEXT,
                    program_name_snapshot TEXT
                );
                """
            )
            connection.execute(
                """
                INSERT INTO party_orders(
                    id, public_id, celebration_date, time_from, time_to, status,
                    program_slug, program_name_snapshot
                ) VALUES (
                    1, 'SRP-SECRET', '2099-08-10', '14:00', '15:00', 'confirmed',
                    'magic-show', 'Магическое шоу'
                )
                """
            )
            connection.commit()
            connection.close()

            with (
                patch.object(customer_store, "DB_ROOT", db_root),
                patch.object(customer_store, "DB_PATH", db_path),
            ):
                result = customer_store.check_character_availability(
                    character_slugs=[],
                    celebration_date="2099-08-10",
                    time_from="13:30",
                    time_to="15:30",
                    program_slug="magic-show",
                )

        self.assertFalse(result["available"])
        conflict_order = result["conflicts"][0]["orders"][0]
        self.assertNotIn("order_id", conflict_order)
        self.assertEqual(conflict_order["time_from"], "14:00")

    def test_same_program_with_different_costumes_stays_available(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            db_root = Path(temporary_directory)
            db_path = db_root / "site_admin.sqlite3"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                """
                CREATE TABLE party_orders (
                    id INTEGER PRIMARY KEY,
                    celebration_date TEXT,
                    time_from TEXT,
                    time_to TEXT,
                    status TEXT,
                    program_slug TEXT,
                    program_name_snapshot TEXT
                );
                CREATE TABLE party_order_characters (
                    order_id INTEGER,
                    slug TEXT,
                    name_snapshot TEXT
                );
                INSERT INTO party_orders(
                    id, celebration_date, time_from, time_to, status,
                    program_slug, program_name_snapshot
                ) VALUES (
                    1, '2099-08-10', '07:00', '08:00', 'confirmed',
                    'standard-program', 'Стандарт'
                );
                INSERT INTO party_order_characters(order_id, slug, name_snapshot)
                VALUES (1, 'rumi-jinu', 'Руми + Джину');
                """
            )
            connection.commit()
            connection.close()

            nick_judy = {
                "slug": "zootopia",
                "name": "Ник + Джуди",
                "entity_type": customer_store.ENTITY_TYPE_CHARACTER,
                "duplicate_count": 0,
            }
            summary = {
                "by_date": {
                    "2099-08-10": {
                        "bookings": [
                            {
                                "time_from": "07:00",
                                "time_to": "08:00",
                                "program_slug": "standard-program",
                                "program_name": "Стандарт",
                                "character_slugs": ["rumi-jinu"],
                                "characters": ["Руми + Джину"],
                            }
                        ]
                    }
                }
            }
            with (
                patch.object(customer_store, "DB_ROOT", db_root),
                patch.object(customer_store, "DB_PATH", db_path),
                patch.object(customer_store, "get_character_by_slug", return_value=nick_judy),
                patch.object(customer_store, "get_busy_dates_summary", return_value=summary),
            ):
                result = customer_store.check_character_availability(
                    character_slugs=["zootopia"],
                    celebration_date="2099-08-10",
                    time_from="07:00",
                    time_to="08:00",
                    program_slug="standard-program",
                )
                calendar = customer_store.build_resource_availability_calendar(
                    character_slugs=["zootopia"],
                    program_slug="standard-program",
                    day_start_hour=6,
                )

        self.assertTrue(result["available"])
        self.assertEqual(calendar, {"by_date": {}})

    def test_public_endpoint_bounds_and_deduplicates_character_slugs(self) -> None:
        app = Flask(__name__)
        app.config["SECRET_KEY"] = "test"
        customer_panel.register_customer_routes(app)
        valid_payload = {
            "character_slugs": ["hero", "hero"],
            "celebration_date": "2099-08-10",
            "time_from": "12:00",
            "time_to": "13:00",
        }
        availability = {"success": True, "available": True, "conflicts": []}

        with (
            app.test_client() as client,
            patch.object(customer_panel, "_guard_public_api", return_value=None),
            patch.object(customer_panel, "check_character_availability", return_value=availability) as check,
            patch.object(customer_panel, "build_time_slots", return_value=[]),
            patch.object(
                customer_panel,
                "build_character_time_slot_availability",
                return_value={"success": True, "time_slots": []},
            ) as start_slots,
            patch.object(
                customer_panel,
                "build_character_end_time_availability",
                return_value={"success": True, "time_to_slots": []},
            ) as end_slots,
            patch.object(
                customer_panel,
                "build_resource_availability_calendar",
                return_value={"by_date": {}},
            ) as calendar,
        ):
            response = client.post("/api/party-builder/check-availability", json=valid_payload)

            self.assertEqual(response.status_code, 200)
            for call in (check, start_slots, end_slots, calendar):
                self.assertEqual(call.call_args.kwargs["character_slugs"], ["hero"])

            oversized_payload = dict(valid_payload)
            oversized_payload["character_slugs"] = [
                f"hero-{index}"
                for index in range(customer_panel.PARTY_BUILDER_AVAILABILITY_MAX_CHARACTERS + 1)
            ]
            response = client.post(
                "/api/party-builder/check-availability",
                json=oversized_payload,
            )

            long_slug_payload = dict(valid_payload)
            long_slug_payload["character_slugs"] = [
                "x" * (customer_panel.PARTY_BUILDER_AVAILABILITY_MAX_SLUG_LENGTH + 1)
            ]
            long_slug_response = client.post(
                "/api/party-builder/check-availability",
                json=long_slug_payload,
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error_code"], "invalid_character_selection")
        self.assertEqual(long_slug_response.status_code, 400)
        self.assertEqual(
            long_slug_response.get_json()["error_code"],
            "invalid_character_selection",
        )
        self.assertEqual(check.call_count, 1)


if __name__ == "__main__":
    unittest.main()
