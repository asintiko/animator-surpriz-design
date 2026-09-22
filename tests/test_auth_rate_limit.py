from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from core.auth_rate_limit import (
    TelegramOTPRateLimiter,
    TelegramOTPRateLimitPolicy,
)
from core import customer_panel


PROJECT_ROOT = Path(__file__).resolve().parent.parent


class AuthRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "admin" / "site_admin.sqlite3"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _policy(self, **overrides: int) -> TelegramOTPRateLimitPolicy:
        values = {
            "phone_limit": 100,
            "phone_window_seconds": 600,
            "ip_limit": 100,
            "ip_window_seconds": 600,
            "global_limit": 1_000,
            "global_window_seconds": 60,
            "resend_cooldown_seconds": 0,
            "cleanup_batch_size": 50,
        }
        values.update(overrides)
        return TelegramOTPRateLimitPolicy(**values)

    def test_new_cookie_or_process_cannot_reset_phone_budget(self) -> None:
        policy = self._policy(phone_limit=2)
        phone = "+998 90 123-45-67"

        first = TelegramOTPRateLimiter(self.db_path, policy=policy).consume(
            phone,
            "203.0.113.10",
            now=100,
        )
        second = TelegramOTPRateLimiter(self.db_path, policy=policy).consume(
            "+998901234567",
            "203.0.113.11",
            now=101,
        )
        self.assertTrue(first.allowed)
        self.assertTrue(second.allowed)

        script = """
import sys
from core.auth_rate_limit import TelegramOTPRateLimiter, TelegramOTPRateLimitPolicy

policy = TelegramOTPRateLimitPolicy(
    phone_limit=2,
    phone_window_seconds=600,
    ip_limit=100,
    ip_window_seconds=600,
    global_limit=1000,
    global_window_seconds=60,
    resend_cooldown_seconds=0,
    cleanup_batch_size=50,
)
decision = TelegramOTPRateLimiter(sys.argv[1], policy=policy).consume(
    "+998901234567",
    "198.51.100.50",
    now=102,
)
print(int(decision.allowed), decision.retry_after)
"""
        completed = subprocess.run(
            [sys.executable, "-c", script, str(self.db_path)],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.stdout.strip(), "0 598")

        with sqlite3.connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT phone_key, ip_key FROM telegram_otp_send_events"
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertNotIn("998901234567", repr(rows))
        self.assertNotIn("203.0.113.10", repr(rows))

    def test_new_cookie_and_phone_cannot_reset_ip_budget(self) -> None:
        policy = self._policy(ip_limit=2)
        ip_address = "2001:db8::10"

        self.assertTrue(
            TelegramOTPRateLimiter(self.db_path, policy=policy)
            .consume("+998901000001", ip_address, now=200)
            .allowed
        )
        self.assertTrue(
            TelegramOTPRateLimiter(self.db_path, policy=policy)
            .consume("+998901000002", "2001:0db8:0:0:0:0:0:10", now=201)
            .allowed
        )
        denied = TelegramOTPRateLimiter(self.db_path, policy=policy).consume(
            "+998901000003",
            ip_address,
            now=202,
        )

        self.assertFalse(denied.allowed)
        self.assertEqual(denied.retry_after, 598)

    def test_concurrent_requests_cannot_overrun_phone_limit(self) -> None:
        policy = self._policy(phone_limit=3)
        limiter = TelegramOTPRateLimiter(self.db_path, policy=policy)
        worker_count = 16
        barrier = threading.Barrier(worker_count)

        def consume(index: int) -> bool:
            barrier.wait()
            return limiter.consume(
                "+998909999999",
                f"198.51.100.{index + 1}",
                now=1_000,
            ).allowed

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            decisions = list(executor.map(consume, range(worker_count)))

        self.assertEqual(sum(decisions), 3)
        with sqlite3.connect(self.db_path) as connection:
            event_count = connection.execute(
                "SELECT COUNT(*) FROM telegram_otp_send_events"
            ).fetchone()[0]
        self.assertEqual(event_count, 3)

    def test_global_budget_returns_retry_after_and_does_not_record_denials(self) -> None:
        policy = self._policy(global_limit=2, global_window_seconds=20)
        limiter = TelegramOTPRateLimiter(self.db_path, policy=policy)

        self.assertEqual(
            limiter.consume("+998901000001", "203.0.113.1", now=100),
            (True, 0),
        )
        self.assertEqual(
            limiter.consume("+998901000002", "203.0.113.2", now=105),
            (True, 0),
        )
        self.assertEqual(
            limiter.consume("+998901000003", "203.0.113.3", now=107),
            (False, 13),
        )
        self.assertEqual(
            limiter.consume("+998901000004", "203.0.113.4", now=119),
            (False, 1),
        )
        self.assertEqual(
            limiter.consume("+998901000005", "203.0.113.5", now=120),
            (True, 0),
        )

        with sqlite3.connect(self.db_path) as connection:
            event_count = connection.execute(
                "SELECT COUNT(*) FROM telegram_otp_send_events"
            ).fetchone()[0]
        self.assertEqual(event_count, 3)

    def test_stale_cleanup_is_bounded(self) -> None:
        policy = self._policy(
            phone_window_seconds=10,
            ip_window_seconds=10,
            global_window_seconds=10,
            cleanup_batch_size=3,
        )
        limiter = TelegramOTPRateLimiter(self.db_path, policy=policy)
        with sqlite3.connect(self.db_path) as connection:
            connection.executemany(
                """
                INSERT INTO telegram_otp_send_events(phone_key, ip_key, created_at)
                VALUES (?, ?, ?)
                """,
                [(f"phone-{index}", f"ip-{index}", 1.0) for index in range(10)],
            )

        decision = limiter.consume("+998901234567", "203.0.113.8", now=100)
        self.assertTrue(decision.allowed)

        with sqlite3.connect(self.db_path) as connection:
            stale_count = connection.execute(
                "SELECT COUNT(*) FROM telegram_otp_send_events WHERE created_at = 1.0"
            ).fetchone()[0]
            total_count = connection.execute(
                "SELECT COUNT(*) FROM telegram_otp_send_events"
            ).fetchone()[0]
        self.assertEqual(stale_count, 7)
        self.assertEqual(total_count, 8)

    def test_public_endpoint_returns_429_and_retry_after(self) -> None:
        app = Flask(__name__)
        app.secret_key = "test"
        customer_panel.register_customer_routes(app)
        limited = {
            "success": False,
            "error_code": "rate_limited",
            "message": "Подождите.",
            "retry_after": 37,
        }
        with patch.object(customer_panel, "_start_telegram_auth", return_value=limited):
            response = app.test_client().post(
                "/api/auth/send-telegram-code",
                json={"phone": "+998901234567", "purpose": "login"},
            )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "37")


if __name__ == "__main__":
    unittest.main()
