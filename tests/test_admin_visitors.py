from __future__ import annotations

import os
import signal
import sqlite3
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from jinja2 import Environment, FileSystemLoader

from core import admin_store


class _ClosingTestConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class AdminVisitorStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_root = Path(self.temp_dir.name) / "admin"
        self.db_path = self.db_root / "site_admin.sqlite3"
        self.forms_root = Path(self.temp_dir.name) / "forms"
        self.environment = patch.dict(
            os.environ,
            {
                "SURPRIZ_ADMIN_USERNAME": "test-admin",
                "SURPRIZ_ADMIN_PASSWORD": "unit-test-password-only",
                "SURPRIZ_ADMIN_BOOTSTRAP": "",
            },
        )
        self.patchers = [
            patch.object(admin_store, "DB_ROOT", self.db_root),
            patch.object(admin_store, "DB_PATH", self.db_path),
            patch.object(admin_store, "FORMS_ROOT", self.forms_root),
            patch.object(admin_store, "init_catalog_store"),
            patch.object(
                admin_store,
                "get_catalog_summary",
                return_value={"character": 0, "category": 0, "tag": 0},
            ),
        ]
        self.environment.start()
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.environment.stop()
        self.temp_dir.cleanup()

    def _connect(self) -> sqlite3.Connection:
        self.db_root.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, factory=_ClosingTestConnection)
        connection.row_factory = sqlite3.Row
        return connection

    def _create_customer_table(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS customer_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_display TEXT NOT NULL,
                    full_name TEXT NOT NULL DEFAULT ''
                );
                """
            )

    def test_legacy_visit_migration_is_private_and_idempotent(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE visit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL,
                    remote_addr TEXT,
                    user_agent TEXT,
                    visited_at TEXT NOT NULL
                );
                """
            )
            connection.executemany(
                """
                INSERT INTO visit_events(path, remote_addr, user_agent, visited_at)
                VALUES (?, ?, ?, ?)
                """,
                [
                    ("/", "203.0.113.10", "Test Browser", "2026-08-06T05:00:00+00:00"),
                    ("/catalog/", "203.0.113.10", "Test Browser", "2026-08-06T05:05:00+00:00"),
                    ("/shows/", "", "", "2026-08-06T05:10:00+00:00"),
                ],
            )

        admin_store.init_admin_store()
        with self._connect() as connection:
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(visit_events)")}
            rows_before = connection.execute(
                "SELECT id, visitor_id, remote_addr FROM visit_events ORDER BY id"
            ).fetchall()
            salt_before = connection.execute(
                "SELECT value FROM site_settings WHERE key = ?",
                (admin_store.VISITOR_ID_SALT_SETTING,),
            ).fetchone()[0]

        self.assertTrue({"visitor_id", "customer_id", "referrer"}.issubset(columns))
        self.assertTrue(all(row["visitor_id"].startswith("v1_") for row in rows_before))
        self.assertEqual(rows_before[0]["visitor_id"], rows_before[1]["visitor_id"])
        self.assertNotEqual(rows_before[1]["visitor_id"], rows_before[2]["visitor_id"])
        self.assertEqual(rows_before[0]["remote_addr"], "203.0.×.×")
        self.assertNotIn("203.0.113.10", repr(rows_before))

        admin_store.init_admin_store()
        with self._connect() as connection:
            rows_after = connection.execute(
                "SELECT id, visitor_id, remote_addr FROM visit_events ORDER BY id"
            ).fetchall()
            salt_after = connection.execute(
                "SELECT value FROM site_settings WHERE key = ?",
                (admin_store.VISITOR_ID_SALT_SETTING,),
            ).fetchone()[0]

        self.assertEqual([tuple(row) for row in rows_before], [tuple(row) for row in rows_after])
        self.assertEqual(salt_before, salt_after)

    def test_visit_storage_masks_ip_truncates_ua_and_expires_old_events(self) -> None:
        fixed_now = datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)
        with patch.object(admin_store, "utcnow", return_value=fixed_now):
            admin_store.init_admin_store()
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO visit_events(path, remote_addr, user_agent, visitor_id, visited_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    ("/old/", "198.51.100.99", "x" * 700, "v1_old", (fixed_now - timedelta(days=181)).isoformat()),
                    ("/recent/", "198.51.100.77", "y" * 700, "v1_recent", fixed_now.isoformat()),
                ],
            )

        with patch.object(admin_store, "utcnow", return_value=fixed_now):
            admin_store.init_admin_store()

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT path, remote_addr, length(user_agent) AS ua_length FROM visit_events ORDER BY id"
            ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], "/recent/")
        self.assertEqual(rows[0]["remote_addr"], "198.51.×.×")
        self.assertEqual(rows[0]["ua_length"], 320)

    def test_log_visit_accepts_legacy_and_enriched_calls(self) -> None:
        admin_store.init_admin_store()
        self._create_customer_table()
        with self._connect() as connection:
            customer_id = int(
                connection.execute(
                    "INSERT INTO customer_accounts(phone_display, full_name) VALUES (?, ?)",
                    ("+998 (90) 123-45-67", "Тестовый клиент"),
                ).lastrowid
            )

        user_agent = (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1"
        )
        admin_store.log_visit("/legacy/", "203.0.113.42", user_agent)
        admin_store.log_visit(
            "/catalog/hero/",
            "203.0.113.42",
            user_agent,
            visitor_id="browser-cookie-value",
            customer_id=customer_id,
            referrer="https://search.example/results?q=private#details",
        )

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT visitor_id, customer_id, referrer FROM visit_events ORDER BY id"
            ).fetchall()

        self.assertTrue(rows[0]["visitor_id"].startswith("v1_"))
        self.assertTrue(rows[1]["visitor_id"].startswith("v1_"))
        self.assertNotEqual(rows[1]["visitor_id"], "browser-cookie-value")
        self.assertEqual(rows[1]["customer_id"], customer_id)
        self.assertEqual(rows[1]["referrer"], "https://search.example/results")

        report = admin_store.list_admin_visitors(search="123-45-67")
        self.assertEqual(report["pagination"]["total"], 1)
        visitor = report["items"][0]
        self.assertEqual(visitor["masked_ip"], "203.0.×.×")
        self.assertEqual(visitor["browser"], "Safari")
        self.assertEqual(visitor["device"], "iPhone")
        self.assertEqual(visitor["customer"]["name"], "Тестовый клиент")
        self.assertEqual(visitor["referrer"], "search.example/results")
        self.assertNotIn("203.0.113.42", repr(report))

    def test_visitor_report_aggregates_sessions_and_paginates(self) -> None:
        admin_store.init_admin_store()
        self._create_customer_table()
        with self._connect() as connection:
            customer_id = int(
                connection.execute(
                    "INSERT INTO customer_accounts(phone_display, full_name) VALUES (?, ?)",
                    ("+998 (91) 000-00-01", "Реальный клиент"),
                ).lastrowid
            )
            connection.executemany(
                """
                INSERT INTO visit_events(
                    path, remote_addr, user_agent, visitor_id, customer_id, referrer, visited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        "/",
                        "198.51.100.22",
                        "Mozilla/5.0 (Windows NT 10.0) Chrome/126.0 Safari/537.36",
                        "v1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        None,
                        "https://google.com/search?q=secret",
                        "2026-08-06T05:00:00+00:00",
                    ),
                    (
                        "/catalog/",
                        "198.51.100.22",
                        "Mozilla/5.0 (Windows NT 10.0) Chrome/126.0 Safari/537.36",
                        "v1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        None,
                        "",
                        "2026-08-06T05:10:00+00:00",
                    ),
                    (
                        "/party-builder/",
                        "198.51.100.22",
                        "Mozilla/5.0 (Windows NT 10.0) Chrome/126.0 Safari/537.36",
                        "v1_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                        customer_id,
                        "",
                        "2026-08-06T06:00:00+00:00",
                    ),
                    (
                        "/show-programs/",
                        "2001:db8:abcd:0012::1",
                        "Mozilla/5.0 (Linux; Android 14; Mobile) Chrome/126.0",
                        "v1_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        None,
                        "",
                        "2026-08-06T05:30:00+00:00",
                    ),
                ],
            )

        first_page = admin_store.list_admin_visitors(page=1, per_page=1)
        self.assertEqual(first_page["summary"]["visitors"], 2)
        self.assertEqual(first_page["summary"]["sessions"], 3)
        self.assertEqual(first_page["summary"]["page_views"], 4)
        self.assertEqual(first_page["summary"]["identified"], 1)
        self.assertEqual(first_page["pagination"]["total"], 2)
        self.assertEqual(first_page["pagination"]["pages"], 2)
        self.assertTrue(first_page["pagination"]["has_next"])

        visitor = first_page["items"][0]
        self.assertEqual(visitor["display_id"], "VIS-AAAAAAAA")
        self.assertEqual(visitor["page_views"], 3)
        self.assertEqual(visitor["sessions"], 2)
        self.assertEqual(visitor["first_path"], "/")
        self.assertEqual(visitor["last_path"], "/party-builder/")
        self.assertEqual(visitor["referrer"], "google.com/search")
        self.assertEqual(visitor["customer"]["phone"], "+998 (91) 000-00-01")
        self.assertNotIn("198.51.100.22", repr(first_page))

        anonymous = admin_store.list_admin_visitors(search="show-programs")
        self.assertEqual(anonymous["pagination"]["total"], 1)
        self.assertIsNone(anonymous["items"][0]["customer"])
        self.assertEqual(anonymous["items"][0]["masked_ip"], "2001:0db8:…")

    def test_visitor_report_handles_production_sized_history_before_proxy_timeout(self) -> None:
        admin_store.init_admin_store()
        self._create_customer_table()
        started_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
        rows = []
        for index in range(20_000):
            visitor_number = index % 2_000
            rows.append(
                (
                    f"/catalog/page-{index % 40}/",
                    f"198.51.{visitor_number % 100}.×",
                    "Mozilla/5.0 (Linux; Android 14; Mobile) Chrome/126.0",
                    f"v1_{visitor_number:032x}",
                    None,
                    "https://google.com/search?q=party" if index % 10 == 0 else "",
                    (started_at + timedelta(seconds=index * 60)).isoformat(),
                )
            )
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO visit_events(
                    path, remote_addr, user_agent, visitor_id, customer_id, referrer, visited_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

        def deadline_exceeded(_signum, _frame):
            raise AssertionError("Visitor report exceeded the 5 second regression deadline")

        previous_handler = signal.signal(signal.SIGALRM, deadline_exceeded)
        signal.setitimer(signal.ITIMER_REAL, 5)
        started = time.monotonic()
        try:
            report = admin_store.list_admin_visitors(page=1, per_page=30)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)

        self.assertLess(time.monotonic() - started, 5)
        self.assertEqual(report["summary"]["visitors"], 2_000)
        self.assertEqual(report["summary"]["page_views"], 20_000)
        self.assertEqual(report["pagination"]["total"], 2_000)
        self.assertEqual(len(report["items"]), 30)

    def test_same_site_referrer_is_not_reported_as_acquisition_source(self) -> None:
        admin_store.init_admin_store()
        admin_store.log_visit(
            "/catalog/",
            "203.0.113.7",
            "Browser",
            visitor_id="same-site-visitor-cookie",
            referrer="https://www.animator-surpriz.uz/?private=query#fragment",
            site_host="animator-surpriz.uz",
        )

        report = admin_store.list_admin_visitors()
        self.assertEqual(report["items"][0]["referrer"], "Прямой заход")
        self.assertFalse(report["items"][0]["has_referrer"])

    def test_locked_database_does_not_break_visit_logging_or_stats(self) -> None:
        lock_error = sqlite3.OperationalError("database is locked")
        with (
            patch.object(admin_store, "_get_connection", side_effect=lock_error),
            patch.object(admin_store.time, "sleep"),
        ):
            self.assertIsNone(admin_store.log_visit("/", "203.0.113.1", "Browser"))
            stats = admin_store.get_dashboard_stats()
            report = admin_store.list_admin_visitors()

        self.assertEqual(stats["total_page_views"], 0)
        self.assertEqual(stats["recent_visits"], [])
        self.assertTrue(report["unavailable"])
        self.assertEqual(report["items"], [])

    def test_existing_admin_survives_without_bootstrap_environment(self) -> None:
        admin_store.init_admin_store()
        with self._connect() as connection:
            before = tuple(
                connection.execute(
                    "SELECT id, username, password_hash FROM admins ORDER BY id LIMIT 1"
                ).fetchone()
            )

        with patch.dict(
            os.environ,
            {
                "SURPRIZ_ADMIN_USERNAME": "",
                "SURPRIZ_ADMIN_PASSWORD": "",
                "SURPRIZ_ADMIN_BOOTSTRAP": "",
            },
        ):
            admin_store.init_admin_store()

        with self._connect() as connection:
            after = tuple(
                connection.execute(
                    "SELECT id, username, password_hash FROM admins ORDER BY id LIMIT 1"
                ).fetchone()
            )
        self.assertEqual(before, after)

    def test_public_settings_never_expose_or_overwrite_visitor_salt(self) -> None:
        admin_store.init_admin_store()
        with self._connect() as connection:
            salt_before = connection.execute(
                "SELECT value FROM site_settings WHERE key = ?",
                (admin_store.VISITOR_ID_SALT_SETTING,),
            ).fetchone()[0]

        settings = admin_store.get_public_settings()
        self.assertNotIn(admin_store.VISITOR_ID_SALT_SETTING, settings)
        admin_store.update_public_settings({"show_snow": True})

        with self._connect() as connection:
            salt_after = connection.execute(
                "SELECT value FROM site_settings WHERE key = ?",
                (admin_store.VISITOR_ID_SALT_SETTING,),
            ).fetchone()[0]
        self.assertEqual(salt_before, salt_after)

    def test_today_boundary_uses_tashkent_midnight(self) -> None:
        with patch.object(
            admin_store,
            "utcnow",
            return_value=datetime(2026, 8, 5, 20, 30, tzinfo=timezone.utc),
        ):
            day_start = admin_store._local_day_start_utc_iso()

        self.assertEqual(
            datetime.fromisoformat(day_start),
            datetime(2026, 8, 5, 19, 0, tzinfo=timezone.utc),
        )

    def test_visitor_dashboard_template_renders_report_items(self) -> None:
        report = admin_store._empty_visitor_report(page=1, per_page=30)
        report["items"] = [
            {
                "display_id": "VIS-1234ABCD",
                "masked_ip": "203.0.×.×",
                "last_seen_label": "06.08.2026, 12:00",
                "first_seen_label": "06.08.2026, 11:00",
                "page_views": 3,
                "sessions": 1,
                "last_path": "/party-builder/",
                "first_path": "/catalog/",
                "referrer": "google.com/search",
                "has_referrer": True,
                "device": "iPhone",
                "browser": "Safari",
                "customer": None,
            }
        ]
        report["pagination"]["total"] = 1
        report["summary"].update({"visitors": 1, "sessions": 1, "page_views": 3})

        project_root = Path(admin_store.__file__).resolve().parents[1]
        environment = Environment(loader=FileSystemLoader(project_root / "templates"), autoescape=True)
        environment.globals.update(
            url_for=lambda endpoint, **values: f"/{endpoint}",
            get_flashed_messages=lambda **kwargs: [],
        )
        rendered = environment.get_template("admin/dashboard.html").render(
            title="Посетители",
            active_tab="visitors",
            admin={"username": "admin"},
            visitors=report,
            visitor_filters={"search": ""},
            order_summary={},
        )

        self.assertIn("VIS-1234ABCD", rendered)
        self.assertIn("203.0.×.×", rendered)
        self.assertNotIn("203.0.113.42", rendered)


if __name__ == "__main__":
    unittest.main()
