from __future__ import annotations

import unittest

from core.loader import rewrite_legacy_public_urls
from core.routing import resolve_route_redirect


class LegacySiteRouteTests(unittest.TestCase):
    def test_removed_public_pages_redirect_to_current_routes(self) -> None:
        cases = {
            "prices": "/show-programs/",
            "contacts": "/",
            "o-nas": "/",
            "v3": "/",
            "v4": "/",
            "v5": "/",
        }

        for requested_path, expected_target in cases.items():
            with self.subTest(requested_path=requested_path):
                self.assertEqual(resolve_route_redirect(requested_path), expected_target)

    def test_frozen_page_links_use_current_routes(self) -> None:
        source = '<a href="/prices/">Цены</a><a href="/contacts/">Контакты</a><a href="/o-nas/">О нас</a>'

        rewritten = rewrite_legacy_public_urls(source)

        self.assertNotIn('href="/prices/', rewritten)
        self.assertNotIn('href="/contacts/', rewritten)
        self.assertNotIn('href="/o-nas/', rewritten)
        self.assertIn('href="/show-programs/"', rewritten)


if __name__ == "__main__":
    unittest.main()
