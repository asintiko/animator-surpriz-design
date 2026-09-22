from __future__ import annotations

import unittest
from pathlib import Path

from PIL import Image


CHARACTER_DIR = Path(__file__).resolve().parents[1] / "assets" / "img" / "characters"
RESPONSIVE_WIDTHS = (480, 768, 1200)
RESPONSIVE_FORMATS = ("webp", "avif")


def alpha_extrema(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.convert("RGBA").getchannel("A").getextrema()


class CharacterImageAlphaTests(unittest.TestCase):
    def test_responsive_variants_preserve_source_transparency(self) -> None:
        sources = sorted(CHARACTER_DIR.glob("*-800.webp"))
        self.assertGreaterEqual(len(sources), 42)

        opaque_variants: list[str] = []
        for source in sources:
            source_alpha = alpha_extrema(source)
            self.assertLess(source_alpha[0], 255, f"Source has no transparency: {source.name}")

            stem = source.name.removesuffix("-800.webp")
            for width in RESPONSIVE_WIDTHS:
                for image_format in RESPONSIVE_FORMATS:
                    variant = CHARACTER_DIR / f"{stem}-{width}.{image_format}"
                    self.assertTrue(variant.is_file(), f"Missing responsive image: {variant.name}")
                    if alpha_extrema(variant)[0] == 255:
                        opaque_variants.append(variant.name)

        self.assertEqual(
            opaque_variants,
            [],
            "Responsive variants replaced transparency with an opaque background:\n"
            + "\n".join(opaque_variants),
        )


if __name__ == "__main__":
    unittest.main()
