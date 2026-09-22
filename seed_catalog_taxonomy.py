"""
Seed/refresh catalog taxonomy: 7 категорий + 2 тега + явное распределение всех персонажей.

Идемпотентен. Запускай: ./.venv/bin/python seed_catalog_taxonomy.py
"""
from __future__ import annotations

from core.catalog_store import (
    _get_connection,
    create_category,
    create_tag,
    list_categories,
    list_tags,
)


CATEGORIES = [
    ("Супергерои", "supergeroi", "Marvel, DC и другие супергерои"),
    ("Мультики", "multiki", "Современные мультсериалы и мульт-герои"),
    ("Сказочные", "skazochnye", "Принцессы, сказочные и Disney-персонажи"),
    ("Фильмы", "filmy", "Герои из фильмов"),
    ("Сериалы", "serialy", "Герои из сериалов"),
    ("Ведущие", "veduschie", "Ведущие праздников и аниматоры"),
    ("Тематические", "tematicheskie", "Сезонные, тематические шоу-герои"),
]

TAGS = [
    ("Мальчикам", "malchikam"),
    ("Девочкам", "devochkam"),
]


# Явное распределение: character_slug -> {"cats": [...], "tags": [...]}
# Один персонаж может быть в нескольких категориях.
ASSIGNMENTS: dict[str, dict[str, list[str]]] = {
    # Супергерои
    "spiderman":                       {"cats": ["supergeroi"], "tags": ["malchikam"]},
    "spiderman-and-captain-america":   {"cats": ["supergeroi"], "tags": ["malchikam"]},
    "hulk":                            {"cats": ["supergeroi"], "tags": ["malchikam"]},
    "deadpool":                        {"cats": ["supergeroi"], "tags": ["malchikam"]},
    "black-panther":                   {"cats": ["supergeroi"], "tags": ["malchikam"]},
    "superman-superwoman":             {"cats": ["supergeroi"], "tags": ["malchikam", "devochkam"]},
    "ladybug-cat-noir":                {"cats": ["supergeroi", "multiki"], "tags": ["devochkam", "malchikam"]},

    # Мультики
    "minecraft":                       {"cats": ["multiki"], "tags": ["malchikam"]},
    "mommy-baby-shark":                {"cats": ["multiki"], "tags": []},
    "masha-and-the-bear":              {"cats": ["multiki"], "tags": ["devochkam", "malchikam"]},
    "stitch-angel":                    {"cats": ["multiki"], "tags": ["devochkam"]},
    "kid-e-cats":                      {"cats": ["multiki"], "tags": []},
    "the-fixies":                      {"cats": ["multiki"], "tags": ["malchikam"]},
    "blue-tractor":                    {"cats": ["multiki"], "tags": ["malchikam"]},
    "mickey-minnie":                   {"cats": ["multiki"], "tags": ["devochkam", "malchikam"]},
    "mario-toad":                      {"cats": ["multiki"], "tags": ["malchikam"]},
    "amy-sonic":                       {"cats": ["multiki"], "tags": ["malchikam", "devochkam"]},
    "paw-patrol":                      {"cats": ["multiki"], "tags": ["malchikam", "devochkam"]},
    "rainbow-friends":                 {"cats": ["multiki"], "tags": []},
    "little-ponies":                   {"cats": ["multiki"], "tags": ["devochkam"]},
    "little-ponies-new":               {"cats": ["multiki"], "tags": ["devochkam"]},
    "pony":                            {"cats": ["multiki"], "tags": ["devochkam"]},
    "dbillions":                       {"cats": ["multiki"], "tags": []},

    # Сказочные
    "anna-elsa-olaf":                  {"cats": ["skazochnye"], "tags": ["devochkam"]},
    "rapunzel":                        {"cats": ["skazochnye"], "tags": ["devochkam"]},
    "jasmine-aladdin":                 {"cats": ["skazochnye"], "tags": ["devochkam"]},
    "rainbow-fairy":                   {"cats": ["skazochnye"], "tags": ["devochkam"]},
    "fairy-tale-fairies":              {"cats": ["skazochnye"], "tags": ["devochkam"]},
    "labubu":                          {"cats": ["skazochnye"], "tags": ["devochkam"]},
    "alice-mad-hatter":                {"cats": ["skazochnye"], "tags": ["devochkam"]},
    "unicorns":                        {"cats": ["skazochnye"], "tags": ["devochkam"]},
    "neptune-mermaids":                {"cats": ["skazochnye"], "tags": ["devochkam"]},

    # Фильмы
    "harry-potter-hermione":           {"cats": ["filmy"], "tags": ["malchikam", "devochkam"]},
    "barbie":                          {"cats": ["filmy"], "tags": ["devochkam"]},
    "pirates":                         {"cats": ["filmy", "tematicheskie"], "tags": ["malchikam"]},
    "naruto-sakura":                   {"cats": ["filmy"], "tags": ["malchikam", "devochkam"]},

    # Сериалы
    "squid-game":                      {"cats": ["serialy"], "tags": []},
    "wednesday-enid":                  {"cats": ["serialy"], "tags": ["devochkam"]},
    "among-us":                        {"cats": ["serialy", "multiki"], "tags": ["malchikam"]},
    "brawl-stars":                     {"cats": ["serialy", "multiki"], "tags": ["malchikam"]},
    "vlad-a4":                         {"cats": ["serialy"], "tags": ["malchikam"]},
    "tiktok-youtube":                  {"cats": ["serialy"], "tags": []},

    # Ведущие
    "surpriz-clown":                   {"cats": ["veduschie"], "tags": []},

    # Тематические
    "military-victory-day":            {"cats": ["tematicheskie"], "tags": ["malchikam"]},
    "hawaiian-party":                  {"cats": ["tematicheskie"], "tags": []},
    "tribal-party":                    {"cats": ["tematicheskie"], "tags": ["malchikam"]},
    "sailors":                         {"cats": ["tematicheskie"], "tags": ["malchikam"]},
    "national-costumes":               {"cats": ["tematicheskie"], "tags": []},
    "ronaldo-messi":                   {"cats": ["tematicheskie"], "tags": ["malchikam"]},
    "footballers":                     {"cats": ["tematicheskie"], "tags": ["malchikam"]},
    "candy":                           {"cats": ["tematicheskie"], "tags": ["devochkam"]},
    "tapalapki":                       {"cats": ["tematicheskie"], "tags": []},
    "fan-fan-ducks":                   {"cats": ["tematicheskie"], "tags": []},

    # LOL / Hello Kitty (детские бренды → мультики + девочкам)
    "lol-doll":                        {"cats": ["multiki"], "tags": ["devochkam"]},
    "lol-bunny-ballerina":             {"cats": ["multiki"], "tags": ["devochkam"]},
    "hello-kitty":                     {"cats": ["multiki"], "tags": ["devochkam"]},
}


def ensure_taxonomy() -> tuple[dict[str, int], dict[str, int]]:
    cats = {c["slug"]: c["id"] for c in list_categories(include_hidden=True)}
    tags = {t["slug"]: t["id"] for t in list_tags(include_hidden=True)}

    cat_ids: dict[str, int] = {}
    for name, slug, desc in CATEGORIES:
        if slug in cats:
            cat_ids[slug] = cats[slug]
            print(f"  cat exists: {slug}")
        else:
            new_id = create_category(name, slug, desc, is_visible=True)
            cat_ids[slug] = new_id
            print(f"  cat created: {slug} (id={new_id})")

    tag_ids: dict[str, int] = {}
    for name, slug in TAGS:
        if slug in tags:
            tag_ids[slug] = tags[slug]
            print(f"  tag exists: {slug}")
        else:
            new_id = create_tag(name, slug, "", is_visible=True)
            tag_ids[slug] = new_id
            print(f"  tag created: {slug} (id={new_id})")
    return cat_ids, tag_ids


def assign_characters(cat_ids: dict[str, int], tag_ids: dict[str, int]) -> None:
    cat_assigned: dict[str, int] = {k: 0 for k in cat_ids}
    tag_assigned: dict[str, int] = {k: 0 for k in tag_ids}

    with _get_connection() as conn:
        rows = conn.execute(
            "SELECT id, slug FROM managed_characters WHERE entity_type = 'character'"
        ).fetchall()
        slug_to_id = {r["slug"]: r["id"] for r in rows}
        print(f"\nDB has {len(slug_to_id)} characters")

        # Удаляем старые автоматические присвоения, чтобы переназначения были чистые
        # (но не трогаем "all" — это дефолтная категория-обёртка)
        non_all_ids = [
            v for k, v in cat_ids.items() if k in {c[1] for c in CATEGORIES}
        ]
        if non_all_ids:
            placeholders = ",".join("?" * len(non_all_ids))
            conn.execute(
                f"DELETE FROM managed_character_categories WHERE category_id IN ({placeholders})",
                non_all_ids,
            )
        non_all_tag_ids = list(tag_ids.values())
        if non_all_tag_ids:
            placeholders = ",".join("?" * len(non_all_tag_ids))
            conn.execute(
                f"DELETE FROM managed_character_tags WHERE tag_id IN ({placeholders})",
                non_all_tag_ids,
            )

        missing_in_db: list[str] = []
        unassigned_in_db: list[str] = []

        for slug, plan in ASSIGNMENTS.items():
            cid = slug_to_id.get(slug)
            if cid is None:
                missing_in_db.append(slug)
                continue
            for cat_slug in plan.get("cats", []):
                cat_id = cat_ids.get(cat_slug)
                if cat_id is None:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO managed_character_categories(character_id, category_id) VALUES (?, ?)",
                    (cid, cat_id),
                )
                cat_assigned[cat_slug] += 1
            for tag_slug in plan.get("tags", []):
                tag_id = tag_ids.get(tag_slug)
                if tag_id is None:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO managed_character_tags(character_id, tag_id) VALUES (?, ?)",
                    (cid, tag_id),
                )
                tag_assigned[tag_slug] += 1

        for slug in slug_to_id:
            if slug not in ASSIGNMENTS:
                unassigned_in_db.append(slug)

        conn.commit()

    print("\nAssigned:")
    for k, v in cat_assigned.items():
        print(f"  category {k}: {v}")
    for k, v in tag_assigned.items():
        print(f"  tag {k}: {v}")
    if missing_in_db:
        print("\n[!] In ASSIGNMENTS but not in DB:")
        for s in missing_in_db:
            print(f"  - {s}")
    if unassigned_in_db:
        print("\n[!] In DB but not in ASSIGNMENTS (left as 'all' only):")
        for s in unassigned_in_db:
            print(f"  - {s}")


def main() -> None:
    print("=== Seeding categories & tags ===")
    cat_ids, tag_ids = ensure_taxonomy()
    print("\n=== Assigning characters ===")
    assign_characters(cat_ids, tag_ids)
    print("\n✓ Done")


if __name__ == "__main__":
    main()
