#!/usr/bin/env python3
"""Populate group rosters and replace legacy show hero media paths."""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = PROJECT_ROOT / "content/data/admin/site_admin.sqlite3"
INCLUDED_MEMBERS = 2
PAIR_EXTRA_MEMBER_PRICE = 0
# Group members are charged through the selected show-program tariff. Keeping
# a second per-card surcharge here would double-charge the third performer.
EXTRA_MEMBER_PRICE = 0


@dataclass(frozen=True)
class EnsembleSpec:
    members: tuple[str, ...]
    included_count: int = INCLUDED_MEMBERS
    extra_member_price: int = PAIR_EXTRA_MEMBER_PRICE


GROUP_SPECS: dict[str, EnsembleSpec] = {
    "kid-e-cats": EnsembleSpec(
        ("Коржик", "Компот", "Карамелька"),
        extra_member_price=EXTRA_MEMBER_PRICE,
    ),
    "anna-elsa-olaf": EnsembleSpec(
        ("Анна", "Эльза", "Олаф (ростовой)"),
        extra_member_price=EXTRA_MEMBER_PRICE,
    ),
    "naruto": EnsembleSpec(("Наруто", "Сакура")),
    "among-us": EnsembleSpec(("Жёлтый Among Us", "Розовый Among Us")),
    "paw-patrol": EnsembleSpec(("Скай", "Гонщик")),
    "amy-sonic": EnsembleSpec(("Эми", "Соник")),
    "brawl-stars": EnsembleSpec(
        ("Шелли", "Леон", "Ворон (ростовой)"),
        extra_member_price=EXTRA_MEMBER_PRICE,
    ),
    "gingerbread": EnsembleSpec(("Печенька (мальчик)", "Печенька (девочка)")),
    "hawaiian-party": EnsembleSpec(("Гаваец", "Гавайка")),
    "hosts-mickey-minnie": EnsembleSpec(
        (
            "Микки Маус",
            "Минни Маус",
        )
    ),
    "jasmine-aladdin": EnsembleSpec(("Аладдин", "Жасмин")),
    "ladybug-cat-noir": EnsembleSpec(("Леди Баг", "Супер-Кот")),
    "masha-and-the-bear": EnsembleSpec(("Маша", "Медведь")),
    "mommy-baby-shark": EnsembleSpec(("Baby Shark", "Mommy Shark")),
    "safari": EnsembleSpec(
        (
            "Сафари (мальчик)",
            "Сафари (девочка)",
            "Динозавр (ростовой)",
        ),
        extra_member_price=EXTRA_MEMBER_PRICE,
    ),
    "sailors": EnsembleSpec(("Моряк", "Морячка")),
    "kuromi-melody": EnsembleSpec(("Куроми", "Мелоди")),
    "steampunk": EnsembleSpec(
        (
            "Золотая игрушка (мальчик)",
            "Золотая игрушка (девочка)",
        )
    ),
    "superman-supergirl": EnsembleSpec(("Супермен", "Супервумен")),
    "surpriz-clown": EnsembleSpec(
        ("Чикки", "Ляля", "Бум-Бум"), extra_member_price=EXTRA_MEMBER_PRICE
    ),
    "the-fixies": EnsembleSpec(("Симка", "Нолик")),
    "tribal-party": EnsembleSpec(("Индеец", "Индианка")),
    "labubu-quad": EnsembleSpec(
        (
            "Лабубу (ментоловый)",
            "Лабубу (розовый)",
            "Лабубу (радужный)",
            "Зимомо (ростовой)",
        ),
        extra_member_price=EXTRA_MEMBER_PRICE,
    ),
    "rumi-jinu": EnsembleSpec(("Руми", "Джину")),
    "stitch-angel": EnsembleSpec(("Стич", "Энджел")),
    "neon-jesters-pair": EnsembleSpec(("Неоновый ведущий", "Неоновая ведущая")),
    "mcqueen-assistant": EnsembleSpec(("Маквин", "Помощница")),
    "pink-blue-fairies": EnsembleSpec(("Розовая фея", "Голубая фея")),
    "youtube-tiktok": EnsembleSpec(("Ютуб", "ТикТок")),
    "harry-hermione": EnsembleSpec(("Гарри Поттер", "Гермиона")),
    "zootopia": EnsembleSpec(("Ник", "Джуди")),
}

NEPTUNE_SPEC = EnsembleSpec(
    (
        "Нептун",
        "Русалочка (розовая)",
        "Русалочка (зелёная)",
    ),
    extra_member_price=EXTRA_MEMBER_PRICE,
)
NEPTUNE_DESCRIPTION = "Подводная сказка с Нептуном и двумя русалочками."
ZOOTOPIA_DESCRIPTION = "Весёлое расследование, игры и танцы с героями Зверополиса."

SHOW_MEDIA_PATHS: dict[str, str] = {
    slug: f"/surpriz/assets/img/show-programs/cards/{slug}-1200.webp"
    for slug in (
        "balloon-show",
        "cryo-show",
        "jesters",
        "neon-jesters",
        "paper-ribbon-show",
        "ribbon-show",
        "streamer-show",
    )
}
SHOW_MEDIA_PATHS.update(
    {
        "squid-game-60": "/surpriz/assets/img/characters/squid-game-1200.webp",
        "squid-game-90": "/surpriz/assets/img/characters/squid-game-1200.webp",
    }
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes. Without this flag the command is a dry run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    database = args.database.expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"Database does not exist: {database}")

    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT slug, name, status, short_description, description,
                   base_price, included_items, ensemble_members,
                   ensemble_included_count, ensemble_extra_member_price
            FROM managed_characters
            WHERE entity_type = 'character'
            """
        ).fetchall()
        current = {str(row["slug"]): row for row in rows}
        active_slugs = {
            slug for slug, row in current.items() if str(row["status"]) == "active"
        }
        missing = sorted(set(GROUP_SPECS) - active_slugs)
        if missing:
            raise RuntimeError(f"Active character cards not found: {', '.join(missing)}")
        if "neptune-mermaids" not in current:
            raise RuntimeError("Hidden character card not found: neptune-mermaids")

        changed_slugs: set[str] = set()
        for slug in sorted(active_slugs):
            if slug == "neptune-mermaids":
                continue
            spec = GROUP_SPECS.get(slug)
            desired = (
                ", ".join(spec.members) if spec else "",
                spec.included_count if spec else INCLUDED_MEMBERS,
                spec.extra_member_price if spec else PAIR_EXTRA_MEMBER_PRICE,
            )
            row = current[slug]
            existing = (
                str(row["ensemble_members"] or ""),
                int(row["ensemble_included_count"] or 0),
                int(row["ensemble_extra_member_price"] or 0),
            )
            marker = "=" if existing == desired else "→"
            label = desired[0] or "отдельная карточка"
            print(f"{marker} {slug}: {row['name']} | {label}")
            if existing == desired:
                continue
            changed_slugs.add(slug)
            connection.execute(
                """
                UPDATE managed_characters
                SET ensemble_members = ?,
                    ensemble_included_count = ?,
                    ensemble_extra_member_price = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE slug = ? AND entity_type = 'character'
                """,
                (*desired, slug),
            )

        neptune = current["neptune-mermaids"]
        neptune_desired = (
            ", ".join(NEPTUNE_SPEC.members),
            NEPTUNE_SPEC.included_count,
            NEPTUNE_SPEC.extra_member_price,
            25_000,
            NEPTUNE_DESCRIPTION,
        )
        neptune_existing = (
            str(neptune["ensemble_members"] or ""),
            int(neptune["ensemble_included_count"] or 0),
            int(neptune["ensemble_extra_member_price"] or 0),
            int(neptune["base_price"] or 0),
            str(neptune["description"] or ""),
        )
        marker = "=" if neptune_existing == neptune_desired else "→"
        print(f"{marker} neptune-mermaids: {neptune['name']} | {neptune_desired[0]}")
        if neptune_existing != neptune_desired:
            changed_slugs.add("neptune-mermaids")
            connection.execute(
                """
                UPDATE managed_characters
                SET ensemble_members = ?, ensemble_included_count = ?,
                    ensemble_extra_member_price = ?, base_price = ?,
                    short_description = ?, description = ?, seo_description = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE slug = 'neptune-mermaids' AND entity_type = 'character'
                """,
                (
                    *neptune_desired[:4],
                    NEPTUNE_DESCRIPTION,
                    NEPTUNE_DESCRIPTION,
                    NEPTUNE_DESCRIPTION,
                ),
            )

        zootopia = current["zootopia"]
        zootopia_desired = (
            1_050_000,
            "Игрушка входит в комплект",
            ZOOTOPIA_DESCRIPTION,
        )
        zootopia_existing = (
            int(zootopia["base_price"] or 0),
            str(zootopia["included_items"] or ""),
            str(zootopia["description"] or ""),
        )
        if zootopia_existing != zootopia_desired:
            changed_slugs.add("zootopia")
            connection.execute(
                """
                UPDATE managed_characters
                SET base_price = ?, included_items = ?, short_description = ?,
                    description = ?, seo_description = ?, updated_at = CURRENT_TIMESTAMP
                WHERE slug = 'zootopia' AND entity_type = 'character' AND status = 'active'
                """,
                (
                    zootopia_desired[0],
                    zootopia_desired[1],
                    ZOOTOPIA_DESCRIPTION,
                    ZOOTOPIA_DESCRIPTION,
                    ZOOTOPIA_DESCRIPTION,
                ),
            )

        changed = len(changed_slugs)

        show_rows = connection.execute(
            """
            SELECT character.id, character.slug, character.name,
                   character.hero_media_id, media.character_id AS media_character_id,
                   media.file_path
            FROM managed_characters AS character
            LEFT JOIN managed_character_media AS media ON media.id = character.hero_media_id
            WHERE character.entity_type = 'show_program' AND character.status = 'active'
            """
        ).fetchall()
        shows = {str(row["slug"]): row for row in show_rows}
        missing_shows = sorted(set(SHOW_MEDIA_PATHS) - set(shows))
        if missing_shows:
            print(f"Skipped inactive or missing show cards: {', '.join(missing_shows)}")

        media_changed = 0
        for slug, file_path in SHOW_MEDIA_PATHS.items():
            row = shows.get(slug)
            if row is None:
                continue
            existing_path = str(row["file_path"] or "")
            marker = "=" if existing_path == file_path else "→"
            print(f"{marker} {slug}: {row['name']} | {file_path}")
            if existing_path == file_path:
                continue
            media_changed += 1
            character_id = int(row["id"])
            hero_media_id = int(row["hero_media_id"]) if row["hero_media_id"] else None
            media_character_id = (
                int(row["media_character_id"]) if row["media_character_id"] else None
            )
            if hero_media_id is not None and media_character_id == character_id:
                connection.execute(
                    """
                    UPDATE managed_character_media
                    SET file_path = ?, alt_text = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (file_path, str(row["name"]), hero_media_id),
                )
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO managed_character_media (
                        character_id, media_type, file_path, alt_text, caption,
                        sort_order, created_at, updated_at
                    ) VALUES (?, 'image', ?, ?, '', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (character_id, file_path, str(row["name"])),
                )
                connection.execute(
                    """
                    UPDATE managed_characters
                    SET hero_media_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (int(cursor.lastrowid), character_id),
                )

        if args.apply:
            connection.commit()
            print(
                f"Applied {changed} roster updates and {media_changed} media updates "
                f"to {database}"
            )
        else:
            connection.rollback()
            print(
                f"Dry run: {changed} roster updates and {media_changed} media updates "
                f"would be applied to {database}"
            )
    finally:
        connection.close()


if __name__ == "__main__":
    main()
