from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "catalogs.json"


def item(
    slug: str,
    title: str,
    description: str,
    *,
    image_slug: str | None = None,
    members: tuple[str, ...] = (),
    categories: tuple[str, ...] = ("boys", "girls", "cartoons"),
    base_price: int = 0,
    notes: tuple[str, ...] = (),
    included_items: str = "",
) -> dict[str, Any]:
    image_slug = image_slug or slug
    result: dict[str, Any] = {
        "id": f"character-{slug}",
        "title": title,
        "description": description,
        "image": f"assets/img/characters/{image_slug}-1200.webp",
        "alt": title,
        "cta_label": "Заказать",
        "href": f"/party-builder/?character={slug}",
        "active": True,
        "title_color": "#21165b",
        "image_position": {"x": 50, "y": 50},
        "image_zoom": 100,
        "categories": list(categories),
        "placements": ["homepage", "catalog", "party_builder"],
    }
    if members:
        result.update(
            ensemble_members=list(members),
            ensemble_included_count=2,
            ensemble_extra_member_price=0,
            ensemble_mode="fixed_pair" if len(members) == 2 else "choose_any",
        )
    if base_price:
        result["base_price"] = base_price
    if notes:
        result["service_notes"] = list(notes)
    if included_items:
        result["included_items"] = included_items
    return result


PAIR = (
    item("zootopia", "Ник и Джуди", "Весёлое расследование, игры и танцы с героями Зверополиса.", members=("Ник", "Джуди"), base_price=1_050_000, included_items="Игрушка входит в комплект"),
    item("paw-patrol", "Скай и Гонщик", "Командные задания и спасательная миссия Щенячьего патруля.", members=("Скай", "Гонщик")),
    item("among-us", "Among Us", "Космическая миссия с жёлтым и розовым членами экипажа.", members=("Жёлтый Among Us", "Розовый Among Us")),
    item("ladybug-cat-noir", "Леди Баг и Супер-Кот", "Супергеройские испытания и спасение праздничного Парижа.", members=("Леди Баг", "Супер-Кот"), categories=("superheroes", "boys", "girls")),
    item("naruto", "Наруто и Сакура", "Ниндзя-испытания, командные задания и яркое аниме-приключение.", members=("Наруто", "Сакура")),
    item("rumi-jinu", "Руми и Джину", "Музыкальная миссия, танцы и приключение любимых героев.", members=("Руми", "Джину")),
    item("amy-sonic", "Эми и Соник", "Скоростные эстафеты и активные игры с героями Соника.", members=("Эми", "Соник")),
    item("steampunk", "Золотые игрушки", "Блестящая пара оживших игрушек для ярких игр и фотографий.", members=("Золотая игрушка (мальчик)", "Золотая игрушка (девочка)")),
    item("gingerbread", "Печеньки", "Озорные Печеньки проводят сладкие испытания и танцы.", members=("Печенька (мальчик)", "Печенька (девочка)")),
    item("hosts-mickey-minnie", "Микки Маус и Минни Маус", "Открытые говорящие костюмы для игр, танцев и живого общения.", members=("Микки Маус", "Минни Маус")),
    item("the-fixies", "Симка и Нолик", "Познавательные игры, маленькие открытия и фиксики на празднике.", members=("Симка", "Нолик")),
    item("masha-and-the-bear", "Маша и Медведь", "Добрые шалости, танцы и лесные приключения.", members=("Маша", "Медведь")),
    item("mommy-baby-shark", "Baby Shark и Mommy Shark", "Морские танцы и весёлые игры всей акульей семьёй.", members=("Baby Shark", "Mommy Shark")),
    item("hawaiian-party", "Гавайская пара", "Тропические танцы, игры и солнечное настроение.", members=("Гаваец", "Гавайка")),
    item("tribal-party", "Индейская пара", "Командные испытания, танцы и приключение племени.", members=("Индеец", "Индианка")),
    item("jasmine-aladdin", "Аладдин и Жасмин", "Восточная сказка, волшебные задания и танцы.", members=("Аладдин", "Жасмин"), categories=("princesses", "boys", "girls")),
    item("sailors", "Моряк и Морячка", "Морские эстафеты и путешествие отважной команды.", members=("Моряк", "Морячка")),
    item("stitch-angel", "Стич и Энджел", "Космические шалости, объятия и зажигательные танцы.", members=("Стич", "Энджел")),
    item("neon-jesters-pair", "Неоновые ведущие", "Парные неоновые ведущие для светящихся игр, танцев и яркого шоу.", image_slug="neon-jesters", members=("Неоновый ведущий", "Неоновая ведущая")),
    item("mcqueen-assistant", "Маквин и Помощница", "Гоночные задания, скорость и настоящий пит-стоп.", members=("Маквин", "Помощница")),
    item("pink-blue-fairies", "Розовая и Голубая феи", "Воздушная сказка, волшебные задания и красивые танцы.", members=("Розовая фея", "Голубая фея"), categories=("princesses", "girls")),
    item("superman-supergirl", "Супермен и Супервумен", "Команда супергероев тренирует силу, ловкость и смелость.", members=("Супермен", "Супервумен"), categories=("superheroes", "boys", "girls")),
    item("kuromi-melody", "Куроми и Мелоди", "Стильная розово-фиолетовая вечеринка с играми и танцами.", members=("Куроми", "Мелоди")),
)

SINGLE = (
    item("spiderman-n1", "Человек-паук №1", "Супергеройские задания, ловкость и паутина.", categories=("superheroes", "boys")),
    item("spiderman-n2", "Человек-паук №2", "Ещё один костюм героя для командной супергеройской программы.", categories=("superheroes", "boys")),
    item("hulk", "Халк (ростовой)", "Сила, эстафеты и эффектное появление зелёного великана.", notes=("Ростовой персонаж выступает минимум с двумя открытыми говорящими ведущими.",), categories=("superheroes", "boys")),
    item("captain-america", "Капитан Америка", "Тренировка героев, щит и командные испытания.", categories=("superheroes", "boys")),
    item("deadpool", "Дэдпул", "Драйвовые задания и яркая супергеройская программа.", categories=("superheroes", "boys")),
    item("black-panther", "Чёрная Пантера", "Ловкость, тайные миссии и сила Ваканды.", categories=("superheroes", "boys")),
    item("digital-circus", "Помни", "Необычные игры из мира Удивительного цифрового цирка."),
    item("lol-mascot", "Кукла L.O.L. (ростовая)", "Яркая модная героиня для танцев и фотографий.", notes=("Ростовой персонаж выступает минимум с двумя открытыми говорящими ведущими.",)),
    item("gingerbread-mascot", "Печенька (ростовой)", "Большая весёлая Печенька для эффектного появления.", notes=("Ростовой персонаж выступает минимум с двумя открытыми говорящими ведущими.",)),
    item("tiger-mascot", "Тигр (ростовой)", "Добрый полосатый герой для танцев и активных игр.", notes=("Ростовой персонаж выступает минимум с двумя открытыми говорящими ведущими.",)),
    item("winnie-pooh", "Винни-Пух", "Добрые игры и тёплая встреча с любимым медвежонком.", image_slug="winnie-tigger"),
    item("rapunzel", "Рапунцель", "Сказочные задания, танцы и мечта о волшебных фонариках.", categories=("princesses", "girls")),
    item("belle", "Белоснежка", "Добрая сказка, музыкальные игры и королевские танцы.", categories=("princesses", "girls")),
    item("sasuke", "Саске", "Ниндзя-тренировка, ловкость и командные испытания."),
    item("little-ponies", "Радужная фея", "Волшебные игры, блёстки и радужное настроение.", categories=("princesses", "girls")),
    item("mickey-mascot", "Микки Маус (ростовой)", "Большой Микки для яркой встречи и фотографий.", notes=("Ростовой персонаж выступает минимум с двумя открытыми говорящими ведущими.",)),
    item("minnie-mascot", "Минни Маус (ростовая)", "Большая Минни для танцев и памятных фотографий.", notes=("Ростовой персонаж выступает минимум с двумя открытыми говорящими ведущими.",)),
    item("ronaldo-mascot", "Роналду (ростовой)", "Футбольные эмоции и встреча со звездой поля.", notes=("Ростовой персонаж выступает минимум с двумя открытыми говорящими ведущими.",), categories=("boys",)),
    item("messi-mascot", "Месси (ростовой)", "Футбольные задания и эффектное появление легенды.", notes=("Ростовой персонаж выступает минимум с двумя открытыми говорящими ведущими.",), categories=("boys",)),
    item("cheerleader-yellow", "Черлидерша (жёлтая)", "Энергичная поддержка, танцы и командные кричалки.", categories=("girls",)),
    item("cheerleader-red", "Черлидерша (красная)", "Спортивный драйв, танцы и яркие командные игры.", categories=("girls",)),
    item("football-ball", "Футбольный мяч", "Весёлый футбольный герой для эстафет и фотографий.", categories=("boys",)),
    item("goalkeeper", "Вратарь", "Футбольные конкурсы, ловкость и командная игра.", categories=("boys",)),
    item("hello-kitty", "Хеллоу Китти", "Нежная героиня для танцев, игр и красивых фотографий.", categories=("girls",)),
)

TRIO_AND_QUAD = (
    item("brawl-stars", "Шелли, Леон и Ворон", "Командная битва и испытания по мотивам Brawl Stars.", members=("Шелли", "Леон", "Ворон (ростовой)"), notes=("Ворон — ростовой персонаж; действует правило двух открытых ведущих.",)),
    item("kid-e-cats", "Три кота", "Коржик, Компот и Карамелька устраивают игры и танцы.", members=("Коржик", "Компот", "Карамелька")),
    item("anna-elsa-olaf", "Анна, Эльза и Олаф", "Снежная сказка, волшебные задания и танцы.", members=("Анна", "Эльза", "Олаф (ростовой)"), notes=("Олаф — ростовой персонаж; действует правило двух открытых ведущих.",), categories=("princesses", "boys", "girls")),
    item("surpriz-clown", "D Billions", "Чикки, Ляля и Бум-Бум проводят музыкальные игры.", members=("Чикки", "Ляля", "Бум-Бум")),
    item("safari", "Сафари", "Исследовательская экспедиция с динозавром и заданиями.", members=("Сафари (мальчик)", "Сафари (девочка)", "Динозавр (ростовой)"), notes=("Динозавр — ростовой персонаж; действует правило двух открытых ведущих.",)),
    item("neptune-mermaids", "Нептун и русалочки", "Подводная сказка с Нептуном и двумя русалочками.", members=("Нептун", "Русалочка (розовая)", "Русалочка (зелёная)"), base_price=25_000, notes=("При выборе Нептуна добавляется 25 000 сум.",), categories=("princesses", "boys", "girls")),
    item("labubu-quad", "Лабубу и Зимомо", "Четыре ярких героя: выберите любых двух или расширьте состав.", members=("Лабубу (ментоловый)", "Лабубу (розовый)", "Лабубу (радужный)", "Зимомо (ростовой)"), notes=("Зимомо — ростовой персонаж; действует правило двух открытых ведущих.",)),
)


def main() -> None:
    characters = [*PAIR, *SINGLE, *TRIO_AND_QUAD]
    if len(characters) != 54:
        raise ValueError(f"Expected 54 verified character cards, got {len(characters)}")
    ids = [character["id"] for character in characters]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate character IDs")
    missing_images = [character["image"] for character in characters if not (ROOT / character["image"]).is_file()]
    if missing_images:
        raise FileNotFoundError("Missing generated images: " + ", ".join(missing_images))

    payload = {
        "version": 3,
        "settings": {
            "autoplay_enabled": True,
            "autoplay_speed": 18,
            "character_booking_rules": {
                "fixed_pairs_include_all_members": True,
                "selectable_groups_include_members": 2,
                "selectable_group_extra_member_price": 0,
                "selectable_group_extra_member_pricing": "selected_show_program",
                "growth_costume_rule": "К ростовому персонажу требуется минимум два открытых говорящих костюма.",
                "outside_character_price_note": "Каждый артист сверх лимита оплачивается по тарифу выбранной шоу-программы.",
            },
        },
        "characters": characters,
    }
    MANIFEST.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(characters)} verified characters to {MANIFEST}")


if __name__ == "__main__":
    main()
