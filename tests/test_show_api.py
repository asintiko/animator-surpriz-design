from __future__ import annotations

import unittest
from unittest.mock import patch

import app as app_module
from core.catalog_site import _format_age
from core.customer_store import _format_program_age


class ShowApiTests(unittest.TestCase):
    def test_zero_age_bounds_are_not_rendered(self) -> None:
        self.assertEqual(_format_age(0, 0), "")
        self.assertEqual(_format_program_age(0, 0), "")

    def test_catalog_endpoint_uses_short_public_cache_and_etag(self) -> None:
        payload = {"version": 3, "characters": []}
        with patch.object(app_module, "build_frontend_catalog_payload", return_value=payload):
            client = app_module.app.test_client()
            first = client.get("/api/catalogs")
            conditional = client.get("/api/catalogs", headers={"If-None-Match": first.headers["ETag"]})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json(), payload)
        self.assertEqual(
            first.headers["Cache-Control"],
            "public, max-age=60, stale-while-revalidate=300",
        )
        self.assertTrue(first.headers["ETag"])
        self.assertEqual(conditional.status_code, 304)

    def test_show_endpoint_is_publicly_cacheable_and_conditional(self) -> None:
        payload = {"version": 1, "shows": [{"id": "cryo-show"}]}
        with patch.object(app_module, "build_frontend_show_payload", return_value=payload):
            client = app_module.app.test_client()
            first = client.get("/api/shows")
            conditional = client.get("/api/shows", headers={"If-None-Match": first.headers["ETag"]})
            alias = client.get("/surpriz/api/shows")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.get_json(), payload)
        self.assertEqual(
            first.headers["Cache-Control"],
            "public, max-age=60, stale-while-revalidate=300",
        )
        self.assertTrue(first.headers["ETag"])
        self.assertEqual(conditional.status_code, 304)
        self.assertEqual(alias.status_code, 200)

    def test_versioned_landing_assets_are_immutable(self) -> None:
        client = app_module.app.test_client()

        mutable = client.get("/surpriz/assets/show-programs.css")
        versioned = client.get("/surpriz/assets/show-programs.css?v=20260807-release4")

        self.assertEqual(mutable.status_code, 200)
        self.assertEqual(mutable.headers["Cache-Control"], "public, max-age=3600, stale-while-revalidate=86400")
        self.assertEqual(versioned.status_code, 200)
        self.assertEqual(versioned.headers["Cache-Control"], "public, max-age=31536000, immutable")
        mutable.close()
        versioned.close()


if __name__ == "__main__":
    unittest.main()
