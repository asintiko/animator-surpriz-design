from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet

from core import admin_notifications, customer_store, google_calendar, google_calendar_store

PROGRAMS = [
    {"slug": "standard-program", "name": "Стандарт", "entity_type": "show_program", "default_duration_minutes": 60, "sort_order": 10},
    {"slug": "streamer-show", "name": "Серпантин-шоу", "entity_type": "show_program", "default_duration_minutes": 60, "sort_order": 20},
    {"slug": "squid-game-60", "name": "Игра в кальмара — 60 минут", "entity_type": "show_program", "default_duration_minutes": 60, "sort_order": 30},
    {"slug": "squid-game-90", "name": "Игра в кальмара — 90 минут", "entity_type": "show_program", "default_duration_minutes": 90, "sort_order": 40},
]
CHARACTERS = [
    {"slug": "ladybug-cat-noir", "name": "Леди Баг и Супер-Кот", "entity_type": "character", "ensemble_members": ["Леди Баг", "Супер-Кот"], "sort_order": 1},
    {"slug": "spiderman-n1", "name": "Человек-паук №1", "entity_type": "character", "sort_order": 2},
    {"slug": "spiderman-n2", "name": "Человек-паук №2", "entity_type": "character", "sort_order": 3},
    {"slug": "hosts-mickey-minnie", "name": "Микки Маус и Минни Маус", "entity_type": "character", "ensemble_members": ["Микки Маус", "Минни Маус"], "sort_order": 4},
    {"slug": "mickey-mascot", "name": "Микки Маус (ростовой)", "entity_type": "character", "sort_order": 5},
    {"slug": "anna-elsa-olaf", "name": "Анна, Эльза и Олаф", "entity_type": "character", "ensemble_members": ["Анна", "Эльза", "Олаф (ростовой)"], "sort_order": 6},
    {"slug": "paw-patrol", "name": "Скай и Гонщик", "entity_type": "character", "ensemble_members": ["Скай", "Гонщик"], "sort_order": 7},
    {"slug": "masha-and-the-bear", "name": "Маша и Медведь", "entity_type": "character", "ensemble_members": ["Маша", "Медведь"], "sort_order": 8},
    {"slug": "deadpool", "name": "Дэдпул", "entity_type": "character", "sort_order": 9},
]
CATALOG = {item["slug"]: item for item in [*PROGRAMS, *CHARACTERS]}


def _catalog_lookup(slug: str, include_hidden: bool = False) -> dict[str, Any] | None:
    item = CATALOG.get(slug)
    if not item:
        return None
    return {"id": list(CATALOG).index(slug) + 1, "duplicate_count": 0, **item}


def _matcher(aliases: list[dict[str, Any]] | None = None) -> google_calendar.CalendarMatcher:
    return google_calendar.CalendarMatcher([*PROGRAMS, *CHARACTERS], aliases or [])


def _recognize(text: str, **kwargs: Any) -> tuple[list[str], list[str]]:
    result = _matcher().recognize(text, **kwargs)
    return [item.slug for item in result.programs], [item.slug for item in result.characters]


class CalendarMatcherTests(unittest.TestCase):
    def test_recognizes_program_and_ensemble_in_free_text(self) -> None:
        programs, characters = _recognize("Стандарт — Леди Баг и Супер Кот, Аня 6 лет, +998901234567")
        self.assertEqual(programs, ["standard-program"])
        self.assertEqual(characters, ["ladybug-cat-noir"])

    def test_ensemble_members_written_separately_resolve_to_one_character(self) -> None:
        self.assertEqual(_recognize("Анна, Эльза")[1], ["anna-elsa-olaf"])
        self.assertEqual(_recognize("Микки и Минни")[1], ["hosts-mickey-minnie"])
        self.assertEqual(_recognize("Скай + Гонщик")[1], ["paw-patrol"])

    def test_qualifier_picks_mascot_over_pair_member(self) -> None:
        self.assertEqual(_recognize("Микки Маус (ростовой)")[1], ["mickey-mascot"])
        self.assertEqual(_recognize("ростовой Микки Маус")[1], ["mickey-mascot"])
        self.assertEqual(_recognize("Микки Маус")[1], ["hosts-mickey-minnie"])

    def test_numbered_costumes_and_quantity(self) -> None:
        self.assertEqual(_recognize("Человек-паук №2 и Дэдпул")[1], ["spiderman-n2", "deadpool"])
        result = _matcher().recognize("2 человека паука")
        self.assertEqual(result.characters[0].alternatives, ["spiderman-n1", "spiderman-n2"])
        self.assertEqual(result.characters[0].quantity, 2)

    def test_case_endings_and_latin_synonyms(self) -> None:
        self.assertEqual(_recognize("Эльзу и Анну на 15:00")[1], ["anna-elsa-olaf"])
        self.assertEqual(_recognize("Spiderman")[1], ["spiderman-n1"])
        self.assertEqual(_recognize("Спайдермен")[1], ["spiderman-n1"])

    def test_program_without_generic_word_and_duration_tie_break(self) -> None:
        self.assertEqual(_recognize("Серпантин, Маша и Медведь")[0], ["streamer-show"])
        self.assertEqual(_recognize("Игра в кальмара", duration_minutes=90)[0], ["squid-game-90"])
        self.assertEqual(_recognize("Игра в кальмара 60", duration_minutes=90)[0], ["squid-game-60"])

    def test_unrelated_text_is_not_recognised(self) -> None:
        for text in ("Купить машину", "Созвон с бухгалтером", "Маршрутка до офиса", "Анализы"):
            with self.subTest(text=text):
                self.assertEqual(_recognize(text), ([], []))

    def test_custom_alias_teaches_new_abbreviation(self) -> None:
        self.assertEqual(_recognize("ЛБ + паук"), ([], ["spiderman-n1"]))
        matcher = _matcher([{"phrase": "ЛБ", "entity_slug": "ladybug-cat-noir"}])
        result = matcher.recognize("ЛБ + паук")
        self.assertEqual([item.slug for item in result.characters], ["ladybug-cat-noir", "spiderman-n1"])


class TempDatabaseMixin:
    def setUp(self) -> None:  # noqa: D401 - unittest hook
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_root = Path(self.temp_dir.name)
        self.db_path = self.db_root / "site_admin.sqlite3"
        self.patchers = [
            patch.dict(os.environ, {google_calendar_store.TOKEN_KEY_ENV: Fernet.generate_key().decode()}),
            patch.object(customer_store, "DB_ROOT", self.db_root),
            patch.object(customer_store, "DB_PATH", self.db_path),
            patch.object(admin_notifications, "DB_ROOT", self.db_root),
            patch.object(admin_notifications, "DB_PATH", self.db_path),
            patch.object(google_calendar_store, "DB_ROOT", self.db_root),
            patch.object(google_calendar_store, "DB_PATH", self.db_path),
            patch.object(customer_store, "get_character_by_slug", _catalog_lookup),
        ]
        for patcher in self.patchers:
            patcher.start()
        customer_store.init_customer_store()
        admin_notifications.init_admin_notifications_store()
        google_calendar.init_google_calendar()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection


def _event(event_id: str, summary: str, start: str, end: str, **extra: Any) -> dict[str, Any]:
    key = "date" if len(start) == 10 else "dateTime"
    return {"id": event_id, "summary": summary, "start": {key: start}, "end": {key: end}, "status": "confirmed", **extra}


class ImportedEventsTests(TempDatabaseMixin, unittest.TestCase):
    def _rows(self, events: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        return google_calendar.build_imported_rows(events, calendar_id="cal@example.com", matcher=_matcher(), **kwargs)

    def test_times_are_converted_to_tashkent_and_split_by_day(self) -> None:
        rows = self._rows(
            [
                _event("utc", "Человек-паук №1", "2099-10-05T10:00:00Z", "2099-10-05T11:30:00Z"),
                _event("night", "Дэдпул", "2099-10-05T22:00:00+05:00", "2099-10-06T01:00:00+05:00"),
                _event("allday", "Маша и Медведь в отпуске", "2099-10-07", "2099-10-09"),
            ]
        )
        by_id = {row["event_id"]: row for row in rows}
        self.assertEqual((by_id["utc"]["start_local"], by_id["utc"]["end_local"]), ("2099-10-05T15:00", "2099-10-05T16:30"))
        self.assertTrue(by_id["allday"]["all_day"])
        google_calendar_store.replace_imported_events(rows)

        with self._connect() as connection:
            blocks = google_calendar_store.fetch_busy_blocks(connection, "2099-10-05", "2099-10-08")
        self.assertEqual(
            [(block["time_from"], block["time_to"], block["character_slugs"]) for block in blocks["2099-10-05"]],
            [("15:00", "16:30", ["spiderman-n1"]), ("22:00", "23:59", ["deadpool"])],
        )
        self.assertEqual([(b["time_from"], b["time_to"]) for b in blocks["2099-10-06"]], [("00:00", "01:00")])
        self.assertEqual([(b["time_from"], b["time_to"]) for b in blocks["2099-10-07"]], [("00:00", "23:59")])
        self.assertEqual([(b["time_from"], b["time_to"]) for b in blocks["2099-10-08"]], [("00:00", "23:59")])
        self.assertNotIn("summary", blocks["2099-10-07"][0])

    def test_own_free_ignored_and_unmatched_events(self) -> None:
        events = [
            _event("own", "Стандарт", "2099-10-05T15:00:00+05:00", "2099-10-05T16:00:00+05:00",
                   extendedProperties={"private": {"surprizOrderId": "SRP-00007"}}),
            _event("free", "Дэдпул", "2099-10-05T15:00:00+05:00", "2099-10-05T16:00:00+05:00", transparency="transparent"),
            _event("skip", "Дэдпул", "2099-10-05T17:00:00+05:00", "2099-10-05T18:00:00+05:00"),
            _event("misc", "Созвон с поставщиком", "2099-10-05T12:00:00+05:00", "2099-10-05T13:00:00+05:00"),
            _event("gone", "Дэдпул", "2099-10-05T19:00:00+05:00", "2099-10-05T20:00:00+05:00", status="cancelled"),
        ]
        site_order = {
            "id": 7, "public_id": "SRP-00007", "status": "new", "celebration_date": "2099-10-05",
            "time_from": "15:00", "time_to": "16:00", "program_slug": "standard-program", "character_slugs": [],
        }
        rows = {
            row["event_id"]: row
            for row in self._rows(events, ignored_keys={"cal@example.com|skip"}, site_orders=[site_order])
        }
        self.assertNotIn("gone", rows)
        self.assertEqual(rows["own"]["match_status"], "own")
        self.assertEqual(rows["own"]["order_public_id"], "SRP-00007")
        self.assertEqual(rows["free"]["match_status"], "free")
        self.assertEqual(rows["skip"]["match_status"], "ignored")
        self.assertEqual(rows["misc"]["match_status"], "unmatched")
        self.assertFalse(any(row["blocks_time"] for row in rows.values()))

        # A site event whose order no longer holds time is read like a manual booking.
        orphan = {row["event_id"]: row for row in self._rows(events[:1])}
        self.assertEqual(orphan["own"]["match_status"], "matched")
        self.assertTrue(orphan["own"]["blocks_time"])

        strict = {row["event_id"]: row for row in self._rows(events[3:4], block_unmatched=True)}
        self.assertTrue(strict["misc"]["blocks_time"])
        self.assertTrue(strict["misc"]["blocks_all"])

    def test_generic_spiderman_mentions_take_free_costumes_first(self) -> None:
        rows = self._rows(
            [
                _event("a", "Паук", "2099-10-05T15:00:00+05:00", "2099-10-05T16:00:00+05:00"),
                _event("b", "Человек-паук", "2099-10-05T15:30:00+05:00", "2099-10-05T16:30:00+05:00"),
                _event("c", "Паук", "2099-10-05T18:00:00+05:00", "2099-10-05T19:00:00+05:00"),
            ]
        )
        self.assertEqual([row["character_slugs"] for row in rows], [["spiderman-n1"], ["spiderman-n2"], ["spiderman-n1"]])


class CalendarAvailabilityTests(TempDatabaseMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.day = (date.today() + timedelta(days=10)).isoformat()

    def _store_events(self, events: list[dict[str, Any]], **kwargs: Any) -> None:
        rows = google_calendar.build_imported_rows(events, calendar_id="cal", matcher=_matcher(), **kwargs)
        google_calendar_store.replace_imported_events(rows)

    def _check(self, characters: list[str], time_from: str, time_to: str, program: str = "") -> dict[str, Any]:
        return customer_store.check_character_availability(
            character_slugs=characters,
            celebration_date=self.day,
            time_from=time_from,
            time_to=time_to,
            program_slug=program,
        )

    def test_recognised_characters_are_busy_with_buffer(self) -> None:
        self._store_events([_event("e1", "Стандарт: Дэдпул", f"{self.day}T15:00:00+05:00", f"{self.day}T16:00:00+05:00")])

        busy = self._check(["deadpool"], "16:30", "17:30")
        self.assertFalse(busy["available"])
        self.assertEqual(busy["conflicts"][0]["orders"][0]["blocked_from"], "14:00")
        self.assertTrue(self._check(["deadpool"], "17:00", "18:00")["available"])
        self.assertTrue(self._check(["spiderman-n1"], "15:00", "16:00")["available"])

        program_busy = self._check([], "15:00", "16:00", program="standard-program")
        self.assertFalse(program_busy["available"])
        self.assertEqual(program_busy["reason"], "program_overlap")

        slots = customer_store.build_character_time_slot_availability(
            character_slugs=["deadpool"], celebration_date=self.day, duration_minutes=60,
        )["time_slots"]
        by_time = {slot["value"]: slot["available"] for slot in slots}
        self.assertFalse(by_time["15:00"])
        self.assertTrue(by_time["18:00"])

    def test_unmatched_event_can_close_time_for_everyone(self) -> None:
        self._store_events(
            [_event("off", "Выходной у команды", f"{self.day}T12:00:00+05:00", f"{self.day}T14:00:00+05:00")],
            block_unmatched=True,
        )
        closed = self._check([], "12:30", "13:30")
        self.assertFalse(closed["available"])
        self.assertEqual(closed["reason"], "calendar_closed")
        self.assertFalse(self._check(["deadpool"], "12:30", "13:30")["available"])
        self.assertTrue(self._check(["deadpool"], "16:00", "17:00")["available"])

        end_slots = customer_store.build_character_end_time_availability(
            character_slugs=[], celebration_date=self.day, time_from="10:00",
        )["time_to_slots"]
        self.assertFalse({slot["value"]: slot["available"] for slot in end_slots}["12:00"])

    def test_busy_dates_summary_and_builder_calendar_include_calendar_blocks(self) -> None:
        self._store_events([_event("e1", "Человек-паук №2", f"{self.day}T15:00:00+05:00", f"{self.day}T16:00:00+05:00")])
        summary = customer_store.get_busy_dates_summary()
        booking = summary["by_date"][self.day]["bookings"][0]
        self.assertEqual(booking["character_slugs"], ["spiderman-n2"])
        self.assertEqual(booking["source"], "google_calendar")

        calendar = customer_store.build_resource_availability_calendar(character_slugs=["spiderman-n2"])
        self.assertEqual(calendar["by_date"][self.day]["blocked_windows"], [{"from": "14:00", "to": "17:00"}])
        other = customer_store.build_resource_availability_calendar(character_slugs=["spiderman-n1"])
        self.assertNotIn(self.day, other["by_date"])


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


class FakeGoogle:
    """In-memory stand-in for the token endpoint and Calendar API."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.events: dict[str, dict[str, Any]] = {}
        self.listed: list[dict[str, Any]] = []
        self.token_response: tuple[int, dict[str, Any]] = (200, {"access_token": "fresh", "expires_in": 3600})

    def api_calls(self) -> list[tuple[str, str]]:
        return [(method, url) for method, url, _ in self.calls if url.startswith(google_calendar.CALENDAR_API_BASE)]

    def __call__(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        if url == google_calendar.GOOGLE_TOKEN_URL:
            return FakeResponse(*self.token_response)
        if url == google_calendar.GOOGLE_REVOKE_URL:
            return FakeResponse(200, {})
        path = url.removeprefix(google_calendar.CALENDAR_API_BASE)
        if path == "/users/me/calendarList":
            return FakeResponse(200, {"items": [
                {"id": "owner@gmail.com", "summary": "owner@gmail.com", "primary": True, "accessRole": "owner"},
                {"id": "orders@group.calendar.google.com", "summary": "Заказы", "accessRole": "writer"},
            ]})
        prefix = "/calendars/cal%40example.com/events"
        if not path.startswith(prefix):
            return FakeResponse(404, {"error": {"message": "Not Found"}})
        event_id = path[len(prefix) + 1:] if len(path) > len(prefix) else ""
        body = kwargs.get("json") or {}
        if method == "GET":
            return FakeResponse(200, {"items": self.listed})
        if method == "POST":
            if body["id"] in self.events:
                return FakeResponse(409, {"error": {"message": "The requested identifier already exists."}})
            self.events[body["id"]] = dict(body)
            return FakeResponse(200, {**body, "htmlLink": f"https://calendar.google.com/event?eid={body['id']}"})
        if method == "PUT":
            if event_id not in self.events:
                return FakeResponse(404, {"error": {"message": "Not Found"}})
            self.events[event_id] = {**body, "id": event_id}
            return FakeResponse(200, {**body, "id": event_id, "htmlLink": f"https://calendar.google.com/event?eid={event_id}"})
        if method == "DELETE":
            if self.events.pop(event_id, None) is None:
                return FakeResponse(410, {"error": {"message": "Resource has been deleted"}})
            return FakeResponse(204)
        return FakeResponse(400, {})


class OrderExportTests(TempDatabaseMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.day = (date.today() + timedelta(days=10)).isoformat()
        self.google = FakeGoogle()
        self.http = patch.object(google_calendar, "_http_request", self.google)
        self.http.start()
        google_calendar_store.set_settings(
            {
                "client_id": "id.apps.googleusercontent.com",
                "client_secret": "secret",
                "refresh_token": "refresh",
                "access_token": "token",
                "access_token_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "calendar_id": "cal@example.com",
            }
        )

    def tearDown(self) -> None:
        self.http.stop()
        super().tearDown()

    def _seed_order(self) -> int:
        now = "2026-08-06T10:00:00+00:00"
        with self._connect() as connection:
            customer_id = connection.execute(
                """
                INSERT INTO customer_accounts(phone_normalized, phone_display, full_name, created_at, updated_at)
                VALUES ('+998901234567', '+998 (90) 123-45-67', 'Дилноза', ?, ?)
                """,
                (now, now),
            ).lastrowid
            order_id = connection.execute(
                """
                INSERT INTO party_orders(
                    public_id, customer_id, status, program_slug, program_name_snapshot, celebration_date,
                    time_from, time_to, duration_minutes, celebrant_name, celebrant_age, children_count,
                    address_text, payment_method, total_price_snapshot, created_at, updated_at
                ) VALUES ('SRP-00001', ?, 'new', 'standard-program', 'Стандарт', ?, '14:00', '15:00', 60,
                          'Аня', 6, 12, 'Юнусабад, 4 квартал', 'cash', 950000, ?, ?)
                """,
                (customer_id, self.day, now, now),
            ).lastrowid
            connection.execute(
                """
                INSERT INTO party_order_characters(order_id, slug, name_snapshot, sort_order, created_at)
                VALUES (?, 'ladybug-cat-noir', 'Леди Баг + Супер-Кот', 1, ?)
                """,
                (order_id, now),
            )
            connection.commit()
        return int(order_id)

    def test_confirmed_order_is_written_in_order_card_format_once(self) -> None:
        order_id = self._seed_order()
        self.assertTrue(customer_store.set_order_confirmation_by_public_id("SRP-00001", "confirmed", source="telegram")["success"])
        self.assertIsNotNone(google_calendar_store.get_queue_row(order_id))

        result = google_calendar.process_order_queue()
        self.assertEqual(result["succeeded"], 1)
        self.assertEqual(len(self.google.events), 1)
        event = next(iter(self.google.events.values()))
        self.assertEqual(event["summary"], "Стандарт (Леди Баг + Супер-Кот) — Аня, 6 лет")
        self.assertEqual(event["start"]["dateTime"], f"{self.day}T14:00:00+05:00")
        self.assertEqual(event["end"]["timeZone"], "Asia/Tashkent")
        self.assertEqual(event["extendedProperties"]["private"]["surprizOrderId"], "SRP-00001")
        self.assertEqual(event["colorId"], "6")
        self.assertIn("Программа:", event["description"])
        self.assertIn("Именинник(ца):", event["description"])
        self.assertIn("Дилноза", event["description"])
        self.assertNotIn("<b>", event["description"])
        self.assertIsNone(google_calendar_store.get_queue_row(order_id))
        self.assertTrue(google_calendar_store.get_order_event_links([order_id])[order_id].startswith("https://calendar.google.com/"))

        calls_before = len(self.google.api_calls())
        google_calendar_store.enqueue_orders([order_id])
        self.assertEqual(google_calendar.process_order_queue()["succeeded"], 1)
        self.assertEqual(len(self.google.api_calls()), calls_before, "unchanged event must not be rewritten")

    def test_cancelled_order_is_removed_and_reconfirmation_restores_it(self) -> None:
        order_id = self._seed_order()
        customer_store.set_order_confirmation(order_id, "confirmed", source="telegram")
        google_calendar.process_order_queue()
        event_id = google_calendar_store.get_order_event(order_id)["event_id"]

        customer_store.set_order_confirmation(order_id, "unconfirmed", source="telegram")
        google_calendar.process_order_queue()
        self.assertNotIn(event_id, self.google.events)
        self.assertIsNone(google_calendar_store.get_order_event(order_id))

        customer_store.set_order_confirmation(order_id, "confirmed", source="admin")
        google_calendar.process_order_queue()
        self.assertIn(event_id, self.google.events)

        customer_store.apply_legacy_order_cancellation_by_public_id("SRP-00001")
        google_calendar.process_order_queue()
        self.assertEqual(self.google.events, {})

    def test_lost_create_response_is_retried_without_duplicate(self) -> None:
        order_id = self._seed_order()
        customer_store.set_order_confirmation(order_id, "confirmed", source="telegram")
        event_id = google_calendar._event_id(order_id, 0)
        self.google.events[event_id] = {"id": event_id, "summary": "old"}

        google_calendar.process_order_queue()
        self.assertEqual(list(self.google.events), [event_id])
        self.assertEqual(self.google.events[event_id]["summary"], "Стандарт (Леди Баг + Супер-Кот) — Аня, 6 лет")
        methods = [method for method, _ in self.google.api_calls()]
        self.assertEqual(methods, ["POST", "PUT"])

    def test_export_waits_until_calendar_is_selected(self) -> None:
        google_calendar_store.set_settings({"calendar_id": ""})
        order_id = self._seed_order()
        customer_store.set_order_confirmation(order_id, "confirmed", source="telegram")
        self.assertEqual(google_calendar.process_order_queue(), {"skipped": True})
        self.assertIsNotNone(google_calendar_store.get_queue_row(order_id))
        self.assertEqual(self.google.calls, [])

    def test_import_skips_events_pushed_by_the_site(self) -> None:
        order_id = self._seed_order()
        customer_store.set_order_confirmation(order_id, "confirmed", source="telegram")
        google_calendar.process_order_queue()
        pushed = next(iter(self.google.events.values()))
        self.google.listed = [
            {**pushed, "status": "confirmed"},
            _event("manual", "Стандарт, Дэдпул", f"{self.day}T17:00:00+05:00", f"{self.day}T18:00:00+05:00"),
        ]
        with patch.object(google_calendar.CalendarMatcher, "from_catalog", classmethod(lambda cls: _matcher())):
            stats = google_calendar.import_calendar_events()
        self.assertEqual(stats["own"], 1)
        self.assertEqual(stats["matched"], 1)
        with self._connect() as connection:
            blocks = google_calendar_store.fetch_busy_blocks(connection, self.day)[self.day]
        self.assertEqual([block["character_slugs"] for block in blocks], [["deadpool"]])

    def test_title_template_drops_empty_parts(self) -> None:
        order = {"program_name": "Стандарт", "character_names": [], "celebrant_name": "", "celebrant_age": None}
        self.assertEqual(google_calendar.render_title(google_calendar.DEFAULT_TITLE_TEMPLATE, order), "Стандарт")
        order.update({"celebrant_name": "Тимур", "celebrant_age": 1, "character_names": ["Дэдпул"]})
        self.assertEqual(google_calendar.render_title(google_calendar.DEFAULT_TITLE_TEMPLATE, order), "Стандарт (Дэдпул) — Тимур, 1 год")
        self.assertEqual(google_calendar.render_title("{order} {unknown}", {"public_id": "SRP-1"}), "SRP-1 {unknown}")


class OAuthTests(TempDatabaseMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.google = FakeGoogle()
        self.http = patch.object(google_calendar, "_http_request", self.google)
        self.http.start()
        google_calendar.save_client_credentials("id.apps.googleusercontent.com", "secret")

    def tearDown(self) -> None:
        self.http.stop()
        super().tearDown()

    def test_connect_flow_stores_refresh_token_and_selects_primary_calendar(self) -> None:
        url = google_calendar.build_authorization_url("https://animator-surpriz.uz/api/admin/google-calendar/callback")
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(query["prompt"], ["consent"])
        self.assertIn("https://www.googleapis.com/auth/calendar.events", query["scope"][0])

        with self.assertRaises(google_calendar.GoogleCalendarError):
            google_calendar.complete_authorization("code", "forged-state")

        url = google_calendar.build_authorization_url("https://animator-surpriz.uz/api/admin/google-calendar/callback")
        state = parse_qs(urlparse(url).query)["state"][0]
        self.google.token_response = (
            200,
            {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": " ".join(google_calendar.OAUTH_SCOPES)},
        )
        result = google_calendar.complete_authorization("code", state)
        self.assertEqual(result["account_email"], "owner@gmail.com")
        settings = google_calendar_store.get_settings()
        self.assertEqual(settings["refresh_token"], "rt")
        self.assertEqual(settings["calendar_id"], "owner@gmail.com")
        token_call = next(kwargs for method, url_, kwargs in self.google.calls if url_ == google_calendar.GOOGLE_TOKEN_URL)
        self.assertEqual(token_call["data"]["redirect_uri"], "https://animator-surpriz.uz/api/admin/google-calendar/callback")

        with self.assertRaises(google_calendar.GoogleCalendarError):
            google_calendar.complete_authorization("code", state)

    def test_revoked_refresh_token_marks_connection_broken(self) -> None:
        google_calendar_store.set_settings({"refresh_token": "rt", "calendar_id": "cal@example.com"})
        self.google.token_response = (400, {"error": "invalid_grant"})
        with self.assertRaises(google_calendar.GoogleCalendarAuthError):
            google_calendar.list_calendars()
        self.assertIn("Подключите", google_calendar_store.get_setting("auth_error"))
        self.assertEqual(google_calendar.process_order_queue(), {"skipped": True})

    def test_settings_validation_and_disconnect_clears_blocks(self) -> None:
        saved = google_calendar.save_sync_settings({"poll_minutes": 7, "color_id": "", "title_template": "  ", "block_unmatched": True})
        self.assertEqual(saved["poll_minutes"], str(google_calendar.DEFAULT_POLL_MINUTES))
        self.assertEqual(saved["color_id"], "none")
        self.assertEqual(saved["title_template"], google_calendar.DEFAULT_TITLE_TEMPLATE)
        self.assertEqual(saved["block_unmatched"], "1")

        google_calendar_store.set_settings({"refresh_token": "rt"})
        google_calendar_store.replace_imported_events(
            google_calendar.build_imported_rows(
                [_event("e", "Дэдпул", "2099-10-05T15:00:00+05:00", "2099-10-05T16:00:00+05:00")],
                calendar_id="cal", matcher=_matcher(),
            )
        )
        google_calendar.disconnect()
        self.assertEqual(google_calendar_store.list_imported_events(), [])
        self.assertEqual(google_calendar_store.get_setting("refresh_token"), "")


class SyncLeaseTests(TempDatabaseMixin, unittest.TestCase):
    def test_manual_sync_does_not_overlap_a_running_cycle(self) -> None:
        self.assertTrue(google_calendar_store.claim_lease(google_calendar.SYNC_LEASE_NAME, "worker", 90))
        with self.assertRaises(google_calendar.GoogleCalendarSyncBusy):
            google_calendar.run_sync_cycle(force_import=True, wait_seconds=0)
        with self.assertRaises(google_calendar.GoogleCalendarSyncBusy):
            google_calendar.import_now(wait_seconds=0)

        google_calendar_store.release_lease(google_calendar.SYNC_LEASE_NAME, "worker")
        self.assertEqual(google_calendar.run_sync_cycle(force_import=True), {"export": {"skipped": True}, "import": {"skipped": True}})
        # The lease is released at the end, so the next caller does not wait for the TTL.
        self.assertTrue(google_calendar_store.claim_lease(google_calendar.SYNC_LEASE_NAME, "next", 90))

    def test_lease_is_renewed_while_a_long_cycle_runs(self) -> None:
        observed: dict[str, bool] = {}

        def slow_cycle(*, force_import: bool) -> dict[str, Any]:
            # Without renewal a 2-second lease (stored with 1 s precision) is gone by now.
            time.sleep(3.0)
            observed["intruder"] = google_calendar_store.claim_lease(google_calendar.SYNC_LEASE_NAME, "intruder", 1)
            return {}

        with (
            patch.object(google_calendar, "SYNC_LEASE_SECONDS", 2),
            patch.object(google_calendar, "SYNC_LEASE_RENEW_SECONDS", 0.2),
            patch.object(google_calendar, "_sync_cycle", slow_cycle),
        ):
            google_calendar.run_sync_cycle()
        self.assertFalse(observed["intruder"], "the lease expired while the cycle was still running")
        self.assertTrue(google_calendar_store.claim_lease(google_calendar.SYNC_LEASE_NAME, "intruder", 1))


class AdapterCalendarEndpointsTests(unittest.TestCase):
    def test_calendar_section_requires_admin_and_returns_payload(self) -> None:
        from webapp.adapter import app as adapter_app

        with (
            patch.dict(os.environ, {"SURPRIZ_ADMIN_SECRET": "test-secret", "SURPRIZ_ADAPTER_TOKEN": "test-token"}),
            patch.multiple(
                adapter_app,
                _initialize_idempotency_database=lambda: None,
                init_customer_store=lambda: None,
                _ensure_customer_admin_columns=lambda: None,
                init_addon_store=lambda: None,
                init_partner_store=lambda: None,
                init_recommendation_store=lambda: None,
                init_promotion_store=lambda: None,
                init_admin_notifications_store=lambda: None,
                init_google_calendar=lambda: None,
                get_admin_by_id=lambda _admin_id: {"id": 1, "username": "admin"},
                get_calendar_admin_payload=lambda base: {"status": {"redirect_uri": f"{base}cb"}, "events": []},
                preview_recognition=lambda text: {"programs": [], "characters": [text], "matched": True},
                complete_authorization=lambda code, state: {"account_email": "owner@gmail.com"},
                import_calendar_now=lambda: {"total": 0},
            ),
        ):
            application = adapter_app.create_app()
            application.config.update(TESTING=True)
            client = application.test_client()
            headers = {"X-Adapter-Token": "test-token"}

            self.assertEqual(client.get("/api/v2/admin/section/calendar", headers=headers).status_code, 401)
            self.assertEqual(
                client.get("/api/v2/admin/google-calendar/callback?code=x&state=y", headers=headers).status_code,
                401,
            )

            with client.session_transaction() as session:
                session[adapter_app.ADMIN_SESSION_KEY] = 1
            payload = client.get("/api/v2/admin/section/calendar", headers=headers).get_json()
            self.assertTrue(payload["success"])
            self.assertEqual(payload["status"]["redirect_uri"], "http://localhost/cb")

            preview = client.post(
                "/api/v2/admin/section/calendar", headers=headers, json={"action": "preview", "text": "Дэдпул"}
            ).get_json()
            self.assertEqual(preview["recognition"]["characters"], ["Дэдпул"])

            connected = client.get("/api/v2/admin/google-calendar/callback?code=x&state=y", headers=headers)
            self.assertEqual(connected.status_code, 200)
            self.assertTrue(connected.get_json()["success"])

            unknown = client.post("/api/v2/admin/section/calendar", headers=headers, json={"action": "nope"})
            self.assertEqual(unknown.status_code, 400)


if __name__ == "__main__":
    unittest.main()


def _site_order(order_id: int, day: str, time_from: str, time_to: str, characters: list[str], program: str = "") -> dict[str, Any]:
    return {
        "id": order_id, "public_id": f"SRP-{order_id:05d}", "status": "new", "celebration_date": day,
        "time_from": time_from, "time_to": time_to, "program_slug": program, "character_slugs": characters,
    }


class ReviewFixesImportTests(TempDatabaseMixin, unittest.TestCase):
    day = "2099-10-05"

    def _rows(self, events: list[dict[str, Any]], **kwargs: Any) -> dict[str, dict[str, Any]]:
        rows = google_calendar.build_imported_rows(events, calendar_id="cal", matcher=_matcher(), **kwargs)
        return {row["event_id"]: row for row in rows}

    def test_generic_mention_skips_costume_sold_on_the_site(self) -> None:
        sold = _site_order(1, self.day, "14:00", "15:00", ["spiderman-n1"])
        rows = self._rows(
            [_event("gen", "Человек-паук, Петя 5 лет", f"{self.day}T15:00:00+05:00", f"{self.day}T16:00:00+05:00")],
            site_orders=[sold],
        )
        self.assertEqual(rows["gen"]["character_slugs"], ["spiderman-n2"])
        self.assertEqual(rows["gen"]["conflicts"], [])

    def test_specific_costume_clash_is_flagged(self) -> None:
        sold = _site_order(2, self.day, "15:00", "16:00", ["deadpool"], program="standard-program")
        rows = self._rows(
            [_event("dup", "Дэдпул", f"{self.day}T16:30:00+05:00", f"{self.day}T17:30:00+05:00")],
            site_orders=[sold],
        )
        self.assertTrue(rows["dup"]["blocks_time"])
        self.assertEqual(rows["dup"]["conflicts"][0]["order"]["public_id"], "SRP-00002")
        self.assertIn("SRP-00002", rows["dup"]["note"])

    def test_site_event_moved_in_google_blocks_its_new_time(self) -> None:
        order = _site_order(3, self.day, "15:00", "16:00", ["ladybug-cat-noir"], program="standard-program")
        own = {"extendedProperties": {"private": {"surprizOrderId": "SRP-00003"}}}
        same = self._rows(
            [_event("e", "Стандарт (Леди Баг)", f"{self.day}T15:00:00+05:00", f"{self.day}T16:00:00+05:00", **own)],
            site_orders=[order],
        )["e"]
        self.assertEqual(same["match_status"], "own")
        self.assertFalse(same["blocks_time"])

        moved = self._rows(
            [_event("e", "Стандарт (Леди Баг)", f"{self.day}T18:00:00+05:00", f"{self.day}T19:00:00+05:00", **own)],
            site_orders=[order],
        )["e"]
        self.assertEqual(moved["match_status"], "own_moved")
        self.assertTrue(moved["blocks_time"])
        self.assertEqual(moved["program_slugs"], ["standard-program"])
        self.assertEqual(moved["character_slugs"], ["ladybug-cat-noir"])
        self.assertEqual(moved["conflicts"], [])
        self.assertIn("15:00–16:00", moved["note"])

        by_mapping = self._rows(
            [_event("mapped", "Стандарт", f"{self.day}T18:00:00+05:00", f"{self.day}T19:00:00+05:00")],
            site_orders=[order], own_event_orders={"mapped": 3},
        )["mapped"]
        self.assertEqual(by_mapping["match_status"], "own_moved")

    def test_all_day_event_uses_time_written_in_text(self) -> None:
        next_day = "2099-10-06"
        rows = self._rows(
            [
                _event("clock", "15:00 Стандарт, Дэдпул", self.day, next_day, transparency="transparent"),
                _event("range", "Дэдпул с 12 до 14", self.day, next_day),
                _event("dash", "Дэдпул 10.30–12.00", self.day, next_day),
                _event("date", "05.10 Дэдпул", self.day, next_day),
                _event("free", "Отпуск", self.day, next_day, transparency="transparent"),
            ]
        )
        self.assertEqual((rows["clock"]["start_local"], rows["clock"]["end_local"]), (f"{self.day}T15:00", f"{self.day}T16:00"))
        self.assertEqual(rows["clock"]["match_status"], "matched")
        self.assertFalse(rows["clock"]["all_day"])
        self.assertEqual((rows["range"]["start_local"], rows["range"]["end_local"]), (f"{self.day}T12:00", f"{self.day}T14:00"))
        self.assertEqual((rows["dash"]["start_local"], rows["dash"]["end_local"]), (f"{self.day}T10:30", f"{self.day}T12:00"))
        self.assertTrue(rows["date"]["all_day"])
        self.assertTrue(rows["date"]["blocks_time"])
        self.assertEqual(rows["free"]["match_status"], "free")

    def test_parse_text_time(self) -> None:
        cases = {
            "в 15:00": (900, None),
            "15.00 Стандарт": (900, None),
            "15:00-16:30": (900, 990),
            "с 9 до 11": (540, 660),
            "05.10 Дэдпул": None,
            "05.10.2099 в 17:30": (1050, None),
            "+998 90 123-45-67": None,
            "3:00 ночи": None,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(google_calendar.parse_text_time(text), expected)


class ReviewFixesAlertTests(TempDatabaseMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.day = (date.today() + timedelta(days=5)).isoformat()
        self.sent: list[str] = []
        self.alert_patch = patch.object(admin_notifications, "send_admin_alert", lambda text: self.sent.append(text) or 1)
        self.alert_patch.start()

    def tearDown(self) -> None:
        self.alert_patch.stop()
        super().tearDown()

    def test_new_unmatched_and_clashing_events_alert_once(self) -> None:
        rows = google_calendar.build_imported_rows(
            [
                _event("u1", "Праздник у Ани", f"{self.day}T15:00:00+05:00", f"{self.day}T16:00:00+05:00"),
                _event("c1", "Дэдпул", f"{self.day}T18:00:00+05:00", f"{self.day}T19:00:00+05:00"),
                _event("old", "Непонятно что", "2000-01-01T15:00:00+05:00", "2000-01-01T16:00:00+05:00"),
            ],
            calendar_id="cal", matcher=_matcher(),
            site_orders=[_site_order(9, self.day, "18:30", "19:30", ["deadpool"])],
        )
        google_calendar._notify_import_findings(rows)
        google_calendar._notify_import_findings(rows)
        self.assertEqual(len(self.sent), 2)
        self.assertIn("не распознано 1 событие", self.sent[0])
        self.assertIn("Праздник у Ани", self.sent[0])
        self.assertNotIn("Непонятно", self.sent[0])
        self.assertIn("двойная бронь", self.sent[1])
        self.assertIn("SRP-00009", self.sent[1])

    def test_auth_error_alerts_once(self) -> None:
        google_calendar._set_auth_error("Google отозвал доступ")
        google_calendar._set_auth_error("Google отозвал доступ")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("отключился", self.sent[0])

    def test_long_import_failure_alerts_once(self) -> None:
        google_calendar._note_import_failure("Нет связи с Google")
        self.assertEqual(self.sent, [])
        past = (datetime.now(timezone.utc) - timedelta(minutes=45)).replace(microsecond=0).isoformat()
        google_calendar_store.set_settings({"import_failing_since": past})
        google_calendar._note_import_failure("Нет связи с Google")
        google_calendar._note_import_failure("Нет связи с Google")
        self.assertEqual(len(self.sent), 1)
        self.assertIn("больше 30 минут", self.sent[0])


class ReviewFixesSecurityTests(TempDatabaseMixin, unittest.TestCase):
    def test_secrets_are_encrypted_at_rest_and_unreadable_without_the_key(self) -> None:
        google_calendar_store.set_settings({"refresh_token": "rt-secret", "client_secret": "cs", "calendar_id": "cal"})
        with self._connect() as connection:
            raw = dict(connection.execute("SELECT key, value FROM google_calendar_settings").fetchall())
        self.assertTrue(raw["refresh_token"].startswith("enc1:"))
        self.assertNotIn("rt-secret", raw["refresh_token"])
        self.assertEqual(raw["calendar_id"], "cal")
        self.assertEqual(google_calendar_store.get_setting("refresh_token"), "rt-secret")

        with patch.dict(os.environ, {google_calendar_store.TOKEN_KEY_ENV: Fernet.generate_key().decode()}):
            self.assertEqual(google_calendar_store.get_setting("refresh_token"), "")
        with patch.dict(os.environ, {google_calendar_store.TOKEN_KEY_ENV: ""}):
            self.assertEqual(google_calendar_store.get_setting("refresh_token"), "")
            self.assertFalse(google_calendar._is_connected(google_calendar._settings()))
            with self.assertRaises(google_calendar_store.TokenKeyMissing):
                google_calendar_store.set_settings({"refresh_token": "x"})
            with self.assertRaises(google_calendar.GoogleCalendarNotConfigured):
                google_calendar.build_authorization_url("https://example.com/cb")
            with self.assertRaises(google_calendar.GoogleCalendarNotConfigured):
                google_calendar.save_client_credentials("id.apps.googleusercontent.com", "secret")
            self.assertIn("GOOGLE_CALENDAR_TOKEN_KEY", google_calendar.get_admin_payload()["status"]["auth_error"])

    def test_worker_is_off_unless_enabled(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_CALENDAR_WORKER", None)
            self.assertFalse(google_calendar.worker_enabled())
        with patch.dict(os.environ, {"GOOGLE_CALENDAR_WORKER": "1"}):
            self.assertTrue(google_calendar.worker_enabled())

    def test_disconnect_revokes_in_body_and_forgets_calendar(self) -> None:
        google = FakeGoogle()
        with patch.object(google_calendar, "_http_request", google):
            google_calendar_store.set_settings({"refresh_token": "rt", "calendar_id": "cal", "calendar_summary": "Заказы"})
            google_calendar.disconnect()
        revoke = next(kwargs for method, url, kwargs in google.calls if url == google_calendar.GOOGLE_REVOKE_URL)
        self.assertEqual(revoke.get("data"), {"token": "rt"})
        self.assertNotIn("params", revoke)
        self.assertEqual(google_calendar_store.get_setting("calendar_id"), "")

    def test_event_id_salt_is_stable(self) -> None:
        first = google_calendar._install_salt()
        self.assertEqual(google_calendar_store.ensure_setting("event_id_salt", "zzzzzz"), first)
        self.assertEqual(google_calendar._install_salt(), first)

    def test_matcher_reads_only_active_catalog(self) -> None:
        calls: list[dict[str, Any]] = []

        def fake_list(**kwargs: Any) -> list[dict[str, Any]]:
            calls.append(kwargs)
            return []

        with patch.object(google_calendar, "list_characters", fake_list):
            google_calendar.CalendarMatcher.from_catalog()
        self.assertTrue(calls)
        self.assertTrue(all(call.get("status") == "active" for call in calls))


class ReviewFixesExportTests(OrderExportTests):
    def test_forbidden_delete_keeps_the_event_link_and_retries(self) -> None:
        order_id = self._seed_order()
        customer_store.set_order_confirmation(order_id, "confirmed", source="telegram")
        google_calendar.process_order_queue()
        self.assertIsNotNone(google_calendar_store.get_order_event(order_id))

        original = self.google.__call__

        def forbid_delete(method: str, url: str, **kwargs: Any) -> FakeResponse:
            if method == "DELETE":
                self.google.calls.append((method, url, kwargs))
                return FakeResponse(403, {"error": {"errors": [{"reason": "forbidden"}], "message": "Forbidden"}})
            return original(method, url, **kwargs)

        with patch.object(google_calendar, "_http_request", forbid_delete):
            customer_store.set_order_confirmation(order_id, "unconfirmed", source="telegram")
            result = google_calendar.process_order_queue()
        self.assertEqual(result["failed"], 1)
        self.assertIsNotNone(google_calendar_store.get_order_event(order_id))
        self.assertEqual(google_calendar_store.queue_stats()["pending"], 1)

