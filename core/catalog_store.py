from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from .config import DATA_ROOT, ROUTES_ROOT, STATIC_ROOT

DB_ROOT = DATA_ROOT / "admin"
DB_PATH = DB_ROOT / "site_admin.sqlite3"
CHARACTER_ROUTES_ROOT = ROUTES_ROOT / "character"
UPLOAD_ROOT = STATIC_ROOT / "admin-media" / "characters"
UPLOAD_URL_ROOT = "/admin-media/characters"
DEFAULT_PHONE = "+998 (99) 892-65-65"
DEFAULT_TELEGRAM_URL = "tg://resolve?phone=998998926565"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".svg"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".ogg"}
CYRILLIC_MAP = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "c",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


CATALOG_HIDDEN_LEGACY_CATEGORIES = {"shou"}
ENTITY_TYPE_CHARACTER = "character"
ENTITY_TYPE_SHOW_PROGRAM = "show_program"
VALID_ENTITY_TYPES = {ENTITY_TYPE_CHARACTER, ENTITY_TYPE_SHOW_PROGRAM}
DEFAULT_SHOW_PROGRAM_PRICE = 1_000_000
DEFAULT_SHOW_PROGRAM_DURATION_MINUTES = 60
DEFAULT_INCLUDED_CHARACTERS_COUNT = 2
DEFAULT_EXTRA_CHARACTER_PRICE = 200_000
DEFAULT_INCLUDED_MEMBERS_COUNT = 2
DEFAULT_EXTRA_MEMBER_PRICE = 0
SHOW_PROGRAM_DURATION_OVERRIDES = {
    "cryo-show": 30,
}
CATALOG_GROUP_ORDER = {
    "supergeroi": 10,
    "igrovye-geroi": 20,
    "mult-personazhi": 30,
    "klassika-disney": 35,
    "muzykalnye-geroi": 40,
    "princessy": 50,
    "fei": 55,
    "mult-poni": 58,
    "kukly": 60,
    "skazka": 70,
    "fjentezi": 75,
    "serial": 80,
    "anime": 85,
    "blogery": 90,
    "obuchajushhie": 95,
    "kvesty": 100,
    "prikljuchenija": 105,
    "morskaja-skazka": 110,
    "morskaja-tema": 115,
    "sport": 120,
    "tematicheskaja-vecherinka": 125,
    "tematika": 130,
    "kostjumy": 135,
    "klouny": 140,
    "patrioticheskaja-tema": 145,
    "new-year": 999,
}
CATALOG_FEATURED_SLUG_ORDER = {
    "ladybug-cat-noir": 1,
    "black-panther": 2,
    "deadpool": 3,
    "hulk": 4,
    "lol-dolls": 10,
    "trolls": 11,
    "blue-tractor": 12,
    "fairy-tale-fairies": 20,
    "rainbow-fairy": 21,
    "unicorns": 22,
    "barbie": 30,
    "rapunzel": 31,
    "anna-elsa-olaf": 32,
}
CURATED_CATALOG_META_KEY = "curated_character_catalog_sha256_v1"
CURATED_REQUIRED_OVERRIDES_META_KEY = "curated_required_character_overrides_v1"
CURATED_REQUIRED_OVERRIDES_VERSION = "2026-08-08-neon-hosts-v1"
CURATED_REQUIRED_OVERRIDE_SLUGS = frozenset({"neon-jesters-pair"})
SHOW_PROGRAM_TARIFFS_META_KEY = "show_program_tariffs_v1"
SHOW_PROGRAM_TARIFFS_VERSION = "2026-08-08-v6"
SHOW_PROGRAM_TARIFFS: tuple[dict[str, Any], ...] = (
    {
        "slug": "standard-program",
        "name": "Стандарт",
        "status": "active",
        "base_price": 950_000,
        "default_duration_minutes": 60,
        "included_characters_count": 2,
        "extra_character_price_3": 350_000,
        "extra_character_price_4_plus": 350_000,
        "sort_order": 10,
        "short_description": "Час активных игр с диджеем и двумя героями: музыка, мыльные пузыри и подарок — маски или шары.",
        "description": "Диджей задаёт ритм, а персонажи проводят активные игры, танцы и весёлые задания.",
        "included_items": (
            "1 диджей, 2 персонажа, генератор мыльных пузырей, "
            "маски или шары на выбор"
        ),
    },
    {
        "slug": "ribbon-show",
        "name": "Ленточное шоу",
        "status": "active",
        "base_price": 1_400_000,
        "default_duration_minutes": 60,
        "included_characters_count": 2,
        "extra_character_price_3": 350_000,
        "extra_character_price_4_plus": 350_000,
        "sort_order": 20,
        "variant_group_slug": "lenta-show",
        "variant_group_name": "Лента-шоу",
        "variant_label": "Атласное",
        "short_description": "Танцы с двумя героями и диджеем, огромный мешок атласных лент, мыльные пузыри и подарок на выбор.",
        "description": "Дети двигаются вместе с героями, участвуют во флешмобах и наполняют зал цветными лентами.",
        "included_items": (
            "1 диджей, 2 персонажа, большая сумка атласных лент, "
            "генератор мыльных пузырей, маски или шары на выбор"
        ),
        "restrictions": "Проводится только в закрытом помещении.",
    },
    {
        "slug": "paper-ribbon-show",
        "name": "Бумажное шоу",
        "status": "hidden",
        "base_price": 1_500_000,
        "default_duration_minutes": 60,
        "included_characters_count": 2,
        "extra_character_price_3": 350_000,
        "extra_character_price_4_plus": 350_000,
        "sort_order": 21,
        "variant_group_slug": "lenta-show",
        "variant_group_name": "Лента-шоу",
        "variant_label": "Бумажное",
        "short_description": "Игры и танцы с двумя героями завершаются морем бумажных лент; мыльные пузыри и подарок уже включены.",
        "description": "Игры и танцы переходят в большой бумажный финал, где дети оказываются внутри праздничного вихря.",
        "included_items": (
            "1 диджей, 2 персонажа, большая сумка бумажных лент, "
            "генератор мыльных пузырей, маски или шары на выбор"
        ),
        "restrictions": "Проводится только в закрытом помещении.",
    },
    {
        "slug": "streamer-show",
        "name": "Серпантин-шоу",
        "status": "active",
        "base_price": 1_400_000,
        "default_duration_minutes": 60,
        "included_characters_count": 2,
        "extra_character_price_3": 350_000,
        "extra_character_price_4_plus": 350_000,
        "sort_order": 22,
        "variant_group_slug": "lenta-show",
        "variant_group_name": "Лента-шоу",
        "variant_label": "Серпантин",
        "short_description": "Динамичные игры с двумя героями завершаются дождём из огромного мешка серпантина; мыльные пузыри и подарок включены.",
        "description": "Персонажи проводят игры и танцы, а кульминацией становится яркий серпантиновый дождь.",
        "included_items": (
            "1 диджей, 2 персонажа, большая сумка серпантина, "
            "генератор мыльных пузырей, маски или шары на выбор"
        ),
        "restrictions": "Проводится только в закрытом помещении.",
    },
    {
        "slug": "neon-start",
        "name": "Neon Start",
        "status": "active",
        "base_price": 1_500_000,
        "default_duration_minutes": 60,
        "included_characters_count": 2,
        "extra_character_price_3": 0,
        "extra_character_price_4_plus": 0,
        "fixed_cast": True,
        "sort_order": 30,
        "variant_group_slug": "neon-program",
        "variant_group_name": "Неоновое шоу",
        "variant_label": "Start",
        "short_description": "Светящаяся вечеринка с двумя неоновыми ведущими, лентами, прожекторами и подарком — маски или шары.",
        "description": "Два неоновых ведущих устраивают танцевальные игры под светом прожекторов и завершают шоу яркими лентами.",
        "included_items": (
            "1 диджей, 2 неоновых ведущих, полная сумка неоновых лент, "
            "2 неоновых прожектора, маски или шары на выбор"
        ),
    },
    {
        "slug": "neon-medium",
        "name": "Neon Medium",
        "status": "active",
        "base_price": 1_850_000,
        "default_duration_minutes": 60,
        "included_characters_count": 2,
        "extra_character_price_3": 0,
        "extra_character_price_4_plus": 0,
        "fixed_cast": True,
        "sort_order": 31,
        "variant_group_slug": "neon-program",
        "variant_group_name": "Неоновое шоу",
        "variant_label": "Medium",
        "short_description": "Два неоновых ведущих, четыре прожектора и светящиеся ленты; перед шоу аквагример создаёт образы детям.",
        "description": "Перед началом аквагример создаёт светящиеся образы, затем ведущие проводят игры и танцы с неоновыми лентами.",
        "included_items": (
            "1 диджей, 2 неоновых ведущих, полная сумка неоновых лент, "
            "4 неоновых прожектора, неоновый аквагрим каждому ребёнку, "
            "аквагример работает 1 час до начала шоу, маски или шары на выбор"
        ),
    },
    {
        "slug": "neon-lux",
        "name": "Neon Lux",
        "status": "active",
        "base_price": 2_100_000,
        "default_duration_minutes": 60,
        "included_characters_count": 3,
        "extra_character_price_3": 0,
        "extra_character_price_4_plus": 0,
        "fixed_cast": True,
        "sort_order": 32,
        "variant_group_slug": "neon-program",
        "variant_group_name": "Неоновое шоу",
        "variant_label": "Lux",
        "short_description": "Три неоновых ведущих, аквагрим, дымные мыльные пузыри, браслеты и мощное световое оформление.",
        "description": "Три ведущих, неоновый аквагрим, дымные пузыри и браслеты создают полноценную светящуюся вечеринку.",
        "included_items": (
            "1 диджей, 3 неоновых ведущих, полная сумка неоновых лент, "
            "4 неоновых прожектора, неоновый аквагрим каждому ребёнку, "
            "аквагример работает 1 час до начала шоу, дым-мыльная машина, "
            "неоновые браслеты каждому ребёнку, маски или шары на выбор"
        ),
    },
    {
        "slug": "squid-game-60",
        "name": "Игра в кальмара — 60 минут",
        "status": "active",
        "base_price": 1_300_000,
        "default_duration_minutes": 60,
        "included_characters_count": 3,
        "extra_character_price_3": 0,
        "extra_character_price_4_plus": 0,
        "fixed_cast": True,
        "sort_order": 40,
        "variant_group_slug": "squid-game-program",
        "variant_group_name": "Игра в кальмара",
        "variant_label": "60 минут",
        "short_description": "Час безопасных испытаний с ведущим в чёрном и двумя красными охранниками; реквизит, пузыри и подарок включены.",
        "description": "Ведущий и два охранника проводят безопасные командные испытания с реквизитом и полным погружением в сюжет.",
        "included_items": (
            "1 диджей, фиксированный состав из 3 артистов: ведущий в чёрном "
            "и 2 красных охранника, тематический реквизит, генератор мыльных "
            "пузырей, маски или шары на выбор"
        ),
    },
    {
        "slug": "squid-game-90",
        "name": "Игра в кальмара — 90 минут",
        "status": "active",
        "base_price": 1_700_000,
        "default_duration_minutes": 90,
        "included_characters_count": 3,
        "extra_character_price_3": 0,
        "extra_character_price_4_plus": 0,
        "fixed_cast": True,
        "sort_order": 41,
        "variant_group_slug": "squid-game-program",
        "variant_group_name": "Игра в кальмара",
        "variant_label": "90 минут",
        "short_description": "Полтора часа испытаний с дополнительными раундами, ведущим и двумя охранниками; реквизит, пузыри и подарок включены.",
        "description": "Больше раундов, командных заданий и сюжетных поворотов с ведущим и двумя охранниками.",
        "included_items": (
            "1 диджей, фиксированный состав из 3 артистов: ведущий в чёрном "
            "и 2 красных охранника, тематический реквизит, генератор мыльных "
            "пузырей, маски или шары на выбор"
        ),
    },
    {
        "slug": "atmosphere-program",
        "name": "Атмосфера",
        "status": "active",
        "base_price": 450_000,
        "default_duration_minutes": 60,
        "included_characters_count": 1,
        "extra_character_price_3": 450_000,
        "extra_character_price_4_plus": 450_000,
        "sort_order": 50,
        "short_description": "Любимый герой встречает гостей, общается, фотографируется и помогает задать настроение без большой шоу-программы.",
        "description": "Лёгкий формат для приветствия, фотографий, коротких игр и тёплого общения без большой шоу-программы.",
        "included_items": "1 персонаж",
    },
    {
        "slug": "greeting-program",
        "name": "Поздравлялка",
        "status": "active",
        "base_price": 400_000,
        "default_duration_minutes": 15,
        "included_characters_count": 1,
        "extra_character_price_3": 250_000,
        "extra_character_price_4_plus": 250_000,
        "sort_order": 60,
        "short_description": "15 минут личного поздравления, вручение подарка и памятные фотографии; диджея можно добавить отдельно.",
        "description": "Персонаж эффектно появляется, поздравляет ребёнка, вручает подарок и остаётся для памятных фотографий.",
        "included_items": "1 персонаж; диджей доступен как дополнительная услуга",
    },
    {
        "slug": "cryo-show",
        "name": "Крио-шоу",
        "status": "hidden",
        "base_price": 975_000,
        "default_duration_minutes": 30,
        "included_characters_count": 0,
        "extra_character_price_3": 0,
        "extra_character_price_4_plus": 0,
        "fixed_cast": True,
        "sort_order": 90,
        "short_description": "Безопасные эксперименты с холодным туманом и снежными облаками вместе с химиком, диджеем и попкорном.",
        "description": "Химик показывает безопасные крио-опыты, вовлекает детей в эксперименты и угощает попкорном.",
        "included_items": "1 диджей, 1 химик, попкорн и крио-эксперименты",
    },
    {
        "slug": "bubble-show",
        "name": "Шоу мыльных пузырей",
        "status": "hidden",
        "base_price": 975_000,
        "default_duration_minutes": 30,
        "included_characters_count": 0,
        "extra_character_price_3": 0,
        "extra_character_price_4_plus": 0,
        "fixed_cast": True,
        "sort_order": 91,
        "short_description": "Гигантские пузыри, необычные трюки и интерактивные опыты под музыку диджея.",
        "description": "Артист создаёт гигантские пузыри, показывает необычные эффекты и вовлекает детей в воздушное представление.",
        "included_items": "1 диджей, огромные пузыри и опыты с мыльными пузырями",
    },
    {
        "slug": "aqua-face-paint",
        "name": "Аквагрим",
        "status": "hidden",
        "base_price": 575_000,
        "default_duration_minutes": 60,
        "included_characters_count": 0,
        "extra_character_price_3": 0,
        "extra_character_price_4_plus": 0,
        "sort_order": 92,
        "short_description": "Аквагример создаёт 10–15 аккуратных тематических образов прямо на площадке праздника.",
        "description": "Аквагример создаёт аккуратные тематические рисунки и помогает каждому ребёнку выбрать свой образ.",
        "included_items": "1 аквагример, 10–15 рисунков",
    },
)
FIXED_CAST_SHOW_PROGRAM_SLUGS = frozenset(
    str(tariff["slug"]) for tariff in SHOW_PROGRAM_TARIFFS if tariff.get("fixed_cast")
)
FIXED_CAST_PROGRAM_DETAILS: dict[str, tuple[str, ...]] = {
    "neon-start": ("Неоновый ведущий", "Неоновая ведущая"),
    "neon-medium": ("Неоновый ведущий", "Неоновая ведущая"),
    "neon-lux": ("Неоновый ведущий", "Неоновая ведущая", "Третий неоновый ведущий"),
    "squid-game-60": ("Ведущий в чёрном костюме", "Красный охранник №1", "Красный охранник №2"),
    "squid-game-90": ("Ведущий в чёрном костюме", "Красный охранник №1", "Красный охранник №2"),
    "cryo-show": ("Химик",),
    "bubble-show": ("Артист шоу мыльных пузырей",),
}
SHOW_PROGRAM_LEGACY_SLUG_ALIASES = {
    "standard-program": "jesters",
    "neon-start": "neon-jesters",
    "atmosphere-program": "balloon-show",
}
SHOW_PROGRAM_MEDIA_CLONES = {
    "neon-start": ("neon-medium", "neon-lux"),
}
SHOW_PROGRAM_STATIC_HEROES = {
    "standard-program": "/surpriz/assets/img/show-programs/cards/standard-program-1200.webp",
    "ribbon-show": "/surpriz/assets/img/show-programs/cards/ribbon-show-1200.webp",
    "streamer-show": "/surpriz/assets/img/show-programs/cards/streamer-show-1200.webp",
    "neon-start": "/surpriz/assets/img/show-programs/cards/neon-start-1200.webp",
    "neon-medium": "/surpriz/assets/img/show-programs/cards/neon-medium-1200.webp",
    "neon-lux": "/surpriz/assets/img/show-programs/cards/neon-lux-1200.webp",
    "atmosphere-program": "/surpriz/assets/img/show-programs/cards/atmosphere-program-1200.webp",
    "squid-game-60": "/surpriz/assets/img/characters/squid-game-1200.webp",
    "squid-game-90": "/surpriz/assets/img/characters/squid-game-1200.webp",
}
SHOW_PROGRAMS_WITHOUT_MEDIA = frozenset(
    {"cryo-show", "bubble-show", "aqua-face-paint"}
)
CURATED_CATEGORY_TAXONOMY = {
    "superheroes": ("supergeroi", "Супергерои", 10),
    "princesses": ("skazochnye", "Принцессы", 20),
    "cartoons": ("multiki", "Мультгерои", 30),
}
CURATED_TAG_TAXONOMY = {
    "boys": ("malchikam", "Мальчикам", 10),
    "girls": ("devochkam", "Девочкам", 20),
}
CURATED_CHARACTER_IMAGE_PREFIXES = (
    "assets/img/characters/",
    "assets/img/catalogs/",
)


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_connection() -> sqlite3.Connection:
    DB_ROOT.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _normalize_entity_type(value: str | None) -> str:
    return value if value in VALID_ENTITY_TYPES else ENTITY_TYPE_CHARACTER


def _normalize_non_negative_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def get_default_show_program_duration_minutes(slug: str | None) -> int:
    return SHOW_PROGRAM_DURATION_OVERRIDES.get((slug or "").strip(), DEFAULT_SHOW_PROGRAM_DURATION_MINUTES)


def _ensure_character_entity_type_column() -> None:
    with _get_connection() as connection:
        if _has_column(connection, "managed_characters", "entity_type"):
            return
        connection.execute(
            "ALTER TABLE managed_characters ADD COLUMN entity_type TEXT NOT NULL DEFAULT 'character'"
        )
        connection.commit()


def _ensure_character_base_price_column() -> bool:
    with _get_connection() as connection:
        if _has_column(connection, "managed_characters", "base_price"):
            return False
        connection.execute(
            "ALTER TABLE managed_characters ADD COLUMN base_price INTEGER NOT NULL DEFAULT 0"
        )
        connection.commit()
    return True


def _ensure_character_default_duration_column() -> bool:
    with _get_connection() as connection:
        if _has_column(connection, "managed_characters", "default_duration_minutes"):
            return False
        connection.execute(
            "ALTER TABLE managed_characters ADD COLUMN default_duration_minutes INTEGER NOT NULL DEFAULT 60"
        )
        connection.commit()
    return True


def _ensure_character_search_terms_column() -> None:
    with _get_connection() as connection:
        if _has_column(connection, "managed_characters", "search_terms"):
            return
        connection.execute(
            "ALTER TABLE managed_characters ADD COLUMN search_terms TEXT NOT NULL DEFAULT ''"
        )
        connection.commit()


def _ensure_character_duplicate_count_column() -> None:
    with _get_connection() as connection:
        if _has_column(connection, "managed_characters", "duplicate_count"):
            return
        connection.execute(
            "ALTER TABLE managed_characters ADD COLUMN duplicate_count INTEGER NOT NULL DEFAULT 0"
        )
        connection.commit()


def _ensure_character_cover_offset_columns() -> None:
    with _get_connection() as connection:
        if not _has_column(connection, "managed_characters", "cover_offset_x"):
            connection.execute(
                "ALTER TABLE managed_characters ADD COLUMN cover_offset_x INTEGER NOT NULL DEFAULT 50"
            )
        if not _has_column(connection, "managed_characters", "cover_offset_y"):
            connection.execute(
                "ALTER TABLE managed_characters ADD COLUMN cover_offset_y INTEGER NOT NULL DEFAULT 50"
            )
        if not _has_column(connection, "managed_characters", "cover_fit"):
            connection.execute(
                "ALTER TABLE managed_characters ADD COLUMN cover_fit TEXT NOT NULL DEFAULT 'cover'"
            )
        if not _has_column(connection, "managed_characters", "image_zoom"):
            connection.execute(
                "ALTER TABLE managed_characters ADD COLUMN image_zoom INTEGER NOT NULL DEFAULT 100"
            )
        if not _has_column(connection, "managed_characters", "mobile_cover_offset_x"):
            connection.execute(
                "ALTER TABLE managed_characters ADD COLUMN mobile_cover_offset_x INTEGER NOT NULL DEFAULT 50"
            )
        if not _has_column(connection, "managed_characters", "mobile_cover_offset_y"):
            connection.execute(
                "ALTER TABLE managed_characters ADD COLUMN mobile_cover_offset_y INTEGER NOT NULL DEFAULT 50"
            )
        if not _has_column(connection, "managed_characters", "mobile_cover_fit"):
            connection.execute(
                "ALTER TABLE managed_characters ADD COLUMN mobile_cover_fit TEXT NOT NULL DEFAULT 'cover'"
            )
        if not _has_column(connection, "managed_characters", "mobile_image_zoom"):
            connection.execute(
                "ALTER TABLE managed_characters ADD COLUMN mobile_image_zoom INTEGER NOT NULL DEFAULT 100"
            )
        if _get_meta(connection, "mobile_cover_backfilled") != "1":
            connection.execute(
                """
                UPDATE managed_characters
                SET mobile_cover_offset_x = cover_offset_x,
                    mobile_cover_offset_y = cover_offset_y,
                    mobile_cover_fit = cover_fit,
                    mobile_image_zoom = image_zoom
                WHERE mobile_cover_offset_x = 50
                  AND mobile_cover_offset_y = 50
                  AND mobile_image_zoom = 100
                  AND mobile_cover_fit = 'cover'
                """
            )
            _set_meta(connection, "mobile_cover_backfilled", "1")
        connection.commit()


def _ensure_character_show_program_columns() -> None:
    columns = {
        "sort_order": "INTEGER DEFAULT 0",
        "age_from": "INTEGER",
        "age_to": "INTEGER",
        "show_category": "TEXT DEFAULT ''",
        "format_tags": "TEXT DEFAULT ''",
        "included_items": "TEXT DEFAULT ''",
        "suitable_for": "TEXT DEFAULT ''",
        "restrictions": "TEXT DEFAULT ''",
        "video_url": "TEXT DEFAULT ''",
        "variant_group_slug": "TEXT DEFAULT ''",
        "variant_group_name": "TEXT DEFAULT ''",
        "variant_label": "TEXT DEFAULT ''",
    }
    with _get_connection() as connection:
        changed = False
        for column, definition in columns.items():
            if _has_column(connection, "managed_characters", column):
                continue
            connection.execute(f"ALTER TABLE managed_characters ADD COLUMN {column} {definition}")
            changed = True
        if changed:
            connection.commit()


def _ensure_show_program_pricing_columns() -> bool:
    columns = {
        "included_characters_count": f"INTEGER NOT NULL DEFAULT {DEFAULT_INCLUDED_CHARACTERS_COUNT}",
        "extra_character_price_3": f"INTEGER NOT NULL DEFAULT {DEFAULT_EXTRA_CHARACTER_PRICE}",
        "extra_character_price_4_plus": f"INTEGER NOT NULL DEFAULT {DEFAULT_EXTRA_CHARACTER_PRICE}",
    }
    added = False
    with _get_connection() as connection:
        for column, definition in columns.items():
            if _has_column(connection, "managed_characters", column):
                continue
            connection.execute(f"ALTER TABLE managed_characters ADD COLUMN {column} {definition}")
            added = True
        if added:
            connection.commit()
    return added


def _ensure_character_ensemble_columns() -> None:
    columns = {
        "ensemble_members": "TEXT NOT NULL DEFAULT ''",
        "ensemble_included_count": f"INTEGER NOT NULL DEFAULT {DEFAULT_INCLUDED_MEMBERS_COUNT}",
        "ensemble_extra_member_price": f"INTEGER NOT NULL DEFAULT {DEFAULT_EXTRA_MEMBER_PRICE}",
    }
    with _get_connection() as connection:
        added = False
        for column, definition in columns.items():
            if _has_column(connection, "managed_characters", column):
                continue
            connection.execute(f"ALTER TABLE managed_characters ADD COLUMN {column} {definition}")
            added = True
        if added:
            connection.commit()


#: 3D icons the show page can draw next to an «Что входит» item; the files live in
#: static/v2/show-detail/icons/<name>.webp and the admin offers exactly this set.
SHOW_FEATURE_ICONS: tuple[str, ...] = (
    "note", "users", "sparkles", "confetti", "star", "wand", "clock", "gift",
    "mask", "box", "map-pin", "home", "calendar", "cash", "info", "party-hat",
)
SHOW_FEATURE_DEFAULT_ICON = "party-hat"
SHOW_FEATURES_LIMIT = 20
SHOW_FEATURE_TEXT_LIMIT = 160
SHOW_CAST_LIMIT = 12
SHOW_CAST_NAME_LIMIT = 80
# First match wins, so the narrow phrases go before the broad ones
# («аквагример работает 1 час до…» is a schedule note, not the service itself).
_SHOW_FEATURE_ICON_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("час до",), "clock"),
    (("аквагрим", "рисун"), "wand"),
    (("диджей",), "note"),
    (("прожектор",), "star"),
    (("лент", "серпантин"), "confetti"),
    (("пузыр", "дым"), "sparkles"),
    (("браслет", "попкорн"), "gift"),
    (("реквизит",), "box"),
    (("маски", "шары"), "mask"),
    (("ведущ", "персонаж", "артист", "химик", "охранник"), "users"),
)


def _ensure_show_program_content_columns() -> None:
    columns = {
        "program_features": "TEXT NOT NULL DEFAULT ''",
        "program_cast": "TEXT NOT NULL DEFAULT ''",
    }
    with _get_connection() as connection:
        added = False
        for column, definition in columns.items():
            if _has_column(connection, "managed_characters", column):
                continue
            connection.execute(f"ALTER TABLE managed_characters ADD COLUMN {column} {definition}")
            added = True
        if added:
            connection.commit()


def guess_show_feature_icon(text: str) -> str:
    lowered = text.casefold()
    for needles, icon in _SHOW_FEATURE_ICON_RULES:
        if any(needle in lowered for needle in needles):
            return icon
    return SHOW_FEATURE_DEFAULT_ICON


def show_features_from_text(value: Any) -> list[dict[str, str]]:
    """Turn the legacy comma/line separated «Что входит» text into icon items."""
    features: list[dict[str, str]] = []
    for chunk in re.split(r"[\n;,]+", str(value or "")):
        text = chunk.strip(" -•\t.")
        if not text:
            continue
        text = text[0].upper() + text[1:]
        features.append({"icon": guess_show_feature_icon(text), "text": text})
    return features[:SHOW_FEATURES_LIMIT]


def normalize_show_features(value: Any) -> list[dict[str, str]]:
    """Accept the admin list (or its JSON form) and keep only valid, non-empty items."""
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else []
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    features: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or "").split())
        if not text:
            continue
        if len(text) > SHOW_FEATURE_TEXT_LIMIT:
            raise ValueError(f"Пункт «Что входит» длиннее {SHOW_FEATURE_TEXT_LIMIT} символов.")
        icon = str(item.get("icon") or "").strip()
        features.append({"icon": icon if icon in SHOW_FEATURE_ICONS else guess_show_feature_icon(text), "text": text})
    if len(features) > SHOW_FEATURES_LIMIT:
        raise ValueError(f"В «Что входит» можно указать не больше {SHOW_FEATURES_LIMIT} пунктов.")
    return features


def normalize_show_cast(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value) if value.strip().startswith("[") else None
        except json.JSONDecodeError:
            parsed = None
        value = parsed if isinstance(parsed, list) else value.split("\n")
    if not isinstance(value, list):
        return []
    members: list[str] = []
    for item in value:
        name = " ".join(str(item or "").split())
        if not name:
            continue
        if len(name) > SHOW_CAST_NAME_LIMIT:
            raise ValueError(f"Имя в составе длиннее {SHOW_CAST_NAME_LIMIT} символов.")
        members.append(name)
    if len(members) > SHOW_CAST_LIMIT:
        raise ValueError(f"В составе можно указать не больше {SHOW_CAST_LIMIT} артистов.")
    return members


def _show_content_values(data: dict[str, Any], entity_type: str) -> tuple[str, str, str]:
    """Serialized features, cast and the legacy included_items text kept in sync with them."""
    included_items = str(data.get("included_items") or "").strip()
    if entity_type != ENTITY_TYPE_SHOW_PROGRAM:
        return "", "", ""
    features = normalize_show_features(data.get("program_features"))
    cast = normalize_show_cast(data.get("program_cast"))
    if features:
        # Listing cards, the API and the builder still read the plain text.
        included_items = "; ".join(item["text"] for item in features)
    return (
        json.dumps(features, ensure_ascii=False) if features else "",
        json.dumps(cast, ensure_ascii=False) if cast else "",
        included_items,
    )


def parse_ensemble_members(value: Any) -> list[str]:
    """Split the admin-entered member list ("Анна, Эльза, Олаф" or one per line)."""
    raw = str(value or "")
    parts = [_clean_text(part) for part in re.split(r"[\n,;]+", raw)]
    members: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part:
            continue
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        members.append(part)
    return members


def _normalize_ensemble_fields(data: dict[str, Any], entity_type: str) -> tuple[str, int, int]:
    """Ensembles only make sense for characters; store the roster in a canonical form."""
    if entity_type != ENTITY_TYPE_CHARACTER:
        return "", DEFAULT_INCLUDED_MEMBERS_COUNT, DEFAULT_EXTRA_MEMBER_PRICE
    members = parse_ensemble_members(data.get("ensemble_members"))
    if len(members) == 1:
        raise ValueError("Для групповой карточки нужны минимум два уникальных участника.")
    included = _normalize_non_negative_int(
        data.get("ensemble_included_count"), DEFAULT_INCLUDED_MEMBERS_COUNT
    )
    if members:
        included = max(2, min(included, len(members)))
    price = _normalize_non_negative_int(
        data.get("ensemble_extra_member_price"), DEFAULT_EXTRA_MEMBER_PRICE
    )
    return ", ".join(members), included, price


def _backfill_show_program_pricing_from_global() -> None:
    included = DEFAULT_INCLUDED_CHARACTERS_COUNT
    extra_3 = DEFAULT_EXTRA_CHARACTER_PRICE
    extra_4 = DEFAULT_EXTRA_CHARACTER_PRICE
    try:
        from .admin_store import get_party_builder_settings

        settings = get_party_builder_settings()
        included = max(0, int(settings.get("party_included_characters") or DEFAULT_INCLUDED_CHARACTERS_COUNT))
        extra_3 = max(0, int(settings.get("party_extra_character_3_price") or DEFAULT_EXTRA_CHARACTER_PRICE))
        extra_4 = max(0, int(settings.get("party_extra_character_4_plus_price") or DEFAULT_EXTRA_CHARACTER_PRICE))
    except Exception:
        pass
    with _get_connection() as connection:
        connection.execute(
            """
            UPDATE managed_characters
            SET included_characters_count = ?,
                extra_character_price_3 = ?,
                extra_character_price_4_plus = ?,
                updated_at = ?
            WHERE entity_type = ?
            """,
            (included, extra_3, extra_4, utcnow_iso(), ENTITY_TYPE_SHOW_PROGRAM),
        )
        connection.commit()


def _ensure_character_member_columns() -> None:
    """Columns for multi-member characters (e.g. Анна, Эльза и Олаф).

    `members_text` holds one member name per line; the guest picks
    `included_members_count` of them for the base price and pays
    `extra_member_price` for each additional one.
    """
    columns = {
        "members_text": "TEXT NOT NULL DEFAULT ''",
        "included_members_count": f"INTEGER NOT NULL DEFAULT {DEFAULT_INCLUDED_MEMBERS_COUNT}",
        "extra_member_price": f"INTEGER NOT NULL DEFAULT {DEFAULT_EXTRA_MEMBER_PRICE}",
    }
    with _get_connection() as connection:
        changed = False
        for column, definition in columns.items():
            if _has_column(connection, "managed_characters", column):
                continue
            connection.execute(f"ALTER TABLE managed_characters ADD COLUMN {column} {definition}")
            changed = True
        if changed:
            connection.commit()


def _ensure_category_linked_tag_column() -> None:
    with _get_connection() as connection:
        if _has_column(connection, "managed_categories", "linked_tag_id"):
            return
        connection.execute("ALTER TABLE managed_categories ADD COLUMN linked_tag_id INTEGER")
        connection.commit()


def _ensure_show_program_characters_table() -> None:
    with _get_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS show_program_characters (
                program_id INTEGER NOT NULL,
                character_id INTEGER NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(program_id, character_id),
                FOREIGN KEY(program_id) REFERENCES managed_characters(id) ON DELETE CASCADE,
                FOREIGN KEY(character_id) REFERENCES managed_characters(id) ON DELETE CASCADE
            )
            """
        )
        connection.commit()


def _sync_show_program_commerce_defaults(*, force_price_defaults: bool = False, force_duration_defaults: bool = False) -> None:
    with _get_connection() as connection:
        if force_price_defaults:
            connection.execute(
                """
                UPDATE managed_characters
                SET base_price = ?, updated_at = ?
                WHERE entity_type = ?
                """,
                (DEFAULT_SHOW_PROGRAM_PRICE, utcnow_iso(), ENTITY_TYPE_SHOW_PROGRAM),
            )
        else:
            connection.execute(
                """
                UPDATE managed_characters
                SET base_price = ?, updated_at = ?
                WHERE entity_type = ? AND COALESCE(base_price, 0) <= 0
                """,
                (DEFAULT_SHOW_PROGRAM_PRICE, utcnow_iso(), ENTITY_TYPE_SHOW_PROGRAM),
            )

        if force_duration_defaults:
            connection.execute(
                """
                UPDATE managed_characters
                SET default_duration_minutes = ?, updated_at = ?
                WHERE entity_type = ?
                """,
                (DEFAULT_SHOW_PROGRAM_DURATION_MINUTES, utcnow_iso(), ENTITY_TYPE_SHOW_PROGRAM),
            )
            for slug, duration in SHOW_PROGRAM_DURATION_OVERRIDES.items():
                connection.execute(
                    """
                    UPDATE managed_characters
                    SET default_duration_minutes = ?, updated_at = ?
                    WHERE entity_type = ? AND slug = ?
                    """,
                    (duration, utcnow_iso(), ENTITY_TYPE_SHOW_PROGRAM, slug),
                )
        else:
            connection.execute(
                """
                UPDATE managed_characters
                SET default_duration_minutes = ?, updated_at = ?
                WHERE entity_type = ? AND COALESCE(default_duration_minutes, 0) <= 0
                """,
                (DEFAULT_SHOW_PROGRAM_DURATION_MINUTES, utcnow_iso(), ENTITY_TYPE_SHOW_PROGRAM),
            )

        connection.commit()


def _detect_entity_type_from_source_path(source_path: str) -> str:
    legacy_context = get_legacy_catalog_context(source_path)
    if legacy_context["category_slug"] == "shou":
        return ENTITY_TYPE_SHOW_PROGRAM
    return ENTITY_TYPE_CHARACTER


def _sync_entity_types_from_legacy() -> None:
    with _get_connection() as connection:
        rows = connection.execute("SELECT id, source_path, entity_type FROM managed_characters").fetchall()
        updates: list[tuple[str, int]] = []
        for row in rows:
            source_path = str(row["source_path"] or "").strip()
            # Rows created by the managed catalog and tariff sync have no
            # legacy filesystem path. Their explicit entity_type is the source
            # of truth and must survive every application restart.
            if not source_path:
                continue
            target_type = _detect_entity_type_from_source_path(source_path)
            current_type = _normalize_entity_type(str(row["entity_type"] or ""))
            if current_type != target_type:
                updates.append((target_type, int(row["id"])))

        if updates:
            connection.executemany(
                "UPDATE managed_characters SET entity_type = ?, updated_at = ? WHERE id = ?",
                [(entity_type, utcnow_iso(), character_id) for entity_type, character_id in updates],
            )
            connection.commit()


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def slugify(value: str) -> str:
    normalized = value.strip().lower()
    transliterated = "".join(CYRILLIC_MAP.get(char, char) for char in normalized)
    transliterated = unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", transliterated).strip("-")
    return slug or "item"


def normalize_search_text(value: Any) -> str:
    raw_value = str(value or "").casefold()
    transliterated = "".join(CYRILLIC_MAP.get(char, char) for char in raw_value)
    ascii_value = unicodedata.normalize("NFKD", transliterated).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", ascii_value).strip()


# Reverse transliteration: latin -> cyrillic. Handles digraphs first (sh, ch, zh, yo, ya, yu, ts, sch).
_LATIN_TO_CYR_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("ch", "ч"), ("sh", "ш"),
    ("yo", "ё"), ("ya", "я"), ("yu", "ю"), ("ts", "ц"), ("kh", "х"),
    ("ye", "е"), ("ph", "ф"),
)
_LATIN_TO_CYR_SINGLE: dict[str, str] = {
    "a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "й", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
    "v": "в", "w": "в", "x": "кс", "y": "ы", "z": "з",
}


def _latin_to_cyrillic(value: str) -> str:
    text = value.casefold()
    for latin, cyr in _LATIN_TO_CYR_DIGRAPHS:
        text = text.replace(latin, cyr)
    return "".join(_LATIN_TO_CYR_SINGLE.get(ch, ch) for ch in text)


# Synonym dictionary: each entry maps a query token to a list of equivalent search tokens.
# Pre-normalized lowercased keys, values are normalized too. Bidirectional via _SYNONYM_PAIRS.
_SYNONYM_PAIRS: tuple[tuple[str, ...], ...] = (
    ("паук", "spider", "spiderman", "spaydermen", "chelovek pauk", "человек паук"),
    ("ледибаг", "ladybug", "ledibag", "miraculous", "леди баг"),
    ("эльза", "elsa", "elza", "frozen", "холодное сердце"),
    ("анна", "anna", "frozen"),
    ("золушка", "cinderella", "zolushka"),
    ("русалка", "ariel", "mermaid", "rusalochka", "русалочка"),
    ("белоснежка", "snow white", "belosnezhka"),
    ("рапунцель", "rapunzel", "rapuncel", "tangled"),
    ("человек паук", "spiderman", "spider man", "spider"),
    ("бэтмен", "batman", "betmen"),
    ("супермен", "superman", "supermen"),
    ("халк", "hulk"),
    ("капитан америка", "captain america", "kapitan amerika"),
    ("железный человек", "iron man", "ironman", "tony stark"),
    ("тор", "thor"),
    ("чёрная вдова", "black widow", "chernaya vdova"),
    ("дэдпул", "deadpool", "dedpul"),
    ("росомаха", "wolverine", "rosomaha"),
    ("джокер", "joker", "dzhoker"),
    ("харли квинн", "harley quinn", "harli kvinn"),
    ("микки маус", "mickey mouse", "miki maus"),
    ("минни маус", "minnie mouse", "mini maus"),
    ("дональд дак", "donald duck"),
    ("гуфи", "goofy"),
    ("винни пух", "winnie pooh", "winni puh"),
    ("чебурашка", "cheburashka", "cheburaska"),
    ("крокодил гена", "krokodil gena", "gena"),
    ("симба", "simba", "lion king", "король лев"),
    ("маугли", "mowgli", "mowgly"),
    ("балу", "baloo"),
    ("робин", "robin"),
    ("питер пэн", "peter pan", "piter pen"),
    ("алиса", "alice", "alisa"),
    ("чеширский кот", "cheshire cat"),
    ("шляпник", "mad hatter", "shlyapnik"),
    ("шрек", "shrek"),
    ("фиона", "fiona"),
    ("кот в сапогах", "puss in boots", "kot v sapogah"),
    ("буратино", "buratino", "pinocchio", "пиноккио"),
    ("карлсон", "karlson", "karlsson"),
    ("малыш и карлсон", "karlson"),
    ("дед мороз", "santa", "ded moroz", "santa claus", "санта", "санта клаус"),
    ("снегурочка", "snow maiden", "snegurochka"),
    ("баба яга", "baba yaga"),
    ("кощей", "koshchei", "koshey"),
    ("единорог", "unicorn", "edinorog"),
    ("дракон", "dragon", "drakon"),
    ("принцесса", "princess", "princessa"),
    ("принц", "prince"),
    ("король", "king", "korol"),
    ("королева", "queen", "koroleva"),
    ("рыцарь", "knight", "rytsar"),
    ("пират", "pirate", "pirat"),
    ("джек воробей", "jack sparrow", "dzhek vorobey"),
    ("робот", "robot"),
    ("трансформер", "transformer"),
    ("оптимус", "optimus", "optimus prime"),
    ("бамблби", "bumblebee", "bambl bi"),
    ("ниндзяго", "ninjago"),
    ("лего", "lego"),
    ("барби", "barbie", "barbi"),
    ("кукла", "doll", "kukla"),
    ("фея", "fairy", "feya"),
    ("эльф", "elf"),
    ("гном", "gnome"),
    ("ведьма", "witch", "vedma"),
    ("вампир", "vampire", "vampir"),
    ("зомби", "zombie", "zombi"),
    ("монстр", "monster"),
    ("привидение", "ghost", "prividenie"),
    ("клоун", "clown", "kloun"),
    ("аниматор", "animator"),
    ("микимаус", "mickey mouse"),
    ("свинка пеппа", "peppa pig", "peppa"),
    ("щенячий патруль", "paw patrol", "paw"),
    ("райдер", "ryder"),
    ("гончик", "chase", "гонщик"),
    ("маршал", "marshall"),
    ("крепыш", "rubble"),
    ("эверест", "everest"),
    ("скай", "skye"),
    ("зума", "zuma"),
    ("роки", "rocky"),
    ("феи дисней", "disney fairies"),
    ("моана", "moana"),
    ("мулан", "mulan"),
    ("жасмин", "jasmine", "zhasmin"),
    ("аладдин", "aladdin"),
    ("симпсоны", "simpsons", "simpson"),
    ("гарри поттер", "harry potter", "garri potter"),
    ("гермиона", "hermione", "germiona"),
    ("рон", "ron"),
    ("дамблдор", "dumbledore"),
    ("волан де морт", "voldemort"),
    ("снейп", "snape"),
    ("маша", "masha", "masha medved"),
    ("медведь", "bear", "medved"),
    ("волк", "wolf", "volk"),
    ("заяц", "rabbit", "hare", "zayats"),
    ("кролик", "rabbit", "krolik"),
    ("лиса", "fox", "lisa"),
    ("тигр", "tiger", "tigr"),
    ("лев", "lion"),
    ("слон", "elephant", "slon"),
    ("обезьяна", "monkey", "obezyana"),
    ("акула", "shark", "akula"),
    ("кит", "whale"),
    ("дельфин", "dolphin", "delfin"),
    ("динозавр", "dinosaur", "dinozavr"),
    ("крокодил", "crocodile", "krokodil"),
    ("чмо", ""),
    ("самурай", "samurai"),
    ("ниндзя", "ninja", "nindzya"),
    ("ковбой", "cowboy", "kovboy"),
    ("гангстер", "gangster"),
    ("полицейский", "police", "policeman", "politseyskiy"),
    ("пожарный", "firefighter", "pozharnyy"),
    ("доктор", "doctor", "doktor"),
    ("повар", "chef", "cook", "povar"),
    ("учитель", "teacher", "uchitel"),
    ("ученый", "scientist"),
    ("астронавт", "astronaut", "kosmonavt", "космонавт"),
    ("чудо женщина", "wonder woman", "chudo zhenshchina"),
    ("стич", "stitch"),
    ("лило", "lilo"),
    ("эльф", "elf"),
    ("халк", "hulk"),
)


def _build_synonym_index() -> dict[str, frozenset[str]]:
    index: dict[str, set[str]] = {}
    for group in _SYNONYM_PAIRS:
        norm_group: set[str] = set()
        for term in group:
            n = normalize_search_text(term)
            if n:
                norm_group.add(n)
                norm_group.add(n.replace(" ", ""))
        if not norm_group:
            continue
        for term in norm_group:
            existing = index.setdefault(term, set())
            existing.update(norm_group)
    return {k: frozenset(v) for k, v in index.items()}


_SYNONYM_INDEX: dict[str, frozenset[str]] = _build_synonym_index()


def _expand_query_variants(value: str) -> set[str]:
    """Expand a raw user query into a set of equivalent normalized variants for matching."""
    variants: set[str] = set()
    raw = str(value or "").casefold().strip()
    if not raw:
        return variants

    candidates = {raw}
    # Reverse-transliterate latin to cyrillic so e.g. "spider" expands into "спайдер" -> finds "паук" via synonyms.
    cyr_form = _latin_to_cyrillic(raw)
    if cyr_form != raw:
        candidates.add(cyr_form)

    for cand in candidates:
        normalized = normalize_search_text(cand)
        if not normalized:
            continue
        variants.add(normalized)
        compact = normalized.replace(" ", "")
        if compact:
            variants.add(compact)
        # Synonym expansion: full phrase
        for key in (normalized, compact):
            if key in _SYNONYM_INDEX:
                variants.update(_SYNONYM_INDEX[key])
        # Synonym expansion: per-token (helps multi-word with one known synonym)
        for token in normalized.split():
            if token in _SYNONYM_INDEX:
                variants.update(_SYNONYM_INDEX[token])

    return {v for v in variants if v}


def _search_tokens(value: str) -> list[str]:
    normalized = normalize_search_text(value)
    return [token for token in normalized.split() if token]


def _character_search_haystack(character: dict[str, Any]) -> tuple[str, str]:
    fields: list[Any] = [
        character.get("name", ""),
        character.get("slug", ""),
        character.get("short_description", ""),
        character.get("description", ""),
        character.get("seo_title", ""),
        character.get("seo_description", ""),
        character.get("search_terms", ""),
        " ".join(character.get("category_names", []) or []),
        " ".join(character.get("tag_names", []) or []),
        character.get("legacy_category_name", ""),
        character.get("legacy_category_slug", ""),
    ]
    raw_text = " ".join(str(field or "") for field in fields)
    normalized = normalize_search_text(raw_text)
    # Add synonym-expanded forms of every token in the haystack so the document indexes
    # both directions (e.g. doc has "spaydermen" -> we also index "пauk"/"паук" via synonyms).
    extras: set[str] = set()
    for token in normalized.split():
        if token in _SYNONYM_INDEX:
            extras.update(_SYNONYM_INDEX[token])
    enriched = normalized + " " + " ".join(sorted(extras)) if extras else normalized
    return enriched.strip(), enriched.replace(" ", "")


def _fuzzy_contains(haystack: str, needle: str, max_edit: int = 1) -> bool:
    """Allow up to `max_edit` edits when matching a needle of length >= 5 in haystack.
    For shorter needles fuzzy is too aggressive (catches false positives), so we require
    an exact substring match. Sliding window: only window sizes near len(needle)."""
    if not needle or not haystack:
        return False
    if needle in haystack:
        return True
    n = len(needle)
    if n < 5:
        return False
    h = haystack
    H = len(h)
    for size in (n - max_edit, n, n + max_edit):
        if size <= 0 or size > H:
            continue
        for i in range(H - size + 1):
            window = h[i : i + size]
            if _edit_distance_at_most(window, needle, max_edit):
                return True
    return False


def _edit_distance_at_most(a: str, b: str, k: int) -> bool:
    """Returns True iff Levenshtein(a, b) <= k. Bounded DP, early-out."""
    la, lb = len(a), len(b)
    if abs(la - lb) > k:
        return False
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        row_min = cur[0]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if cur[j] < row_min:
                row_min = cur[j]
        if row_min > k:
            return False
        prev = cur
    return prev[lb] <= k


def character_matches_search(character: dict[str, Any], query: str) -> bool:
    raw = (query or "").strip()
    if not raw:
        return True
    haystack, compact_haystack = _character_search_haystack(character)
    variants = _expand_query_variants(raw)
    # Direct substring match in either form
    for v in variants:
        if v and (v in haystack or v in compact_haystack):
            return True
    # Token-based AND match (every token of the original query found anywhere)
    tokens = _search_tokens(raw)
    if tokens and all(t in haystack or t in compact_haystack for t in tokens):
        return True
    # Fuzzy fallback: every token allows 1 typo (for tokens >=4 chars)
    if tokens and all(_fuzzy_contains(haystack, t, 1) or _fuzzy_contains(compact_haystack, t, 1) for t in tokens):
        return True
    return False


def _character_search_score(character: dict[str, Any], query: str) -> tuple[int, str]:
    normalized_query = normalize_search_text(query)
    compact_query = normalized_query.replace(" ", "")
    normalized_name = normalize_search_text(character.get("name", ""))
    normalized_slug = normalize_search_text(character.get("slug", ""))
    normalized_terms = normalize_search_text(character.get("search_terms", ""))
    haystack, compact_haystack = _character_search_haystack(character)
    variants = _expand_query_variants(query)

    if normalized_name == normalized_query or normalized_slug == normalized_query:
        score = 0
    elif compact_query and (normalized_name.replace(" ", "") == compact_query or normalized_slug.replace(" ", "") == compact_query):
        score = 1
    elif normalized_name.startswith(normalized_query):
        score = 2
    elif normalized_query in normalized_name:
        score = 3
    elif any(v in normalized_name for v in variants if v):
        score = 4
    elif normalized_query in normalized_slug or (compact_query and compact_query in normalized_slug.replace(" ", "")):
        score = 5
    elif normalized_query in normalized_terms or any(v in normalized_terms for v in variants if v):
        score = 6
    elif compact_query and compact_query in compact_haystack:
        score = 7
    elif normalized_query in haystack or any(v in haystack for v in variants if v):
        score = 8
    else:
        score = 9

    return score, normalized_name


def filter_characters_by_search(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    if not query.strip():
        return items
    return [item for item in items if character_matches_search(item, query)]


def sort_characters_for_search(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    if not query.strip():
        return items
    return sorted(items, key=lambda item: _character_search_score(item, query))


def build_character_search_index(character: dict[str, Any]) -> dict[str, str]:
    normalized, compact = _character_search_haystack(character)
    return {"normalized": normalized, "compact": compact}


def _ensure_unique_slug(connection: sqlite3.Connection, table: str, slug: str, exclude_id: int | None = None) -> str:
    base_slug = slugify(slug)
    candidate = base_slug
    suffix = 2
    while True:
        params: list[Any] = [candidate]
        query = f"SELECT id FROM {table} WHERE slug = ?"
        if exclude_id is not None:
            query += " AND id != ?"
            params.append(exclude_id)
        row = connection.execute(query, params).fetchone()
        if not row:
            return candidate
        candidate = f"{base_slug}-{suffix}"
        suffix += 1


def _next_sort_order(connection: sqlite3.Connection, table: str, *, slug_column: str = "slug", pinned_slug: str = "all") -> int:
    row = connection.execute(
        f"SELECT COALESCE(MAX(sort_order), 0) AS max_sort_order FROM {table} WHERE {slug_column} != ?",
        (pinned_slug,),
    ).fetchone()
    return int(row["max_sort_order"]) + 1


def _get_default_taxonomy_ids(connection: sqlite3.Connection) -> tuple[int, int]:
    all_category_id = int(connection.execute("SELECT id FROM managed_categories WHERE slug = 'all'").fetchone()["id"])
    all_tag_id = int(connection.execute("SELECT id FROM managed_tags WHERE slug = 'all'").fetchone()["id"])
    return all_category_id, all_tag_id


def _resolve_or_create_tag_id(
    connection: sqlite3.Connection,
    *,
    tag_id: int | None = None,
    name: str = "",
    slug: str = "",
    is_visible: bool = True,
) -> int | None:
    if tag_id:
        row = connection.execute("SELECT id FROM managed_tags WHERE id = ? LIMIT 1", (tag_id,)).fetchone()
        if row:
            return int(row["id"])

    tag_name = name.strip()
    tag_slug = slug.strip()
    if not tag_name and not tag_slug:
        return None

    lookup_slug = slugify(tag_slug or tag_name)
    existing = connection.execute("SELECT id FROM managed_tags WHERE slug = ? LIMIT 1", (lookup_slug,)).fetchone()
    if existing:
        return int(existing["id"])

    final_slug = _ensure_unique_slug(connection, "managed_tags", tag_slug or tag_name)
    next_sort_order = _next_sort_order(connection, "managed_tags")
    cursor = connection.execute(
        """
        INSERT INTO managed_tags(name, slug, description, is_visible, is_system, sort_order, created_at, updated_at)
        VALUES (?, ?, '', ?, 0, ?, ?, ?)
        """,
        (tag_name or lookup_slug, final_slug, 1 if is_visible else 0, next_sort_order, utcnow_iso(), utcnow_iso()),
    )
    return int(cursor.lastrowid)


def _resolve_category_ids_for_tags(
    connection: sqlite3.Connection,
    *,
    explicit_category_ids: list[int],
    tag_ids: list[int],
) -> list[int]:
    all_category_id, _ = _get_default_taxonomy_ids(connection)
    category_ids = {int(category_id) for category_id in explicit_category_ids if category_id}
    category_ids.add(all_category_id)
    if tag_ids:
        placeholders = ", ".join("?" for _ in tag_ids)
        linked_rows = connection.execute(
            f"""
            SELECT id
            FROM managed_categories
            WHERE linked_tag_id IN ({placeholders})
            """,
            tuple(tag_ids),
        ).fetchall()
        category_ids.update(int(row["id"]) for row in linked_rows)
    return sorted(category_ids)


def _sync_linked_category_assignments(connection: sqlite3.Connection) -> None:
    all_category_id, all_tag_id = _get_default_taxonomy_ids(connection)
    character_rows = connection.execute(
        """
        SELECT id
        FROM managed_characters
        WHERE entity_type = ?
        """,
        (ENTITY_TYPE_CHARACTER,),
    ).fetchall()
    for row in character_rows:
        character_id = int(row["id"])
        connection.execute(
            "INSERT OR IGNORE INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
            (character_id, all_category_id),
        )
        tag_rows = connection.execute(
            "SELECT tag_id FROM managed_character_tags WHERE character_id = ?",
            (character_id,),
        ).fetchall()
        tag_ids = [int(tag_row["tag_id"]) for tag_row in tag_rows] or [all_tag_id]
        explicit_rows = connection.execute(
            "SELECT category_id FROM managed_character_categories WHERE character_id = ?",
            (character_id,),
        ).fetchall()
        category_ids = _resolve_category_ids_for_tags(
            connection,
            explicit_category_ids=[int(item["category_id"]) for item in explicit_rows],
            tag_ids=tag_ids,
        )
        for category_id in category_ids:
            connection.execute(
                "INSERT OR IGNORE INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
                (character_id, category_id),
            )


def _safe_json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _extract_meta_value(head_html: str, name: str, attribute: str = "name") -> str:
    soup = BeautifulSoup(head_html, "html.parser")
    selector = f'meta[{attribute}="{name}"]'
    element = soup.select_one(selector)
    return _clean_text(element.get("content", "")) if element else ""


def _extract_title_from_head(head_html: str) -> str:
    soup = BeautifulSoup(head_html, "html.parser")
    title = soup.title.string if soup.title and soup.title.string else ""
    return _clean_text(title)


def _extract_character_seed(entry: Path) -> dict[str, Any]:
    meta = _safe_json_load(entry / "meta.json")
    content_html = (entry / "content.html").read_text(encoding="utf-8-sig")
    head_html = (entry / "head.html").read_text(encoding="utf-8-sig")
    soup = BeautifulSoup(content_html, "html.parser")

    title_element = soup.select_one("h1.product_title") or soup.select_one("h1")
    title = _clean_text(title_element.get_text(" ", strip=True)) if title_element else entry.name.replace("-", " ").title()

    short_description = ""
    short_description_container = soup.select_one(".woocommerce-product-details__short-description")
    if short_description_container:
        short_description = _clean_text(short_description_container.get_text(" ", strip=True))

    phone = DEFAULT_PHONE
    phone_button = soup.select_one('a[href^="tel:"]')
    if phone_button:
        phone = _clean_text(phone_button.get_text(" ", strip=True)) or phone

    telegram_url = DEFAULT_TELEGRAM_URL
    telegram_button = soup.select_one('a[href^="tg://"], a[href*="t.me/"]')
    if telegram_button and telegram_button.get("href"):
        telegram_url = telegram_button["href"]

    media_urls: list[tuple[str, str, str]] = []
    seen_urls: set[str] = set()

    for image_link in soup.select(".woocommerce-product-gallery__image a[href]"):
        href = image_link.get("href", "").strip()
        if not href or href in seen_urls:
            continue
        image = image_link.select_one("img")
        alt_text = _clean_text(image.get("alt", "")) if image else ""
        media_urls.append(("image", href, alt_text))
        seen_urls.add(href)

    for iframe in soup.select("iframe[src], video[src], video source[src]"):
        href = (iframe.get("src") or "").strip()
        if not href or href in seen_urls:
            continue
        media_urls.append(("video", href, title))
        seen_urls.add(href)

    if not media_urls:
        og_image = _extract_meta_value(head_html, "og:image", attribute="property")
        if og_image:
            media_urls.append(("image", og_image, title))

    seo_title = _extract_title_from_head(head_html) or title
    seo_description = _extract_meta_value(head_html, "description")

    return {
        "name": title,
        "slug": entry.name,
        "short_description": short_description,
        "description": short_description,
        "seo_title": seo_title,
        "seo_description": seo_description,
        "contact_phone": phone,
        "telegram_url": telegram_url,
        "source_path": str(entry.relative_to(ROUTES_ROOT)).replace("\\", "/"),
        "media": media_urls,
    }


@lru_cache(maxsize=512)
def get_legacy_catalog_context(source_path: str) -> dict[str, str]:
    if not source_path:
        return {"category_slug": "", "category_name": ""}

    bundle_root = ROUTES_ROOT / Path(source_path)
    content_path = bundle_root / "content.html"
    if not content_path.exists():
        return {"category_slug": "", "category_name": ""}

    soup = BeautifulSoup(content_path.read_text(encoding="utf-8-sig"), "html.parser")
    crumb_links = soup.select(".woocommerce-breadcrumb a[href]")
    if len(crumb_links) < 2:
        return {"category_slug": "", "category_name": ""}

    category_href = crumb_links[1].get("href", "").strip("/")
    category_slug = ""
    if category_href.startswith("character-category/"):
        category_slug = category_href.split("/", 1)[1]

    return {
        "category_slug": category_slug,
        "category_name": _clean_text(crumb_links[1].get_text(" ", strip=True)),
    }


def _character_public_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    if item.get("entity_type") == ENTITY_TYPE_SHOW_PROGRAM:
        return (0, _normalize_non_negative_int(item.get("sort_order"), 0), item["name"].casefold())
    curated_order = _normalize_non_negative_int(item.get("sort_order"), 0)
    if curated_order > 0:
        return (0, curated_order, item["name"].casefold())
    legacy_context = get_legacy_catalog_context(item.get("source_path", ""))
    category_slug = legacy_context["category_slug"]
    group_order = CATALOG_GROUP_ORDER.get(category_slug, 500)
    featured_order = CATALOG_FEATURED_SLUG_ORDER.get(item["slug"], 999)
    return (group_order, featured_order, item["name"].casefold())


def init_catalog_store() -> None:
    with _get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS managed_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS managed_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                is_visible INTEGER NOT NULL DEFAULT 1,
                is_system INTEGER NOT NULL DEFAULT 0,
                linked_tag_id INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(linked_tag_id) REFERENCES managed_tags(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS managed_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                is_visible INTEGER NOT NULL DEFAULT 1,
                is_system INTEGER NOT NULL DEFAULT 0,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS managed_characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                short_description TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                seo_title TEXT NOT NULL DEFAULT '',
                seo_description TEXT NOT NULL DEFAULT '',
                search_terms TEXT NOT NULL DEFAULT '',
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                contact_phone TEXT NOT NULL DEFAULT '',
                telegram_url TEXT NOT NULL DEFAULT '',
                base_price INTEGER NOT NULL DEFAULT 0,
                default_duration_minutes INTEGER NOT NULL DEFAULT 60,
                included_characters_count INTEGER NOT NULL DEFAULT 2,
                extra_character_price_3 INTEGER NOT NULL DEFAULT 200000,
                extra_character_price_4_plus INTEGER NOT NULL DEFAULT 200000,
                sort_order INTEGER DEFAULT 0,
                age_from INTEGER,
                age_to INTEGER,
                show_category TEXT DEFAULT '',
                format_tags TEXT DEFAULT '',
                included_items TEXT DEFAULT '',
                suitable_for TEXT DEFAULT '',
                restrictions TEXT DEFAULT '',
                video_url TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                entity_type TEXT NOT NULL DEFAULT 'character',
                hero_media_id INTEGER,
                source_path TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS managed_character_media (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                character_id INTEGER NOT NULL,
                media_type TEXT NOT NULL,
                file_path TEXT NOT NULL,
                alt_text TEXT NOT NULL DEFAULT '',
                caption TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(character_id) REFERENCES managed_characters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS managed_character_categories (
                character_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                PRIMARY KEY(character_id, category_id),
                FOREIGN KEY(character_id) REFERENCES managed_characters(id) ON DELETE CASCADE,
                FOREIGN KEY(category_id) REFERENCES managed_categories(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS managed_character_tags (
                character_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY(character_id, tag_id),
                FOREIGN KEY(character_id) REFERENCES managed_characters(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES managed_tags(id) ON DELETE CASCADE
            );
            """
        )
        connection.commit()

    _ensure_character_entity_type_column()
    base_price_added = _ensure_character_base_price_column()
    duration_added = _ensure_character_default_duration_column()
    _ensure_character_search_terms_column()
    _ensure_character_duplicate_count_column()
    _ensure_character_show_program_columns()
    pricing_columns_added = _ensure_show_program_pricing_columns()
    _ensure_character_cover_offset_columns()
    _ensure_character_ensemble_columns()
    _ensure_show_program_content_columns()
    _ensure_category_linked_tag_column()
    _ensure_show_program_characters_table()
    _sync_entity_types_from_legacy()
    _sync_show_program_commerce_defaults(
        force_price_defaults=base_price_added,
        force_duration_defaults=duration_added,
    )
    if pricing_columns_added:
        _backfill_show_program_pricing_from_global()
    _ensure_default_taxonomy()
    _seed_characters_from_legacy_if_needed()
    sync_show_program_tariffs()
    _run_catalog_bootstrap()


def _ensure_default_taxonomy() -> None:
    now = utcnow_iso()
    with _get_connection() as connection:
        if connection.execute("SELECT COUNT(*) FROM managed_categories").fetchone()[0] == 0:
            connection.execute(
                """
                INSERT INTO managed_categories(name, slug, description, is_visible, is_system, linked_tag_id, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, 1, 1, NULL, 0, ?, ?)
                """,
                ("Все", "all", "Общая категория каталога.", now, now),
            )

        if connection.execute("SELECT COUNT(*) FROM managed_tags").fetchone()[0] == 0:
            connection.execute(
                """
                INSERT INTO managed_tags(name, slug, description, is_visible, is_system, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, 1, 1, 0, ?, ?)
                """,
                ("All", "all", "Общий тег каталога.", now, now),
            )
        all_tag = connection.execute("SELECT id FROM managed_tags WHERE slug = 'all' LIMIT 1").fetchone()
        if all_tag:
            connection.execute(
                """
                UPDATE managed_categories
                SET linked_tag_id = ?, updated_at = ?
                WHERE slug = 'all' AND (linked_tag_id IS NULL OR linked_tag_id != ?)
                """,
                (int(all_tag["id"]), now, int(all_tag["id"])),
            )
        connection.commit()


def _assign_default_taxonomy(connection: sqlite3.Connection, character_id: int) -> None:
    all_category_id = connection.execute("SELECT id FROM managed_categories WHERE slug = 'all'").fetchone()["id"]
    all_tag_id = connection.execute("SELECT id FROM managed_tags WHERE slug = 'all'").fetchone()["id"]
    connection.execute(
        "INSERT OR IGNORE INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
        (character_id, all_category_id),
    )
    connection.execute(
        "INSERT OR IGNORE INTO managed_character_tags(character_id, tag_id) VALUES (?, ?)",
        (character_id, all_tag_id),
    )


def _get_meta(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM managed_meta WHERE key = ? LIMIT 1", (key,)).fetchone()
    return str(row["value"]) if row else None


def _set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO managed_meta(key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (key, value, utcnow_iso()),
    )


def _copy_show_media_if_empty(
    connection: sqlite3.Connection,
    *,
    source_id: int,
    target_id: int,
    now: str,
) -> None:
    if source_id == target_id:
        return
    target_media = connection.execute(
        "SELECT 1 FROM managed_character_media WHERE character_id = ? LIMIT 1",
        (target_id,),
    ).fetchone()
    if target_media:
        return

    source = connection.execute(
        "SELECT hero_media_id FROM managed_characters WHERE id = ? LIMIT 1",
        (source_id,),
    ).fetchone()
    source_media = connection.execute(
        """
        SELECT id, media_type, file_path, alt_text, caption, sort_order
        FROM managed_character_media
        WHERE character_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (source_id,),
    ).fetchall()
    target_hero_id: int | None = None
    for media in source_media:
        cursor = connection.execute(
            """
            INSERT INTO managed_character_media(
                character_id, media_type, file_path, alt_text, caption,
                sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_id,
                media["media_type"],
                media["file_path"],
                media["alt_text"],
                media["caption"],
                int(media["sort_order"] or 0),
                now,
                now,
            ),
        )
        if source and int(media["id"]) == int(source["hero_media_id"] or 0):
            target_hero_id = int(cursor.lastrowid)
        elif target_hero_id is None and str(media["media_type"]) == "image":
            target_hero_id = int(cursor.lastrowid)

    if target_hero_id is not None:
        connection.execute(
            "UPDATE managed_characters SET hero_media_id = ?, updated_at = ? WHERE id = ?",
            (target_hero_id, now, target_id),
        )


def _set_static_show_hero(
    connection: sqlite3.Connection,
    *,
    character_id: int,
    file_path: str,
    alt_text: str,
    now: str,
) -> None:
    current = connection.execute(
        """
        SELECT media.id
        FROM managed_characters AS character
        LEFT JOIN managed_character_media AS media
          ON media.id = character.hero_media_id
         AND media.character_id = character.id
        WHERE character.id = ?
        LIMIT 1
        """,
        (character_id,),
    ).fetchone()
    if current and current["id"]:
        connection.execute(
            """
            UPDATE managed_character_media
            SET media_type = 'image', file_path = ?, alt_text = ?, updated_at = ?
            WHERE id = ?
            """,
            (file_path, alt_text, now, int(current["id"])),
        )
        return
    cursor = connection.execute(
        """
        INSERT INTO managed_character_media(
            character_id, media_type, file_path, alt_text, caption,
            sort_order, created_at, updated_at
        )
        VALUES (?, 'image', ?, ?, '', 1, ?, ?)
        """,
        (character_id, file_path, alt_text, now, now),
    )
    connection.execute(
        "UPDATE managed_characters SET hero_media_id = ?, updated_at = ? WHERE id = ?",
        (int(cursor.lastrowid), now, character_id),
    )


def sync_show_program_tariffs() -> dict[str, Any]:
    """Apply the approved show tariff baseline once, preserving IDs and media."""
    now = utcnow_iso()
    tariffs_by_slug = {str(tariff["slug"]): tariff for tariff in SHOW_PROGRAM_TARIFFS}
    inserted = 0
    updated = 0
    with _get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if _get_meta(connection, SHOW_PROGRAM_TARIFFS_META_KEY) == SHOW_PROGRAM_TARIFFS_VERSION:
            connection.rollback()
            return {
                "changed": False,
                "reason": "already_synced",
                "count": len(SHOW_PROGRAM_TARIFFS),
                "inserted": 0,
                "updated": 0,
            }

        for canonical_slug, legacy_slug in SHOW_PROGRAM_LEGACY_SLUG_ALIASES.items():
            canonical = connection.execute(
                "SELECT id FROM managed_characters WHERE slug = ? LIMIT 1",
                (canonical_slug,),
            ).fetchone()
            legacy = connection.execute(
                "SELECT id FROM managed_characters WHERE slug = ? LIMIT 1",
                (legacy_slug,),
            ).fetchone()
            if legacy and not canonical:
                connection.execute(
                    "UPDATE managed_characters SET slug = ?, updated_at = ? WHERE id = ?",
                    (canonical_slug, now, int(legacy["id"])),
                )
            elif legacy:
                connection.execute(
                    "UPDATE managed_characters SET status = 'hidden', updated_at = ? WHERE id = ?",
                    (now, int(legacy["id"])),
                )

        program_ids: dict[str, int] = {}
        for tariff in SHOW_PROGRAM_TARIFFS:
            slug = str(tariff["slug"])
            existing = connection.execute(
                "SELECT id FROM managed_characters WHERE slug = ? LIMIT 1",
                (slug,),
            ).fetchone()
            values = (
                str(tariff["name"]),
                str(tariff.get("short_description") or ""),
                str(tariff.get("description") or tariff.get("short_description") or ""),
                int(tariff["base_price"]),
                int(tariff["default_duration_minutes"]),
                int(tariff["included_characters_count"]),
                int(tariff["extra_character_price_3"]),
                int(tariff["extra_character_price_4_plus"]),
                int(tariff["sort_order"]),
                str(tariff.get("included_items") or ""),
                str(tariff.get("restrictions") or ""),
                str(tariff.get("variant_group_slug") or ""),
                str(tariff.get("variant_group_name") or ""),
                str(tariff.get("variant_label") or ""),
                str(tariff["status"]),
                now,
            )
            if existing:
                connection.execute(
                    """
                    UPDATE managed_characters
                    SET name = ?,
                        short_description = ?,
                        description = ?,
                        base_price = ?,
                        default_duration_minutes = ?,
                        included_characters_count = ?,
                        extra_character_price_3 = ?,
                        extra_character_price_4_plus = ?,
                        sort_order = ?,
                        included_items = ?,
                        restrictions = ?,
                        variant_group_slug = ?,
                        variant_group_name = ?,
                        variant_label = ?,
                        status = ?,
                        entity_type = 'show_program',
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, int(existing["id"])),
                )
                character_id = int(existing["id"])
                updated += 1
            else:
                short_description = str(tariff.get("short_description") or "")
                description = str(tariff.get("description") or short_description)
                cursor = connection.execute(
                    """
                    INSERT INTO managed_characters(
                        name, slug, short_description, description, search_terms,
                        contact_phone, telegram_url, base_price, default_duration_minutes,
                        included_characters_count, extra_character_price_3,
                        extra_character_price_4_plus, sort_order, included_items,
                        restrictions, variant_group_slug, variant_group_name, variant_label,
                        status, entity_type, source_path, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            'show_program', '', ?, ?)
                    """,
                    (
                        str(tariff["name"]),
                        slug,
                        short_description,
                        description,
                        f"{tariff['name']} {tariff.get('variant_label') or ''}".strip(),
                        DEFAULT_PHONE,
                        DEFAULT_TELEGRAM_URL,
                        int(tariff["base_price"]),
                        int(tariff["default_duration_minutes"]),
                        int(tariff["included_characters_count"]),
                        int(tariff["extra_character_price_3"]),
                        int(tariff["extra_character_price_4_plus"]),
                        int(tariff["sort_order"]),
                        str(tariff.get("included_items") or ""),
                        str(tariff.get("restrictions") or ""),
                        str(tariff.get("variant_group_slug") or ""),
                        str(tariff.get("variant_group_name") or ""),
                        str(tariff.get("variant_label") or ""),
                        str(tariff["status"]),
                        now,
                        now,
                    ),
                )
                character_id = int(cursor.lastrowid)
                inserted += 1

            program_ids[slug] = character_id
            _assign_default_taxonomy(connection, character_id)

        for slug in SHOW_PROGRAMS_WITHOUT_MEDIA:
            character_id = program_ids[slug]
            connection.execute(
                "UPDATE managed_characters SET hero_media_id = NULL, updated_at = ? WHERE id = ?",
                (now, character_id),
            )
            connection.execute(
                "DELETE FROM managed_character_media WHERE character_id = ?",
                (character_id,),
            )

        for canonical_slug, legacy_slug in SHOW_PROGRAM_LEGACY_SLUG_ALIASES.items():
            legacy = connection.execute(
                "SELECT id FROM managed_characters WHERE slug = ? LIMIT 1",
                (legacy_slug,),
            ).fetchone()
            if legacy:
                _copy_show_media_if_empty(
                    connection,
                    source_id=int(legacy["id"]),
                    target_id=program_ids[canonical_slug],
                    now=now,
                )

        for source_slug, target_slugs in SHOW_PROGRAM_MEDIA_CLONES.items():
            for target_slug in target_slugs:
                _copy_show_media_if_empty(
                    connection,
                    source_id=program_ids[source_slug],
                    target_id=program_ids[target_slug],
                    now=now,
                )

        for slug, file_path in SHOW_PROGRAM_STATIC_HEROES.items():
            _set_static_show_hero(
                connection,
                character_id=program_ids[slug],
                file_path=file_path,
                alt_text=str(tariffs_by_slug[slug]["name"]),
                now=now,
            )

        _set_meta(connection, SHOW_PROGRAM_TARIFFS_META_KEY, SHOW_PROGRAM_TARIFFS_VERSION)
        connection.commit()

    return {
        "changed": True,
        "count": len(SHOW_PROGRAM_TARIFFS),
        "inserted": inserted,
        "updated": updated,
    }


def _curated_character_slug(item: dict[str, Any]) -> str:
    href = str(item.get("href") or "")
    match = re.search(r"[?&]character=([a-z0-9-]+)", href, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    item_id = str(item.get("id") or "").strip().lower()
    return item_id.removeprefix("character-")


def _prepare_curated_character_catalog(
    catalog_path: Path,
) -> tuple[bytes, list[dict[str, Any]], set[str]]:
    """Parse and validate the landing manifest before it can change the catalog."""
    manifest_path = Path(catalog_path).expanduser().resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Curated catalog manifest is missing: {manifest_path}")

    raw = manifest_path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    raw_characters = payload.get("characters") if isinstance(payload, dict) else None
    if not isinstance(raw_characters, list):
        raise ValueError("Curated catalog must contain a characters list")

    landing_root = manifest_path.parent.parent
    prepared: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for position, raw_item in enumerate(raw_characters, start=1):
        if not isinstance(raw_item, dict) or raw_item.get("active") is False:
            continue
        slug = _curated_character_slug(raw_item)
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError(f"Invalid curated character slug: {slug!r}")
        if slug in seen_slugs:
            raise ValueError(f"Duplicate curated character slug: {slug}")

        title = str(raw_item.get("title") or "").strip()
        image = str(raw_item.get("image") or "").strip().lstrip("/")
        image_parts = Path(image).parts
        if (
            not title
            or not image.startswith(CURATED_CHARACTER_IMAGE_PREFIXES)
            or ".." in image_parts
        ):
            raise ValueError(f"Invalid curated character record: {slug}")
        if not (landing_root / image).is_file():
            raise ValueError(f"Curated character image is missing: {image}")

        categories = [
            str(value).strip().lower()
            for value in (raw_item.get("categories") or [])
            if str(value).strip().lower() in CURATED_CATEGORY_TAXONOMY | CURATED_TAG_TAXONOMY
        ]
        image_position = raw_item.get("image_position") or {}
        try:
            offset_x = max(0, min(100, int(image_position.get("x", 50))))
        except (TypeError, ValueError):
            offset_x = 50
        try:
            offset_y = max(0, min(100, int(image_position.get("y", 50))))
        except (TypeError, ValueError):
            offset_y = 50
        ensemble_members = [
            str(value).strip()
            for value in (raw_item.get("ensemble_members") or [])
            if str(value).strip()
        ]
        try:
            ensemble_included_count = max(
                0,
                min(len(ensemble_members), int(raw_item.get("ensemble_included_count") or 0)),
            )
        except (TypeError, ValueError):
            ensemble_included_count = 0
        try:
            ensemble_extra_member_price = max(
                0, int(raw_item.get("ensemble_extra_member_price") or 0)
            )
        except (TypeError, ValueError):
            ensemble_extra_member_price = 0

        prepared.append(
            {
                "slug": slug,
                "name": title,
                "description": str(raw_item.get("description") or "").strip(),
                "search_terms": " ".join(
                    part for part in (title, str(raw_item.get("alt") or "").strip()) if part
                ),
                "image_path": f"/surpriz/{image}",
                "categories": list(dict.fromkeys(categories)),
                "sort_order": position,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "ensemble_members": ensemble_members,
                "ensemble_included_count": ensemble_included_count,
                "ensemble_extra_member_price": ensemble_extra_member_price,
            }
        )
        seen_slugs.add(slug)

    if len(prepared) < 8:
        raise ValueError("Curated catalog is unexpectedly small")
    return raw, prepared, seen_slugs


def validate_curated_character_catalog(catalog_path: Path) -> dict[str, Any]:
    """Validate a candidate manifest without mutating the catalog database."""
    _, prepared, _ = _prepare_curated_character_catalog(catalog_path)
    return {"valid": True, "count": len(prepared)}


def _ensure_curated_taxonomy(
    connection: sqlite3.Connection,
    *,
    table: str,
    slug: str,
    name: str,
    sort_order: int,
    now: str,
) -> int:
    row = connection.execute(f"SELECT id FROM {table} WHERE slug = ? LIMIT 1", (slug,)).fetchone()
    if row:
        # Once imported, taxonomy is managed from the admin panel. A manifest
        # refresh must not undo renamed, hidden or reordered filters.
        return int(row["id"])

    if table == "managed_categories":
        cursor = connection.execute(
            """
            INSERT INTO managed_categories(
                name, slug, description, is_visible, is_system, linked_tag_id,
                sort_order, created_at, updated_at
            )
            VALUES (?, ?, '', 1, 0, NULL, ?, ?, ?)
            """,
            (name, slug, sort_order, now, now),
        )
    else:
        cursor = connection.execute(
            """
            INSERT INTO managed_tags(
                name, slug, description, is_visible, is_system,
                sort_order, created_at, updated_at
            )
            VALUES (?, ?, '', 1, 0, ?, ?, ?)
            """,
            (name, slug, sort_order, now, now),
        )
    return int(cursor.lastrowid)


def sync_curated_character_catalog(catalog_path: Path) -> dict[str, Any]:
    """Seed the approved landing character set into the canonical catalog.

    The manifest owns only initial values. Existing characters, taxonomy and
    media are controlled by the admin panel and are never reset by a later
    manifest digest. New manifest categories are added to existing characters
    without removing administrator assignments.
    """
    manifest_path = Path(catalog_path).expanduser().resolve()
    if not manifest_path.is_file():
        return {"changed": False, "reason": "manifest_missing", "count": 0}
    raw, prepared, seen_slugs = _prepare_curated_character_catalog(manifest_path)

    digest = hashlib.sha256(raw).hexdigest()
    now = utcnow_iso()
    with _get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        overrides_required = (
            _get_meta(connection, CURATED_REQUIRED_OVERRIDES_META_KEY)
            != CURATED_REQUIRED_OVERRIDES_VERSION
        )
        if _get_meta(connection, CURATED_CATALOG_META_KEY) == digest and not overrides_required:
            connection.commit()
            return {"changed": False, "reason": "already_synced", "count": len(prepared)}

        all_category = connection.execute(
            "SELECT id FROM managed_categories WHERE slug = 'all' LIMIT 1"
        ).fetchone()
        all_tag = connection.execute(
            "SELECT id FROM managed_tags WHERE slug = 'all' LIMIT 1"
        ).fetchone()
        if not all_category or not all_tag:
            raise RuntimeError("Default catalog taxonomy is missing")
        all_category_id = int(all_category["id"])
        all_tag_id = int(all_tag["id"])

        category_ids = {
            key: _ensure_curated_taxonomy(
                connection,
                table="managed_categories",
                slug=slug,
                name=name,
                sort_order=sort_order,
                now=now,
            )
            for key, (slug, name, sort_order) in CURATED_CATEGORY_TAXONOMY.items()
        }
        tag_ids = {
            key: _ensure_curated_taxonomy(
                connection,
                table="managed_tags",
                slug=slug,
                name=name,
                sort_order=sort_order,
                now=now,
            )
            for key, (slug, name, sort_order) in CURATED_TAG_TAXONOMY.items()
        }

        inserted = 0
        updated = 0
        for item in prepared:
            row = connection.execute(
                "SELECT id, hero_media_id FROM managed_characters WHERE slug = ? LIMIT 1",
                (item["slug"],),
            ).fetchone()
            if row:
                character_id = int(row["id"])
                if overrides_required and item["slug"] in CURATED_REQUIRED_OVERRIDE_SLUGS:
                    connection.execute(
                        """
                        UPDATE managed_characters
                        SET name = ?, short_description = ?, description = ?, seo_title = ?,
                            seo_description = ?, search_terms = ?, ensemble_members = ?,
                            ensemble_included_count = ?, ensemble_extra_member_price = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            item["name"],
                            item["description"],
                            item["description"],
                            item["name"],
                            item["description"],
                            item["search_terms"],
                            ", ".join(item["ensemble_members"]),
                            item["ensemble_included_count"],
                            item["ensemble_extra_member_price"],
                            now,
                            character_id,
                        ),
                    )
                    updated += 1
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO managed_characters(
                        name, slug, short_description, description, seo_title, seo_description,
                        search_terms, contact_phone, telegram_url, sort_order, status, entity_type,
                        source_path, cover_offset_x, cover_offset_y, cover_fit, ensemble_members,
                        ensemble_included_count, ensemble_extra_member_price, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 'character', '', ?, ?, 'contain', ?, ?, ?, ?, ?)
                    """,
                    (
                        item["name"],
                        item["slug"],
                        item["description"],
                        item["description"],
                        item["name"],
                        item["description"],
                        item["search_terms"],
                        DEFAULT_PHONE,
                        DEFAULT_TELEGRAM_URL,
                        item["sort_order"],
                        item["offset_x"],
                        item["offset_y"],
                        ", ".join(item["ensemble_members"]),
                        item["ensemble_included_count"],
                        item["ensemble_extra_member_price"],
                        now,
                        now,
                    ),
                )
                character_id = int(cursor.lastrowid)
                row = None
                inserted += 1

            hero_media_id = int(row["hero_media_id"]) if row and row["hero_media_id"] else None
            media_updated = 0
            if row is None and hero_media_id is not None:
                cursor = connection.execute(
                    """
                    UPDATE managed_character_media
                    SET media_type = 'image', file_path = ?, alt_text = ?, caption = '',
                        sort_order = 0, updated_at = ?
                    WHERE id = ? AND character_id = ?
                    """,
                    (item["image_path"], item["name"], now, hero_media_id, character_id),
                )
                media_updated = int(cursor.rowcount or 0)
            if hero_media_id is None or (row is None and not media_updated):
                media_cursor = connection.execute(
                    """
                    INSERT INTO managed_character_media(
                        character_id, media_type, file_path, alt_text, caption,
                        sort_order, created_at, updated_at
                    )
                    VALUES (?, 'image', ?, ?, '', 0, ?, ?)
                    """,
                    (character_id, item["image_path"], item["name"], now, now),
                )
                hero_media_id = int(media_cursor.lastrowid)
                connection.execute(
                    "UPDATE managed_characters SET hero_media_id = ? WHERE id = ?",
                    (hero_media_id, character_id),
                )
            elif overrides_required and item["slug"] in CURATED_REQUIRED_OVERRIDE_SLUGS:
                connection.execute(
                    """
                    UPDATE managed_character_media
                    SET file_path = ?, alt_text = ?, updated_at = ?
                    WHERE id = ? AND character_id = ?
                    """,
                    (item["image_path"], item["name"], now, hero_media_id, character_id),
                )

            connection.execute(
                "INSERT OR IGNORE INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
                (character_id, all_category_id),
            )
            connection.execute(
                "INSERT OR IGNORE INTO managed_character_tags(character_id, tag_id) VALUES (?, ?)",
                (character_id, all_tag_id),
            )
            if row is None:
                for category in item["categories"]:
                    if category in category_ids:
                        connection.execute(
                            "INSERT OR IGNORE INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
                            (character_id, category_ids[category]),
                        )
                    if category in tag_ids:
                        connection.execute(
                            "INSERT OR IGNORE INTO managed_character_tags(character_id, tag_id) VALUES (?, ?)",
                            (character_id, tag_ids[category]),
                        )

        _set_meta(connection, CURATED_CATALOG_META_KEY, digest)
        _set_meta(
            connection,
            CURATED_REQUIRED_OVERRIDES_META_KEY,
            CURATED_REQUIRED_OVERRIDES_VERSION,
        )
        connection.commit()

    get_legacy_catalog_context.cache_clear()
    return {
        "changed": True,
        "count": len(prepared),
        "inserted": inserted,
        "updated": updated,
        "hidden": 0,
    }


def collapse_taxonomy_to_all() -> None:
    now = utcnow_iso()
    with _get_connection() as connection:
        all_category = connection.execute(
            "SELECT id FROM managed_categories WHERE slug = 'all' LIMIT 1"
        ).fetchone()
        if not all_category:
            category_cursor = connection.execute(
                """
                INSERT INTO managed_categories(name, slug, description, is_visible, is_system, sort_order, created_at, updated_at)
                VALUES (?, 'all', ?, 1, 1, 0, ?, ?)
                """,
                ("Все", "Общая категория каталога.", now, now),
            )
            all_category_id = int(category_cursor.lastrowid)
        else:
            all_category_id = int(all_category["id"])
            connection.execute(
                """
                UPDATE managed_categories
                SET name = ?, slug = 'all', description = ?, is_visible = 1, is_system = 1, sort_order = 0, updated_at = ?
                WHERE id = ?
                """,
                ("Все", "Общая категория каталога.", now, all_category_id),
            )

        all_tag = connection.execute(
            "SELECT id FROM managed_tags WHERE slug = 'all' LIMIT 1"
        ).fetchone()
        if not all_tag:
            tag_cursor = connection.execute(
                """
                INSERT INTO managed_tags(name, slug, description, is_visible, is_system, sort_order, created_at, updated_at)
                VALUES (?, 'all', ?, 1, 1, 0, ?, ?)
                """,
                ("all", "Общий тег каталога.", now, now),
            )
            all_tag_id = int(tag_cursor.lastrowid)
        else:
            all_tag_id = int(all_tag["id"])
            connection.execute(
                """
                UPDATE managed_tags
                SET name = ?, slug = 'all', description = ?, is_visible = 1, is_system = 1, sort_order = 0, updated_at = ?
                WHERE id = ?
                """,
                ("all", "Общий тег каталога.", now, all_tag_id),
            )

        connection.execute(
            "DELETE FROM managed_character_categories WHERE category_id != ?",
            (all_category_id,),
        )
        connection.execute(
            "DELETE FROM managed_character_tags WHERE tag_id != ?",
            (all_tag_id,),
        )
        connection.execute(
            "DELETE FROM managed_categories WHERE id != ?",
            (all_category_id,),
        )
        connection.execute(
            "DELETE FROM managed_tags WHERE id != ?",
            (all_tag_id,),
        )

        character_rows = connection.execute("SELECT id FROM managed_characters").fetchall()
        for character_row in character_rows:
            character_id = int(character_row["id"])
            connection.execute(
                "DELETE FROM managed_character_categories WHERE character_id = ?",
                (character_id,),
            )
            connection.execute(
                "DELETE FROM managed_character_tags WHERE character_id = ?",
                (character_id,),
            )
            connection.execute(
                "INSERT OR IGNORE INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
                (character_id, all_category_id),
            )
            connection.execute(
                "INSERT OR IGNORE INTO managed_character_tags(character_id, tag_id) VALUES (?, ?)",
                (character_id, all_tag_id),
            )

        _set_meta(connection, "taxonomy_bootstrap_done", "1")
        connection.commit()


def _run_catalog_bootstrap() -> None:
    with _get_connection() as connection:
        if _get_meta(connection, "taxonomy_bootstrap_done") == "1":
            return

    collapse_taxonomy_to_all()


def _seed_characters_from_legacy_if_needed() -> None:
    with _get_connection() as connection:
        existing_count = connection.execute("SELECT COUNT(*) FROM managed_characters").fetchone()[0]
        if existing_count > 0:
            return

        now = utcnow_iso()
        for entry in sorted(CHARACTER_ROUTES_ROOT.iterdir()):
            if not entry.is_dir() or entry.name == "page":
                continue

            meta_path = entry / "meta.json"
            if not meta_path.exists():
                continue

            seed = _extract_character_seed(entry)
            entity_type = _detect_entity_type_from_source_path(seed["source_path"])
            cursor = connection.execute(
                """
                INSERT INTO managed_characters(
                    name, slug, short_description, description, seo_title, seo_description,
                    contact_phone, telegram_url, base_price, default_duration_minutes,
                    status, entity_type, source_path, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    seed["name"],
                    seed["slug"],
                    seed["short_description"],
                    seed["description"],
                    seed["seo_title"],
                    seed["seo_description"],
                    seed["contact_phone"],
                    seed["telegram_url"],
                    DEFAULT_SHOW_PROGRAM_PRICE if entity_type == ENTITY_TYPE_SHOW_PROGRAM else 0,
                    get_default_show_program_duration_minutes(seed["slug"])
                    if entity_type == ENTITY_TYPE_SHOW_PROGRAM
                    else DEFAULT_SHOW_PROGRAM_DURATION_MINUTES,
                    entity_type,
                    seed["source_path"],
                    now,
                    now,
                ),
            )
            character_id = int(cursor.lastrowid)

            hero_media_id: int | None = None
            for index, (media_type, file_path, alt_text) in enumerate(seed["media"], start=1):
                media_cursor = connection.execute(
                    """
                    INSERT INTO managed_character_media(
                        character_id, media_type, file_path, alt_text, caption, sort_order, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, '', ?, ?, ?)
                    """,
                    (character_id, media_type, file_path, alt_text, index, now, now),
                )
                if hero_media_id is None and media_type == "image":
                    hero_media_id = int(media_cursor.lastrowid)

            if hero_media_id:
                connection.execute(
                    "UPDATE managed_characters SET hero_media_id = ? WHERE id = ?",
                    (hero_media_id, character_id),
                )

            _assign_default_taxonomy(connection, character_id)

        connection.commit()


def _media_type_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return "image"


def _stored_show_features(row: sqlite3.Row) -> list[dict[str, str]]:
    if "program_features" not in row.keys() or not row["program_features"]:
        return []
    try:
        return normalize_show_features(row["program_features"])
    except ValueError:
        return []


def _character_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    entity_type = _normalize_entity_type(row["entity_type"]) if "entity_type" in row.keys() else ENTITY_TYPE_CHARACTER
    route_prefix = "show-programs" if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "character"
    ensemble_members = parse_ensemble_members(
        row["ensemble_members"] if "ensemble_members" in row.keys() else ""
    )
    ensemble_included_count = _normalize_non_negative_int(
        row["ensemble_included_count"]
        if "ensemble_included_count" in row.keys() and row["ensemble_included_count"] is not None
        else DEFAULT_INCLUDED_MEMBERS_COUNT,
        DEFAULT_INCLUDED_MEMBERS_COUNT,
    )
    ensemble_extra_member_price = _normalize_non_negative_int(
        row["ensemble_extra_member_price"]
        if "ensemble_extra_member_price" in row.keys() and row["ensemble_extra_member_price"] is not None
        else DEFAULT_EXTRA_MEMBER_PRICE,
        DEFAULT_EXTRA_MEMBER_PRICE,
    )
    return {
        "id": row["id"],
        "name": row["name"],
        "slug": row["slug"],
        "route": f"/{route_prefix}/{row['slug']}/",
        "short_description": row["short_description"],
        "description": row["description"],
        "seo_title": row["seo_title"],
        "seo_description": row["seo_description"],
        "search_terms": row["search_terms"] if "search_terms" in row.keys() else "",
        "duplicate_count": _normalize_non_negative_int(row["duplicate_count"] if "duplicate_count" in row.keys() else 0, 0),
        "total_capacity": 1 + _normalize_non_negative_int(row["duplicate_count"] if "duplicate_count" in row.keys() else 0, 0),
        "contact_phone": row["contact_phone"],
        "telegram_url": row["telegram_url"],
        "base_price": _normalize_non_negative_int(row["base_price"] if "base_price" in row.keys() else 0, 0),
        "default_duration_minutes": _normalize_non_negative_int(
            row["default_duration_minutes"] if "default_duration_minutes" in row.keys() else DEFAULT_SHOW_PROGRAM_DURATION_MINUTES,
            DEFAULT_SHOW_PROGRAM_DURATION_MINUTES,
        ),
        "included_characters_count": _normalize_non_negative_int(
            row["included_characters_count"]
            if "included_characters_count" in row.keys() and row["included_characters_count"] is not None
            else DEFAULT_INCLUDED_CHARACTERS_COUNT,
            DEFAULT_INCLUDED_CHARACTERS_COUNT,
        ),
        "extra_character_price_3": _normalize_non_negative_int(
            row["extra_character_price_3"]
            if "extra_character_price_3" in row.keys() and row["extra_character_price_3"] is not None
            else 0,
            0,
        ),
        "extra_character_price_4_plus": _normalize_non_negative_int(
            row["extra_character_price_4_plus"]
            if "extra_character_price_4_plus" in row.keys() and row["extra_character_price_4_plus"] is not None
            else 0,
            0,
        ),
        "sort_order": _normalize_non_negative_int(row["sort_order"] if "sort_order" in row.keys() else 0, 0),
        "age_from": _normalize_non_negative_int(row["age_from"], 0)
        if "age_from" in row.keys() and row["age_from"] is not None
        else None,
        "age_to": _normalize_non_negative_int(row["age_to"], 0)
        if "age_to" in row.keys() and row["age_to"] is not None
        else None,
        "show_category": row["show_category"] if "show_category" in row.keys() and row["show_category"] is not None else "",
        "format_tags": row["format_tags"] if "format_tags" in row.keys() and row["format_tags"] is not None else "",
        "included_items": row["included_items"] if "included_items" in row.keys() and row["included_items"] is not None else "",
        "suitable_for": row["suitable_for"] if "suitable_for" in row.keys() and row["suitable_for"] is not None else "",
        "restrictions": row["restrictions"] if "restrictions" in row.keys() and row["restrictions"] is not None else "",
        "video_url": row["video_url"] if "video_url" in row.keys() and row["video_url"] is not None else "",
        "ensemble_members": ensemble_members,
        "program_features": _stored_show_features(row),
        "program_cast": normalize_show_cast(row["program_cast"]) if "program_cast" in row.keys() and row["program_cast"] else [],
        "ensemble_included_count": ensemble_included_count,
        "ensemble_extra_member_price": ensemble_extra_member_price,
        # A roster with two or more real performers is a grouped character
        # even when every member is included (for example a fixed pair).
        "is_ensemble": len(ensemble_members) > 1,
        "variant_group_slug": row["variant_group_slug"] if "variant_group_slug" in row.keys() and row["variant_group_slug"] is not None else "",
        "variant_group_name": row["variant_group_name"] if "variant_group_name" in row.keys() and row["variant_group_name"] is not None else "",
        "variant_label": row["variant_label"] if "variant_label" in row.keys() and row["variant_label"] is not None else "",
        "status": row["status"],
        "entity_type": entity_type,
        "hero_media_id": row["hero_media_id"],
        "cover_offset_x": _normalize_non_negative_int(row["cover_offset_x"] if "cover_offset_x" in row.keys() and row["cover_offset_x"] is not None else 50, 50),
        "cover_offset_y": _normalize_non_negative_int(row["cover_offset_y"] if "cover_offset_y" in row.keys() and row["cover_offset_y"] is not None else 50, 50),
        "cover_fit": (str(row["cover_fit"]) if "cover_fit" in row.keys() and row["cover_fit"] else "cover"),
        "image_zoom": max(100, min(200, _normalize_non_negative_int(row["image_zoom"] if "image_zoom" in row.keys() and row["image_zoom"] is not None else 100, 100))),
        "mobile_cover_offset_x": _normalize_non_negative_int(row["mobile_cover_offset_x"] if "mobile_cover_offset_x" in row.keys() and row["mobile_cover_offset_x"] is not None else 50, 50),
        "mobile_cover_offset_y": _normalize_non_negative_int(row["mobile_cover_offset_y"] if "mobile_cover_offset_y" in row.keys() and row["mobile_cover_offset_y"] is not None else 50, 50),
        "mobile_cover_fit": (str(row["mobile_cover_fit"]) if "mobile_cover_fit" in row.keys() and row["mobile_cover_fit"] else "cover"),
        "mobile_image_zoom": max(100, min(200, _normalize_non_negative_int(row["mobile_image_zoom"] if "mobile_image_zoom" in row.keys() and row["mobile_image_zoom"] is not None else 100, 100))),
        "source_path": row["source_path"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_categories(include_hidden: bool = True) -> list[dict[str, Any]]:
    query = """
        SELECT
            c.id,
            c.name,
            c.slug,
            c.description,
            c.is_visible,
            c.is_system,
            c.linked_tag_id,
            lt.name AS linked_tag_name,
            lt.slug AS linked_tag_slug,
            c.sort_order,
            COUNT(DISTINCT CASE WHEN ch.entity_type = 'character' THEN cc.character_id END) AS character_count
        FROM managed_categories c
        LEFT JOIN managed_tags lt ON lt.id = c.linked_tag_id
        LEFT JOIN managed_character_categories cc ON cc.category_id = c.id
        LEFT JOIN managed_characters ch ON ch.id = cc.character_id
        GROUP BY c.id
    """
    if not include_hidden:
        query += " HAVING c.is_visible = 1"
    query += " ORDER BY CASE WHEN c.slug = 'all' THEN 0 ELSE 1 END ASC, c.sort_order ASC, c.name COLLATE NOCASE ASC"

    with _get_connection() as connection:
        rows = connection.execute(query).fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "slug": row["slug"],
            "route": f"/character-category/{row['slug']}/",
            "description": row["description"],
            "is_visible": bool(row["is_visible"]),
            "is_system": bool(row["is_system"]),
            "linked_tag_id": row["linked_tag_id"],
            "linked_tag_name": row["linked_tag_name"] or "",
            "linked_tag_slug": row["linked_tag_slug"] or "",
            "sort_order": row["sort_order"],
            "character_count": row["character_count"],
        }
        for row in rows
    ]


def list_categories_with_characters(include_hidden: bool = True) -> list[dict[str, Any]]:
    """Same as list_categories but each category embeds list of its characters with their tags."""
    categories = list_categories(include_hidden=include_hidden)
    if not categories:
        return []
    cat_ids = [c["id"] for c in categories]
    placeholders = ",".join("?" * len(cat_ids))
    with _get_connection() as connection:
        char_rows = connection.execute(
            f"""
            SELECT
                cc.category_id,
                ch.id            AS character_id,
                ch.name          AS character_name,
                ch.slug          AS character_slug,
                ch.status        AS character_status,
                ch.entity_type   AS entity_type
            FROM managed_character_categories cc
            INNER JOIN managed_characters ch ON ch.id = cc.character_id
            WHERE cc.category_id IN ({placeholders})
              AND ch.entity_type = 'character'
            ORDER BY ch.name COLLATE NOCASE ASC
            """,
            tuple(cat_ids),
        ).fetchall()
        all_char_ids = list({r["character_id"] for r in char_rows})
        tag_map: dict[int, list[dict[str, Any]]] = {cid: [] for cid in all_char_ids}
        if all_char_ids:
            tag_placeholders = ",".join("?" * len(all_char_ids))
            tag_rows = connection.execute(
                f"""
                SELECT ct.character_id, t.id AS tag_id, t.name AS tag_name, t.slug AS tag_slug
                FROM managed_character_tags ct
                INNER JOIN managed_tags t ON t.id = ct.tag_id
                WHERE ct.character_id IN ({tag_placeholders})
                  AND t.slug != 'all'
                ORDER BY t.sort_order ASC, t.name COLLATE NOCASE ASC
                """,
                tuple(all_char_ids),
            ).fetchall()
            for tr in tag_rows:
                tag_map.setdefault(int(tr["character_id"]), []).append(
                    {"id": int(tr["tag_id"]), "name": str(tr["tag_name"]), "slug": str(tr["tag_slug"])}
                )

    chars_by_cat: dict[int, list[dict[str, Any]]] = {cid: [] for cid in cat_ids}
    for r in char_rows:
        cat_id = int(r["category_id"])
        char_id = int(r["character_id"])
        chars_by_cat.setdefault(cat_id, []).append({
            "id": char_id,
            "name": str(r["character_name"]),
            "slug": str(r["character_slug"]),
            "status": str(r["character_status"] or ""),
            "tags": tag_map.get(char_id, []),
        })
    for cat in categories:
        cat["characters"] = chars_by_cat.get(cat["id"], [])
    return categories


def list_tags(include_hidden: bool = True) -> list[dict[str, Any]]:
    query = """
        SELECT
            t.id,
            t.name,
            t.slug,
            t.description,
            t.is_visible,
            t.is_system,
            t.sort_order,
            COUNT(DISTINCT CASE WHEN ch.entity_type = 'character' THEN ct.character_id END) AS character_count
        FROM managed_tags t
        LEFT JOIN managed_character_tags ct ON ct.tag_id = t.id
        LEFT JOIN managed_characters ch ON ch.id = ct.character_id
        GROUP BY t.id
    """
    if not include_hidden:
        query += " HAVING t.is_visible = 1"
    query += " ORDER BY t.sort_order ASC, t.name COLLATE NOCASE ASC"

    with _get_connection() as connection:
        rows = connection.execute(query).fetchall()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "slug": row["slug"],
            "route": f"/character-tag/{row['slug']}/",
            "description": row["description"],
            "is_visible": bool(row["is_visible"]),
            "is_system": bool(row["is_system"]),
            "sort_order": row["sort_order"],
            "character_count": row["character_count"],
        }
        for row in rows
    ]


def _character_list_query(filter_sql: str = "", params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    query = f"""
        SELECT
            ch.id,
            ch.name,
            ch.slug,
            ch.short_description,
            ch.description,
            ch.seo_title,
            ch.seo_description,
            ch.search_terms,
            ch.duplicate_count,
            ch.contact_phone,
            ch.telegram_url,
            ch.base_price,
            ch.default_duration_minutes,
            ch.included_characters_count,
            ch.extra_character_price_3,
            ch.extra_character_price_4_plus,
            ch.sort_order,
            ch.age_from,
            ch.age_to,
            ch.show_category,
            ch.format_tags,
            ch.included_items,
            ch.suitable_for,
            ch.restrictions,
            ch.video_url,
            ch.variant_group_slug,
            ch.variant_group_name,
            ch.variant_label,
            ch.ensemble_members,
            ch.ensemble_included_count,
            ch.ensemble_extra_member_price,
            ch.program_features,
            ch.program_cast,
            ch.status,
            ch.entity_type,
            ch.hero_media_id,
            ch.cover_offset_x,
            ch.cover_offset_y,
            ch.cover_fit,
            ch.image_zoom,
            ch.mobile_cover_offset_x,
            ch.mobile_cover_offset_y,
            ch.mobile_cover_fit,
            ch.mobile_image_zoom,
            ch.source_path,
            ch.created_at,
            ch.updated_at,
            hero.file_path AS hero_file_path,
            GROUP_CONCAT(DISTINCT cat.name) AS category_names,
            GROUP_CONCAT(DISTINCT cat.slug) AS category_slugs,
            GROUP_CONCAT(DISTINCT tag.name) AS tag_names,
            GROUP_CONCAT(DISTINCT tag.slug) AS tag_slugs
        FROM managed_characters ch
        LEFT JOIN managed_character_media hero ON hero.id = ch.hero_media_id
        LEFT JOIN managed_character_categories cc ON cc.character_id = ch.id
        LEFT JOIN managed_categories cat ON cat.id = cc.category_id
        LEFT JOIN managed_character_tags ct ON ct.character_id = ch.id
        LEFT JOIN managed_tags tag ON tag.id = ct.tag_id
        {filter_sql}
        GROUP BY ch.id
        ORDER BY
            CASE WHEN ch.entity_type = 'show_program' THEN COALESCE(ch.sort_order, 0) ELSE 0 END ASC,
            ch.name COLLATE NOCASE ASC
    """
    with _get_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = _character_row_to_dict(row)
        item["hero_file_path"] = row["hero_file_path"] or ""
        item["category_names"] = [name for name in (row["category_names"] or "").split(",") if name]
        item["category_slugs"] = [slug for slug in (row["category_slugs"] or "").split(",") if slug]
        item["tag_names"] = [name for name in (row["tag_names"] or "").split(",") if name]
        item["tag_slugs"] = [slug for slug in (row["tag_slugs"] or "").split(",") if slug]
        items.append(item)
    return items


def list_characters(search: str = "", status: str = "", entity_type: str | None = None) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if status.strip():
        clauses.append("ch.status = ?")
        params.append(status.strip())
    if entity_type:
        clauses.append("ch.entity_type = ?")
        params.append(_normalize_entity_type(entity_type))

    filter_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    items = _character_list_query(filter_sql, params)
    if search.strip():
        return sort_characters_for_search(filter_characters_by_search(items, search), search)
    return items


def attach_media_counts(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return items

    ids = [int(item["id"]) for item in items if item.get("id") is not None]
    if not ids:
        return items

    placeholders = ", ".join("?" for _ in ids)
    counts_by_id: dict[int, int] = {}
    with _get_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT character_id, COUNT(*) AS media_count
            FROM managed_character_media
            WHERE character_id IN ({placeholders})
            GROUP BY character_id
            """,
            tuple(ids),
        ).fetchall()
    for row in rows:
        counts_by_id[int(row["character_id"])] = int(row["media_count"] or 0)

    for item in items:
        item["media_count"] = counts_by_id.get(int(item["id"]), 0)
    return items


def list_characters_for_public(
    category_slug: str | None = None,
    tag_slug: str | None = None,
    *,
    entity_type: str = ENTITY_TYPE_CHARACTER,
    search: str = "",
) -> list[dict[str, Any]]:
    joins: list[str] = []
    clauses = ["ch.status = 'active'", "ch.entity_type = ?"]
    params: list[Any] = [_normalize_entity_type(entity_type)]

    if category_slug and category_slug != "all":
        joins.append("INNER JOIN managed_character_categories pcc ON pcc.character_id = ch.id")
        joins.append("INNER JOIN managed_categories pcat ON pcat.id = pcc.category_id")
        clauses.append("pcat.slug = ? AND pcat.is_visible = 1")
        params.append(category_slug)

    if tag_slug and tag_slug != "all":
        joins.append("INNER JOIN managed_character_tags pct ON pct.character_id = ch.id")
        joins.append("INNER JOIN managed_tags ptag ON ptag.id = pct.tag_id")
        clauses.append("ptag.slug = ? AND ptag.is_visible = 1")
        params.append(tag_slug)

    filter_sql = ""
    if joins or clauses:
        filter_sql = " ".join(joins)
        if clauses:
            filter_sql += " WHERE " + " AND ".join(clauses)

    items = _character_list_query(filter_sql, params)
    filtered_items: list[dict[str, Any]] = []
    for item in items:
        legacy_context = get_legacy_catalog_context(item.get("source_path", ""))
        item["legacy_category_slug"] = legacy_context["category_slug"]
        item["legacy_category_name"] = legacy_context["category_name"]
        if item["entity_type"] == ENTITY_TYPE_CHARACTER and legacy_context["category_slug"] in CATALOG_HIDDEN_LEGACY_CATEGORIES:
            continue
        item["is_show_program"] = item["entity_type"] == ENTITY_TYPE_SHOW_PROGRAM
        filtered_items.append(item)

    if search.strip():
        return sort_characters_for_search(filter_characters_by_search(filtered_items, search), search)
    return sorted(filtered_items, key=_character_public_sort_key)


def get_category_by_slug(slug: str) -> dict[str, Any] | None:
    for category in list_categories(include_hidden=True):
        if category["slug"] == slug:
            return category
    return None


def get_show_program_character_ids(program_id: int) -> list[int]:
    _ensure_show_program_characters_table()
    with _get_connection() as connection:
        rows = connection.execute(
            """
            SELECT spc.character_id
            FROM show_program_characters spc
            INNER JOIN managed_characters program
                ON program.id = spc.program_id AND program.entity_type = ?
            INNER JOIN managed_characters character
                ON character.id = spc.character_id AND character.entity_type = ?
            WHERE spc.program_id = ?
            ORDER BY spc.sort_order ASC, character.name COLLATE NOCASE ASC
            """,
            (ENTITY_TYPE_SHOW_PROGRAM, ENTITY_TYPE_CHARACTER, int(program_id)),
        ).fetchall()
    return [int(row["character_id"]) for row in rows]


def set_show_program_characters(program_id: int, character_ids: list[int]) -> None:
    _ensure_show_program_characters_table()
    unique_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in character_ids:
        try:
            character_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if character_id > 0 and character_id not in seen:
            unique_ids.append(character_id)
            seen.add(character_id)

    now = utcnow_iso()
    with _get_connection() as connection:
        program = connection.execute(
            "SELECT id FROM managed_characters WHERE id = ? AND entity_type = ? LIMIT 1",
            (int(program_id), ENTITY_TYPE_SHOW_PROGRAM),
        ).fetchone()
        if not program:
            return

        valid_ids: list[int] = []
        if unique_ids:
            placeholders = ", ".join("?" for _ in unique_ids)
            rows = connection.execute(
                f"""
                SELECT id
                FROM managed_characters
                WHERE id IN ({placeholders}) AND entity_type = ?
                ORDER BY name COLLATE NOCASE ASC
                """,
                (*unique_ids, ENTITY_TYPE_CHARACTER),
            ).fetchall()
            valid_ids = [int(row["id"]) for row in rows]

        connection.execute("DELETE FROM show_program_characters WHERE program_id = ?", (int(program_id),))
        for index, character_id in enumerate(valid_ids, start=1):
            connection.execute(
                """
                INSERT INTO show_program_characters(program_id, character_id, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(program_id), character_id, index, now, now),
            )
        connection.commit()


def get_show_program_character_slug_map(*, active_only: bool = True) -> dict[str, list[str]]:
    _ensure_show_program_characters_table()
    status_clause = "AND program.status = 'active'" if active_only else ""
    character_status_clause = "AND character.status = 'active'" if active_only else ""
    with _get_connection() as connection:
        programs = connection.execute(
            f"""
            SELECT program.id, program.slug
            FROM managed_characters program
            WHERE program.entity_type = ? {status_clause}
            ORDER BY COALESCE(program.sort_order, 0) ASC, program.name COLLATE NOCASE ASC
            """,
            (ENTITY_TYPE_SHOW_PROGRAM,),
        ).fetchall()
        result: dict[str, list[str]] = {str(row["slug"]): [] for row in programs}
        if not programs:
            return result

        rows = connection.execute(
            f"""
            SELECT program.slug AS program_slug, character.slug AS character_slug
            FROM show_program_characters spc
            INNER JOIN managed_characters program
                ON program.id = spc.program_id AND program.entity_type = ? {status_clause}
            INNER JOIN managed_characters character
                ON character.id = spc.character_id AND character.entity_type = ? {character_status_clause}
            ORDER BY spc.sort_order ASC, character.name COLLATE NOCASE ASC
            """,
            (ENTITY_TYPE_SHOW_PROGRAM, ENTITY_TYPE_CHARACTER),
        ).fetchall()

    for row in rows:
        program_slug = str(row["program_slug"])
        character_slug = str(row["character_slug"])
        result.setdefault(program_slug, [])
        if character_slug not in result[program_slug]:
            result[program_slug].append(character_slug)
    return result


def get_tag_by_slug(slug: str) -> dict[str, Any] | None:
    for tag in list_tags(include_hidden=True):
        if tag["slug"] == slug:
            return tag
    return None


def _get_media_for_character(connection: sqlite3.Connection, character_id: int) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, media_type, file_path, alt_text, caption, sort_order
        FROM managed_character_media
        WHERE character_id = ?
        ORDER BY sort_order ASC, id ASC
        """,
        (character_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "media_type": row["media_type"],
            "file_path": row["file_path"],
            "alt_text": row["alt_text"],
            "caption": row["caption"],
            "sort_order": row["sort_order"],
        }
        for row in rows
    ]


def _get_taxonomy_assignments(connection: sqlite3.Connection, character_id: int) -> tuple[list[int], list[int]]:
    category_ids = [
        row["category_id"]
        for row in connection.execute(
            "SELECT category_id FROM managed_character_categories WHERE character_id = ?",
            (character_id,),
        ).fetchall()
    ]
    tag_ids = [
        row["tag_id"]
        for row in connection.execute(
            "SELECT tag_id FROM managed_character_tags WHERE character_id = ?",
            (character_id,),
        ).fetchall()
    ]
    return category_ids, tag_ids


def get_character_by_id(character_id: int) -> dict[str, Any] | None:
    with _get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM managed_characters WHERE id = ? LIMIT 1",
            (character_id,),
        ).fetchone()
        if not row:
            return None
        character = _character_row_to_dict(row)
        character["media"] = _get_media_for_character(connection, character_id)
        category_ids, tag_ids = _get_taxonomy_assignments(connection, character_id)
        character["category_ids"] = category_ids
        character["tag_ids"] = tag_ids

    categories = list_categories(include_hidden=True)
    tags = list_tags(include_hidden=True)
    character["categories"] = [item for item in categories if item["id"] in character["category_ids"]]
    character["tags"] = [item for item in tags if item["id"] in character["tag_ids"]]
    legacy_context = get_legacy_catalog_context(character.get("source_path", ""))
    character["legacy_category_slug"] = legacy_context["category_slug"]
    character["legacy_category_name"] = legacy_context["category_name"]
    character["is_show_program"] = character["entity_type"] == ENTITY_TYPE_SHOW_PROGRAM
    character["hero_file_path"] = ""
    for media in character["media"]:
        if media["id"] == character["hero_media_id"]:
            character["hero_file_path"] = media["file_path"]
            break
    if not character["hero_file_path"] and character["media"]:
        character["hero_file_path"] = character["media"][0]["file_path"]
    return character


def get_character_by_slug(slug: str, include_hidden: bool = False) -> dict[str, Any] | None:
    with _get_connection() as connection:
        clauses = ["slug = ?"]
        params: list[Any] = [slug]
        if not include_hidden:
            clauses.append("status = 'active'")
        row = connection.execute(
            f"SELECT * FROM managed_characters WHERE {' AND '.join(clauses)} LIMIT 1",
            params,
        ).fetchone()
        if not row:
            return None
        character = _character_row_to_dict(row)
        character["media"] = _get_media_for_character(connection, row["id"])
        category_ids, tag_ids = _get_taxonomy_assignments(connection, row["id"])
        character["category_ids"] = category_ids
        character["tag_ids"] = tag_ids

    categories = list_categories(include_hidden=True)
    tags = list_tags(include_hidden=True)
    character["categories"] = [item for item in categories if item["id"] in character["category_ids"]]
    character["tags"] = [item for item in tags if item["id"] in character["tag_ids"]]
    legacy_context = get_legacy_catalog_context(character.get("source_path", ""))
    character["legacy_category_slug"] = legacy_context["category_slug"]
    character["legacy_category_name"] = legacy_context["category_name"]
    character["is_show_program"] = character["entity_type"] == ENTITY_TYPE_SHOW_PROGRAM
    character["hero_file_path"] = ""
    for media in character["media"]:
        if media["id"] == character["hero_media_id"]:
            character["hero_file_path"] = media["file_path"]
            break
    if not character["hero_file_path"] and character["media"]:
        character["hero_file_path"] = character["media"][0]["file_path"]
    return character


def get_catalog_summary() -> dict[str, int]:
    return {
        "character": len(list_characters(entity_type=ENTITY_TYPE_CHARACTER)),
        "show_program": len(list_characters(entity_type=ENTITY_TYPE_SHOW_PROGRAM)),
        "category": len(list_categories()),
        "tag": len(list_tags()),
    }


def create_category(
    name: str,
    slug: str,
    description: str,
    is_visible: bool,
    *,
    linked_tag_id: int | None = None,
    linked_tag_name: str = "",
    linked_tag_slug: str = "",
) -> int:
    with _get_connection() as connection:
        # If no linked tag info given, auto-create a tag from the category's own name/slug.
        if not linked_tag_id and not (linked_tag_name.strip() or linked_tag_slug.strip()):
            linked_tag_name = name
            linked_tag_slug = slug
        resolved_tag_id = _resolve_or_create_tag_id(
            connection,
            tag_id=linked_tag_id,
            name=linked_tag_name,
            slug=linked_tag_slug,
            is_visible=is_visible,
        )
        final_slug = _ensure_unique_slug(connection, "managed_categories", slug or name)
        next_sort_order = _next_sort_order(connection, "managed_categories")
        cursor = connection.execute(
            """
            INSERT INTO managed_categories(name, slug, description, is_visible, is_system, linked_tag_id, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?)
            """,
            (
                name.strip(),
                final_slug,
                description.strip(),
                1 if is_visible else 0,
                resolved_tag_id,
                next_sort_order,
                utcnow_iso(),
                utcnow_iso(),
            ),
        )
        _sync_linked_category_assignments(connection)
        connection.commit()
        return int(cursor.lastrowid)


def update_category(
    category_id: int,
    name: str,
    slug: str,
    description: str,
    is_visible: bool,
    *,
    linked_tag_id: int | None = None,
    linked_tag_name: str = "",
    linked_tag_slug: str = "",
) -> None:
    with _get_connection() as connection:
        row = connection.execute("SELECT is_system FROM managed_categories WHERE id = ?", (category_id,)).fetchone()
        if not row:
            return
        resolved_tag_id = _resolve_or_create_tag_id(
            connection,
            tag_id=linked_tag_id,
            name=linked_tag_name,
            slug=linked_tag_slug,
            is_visible=is_visible,
        )
        final_slug = _ensure_unique_slug(connection, "managed_categories", slug or name, exclude_id=category_id)
        if row["is_system"]:
            final_slug = "all"
            is_visible = True
            _, all_tag_id = _get_default_taxonomy_ids(connection)
            resolved_tag_id = all_tag_id
        connection.execute(
            """
            UPDATE managed_categories
            SET name = ?, slug = ?, description = ?, is_visible = ?, linked_tag_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                name.strip(),
                final_slug,
                description.strip(),
                1 if is_visible else 0,
                resolved_tag_id,
                utcnow_iso(),
                category_id,
            ),
        )
        _sync_linked_category_assignments(connection)
        connection.commit()


def delete_category(category_id: int) -> bool:
    with _get_connection() as connection:
        row = connection.execute("SELECT is_system FROM managed_categories WHERE id = ?", (category_id,)).fetchone()
        if not row or row["is_system"]:
            return False
        connection.execute("DELETE FROM managed_character_categories WHERE category_id = ?", (category_id,))
        connection.execute("DELETE FROM managed_categories WHERE id = ?", (category_id,))
        all_category = connection.execute("SELECT id FROM managed_categories WHERE slug = 'all'").fetchone()
        if all_category:
            orphan_rows = connection.execute(
                """
                SELECT id FROM managed_characters
                WHERE id NOT IN (SELECT DISTINCT character_id FROM managed_character_categories)
                """
            ).fetchall()
            for orphan in orphan_rows:
                connection.execute(
                    "INSERT OR IGNORE INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
                    (orphan["id"], all_category["id"]),
                )
        _sync_linked_category_assignments(connection)
        connection.commit()
        return True


def create_tag(name: str, slug: str, description: str, is_visible: bool) -> int:
    with _get_connection() as connection:
        final_slug = _ensure_unique_slug(connection, "managed_tags", slug or name)
        next_sort_order = _next_sort_order(connection, "managed_tags")
        cursor = connection.execute(
            """
            INSERT INTO managed_tags(name, slug, description, is_visible, is_system, sort_order, created_at, updated_at)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                name.strip(),
                final_slug,
                description.strip(),
                1 if is_visible else 0,
                next_sort_order,
                utcnow_iso(),
                utcnow_iso(),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def update_tag(tag_id: int, name: str, slug: str, description: str, is_visible: bool) -> None:
    with _get_connection() as connection:
        row = connection.execute("SELECT is_system FROM managed_tags WHERE id = ?", (tag_id,)).fetchone()
        if not row:
            return
        final_slug = _ensure_unique_slug(connection, "managed_tags", slug or name, exclude_id=tag_id)
        if row["is_system"]:
            final_slug = "all"
            is_visible = True
        connection.execute(
            """
            UPDATE managed_tags
            SET name = ?, slug = ?, description = ?, is_visible = ?, updated_at = ?
            WHERE id = ?
            """,
            (name.strip(), final_slug, description.strip(), 1 if is_visible else 0, utcnow_iso(), tag_id),
        )
        _sync_linked_category_assignments(connection)
        connection.commit()


def delete_tag(tag_id: int) -> bool:
    with _get_connection() as connection:
        row = connection.execute("SELECT is_system FROM managed_tags WHERE id = ?", (tag_id,)).fetchone()
        if not row or row["is_system"]:
            return False
        connection.execute("UPDATE managed_categories SET linked_tag_id = NULL, updated_at = ? WHERE linked_tag_id = ?", (utcnow_iso(), tag_id))
        connection.execute("DELETE FROM managed_character_tags WHERE tag_id = ?", (tag_id,))
        connection.execute("DELETE FROM managed_tags WHERE id = ?", (tag_id,))
        all_tag = connection.execute("SELECT id FROM managed_tags WHERE slug = 'all'").fetchone()
        if all_tag:
            orphan_rows = connection.execute(
                """
                SELECT id FROM managed_characters
                WHERE id NOT IN (SELECT DISTINCT character_id FROM managed_character_tags)
                """
            ).fetchall()
            for orphan in orphan_rows:
                connection.execute(
                    "INSERT OR IGNORE INTO managed_character_tags(character_id, tag_id) VALUES (?, ?)",
                    (orphan["id"], all_tag["id"]),
                )
        _sync_linked_category_assignments(connection)
        connection.commit()
        return True


def create_character(data: dict[str, Any]) -> int:
    entity_type = _normalize_entity_type(data.get("entity_type"))
    default_price = DEFAULT_SHOW_PROGRAM_PRICE if entity_type == ENTITY_TYPE_SHOW_PROGRAM else 0
    default_duration = (
        get_default_show_program_duration_minutes(data.get("slug") or data.get("name", ""))
        if entity_type == ENTITY_TYPE_SHOW_PROGRAM
        else DEFAULT_SHOW_PROGRAM_DURATION_MINUTES
    )
    base_price = _normalize_non_negative_int(data.get("base_price"), default_price) if entity_type == ENTITY_TYPE_SHOW_PROGRAM else 0
    default_duration_minutes = _normalize_non_negative_int(data.get("default_duration_minutes"), default_duration)
    included_characters_count = (
        _normalize_non_negative_int(data.get("included_characters_count"), DEFAULT_INCLUDED_CHARACTERS_COUNT)
        if entity_type == ENTITY_TYPE_SHOW_PROGRAM
        else DEFAULT_INCLUDED_CHARACTERS_COUNT
    )
    extra_character_price_3 = (
        _normalize_non_negative_int(data.get("extra_character_price_3"), 0)
        if entity_type == ENTITY_TYPE_SHOW_PROGRAM
        else 0
    )
    extra_character_price_4_plus = (
        _normalize_non_negative_int(data.get("extra_character_price_4_plus"), 0)
        if entity_type == ENTITY_TYPE_SHOW_PROGRAM
        else 0
    )
    sort_order = _normalize_non_negative_int(data.get("sort_order"), 0) if entity_type == ENTITY_TYPE_SHOW_PROGRAM else 0
    age_from = _normalize_non_negative_int(data.get("age_from"), 0) if entity_type == ENTITY_TYPE_SHOW_PROGRAM and str(data.get("age_from", "")).strip() else None
    age_to = _normalize_non_negative_int(data.get("age_to"), 0) if entity_type == ENTITY_TYPE_SHOW_PROGRAM and str(data.get("age_to", "")).strip() else None
    ensemble_members, ensemble_included_count, ensemble_extra_member_price = _normalize_ensemble_fields(data, entity_type)
    program_features, program_cast, included_items = _show_content_values(data, entity_type)
    with _get_connection() as connection:
        final_slug = _ensure_unique_slug(connection, "managed_characters", data.get("slug") or data.get("name", "character"))
        cursor = connection.execute(
            """
            INSERT INTO managed_characters(
                name, slug, short_description, description, seo_title, seo_description,
                search_terms, duplicate_count, contact_phone, telegram_url, base_price, default_duration_minutes,
                included_characters_count, extra_character_price_3, extra_character_price_4_plus,
                sort_order, age_from, age_to, show_category, format_tags, included_items, suitable_for,
                restrictions, video_url, variant_group_slug, variant_group_name, variant_label,
                ensemble_members, ensemble_included_count, ensemble_extra_member_price,
                program_features, program_cast,
                status, entity_type, source_path, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.get("name", "").strip(),
                final_slug,
                data.get("short_description", "").strip(),
                data.get("description", "").strip(),
                data.get("seo_title", "").strip(),
                data.get("seo_description", "").strip(),
                data.get("search_terms", "").strip(),
                _normalize_non_negative_int(data.get("duplicate_count"), 0) if entity_type == ENTITY_TYPE_CHARACTER else 0,
                data.get("contact_phone", "").strip() or DEFAULT_PHONE,
                data.get("telegram_url", "").strip() or DEFAULT_TELEGRAM_URL,
                base_price,
                default_duration_minutes,
                included_characters_count,
                extra_character_price_3,
                extra_character_price_4_plus,
                sort_order,
                age_from,
                age_to,
                data.get("show_category", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("format_tags", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                included_items,
                data.get("suitable_for", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("restrictions", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("video_url", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("variant_group_slug", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("variant_group_name", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("variant_label", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                ensemble_members,
                ensemble_included_count,
                ensemble_extra_member_price,
                program_features,
                program_cast,
                data.get("status", "active"),
                entity_type,
                "",
                utcnow_iso(),
                utcnow_iso(),
            ),
        )
        character_id = int(cursor.lastrowid)
        connection.commit()

    set_character_taxonomy(
        character_id,
        category_ids=[int(value) for value in data.get("category_ids", [])],
        tag_ids=[int(value) for value in data.get("tag_ids", [])],
    )
    return character_id


def update_character(character_id: int, data: dict[str, Any]) -> None:
    entity_type = _normalize_entity_type(data.get("entity_type"))
    default_price = DEFAULT_SHOW_PROGRAM_PRICE if entity_type == ENTITY_TYPE_SHOW_PROGRAM else 0
    default_duration = (
        get_default_show_program_duration_minutes(data.get("slug") or data.get("name", ""))
        if entity_type == ENTITY_TYPE_SHOW_PROGRAM
        else DEFAULT_SHOW_PROGRAM_DURATION_MINUTES
    )
    base_price = _normalize_non_negative_int(data.get("base_price"), default_price) if entity_type == ENTITY_TYPE_SHOW_PROGRAM else 0
    default_duration_minutes = _normalize_non_negative_int(data.get("default_duration_minutes"), default_duration)
    included_characters_count = (
        _normalize_non_negative_int(data.get("included_characters_count"), DEFAULT_INCLUDED_CHARACTERS_COUNT)
        if entity_type == ENTITY_TYPE_SHOW_PROGRAM
        else DEFAULT_INCLUDED_CHARACTERS_COUNT
    )
    extra_character_price_3 = (
        _normalize_non_negative_int(data.get("extra_character_price_3"), 0)
        if entity_type == ENTITY_TYPE_SHOW_PROGRAM
        else 0
    )
    extra_character_price_4_plus = (
        _normalize_non_negative_int(data.get("extra_character_price_4_plus"), 0)
        if entity_type == ENTITY_TYPE_SHOW_PROGRAM
        else 0
    )
    sort_order = _normalize_non_negative_int(data.get("sort_order"), 0) if entity_type == ENTITY_TYPE_SHOW_PROGRAM else 0
    age_from = _normalize_non_negative_int(data.get("age_from"), 0) if entity_type == ENTITY_TYPE_SHOW_PROGRAM and str(data.get("age_from", "")).strip() else None
    age_to = _normalize_non_negative_int(data.get("age_to"), 0) if entity_type == ENTITY_TYPE_SHOW_PROGRAM and str(data.get("age_to", "")).strip() else None
    ensemble_members, ensemble_included_count, ensemble_extra_member_price = _normalize_ensemble_fields(data, entity_type)
    if entity_type == ENTITY_TYPE_SHOW_PROGRAM and not {"program_features", "program_cast"} <= data.keys():
        # Callers that only know the legacy fields (the Flask form) must not wipe
        # the structured content the Next admin saved.
        stored = get_character_by_id(character_id) or {}
        data = {"program_features": stored.get("program_features"), "program_cast": stored.get("program_cast"), **data}
    program_features, program_cast, included_items = _show_content_values(data, entity_type)
    with _get_connection() as connection:
        final_slug = _ensure_unique_slug(connection, "managed_characters", data.get("slug") or data.get("name", "character"), exclude_id=character_id)
        connection.execute(
            """
            UPDATE managed_characters
            SET
                name = ?,
                slug = ?,
                short_description = ?,
                description = ?,
                seo_title = ?,
                seo_description = ?,
                search_terms = ?,
                duplicate_count = ?,
                contact_phone = ?,
                telegram_url = ?,
                base_price = ?,
                default_duration_minutes = ?,
                included_characters_count = ?,
                extra_character_price_3 = ?,
                extra_character_price_4_plus = ?,
                sort_order = ?,
                age_from = ?,
                age_to = ?,
                show_category = ?,
                format_tags = ?,
                included_items = ?,
                suitable_for = ?,
                restrictions = ?,
                video_url = ?,
                variant_group_slug = ?,
                variant_group_name = ?,
                variant_label = ?,
                status = ?,
                entity_type = ?,
                cover_offset_x = ?,
                cover_offset_y = ?,
                cover_fit = ?,
                image_zoom = ?,
                mobile_cover_offset_x = ?,
                mobile_cover_offset_y = ?,
                mobile_cover_fit = ?,
                mobile_image_zoom = ?,
                ensemble_members = ?,
                ensemble_included_count = ?,
                ensemble_extra_member_price = ?,
                program_features = ?,
                program_cast = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                data.get("name", "").strip(),
                final_slug,
                data.get("short_description", "").strip(),
                data.get("description", "").strip(),
                data.get("seo_title", "").strip(),
                data.get("seo_description", "").strip(),
                data.get("search_terms", "").strip(),
                _normalize_non_negative_int(data.get("duplicate_count"), 0) if entity_type == ENTITY_TYPE_CHARACTER else 0,
                data.get("contact_phone", "").strip() or DEFAULT_PHONE,
                data.get("telegram_url", "").strip() or DEFAULT_TELEGRAM_URL,
                base_price,
                default_duration_minutes,
                included_characters_count,
                extra_character_price_3,
                extra_character_price_4_plus,
                sort_order,
                age_from,
                age_to,
                data.get("show_category", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("format_tags", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                included_items,
                data.get("suitable_for", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("restrictions", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("video_url", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("variant_group_slug", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("variant_group_name", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("variant_label", "").strip() if entity_type == ENTITY_TYPE_SHOW_PROGRAM else "",
                data.get("status", "active"),
                entity_type,
                max(0, min(100, _normalize_non_negative_int(data.get("cover_offset_x"), 50))),
                max(0, min(100, _normalize_non_negative_int(data.get("cover_offset_y"), 50))),
                "contain" if str(data.get("cover_fit", "cover")).lower() == "contain" else "cover",
                max(100, min(200, _normalize_non_negative_int(data.get("image_zoom"), 100))),
                max(0, min(100, _normalize_non_negative_int(data.get("mobile_cover_offset_x"), 50))),
                max(0, min(100, _normalize_non_negative_int(data.get("mobile_cover_offset_y"), 50))),
                "contain" if str(data.get("mobile_cover_fit", "cover")).lower() == "contain" else "cover",
                max(100, min(200, _normalize_non_negative_int(data.get("mobile_image_zoom"), 100))),
                ensemble_members,
                ensemble_included_count,
                ensemble_extra_member_price,
                program_features,
                program_cast,
                utcnow_iso(),
                character_id,
            ),
        )
        connection.commit()

    set_character_taxonomy(
        character_id,
        category_ids=[int(value) for value in data.get("category_ids", [])],
        tag_ids=[int(value) for value in data.get("tag_ids", [])],
    )


def update_character_status(character_id: int, entity_type: str, status: str) -> bool:
    normalized_entity_type = _normalize_entity_type(entity_type)
    normalized_status = status if status in {"active", "draft", "hidden"} else "draft"
    with _get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE managed_characters
            SET status = ?, updated_at = ?
            WHERE id = ? AND entity_type = ?
            """,
            (normalized_status, utcnow_iso(), character_id, normalized_entity_type),
        )
        connection.commit()
        return cursor.rowcount > 0


def set_character_taxonomy(character_id: int, category_ids: list[int], tag_ids: list[int]) -> None:
    with _get_connection() as connection:
        connection.execute("DELETE FROM managed_character_categories WHERE character_id = ?", (character_id,))
        connection.execute("DELETE FROM managed_character_tags WHERE character_id = ?", (character_id,))

        _, all_tag_id = _get_default_taxonomy_ids(connection)
        if not tag_ids:
            tag_ids = [all_tag_id]
        category_ids = _resolve_category_ids_for_tags(
            connection,
            explicit_category_ids=category_ids,
            tag_ids=tag_ids,
        )

        for category_id in category_ids:
            connection.execute(
                "INSERT OR IGNORE INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
                (character_id, category_id),
            )
        for tag_id in tag_ids:
            connection.execute(
                "INSERT OR IGNORE INTO managed_character_tags(character_id, tag_id) VALUES (?, ?)",
                (character_id, tag_id),
            )
        connection.commit()


def update_media_metadata(character_id: int, media_updates: list[dict[str, Any]], hero_media_id: int | None) -> None:
    with _get_connection() as connection:
        for item in media_updates:
            connection.execute(
                """
                UPDATE managed_character_media
                SET alt_text = ?, caption = ?, sort_order = ?, updated_at = ?
                WHERE id = ? AND character_id = ?
                """,
                (
                    item.get("alt_text", "").strip(),
                    item.get("caption", "").strip(),
                    int(item.get("sort_order", 0)),
                    utcnow_iso(),
                    int(item["id"]),
                    character_id,
                ),
            )

        if hero_media_id is not None:
            valid = connection.execute(
                "SELECT id FROM managed_character_media WHERE id = ? AND character_id = ?",
                (hero_media_id, character_id),
            ).fetchone()
            if valid:
                connection.execute(
                    "UPDATE managed_characters SET hero_media_id = ?, updated_at = ? WHERE id = ?",
                    (hero_media_id, utcnow_iso(), character_id),
                )
        connection.commit()


def _save_file(character_slug: str, storage: FileStorage) -> tuple[str, str]:
    filename = secure_filename(storage.filename or "")
    if not filename:
        raise ValueError("empty filename")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    final_name = f"{timestamp}-{filename}"
    target_dir = UPLOAD_ROOT / character_slug
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / final_name
    storage.save(target_path)
    public_path = f"{UPLOAD_URL_ROOT}/{character_slug}/{final_name}"
    media_type = _media_type_for_path(final_name)
    return public_path.replace("\\", "/"), media_type


def upload_character_media(character_id: int, files: list[FileStorage]) -> int:
    character = get_character_by_id(character_id)
    if not character:
        return 0

    uploaded_count = 0
    with _get_connection() as connection:
        next_sort_order = connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM managed_character_media WHERE character_id = ?",
            (character_id,),
        ).fetchone()[0]
        hero_media_id = character["hero_media_id"]

        for storage in files:
            if not storage or not storage.filename:
                continue
            try:
                public_path, media_type = _save_file(character["slug"], storage)
            except ValueError:
                continue
            alt_text = Path(storage.filename).stem
            cursor = connection.execute(
                """
                INSERT INTO managed_character_media(
                    character_id, media_type, file_path, alt_text, caption, sort_order, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, '', ?, ?, ?)
                """,
                (character_id, media_type, public_path, alt_text, next_sort_order, utcnow_iso(), utcnow_iso()),
            )
            uploaded_count += 1
            if hero_media_id is None and media_type == "image":
                hero_media_id = int(cursor.lastrowid)
            next_sort_order += 1

        if hero_media_id and not character["hero_media_id"]:
            connection.execute(
                "UPDATE managed_characters SET hero_media_id = ?, updated_at = ? WHERE id = ?",
                (hero_media_id, utcnow_iso(), character_id),
            )
        connection.commit()

    return uploaded_count


def delete_media(character_id: int, media_id: int) -> bool:
    with _get_connection() as connection:
        media = connection.execute(
            "SELECT id, file_path FROM managed_character_media WHERE id = ? AND character_id = ?",
            (media_id, character_id),
        ).fetchone()
        if not media:
            return False

        file_path = str(media["file_path"])
        connection.execute("DELETE FROM managed_character_media WHERE id = ?", (media_id,))
        current_hero = connection.execute(
            "SELECT hero_media_id FROM managed_characters WHERE id = ?",
            (character_id,),
        ).fetchone()["hero_media_id"]
        if current_hero == media_id:
            replacement = connection.execute(
                """
                SELECT id FROM managed_character_media
                WHERE character_id = ?
                ORDER BY sort_order ASC, id ASC
                LIMIT 1
                """,
                (character_id,),
            ).fetchone()
            connection.execute(
                "UPDATE managed_characters SET hero_media_id = ?, updated_at = ? WHERE id = ?",
                (replacement["id"] if replacement else None, utcnow_iso(), character_id),
            )
        connection.commit()

    if file_path.startswith(UPLOAD_URL_ROOT):
        disk_path = STATIC_ROOT / file_path.lstrip("/")
        if disk_path.exists() and disk_path.is_file():
            disk_path.unlink()
    return True


def delete_character(character_id: int) -> bool:
    character = get_character_by_id(character_id)
    if not character:
        return False
    for media in character["media"]:
        delete_media(character_id, media["id"])
    with _get_connection() as connection:
        connection.execute("DELETE FROM managed_character_categories WHERE character_id = ?", (character_id,))
        connection.execute("DELETE FROM managed_character_tags WHERE character_id = ?", (character_id,))
        if connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'show_program_addons'"
        ).fetchone():
            connection.execute("DELETE FROM show_program_addons WHERE program_id = ?", (character_id,))
        if connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'show_program_characters'"
        ).fetchone():
            connection.execute(
                "DELETE FROM show_program_characters WHERE program_id = ? OR character_id = ?",
                (character_id, character_id),
            )
        connection.execute("DELETE FROM managed_characters WHERE id = ?", (character_id,))
        connection.commit()
    return True
