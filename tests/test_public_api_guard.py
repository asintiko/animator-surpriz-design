from __future__ import annotations

import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from core import customer_panel
from core.config import DATA_ROOT
from core.public_api_guard import (
    DB_PATH,
    PublicAPIRequestDecision,
    PublicAPIRequestLimiter,
    consume_public_api_request,
)


class PublicAPIGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "admin" / "site_admin.sqlite3"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_uses_canonical_admin_database_by_default(self) -> None:
        self.assertEqual(DB_PATH, DATA_ROOT / "admin" / "site_admin.sqlite3")

    def test_budget_is_durable_and_database_does_not_store_raw_ip(self) -> None:
        first = PublicAPIRequestLimiter(self.db_path).consume(
            "party-builder-geocode",
            "2001:db8::10",
            2,
            100,
            60,
            now=100,
        )
        second = PublicAPIRequestLimiter(self.db_path).consume(
            "party-builder-geocode",
            "2001:0db8:0:0:0:0:0:10",
            2,
            100,
            60,
            now=101,
        )
        denied = PublicAPIRequestLimiter(self.db_path).consume(
            "party-builder-geocode",
            "2001:db8::10",
            2,
            100,
            60,
            now=102,
        )

        self.assertEqual(first, (True, 0))
        self.assertEqual(second, (True, 0))
        self.assertEqual(denied, (False, 58))
        with closing(sqlite3.connect(self.db_path)) as connection:
            rows = connection.execute(
                "SELECT bucket_key, ip_key FROM public_api_request_events"
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(len(bucket_key) == 64 for bucket_key, _ in rows))
        self.assertTrue(all(len(ip_key) == 64 for _, ip_key in rows))
        self.assertNotIn("2001:db8", repr(rows))
        self.assertNotIn("party-builder-geocode", repr(rows))

    def test_concurrent_requests_cannot_overrun_per_ip_limit(self) -> None:
        limiter = PublicAPIRequestLimiter(self.db_path)
        worker_count = 20
        barrier = threading.Barrier(worker_count)

        def consume(_: int) -> bool:
            barrier.wait()
            return limiter.consume(
                "party-builder-suggest",
                "203.0.113.8",
                4,
                100,
                60,
                now=1_000,
            ).allowed

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            decisions = list(executor.map(consume, range(worker_count)))

        self.assertEqual(sum(decisions), 4)
        with closing(sqlite3.connect(self.db_path)) as connection:
            event_count = connection.execute(
                "SELECT COUNT(*) FROM public_api_request_events"
            ).fetchone()[0]
        self.assertEqual(event_count, 4)

    def test_concurrent_requests_cannot_overrun_global_limit(self) -> None:
        limiter = PublicAPIRequestLimiter(self.db_path)
        worker_count = 20
        barrier = threading.Barrier(worker_count)

        def consume(index: int) -> bool:
            barrier.wait()
            return limiter.consume(
                "party-builder-geocode",
                f"198.51.100.{index + 1}",
                100,
                5,
                60,
                now=2_000,
            ).allowed

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            decisions = list(executor.map(consume, range(worker_count)))

        self.assertEqual(sum(decisions), 5)
        with closing(sqlite3.connect(self.db_path)) as connection:
            event_count = connection.execute(
                "SELECT COUNT(*) FROM public_api_request_events"
            ).fetchone()[0]
        self.assertEqual(event_count, 5)

    def test_buckets_have_isolated_global_budgets(self) -> None:
        limiter = PublicAPIRequestLimiter(self.db_path)

        self.assertEqual(
            limiter.consume("geocode", "203.0.113.1", 100, 2, 20, now=100),
            (True, 0),
        )
        self.assertEqual(
            limiter.consume("geocode", "203.0.113.2", 100, 2, 20, now=105),
            (True, 0),
        )
        self.assertEqual(
            limiter.consume("geocode", "203.0.113.3", 100, 2, 20, now=107),
            (False, 13),
        )
        self.assertEqual(
            limiter.consume("suggest", "203.0.113.3", 100, 2, 20, now=107),
            (True, 0),
        )

    def test_stale_cleanup_is_bounded_and_preserves_unexpired_other_bucket(self) -> None:
        limiter = PublicAPIRequestLimiter(self.db_path, cleanup_batch_size=3)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.executemany(
                """
                INSERT INTO public_api_request_events(
                    bucket_key, ip_key, created_at, expires_at
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    ("a" * 64, f"{index:064x}", 1.0, 2.0)
                    for index in range(10)
                ]
                + [("b" * 64, "c" * 64, 1.0, 1_000.0)],
            )
            connection.commit()

        decision = limiter.consume("short-window", "203.0.113.8", 10, 10, 5, now=100)

        self.assertEqual(decision, (True, 0))
        with closing(sqlite3.connect(self.db_path)) as connection:
            stale_count = connection.execute(
                "SELECT COUNT(*) FROM public_api_request_events WHERE expires_at = 2.0"
            ).fetchone()[0]
            long_lived_count = connection.execute(
                "SELECT COUNT(*) FROM public_api_request_events WHERE expires_at = 1000.0"
            ).fetchone()[0]
        self.assertEqual(stale_count, 7)
        self.assertEqual(long_lived_count, 1)

    def test_invalid_or_missing_addresses_share_conservative_unknown_budget(self) -> None:
        self.assertEqual(
            consume_public_api_request(
                "party-builder-geocode",
                None,
                1,
                100,
                60,
                db_path=self.db_path,
                now=100,
            ),
            (True, 0),
        )
        self.assertEqual(
            consume_public_api_request(
                "party-builder-geocode",
                "not-an-ip",
                1,
                100,
                60,
                db_path=self.db_path,
                now=101,
            ),
            (False, 59),
        )

    def test_rejects_invalid_policy_and_bucket_values(self) -> None:
        limiter = PublicAPIRequestLimiter(self.db_path)
        invalid_calls = (
            ("", "203.0.113.1", 1, 1, 60),
            ("valid", "203.0.113.1", 0, 1, 60),
            ("valid", "203.0.113.1", 1, 0, 60),
            ("valid", "203.0.113.1", 1, 1, 0),
        )
        for arguments in invalid_calls:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    limiter.consume(*arguments, now=100)

    def test_http_guard_returns_429_with_retry_after(self) -> None:
        app = Flask(__name__)
        with (
            app.test_request_context("/api", environ_base={"REMOTE_ADDR": "203.0.113.10"}),
            patch.object(
                customer_panel,
                "consume_public_api_request",
                return_value=PublicAPIRequestDecision(False, 23),
            ),
        ):
            response, status = customer_panel._guard_public_api(
                "party-builder-suggest-address",
                per_ip_limit=30,
                global_limit=300,
            )
        self.assertEqual(status, 429)
        self.assertEqual(response.headers["Retry-After"], "23")

    def test_http_guard_fails_closed_when_sqlite_is_unavailable(self) -> None:
        app = Flask(__name__)
        with (
            app.test_request_context("/api", environ_base={"REMOTE_ADDR": "203.0.113.10"}),
            patch.object(
                customer_panel,
                "consume_public_api_request",
                side_effect=sqlite3.OperationalError("database is locked"),
            ),
        ):
            response, status = customer_panel._guard_public_api(
                "party-builder-resolve-address",
                per_ip_limit=12,
                global_limit=120,
            )
        self.assertEqual(status, 503)
        self.assertEqual(response.get_json()["error_code"], "rate_limit_unavailable")


if __name__ == "__main__":
    unittest.main()
