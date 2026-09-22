from __future__ import annotations

import unittest

from core.v2_theme import build_body_prefix_html, build_body_suffix_html, build_header_html, render_v2_page


class V2ThemeNavigationTests(unittest.TestCase):
    def test_standard_header_contains_accessible_character_dropdown(self) -> None:
        header = build_header_html(active="catalog")

        self.assertIn('data-character-menu', header)
        self.assertIn('data-character-menu-toggle', header)
        self.assertIn('aria-controls="character-navigation-profile"', header)
        self.assertIn('aria-expanded="false"', header)
        self.assertIn('class="nav-menu__toggle is-active"', header)
        self.assertIn('aria-current="page"', header)
        self.assertEqual(header.count('id="character-navigation-profile"'), 1)

        for category in ("all", "superheroes", "princesses", "boys", "girls", "cartoons"):
            self.assertIn(f'/catalog/?character={category}#characters', header)
            self.assertIn(f'data-character-filter="{category}"', header)

    def test_builder_and_account_headers_reuse_landing_menu_contract(self) -> None:
        for active in ("builder", "account"):
            with self.subTest(active=active):
                header = build_header_html(active=active)
                self.assertIn('class="header"', header)
                self.assertIn('data-character-menu', header)
                self.assertIn('aria-controls="character-navigation-profile"', header)
                self.assertIn('/catalog/?character=cartoons#characters', header)

    def test_body_suffix_loads_character_navigation_before_v2_runtime(self) -> None:
        suffix = build_body_suffix_html()

        navigation_index = suffix.index('/surpriz/navigation.js')
        v2_index = suffix.index('/v2/v2.js')
        self.assertLess(navigation_index, v2_index)

    def test_inline_icon_sprite_contains_selection_checkmark(self) -> None:
        prefix = build_body_prefix_html()

        self.assertIn('<symbol id="i-check"', prefix)
        self.assertIn('<symbol id="i-clock"', prefix)

    def test_account_footer_has_one_balanced_navigation_list(self) -> None:
        page = render_v2_page(
            '<main id="content"></main>',
            title="Профиль",
            description="Личный кабинет",
            canonical_path="/account/",
            active="account",
        )

        self.assertEqual(page.footer_html.count('<ul class="surpriz-site-footer__links">'), 1)
        self.assertEqual(page.footer_html.count("<ul"), page.footer_html.count("</ul>"))


if __name__ == "__main__":
    unittest.main()
