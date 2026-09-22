"""Surpriz v2 theme: clean chrome (head / header / footer / sprite) for the redesign.

Replaces the frozen WordPress chrome on dynamic pages. Pages are assembled via
:func:`render_v2_page`, which returns a :class:`core.loader.PageBundle` ready for
``templates/base.html`` and ``build_runtime_page_bundle``.

Auth personalization: the header contains two ``<template data-v2-auth="...">``
blocks; :func:`personalize` keeps the right one at runtime (called from
``core.loader.build_runtime_page_bundle`` when ``v2`` is in ``body_class``).
"""

from __future__ import annotations

import html
import os
import re
from functools import lru_cache
from pathlib import Path

from .catalog_bootstrap import resolve_landing_root
from .config import STATIC_ROOT
from .loader import PageBundle, build_site_footer_html

V2_BODY_CLASS = "v2"
DEFAULT_OG_IMAGE = "/surpriz/assets/img/show-programs/hero-desktop.webp"

#: Google Ads conversion tag. Appended last so it sits right before </head> on
#: every page rendered with this chrome.
GOOGLE_ADS_TAG_ID = "AW-18377952314"
GOOGLE_ANALYTICS_ID = "G-NPCRDJ4H5T"
#: Ownership proof for Search Console; has to sit in <head> on every page.
GOOGLE_SITE_VERIFICATION = "2AJ1hzBw1100KtlX1RdzHhmee59s-uGNXblWVGvtFU8"
GOOGLE_SITE_VERIFICATION_HTML = (
    f'<meta name="google-site-verification" content="{GOOGLE_SITE_VERIFICATION}">'
)
#: One gtag.js serves both properties — loading the library twice would double
#: every pageview, so the analytics property only adds its own config call.
GOOGLE_ADS_TAG_HTML = (
    f'<script async src="https://www.googletagmanager.com/gtag/js?id={GOOGLE_ADS_TAG_ID}"></script>\n'
    "<script>\n"
    "  window.dataLayer = window.dataLayer || [];\n"
    "  function gtag(){dataLayer.push(arguments);}\n"
    "  gtag('js', new Date());\n"
    f"  gtag('config', '{GOOGLE_ADS_TAG_ID}');\n"
    f"  gtag('config', '{GOOGLE_ANALYTICS_ID}');\n"
    "</script>"
)
LOGO_URL = "/wp-content/uploads/2025/06/logo.png"
FAVICON_URL = "/wp-content/uploads/2025/06/logo-100x100.png"
PHONE_DISPLAY = "+998 99 892-65-65"
PHONE_TEL = "tel:+998998926565"
TELEGRAM_URL = "https://t.me/Animator_Surpriz"
INSTAGRAM_URL = "https://www.instagram.com/animator.surpriz/"

#: active-key -> (href, label) for the primary navigation.
NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("shows", "/show-programs/", "Шоу-программы"),
    ("catalog", "/catalog/", "Персонажи"),
    ("prices", "/prices/", "Цены"),
    ("contacts", "/contacts/", "Контакты"),
)

CHARACTER_NAV_ITEMS: tuple[tuple[str, str, str, str], ...] = (
    ("all", "Все персонажи", "Весь каталог", "all-heroes.svg"),
    ("superheroes", "Супергерои", "Marvel, DC и другие", "superheroes.svg"),
    ("princesses", "Принцессы", "Сказочные героини", "princesses.svg"),
    ("boys", "Для мальчиков", "Экшен и приключения", "for-boys.svg"),
    ("girls", "Для девочек", "Магия и творчество", "for-girls.svg"),
    ("cartoons", "Мультгерои", "Любимые мультфильмы", "cartoon-characters.svg"),
)

#: routes rendered with the landing-page chrome instead of the v2 header.
# Routes rendered with the landing-page chrome. Detail pages are reached from
# the static catalog, so a v2 header there read as an older site.
_LANDING_SHELL_ROUTES = frozenset({"account", "builder", "catalog", "shows"})

_AUTH_TEMPLATE_RE = re.compile(
    r'<template\s+data-v2-auth="(login|account)">(.*?)</template>',
    re.IGNORECASE | re.DOTALL,
)


def _asset_version(relative_path: str) -> str:
    try:
        return str(int((STATIC_ROOT / relative_path).stat().st_mtime))
    except OSError:
        return "1"


def _landing_asset_version(relative_path: str) -> str:
    try:
        landing_root = resolve_landing_root(
            STATIC_ROOT.parent,
            os.environ.get("SURPRIZ_LANDING_ROOT", ""),
        )
        return str(int((Path(landing_root) / relative_path).stat().st_mtime_ns))
    except OSError:
        return "0"


def _icon(name: str, css_class: str = "v2-i") -> str:
    return f'<svg class="{css_class}" aria-hidden="true"><use href="#i-{name}"/></svg>'


@lru_cache(maxsize=1)
def _icons_sprite_inner() -> str:
    """Inner <symbol> markup of static/v2/icons.svg (single source of truth)."""
    sprite_path = STATIC_ROOT / "v2" / "icons.svg"
    try:
        raw = sprite_path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r"<svg[^>]*>(.*)</svg>", raw, re.DOTALL)
    return match.group(1).strip() if match else ""


CANONICAL_ORIGIN = "https://animator-surpriz.uz"


def _absolute_url(path_or_url: str) -> str:
    """Абсолютный адрес для og-тегов; уже абсолютные значения не трогает."""
    value = str(path_or_url or "").strip()
    if not value or value.startswith(("http://", "https://")):
        return value
    return f"{CANONICAL_ORIGIN}/{value.lstrip('/')}"


def build_head_html(
    title: str,
    description: str,
    canonical_path: str,
    og_image: str = "",
    *,
    extra_head_html: str = "",
    after_v2_css_html: str = "",
) -> str:
    """Clean v2 <head>: SEO meta, favicon, font preloads, fonts.css + v2.css. No WP assets."""
    normalized_title = html.escape(title, quote=False)
    normalized_description = description.strip()
    normalized_canonical = canonical_path if canonical_path.startswith("/") else f"/{canonical_path.lstrip('/')}"
    normalized_og_image = (og_image or DEFAULT_OG_IMAGE).strip() or DEFAULT_OG_IMAGE
    escaped_description = html.escape(normalized_description, quote=True)
    escaped_canonical = html.escape(normalized_canonical, quote=True)
    # Open Graph требует абсолютных адресов: Telegram и WhatsApp относительный
    # og:image не разворачивают, и превью ссылки собиралось пустым.
    escaped_og_url = html.escape(_absolute_url(normalized_canonical), quote=True)
    escaped_og_image = html.escape(_absolute_url(normalized_og_image), quote=True)
    css_version = _asset_version("v2/v2.css")

    parts = [
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
        GOOGLE_SITE_VERIFICATION_HTML,
        f"<title>{normalized_title}</title>",
    ]
    if normalized_description:
        parts.append(f'<meta name="description" content="{escaped_description}">')
    parts.extend(
        [
            f'<link rel="canonical" href="{escaped_canonical}">',
            '<meta property="og:locale" content="ru_RU">',
            '<meta property="og:type" content="website">',
            '<meta property="og:site_name" content="Surpriz">',
            f'<meta property="og:title" content="{html.escape(title, quote=True)}">',
            f'<meta property="og:url" content="{escaped_og_url}">',
            f'<meta property="og:image" content="{escaped_og_image}">',
            '<meta name="twitter:card" content="summary_large_image">',
        ]
    )
    if normalized_description:
        parts.append(f'<meta property="og:description" content="{escaped_description}">')
        parts.append(f'<meta name="twitter:description" content="{escaped_description}">')
    parts.extend(
        [
            f'<link rel="icon" type="image/png" sizes="100x100" href="{FAVICON_URL}">',
            f'<link rel="apple-touch-icon" href="{FAVICON_URL}">',
            '<link rel="preload" href="/fonts/rubik-var-cyrillic.woff2" as="font" type="font/woff2" crossorigin>',
            '<link rel="preload" href="/fonts/rubik-var-latin.woff2" as="font" type="font/woff2" crossorigin>',
            '<link rel="preload" href="/fonts/balsamiq-sans-700-cyrillic.woff2" as="font" type="font/woff2" crossorigin>',
            '<link rel="preload" href="/fonts/balsamiq-sans-700-latin.woff2" as="font" type="font/woff2" crossorigin>',
            '<link rel="stylesheet" href="/fonts/fonts.css">',
        ]
    )
    if extra_head_html.strip():
        parts.append(extra_head_html.strip())
    parts.append(f'<link rel="stylesheet" href="/v2/v2.css?v={css_version}">')
    # Skins that exist to override v2 have to come after it: at equal specificity
    # the later sheet wins, and v2 paints links with its own teal.
    if after_v2_css_html.strip():
        parts.append(after_v2_css_html.strip())
    parts.append(GOOGLE_ADS_TAG_HTML)
    # Ставится в <head>, а не перед </body>: инлайновый скрипт сборщика выполняется
    # раньше конца body, и на старте воронки хелперов ещё не существовало бы.
    parts.append(CONVERSION_EVENTS_HTML)
    parts.append(LOCAL_BUSINESS_JSONLD)
    return "\n".join(parts)


def _nav_link(key: str, href: str, label: str, active: str, css_class: str) -> str:
    is_active = key == active
    classes = f"{css_class} is-active" if is_active else css_class
    aria = ' aria-current="page"' if is_active else ""
    return f'<a class="{classes}" href="{href}"{aria}>{label}</a>'


def _character_menu_html(panel_id: str, *, is_active: bool = False) -> str:
    toggle_class = "nav-menu__toggle is-active" if is_active else "nav-menu__toggle"
    toggle_current = ' aria-current="page"' if is_active else ""
    items = "\n".join(
        f'''        <a class="nav-menu__item" href="/catalog/?character={slug}#characters" data-character-filter="{slug}">
          <span class="nav-menu__icon nav-menu__icon--{slug}" aria-hidden="true">
            <img src="/surpriz/assets/icons/categories/{icon}" alt="">
          </span>
          <span><strong>{label}</strong><small>{description}</small></span>
        </a>'''
        for slug, label, description, icon in CHARACTER_NAV_ITEMS
    )
    return f'''<div class="nav-menu" data-character-menu>
  <button class="{toggle_class}" type="button" aria-expanded="false" aria-controls="{panel_id}" data-character-menu-toggle{toggle_current}>
    Персонажи
    <span class="nav-menu__chevron" aria-hidden="true"></span>
  </button>
  <div class="nav-menu__panel" id="{panel_id}" data-character-menu-panel hidden>
    <div class="nav-menu__grid">
{items}
    </div>
    <a class="nav-menu__footer" href="/catalog/">Открыть полный каталог <span aria-hidden="true">→</span></a>
  </div>
</div>'''


def _profile_shell_html(active: str = "account") -> str:
    """Use the exact landing-page chrome for every landing-shell route."""
    create_class = "mobile-dock__create is-active" if active == "builder" else "mobile-dock__create"
    create_aria = ' aria-current="page"' if active == "builder" else ""

    def dock(route: str) -> tuple[str, str]:
        if active == route:
            return "mobile-dock__item is-active", ' aria-current="page"'
        return "mobile-dock__item", ""

    shows_class, shows_aria = dock("shows")
    catalog_class, catalog_aria = dock("catalog")
    profile_class, profile_aria = dock("account")
    character_menu = _character_menu_html("character-navigation-profile", is_active=active == "catalog")
    shows_link_class = ' class="is-active"' if active == "shows" else ""
    shows_link_aria = ' aria-current="page"' if active == "shows" else ""
    return f"""<header class="header">
  <a class="brand" href="/surpriz/" aria-label="Surpriz — на главную">
    <img src="/surpriz/favicon.png" alt="Surpriz" width="100" height="100">
    <span>СЮРПРИЗ</span>
  </a>
  <nav class="nav" aria-label="Главное меню">
    <a href="/show-programs/"{shows_link_class}{shows_link_aria}>Шоу-программы</a>
    {character_menu}
    <a href="/surpriz/#about">О нас</a>
  </nav>
  <div class="header__utility">
    <a class="header__phone" href="{PHONE_TEL}"><span>{PHONE_DISPLAY}</span></a>
    <a aria-label="Зарегистрироваться" class="header__register" data-auth-open href="/register/">
      <span data-auth-label>Зарегистрироваться</span>
      <svg aria-hidden="true"><use href="/surpriz/assets/icons.svg#i-user" /></svg>
    </a>
  </div>
</header>
<nav class="mobile-dock" aria-label="Мобильная навигация">
  <a class="mobile-dock__item" href="/surpriz/"><svg aria-hidden="true"><use href="/surpriz/assets/icons.svg#i-home" /></svg><span>Главная</span></a>
  <a class="{shows_class}" href="/show-programs/"{shows_aria}><svg aria-hidden="true"><use href="/surpriz/assets/icons.svg#i-star" /></svg><span>Шоу</span></a>
  <a class="{create_class}" href="/party-builder/" aria-label="Собрать праздник"{create_aria}><span class="mobile-dock__fab"><svg aria-hidden="true"><use href="/surpriz/assets/icons.svg#i-plus" /></svg></span><span>Собрать</span></a>
  <a class="{catalog_class}" href="/catalog/"{catalog_aria}><svg aria-hidden="true"><use href="/surpriz/assets/icons.svg#i-mask" /></svg><span>Герои</span></a>
  <a class="{profile_class}" href="/account/"{profile_aria}><svg aria-hidden="true"><use href="/surpriz/assets/icons.svg#i-user" /></svg><span>Профиль</span></a>
</nav>"""


def _profile_shell_footer_html() -> str:
    """Landing-page footer for account pages; avoids falling back to v2 chrome."""
    return f"""<footer class="surpriz-site-footer" role="contentinfo">
  <div class="surpriz-site-footer__inner">
    <section class="surpriz-site-footer__brand" aria-label="Surpriz">
      <a class="surpriz-site-footer__logo" href="/surpriz/"><img src="/surpriz/assets/original/logo.png" alt="Surpriz" loading="lazy"></a>
      <p>Организуем детские праздники, аниматоров и шоу-программы в Ташкенте.</p>
    </section>
    <section class="surpriz-site-footer__section" aria-label="Контакты">
      <h2 class="surpriz-site-footer__title">Контакты</h2>
      <a class="surpriz-site-footer__contact surpriz-site-footer__contact--phone" href="{PHONE_TEL}">{PHONE_DISPLAY}</a>
      <a class="surpriz-site-footer__contact" href="{TELEGRAM_URL}" target="_blank" rel="noopener">Telegram</a>
      <a class="surpriz-site-footer__contact" href="{INSTAGRAM_URL}" target="_blank" rel="noopener">Instagram</a>
    </section>
    <nav class="surpriz-site-footer__section" aria-label="Навигация">
      <h2 class="surpriz-site-footer__title">Навигация</h2>
      <ul class="surpriz-site-footer__links">
        <li><a href="/surpriz/">Главная</a></li>
        <li><a href="/surpriz/#shows">Шоу-программы</a></li>
        <li><a href="/surpriz/#heroes">Каталог персонажей</a></li>
        <li><a href="/surpriz/#about">О нас</a></li>
      </ul>
    </nav>
    <section class="surpriz-site-footer__section" aria-label="Быстрые действия">
      <h2 class="surpriz-site-footer__title">Быстро</h2>
      <div class="surpriz-site-footer__actions">
        <a class="surpriz-site-footer__button" href="/surpriz/#order">Собрать праздник</a>
        <a class="surpriz-site-footer__button" href="/account/">Личный кабинет</a>
        <a class="surpriz-site-footer__button" href="{PHONE_TEL}">Позвонить</a>
      </div>
    </section>
    <section class="surpriz-site-footer__section surpriz-site-footer__section--popular" aria-label="Популярные шоу">
      <h2 class="surpriz-site-footer__title">Популярные шоу</h2>
      <div class="surpriz-site-footer__popular">
      <a href="/show-programs/"><strong>Стандарт</strong><span>1 час · от 950 000 сум</span></a>
      <a href="/show-programs/"><strong>Крио шоу</strong><span>30 мин · от 1 000 000 сум</span></a>
      <a href="/show-programs/"><strong>Ленточное шоу</strong><span>1 час · от 1 000 000 сум</span></a>
      <a href="/show-programs/"><strong>Серпантин шоу</strong><span>1 час · от 1 000 000 сум</span></a>
      </div>
      </section>
  </div>
  <div class="surpriz-site-footer__bottom"><span>© 2026 Surpriz. Детские праздники в Ташкенте.</span></div>
</footer>"""


def build_header_html(active: str = "", is_authenticated: bool = False) -> str:
    """Sticky glass header + fullscreen mobile menu + mobile bottom bar.

    Auth state is embedded as <template data-v2-auth="login|account"> blocks and
    resolved later by :func:`personalize` (runtime, when the session is known).
    ``is_authenticated`` only pre-selects the default state for non-runtime renders.
    """
    if active in _LANDING_SHELL_ROUTES:
        return _profile_shell_html(active)

    nav_links = "\n        ".join(
        _character_menu_html("character-navigation-v2", is_active=active == "catalog")
        if key == "catalog"
        else _nav_link(key, href, label, active, "v2-header__nav-link")
        for key, href, label in NAV_ITEMS
    )
    mmenu_links = "\n        ".join(
        _nav_link(key, href, label, active, "v2-mmenu__link") for key, href, label in NAV_ITEMS
    )

    def auth_block(
        state: str,
        href: str,
        label: str,
        mbar_label: str,
        mbar_key: str,
        *,
        mbar_href: str = "",
    ) -> tuple[str, str, str]:
        """Return (header, mobile-menu, mobile-bar) auth snippets, each wrapped in
        its own <template data-v2-auth="..."> so personalize() can resolve state
        per location without leaking menu/bar markup into the header."""
        mbar_active = " is-active" if active in {"account", "auth"} else ""
        mbar_current = ' aria-current="page"' if mbar_active else ""
        header = (
            f'<template data-v2-auth="{state}">'
            f'<a class="v2-header__auth" href="{href}">{_icon("user")}<span>{label}</span></a>'
            f"</template>"
        )
        mmenu = (
            f'<template data-v2-auth="{state}">'
            f'<a class="v2-mmenu__auth" href="{href}">{_icon("user")}<span>{label}</span></a>'
            f"</template>"
        )
        mbar = (
            f'<template data-v2-auth="{state}">'
            f'<a class="v2-mbar__item{mbar_active}" data-v2-mbar-key="{mbar_key}" href="{mbar_href or href}"{mbar_current}>'
            f'{_icon("user", "v2-i v2-mbar__icon")}<span class="v2-mbar__label">{mbar_label}</span></a>'
            f"</template>"
        )
        return header, mmenu, mbar

    login_blocks = auth_block("login", "/login/", "Войти", "Регистрация", "login", mbar_href="/register/")
    account_blocks = auth_block("account", "/account/", "Кабинет", "Профиль", "account")
    auth_header = login_blocks[0] + account_blocks[0]
    auth_mmenu = login_blocks[1] + account_blocks[1]
    auth_mbar = login_blocks[2] + account_blocks[2]

    return f"""<header class="v2-header" data-v2-header>
  <div class="v2-header__inner v2-container">
    <a class="v2-header__brand" href="/" aria-label="Surpriz — на главную">
      <img class="v2-header__logo" src="{LOGO_URL}" alt="Surpriz — студия детских праздников" width="662" height="603">
      <span class="v2-header__word">СЮРПРИЗ</span>
    </a>
    <nav class="v2-header__nav" aria-label="Основная навигация">
        {nav_links}
    </nav>
    <div class="v2-header__actions">
      <a class="v2-header__phone" href="{PHONE_TEL}" aria-label="Позвонить: {PHONE_DISPLAY}">{_icon("phone")}<span>{PHONE_DISPLAY}</span></a>
      {auth_header}
      <a class="v2-btn v2-btn--primary v2-btn--md v2-header__cta" href="/party-builder/">{_icon("party-hat")}<span>Собрать праздник</span></a>
      <button class="v2-header__burger" type="button" data-v2-burger aria-label="Открыть меню" aria-expanded="false" aria-controls="v2-mmenu">
        <span class="v2-header__burger-line"></span>
        <span class="v2-header__burger-line"></span>
        <span class="v2-header__burger-line"></span>
      </button>
    </div>
  </div>
</header>
<div class="v2-mmenu" id="v2-mmenu" data-v2-mmenu aria-hidden="true" inert>
  <div class="v2-mmenu__inner">
    <nav class="v2-mmenu__nav" aria-label="Мобильная навигация">
        {mmenu_links}
    </nav>
    <div class="v2-mmenu__contacts">
      <a class="v2-mmenu__phone" href="{PHONE_TEL}">{_icon("phone")}<span>{PHONE_DISPLAY}</span></a>
      <a class="v2-mmenu__tg" href="{TELEGRAM_URL}" target="_blank" rel="noopener">{_icon("telegram")}<span>@Animator_Surpriz</span></a>
      {auth_mmenu}
    </div>
    <a class="v2-btn v2-btn--primary v2-btn--lg v2-mmenu__cta" href="/party-builder/">{_icon("party-hat")}<span>Собрать праздник</span></a>
  </div>
</div>
<nav class="v2-mbar" data-v2-mbar aria-label="Быстрая навигация">
  <a class="v2-mbar__item{' is-active' if active == 'home' else ''}" href="/">{_icon("home", "v2-i v2-mbar__icon")}<span class="v2-mbar__label">Главная</span></a>
  <a class="v2-mbar__item{' is-active' if active == 'shows' else ''}" href="/show-programs/">{_icon("sparkles", "v2-i v2-mbar__icon")}<span class="v2-mbar__label">Шоу</span></a>
  <a class="v2-mbar__item v2-mbar__item--cta{' is-active' if active == 'builder' else ''}" href="/party-builder/"><span class="v2-mbar__cta-circle">{_icon("plus", "v2-i v2-mbar__icon")}</span><span class="v2-mbar__label">Собрать</span></a>
  <a class="v2-mbar__item{' is-active' if active == 'catalog' else ''}" href="/catalog/">{_icon("mask", "v2-i v2-mbar__icon")}<span class="v2-mbar__label">Герои</span></a>
  {auth_mbar}
</nav>"""


def build_footer_html() -> str:
    return build_site_footer_html()


def build_body_prefix_html() -> str:
    """Skip link + inline SVG icon sprite (same-document <use href="#i-...">)."""
    return (
        '<a class="v2-skip" href="#content">Перейти к содержимому</a>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" style="position:absolute;width:0;height:0;overflow:hidden" aria-hidden="true" focusable="false">'
        + _icons_sprite_inner()
        + "</svg>"
    )


#: Карточка организации для поисковиков. Цифры сверены с базой и сайтом:
#: год основания и часы работы взяты с /o-nas/, «предоплаты нет» — с /prices/.
#: Маркетинговые «150+ костюмов» сюда намеренно не попали: в structured data это
#: превращается в заявление, которое опровергается страницей каталога.
LOCAL_BUSINESS_JSONLD = """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "EntertainmentBusiness",
  "@id": "https://animator-surpriz.uz/#business",
  "name": "\u0421\u044e\u0440\u043f\u0440\u0438\u0437",
  "alternateName": "Surpriz",
  "url": "https://animator-surpriz.uz/",
  "logo": "https://animator-surpriz.uz/surpriz/assets/original/logo.png",
  "image": "https://animator-surpriz.uz/surpriz/assets/img/show-programs/hero-desktop.webp",
  "description": "\u041e\u0440\u0433\u0430\u043d\u0438\u0437\u0430\u0446\u0438\u044f \u0434\u0435\u0442\u0441\u043a\u0438\u0445 \u043f\u0440\u0430\u0437\u0434\u043d\u0438\u043a\u043e\u0432 \u0432 \u0422\u0430\u0448\u043a\u0435\u043d\u0442\u0435 \u0441 2017 \u0433\u043e\u0434\u0430: \u0430\u043d\u0438\u043c\u0430\u0442\u043e\u0440\u044b, \u0448\u043e\u0443-\u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u044b, \u0432\u0435\u0434\u0443\u0449\u0438\u0439 \u0438 \u0434\u0438\u0434\u0436\u0435\u0439 \u043f\u043e\u0434 \u043a\u043b\u044e\u0447.",
  "telephone": "+998998926565",
  "foundingDate": "2017",
  "priceRange": "$$",
  "currenciesAccepted": "UZS",
  "openingHoursSpecification": [{
    "@type": "OpeningHoursSpecification",
    "dayOfWeek": ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"],
    "opens": "09:00",
    "closes": "21:00"
  }],
  "address": {
    "@type": "PostalAddress",
    "addressLocality": "\u0422\u0430\u0448\u043a\u0435\u043d\u0442",
    "addressCountry": "UZ"
  },
  "areaServed": [
    { "@type": "City", "name": "\u0422\u0430\u0448\u043a\u0435\u043d\u0442" },
    { "@type": "AdministrativeArea", "name": "\u0422\u0430\u0448\u043a\u0435\u043d\u0442\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c" }
  ],
  "sameAs": [
    "https://www.instagram.com/animator.surpriz/",
    "https://t.me/Animator_Surpriz"
  ]
}
</script>"""


#: Conversion events for GA4. Contact clicks are caught by delegation, so they
#: keep working for markup rendered later; the builder calls surprizStep itself.
CONVERSION_EVENTS_HTML = """<script>
(function () {
  function ev(name, params) {
    if (typeof gtag === 'function') gtag('event', name, params || {});
  }

  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a');
    if (!a) return;
    var href = a.getAttribute('href') || '';
    if (href.indexOf('tel:') === 0) {
      ev('click_phone', { link_url: href, page_path: location.pathname });
    } else if (href.indexOf('t.me/') > -1) {
      ev('click_telegram', { link_url: href, page_path: location.pathname });
    } else if (href.indexOf('instagram.com') > -1) {
      ev('click_instagram', { link_url: href, page_path: location.pathname });
    }
  }, true);

  var STEP_NAMES = { 1: 'show', 2: 'heroes', 3: 'date', 4: 'details', 5: 'address', 6: 'checkout' };
  var seenSteps = {};
  window.surprizStep = function (step, extra) {
    // Без currency GA4 не берёт value в отчёты, и в Google Ads конверсия
    // приходит с нулевой ценностью.
    var params = Object.assign({
      step_number: step,
      step_name: STEP_NAMES[step] || String(step),
      currency: 'UZS'
    }, extra || {});
    ev('builder_step', params);
    // Steps are revisited with Back, and a repeated builder_start would inflate
    // the funnel, so the once-per-visit events fire only the first time.
    if (step === 1 && !seenSteps[1]) ev('builder_start', {});
    if (step === 6 && !seenSteps[6]) ev('begin_checkout', params);
    seenSteps[step] = true;
  };

  window.surprizLead = function (data) {
    data = data || {};
    ev('generate_lead', {
      currency: 'UZS',
      value: data.value || 0,
      transaction_id: data.order_id || '',
      program: data.program || '',
      characters: data.characters || ''
    });
  };
})();
</script>"""


def build_body_suffix_html() -> str:
    return (
        f'<script src="/surpriz/navigation.js?v={_landing_asset_version("navigation.js")}" defer></script>\n'
        f'<script src="/v2/v2.js?v={_asset_version("v2/v2.js")}" defer></script>'
    )


def personalize(html_text: str, is_authenticated: bool) -> str:
    """Resolve <template data-v2-auth="login|account"> blocks for the current session."""
    want = "account" if is_authenticated else "login"

    def _keep(match: re.Match[str]) -> str:
        return match.group(2) if match.group(1) == want else ""

    return _AUTH_TEMPLATE_RE.sub(_keep, html_text)


def render_v2_page(
    content_html: str,
    *,
    title: str,
    description: str,
    canonical_path: str,
    og_image: str = "",
    active: str = "",
    route: str = "",
    extra_head_html: str = "",
    extra_body_class: str = "",
    lang: str = "ru",
) -> PageBundle:
    """Assemble a full v2 page bundle in one call (used by view functions)."""
    canonical = canonical_path if canonical_path.startswith("/") else f"/{canonical_path.lstrip('/')}"
    account_shell_class = "v2-account-shell" if active == "account" else ""
    # Detail pages keep their v2 content but wear the landing chrome, whose header
    # is taller than the v2 one — the class carries that offset.
    landing_shell_class = "v2-landing-shell" if active in {"catalog", "shows"} else ""
    body_class = f"{V2_BODY_CLASS} {extra_body_class} {account_shell_class} {landing_shell_class}".strip()
    shell_css = ""
    if active in _LANDING_SHELL_ROUTES:
        shell_css = f'<link rel="stylesheet" href="/surpriz/styles.css?v={_landing_asset_version("styles.css")}">'
    if active == "builder":
        shell_css += f'\n<link rel="stylesheet" href="/surpriz/assets/party-builder.css?v={_landing_asset_version("assets/party-builder.css")}">'
    detail_skin_css = ""
    if active in {"catalog", "shows"}:
        detail_skin_css = f'<link rel="stylesheet" href="/surpriz/assets/detail-page.css?v={_landing_asset_version("assets/detail-page.css")}">'
    return PageBundle(
        route=route or canonical,
        title=title,
        lang=lang,
        body_class=body_class,
        head_html=build_head_html(
            title,
            description,
            canonical,
            og_image,
            extra_head_html=f"{extra_head_html}\n{shell_css}".strip(),
            after_v2_css_html=detail_skin_css,
        ),
        body_prefix_html=build_body_prefix_html(),
        header_html=build_header_html(active=active),
        content_html=content_html,
        footer_html=_profile_shell_footer_html() if active in _LANDING_SHELL_ROUTES else build_footer_html(),
        body_suffix_html=build_body_suffix_html(),
    )
