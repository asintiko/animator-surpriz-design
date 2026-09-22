from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

from core import customer_store


class GroupCharacterPricingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.program = {
            "included_characters_count": 2,
            "extra_character_price_3": 350_000,
            "extra_character_price_4_plus": 350_000,
        }
        self.pair = {
            "slug": "ladybug-cat-noir",
            "ensemble_members": ["Леди Баг", "Супер-Кот"],
            "ensemble_included_count": 2,
            "ensemble_extra_member_price": 0,
        }
        self.trio = {
            "slug": "anna-elsa-olaf",
            "ensemble_members": ["Анна", "Эльза", "Олаф"],
            "ensemble_included_count": 2,
            "ensemble_extra_member_price": 0,
        }
        self.solo = {
            "slug": "spider-man",
            "ensemble_members": [],
            "ensemble_included_count": 2,
            "ensemble_extra_member_price": 0,
        }

    def test_pair_consumes_two_program_slots_without_surcharge(self) -> None:
        selection = {self.pair["slug"]: ["Леди Баг", "Супер-Кот"]}

        self.assertEqual(
            customer_store.count_program_character_slots(self.pair, selection[self.pair["slug"]]),
            2,
        )
        self.assertEqual(
            customer_store.calculate_order_character_surcharge(
                self.program,
                [self.pair],
                selection,
            ),
            0,
        )

    def test_trio_requires_two_selected_members_for_its_base_slots(self) -> None:
        selection = {self.trio["slug"]: ["Эльза", "Олаф"]}

        self.assertEqual(
            customer_store.count_program_character_slots(self.trio, selection[self.trio["slug"]]),
            2,
        )
        self.assertEqual(customer_store.calculate_ensemble_surcharge(self.trio, selection[self.trio["slug"]]), 0)

    def test_third_trio_member_uses_duration_scaled_program_tariff(self) -> None:
        selection = {self.trio["slug"]: ["Анна", "Эльза", "Олаф"]}

        self.assertEqual(
            customer_store.calculate_order_character_surcharge(
                self.program,
                [self.trio],
                selection,
                duration_multiplier=2.0,
            ),
            700_000,
        )

    def test_pair_plus_solo_uses_generic_third_character_price(self) -> None:
        selection = {self.pair["slug"]: ["Леди Баг", "Супер-Кот"]}

        self.assertEqual(
            customer_store.calculate_order_character_surcharge(
                self.program,
                [self.pair, self.solo],
                selection,
            ),
            350_000,
        )

    def test_trio_extra_receives_exactly_one_program_extra_price(self) -> None:
        selection = {self.trio["slug"]: ["Анна", "Эльза", "Олаф"]}

        self.assertEqual(
            customer_store.calculate_order_character_surcharge(
                self.program,
                [self.trio],
                selection,
            ),
            350_000,
        )

    def test_order_snapshot_contains_selected_group_members_in_catalog_order(self) -> None:
        self.trio["name"] = "Анна, Эльза и Олаф"

        self.assertEqual(
            customer_store.build_character_name_snapshot(self.trio, ["Олаф", "Анна"]),
            "Анна + Олаф",
        )

    def test_order_snapshot_contains_roster_without_obsolete_fixed_surcharge(self) -> None:
        self.trio["name"] = "Анна, Эльза и Олаф"

        self.assertEqual(
            customer_store.build_character_name_snapshot(
                self.trio,
                ["Анна", "Эльза", "Олаф"],
            ),
            "Анна + Эльза + Олаф",
        )

    def test_client_card_badge_uses_program_tariff_and_character_specific_extras(self) -> None:
        template = (
            Path(__file__).resolve().parents[1] / "templates/site/order_builder_content.html"
        ).read_text(encoding="utf-8")

        self.assertIn("const cardPrice = applyBadgeDurationMultiplier(genericPrice, programInput)", template)
        self.assertNotIn("fixedGroupPrice", template)
        self.assertIn("+ fixedCharacterPrice", template)
        self.assertIn("checked.sort((left, right)", template)

    def test_zootopia_fixed_extra_is_not_duration_multiplied(self) -> None:
        pair = {
            **self.pair,
            "slug": "zootopia",
            "base_price": 1_050_000,
            "ensemble_members": ["Ник", "Джуди"],
        }
        selection = {"zootopia": ["Ник", "Джуди"]}

        self.assertEqual(
            customer_store.calculate_order_character_surcharge(
                self.program,
                [pair],
                selection,
                actual_duration_minutes=120,
                base_duration_minutes=60,
            ),
            100_000,
        )

    def test_neptune_extra_applies_only_when_neptune_is_selected(self) -> None:
        trio = {
            **self.trio,
            "slug": "neptune-mermaids",
            "base_price": 25_000,
            "ensemble_members": ["Нептун (+25 000 сум)", "Розовая Русалочка", "Зелёная Русалочка"],
        }
        self.assertEqual(
            customer_store.calculate_fixed_character_surcharge(
                trio,
                ["Розовая Русалочка", "Зелёная Русалочка"],
            ),
            0,
        )
        self.assertEqual(
            customer_store.calculate_fixed_character_surcharge(
                trio,
                ["Нептун (+25 000 сум)", "Розовая Русалочка"],
            ),
            25_000,
        )

    def test_mascot_requires_two_open_speaking_performers(self) -> None:
        program = {"slug": "standard-program", "included_characters_count": 2}
        mascot = {"slug": "hulk", "name": "Халк (ростовой)", "ensemble_members": []}
        open_one = {"slug": "spider-man", "name": "Человек-паук", "ensemble_members": []}
        open_two = {"slug": "deadpool", "name": "Дэдпул", "ensemble_members": []}

        self.assertIn(
            "двух открытых",
            customer_store.validate_character_performer_rules(
                program,
                [mascot, open_one],
                {},
            ),
        )
        self.assertEqual(
            customer_store.validate_character_performer_rules(
                program,
                [mascot, open_one, open_two],
                {},
            ),
            "",
        )

    def test_client_and_server_duration_rounding_match_on_half_values(self) -> None:
        template = (
            Path(__file__).resolve().parents[1] / "templates/site/order_builder_content.html"
        ).read_text(encoding="utf-8")
        match = re.search(
            r"const scalePriceForDuration = \(amount, actualMinutes, baseMinutes\) => \{.*?^    \};",
            template,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match)
        vectors = [
            (1, 3, 2),
            (3, 3, 2),
            (199_999, 90, 60),
            (200_000, 90, 60),
            (125_001, 100, 60),
        ]
        script = (
            f"{match.group(0)}\n"
            f"const vectors = {json.dumps(vectors)};\n"
            "process.stdout.write(JSON.stringify(vectors.map((entry) => scalePriceForDuration(...entry))));"
        )
        completed = subprocess.run(
            ["node", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        client_values = json.loads(completed.stdout)
        server_values = [customer_store.scale_price_for_duration(*vector) for vector in vectors]
        self.assertEqual(client_values, server_values)


if __name__ == "__main__":
    unittest.main()
