"""Apply reviewed cover crops to show programs.

The public show card is 16/10 on desktop and 16/11 on mobile, while almost every
cover photo is portrait. With the default 50%/50% position the widest part of the
frame lands in the middle of the photo, which cuts performers' faces off. For each
cover the reviewed vertical centre of the faces is recorded below as ``focus`` (a
share of the photo height); the object-position that puts those faces at
``FACE_TARGET`` of the visible window is derived from the card geometry.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.catalog_store import (  # noqa: E402
    get_character_by_id,
    list_characters,
    update_character,
)

DESKTOP_CARD_RATIO = 16 / 10
MOBILE_CARD_RATIO = 16 / 11
FACE_TARGET = 0.38

# slug -> (photo aspect ratio, vertical share of the faces, horizontal position, fit)
COVERS: dict[str, tuple[float, float, int, str]] = {
    "standard-program": (1200 / 1600, 0.41, 50, "cover"),
    "ribbon-show": (1200 / 1600, 0.50, 50, "cover"),
    "streamer-show": (1200 / 1600, 0.58, 50, "cover"),
    "paper-ribbon-show": (1200 / 1800, 0.35, 58, "cover"),
    "neon-start": (1200 / 1600, 0.45, 50, "cover"),
    "neon-medium": (1200 / 1600, 0.45, 50, "cover"),
    "neon-lux": (1200 / 1600, 0.45, 50, "cover"),
    "jesters": (1200 / 2134, 0.33, 50, "cover"),
    "neon-jesters": (1200 / 2134, 0.375, 50, "cover"),
    "balloon-show": (1200 / 2134, 0.48, 50, "cover"),
    "cryo-show": (1200 / 2134, 0.37, 50, "cover"),
    "atmosphere-program": (1200 / 850, 0.37, 45, "cover"),
    # Cut-outs with transparency sit on the card's own red backdrop, so they are
    # shown whole instead of being cropped into.
    "squid-game-60": (1200 / 1600, 0.50, 50, "contain"),
    "squid-game-90": (1200 / 1600, 0.50, 50, "contain"),
}


def offset_for(photo_ratio: float, focus: float, card_ratio: float) -> int:
    """Vertical object-position that puts ``focus`` at FACE_TARGET of the window."""
    visible = photo_ratio / card_ratio
    if visible >= 1:
        # The photo is wider than the card: the full height shows, nothing to aim.
        return 50
    slack = 1 - visible
    if slack < 0.1:
        # Only a sliver of travel is available; the default reads the same.
        return 50
    return max(0, min(100, round((focus - FACE_TARGET * visible) / slack * 100)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write the values to the database")
    args = parser.parse_args()

    by_slug = {
        str(row.get("slug") or ""): row
        for row in list_characters(entity_type="show_program")
    }

    missing = sorted(set(COVERS) - set(by_slug))
    if missing:
        print(f"! not in catalog: {', '.join(missing)}")

    print(f"{'slug':<22}{'fit':<9}{'desktop':<12}{'mobile':<12}")
    for slug, (photo_ratio, focus, x, fit) in COVERS.items():
        row = by_slug.get(slug)
        if not row:
            continue
        desktop_y = 50 if fit == "contain" else offset_for(photo_ratio, focus, DESKTOP_CARD_RATIO)
        mobile_y = 50 if fit == "contain" else offset_for(photo_ratio, focus, MOBILE_CARD_RATIO)
        print(f"{slug:<22}{fit:<9}{f'{x}% / {desktop_y}%':<12}{f'{x}% / {mobile_y}%':<12}")

        if not args.apply:
            continue
        entity_id = int(row["id"])
        current = get_character_by_id(entity_id)
        if not current:
            continue
        current.update(
            cover_offset_x=x,
            cover_offset_y=desktop_y,
            cover_fit=fit,
            image_zoom=100,
            mobile_cover_offset_x=x,
            mobile_cover_offset_y=mobile_y,
            mobile_cover_fit=fit,
            mobile_image_zoom=100,
        )
        update_character(entity_id, current)

    print("applied" if args.apply else "dry run — pass --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
