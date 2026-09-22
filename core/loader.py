from __future__ import annotations

import json
import html as html_lib
import os
import re
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Callable

from bs4 import BeautifulSoup

from .admin_store import get_public_settings
from .config import ROUTES_ROOT, STATIC_ROOT
from .routing import route_bundle_path


@dataclass(frozen=True)
class PageBundle:
    route: str
    title: str
    lang: str
    body_class: str
    head_html: str
    body_prefix_html: str
    header_html: str
    content_html: str
    footer_html: str
    body_suffix_html: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig") if path.exists() else ""


SNOW_STYLE_RE = re.compile(
    r"<style\b[^>]*>(?:(?!</style>).)*?\.snow-container(?:(?!</style>).)*?</style>",
    re.IGNORECASE | re.DOTALL,
)
SNOW_SCRIPT_RE = re.compile(
    r"<script\b[^>]*>(?:(?!</script>).)*?snowContainer\.className\s*=\s*['\"]snow-container['\"](?:(?!</script>).)*?</script>",
    re.IGNORECASE | re.DOTALL,
)
PROTECTED_BLOCK_RE = re.compile(r"(<script\b.*?</script>|<style\b.*?</style>)", re.IGNORECASE | re.DOTALL)
HTML_TAG_RE = re.compile(r"(<[^>]+>)", re.DOTALL)
UL_RE = re.compile(r"(<ul\b[^>]*>)(.*?)(</ul>)", re.IGNORECASE | re.DOTALL)
LI_BLOCK_RE = re.compile(r"\s*<li\b.*?</li>\s*", re.IGNORECASE | re.DOTALL)
PRODUCTS_UL_RE = re.compile(
    r'(<ul\b[^>]*class="[^"]*\bproducts\b[^"]*"[^>]*>)(.*?)(</ul>)',
    re.IGNORECASE | re.DOTALL,
)
INSTAGRAM_WIDGET_RE = re.compile(
    r'<a\b[^>]*href="https://www\.instagram\.com/(?:event_surpriz|animator\.surpriz)/?"[^>]*>\s*'
    r'(?:(?!</a>).)*?social_media_label-1-1(?:(?!</a>).)*?</a>',
    re.IGNORECASE | re.DOTALL,
)
PRICE_LIST_LINK_RE = re.compile(
    r'<li>\s*<a\b[^>]*class="([^"]*\belementor-price-list-item\b[^"]*)"[^>]*>(.*?)</a>\s*</li>',
    re.IGNORECASE | re.DOTALL,
)
LINK_ASSET_TAG_RE = re.compile(r'<link\b[^>]*href=(["\'])(?P<url>[^"\']+)\1[^>]*>\s*', re.IGNORECASE)
SCRIPT_ASSET_TAG_RE = re.compile(
    r'<script\b[^>]*src=(["\'])(?P<url>[^"\']+)\1[^>]*>\s*</script>\s*',
    re.IGNORECASE | re.DOTALL,
)
ROCKET_BEACON_INLINE_RE = re.compile(
    r'<script\b[^>]*>\s*var rocket_beacon_data\s*=.*?</script>\s*',
    re.IGNORECASE | re.DOTALL,
)
MANAGED_WOO_EXTRA_INLINE_RE = re.compile(
    r'<script\b[^>]*id="(?:wc-add-to-cart-js-extra|wc-single-product-js-extra|wc-order-attribution-js-extra|astra-single-product-ajax-cart-js-extra)"[^>]*>.*?</script>\s*',
    re.IGNORECASE | re.DOTALL,
)
SHOW_TABS_TELEGRAM_BINDING_RE = re.compile(
    r"<script\b[^>]*>(?:(?!</script>).)*?\.js-tabs-scroll \.elementor-widget-button a(?:(?!</script>).)*?tg://resolve\?phone=998998926565(?:(?!</script>).)*?</script>\s*",
    re.IGNORECASE | re.DOTALL,
)
FOOTER_NAV_WIDGET_MARKER = 'data-id="f530b2d"'
FOOTER_PROMO_COLUMN_MARKER = 'data-id="09f65f6"'
MANAGED_HEAD_ASSET_HINTS = (
    "/wp-content/plugins/woocommerce/assets/css/photoswipe/photoswipe.min.css",
    "/wp-content/plugins/woocommerce/assets/css/photoswipe/default-skin/default-skin.min.css",
    "/wp-content/plugins/elementor-pro/assets/css/widget-woocommerce-product-images.min.css",
    "/wp-content/plugins/elementor-pro/assets/css/widget-woocommerce-products.min.css",
    "/wp-content/plugins/woocommerce/assets/client/blocks/wc-blocks.css",
    "/wp-content/plugins/elementor-pro/assets/css/widget-form.min.css",
    "/wp-content/plugins/elementor-pro/assets/css/widget-loop-carousel.min.css",
    "/wp-content/plugins/elementor-pro/assets/css/widget-gallery.min.css",
    "/wp-content/plugins/elementor-pro/assets/css/widget-nested-carousel.min.css",
    "/wp-content/plugins/elementor-pro/assets/css/widget-price-list.min.css",
    "/wp-content/plugins/elementor-pro/assets/css/conditionals/popup.min.css",
    "/wp-content/plugins/elementor-pro/assets/css/conditionals/transitions.min.css",
    "/wp-content/plugins/elementor/assets/lib/animations/styles/fadeInDown.min.css",
    "/wp-content/plugins/elementor/assets/lib/animations/styles/slideInRight.min.css",
    "/wp-content/plugins/elementor/assets/lib/animations/styles/e-animation-pulse-grow.min.css",
    "/wp-content/plugins/elementor/assets/lib/e-gallery/css/e-gallery.min.css",
    "/wp-content/plugins/elementor/assets/css/conditionals/e-swiper.min.css",
    "/wp-content/plugins/elementor/assets/css/conditionals/shapes.min.css",
    "/wp-content/plugins/elementor/assets/css/widget-image.min.css",
    "/wp-content/plugins/elementor/assets/css/widget-divider.min.css",
    "/wp-content/plugins/woocommerce/assets/css/brands.css",
    "/wp-content/plugins/elementor/assets/lib/swiper/v8/css/swiper.min.css",
    "/wp-content/uploads/elementor/css/custom-widget-nested-tabs.min.css",
)
MANAGED_BODY_SCRIPT_HINTS = (
    "/wp-includes/js/comment-reply.min.js",
    "/wp-content/plugins/woocommerce/assets/js/jquery-blockui/jquery.blockUI.min.js",
    "/wp-content/plugins/woocommerce/assets/js/frontend/add-to-cart.min.js",
    "/wp-content/plugins/woocommerce/assets/js/zoom/jquery.zoom.min.js",
    "/wp-content/plugins/woocommerce/assets/js/photoswipe/photoswipe.min.js",
    "/wp-content/plugins/woocommerce/assets/js/photoswipe/photoswipe-ui-default.min.js",
    "/wp-content/plugins/woocommerce/assets/js/js-cookie/js.cookie.min.js",
    "/wp-content/plugins/woocommerce/assets/js/frontend/single-product.min.js",
    "/wp-content/plugins/woocommerce/assets/js/frontend/woocommerce.min.js",
    "/wp-content/plugins/woocommerce/assets/js/flexslider/jquery.flexslider.min.js",
    "/wp-content/plugins/astra-addon/addons/woocommerce/assets/js/minified/single-product-ajax-cart.min.js",
    "/wp-content/plugins/woocommerce/assets/js/sourcebuster/sourcebuster.min.js",
    "/wp-content/plugins/woocommerce/assets/js/frontend/order-attribution.min.js",
    "/wp-content/plugins/wp-rocket/assets/js/wpr-beacon.min.js",
)
MOJIBAKE_TEXT_REPLACEMENTS = {
    "РЁРѕСѓ-РїСЂРѕРіСЂР°РјРјС‹": "Шоу-программы",
    "РљР°С‚Р°Р»РѕРі РїРµСЂСЃРѕРЅР°Р¶РµР№": "Каталог персонажей",
    "Рћ РЅР°СЃ": "О Нас",
    "Рћ РќР°СЃ": "О Нас",
    "РљРѕРЅС‚Р°РєС‚С‹": "Контакты",
    "Р·Р°СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°С‚СЊСЃСЏ": "Зарегистрироваться",
    "Р—Р°СЂРµРіРёСЃС‚СЂРёСЂРѕРІР°С‚СЊСЃСЏ": "Зарегистрироваться",
    "Р—Р°РєР°Р·Р°С‚СЊ РїСЂР°Р·РґРЅРёРє": "Зарегистрироваться",
    "Р»РёС‡РЅС‹Р№ РєР°Р±РёРЅРµС‚": "Личный кабинет",
    "Р›РёС‡РЅС‹Р№ РєР°Р±РёРЅРµС‚": "Личный кабинет",
}
LEGACY_PUBLIC_URL_REPLACEMENTS = (
    ("/wp-admin/admin-ajax.php", "/forms/submit/"),
    ("/wp-content/", "/_assets/content/"),
    ("/wp-includes/", "/_assets/includes/"),
)
SEASONAL_OVERRIDE_CSS_BASE = """
<style id="seasonal-site-overrides">
:root {
    --site-cta-orange: #F26A20;
    --site-cta-purple: #6c1be3;
}

a[href="/register/"].elementor-button,
a[href="/register/"].elementor-button:visited,
a[href="#prices"].elementor-button,
a[href="#prices"].elementor-button:visited,
a[href="/show-programs/"].elementor-button,
a[href="/show-programs/"].elementor-button:visited {
    background: var(--site-cta-orange) !important;
    border-color: var(--site-cta-orange) !important;
    color: #ffffff !important;
    text-decoration: none !important;
}

a[href="/register/"].elementor-button:hover,
a[href="/register/"].elementor-button:focus,
a[href="/register/"].elementor-button:active,
a[href="#prices"].elementor-button:hover,
a[href="#prices"].elementor-button:focus,
a[href="#prices"].elementor-button:active,
a[href="/show-programs/"].elementor-button:hover,
a[href="/show-programs/"].elementor-button:focus,
a[href="/show-programs/"].elementor-button:active,
a[href^="/party-builder/"].elementor-button,
a[href^="/party-builder/"].elementor-button:visited {
    background: var(--site-cta-purple) !important;
    border-color: var(--site-cta-purple) !important;
    color: #ffffff !important;
    text-decoration: none !important;
}

a[href^="/party-builder/"].elementor-button:hover,
a[href^="/party-builder/"].elementor-button:focus,
a[href^="/party-builder/"].elementor-button:active {
    background: var(--site-cta-orange) !important;
    border-color: var(--site-cta-orange) !important;
    color: #ffffff !important;
    text-decoration: none !important;
}

a[href="/register/"].elementor-button .elementor-button-text,
a[href="/register/"].elementor-button .elementor-button-icon,
a[href="/register/"].elementor-button:visited .elementor-button-text,
a[href="/register/"].elementor-button:hover .elementor-button-text,
a[href="/register/"].elementor-button:focus .elementor-button-text,
a[href="/register/"].elementor-button:active .elementor-button-text,
a[href="#prices"].elementor-button .elementor-button-text,
a[href="#prices"].elementor-button .elementor-button-icon,
a[href="#prices"].elementor-button:visited .elementor-button-text,
a[href="#prices"].elementor-button:hover .elementor-button-text,
a[href="#prices"].elementor-button:focus .elementor-button-text,
a[href="#prices"].elementor-button:active .elementor-button-text,
a[href="/show-programs/"].elementor-button .elementor-button-text,
a[href="/show-programs/"].elementor-button .elementor-button-icon,
a[href="/show-programs/"].elementor-button:visited .elementor-button-text,
a[href="/show-programs/"].elementor-button:hover .elementor-button-text,
a[href="/show-programs/"].elementor-button:focus .elementor-button-text,
a[href="/show-programs/"].elementor-button:active .elementor-button-text,
a[href^="/party-builder/"].elementor-button .elementor-button-text,
a[href^="/party-builder/"].elementor-button .elementor-button-icon,
a[href^="/party-builder/"].elementor-button:visited .elementor-button-text,
a[href^="/party-builder/"].elementor-button:hover .elementor-button-text,
a[href^="/party-builder/"].elementor-button:focus .elementor-button-text,
a[href^="/party-builder/"].elementor-button:active .elementor-button-text {
    color: #ffffff !important;
}

.elementor-button-icon .site-button-icon-svg {
    display: block;
    width: 1em;
    height: 1em;
    fill: currentColor;
}

.elementor-price-list a.elementor-price-list-item,
.elementor-price-list a.elementor-price-list-item:visited,
.elementor-price-list a.elementor-price-list-item:hover,
.elementor-price-list a.elementor-price-list-item:focus {
    color: inherit !important;
    text-decoration: none !important;
}

.elementor-price-list a.elementor-price-list-item {
    pointer-events: none;
    cursor: default;
}

.site-instagram-pill {
    box-sizing: border-box;
    width: min(100%, 200px);
    aspect-ratio: 500 / 179;
    display: inline-block;
    position: relative;
    padding: 0;
    box-shadow: none;
    background: url("/wp-content/uploads/2026/04/instagram-pill-live-reference.png") center / 100% 100% no-repeat;
    color: #c53c94 !important;
    text-decoration: none !important;
    overflow: visible;
}

.site-instagram-pill:hover,
.site-instagram-pill:focus,
.site-instagram-pill:visited {
    color: #c53c94 !important;
    text-decoration: none !important;
}

.site-instagram-pill__bar {
    display: none;
}

.site-instagram-pill__icon {
    display: none;
}

.site-instagram-pill__icon svg {
    width: 54%;
    height: 54%;
}

.site-instagram-pill__track {
    display: none;
}

.site-instagram-pill__text-mask {
    position: absolute;
    z-index: 3;
    left: 35.8%;
    right: 6.7%;
    top: 27%;
    bottom: 25%;
    border-radius: 6px;
    background: #ffffff;
}

.site-instagram-pill__handle {
    position: absolute;
    z-index: 4;
    left: 36.5%;
    top: 50%;
    transform: translateY(-50%);
    font-family: "Rubik", sans-serif;
    font-size: clamp(8.5px, 2.5vw, 12px);
    font-weight: 700;
    line-height: 1;
    letter-spacing: -0.01em;
    white-space: nowrap;
}

.elementor-19606 .elementor-element-109dbd9 > .e-con-inner {
    display: flex !important;
    flex-flow: row wrap !important;
    align-items: center !important;
}

.elementor-19606 .elementor-element-2a9b654,
.elementor-19606 .elementor-element-a7b3099,
.elementor-19606 .elementor-element-e106cac {
    flex: 0 0 100% !important;
    width: 100% !important;
}

.elementor-19606 .elementor-element-fe790b7 {
    box-sizing: border-box !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    flex: 0 1 220px !important;
    width: 220px !important;
    min-height: 76px !important;
    margin: 26px 10px 0 auto !important;
    vertical-align: middle !important;
}

.elementor-19606 .elementor-element-fe790b7 .site-instagram-pill {
    display: block !important;
    width: min(100%, 190px) !important;
    margin: 0 !important;
}

/* Temporary hide of Instagram widget on Contacts page. */
.elementor-348 .elementor-element.elementor-element-18c892b {
    display: none !important;
}

.elementor-19606 .elementor-element-569e686 {
    position: relative !important;
    z-index: 5 !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    flex: 0 1 238px !important;
    width: 238px !important;
    margin: 26px auto 0 10px !important;
    text-align: center !important;
    vertical-align: middle !important;
}

.elementor-19606 .elementor-element-569e686 .elementor-button {
    box-sizing: border-box !important;
    width: 100% !important;
    max-width: 238px !important;
    min-height: 48px !important;
    margin-inline: auto !important;
    padding-inline: 16px !important;
}

.elementor-19606 .elementor-element-569e686 .elementor-button-text {
    font-size: clamp(12px, 2.25vw, 16px) !important;
    letter-spacing: 0.01em !important;
    white-space: nowrap !important;
}

.elementor-19606 .elementor-element-569e686 .elementor-button-icon {
    margin-left: 10px !important;
}

.site-mobile-menu-popup {
    transition: background-color 0.22s ease, opacity 0.22s ease !important;
}

.site-mobile-menu-popup .dialog-widget-content {
    animation: site-mobile-popup-in 0.24s cubic-bezier(0.2, 0.8, 0.2, 1) both;
    transform-origin: right center;
}

.site-mobile-menu-popup.site-mobile-menu-popup--closing {
    opacity: 1 !important;
    pointer-events: none !important;
}

.site-mobile-menu-popup.site-mobile-menu-popup--closing .dialog-widget-content {
    animation: site-mobile-popup-out 0.28s cubic-bezier(0.4, 0, 0.2, 1) both !important;
}

.site-mobile-menu-popup.site-mobile-menu-popup--closing::before {
    opacity: 0 !important;
}

@keyframes site-mobile-popup-in {
    from {
        opacity: 0;
        transform: translateX(24px) scale(0.985);
    }
    to {
        opacity: 1;
        transform: translateX(0) scale(1);
    }
}

@keyframes site-mobile-popup-out {
    from {
        opacity: 1;
        transform: translateX(0) scale(1);
    }
    to {
        opacity: 0;
        transform: translateX(36px) scale(0.975);
    }
}

@media (max-width: 520px) {
    .elementor-19606 .elementor-element-fe790b7,
    .elementor-19606 .elementor-element-569e686 {
        display: flex !important;
        width: 100% !important;
        max-width: 238px !important;
        margin: 18px auto 0 !important;
    }
}

.site-footer-popular {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 15px;
    width: 100%;
}

.site-footer-popular-card,
.site-footer-popular-card:visited,
.site-footer-popular-card:hover,
.site-footer-popular-card:focus {
    display: flex;
    flex-direction: column;
    min-width: 0;
    color: #ffffff !important;
    text-decoration: none !important;
}

.site-footer-popular-card__media {
    display: block;
    width: 100%;
    height: 200px;
    position: relative;
    overflow: hidden;
    border-radius: 15px 15px 0 0;
    background: #ffffff;
}

.site-footer-popular-card__image {
    display: block;
    position: absolute;
    inset: 0;
    width: 100% !important;
    height: 100% !important;
    max-width: none !important;
    object-fit: cover !important;
}

.site-footer-popular-card--ribbon .site-footer-popular-card__image {
    object-position: center 30%;
}

.site-footer-popular-card--cryo .site-footer-popular-card__image {
    object-position: center 24%;
}

.site-footer-popular-card__content {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    min-height: 108px;
    padding: 18px 20px;
    border-radius: 0 0 15px 15px;
    background: #6c1be3;
    transition: color 0.2s ease;
}

.site-footer-popular-card:hover .site-footer-popular-card__content,
.site-footer-popular-card:focus .site-footer-popular-card__content {
    color: #f26a20;
}

.site-footer-popular-card__copy {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
}

.site-footer-popular-card__eyebrow,
.site-footer-popular-card__title,
.site-footer-popular-card__arrow {
    font-family: "Rubik", sans-serif;
}

.site-footer-popular-card__eyebrow {
    font-size: 14px;
    font-weight: 500;
    line-height: 1.15;
    opacity: 0.94;
}

.site-footer-popular-card__title {
    font-size: 25px;
    font-weight: 500;
    line-height: 1;
}

.site-footer-popular-card__arrow {
    flex: 0 0 auto;
    font-size: 34px;
    line-height: 1;
}

@media (max-width: 1366px) {
    .site-footer-popular-card__content {
        min-height: 96px;
        padding: 16px 18px;
    }

    .site-footer-popular-card__title {
        font-size: 22px;
    }
}

@media (max-width: 1024px) {
    .site-footer-popular {
        grid-template-columns: 1fr;
    }

    .site-footer-popular-card__media {
        height: 220px;
    }
}

@media (max-width: 767px) {
    .site-instagram-pill {
        width: min(100%, 200px);
    }

    .site-footer-popular-card__media {
        height: 180px;
    }

    .site-footer-popular-card__content {
        min-height: 86px;
        padding: 14px 16px;
    }

    .site-footer-popular-card__eyebrow {
        font-size: 12px;
    }

    .site-footer-popular-card__title {
        font-size: 18px;
    }

    .site-footer-popular-card__arrow {
        font-size: 28px;
    }
}

/* Stage 3.1: code-driven home funnel, managed shows and mobile public polish. */
.surpriz-image-placeholder,
.surpriz-home-show-card__placeholder {
    box-sizing: border-box;
    display: grid;
    place-items: center;
    align-content: center;
    gap: 0.35rem;
    width: 100%;
    min-height: 180px;
    padding: 1.2rem;
    border: 1px dashed rgba(108, 27, 227, 0.2);
    background:
        radial-gradient(circle at 20% 18%, rgba(255, 199, 42, 0.28), transparent 30%),
        radial-gradient(circle at 82% 20%, rgba(108, 27, 227, 0.16), transparent 28%),
        linear-gradient(135deg, #fff7ef, #ffffff);
    color: #6c1be3;
    text-align: center;
}

.surpriz-image-placeholder span {
    color: #22283a;
    font-family: "Balsamiq Sans", "Rubik", sans-serif;
    font-size: clamp(1.45rem, 4vw, 2.05rem);
    font-weight: 700;
    line-height: 1;
}

.surpriz-image-placeholder small {
    color: #d97835;
    font-family: "Rubik", sans-serif;
    font-size: 0.88rem;
    font-weight: 800;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.surpriz-home-funnel,
.surpriz-home-shows {
    box-sizing: border-box;
    width: min(100% - 32px, 1240px);
    margin: clamp(1.1rem, 3vw, 2rem) auto;
}

.surpriz-home-funnel {
    padding: clamp(1rem, 3vw, 1.5rem);
    border: 1px solid rgba(108, 27, 227, 0.12);
    border-radius: 30px;
    background: linear-gradient(135deg, #fff7ef 0%, #ffffff 50%, #f3ecff 100%);
    box-shadow: 0 18px 42px rgba(35, 18, 80, 0.08);
}

.surpriz-home-funnel__eyebrow,
.surpriz-home-shows__eyebrow {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    min-height: 38px;
    padding: 0 1.05rem;
    border-radius: 999px;
    background: rgba(242, 106, 32, 0.12);
    color: #d97835;
    font-family: "Rubik", sans-serif;
    font-size: 0.84rem;
    font-weight: 900;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

.surpriz-home-funnel h2,
.surpriz-home-shows h2 {
    margin: 0.65rem 0 0;
    color: #22283a;
    font-family: "Balsamiq Sans", "Rubik", sans-serif;
    font-size: clamp(2rem, 4.6vw, 3.3rem);
    line-height: 1.05;
}

.surpriz-home-funnel p,
.surpriz-home-shows__lead {
    max-width: 780px;
    margin: 0.55rem 0 0;
    color: #555b70;
    font-family: "Rubik", sans-serif;
    font-size: clamp(1rem, 1.5vw, 1.1rem);
    line-height: 1.55;
}

.surpriz-home-funnel__actions {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.75rem;
    margin-top: 1.1rem;
}

.surpriz-home-funnel__action {
    display: grid;
    gap: 0.25rem;
    min-width: 0;
    min-height: 92px;
    padding: 1rem;
    border: 1px solid rgba(108, 27, 227, 0.12);
    border-radius: 24px;
    background: #ffffff;
    color: #22283a;
    text-decoration: none !important;
    box-shadow: 0 12px 28px rgba(35, 18, 80, 0.06);
    transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
}

.surpriz-home-funnel__action:hover,
.surpriz-home-funnel__action:focus {
    border-color: rgba(242, 106, 32, 0.36);
    color: #22283a;
    transform: translateY(-2px);
    box-shadow: 0 18px 36px rgba(242, 106, 32, 0.12);
}

.surpriz-home-funnel__number {
    display: inline-grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 999px;
    background: #6c1be3;
    color: #ffffff;
    font-family: "Rubik", sans-serif;
    font-weight: 900;
}

.surpriz-home-funnel__title {
    font-family: "Rubik", sans-serif;
    font-weight: 900;
    line-height: 1.15;
}

.surpriz-home-funnel__hint {
    color: #747684;
    font-family: "Rubik", sans-serif;
    font-size: 0.86rem;
    line-height: 1.35;
}

.surpriz-home-shows {
    padding: clamp(1.15rem, 3vw, 2rem);
    border: 1px solid rgba(108, 27, 227, 0.12);
    border-radius: 34px;
    background:
        radial-gradient(circle at 12% 12%, rgba(255, 199, 42, 0.2), transparent 28%),
        radial-gradient(circle at 85% 20%, rgba(108, 27, 227, 0.12), transparent 32%),
        #ffffff;
    box-shadow: 0 20px 52px rgba(35, 18, 80, 0.08);
}

.surpriz-home-shows__head {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 1.2rem;
    margin-bottom: clamp(1rem, 2vw, 1.4rem);
}

.surpriz-home-shows__all,
.surpriz-home-shows__empty-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 50px;
    padding: 0 1.3rem;
    border-radius: 999px;
    background: #f26a20;
    color: #ffffff !important;
    font-family: "Rubik", sans-serif;
    font-weight: 900;
    text-decoration: none !important;
    white-space: nowrap;
}

.surpriz-home-shows__all--bottom {
    display: none;
}

.surpriz-home-shows__grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: clamp(0.9rem, 2vw, 1.25rem);
}

.surpriz-home-show-card {
    display: flex;
    flex-direction: column;
    min-width: 0;
    overflow: hidden;
    border: 1px solid rgba(64, 56, 90, 0.12);
    border-radius: 28px;
    background: #ffffff;
    box-shadow: 0 16px 38px rgba(35, 18, 80, 0.08);
}

.surpriz-home-show-card__media {
    display: block;
    aspect-ratio: 16 / 10;
    overflow: hidden;
    background: #fff7ef;
}

.surpriz-home-show-card__media img,
.surpriz-home-show-card__media .surpriz-image-placeholder {
    display: grid;
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.surpriz-home-show-card__body {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 0.7rem;
    padding: 1rem;
}

.surpriz-home-show-card h3 {
    margin: 0;
    color: #22283a;
    font-family: "Balsamiq Sans", "Rubik", sans-serif;
    font-size: clamp(1.4rem, 2.2vw, 1.75rem);
    line-height: 1.08;
}

.surpriz-home-show-card h3 a {
    color: inherit !important;
    text-decoration: none !important;
}

.surpriz-home-show-card__badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
}

.surpriz-home-show-card__price,
.surpriz-home-show-card__duration {
    display: inline-flex;
    align-items: center;
    min-height: 32px;
    padding: 0 0.8rem;
    border-radius: 999px;
    font-family: "Rubik", sans-serif;
    font-size: 0.9rem;
    font-weight: 900;
    line-height: 1;
}

.surpriz-home-show-card__price {
    background: #f9eadf;
    color: #b66a26;
}

.surpriz-home-show-card__duration {
    background: #f0e8ff;
    color: #4d2ab3;
}

.surpriz-home-show-card__badges .surpriz-promo-badge {
    display: inline-flex;
    align-items: center;
    max-width: 100%;
    min-height: 24px;
    padding: 0 9px;
    border-radius: 999px;
    border: 1px solid rgba(184, 145, 63, 0.52);
    background: linear-gradient(135deg, #fff1bf 0%, #f3d879 52%, #dbb24c 100%);
    color: #4a3208;
    font-family: "Rubik", sans-serif;
    font-size: 11px;
    font-weight: 800;
    line-height: 1.3;
    white-space: normal;
    overflow-wrap: anywhere;
    word-break: break-word;
    box-shadow: 0 2px 10px rgba(164, 120, 35, 0.2);
    flex: 0 1 auto;
}

.surpriz-home-show-card__badges .surpriz-promo-badge:empty {
    display: none;
}

.surpriz-home-show-card p {
    display: -webkit-box;
    margin: 0;
    overflow: hidden;
    color: #5b5d68;
    font-family: "Rubik", sans-serif;
    line-height: 1.48;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 3;
}

.surpriz-home-show-card__actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.55rem;
    margin-top: auto;
}

.surpriz-home-show-card__button {
    box-sizing: border-box;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 0;
    min-height: 46px;
    padding: 0 0.9rem;
    border-radius: 999px;
    background: #f26a20;
    color: #ffffff !important;
    font-family: "Rubik", sans-serif;
    font-size: 0.92rem;
    font-weight: 900;
    line-height: 1;
    text-align: center;
    text-decoration: none !important;
    white-space: nowrap;
}

.surpriz-home-show-card__button--ghost {
    border: 2px solid #f26a20;
    background: #ffffff;
    color: #dc7133 !important;
}

.surpriz-home-shows__empty {
    display: grid;
    gap: 0.8rem;
    padding: 1.25rem;
    border: 1px dashed rgba(108, 27, 227, 0.22);
    border-radius: 24px;
    background: rgba(255, 255, 255, 0.74);
}

@media (max-width: 980px) {
    .surpriz-home-funnel__actions,
    .surpriz-home-shows__grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 767px) {
    body,
    .site {
        overflow-x: clip !important;
    }

    .surpriz-home-funnel,
    .surpriz-home-shows {
        width: calc(100% - 28px);
        margin-block: 1rem;
        border-radius: 26px;
    }

    .surpriz-home-funnel {
        margin-top: 0.85rem;
    }

    .surpriz-home-funnel__actions,
    .surpriz-home-shows__grid {
        grid-template-columns: minmax(0, 1fr);
    }

    .surpriz-home-funnel__action {
        min-height: 78px;
        grid-template-columns: auto minmax(0, 1fr);
        align-items: center;
        column-gap: 0.75rem;
    }

    .surpriz-home-funnel__hint {
        grid-column: 2;
    }

    .surpriz-home-shows__head {
        align-items: stretch;
        flex-direction: column;
    }

    .surpriz-home-shows__head .surpriz-home-shows__all {
        display: none;
    }

    .surpriz-home-shows__all--bottom {
        display: flex;
        width: 100%;
        margin-top: 1.4rem;
    }

    .surpriz-home-shows__all {
        width: 100%;
    }

    .surpriz-home-show-card__media {
        aspect-ratio: 4 / 3;
    }

    .surpriz-home-show-card__body {
        gap: 0.55rem;
        padding: 0.95rem 1rem 1.05rem;
    }

    .surpriz-home-show-card p {
        -webkit-line-clamp: 2;
        margin-bottom: 0.15rem;
    }

    .surpriz-home-show-card__actions {
        grid-template-columns: 1fr 1fr;
        gap: 0.5rem;
        margin-top: 0.35rem;
    }

    .surpriz-home-show-card__button {
        min-height: 44px;
        padding: 0 0.7rem;
        font-size: 0.86rem;
        letter-spacing: 0.01em;
    }

    .surpriz-home-show-card__button--ghost {
        border-width: 1.5px;
    }

    .elementor-348 .elementor-element.elementor-element-d0ea588 {
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-start !important;
        gap: 10px !important;
        position: relative !important;
        z-index: 3 !important;
    }

    .elementor-348 .elementor-element.elementor-element-e3bbe0c > .e-con-inner {
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-start !important;
        gap: 14px !important;
    }

    .elementor-348 .elementor-element.elementor-element-b501c90 {
        position: relative !important;
        z-index: 1 !important;
        width: 100% !important;
        max-width: 100% !important;
        margin: 12px 0 0 !important;
    }

    .elementor-348 .elementor-element.elementor-element-b501c90 iframe {
        display: block !important;
        width: 100% !important;
        max-width: 100% !important;
        height: 300px !important;
    }

    .elementor-348 .elementor-element.elementor-element-18c892b,
    .elementor-348 .elementor-element.elementor-element-7c0e212 {
        display: block !important;
        position: static !important;
        inset: auto !important;
        margin: 0 !important;
        width: fit-content !important;
        max-width: 100% !important;
        transform: none !important;
        z-index: 4 !important;
    }

    .elementor-348 .elementor-element.elementor-element-18c892b .site-instagram-pill {
        width: min(100%, 194px) !important;
        margin: 0 !important;
    }

    .elementor-348 .elementor-element.elementor-element-7c0e212 .elementor-button {
        display: inline-flex !important;
        width: auto !important;
        max-width: 100% !important;
    }

    .elementor-348 .elementor-element.elementor-element-7c0e212 {
        margin-top: 10px !important;
    }

    .elementor-location-footer .elementor-element-555a4e4 {
        margin: 0 14px 18px !important;
        padding: 18px 16px !important;
        border-radius: 24px !important;
    }

    .elementor-location-footer .elementor-element-1d0a992 .elementor-heading-title {
        font-size: 30px !important;
        line-height: 1 !important;
    }

    .elementor-location-footer .elementor-element-d95a1ca p {
        margin-bottom: 0 !important;
        font-size: 15px !important;
        line-height: 1.4 !important;
    }

    .elementor-location-footer .elementor-element-13f8257 {
        display: none !important;
    }

    .elementor-location-footer .elementor-element-1973ab2,
    .elementor-location-footer .elementor-element-1973ab2 > .e-con-inner {
        padding-top: 24px !important;
        padding-bottom: 24px !important;
    }

    .elementor-location-footer .site-footer-popular-card__media {
        display: none !important;
    }

    .elementor-location-footer .site-footer-popular-card__content {
        min-height: 56px !important;
        border-radius: 18px !important;
    }
}

/* Stage 3.3: code-driven footer and calmer public home sections. */
.surpriz-home-funnel {
    display: none !important;
}

.surpriz-home-shows {
    background:
        linear-gradient(180deg, rgba(255, 253, 249, 0.98) 0%, rgba(250, 246, 255, 0.9) 100%),
        #ffffff !important;
}

.surpriz-site-footer {
    box-sizing: border-box;
    position: relative;
    margin-top: 28px;
    padding: calc(clamp(2rem, 4vw, 3.2rem) + 14px) 0 1rem;
    overflow: visible;
    isolation: isolate;
    background:
        radial-gradient(circle at 14% 10%, rgba(242, 106, 32, 0.09), transparent 28%),
        radial-gradient(circle at 88% 12%, rgba(108, 27, 227, 0.08), transparent 30%),
        linear-gradient(180deg, #fffaf5 0%, #f7f1ff 100%);
    color: #232131;
}

.surpriz-site-footer::before {
    content: "";
    position: absolute;
    z-index: 0;
    top: -30px;
    left: 0;
    right: 0;
    height: 44px;
    pointer-events: none;
    background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1440 80' preserveAspectRatio='none'%3E%3Cpath fill='%23fffaf5' d='M0 28 C160 58 330 5 520 28 C720 52 910 70 1120 30 C1240 8 1340 22 1440 38 L1440 80 L0 80 Z'/%3E%3Cpath fill='none' stroke='%23eadcfb' stroke-width='3' d='M0 30 C160 60 330 7 520 30 C720 54 910 72 1120 32 C1240 10 1340 24 1440 40'/%3E%3C/svg%3E") center top / 100% 100% no-repeat;
}

.surpriz-site-footer *,
.surpriz-site-footer *::before,
.surpriz-site-footer *::after {
    box-sizing: border-box;
}

.surpriz-site-footer a {
    color: inherit;
    text-decoration: none !important;
}

.surpriz-site-footer a:hover,
.surpriz-site-footer a:focus {
    color: #df7634;
}

.surpriz-site-footer__inner {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(210px, 1.15fr) minmax(150px, 0.78fr) minmax(150px, 0.78fr) minmax(190px, 0.95fr) minmax(210px, 1fr);
    gap: clamp(1.2rem, 3vw, 2rem);
    width: min(100% - 32px, 1240px);
    margin: 0 auto;
}

.surpriz-site-footer__brand,
.surpriz-site-footer__section {
    display: grid;
    align-content: start;
    gap: 0.85rem;
    min-width: 0;
}

.surpriz-site-footer__logo {
    display: inline-flex;
    align-items: center;
    width: fit-content;
}

.surpriz-site-footer__logo img {
    display: block;
    width: 92px;
    height: auto;
}

.surpriz-site-footer__brand-name {
    color: #22283a;
    font-family: "Balsamiq Sans", "Rubik", sans-serif;
    font-size: 1.35rem;
    font-weight: 700;
    line-height: 1;
}

.surpriz-site-footer__brand p,
.surpriz-site-footer__bottom,
.surpriz-site-footer__hint {
    color: #66606f;
    font-family: "Rubik", sans-serif;
    font-size: 0.95rem;
    line-height: 1.55;
}

.surpriz-site-footer__title {
    display: inline-grid;
    gap: 0.42rem;
    width: fit-content;
    margin: 0;
    color: #22283a;
    font-family: "Balsamiq Sans", "Rubik", sans-serif;
    font-size: clamp(1.35rem, 2vw, 1.65rem);
    line-height: 1;
}

.surpriz-site-footer__title::after {
    content: "";
    display: block;
    width: min(92px, 100%);
    height: 4px;
    border-radius: 999px;
    background: linear-gradient(90deg, #f26a20 0%, #6c1be3 100%);
    opacity: 0.9;
}

.surpriz-site-footer__links {
    display: grid;
    gap: 0.55rem;
    margin: 0;
    padding: 0;
    list-style: none;
}

.surpriz-site-footer__links a,
.surpriz-site-footer__contact {
    display: inline-flex;
    align-items: center;
    width: fit-content;
    min-height: 34px;
    color: #272431;
    font-family: "Rubik", sans-serif;
    font-weight: 800;
    line-height: 1.2;
}

.surpriz-site-footer__contact--phone {
    color: #6c1be3;
    font-size: 1.08rem;
}

.surpriz-site-footer__actions {
    display: grid;
    gap: 0.7rem;
}

.surpriz-site-footer__button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 46px;
    padding: 0 1rem;
    border: 2px solid rgba(108, 27, 227, 0.16);
    border-radius: 999px;
    background: #ffffff;
    color: #4d2ab3 !important;
    font-family: "Rubik", sans-serif;
    font-weight: 900;
    text-align: center;
    box-shadow: 0 10px 26px rgba(53, 27, 125, 0.08);
    transition: border-color 0.2s ease, box-shadow 0.2s ease, color 0.2s ease, background-color 0.2s ease, transform 0.2s ease;
}

.surpriz-site-footer__button--ghost {
    background: #ffffff;
    color: #4d2ab3 !important;
}

.surpriz-site-footer__button:hover,
.surpriz-site-footer__button:focus {
    border-color: rgba(242, 106, 32, 0.38);
    color: #df7634 !important;
    transform: translateY(-1px);
}

.surpriz-site-footer__button.is-active {
    border-color: #f26a20;
    background: #f26a20;
    color: #ffffff !important;
    box-shadow: 0 14px 30px rgba(242, 106, 32, 0.2);
}

.surpriz-site-footer__button.is-active:hover,
.surpriz-site-footer__button.is-active:focus {
    color: #ffffff !important;
}

.surpriz-site-footer__popular {
    display: grid;
    gap: 0.55rem;
}

.surpriz-site-footer__popular a {
    display: grid;
    gap: 0.15rem;
    padding: 0.75rem 0.85rem;
    border: 1px solid rgba(108, 27, 227, 0.12);
    border-radius: 18px;
    background: rgba(255, 255, 255, 0.76);
    box-shadow: 0 12px 24px rgba(53, 27, 125, 0.05);
}

.surpriz-site-footer__popular strong {
    color: #22283a;
    font-family: "Rubik", sans-serif;
    font-size: 0.98rem;
    font-weight: 900;
    line-height: 1.2;
}

.surpriz-site-footer__popular span {
    color: #777281;
    font-family: "Rubik", sans-serif;
    font-size: 0.84rem;
    font-weight: 700;
    line-height: 1.3;
}

.surpriz-site-footer__bottom {
    position: relative;
    z-index: 1;
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 0.7rem 1rem;
    width: min(100% - 32px, 1240px);
    margin: clamp(1.5rem, 3vw, 2rem) auto 0;
    padding-top: 1rem;
    border-top: 1px solid rgba(108, 27, 227, 0.12);
}

@media (max-width: 1024px) {
    .surpriz-site-footer__inner {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 640px) {
    .surpriz-site-footer {
        padding-top: calc(1.5rem + 12px);
    }

    .surpriz-site-footer__inner {
        grid-template-columns: 1fr 1fr;
        column-gap: 1rem;
        row-gap: 1.4rem;
        width: calc(100% - 28px);
    }

    .surpriz-site-footer__brand {
        grid-column: 1 / -1;
    }

    .surpriz-site-footer__section[aria-label="Навигация"] {
        order: 1;
        grid-column: 1 / 2;
    }

    .surpriz-site-footer__section[aria-label="Контакты"] {
        order: 2;
        grid-column: 2 / 3;
    }

    .surpriz-site-footer__section[aria-label="Быстрые действия"] {
        order: 3;
        grid-column: 1 / -1;
        justify-items: center;
        text-align: center;
    }

    .surpriz-site-footer__section[aria-label="Быстрые действия"] .surpriz-site-footer__title {
        margin-left: auto;
        margin-right: auto;
    }

    .surpriz-site-footer__section[aria-label="Быстрые действия"] .surpriz-site-footer__actions {
        width: 100%;
        max-width: 360px;
        margin: 0 auto;
    }

    .surpriz-site-footer__brand,
    .surpriz-site-footer__section {
        gap: 0.7rem;
    }

    .surpriz-site-footer__logo img {
        width: 78px;
    }

    .surpriz-site-footer__button {
        width: 100%;
    }

    .surpriz-site-footer__bottom {
        width: calc(100% - 28px);
        flex-direction: column;
        text-align: center;
        gap: 0.5rem;
    }

    .surpriz-site-footer__popular {
        display: none;
    }

    .surpriz-site-footer__section--popular {
        display: none;
    }
}
</style>
""".strip()
SEASONAL_LINKS = ("/character-category/new-year/", "/character-tag/novyj-god/")
SEASONAL_PRODUCT_MARKERS = ("product_cat-new-year", "product_tag-novyj-god")
INSTAGRAM_URL_REPLACEMENTS = (
    "https://www.instagram.com/event_surpriz/",
    "https://www.instagram.com/event_surpriz",
)
NEW_INSTAGRAM_URL = "https://www.instagram.com/animator.surpriz/"
OLD_INSTAGRAM_HANDLE = "@event_surpriz"
NEW_INSTAGRAM_HANDLE = "@animator.surpriz"
SITE_PHONE_DISPLAY = "+998 (99) 892-65-65"
SITE_PHONE_TEL = "+998998926565"
SITE_TELEGRAM_URL = "https://t.me/Animator_Surpriz"
SITE_LOGO_URL = "/wp-content/uploads/2025/06/logo.png"
ACCOUNT_ICON_SVG = """
<svg aria-hidden="true" class="site-button-icon-svg" focusable="false" viewBox="0 0 448 512">
<path d="M224 256A128 128 0 1 0 224 0a128 128 0 1 0 0 256zm89.6 32h-16.7c-22.2 10.2-46.9 16-72.9 16s-50.6-5.8-72.9-16h-16.7C60.2 288 0 348.2 0 422.4V464c0 26.5 21.5 48 48 48h352c26.5 0 48-21.5 48-48v-41.6C448 348.2 387.8 288 313.6 288z"/>
</svg>
""".strip()
PRICE_LIST_ICON_SVG = """
<svg aria-hidden="true" class="site-button-icon-svg" focusable="false" viewBox="0 0 448 512">
<path d="M207 381.5 12.7 187.1c-9.4-9.4-9.4-24.6 0-33.9l22.6-22.6c9.4-9.4 24.6-9.4 33.9 0L224 285.3l154.7-154.7c9.4-9.4 24.6-9.4 33.9 0l22.6 22.6c9.4 9.4 9.4 24.6 0 33.9L241 381.5c-9.4 9.4-24.6 9.4-34 0z"/>
</svg>
""".strip()
LONG_ARROW_LEFT_ICON_SVG = """
<svg aria-hidden="true" class="site-button-icon-svg" focusable="false" viewBox="0 0 448 512">
<path d="M9.4 233.4c-12.5 12.5-12.5 32.8 0 45.3l160 160c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L109.2 288H416c17.7 0 32-14.3 32-32s-14.3-32-32-32H109.2L214.6 118.6c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0l-160 160z"/>
</svg>
""".strip()
LONG_ARROW_RIGHT_ICON_SVG = """
<svg aria-hidden="true" class="site-button-icon-svg" focusable="false" viewBox="0 0 448 512">
<path d="M438.6 278.6c12.5-12.5 12.5-32.8 0-45.3l-160-160c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3L338.8 224H32c-17.7 0-32 14.3-32 32s14.3 32 32 32h306.8L233.4 393.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0l160-160z"/>
</svg>
""".strip()
CHEVRON_LEFT_ICON_SVG = """
<svg aria-hidden="true" class="site-button-icon-svg" focusable="false" viewBox="0 0 320 512">
<path d="M9.4 233.4c-12.5 12.5-12.5 32.8 0 45.3l192 192c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L77.3 256 246.6 86.6c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0l-192 192z"/>
</svg>
""".strip()
CHEVRON_RIGHT_ICON_SVG = """
<svg aria-hidden="true" class="site-button-icon-svg" focusable="false" viewBox="0 0 320 512">
<path d="M310.6 233.4c12.5 12.5 12.5 32.8 0 45.3l-192 192c-12.5 12.5-32.8 12.5-45.3 0s-12.5-32.8 0-45.3L242.7 256 73.4 86.6c-12.5-12.5-12.5-32.8 0-45.3s32.8-12.5 45.3 0l192 192z"/>
</svg>
""".strip()
MENU_ICON_SVG = """
<svg aria-hidden="true" class="site-button-icon-svg" focusable="false" viewBox="0 0 448 512">
<path d="M0 96c0-17.7 14.3-32 32-32h384c17.7 0 32 14.3 32 32s-14.3 32-32 32H32C14.3 128 0 113.7 0 96zm0 160c0-17.7 14.3-32 32-32h384c17.7 0 32 14.3 32 32s-14.3 32-32 32H32c-17.7 0-32-14.3-32-32zm448 160c0 17.7-14.3 32-32 32H32c-17.7 0-32-14.3-32-32s14.3-32 32-32h384c17.7 0 32 14.3 32 32z"/>
</svg>
""".strip()
MINUS_ICON_SVG = """
<svg aria-hidden="true" class="site-button-icon-svg" focusable="false" viewBox="0 0 448 512">
<path d="M432 256c0 17.7-14.3 32-32 32H48c-17.7 0-32-14.3-32-32s14.3-32 32-32h352c17.7 0 32 14.3 32 32z"/>
</svg>
""".strip()
PLAY_CIRCLE_ICON_SVG = """
<svg aria-hidden="true" class="site-button-icon-svg" focusable="false" viewBox="0 0 512 512">
<path d="M371.7 238 197.9 133.7c-21.3-12.8-49.9 2.5-49.9 27.5v189.6c0 25 28.6 40.3 49.9 27.5L371.7 274c20.8-12.5 20.8-49.5 0-62zM256 8C119 8 8 119 8 256s111 248 248 248 248-111 248-248S393 8 256 8zm0 448c-110.5 0-200-89.5-200-200S145.5 56 256 56s200 89.5 200 200-89.5 200-200 200z"/>
</svg>
""".strip()
INSTAGRAM_PILL_HTML = f"""
<a class="site-instagram-pill" href="{NEW_INSTAGRAM_URL}" rel="noopener noreferrer" target="_blank">
<span aria-hidden="true" class="site-instagram-pill__text-mask"></span>
<span class="site-instagram-pill__handle">{NEW_INSTAGRAM_HANDLE}</span>
</a>
""".strip()
FOOTER_POPULAR_HTML = """
<div class="elementor-element elementor-element-09f65f6 e-con-full e-flex e-con e-child" data-element_type="container" data-id="09f65f6">
<div class="elementor-element elementor-element-a007c22 elementor-widget elementor-widget-heading" data-element_type="widget" data-id="a007c22" data-widget_type="heading.default">
<span class="elementor-heading-title elementor-size-default">Популярные:</span> </div>
<div class="site-footer-popular">
<a class="site-footer-popular-card site-footer-popular-card--ribbon" href="/show-programs/ribbon-show/">
<span class="site-footer-popular-card__media">
<img alt="Ленточное шоу" class="site-footer-popular-card__image" loading="lazy" src="/wp-content/uploads/2025/10/1F5A0328-1-1200x1800.webp"/>
</span>
<span class="site-footer-popular-card__content">
<span class="site-footer-popular-card__copy">
<span class="site-footer-popular-card__eyebrow">Шоу-программа</span>
<span class="site-footer-popular-card__title">Ленточное шоу</span>
</span>
<span aria-hidden="true" class="site-footer-popular-card__arrow">→</span>
</span>
</a>
<a class="site-footer-popular-card site-footer-popular-card--cryo" href="/show-programs/cryo-show/">
<span class="site-footer-popular-card__media">
<img alt="Крио шоу" class="site-footer-popular-card__image" loading="lazy" src="/wp-content/uploads/2025/10/IMG_5941-1200x2134.webp"/>
</span>
<span class="site-footer-popular-card__content">
<span class="site-footer-popular-card__copy">
<span class="site-footer-popular-card__eyebrow">Шоу-программа</span>
<span class="site-footer-popular-card__title">Крио шоу</span>
</span>
<span aria-hidden="true" class="site-footer-popular-card__arrow">→</span>
</span>
</a>
</div>
</div>
""".strip()
SHOW_TABS_SWIPER_FIX_SCRIPT = """
<script id="site-show-tabs-swiper-fix">
(() => {
  const WIDGET_SELECTOR = '.e-n-tabs-content .elementor-widget-n-carousel';

  const toNumber = (value, fallback) => {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const getSettingSize = (settings, key, fallback) => {
    const value = settings?.[key];
    if (value && typeof value === 'object') {
      return toNumber(value.size, fallback);
    }
    return toNumber(value, fallback);
  };

  const getSwiperOptions = (widget) => {
    let settings = {};
    try {
      settings = JSON.parse(widget.getAttribute('data-settings') || '{}');
    } catch (error) {
      console.warn('site-show-tabs-swiper-fix: settings parse failed', error);
    }

    const paginationEl = widget.querySelector('.swiper-pagination');
    const prevEl = widget.querySelector('.elementor-swiper-button-prev');
    const nextEl = widget.querySelector('.elementor-swiper-button-next');
    const gapDesktop = getSettingSize(settings, 'image_spacing_custom', 10);

    return {
      loop: settings.infinite === 'yes',
      speed: toNumber(settings.speed, 500),
      slidesPerView: toNumber(settings.slides_to_show_mobile, 1),
      spaceBetween: getSettingSize(settings, 'image_spacing_custom_mobile', gapDesktop),
      watchOverflow: true,
      observer: true,
      observeParents: true,
      updateOnWindowResize: true,
      navigation: prevEl && nextEl ? { prevEl, nextEl } : undefined,
      pagination: paginationEl ? { el: paginationEl, clickable: true } : undefined,
      breakpoints: {
        768: {
          slidesPerView: toNumber(settings.slides_to_show_tablet, 2),
          spaceBetween: getSettingSize(settings, 'image_spacing_custom_tablet', gapDesktop),
        },
        1025: {
          slidesPerView: toNumber(settings.slides_to_show_laptop || settings.slides_to_show, 3),
          spaceBetween: getSettingSize(settings, 'image_spacing_custom_laptop', gapDesktop),
        },
        1367: {
          slidesPerView: toNumber(settings.slides_to_show, 3),
          spaceBetween: gapDesktop,
        },
      },
    };
  };

  const ensureWidget = (widget) => {
    const carousel = widget.querySelector('.e-n-carousel.swiper');
    if (!carousel) {
      return;
    }

    if (carousel.swiper && typeof carousel.swiper.update === 'function') {
      carousel.swiper.update();
      return;
    }

    if (typeof window.Swiper === 'undefined' || carousel.classList.contains('swiper-initialized')) {
      return;
    }

    try {
      const swiper = new window.Swiper(carousel, getSwiperOptions(widget));
      requestAnimationFrame(() => swiper.update());
    } catch (error) {
      console.warn('site-show-tabs-swiper-fix: init failed', error);
    }
  };

  const refresh = () => {
    document.querySelectorAll(WIDGET_SELECTOR).forEach(ensureWidget);
  };

  const scheduleRefresh = () => {
    refresh();
    setTimeout(refresh, 120);
    setTimeout(refresh, 600);
    setTimeout(refresh, 1500);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', scheduleRefresh, { once: true });
  } else {
    scheduleRefresh();
  }

  window.addEventListener('load', scheduleRefresh);
  window.addEventListener('resize', () => setTimeout(refresh, 120));
  document.addEventListener('click', (event) => {
    if (event.target.closest('.e-n-tab-title')) {
      setTimeout(scheduleRefresh, 120);
    }
  });
})();
</script>
""".strip()
MOBILE_MENU_POPUP_FIX_SCRIPT = """
<script id="site-mobile-menu-popup-fix">
(() => {
  const popupId = 19606;
  const triggerSelector = 'a.elementor-icon[href^="#elementor-action"][href*="popup%3Aopen"], a.elementor-icon[href^="#elementor-action"][href*="popup:open"]';
  const popupSelector = '.elementor-popup-modal';
  const popupContentSelector = '.elementor-19606';
  let savedScrollY = 0;
  let isClosing = false;
  let isScrollLocked = false;
  let previousBodyStyle = null;
  let closeWatchTimer = null;

  const currentScrollY = () => window.scrollY || document.documentElement.scrollTop || document.body.scrollTop || 0;

  const openPopup = (trigger) => {
    const popupModule = window.elementorProFrontend?.modules?.popup;
    if (popupModule?.showPopup) {
      popupModule.showPopup({ id: popupId, toggle: false }, trigger);
      return true;
    }
    return false;
  };

  const findMenuPopup = () => {
    return Array.from(document.querySelectorAll(popupSelector)).find((popup) => popup.querySelector(popupContentSelector)) || null;
  };

  const closePopup = (popup, event) => {
    const popupDocument = window.elementorFrontend?.documentsManager?.documents?.[popupId];
    const modal = popupDocument?.getModal?.();
    if (modal?.hide) {
      modal.hide();
      return;
    }
    const popupModule = window.elementorProFrontend?.modules?.popup;
    const contentTarget = popup?.querySelector(popupContentSelector);
    if (popupModule?.closePopup && contentTarget) {
      popupModule.closePopup({}, { target: contentTarget });
      return;
    }
    popup?.querySelector('.dialog-close-button')?.click?.();
    if (popup) {
      popup.style.display = 'none';
    }
  };

  const restoreScroll = () => {
    window.scrollTo(0, savedScrollY);
  };

  const lockPageScroll = () => {
    if (isScrollLocked) {
      return;
    }
    previousBodyStyle = {
      position: document.body.style.position,
      top: document.body.style.top,
      left: document.body.style.left,
      right: document.body.style.right,
      width: document.body.style.width,
      overflow: document.body.style.overflow,
    };
    document.body.style.position = 'fixed';
    document.body.style.top = `-${savedScrollY}px`;
    document.body.style.left = '0';
    document.body.style.right = '0';
    document.body.style.width = '100%';
    document.body.style.overflow = 'hidden';
    isScrollLocked = true;
  };

  const unlockPageScroll = () => {
    if (!isScrollLocked) {
      restoreScroll();
      return;
    }
    const targetScrollY = savedScrollY;
    document.body.style.position = previousBodyStyle?.position || '';
    document.body.style.top = previousBodyStyle?.top || '';
    document.body.style.left = previousBodyStyle?.left || '';
    document.body.style.right = previousBodyStyle?.right || '';
    document.body.style.width = previousBodyStyle?.width || '';
    document.body.style.overflow = previousBodyStyle?.overflow || '';
    previousBodyStyle = null;
    isScrollLocked = false;
    document.body.classList.remove('dialog-prevent-scroll');
    window.scrollTo(0, targetScrollY);
  };

  const scheduleRestore = () => {
    requestAnimationFrame(restoreScroll);
    window.setTimeout(restoreScroll, 0);
    window.setTimeout(restoreScroll, 80);
    window.setTimeout(restoreScroll, 220);
    window.setTimeout(restoreScroll, 520);
    window.setTimeout(restoreScroll, 900);
  };

  const markMenuPopup = () => {
    const popup = findMenuPopup();
    if (popup) {
      popup.classList.add('site-mobile-menu-popup');
    }
    return popup;
  };

  const schedulePopupSetup = () => {
    window.setTimeout(markMenuPopup, 0);
    window.setTimeout(markMenuPopup, 90);
    window.setTimeout(markMenuPopup, 240);
  };

  const stopCloseWatch = () => {
    if (closeWatchTimer) {
      window.clearInterval(closeWatchTimer);
      closeWatchTimer = null;
    }
  };

  const startCloseWatch = () => {
    stopCloseWatch();
    closeWatchTimer = window.setInterval(() => {
      const popup = findMenuPopup();
      const isVisible = popup && getComputedStyle(popup).display !== 'none' && popup.offsetParent !== null;
      if (!isVisible && isScrollLocked) {
        stopCloseWatch();
        unlockPageScroll();
        scheduleRestore();
      }
    }, 160);
  };

  const finishClose = (popup, event) => {
    closePopup(popup, event);
    window.setTimeout(() => {
      popup?.classList.remove('site-mobile-menu-popup--closing');
      isClosing = false;
      stopCloseWatch();
      unlockPageScroll();
      scheduleRestore();
    }, 40);
  };

  const animateClose = (event, popup) => {
    if (!popup || isClosing) {
      return false;
    }
    isClosing = true;
    savedScrollY = savedScrollY || currentScrollY();
    event?.preventDefault?.();
    event?.stopPropagation?.();
    event?.stopImmediatePropagation?.();
    popup.classList.add('site-mobile-menu-popup', 'site-mobile-menu-popup--closing');
    window.setTimeout(() => finishClose(popup, event), 280);
    return true;
  };

  const closeIntentPopup = (event) => {
    const target = event.target;
    if (!(target instanceof Element)) {
      return null;
    }
    const closeButton = target.closest('.elementor-popup-modal .dialog-close-button');
    if (closeButton) {
      const popup = closeButton.closest(popupSelector);
      return popup?.querySelector(popupContentSelector) ? popup : null;
    }
    const popup = target.closest(popupSelector);
    if (!popup || !popup.querySelector(popupContentSelector)) {
      return null;
    }
    const clickedInsideContent = Boolean(target.closest('.dialog-widget-content'));
    return clickedInsideContent ? null : popup;
  };

  document.addEventListener('pointerdown', (event) => {
    if (!event.target.closest(triggerSelector)) {
      return;
    }
    savedScrollY = currentScrollY();
  }, true);

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest(triggerSelector);
    if (!trigger) {
      return;
    }
    savedScrollY = currentScrollY();
    isClosing = false;
    const canOpenPopup = Boolean(window.elementorProFrontend?.modules?.popup?.showPopup);
    if (canOpenPopup) {
      lockPageScroll();
    }
    if (openPopup(trigger)) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
    } else if (canOpenPopup) {
      unlockPageScroll();
    }
    schedulePopupSetup();
    scheduleRestore();
    startCloseWatch();
  }, true);

  window.addEventListener('click', (event) => {
    const popup = closeIntentPopup(event);
    if (!popup) {
      return;
    }
    animateClose(event, popup);
  }, true);

  window.addEventListener('keyup', (event) => {
    if (event.key !== 'Escape') {
      return;
    }
    const popup = findMenuPopup();
    if (popup && getComputedStyle(popup).display !== 'none') {
      animateClose(event, popup);
    }
  }, true);

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', markMenuPopup, { once: true });
  } else {
    markMenuPopup();
  }
})();
</script>
""".strip()
VIDEO_LIGHTBOX_FALLBACK_BLOCK = """
<style id="site-video-lightbox-fallback-style">
#site-video-lightbox-fallback {
  position: fixed;
  inset: 0;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(12, 10, 20, 0.76);
  backdrop-filter: blur(4px);
  z-index: 2147483645;
}
#site-video-lightbox-fallback.is-visible {
  display: flex;
}
#site-video-lightbox-fallback .site-video-lightbox-fallback__dialog {
  position: relative;
  width: min(420px, calc(100vw - 18px));
  border-radius: 18px;
  overflow: hidden;
  background: #000;
  box-shadow: 0 24px 56px rgba(0, 0, 0, 0.5);
}
#site-video-lightbox-fallback .site-video-lightbox-fallback__video {
  display: block;
  width: 100%;
  height: auto;
  aspect-ratio: 9 / 16;
  max-height: 80vh;
  background: #000;
}
#site-video-lightbox-fallback .site-video-lightbox-fallback__close {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  background: rgba(12, 10, 20, 0.7);
  font: 700 22px/1 "Rubik", sans-serif;
  cursor: pointer;
}
</style>
<script id="site-video-lightbox-fallback-script">
(() => {
  const MODAL_ID = 'site-video-lightbox-fallback';
  let modal = null;
  let videoNode = null;
  let previousBodyOverflow = '';

  const decodeBase64Url = (value) => {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized + '==='.slice((normalized.length + 3) % 4);
    return window.atob(padded);
  };

  const safeDecodeURIComponent = (value) => {
    try {
      return decodeURIComponent(value);
    } catch (_) {
      return value;
    }
  };

  const parseSettings = (rawValue, fallbackRawAction) => {
    if (!rawValue && !fallbackRawAction) {
      return null;
    }
    const candidates = [];
    if (rawValue) {
      candidates.push(rawValue, safeDecodeURIComponent(rawValue));
    }
    if (fallbackRawAction) {
      candidates.push(fallbackRawAction, safeDecodeURIComponent(fallbackRawAction));
    }

    for (const candidate of candidates) {
      try {
        return JSON.parse(candidate);
      } catch (_) {
        // try base64 decode below
      }
      try {
        return JSON.parse(decodeBase64Url(candidate));
      } catch (_) {
        const match = candidate.match(/"url"\\s*:\\s*"([^"]+\\.mp4[^"]*)"/i);
        if (match) {
          return { type: "video", url: match[1] };
        }
      }
    }
    return null;
  };

  const normalizeVideoUrl = (rawUrl) => {
    if (!rawUrl) {
      return "";
    }
    const unescaped = rawUrl.split("\\/").join("/");
    try {
      const parsed = new URL(unescaped, window.location.origin);
      if (parsed.pathname.startsWith("/wp-content/")) {
        return `/_assets/content${parsed.pathname.slice("/wp-content".length)}${parsed.search}`;
      }
      return parsed.toString();
    } catch (_) {
      return unescaped;
    }
  };

  const closeModal = () => {
    if (!modal || !videoNode) {
      return;
    }
    videoNode.pause();
    videoNode.removeAttribute('src');
    videoNode.load();
    modal.classList.remove('is-visible');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = previousBodyOverflow;
  };

  const ensureModal = () => {
    if (modal && videoNode) {
      return;
    }

    modal = document.createElement('div');
    modal.id = MODAL_ID;
    modal.setAttribute('aria-hidden', 'true');

    const dialog = document.createElement('div');
    dialog.className = 'site-video-lightbox-fallback__dialog';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-label', 'Видео');

    const closeButton = document.createElement('button');
    closeButton.type = 'button';
    closeButton.className = 'site-video-lightbox-fallback__close';
    closeButton.setAttribute('aria-label', 'Закрыть');
    closeButton.textContent = '×';

    videoNode = document.createElement('video');
    videoNode.className = 'site-video-lightbox-fallback__video';
    videoNode.setAttribute('controls', '');
    videoNode.setAttribute('playsinline', '');
    videoNode.setAttribute('preload', 'metadata');

    dialog.appendChild(closeButton);
    dialog.appendChild(videoNode);
    modal.appendChild(dialog);
    document.body.appendChild(modal);

    modal.addEventListener('click', (event) => {
      if (event.target === modal || event.target === closeButton) {
        closeModal();
      }
    });

    window.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && modal?.classList.contains('is-visible')) {
        closeModal();
      }
    });
  };

  const openModal = (url) => {
    ensureModal();
    previousBodyOverflow = document.body.style.overflow || '';
    document.body.style.overflow = 'hidden';
    videoNode.src = url;
    modal.classList.add('is-visible');
    modal.setAttribute('aria-hidden', 'false');
    videoNode.load();
    const playPromise = videoNode.play();
    if (playPromise && typeof playPromise.catch === 'function') {
      playPromise.catch(() => {});
    }
  };

  const extractVideoUrlFromAction = (href) => {
    if (!href || !href.includes('elementor-action')) {
      return null;
    }
    const decodedHref = safeDecodeURIComponent(href);
    if (!decodedHref.includes('elementor-action:')) {
      return null;
    }
    const actionPart = decodedHref.replace(/^#?elementor-action:/, '');
    const params = new URLSearchParams(safeDecodeURIComponent(actionPart));
    if (params.get('action') !== 'lightbox') {
      return null;
    }
    const settings = parseSettings(params.get('settings'), actionPart);
    if (!settings || settings.type !== 'video') {
      return null;
    }
    return normalizeVideoUrl(settings.url || settings.videoUrl || "");
  };

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('a[href*="elementor-action"]');
    if (!trigger) {
      return;
    }
    const videoUrl = extractVideoUrlFromAction(trigger.getAttribute('href') || '');
    if (!videoUrl) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    openModal(videoUrl);
  }, true);
})();
</script>
""".strip()
MOBILE_MENU_LAYOUT_FINAL_STYLE = """
<style id="site-mobile-menu-layout-final-fix">
#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-109dbd9 > .e-con-inner {
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) !important;
    column-gap: 0 !important;
    align-items: start !important;
    align-content: start !important;
    justify-items: start !important;
}

#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-2a9b654,
#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-a7b3099,
#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-e106cac {
    grid-column: 1 / -1 !important;
    width: 100% !important;
}

#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-fe790b7 {
    grid-column: 1 / -1 !important;
    justify-self: start !important;
    align-self: start !important;
    width: clamp(190px, 36vw, 230px) !important;
    max-width: 230px !important;
    min-width: 0 !important;
    min-height: 0 !important;
    margin: 22px 0 0 !important;
    text-align: left !important;
}

#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-fe790b7 .site-instagram-pill {
    width: 100% !important;
    max-width: 230px !important;
    margin: 0 !important;
}

#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-569e686 {
    grid-column: 1 / -1 !important;
    justify-self: start !important;
    align-self: start !important;
    width: clamp(190px, 36vw, 230px) !important;
    max-width: 230px !important;
    min-width: 0 !important;
    margin: 14px 0 0 !important;
    text-align: left !important;
}

#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-569e686 .elementor-button {
    box-sizing: border-box !important;
    width: 100% !important;
    max-width: 230px !important;
    min-height: 46px !important;
    padding: 13px 14px !important;
    border-radius: 999px !important;
}

#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-569e686 .elementor-button-text {
    font-size: clamp(10px, 2.05vw, 15px) !important;
    line-height: 1 !important;
    white-space: nowrap !important;
}

#elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-569e686 .elementor-button-icon {
    margin-left: 8px !important;
}

@media (max-width: 430px) {
    #elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-109dbd9 > .e-con-inner {
        column-gap: 0 !important;
    }

    #elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-fe790b7 {
        width: 220px !important;
        max-width: min(100%, 220px) !important;
    }

    #elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-569e686 {
        width: 220px !important;
        max-width: min(100%, 220px) !important;
    }

    #elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-569e686 .elementor-button {
        min-height: 44px !important;
        padding: 12px 11px !important;
    }

    #elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-569e686 .elementor-button-text {
        font-size: 13px !important;
        letter-spacing: 0 !important;
    }

    #elementor-popup-modal-19606 .elementor-19606 .elementor-element.elementor-element-569e686 .elementor-button-icon {
        margin-left: 8px !important;
    }
}
</style>
""".strip()


CATALOG_MENU_CATEGORIES = (
    ("/character-category/supergeroi/", "Супергерои", "mask"),
    ("/character-category/multiki/", "Мультики", "tv"),
    ("/character-category/skazochnye/", "Сказочные", "wand"),
    ("/character-category/filmy/", "Фильмы", "clapperboard"),
    ("/character-category/serialy/", "Сериалы", "playlist"),
    ("/character-category/veduschie/", "Ведущие", "mic"),
    ("/character-category/tematicheskie/", "Тематические", "palette"),
    ("/character-tag/malchikam/", "Мальчикам", "rocket"),
    ("/character-tag/devochkam/", "Девочкам", "bow"),
)


CATALOG_MENU_ICON_PATHS = {
    # Superhero mask (Robin / Spider-Man eye-mask shape)
    "mask": '<path d="M3 9c2-2 5-3 9-3s7 1 9 3c-1 4-4 6-9 6s-8-2-9-6z"/><circle cx="9" cy="10" r="1.6" fill="currentColor"/><circle cx="15" cy="10" r="1.6" fill="currentColor"/><path d="M3 9c-1 1-1.5 2-1.5 3"/><path d="M21 9c1 1 1.5 2 1.5 3"/>',
    # TV / cartoon set with antenna
    "tv": '<rect x="3" y="7" width="18" height="12" rx="2"/><path d="M8 4l4 3M16 4l-4 3"/><circle cx="18" cy="11" r="0.8" fill="currentColor"/><path d="M7 11h6M7 14h6"/>',
    # Magic wand with sparkles (fairytale)
    "wand": '<path d="M5 19l10-10"/><path d="M14 8l2 2"/><path d="M18 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/><path d="M5 5l.7 1.3L7 7l-1.3.7L5 9l-.7-1.3L3 7l1.3-.7z"/>',
    # Clapperboard (movies)
    "clapperboard": '<rect x="3" y="9" width="18" height="11" rx="1"/><path d="M3 9l2.5-4 4 1L7 10M9 5l4 1-2.5 4M14 6l4 1-2.5 4"/>',
    # Playlist / TV series episodes
    "playlist": '<rect x="3" y="5" width="14" height="3" rx="1"/><rect x="3" y="11" width="14" height="3" rx="1"/><rect x="3" y="17" width="9" height="3" rx="1"/><path d="M19 6v3l3-1.5z" fill="currentColor"/>',
    # Microphone (host / animator)
    "mic": '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0014 0"/><path d="M12 18v3M9 21h6"/>',
    # Artist palette (themed events)
    "palette": '<path d="M12 3a9 9 0 100 18c1 0 1.5-.7 1.5-1.5 0-.5-.3-.8-.5-1.2-.2-.4-.5-.7-.5-1.2 0-.8.5-1.5 1.5-1.5h2.5a4 4 0 004-4 9 9 0 00-9-9z"/><circle cx="7" cy="9" r="1.2" fill="currentColor"/><circle cx="9" cy="6" r="1.2" fill="currentColor"/><circle cx="14" cy="6" r="1.2" fill="currentColor"/><circle cx="17" cy="9" r="1.2" fill="currentColor"/>',
    # Rocket (boys)
    "rocket": '<path d="M12 3c3 2 5 5 5 9 0 2-1 4-2 5h-6c-1-1-2-3-2-5 0-4 2-7 5-9z"/><circle cx="12" cy="10" r="1.5"/><path d="M9 17c-1 1-2 3-2 4 1-.2 3-1 4-2M15 17c1 1 2 3 2 4-1-.2-3-1-4-2"/>',
    # Hair bow (girls)
    "bow": '<path d="M12 12L4 7v10z"/><path d="M12 12l8-5v10z"/><circle cx="12" cy="12" r="2"/><path d="M11 14l-2 7M13 14l2 7"/>',
    # Legacy keys retained for backward compat
    "crown": '<path d="M3 8l4 4 5-7 5 7 4-4-1 11H4z"/><path d="M5 19h14"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-4 8-8 9-4-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    "castle": '<path d="M3 21V8l3-2 3 2V4l3 2 3-2v4l3-2 3 2v13z"/><path d="M10 21v-5h4v5"/>',
    "film": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 10h18M3 16h18"/>',
    "sparkle": '<path d="M12 3l1.6 5.4L19 10l-5.4 1.6L12 17l-1.6-5.4L5 10l5.4-1.6z"/><path d="M19 4l.5 1.5L21 6l-1.5.5L19 8l-.5-1.5L17 6l1.5-.5z"/>',
    "gamepad": '<path d="M6 11h4M8 9v4"/><circle cx="16" cy="11" r="1"/><circle cx="14" cy="13" r="1"/><rect x="2" y="6" width="20" height="12" rx="6"/>',
    "book": '<path d="M4 4h12a3 3 0 013 3v13H7a3 3 0 01-3-3z"/><path d="M4 17a3 3 0 013-3h12"/>',
    "fairy": '<path d="M12 8a4 4 0 100 8 4 4 0 000-8z"/><path d="M12 4v2M12 18v2M4 12h2M18 12h2M6 6l1.5 1.5M16.5 16.5L18 18M6 18l1.5-1.5M16.5 7.5L18 6"/>',
    "smile": '<circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><circle cx="9" cy="10" r=".7" fill="currentColor"/><circle cx="15" cy="10" r=".7" fill="currentColor"/>',
    "tree": '<path d="M12 3l4 5h-2l3 4h-2l3 5H6l3-5H7l3-4H8z"/><path d="M11 17h2v4h-2z"/>',
    "wave": '<path d="M3 12c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2"/><path d="M3 17c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2"/><path d="M3 7c2 0 2-2 4-2s2 2 4 2 2-2 4-2 2 2 4 2"/>',
    "ball": '<circle cx="12" cy="12" r="9"/><path d="M3.5 9.5l5 1.5 1.5 5M14 4l-1 5 4 3M20.5 14.5L16 13l-1 5"/>',
}


def _build_catalog_menu_dropdown_script() -> str:
    import json as _json
    items_payload = _json.dumps(
        [
            {"href": href, "label": label, "icon": CATALOG_MENU_ICON_PATHS.get(icon_key, "")}
            for href, label, icon_key in CATALOG_MENU_CATEGORIES
        ],
        ensure_ascii=False,
    )
    return """
<style id="site-catalog-menu-dropdown-style">
.menu-item--catalog-dropdown { position: relative; }
.menu-item--catalog-dropdown > .menu-link::before {
  content: none !important;
  background: transparent !important;
  display: none !important;
}
.menu-item--catalog-dropdown > .menu-link::after {
  content: "▾" !important;
  display: inline-block !important;
  margin-left: 6px !important;
  font-size: 0.7em !important;
  opacity: 0.7 !important;
  transition: transform 0.18s ease !important;
  background: transparent !important;
  width: auto !important;
  height: auto !important;
  position: static !important;
  border: 0 !important;
  color: inherit !important;
}
.menu-item--catalog-dropdown:hover > .menu-link::after,
.menu-item--catalog-dropdown.is-open > .menu-link::after {
  transform: rotate(180deg) !important;
}
.surpriz-catalog-dropdown {
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%) translateY(-8px);
  z-index: 9999;
  background: #fff;
  border-radius: 18px;
  padding: 18px;
  box-shadow: 0 24px 60px rgba(53, 27, 125, 0.18), 0 4px 16px rgba(0, 0, 0, 0.08);
  min-width: 480px;
  max-width: 96vw;
  opacity: 0;
  pointer-events: none;
  visibility: hidden;
  transition: opacity 0.18s ease, transform 0.22s cubic-bezier(0.2, 0.8, 0.2, 1), visibility 0s linear 0.18s;
  border: 1px solid rgba(108, 27, 227, 0.08);
  margin-top: 12px;
}
.surpriz-catalog-dropdown::before {
  content: "";
  position: absolute;
  top: -18px;
  left: 0;
  right: 0;
  height: 18px;
}
.menu-item--catalog-dropdown:hover > .surpriz-catalog-dropdown,
.menu-item--catalog-dropdown:focus-within > .surpriz-catalog-dropdown,
.menu-item--catalog-dropdown.is-open > .surpriz-catalog-dropdown,
.surpriz-catalog-dropdown:hover {
  opacity: 1;
  pointer-events: auto;
  visibility: visible;
  transform: translateX(-50%) translateY(0);
  transition: opacity 0.18s ease, transform 0.22s cubic-bezier(0.2, 0.8, 0.2, 1), visibility 0s;
}
.surpriz-catalog-dropdown__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(180px, 1fr));
  gap: 4px;
}
.surpriz-catalog-dropdown__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 12px;
  text-decoration: none;
  color: #2d2839;
  font-size: 0.95rem;
  transition: background 0.16s ease, color 0.16s ease;
  font-family: 'Rubik', sans-serif;
}
.surpriz-catalog-dropdown__item:hover,
.surpriz-catalog-dropdown__item:focus {
  background: linear-gradient(135deg, rgba(108, 27, 227, 0.08), rgba(235, 126, 41, 0.06));
  color: #6c1be3;
}
.surpriz-catalog-dropdown__icon {
  flex: 0 0 auto;
  width: 32px;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(108, 27, 227, 0.06);
  border-radius: 10px;
  color: #6c1be3;
  transition: background 0.16s ease, color 0.16s ease;
}
.surpriz-catalog-dropdown__item:hover .surpriz-catalog-dropdown__icon,
.surpriz-catalog-dropdown__item:focus .surpriz-catalog-dropdown__icon {
  background: rgba(108, 27, 227, 0.14);
  color: #4d10b3;
}
.surpriz-catalog-dropdown__icon svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.surpriz-catalog-dropdown__footer {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(108, 27, 227, 0.1);
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  font-size: 0.9rem;
}
.surpriz-catalog-dropdown__footer a {
  color: #6c1be3;
  font-weight: 600;
  text-decoration: none;
}
.surpriz-catalog-dropdown__footer a:hover {
  text-decoration: underline;
}
@media (max-width: 920px) {
  .surpriz-catalog-dropdown { display: none !important; }
}
</style>
<script id="site-catalog-menu-dropdown">
(() => {
  const CATEGORIES = %%ITEMS_JSON%%;
  const CATALOG_HREF_TARGETS = ["/catalog/", "/catalog"];
  const SVG_NS = "http://www.w3.org/2000/svg";
  const buildIcon = (paths) => {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const tpl = document.createElement("template");
    tpl.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">' + paths + '</svg>';
    const parsed = tpl.content.querySelector('svg');
    if (parsed) {
      parsed.childNodes.forEach((node) => svg.appendChild(node.cloneNode(true)));
    }
    return svg;
  };
  const init = () => {
    const links = document.querySelectorAll('a.menu-link, a.elementor-item');
    let initialized = false;
    links.forEach((link) => {
      const href = (link.getAttribute('href') || '').trim();
      if (!CATALOG_HREF_TARGETS.includes(href)) return;
      const li = link.closest('li');
      if (!li || li.classList.contains('menu-item--catalog-dropdown')) return;
      li.classList.add('menu-item--catalog-dropdown');

      const dropdown = document.createElement('div');
      dropdown.className = 'surpriz-catalog-dropdown';
      dropdown.setAttribute('role', 'menu');

      const grid = document.createElement('div');
      grid.className = 'surpriz-catalog-dropdown__grid';
      CATEGORIES.forEach((item) => {
        const a = document.createElement('a');
        a.className = 'surpriz-catalog-dropdown__item';
        a.href = item.href;
        a.setAttribute('role', 'menuitem');
        const icon = document.createElement('span');
        icon.className = 'surpriz-catalog-dropdown__icon';
        icon.setAttribute('aria-hidden', 'true');
        if (item.icon) icon.appendChild(buildIcon(item.icon));
        const label = document.createElement('span');
        label.textContent = item.label;
        a.appendChild(icon);
        a.appendChild(label);
        grid.appendChild(a);
      });
      dropdown.appendChild(grid);

      const footer = document.createElement('div');
      footer.className = 'surpriz-catalog-dropdown__footer';
      const allLink = document.createElement('a');
      allLink.href = '/catalog/';
      allLink.textContent = 'Все персонажи →';
      const showsLink = document.createElement('a');
      showsLink.href = '/show-programs/';
      showsLink.textContent = 'Шоу-программы →';
      footer.appendChild(showsLink);
      footer.appendChild(allLink);
      dropdown.appendChild(footer);

      li.appendChild(dropdown);

      // Close-on-leave with grace period
      let closeTimer;
      const open = () => { clearTimeout(closeTimer); li.classList.add('is-open'); };
      const close = () => { clearTimeout(closeTimer); li.classList.remove('is-open'); };
      const scheduleClose = () => {
        clearTimeout(closeTimer);
        closeTimer = setTimeout(() => li.classList.remove('is-open'), 220);
      };
      li.addEventListener('mouseenter', open);
      li.addEventListener('mouseleave', scheduleClose);
      dropdown.addEventListener('mouseenter', open);
      dropdown.addEventListener('mouseleave', scheduleClose);
      // Touch toggle: первый тап по «Каталог» — открыть dropdown; повторный — перейти.
      link.addEventListener('click', (event) => {
        if (!matchMedia('(hover: none)').matches) return;
        if (!li.classList.contains('is-open')) {
          event.preventDefault();
          open();
        }
      });
      // Click outside / focusout → close (надёжно на тач и desktop).
      document.addEventListener('click', (event) => {
        if (!li.classList.contains('is-open')) return;
        if (li.contains(event.target)) return;
        close();
      });
      document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && li.classList.contains('is-open')) close();
      });
      // Закрыть при клике на пункт dropdown (чтобы он не торчал после перехода в SPA-like среде).
      dropdown.addEventListener('click', (event) => {
        if (event.target.closest('a')) close();
      });

      initialized = true;
    });
    return initialized;
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
</script>
""".strip().replace("%%ITEMS_JSON%%", items_payload)


CATALOG_MENU_DROPDOWN_SCRIPT = _build_catalog_menu_dropdown_script()




INSPECT_OVERLAY_BLOCK = r"""
<style id="surpriz-inspect-overlay-style">
#surpriz-inspect-overlay,#surpriz-inspect-overlay *{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
#surpriz-inspect-overlay{position:fixed;inset:0;pointer-events:none;z-index:2147483640}
#surpriz-inspect-toolbar{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);display:flex;gap:8px;align-items:center;padding:8px;background:#0b0b10;border:1px solid #2a2a35;border-radius:14px;box-shadow:0 12px 40px rgba(0,0,0,.45);pointer-events:auto;z-index:2147483647;font-size:13px;color:#fff}
#surpriz-inspect-toolbar button{display:inline-flex;align-items:center;gap:6px;padding:8px 12px;background:#1a1a25;color:#fff;border:1px solid #2a2a35;border-radius:9px;cursor:pointer;font-size:13px;line-height:1;transition:.12s}
#surpriz-inspect-toolbar button:hover:not(:disabled){background:#23232f;border-color:#3a3a47}
#surpriz-inspect-toolbar button.is-active{background:#7c5cff;border-color:#7c5cff}
#surpriz-inspect-toolbar button.swp-primary{background:#7c5cff;border-color:#7c5cff}
#surpriz-inspect-toolbar button.swp-primary:hover:not(:disabled){background:#6a48ff;border-color:#6a48ff}
#surpriz-inspect-toolbar button:disabled{opacity:.45;cursor:not-allowed}
#surpriz-inspect-toolbar .swp-count{display:inline-flex;align-items:center;justify-content:center;min-width:30px;height:30px;padding:0 9px;background:#1a1a25;border:1px solid #2a2a35;border-radius:9px;color:#cfcfe0;font-variant-numeric:tabular-nums;font-weight:600}
#surpriz-inspect-hover-box{position:fixed;pointer-events:none;border:2px solid #7c5cff;background:rgba(124,92,255,.12);border-radius:4px;transition:all .04s linear;z-index:2147483641}
#surpriz-inspect-hover-label{position:fixed;pointer-events:none;background:#7c5cff;color:#fff;padding:3px 8px;border-radius:6px;font-size:11px;line-height:1.3;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;white-space:nowrap;z-index:2147483642;box-shadow:0 4px 12px rgba(0,0,0,.3)}
.swp-pin-box{position:absolute;pointer-events:none;border:2px solid #ff2d8a;border-radius:4px;z-index:2147483641}
.swp-pin-box.is-empty{border-color:#7c5cff;border-style:dashed}
.swp-pin-num{position:absolute;width:28px;height:28px;border-radius:50%;background:#ff2d8a;color:#fff;font-size:13px;font-weight:700;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 12px rgba(255,45,138,.45),0 0 0 3px #fff;cursor:pointer;pointer-events:auto;z-index:2147483643;font-variant-numeric:tabular-nums;transition:transform .1s;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.swp-pin-num:hover{transform:scale(1.15)}
.swp-pin-num.is-empty{background:#7c5cff;box-shadow:0 4px 12px rgba(124,92,255,.45),0 0 0 3px #fff}
#surpriz-inspect-panel{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);width:min(560px,calc(100vw - 32px));max-height:calc(100vh - 64px);background:#0b0b10;border:1px solid #2a2a35;border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.55);pointer-events:auto;z-index:2147483647;display:flex;flex-direction:column;overflow:hidden}
#surpriz-inspect-panel header{padding:14px 16px;border-bottom:1px solid #1f1f2a;display:flex;align-items:center;gap:10px;color:#fff}
#surpriz-inspect-panel header .swp-title{font-weight:600;font-size:15px}
#surpriz-inspect-panel header .swp-spacer{flex:1}
#surpriz-inspect-panel header .swp-x{background:transparent;border:0;color:#cfcfe0;font-size:20px;cursor:pointer;padding:4px 10px;border-radius:6px;line-height:1}
#surpriz-inspect-panel header .swp-x:hover{background:#1a1a25;color:#fff}
#surpriz-inspect-panel .swp-body{padding:14px 16px;display:flex;flex-direction:column;gap:10px;overflow:auto}
.swp-pin-row{display:flex;flex-direction:column;gap:6px;padding:10px;background:#11111a;border:1px solid #1f1f2a;border-radius:10px}
.swp-pin-row.is-current{border-color:#7c5cff;box-shadow:0 0 0 1px #7c5cff inset}
.swp-pin-head{display:flex;align-items:center;gap:8px;color:#fff;font-size:13px}
.swp-pin-head .swp-pin-badge{display:inline-flex;align-items:center;justify-content:center;width:24px;height:24px;border-radius:50%;background:#ff2d8a;color:#fff;font-size:12px;font-weight:700;flex-shrink:0}
.swp-pin-head .swp-pin-sel{flex:1;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#cfcfe0;background:#15151f;border:1px solid #1f1f2a;padding:5px 8px;border-radius:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.swp-pin-head .swp-pin-del{background:transparent;border:0;color:#9090a8;cursor:pointer;font-size:16px;padding:4px 8px;border-radius:6px;line-height:1}
.swp-pin-head .swp-pin-del:hover{background:#1a1a25;color:#ef4444}
#surpriz-inspect-panel textarea{width:100%;min-height:64px;background:#15151f;color:#fff;border:1px solid #2a2a35;border-radius:8px;padding:8px 10px;font-size:13px;line-height:1.45;resize:vertical;outline:none;font-family:inherit}
#surpriz-inspect-panel textarea:focus{border-color:#7c5cff}
#surpriz-inspect-panel footer{padding:12px 16px;border-top:1px solid #1f1f2a;display:flex;gap:8px;justify-content:space-between;align-items:center;background:#0b0b10;flex-wrap:wrap}
#surpriz-inspect-panel footer .swp-foot-left{color:#9090a8;font-size:12px}
#surpriz-inspect-panel footer button{padding:9px 14px;background:#1a1a25;color:#fff;border:1px solid #2a2a35;border-radius:9px;cursor:pointer;font-size:13px}
#surpriz-inspect-panel footer button.swp-primary{background:#7c5cff;border-color:#7c5cff}
#surpriz-inspect-panel footer button.swp-primary:hover:not(:disabled){background:#6a48ff}
#surpriz-inspect-panel footer button:disabled{opacity:.5;cursor:not-allowed}
#surpriz-inspect-toast{position:fixed;left:50%;top:24px;transform:translateX(-50%);padding:10px 16px;background:#22c55e;color:#fff;border-radius:10px;font-size:13px;z-index:2147483647;box-shadow:0 8px 24px rgba(0,0,0,.3);pointer-events:none;opacity:0;transition:opacity .2s}
#surpriz-inspect-toast.is-show{opacity:1}
#surpriz-inspect-toast.is-error{background:#ef4444}
@media (max-width:520px){#surpriz-inspect-toolbar{bottom:90px;padding:6px;font-size:12px}#surpriz-inspect-toolbar button{padding:7px 10px}}
</style>
<div id="surpriz-inspect-overlay" aria-hidden="true">
  <div id="surpriz-inspect-toolbar" role="toolbar" aria-label="Surpriz inspect">
    <button type="button" id="swp-pick" title="Выбрать элементы (клик — добавить метку, Esc — выйти)">⌖ Pick</button>
    <span class="swp-count" id="swp-count" title="Сколько меток">0</span>
    <button type="button" id="swp-review" class="swp-primary" title="Открыть список меток">Готово</button>
    <button type="button" id="swp-clear" title="Удалить все метки">↺</button>
  </div>
</div>
<script id="surpriz-inspect-overlay-script">
(function(){
  if (window.__surprizInspectInit) return;
  window.__surprizInspectInit = true;
  var overlay = document.getElementById('surpriz-inspect-overlay');
  var pickBtn = document.getElementById('swp-pick');
  var countEl = document.getElementById('swp-count');
  var reviewBtn = document.getElementById('swp-review');
  var clearBtn = document.getElementById('swp-clear');
  var picking = false;
  var hoverBox = null, hoverLabel = null, panelEl = null, toastEl = null;
  var pins = [];
  var pinSeq = 0;

  function el(tag, props, children){
    var n = document.createElement(tag);
    if (props) Object.keys(props).forEach(function(k){
      if (k === 'style' && typeof props[k] === 'object') Object.assign(n.style, props[k]);
      else if (k === 'on' && typeof props[k] === 'object') Object.keys(props[k]).forEach(function(ev){ n.addEventListener(ev, props[k][ev]); });
      else if (k in n) n[k] = props[k];
      else n.setAttribute(k, props[k]);
    });
    (children||[]).forEach(function(c){ if (c == null) return; n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
    return n;
  }

  function shouldSkip(t){
    if (!t) return true;
    if (t === overlay || overlay.contains(t)) return true;
    if (t.id && t.id.indexOf('surpriz-inspect') === 0) return true;
    if (panelEl && (t === panelEl || panelEl.contains(t))) return true;
    if (t.classList && (t.classList.contains('swp-pin-num') || t.classList.contains('swp-pin-box'))) return true;
    return false;
  }

  function describe(t){
    if (!t) return '';
    var s = t.tagName.toLowerCase();
    if (t.id) s += '#' + t.id;
    if (t.classList && t.classList.length) s += '.' + Array.from(t.classList).slice(0,3).join('.');
    return s;
  }

  function uniqueSelector(t){
    if (!t || !t.tagName) return '';
    if (t.id) return '#' + t.id;
    var parts = [];
    var cur = t;
    while (cur && cur.nodeType === 1 && cur !== document.body && parts.length < 6) {
      var part = cur.tagName.toLowerCase();
      if (cur.classList && cur.classList.length) part += '.' + Array.from(cur.classList).slice(0,2).join('.');
      var parent = cur.parentElement;
      if (parent) {
        var sib = Array.from(parent.children).filter(function(c){return c.tagName === cur.tagName;});
        if (sib.length > 1) part += ':nth-of-type(' + (sib.indexOf(cur)+1) + ')';
      }
      parts.unshift(part);
      cur = cur.parentElement;
    }
    return parts.join(' > ');
  }

  function ensureHoverBox(){
    if (hoverBox) return;
    hoverBox = el('div', {id:'surpriz-inspect-hover-box'});
    hoverLabel = el('div', {id:'surpriz-inspect-hover-label'});
    document.body.appendChild(hoverBox);
    document.body.appendChild(hoverLabel);
  }
  function clearHoverBox(){
    if (hoverBox) { hoverBox.remove(); hoverBox = null; }
    if (hoverLabel) { hoverLabel.remove(); hoverLabel = null; }
  }
  function moveHover(t){
    ensureHoverBox();
    var r = t.getBoundingClientRect();
    Object.assign(hoverBox.style, {left:r.left+'px', top:r.top+'px', width:r.width+'px', height:r.height+'px'});
    hoverLabel.textContent = describe(t) + ' — ' + Math.round(r.width) + '×' + Math.round(r.height);
    var top = r.top - 26; if (top < 4) top = r.bottom + 6;
    Object.assign(hoverLabel.style, {left:r.left+'px', top:top+'px'});
  }
  function setPicking(on){
    picking = !!on;
    pickBtn.classList.toggle('is-active', picking);
    pickBtn.textContent = picking ? '✕ Stop' : '⌖ Pick';
    document.documentElement.style.cursor = picking ? 'crosshair' : '';
    if (!picking) clearHoverBox();
  }

  function updateCount(){
    countEl.textContent = pins.length;
    reviewBtn.disabled = pins.length === 0;
  }

  function buildMeta(t){
    var sel = uniqueSelector(t);
    var r = t.getBoundingClientRect();
    var cs = window.getComputedStyle(t);
    return {
      tag: t.tagName.toLowerCase(),
      id: t.id || null,
      classes: Array.from(t.classList||[]),
      selector: sel,
      text: (t.textContent||'').trim().slice(0, 240),
      rect: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
      computed: {
        color: cs.color, background: cs.backgroundColor,
        padding: cs.padding, margin: cs.margin, border: cs.border, display: cs.display,
        position: cs.position, fontSize: cs.fontSize, fontWeight: cs.fontWeight, lineHeight: cs.lineHeight,
      },
      outerHTML: (t.outerHTML||'').slice(0, 1200),
      url: location.pathname + location.search,
      viewport: { w: window.innerWidth, h: window.innerHeight },
    };
  }

  function renderPinMarkers(){
    document.querySelectorAll('.swp-pin-num,.swp-pin-box').forEach(function(n){ n.remove(); });
    var sx = window.scrollX, sy = window.scrollY;
    pins.forEach(function(pin, i){
      var t = pin.target;
      if (!t || !document.body.contains(t)) return;
      var r = t.getBoundingClientRect();
      var box = el('div', {className:'swp-pin-box' + (pin.comment ? '' : ' is-empty')});
      Object.assign(box.style, {left:(r.left+sx)+'px', top:(r.top+sy)+'px', width:r.width+'px', height:r.height+'px'});
      document.body.appendChild(box);
      var num = el('div', {className:'swp-pin-num' + (pin.comment ? '' : ' is-empty'), title: '#' + (i+1) + (pin.comment ? ' — ' + pin.comment.slice(0,80) : ' — без комментария (клик чтобы дописать)')}, [String(i+1)]);
      Object.assign(num.style, {left:(r.left+sx-14)+'px', top:(r.top+sy-14)+'px'});
      num.addEventListener('click', function(e){ e.stopPropagation(); openReview(i); });
      document.body.appendChild(num);
    });
  }

  function showToast(msg, isError){
    if (!toastEl) { toastEl = el('div', {id:'surpriz-inspect-toast'}); document.body.appendChild(toastEl); }
    toastEl.textContent = msg;
    toastEl.classList.toggle('is-error', !!isError);
    toastEl.classList.add('is-show');
    clearTimeout(toastEl._t);
    toastEl._t = setTimeout(function(){ toastEl.classList.remove('is-show'); }, 2200);
  }

  function closePanel(){ if (panelEl) { panelEl.remove(); panelEl = null; } renderPinMarkers(); }

  function openReview(focusIdx){
    closePanel();
    if (!pins.length) { showToast('Сначала отметь хотя бы один элемент', true); return; }
    var rows = pins.map(function(pin, i){
      var sel = pin.meta && pin.meta.selector || '';
      var badge = el('span', {className:'swp-pin-badge'}, [String(i+1)]);
      var selEl = el('span', {className:'swp-pin-sel', title:sel}, [sel]);
      var del = el('button', {type:'button', className:'swp-pin-del', title:'Удалить метку', on:{click:function(){
        pins.splice(i,1); updateCount(); renderPinMarkers();
        if (pins.length) openReview(Math.max(0, i-1)); else closePanel();
      }}}, ['×']);
      var head = el('div', {className:'swp-pin-head'}, [badge, selEl, del]);
      var ta = el('textarea', {placeholder:'Что нужно поправить с #' + (i+1) + '?', value:pin.comment || '', on:{input:function(e){ pin.comment = e.target.value; }, blur:renderPinMarkers}});
      pin._ta = ta;
      var row = el('div', {className:'swp-pin-row' + (i === focusIdx ? ' is-current' : '')}, [head, ta]);
      return row;
    });
    var head = el('header', {}, [
      el('span', {className:'swp-title'}, ['Метки на странице — ' + pins.length]),
      el('span', {className:'swp-spacer'}),
      el('button', {className:'swp-x', type:'button', 'aria-label':'Закрыть', on:{click:closePanel}}, ['×'])
    ]);
    var body = el('div', {className:'swp-body'}, rows);
    var sendBtn = el('button', {type:'button', className:'swp-primary', id:'swp-send-all', on:{click:submitAll}}, ['Отправить всё']);
    var pickMore = el('button', {type:'button', on:{click:function(){ closePanel(); setPicking(true); }}}, ['+ Ещё метку']);
    var clearAll = el('button', {type:'button', on:{click:function(){
      if (!confirm('Удалить все метки?')) return;
      pins = []; updateCount(); renderPinMarkers(); closePanel();
    }}}, ['Очистить']);
    var foot = el('footer', {}, [
      el('span', {className:'swp-foot-left'}, [pins.length + ' меток · Cmd+Enter — отправить']),
      el('div', {style:{display:'flex',gap:'8px'}}, [clearAll, pickMore, sendBtn])
    ]);
    panelEl = el('div', {id:'surpriz-inspect-panel'}, [head, body, foot]);
    document.body.appendChild(panelEl);
    panelEl.addEventListener('keydown', function(e){
      if ((e.metaKey||e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); submitAll(); }
      if (e.key === 'Escape') { e.preventDefault(); closePanel(); }
    });
    if (typeof focusIdx === 'number' && pins[focusIdx] && pins[focusIdx]._ta) {
      setTimeout(function(){
        pins[focusIdx]._ta.focus();
        var rows = panelEl.querySelectorAll('.swp-pin-row');
        if (rows[focusIdx] && rows[focusIdx].scrollIntoView) rows[focusIdx].scrollIntoView({behavior:'smooth', block:'center'});
      }, 60);
    }
  }

  function submitAll(){
    var items = pins.map(function(pin, i){
      return { index: i+1, comment: (pin.comment||'').trim(), meta: pin.meta };
    });
    var withComment = items.filter(function(x){ return x.comment.length > 0; });
    if (!withComment.length) { showToast('Опиши хотя бы одну метку', true); return; }
    var sendBtn = panelEl ? panelEl.querySelector('#swp-send-all') : null;
    if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = 'Отправка…'; }
    fetch('/__inspect/batch', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ items: items, ts: Date.now(), url: location.pathname + location.search, viewport: {w: innerWidth, h: innerHeight} })
    }).then(function(r){
      if (!r.ok) throw new Error('http '+r.status);
      return r.json();
    }).then(function(){
      showToast('Отправлено ' + items.length + ' меток ✓');
      pins = []; updateCount(); renderPinMarkers(); closePanel();
    }).catch(function(e){
      if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Отправить всё'; }
      showToast('Ошибка: '+e.message, true);
    });
  }

  document.addEventListener('mousemove', function(e){
    if (!picking) return;
    var t = document.elementFromPoint(e.clientX, e.clientY);
    if (shouldSkip(t)) return;
    if (t) moveHover(t);
  }, true);

  document.addEventListener('click', function(e){
    if (!picking) return;
    var t = document.elementFromPoint(e.clientX, e.clientY);
    if (shouldSkip(t)) return;
    e.preventDefault(); e.stopPropagation();
    pinSeq += 1;
    pins.push({ id: pinSeq, target: t, meta: buildMeta(t), comment: '' });
    updateCount();
    renderPinMarkers();
    showToast('Метка #' + pins.length + ' добавлена');
  }, true);

  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape' && picking) setPicking(false);
    if ((e.metaKey||e.ctrlKey) && e.shiftKey && (e.key === 'I' || e.key === 'i')) { e.preventDefault(); setPicking(!picking); }
  });

  pickBtn.onclick = function(){ setPicking(!picking); };
  reviewBtn.onclick = function(){ openReview(pins.length - 1); };
  clearBtn.onclick = function(){
    if (!pins.length) { fetch('/__inspect/clear', {method:'POST'}).catch(function(){}); showToast('Сброшено'); return; }
    if (!confirm('Удалить все ' + pins.length + ' меток?')) return;
    pins = []; updateCount(); renderPinMarkers();
    fetch('/__inspect/clear', {method:'POST'}).catch(function(){});
    showToast('Сброшено');
  };

  window.addEventListener('scroll', renderPinMarkers, true);
  window.addEventListener('resize', renderPinMarkers);

  updateCount();
})();
</script>
"""


HOME_POPULAR_GRID_BLOCK = """
<style id="home-popular-grid-fix">
@media (max-width: 860px) {
  .home .woocommerce.columns-4 ul.products.elementor-grid,
  body.home ul.products.elementor-grid.columns-4 {
    display: grid !important;
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    gap: 12px !important;
    padding: 0 12px !important;
    margin: 0 !important;
  }
  .home ul.products.elementor-grid > li.product,
  body.home ul.products.elementor-grid > li {
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    flex: 1 1 0 !important;
  }
  .home ul.products.elementor-grid > li .astra-shop-thumbnail-wrap img,
  body.home ul.products.elementor-grid > li img.attachment-full {
    width: 100% !important;
    height: auto !important;
    aspect-ratio: 4 / 5 !important;
    object-fit: cover !important;
    border-radius: 14px !important;
  }
  .home ul.products.elementor-grid > li .astra-shop-summary-wrap,
  body.home ul.products.elementor-grid > li .ast-woo-shop-product-description {
    padding: 8px 4px 12px !important;
  }
  .home ul.products.elementor-grid > li .woocommerce-loop-product__title {
    font-size: 14px !important;
    line-height: 1.3 !important;
    margin: 0 0 4px !important;
    -webkit-line-clamp: 2 !important;
    display: -webkit-box !important;
    -webkit-box-orient: vertical !important;
    overflow: hidden !important;
  }
  .home ul.products.elementor-grid > li .price,
  body.home ul.products.elementor-grid > li .price {
    font-size: 13px !important;
  }
  .home ul.products.elementor-grid > li a.button,
  .home ul.products.elementor-grid > li a.button.product_type_simple,
  body.home ul.products.elementor-grid > li a.button,
  body.home ul.products.elementor-grid > li a.add_to_cart_button {
    display: none !important;
  }
  .home ul.products.elementor-grid > li .astra-shop-summary-wrap,
  body.home ul.products.elementor-grid > li .astra-shop-summary-wrap {
    position: static !important;
    min-height: 0 !important;
  }
}
@media (max-width: 380px) {
  .home ul.products.elementor-grid > li .woocommerce-loop-product__title {
    font-size: 13px !important;
  }
}
</style>
"""


CATALOG_EASTER_EGG_BLOCK = r"""
<style id="catalog-easter-egg-style">
@media (hover: hover) and (min-width: 861px) {
  .managed-catalog__products > li.has-easter-egg {
    position: relative;
  }
  .managed-catalog__products > li.has-easter-egg .easter-egg-video {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: inherit;
    opacity: 0;
    pointer-events: none;
    transition: opacity 0.25s ease;
    z-index: 5;
    background: #000;
  }
  .managed-catalog__products > li.has-easter-egg.is-easter-active .easter-egg-video {
    opacity: 1;
  }
  .managed-catalog__products > li.has-easter-egg.is-easter-active .surpriz-card__media,
  .managed-catalog__products > li.has-easter-egg.is-easter-active > a:not(.easter-egg-link),
  .managed-catalog__products > li.has-easter-egg.is-easter-active .surpriz-card__body {
    opacity: 0;
    transition: opacity 0.25s ease;
  }
  .managed-catalog__products > li.has-easter-egg .easter-egg-mute {
    position: absolute;
    bottom: 10px;
    right: 10px;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: rgba(0, 0, 0, 0.55);
    color: #fff;
    border: 0;
    cursor: pointer;
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 6;
    backdrop-filter: blur(8px);
  }
  .managed-catalog__products > li.has-easter-egg.is-easter-active .easter-egg-mute {
    display: flex;
  }
  .managed-catalog__products > li.has-easter-egg .easter-egg-mute svg { width: 18px; height: 18px; }
}
</style>
<script id="catalog-easter-egg" data-easter-egg>
(function(){
  if (window.__easterEggInit) return;
  window.__easterEggInit = true;
  var TARGET_SLUGS = ['spiderman'];
  function isDesktopHover(){
    return window.matchMedia &&
      window.matchMedia('(hover: hover) and (min-width: 861px)').matches;
  }
  function findTarget(){
    var products = document.querySelector('.managed-catalog__products');
    if (!products) return null;
    var items = products.querySelectorAll(':scope > li');
    for (var i = 0; i < items.length; i++) {
      var link = items[i].querySelector('a[href*="/character/"]');
      if (!link) continue;
      var href = link.getAttribute('href') || '';
      var match = href.match(/\/character\/([^\/?#]+)/);
      if (match && TARGET_SLUGS.indexOf(match[1]) !== -1) {
        return items[i];
      }
    }
    return null;
  }
  function init(){
    if (!isDesktopHover()) return;
    var target = findTarget();
    if (!target) return;
    if (target.classList.contains('has-easter-egg')) return;
    target.classList.add('has-easter-egg');

    var video = document.createElement('video');
    video.className = 'easter-egg-video';
    video.preload = 'metadata';
    video.muted = false;
    video.playsInline = true;
    video.loop = true;
    video.setAttribute('aria-hidden', 'true');
    var src1 = document.createElement('source');
    src1.src = '/easter/pashalca.mp4';
    src1.type = 'video/mp4';
    var src2 = document.createElement('source');
    src2.src = '/easter/pashalca.webm';
    src2.type = 'video/webm';
    video.appendChild(src1);
    video.appendChild(src2);
    target.appendChild(video);

    var muteBtn = document.createElement('button');
    muteBtn.type = 'button';
    muteBtn.className = 'easter-egg-mute';
    muteBtn.setAttribute('aria-label', 'Звук');
    function paintIcon(){
      muteBtn.innerHTML = video.muted
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>';
    }
    paintIcon();
    muteBtn.addEventListener('click', function(e){
      e.preventDefault();
      e.stopPropagation();
      video.muted = !video.muted;
      paintIcon();
    });
    target.appendChild(muteBtn);

    var leaveTimer;
    target.addEventListener('mouseenter', function(){
      clearTimeout(leaveTimer);
      target.classList.add('is-easter-active');
      try { video.currentTime = 0; } catch(e){}
      var p = video.play();
      if (p && typeof p.catch === 'function') {
        p.catch(function(){
          video.muted = true;
          paintIcon();
          video.play().catch(function(){});
        });
      }
    });
    target.addEventListener('mouseleave', function(){
      leaveTimer = setTimeout(function(){
        target.classList.remove('is-easter-active');
        video.pause();
      }, 80);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
</script>
"""


CATALOG_TRANSITION_BLOCK = r"""
<style id="catalog-transition-style">
.managed-catalog__products,
.managed-catalog__hero-title,
.managed-catalog__hero-meta {
  animation: catalog-fade-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
}
.managed-catalog__hero-meta { animation-delay: 60ms; }
.managed-catalog__products { animation-delay: 120ms; }
.managed-catalog__products > li {
  animation: catalog-card-in 0.78s cubic-bezier(0.22, 1, 0.36, 1) both;
  animation-delay: calc(160ms + var(--card-i, 0) * 55ms);
}
.managed-catalog.is-leaving .managed-catalog__products,
.managed-catalog.is-leaving .managed-catalog__hero-title,
.managed-catalog.is-leaving .managed-catalog__hero-meta {
  animation: catalog-fade-out 0.32s cubic-bezier(0.55, 0, 0.68, 0) both;
}
.managed-catalog.is-leaving .managed-catalog__hero-chip {
  pointer-events: none;
}
.managed-catalog__hero-chip {
  transition: background-color 0.24s ease, color 0.24s ease, border-color 0.24s ease, transform 0.18s ease;
}
.managed-catalog__hero-chip:active { transform: scale(0.96); }
@keyframes catalog-fade-in {
  from { opacity: 0; transform: translateY(12px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes catalog-card-in {
  from { opacity: 0; transform: translateY(18px) scale(0.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes catalog-fade-out {
  from { opacity: 1; transform: translateY(0); }
  to   { opacity: 0; transform: translateY(-8px); }
}
@media (prefers-reduced-motion: reduce) {
  .managed-catalog__products,
  .managed-catalog__products > li,
  .managed-catalog__hero-title,
  .managed-catalog__hero-meta,
  .managed-catalog.is-leaving .managed-catalog__products,
  .managed-catalog.is-leaving .managed-catalog__hero-title,
  .managed-catalog.is-leaving .managed-catalog__hero-meta {
    animation: none !important;
  }
}
</style>
<script id="catalog-transition">
(function(){
  var root = document.querySelector('.managed-catalog');
  if (!root) return;
  var items = root.querySelectorAll('.managed-catalog__products > li');
  for (var i = 0; i < items.length; i++) {
    items[i].style.setProperty('--card-i', i);
  }
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  function fadeOutAndGo(href){
    if (!href || root.classList.contains('is-leaving')) return;
    root.classList.add('is-leaving');
    setTimeout(function(){ window.location.href = href; }, 320);
  }
  root.addEventListener('click', function(e){
    var a = e.target.closest && e.target.closest('a.managed-catalog__hero-chip');
    if (!a) return;
    if (a.classList.contains('is-active')) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1) return;
    e.preventDefault();
    fadeOutAndGo(a.getAttribute('href'));
  });
})();
</script>
"""


GLOBAL_MOTION_BLOCK = r"""
<style id="global-motion-style">
:root {
  --motion-ease-out: cubic-bezier(0.22, 1, 0.36, 1);
  --motion-ease-in:  cubic-bezier(0.55, 0, 0.68, 0);
  --motion-ease:     cubic-bezier(0.4, 0, 0.2, 1);
  --motion-fast:     180ms;
  --motion-base:     280ms;
  --motion-slow:     520ms;
}
html { scroll-behavior: smooth; }
body { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
a, button, [role="button"], .button, .ast-button, input[type="submit"],
.surpriz-card, .managed-show-card, .managed-product-card, .surpriz-card__btn,
.elementor-button, .surpriz-site-footer__nav a {
  transition:
    background-color var(--motion-base) var(--motion-ease),
    color            var(--motion-base) var(--motion-ease),
    border-color     var(--motion-base) var(--motion-ease),
    box-shadow       var(--motion-base) var(--motion-ease),
    opacity          var(--motion-base) var(--motion-ease),
    transform        var(--motion-fast) var(--motion-ease-out);
}
a:active, button:active, [role="button"]:active, .button:active, .surpriz-card__btn:active,
.elementor-button:active { transform: scale(0.97); }
img, video { transition: opacity var(--motion-slow) var(--motion-ease-out); }
img[loading="lazy"]:not([data-loaded]) { opacity: 0; }
img[data-loaded] { opacity: 1; }
.surpriz-card:hover, .managed-show-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 14px 32px -16px rgba(31, 28, 44, 0.22);
}

body { animation: page-fade-in var(--motion-slow) var(--motion-ease-out) both; }
body.skip-page-anim,
html.skip-page-anim body { animation: none !important; }
body.skip-page-anim .animated.fadeInDown,
body.skip-page-anim .animated.fadeIn,
html.skip-page-anim .animated.fadeInDown,
html.skip-page-anim .animated.fadeIn {
  animation: none !important;
  opacity: 1 !important;
  visibility: visible !important;
}
/* Elementor sticky spacer must remain hidden — never reset its transform/opacity */
.elementor-sticky__spacer { visibility: hidden !important; pointer-events: none !important; }
.elementor-invisible:not(.elementor-sticky__spacer) {
  /* Visibility-restore for content that uses .elementor-invisible as load-state.
     Sticky spacer is excluded because Elementor positions it offscreen on purpose. */
}
body.skip-page-anim .elementor-invisible:not(.elementor-sticky__spacer),
html.skip-page-anim .elementor-invisible:not(.elementor-sticky__spacer) {
  animation: none !important;
  opacity: 1 !important;
  visibility: visible !important;
}
body.is-leaving-page { pointer-events: none; }
@keyframes page-fade-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes page-fade-out { from { opacity: 1; } to { opacity: 0; transform: translateY(-4px); } }

/* Cross-page fade overlay — eliminates flash between navigations */
#site-page-veil {
  position: fixed;
  inset: 0;
  background: #ffffff;
  z-index: 99999;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.36s cubic-bezier(0.22, 1, 0.36, 1);
}
#site-page-veil.is-visible { opacity: 1; pointer-events: auto; }
@media (prefers-reduced-motion: reduce) {
  #site-page-veil { transition: none !important; }
}

.scroll-reveal { opacity: 0; transform: translateY(28px); transition: opacity var(--motion-slow) var(--motion-ease-out), transform var(--motion-slow) var(--motion-ease-out); }
.scroll-reveal.is-revealed { opacity: 1; transform: translateY(0); }

.managed-show-card, .surpriz-card, .ast-woocommerce-container .product { will-change: transform; }

/* === Polish: focus rings, button states, image hover === */
:root {
  --motion-focus-ring: 0 0 0 3px rgba(108, 27, 227, 0.32);
}
a:focus-visible,
button:focus-visible,
[role="button"]:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
.button:focus-visible,
.surpriz-card__btn:focus-visible {
  outline: none !important;
  box-shadow: var(--motion-focus-ring) !important;
  border-radius: 8px;
}
img { transform: translateZ(0); }
.surpriz-card__media img,
.managed-show-card__media img { transition: transform 0.55s cubic-bezier(0.22, 1, 0.36, 1); }
.surpriz-card:hover .surpriz-card__media img,
.managed-show-card:hover .managed-show-card__media img { transform: scale(1.04); }

/* Smooth selection feedback for radio/checkbox cards */
.party-program-card,
.party-character-card,
.party-payment-option {
  transition: border-color var(--motion-base) var(--motion-ease),
              background-color var(--motion-base) var(--motion-ease),
              box-shadow var(--motion-base) var(--motion-ease),
              transform var(--motion-fast) var(--motion-ease-out);
}
.party-program-card:hover,
.party-character-card:hover,
.party-payment-option:hover { transform: translateY(-2px); }
.party-program-card.is-selected,
.party-character-card.is-selected,
.party-payment-option.is-selected {
  box-shadow: 0 8px 24px -12px rgba(108, 27, 227, 0.32);
}

/* Section enter — staggered for visible above-the-fold */
@keyframes section-soft-in {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
.elementor-section, .surpriz-site-footer, .managed-catalog__products,
.elementor-element[data-element_type="container"] {
  /* keep existing animations from elementor; do not stack ours unless visible */
}

/* Inputs: subtle focus highlight */
input[type="text"],
input[type="tel"],
input[type="email"],
input[type="search"],
input[type="number"],
input[type="date"],
input[type="time"],
textarea,
select {
  transition: border-color var(--motion-base) var(--motion-ease),
              box-shadow var(--motion-base) var(--motion-ease),
              background-color var(--motion-base) var(--motion-ease);
}

@media (prefers-reduced-motion: reduce) {
  .surpriz-card__media img,
  .managed-show-card__media img,
  .party-program-card,
  .party-character-card,
  .party-payment-option {
    transition: none !important;
  }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
  html { scroll-behavior: auto; }
}
</style>
<script id="global-motion">
(function(){
  // Mark "not first" before paint to disable header drop-down animation on subsequent pages.
  // First open in tab/session = full animations. Internal navigation = animations skipped.
  try {
    var visited = sessionStorage.getItem('surpriz_visited');
    if (visited) {
      document.documentElement.classList.add('skip-page-anim');
      // Apply to body once it exists
      if (document.body) document.body.classList.add('skip-page-anim');
      else document.addEventListener('DOMContentLoaded', function(){ document.body.classList.add('skip-page-anim'); }, {once: true});
    } else {
      sessionStorage.setItem('surpriz_visited', '1');
    }
  } catch (_) {}

  // Cross-page veil overlay
  function ensureVeil() {
    var veil = document.getElementById('site-page-veil');
    if (!veil) {
      veil = document.createElement('div');
      veil.id = 'site-page-veil';
      veil.setAttribute('aria-hidden', 'true');
      document.documentElement.appendChild(veil);
    }
    return veil;
  }
  function showVeil(){ var v = ensureVeil(); v.classList.add('is-visible'); }
  function hideVeil(){ var v = document.getElementById('site-page-veil'); if (v) v.classList.remove('is-visible'); }

  // Pre-create veil so first paint already has it ready (in visited-state we fade in from veil)
  if (sessionStorage.getItem('surpriz_visited')) {
    var preVeil = ensureVeil();
    preVeil.classList.add('is-visible');
    requestAnimationFrame(function(){
      requestAnimationFrame(function(){
        // 2× rAF ensures style applied before transition
        preVeil.classList.remove('is-visible');
      });
    });
  }
  window.addEventListener('pageshow', function(e){
    document.body && document.body.classList.remove('is-leaving-page');
    hideVeil();
  });

  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;
  function markLoaded(img){ img.setAttribute('data-loaded', '1'); }
  function bindImage(img){
    if (img.hasAttribute('data-loaded')) return;
    if (img.complete && img.naturalWidth > 0) { markLoaded(img); return; }
    img.addEventListener('load', function(){ markLoaded(img); }, {once: true});
    img.addEventListener('error', function(){ markLoaded(img); }, {once: true});
  }
  function setupImages(root){
    (root || document).querySelectorAll('img[loading="lazy"]:not([data-loaded])').forEach(bindImage);
  }
  setupImages();
  if ('MutationObserver' in window) {
    var imgObserver = new MutationObserver(function(mutations){
      mutations.forEach(function(m){
        m.addedNodes && m.addedNodes.forEach(function(node){
          if (node.nodeType !== 1) return;
          if (node.tagName === 'IMG' && node.getAttribute('loading') === 'lazy') {
            bindImage(node);
          } else if (node.querySelectorAll) {
            setupImages(node);
          }
        });
      });
    });
    imgObserver.observe(document.body, { childList: true, subtree: true });
  }

  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(en){
        if (en.isIntersecting) {
          en.target.classList.add('is-revealed');
          io.unobserve(en.target);
        }
      });
    }, { rootMargin: '0px 0px -10% 0px', threshold: 0.05 });
    var revealSelectors = [
      '.surpriz-site-footer__col',
      '.managed-show-card',
      '.surpriz-card',
      '.elementor-section:not(.elementor-sticky)'
    ];
    document.querySelectorAll(revealSelectors.join(',')).forEach(function(el){
      el.classList.add('scroll-reveal');
      io.observe(el);
    });
  }

  function isInternal(href){
    if (!href) return false;
    if (href.charAt(0) === '#') return false;
    if (href.indexOf('mailto:') === 0 || href.indexOf('tel:') === 0 || href.indexOf('javascript:') === 0) return false;
    try {
      var u = new URL(href, location.href);
      return u.origin === location.origin;
    } catch (_) { return false; }
  }
  document.addEventListener('click', function(e){
    var a = e.target.closest && e.target.closest('a');
    if (!a || !a.href) return;
    if (a.target && a.target !== '_self') return;
    if (a.hasAttribute('download')) return;
    if (e.defaultPrevented) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1) return;
    if (a.closest('.managed-catalog__hero-chips')) return; // owned by catalog-transition
    if (a.closest('.surpriz-bottom-bar')) return;          // bottom-bar handles its own
    if (!isInternal(a.href)) return;
    if (a.href === location.href) return;
    var href = a.href;
    e.preventDefault();
    document.body.classList.add('is-leaving-page');
    showVeil();
    setTimeout(function(){ window.location.href = href; }, 380);
  });
  window.addEventListener('pageshow', function(e){
    if (e.persisted) {
      document.body.classList.remove('is-leaving-page');
      hideVeil();
    }
  });
})();
</script>
"""


CATALOG_MOBILE_HERO_BLOCK = r"""
<style id="catalog-mobile-hero-style">
.managed-catalog .woocommerce-products-header,
.managed-catalog .managed-catalog__intro,
.managed-catalog .ast-shop-toolbar-container { display: none !important; }
#secondary.widget-area { display: none !important; }
.ast-container { display: block !important; }
body.archive #primary,
body.archive .content-area { width: 100% !important; max-width: 100% !important; padding-left: 0 !important; padding-right: 0 !important; }

.managed-catalog__hero {
  position: relative;
  margin: 8px auto 24px;
  padding: 28px 28px 22px;
  width: min(100% - 32px, 1280px);
  background:
    radial-gradient(circle at 20% 0%, rgba(108, 27, 227, 0.08) 0%, transparent 55%),
    radial-gradient(circle at 100% 30%, rgba(225, 115, 51, 0.06) 0%, transparent 55%),
    linear-gradient(180deg, #faf6ff 0%, #ffffff 100%);
  border: 1px solid rgba(108, 27, 227, 0.08);
  border-radius: 24px;
  box-shadow: 0 12px 32px rgba(108, 27, 227, 0.06);
  overflow: hidden;
}
.managed-catalog__hero-title {
  margin: 0 0 6px;
  color: #1f1c2c;
  font-family: "Balsamiq Sans", "Rubik", sans-serif;
  font-size: 36px;
  font-weight: 700;
  line-height: 1.1;
  letter-spacing: -0.01em;
}
.managed-catalog__hero-meta {
  margin: 0 0 22px;
  color: #6c1be3;
  font-size: 15px;
  font-weight: 600;
}
.managed-catalog__hero-search {
  position: relative;
  display: block;
  margin: 0 0 18px;
  max-width: 720px;
}
.managed-catalog__hero-search-icon {
  position: absolute;
  left: 18px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  color: #8a8694;
  pointer-events: none;
}
.managed-catalog__hero-search input {
  width: 100%;
  height: 56px;
  padding: 0 50px 0 50px;
  background: #ffffff;
  border: 1.5px solid #e7e2ee;
  border-radius: 16px;
  color: #1f1c2c;
  font-family: inherit;
  font-size: 16px;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.managed-catalog__hero-search input::placeholder { color: #9a96a8; }
.managed-catalog__hero-search input:focus {
  border-color: #6c1be3;
  box-shadow: 0 0 0 4px rgba(108, 27, 227, 0.12);
}
.managed-catalog__hero-search-clear {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  width: 36px;
  height: 36px;
  border: 0;
  background: transparent;
  color: #8a8694;
  cursor: pointer;
  display: none;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
}
.managed-catalog__hero-search-clear:hover { background: #f4f0fa; color: #1f1c2c; }
.managed-catalog__hero-search.has-value .managed-catalog__hero-search-clear { display: flex; }
.managed-catalog__hero-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0 0 16px;
}
.managed-catalog__hero-chip {
  display: inline-flex;
  align-items: center;
  height: 38px;
  padding: 0 16px;
  background: #ffffff;
  border: 1.5px solid #e7e2ee;
  border-radius: 999px;
  color: #4d4861;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
  transition: all 0.15s ease;
}
.managed-catalog__hero-chip:hover { border-color: #c8b8eb; color: #1f1c2c; transform: translateY(-1px); }
.managed-catalog__hero-chip.is-active {
  background: #6c1be3;
  border-color: #6c1be3;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(108, 27, 227, 0.28);
}
.managed-catalog__hero-tools {
  display: none !important;
}
.managed-catalog__hero-intro {
  display: none !important;
}
.managed-catalog__hero-tool {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 14px;
  background: transparent;
  border: 1.5px solid #e7e2ee;
  border-radius: 12px;
  color: #4d4861;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.managed-catalog__hero-tool svg { width: 16px; height: 16px; }
.managed-catalog__hero-tool:hover { border-color: #c8b8eb; color: #1f1c2c; }
.managed-catalog__hero-intro summary {
  list-style: none;
  cursor: pointer;
  color: #6c1be3;
  font-size: 13.5px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 0;
}
.managed-catalog__hero-intro summary::-webkit-details-marker { display: none; }
.managed-catalog__hero-intro summary::after {
  content: "›";
  display: inline-block;
  transform: rotate(90deg);
  transition: transform 0.15s ease;
  font-size: 16px;
  line-height: 1;
}
.managed-catalog__hero-intro[open] summary::after { transform: rotate(-90deg); }
.managed-catalog__hero-intro-body {
  margin-top: 10px;
  color: #66606f;
  font-size: 14px;
  line-height: 1.6;
  max-width: 720px;
}
.managed-catalog__hero-intro-body p { margin: 0 0 8px; }
.managed-catalog__hero-intro-body p:last-child { margin: 0; }

.managed-catalog__products.products {
  width: min(100% - 32px, 1280px) !important;
  margin-left: auto !important;
  margin-right: auto !important;
}

@media (min-width: 861px) {
  .managed-catalog .managed-catalog__products.products,
  .managed-catalog.managed-catalog--view-list .managed-catalog__products.products,
  ul.products.managed-catalog__products.surpriz-cards {
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    gap: 24px !important;
  }
}
@media (min-width: 1280px) {
  .managed-catalog .managed-catalog__products.products,
  .managed-catalog.managed-catalog--view-list .managed-catalog__products.products,
  ul.products.managed-catalog__products.surpriz-cards {
    grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
    gap: 28px !important;
  }
}

@media (max-width: 860px) {
  html, body { max-width: 100vw; overflow-x: hidden; }
  body.archive #primary,
  body.archive .content-area,
  .managed-catalog,
  .managed-catalog .site-main {
    max-width: 100vw !important;
    width: 100% !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
  }
  .managed-catalog__hero {
    margin: 6px 12px 14px;
    padding: 18px 16px 14px;
    width: auto;
    border-radius: 18px;
  }
  .managed-catalog__hero-title { font-size: 24px; }
  .managed-catalog__hero-meta { font-size: 13px; margin-bottom: 14px; }
  .managed-catalog__hero-search { margin-bottom: 12px; max-width: none; }
  .managed-catalog__hero-search input { height: 48px; padding: 0 44px 0 42px; font-size: 15px; border-radius: 14px; }
  .managed-catalog__hero-search-icon { left: 14px; width: 18px; height: 18px; }
  .managed-catalog__hero-search-clear { right: 8px; width: 30px; height: 30px; border-radius: 8px; }
  .managed-catalog__hero-chips {
    flex-wrap: wrap;
    overflow: visible;
    padding: 0;
    margin: 0 0 8px;
    gap: 8px;
    scroll-snap-type: none;
  }
  .managed-catalog__hero-chips::-webkit-scrollbar { display: none; }
  .managed-catalog__hero-chip {
    flex: 0 0 auto;
    height: 34px;
    padding: 0 12px;
    font-size: 12.5px;
    scroll-snap-align: none;
  }
  .managed-catalog__hero-tools { padding-top: 12px; }
  .managed-catalog__hero-tool { height: 36px; padding: 0 12px; flex: 1 1 auto; justify-content: center; }
  .managed-catalog__hero-intro-body { font-size: 13.5px; line-height: 1.55; }
  .managed-catalog__products.products { width: 100% !important; padding: 0 12px !important; box-sizing: border-box !important; }
}

.managed-catalog__sticky {
  display: none;
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: saturate(180%) blur(12px);
  -webkit-backdrop-filter: saturate(180%) blur(12px);
  border-bottom: 1px solid rgba(108, 27, 227, 0.1);
  padding: 8px 12px;
  transform: translateY(-100%);
  transition: transform 0.22s ease;
}
.managed-catalog__sticky.is-visible {
  display: flex;
  align-items: center;
  gap: 8px;
  transform: translateY(0);
}
.managed-catalog__sticky-search { position: relative; flex: 1; max-width: 720px; margin: 0 auto; }
.managed-catalog__sticky-search input {
  width: 100%;
  height: 40px;
  padding: 0 12px 0 36px;
  background: #f6f3fb;
  border: 1.5px solid transparent;
  border-radius: 12px;
  font-size: 14px;
  outline: none;
}
.managed-catalog__sticky-search input:focus {
  background: #ffffff;
  border-color: #6c1be3;
}
.managed-catalog__sticky-search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  color: #8a8694;
  pointer-events: none;
}
.managed-catalog__sticky-tool {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: #f6f3fb;
  border: 0;
  border-radius: 12px;
  color: #4d4861;
  cursor: pointer;
}
.managed-catalog__sticky-tool svg { width: 18px; height: 18px; }
</style>
<script id="catalog-mobile-hero-script">
(function(){
  if (window.__catalogMobileHeroInit) return;
  function init(){
    var root = document.querySelector('.managed-catalog');
    if (!root) return;
    if (root.querySelector('.managed-catalog__hero')) return;
    window.__catalogMobileHeroInit = true;

    var origH1 = root.querySelector('.woocommerce-products-header__title');
    var origIntro = root.querySelector('.managed-catalog__intro');
    var origToolbar = root.querySelector('.ast-shop-toolbar-container');
    var origSearchInput = origToolbar ? origToolbar.querySelector('input[name="q"], input[type="search"], input[name="s"], input[type="text"]') : null;
    if (!origSearchInput) {
      origSearchInput = root.querySelector('[data-catalog-search-input]');
    }
    var origCount = root.querySelector('.woocommerce-result-count');
    var origCountText = (origCount && origCount.textContent || '').trim();
    var resultMatch = origCountText.match(/(?:из\s+)(\d+)/i);
    var totalItems = resultMatch ? parseInt(resultMatch[1], 10) : null;

    function plural(n){
      if (!n) return '';
      var m10 = n % 10, m100 = n % 100;
      if (m100 >= 11 && m100 <= 14) return 'персонажей';
      if (m10 === 1) return 'персонаж';
      if (m10 >= 2 && m10 <= 4) return 'персонажа';
      return 'персонажей';
    }

    var heroTitle = (origH1 && origH1.textContent || 'Каталог персонажей').trim();
    var heroMeta = totalItems ? totalItems + ' ' + plural(totalItems) + ' на любой вкус' : 'Любимые герои на праздник';

    var hero = document.createElement('section');
    hero.className = 'managed-catalog__hero';
    hero.id = 'managed-catalog-hero-mobile';

    var h = document.createElement('h1');
    h.className = 'managed-catalog__hero-title';
    h.textContent = heroTitle;
    hero.appendChild(h);

    var meta = document.createElement('p');
    meta.className = 'managed-catalog__hero-meta';
    meta.textContent = heroMeta;
    hero.appendChild(meta);

    // Search form
    var form = document.createElement('form');
    form.className = 'managed-catalog__hero-search';
    form.method = 'get';
    form.action = '/catalog/';
    form.setAttribute('role', 'search');

    var iconWrap = document.createElement('span');
    iconWrap.className = 'managed-catalog__hero-search-icon';
    iconWrap.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>';
    form.appendChild(iconWrap);

    var input = document.createElement('input');
    input.type = 'search';
    input.name = 'q';
    input.placeholder = 'Найти Эльзу, Бэтмена, Леди Баг…';
    input.setAttribute('aria-label', 'Поиск персонажа');
    input.autocomplete = 'off';
    // Mark as the catalog search input so the live-search script in catalog_content.html
    // attaches to this mobile hero input as well (it queries [data-catalog-search-input]).
    input.setAttribute('data-catalog-search-input', '');
    input.setAttribute('data-catalog-search-mobile', '');
    // Pre-populate from existing input value or URL ?q= so the user sees current query.
    var initialValue = '';
    if (origSearchInput && origSearchInput.value) {
      initialValue = origSearchInput.value;
    } else {
      try {
        var qp = new URLSearchParams(location.search);
        initialValue = qp.get('q') || qp.get('s') || '';
      } catch (e) {}
    }
    if (initialValue) input.value = initialValue;
    form.appendChild(input);

    var clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'managed-catalog__hero-search-clear';
    clearBtn.setAttribute('aria-label', 'Очистить поиск');
    clearBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
    form.appendChild(clearBtn);

    if (input.value) form.classList.add('has-value');
    input.addEventListener('input', function(){
      form.classList.toggle('has-value', input.value.length > 0);
    });
    clearBtn.addEventListener('click', function(){
      input.value = '';
      form.classList.remove('has-value');
      input.focus();
    });

    hero.appendChild(form);

    // Chips: collect categories from existing toolbar/category-bar if available, otherwise fallback static list
    var chipsWrap = document.createElement('nav');
    chipsWrap.className = 'managed-catalog__hero-chips';
    chipsWrap.setAttribute('aria-label', 'Категории');

    var fallbackCats = [
      {label:'Все', href:'/catalog/'},
      {label:'Мальчики', href:'/character-tag/malchikam/'},
      {label:'Девочки', href:'/character-tag/devochkam/'},
      {label:'Супергерои', href:'/character-category/supergeroi/'},
      {label:'Мультики', href:'/character-category/multiki/'},
      {label:'Сказочные', href:'/character-category/skazochnye/'},
      {label:'Фильмы', href:'/character-category/filmy/'},
      {label:'Сериалы', href:'/character-category/serialy/'},
      {label:'Ведущие', href:'/character-category/veduschie/'},
      {label:'Тематические', href:'/character-category/tematicheskie/'}
    ];
    var picked = fallbackCats;
    var currentPath = location.pathname.replace(/\/page\/\d+\/$/, '/');
    picked.forEach(function(c){
      var a = document.createElement('a');
      a.className = 'managed-catalog__hero-chip';
      a.href = c.href;
      a.textContent = c.label;
      if (c.href === currentPath || (c.href === '/catalog/' && currentPath === '/catalog/')) {
        a.classList.add('is-active');
      }
      chipsWrap.appendChild(a);
    });
    hero.appendChild(chipsWrap);

    // Tools row: Filter + Sort (sort uses original Astra select if present)
    var tools = document.createElement('div');
    tools.className = 'managed-catalog__hero-tools';

    var filterBtn = document.createElement('button');
    filterBtn.type = 'button';
    filterBtn.className = 'managed-catalog__hero-tool';
    filterBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="4" y1="6" x2="20" y2="6"/><line x1="7" y1="12" x2="17" y2="12"/><line x1="10" y1="18" x2="14" y2="18"/></svg><span>Фильтры</span>';
    filterBtn.addEventListener('click', function(){
      // Try to scroll to original toolbar / open any filter widget
      var anchor = document.querySelector('.term-list, .ast-shop-filters, .managed-catalog__products');
      if (anchor) anchor.scrollIntoView({behavior:'smooth', block:'start'});
    });
    tools.appendChild(filterBtn);

    var sortBtn = document.createElement('button');
    sortBtn.type = 'button';
    sortBtn.className = 'managed-catalog__hero-tool';
    sortBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M7 12h10"/><path d="M11 18h2"/></svg><span>А → Я</span>';
    var sortSelect = root.querySelector('select.orderby');
    if (sortSelect) {
      sortBtn.addEventListener('click', function(e){
        e.preventDefault();
        sortSelect.focus();
        sortSelect.click();
      });
    }
    tools.appendChild(sortBtn);

    hero.appendChild(tools);

    // Intro details
    if (origIntro && origIntro.textContent.trim()) {
      var details = document.createElement('details');
      details.className = 'managed-catalog__hero-intro';
      var summary = document.createElement('summary');
      summary.textContent = 'Подробнее о каталоге';
      details.appendChild(summary);
      var introBody = document.createElement('div');
      introBody.className = 'managed-catalog__hero-intro-body';
      // copy text content as paragraphs
      var paragraphs = origIntro.querySelectorAll('p');
      if (paragraphs.length) {
        paragraphs.forEach(function(p){
          var np = document.createElement('p');
          np.textContent = p.textContent.trim();
          if (np.textContent) introBody.appendChild(np);
        });
      } else {
        var p = document.createElement('p');
        p.textContent = origIntro.textContent.trim();
        introBody.appendChild(p);
      }
      details.appendChild(introBody);
      hero.appendChild(details);
    }

    // Insert before products grid
    var productsList = root.querySelector('.managed-catalog__products');
    if (productsList && productsList.parentNode) {
      productsList.parentNode.insertBefore(hero, productsList);
    } else {
      root.insertBefore(hero, root.firstChild);
    }

    // Sticky bar
    var sticky = document.createElement('div');
    sticky.className = 'managed-catalog__sticky';
    sticky.id = 'managed-catalog-sticky';
    sticky.innerHTML = '';
    var sForm = document.createElement('form');
    sForm.className = 'managed-catalog__sticky-search';
    sForm.method = 'get';
    sForm.action = '/catalog/';
    sForm.setAttribute('role','search');
    sForm.innerHTML = '<span class="managed-catalog__sticky-search-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg></span><input type="search" name="s" placeholder="Поиск персонажа" aria-label="Поиск" autocomplete="off"/>';
    var sFilter = document.createElement('button');
    sFilter.type = 'button';
    sFilter.className = 'managed-catalog__sticky-tool';
    sFilter.setAttribute('aria-label', 'Фильтры');
    sFilter.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="4" y1="6" x2="20" y2="6"/><line x1="7" y1="12" x2="17" y2="12"/><line x1="10" y1="18" x2="14" y2="18"/></svg>';
    sFilter.addEventListener('click', function(){
      window.scrollTo({top:0, behavior:'smooth'});
      setTimeout(function(){ var inp = hero.querySelector('input[name="s"]'); if (inp) inp.focus(); }, 360);
    });
    sticky.appendChild(sForm);
    sticky.appendChild(sFilter);
    document.body.appendChild(sticky);

    var lastVisible = false;
    function onScroll(){
      var heroBottom = hero.getBoundingClientRect().bottom;
      var visible = heroBottom < 0;
      if (visible !== lastVisible) {
        sticky.classList.toggle('is-visible', visible);
        lastVisible = visible;
      }
    }
    window.addEventListener('scroll', onScroll, {passive:true});
    onScroll();

    // Sync sticky search ↔ hero search
    var sInput = sForm.querySelector('input');
    sInput.value = input.value;
    sInput.addEventListener('input', function(){ input.value = sInput.value; form.classList.toggle('has-value', sInput.value.length > 0); });
    input.addEventListener('input', function(){ sInput.value = input.value; });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
</script>
"""


MOBILE_BOTTOM_BAR_BLOCK = """
<style id="site-mobile-bottom-bar-style">
.surpriz-bottom-bar { display: none; }
/* Force body to have no CSS containing block so position:fixed bars stick to the viewport.
   Astra theme applies a no-op transform that breaks fixed positioning — neutralize it everywhere. */
html body, html.surpriz-portal-page body { transform: none !important; -webkit-transform: none !important; perspective: none !important; filter: none !important; will-change: auto !important; }
@media (max-width: 860px) {
  body { padding-bottom: 76px !important; }
  .surpriz-bottom-bar {
    display: grid !important;
    grid-template-columns: repeat(5, 1fr);
    position: fixed !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    top: auto !important;
    transform: none !important;
    z-index: 2147483646;
    background: #ffffff;
    border-top: 1px solid rgba(53, 27, 125, 0.06);
    box-shadow: 0 -2px 12px rgba(53, 27, 125, 0.05);
    padding: 0 4px calc(0px + env(safe-area-inset-bottom, 0px));
    font-family: 'Rubik', sans-serif;
    height: calc(60px + env(safe-area-inset-bottom, 0px));
    pointer-events: auto;
  }
  .surpriz-bottom-bar__item {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    padding: 8px 2px 6px;
    color: #8a8694;
    text-decoration: none;
    font-size: 10.5px;
    line-height: 1.05;
    font-weight: 500;
    letter-spacing: 0;
    -webkit-tap-highlight-color: transparent;
    text-align: center;
    position: relative;
    transition: color 0.15s ease;
    height: 60px;
  }
  .surpriz-bottom-bar__icon {
    width: 26px;
    height: 26px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: currentColor;
  }
  .surpriz-bottom-bar__icon svg {
    width: 100%;
    height: 100%;
    display: block;
    stroke: currentColor;
    fill: none;
    stroke-width: 1.7;
    stroke-linecap: round;
    stroke-linejoin: round;
  }
  .surpriz-bottom-bar__label {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }
  .surpriz-bottom-bar__item:hover,
  .surpriz-bottom-bar__item:focus { color: #2d2839; outline: none; }
  .surpriz-bottom-bar__item.is-active {
    color: #6c1be3;
  }
  .surpriz-bottom-bar__item.is-active .surpriz-bottom-bar__icon svg {
    stroke-width: 2.1;
  }
  .surpriz-bottom-bar__item--cta {
    color: #6c1be3;
    overflow: visible;
    justify-content: flex-end;
    padding-bottom: 6px;
    gap: 4px;
  }
  .surpriz-bottom-bar__item--cta .surpriz-bottom-bar__icon {
    width: 54px;
    height: 54px;
    flex: 0 0 54px;
    border-radius: 50%;
    background: linear-gradient(135deg, #6c1be3 0%, #8e3df0 100%);
    box-shadow: 0 6px 16px -6px rgba(108, 27, 227, 0.32);
    color: #fff !important;
    transform: translateY(-26px);
    margin-bottom: -26px;
    transition: transform 0.18s ease, box-shadow 0.22s ease;
  }
  .surpriz-bottom-bar__item--cta .surpriz-bottom-bar__icon svg {
    width: 24px;
    height: 24px;
    stroke: #fff;
    stroke-width: 2.2;
  }
  .surpriz-bottom-bar__item--cta .surpriz-bottom-bar__label {
    color: #5a1bb3;
    font-weight: 700;
    font-size: 10.5px;
    line-height: 1.1;
    margin-top: 0;
  }
  .surpriz-bottom-bar__item--cta:hover .surpriz-bottom-bar__icon,
  .surpriz-bottom-bar__item--cta:focus .surpriz-bottom-bar__icon,
  .surpriz-bottom-bar__item--cta:active .surpriz-bottom-bar__icon {
    transform: translateY(-27px) scale(0.97);
    box-shadow: 0 4px 10px -4px rgba(108, 27, 227, 0.38);
  }
  .surpriz-bottom-bar__item.is-active::before {
    content: "";
    position: absolute;
    top: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 22px;
    height: 2px;
    background: #6c1be3;
    border-radius: 0 0 2px 2px;
  }
  .surpriz-bottom-bar__item--cta.is-active::before { display: none; }
  .ast-mobile-header-wrap .ast-button-wrap,
  .ast-mobile-menu-trigger,
  .ast-mobile-menu-buttons,
  .ast-button-wrap[data-section="section-mobile-header"],
  .menu-toggle,
  .ast-mobile-menu-buttons-fill,
  .ast-mobile-menu-buttons-outline,
  .ast-mobile-menu-buttons-minimal,
  .elementor-menu-toggle,
  button.elementor-menu-toggle,
  .e-menu-toggle,
  [aria-label="Menu Toggle"],
  [aria-label="Toggle Menu"],
  [aria-label*="меню"][role="button"],
  [data-widget_type*="nav-menu"] .elementor-menu-toggle,
  .elementor-widget-nav-menu .elementor-menu-toggle,
  .ast-mobile-svg .ast-mobile-svg,
  .main-header-bar .ast-button-wrap,
  .ast-header-button-1,
  .elementor-element-cdcc0dc,
  .elementor-element.elementor-hidden-widescreen .elementor-icon[href*="popup"],
  .elementor-element.elementor-hidden-widescreen.elementor-widget-icon {
    display: none !important;
    visibility: hidden !important;
  }
}
@media (max-width: 380px) {
  .surpriz-bottom-bar__item { font-size: 9.5px; gap: 2px; }
  .surpriz-bottom-bar__icon { width: 22px; height: 22px; }
  .surpriz-bottom-bar__item--cta .surpriz-bottom-bar__icon { width: 48px; height: 48px; flex: 0 0 48px; transform: translateY(-22px); margin-bottom: -22px; }
  .surpriz-bottom-bar__item--cta .surpriz-bottom-bar__icon svg { width: 20px; height: 20px; }
  .surpriz-bottom-bar__item--cta .surpriz-bottom-bar__label { font-size: 9.5px; }
}
</style>
<nav aria-label="Навигация" class="surpriz-bottom-bar" id="site-mobile-bottom-bar">
  <a class="surpriz-bottom-bar__item" data-bottom-bar-key="home" href="/">
    <span aria-hidden="true" class="surpriz-bottom-bar__icon"><svg viewBox="0 0 24 24"><path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/></svg></span>
    <span class="surpriz-bottom-bar__label">Главная</span>
  </a>
  <a class="surpriz-bottom-bar__item" data-bottom-bar-key="shows" href="/show-programs/">
    <span aria-hidden="true" class="surpriz-bottom-bar__icon"><svg viewBox="0 0 24 24"><path d="m12 3 2.6 5.4 5.9.6-4.4 4 1.3 5.9L12 16l-5.4 2.9 1.3-5.9-4.4-4 5.9-.6z"/></svg></span>
    <span class="surpriz-bottom-bar__label">Шоу</span>
  </a>
  <a class="surpriz-bottom-bar__item surpriz-bottom-bar__item--cta" data-bottom-bar-key="builder" href="/party-builder/">
    <span aria-hidden="true" class="surpriz-bottom-bar__icon"><svg viewBox="0 0 24 24"><path d="M12 5v14"/><path d="M5 12h14"/></svg></span>
    <span class="surpriz-bottom-bar__label">Собрать</span>
  </a>
  <a class="surpriz-bottom-bar__item" data-bottom-bar-key="costumes" href="/catalog/">
    <span aria-hidden="true" class="surpriz-bottom-bar__icon"><svg viewBox="0 0 24 24"><path d="M8.5 4 6 6.5 3 9l2 3 2-1v9h10v-9l2 1 2-3-3-2.5L15.5 4"/><path d="M8.5 4c.5 1.7 1.8 2.6 3.5 2.6S15 5.7 15.5 4"/></svg></span>
    <span class="surpriz-bottom-bar__label">Костюмы</span>
  </a>
  <a class="surpriz-bottom-bar__item" data-bottom-bar-key="profile" href="/account/">
    <span aria-hidden="true" class="surpriz-bottom-bar__icon"><svg viewBox="0 0 24 24"><circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c.7-3.6 3.6-6 7-6s6.3 2.4 7 6"/></svg></span>
    <span class="surpriz-bottom-bar__label">Профиль</span>
  </a>
</nav>
<script id="site-mobile-bottom-bar-script">
(() => {
  const init = () => {
    const bar = document.getElementById('site-mobile-bottom-bar');
    if (!bar) return;

    // Root cause of the floating-bar bug:
    // Astra/Elementor apply `transform: matrix(1,0,0,1,0,0)` (or similar) to <body> or wrappers,
    // which creates a CSS containing block — making `position: fixed` resolve relative to that
    // ancestor instead of the viewport.
    // The cleanest fix: detach the bar from <body> and append it as a direct child of <html>.
    // <html> has no transform (we control it), so position:fixed always sticks to the viewport.
    if (bar.parentElement !== document.documentElement) {
      document.documentElement.appendChild(bar);
    }

    // Lock the bar styles inline (highest specificity, beats theme CSS).
    const lockBar = () => {
      bar.style.setProperty('position', 'fixed', 'important');
      bar.style.setProperty('left', '0', 'important');
      bar.style.setProperty('right', '0', 'important');
      bar.style.setProperty('bottom', '0', 'important');
      bar.style.setProperty('top', 'auto', 'important');
      bar.style.setProperty('transform', 'none', 'important');
      bar.style.setProperty('-webkit-transform', 'none', 'important');
      bar.style.setProperty('z-index', '2147483646', 'important');
      bar.style.setProperty('pointer-events', 'auto', 'important');
      bar.style.setProperty('width', '100%', 'important');
    };
    lockBar();

    // If anything re-parents or re-styles the bar (Elementor sticky kit, page transitions),
    // restore it to <html> and re-lock styles.
    const restore = () => {
      if (bar.parentElement !== document.documentElement) {
        document.documentElement.appendChild(bar);
      }
      lockBar();
    };
    try {
      const obs = new MutationObserver(() => {
        if (bar.parentElement !== document.documentElement) restore();
      });
      obs.observe(document.documentElement, { childList: true, subtree: true });
    } catch (_) {}
    window.addEventListener('pageshow', restore);
    window.addEventListener('orientationchange', restore);

    const path = location.pathname.replace(/\\/+$/, '');
    const map = [
      { key: 'home', match: (p) => p === '' || p === '/' },
      { key: 'shows', match: (p) => p === '/show-programs' || p.startsWith('/show-programs/') || p.startsWith('/prices') },
      { key: 'builder', match: (p) => p.startsWith('/party-builder') },
      { key: 'costumes', match: (p) => p === '/catalog' || p.startsWith('/catalog/') || p.startsWith('/character') },
      { key: 'profile', match: (p) => p.startsWith('/account') || p.startsWith('/login') || p.startsWith('/register') },
    ];
    const probe = path === '' ? '/' : path;
    const active = map.find((entry) => entry.match(probe));
    if (active) {
      const el = bar.querySelector(`[data-bottom-bar-key="${active.key}"]`);
      if (el) el.classList.add('is-active');
    }
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
</script>
""".strip()


STICKY_HEADER_FIX_BLOCK = """
<style id="site-sticky-header-fix-style">
@media (max-width: 860px) {
  html, body, #page, .site, .ast-container,
  .elementor-location-header, .elementor-location-header > * {
    transform: none !important;
    -webkit-transform: none !important;
    perspective: none !important;
    -webkit-perspective: none !important;
    filter: none !important;
    -webkit-filter: none !important;
  }
  #c-header.elementor-sticky.elementor-sticky--active {
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    width: 100% !important;
    z-index: 2147483645 !important;
    transform: none !important;
    -webkit-transform: none !important;
  }
}
</style>
<script id="site-sticky-header-fix-script">
(() => {
  const stripBodyTransform = () => {
    const targets = [document.documentElement, document.body, document.getElementById('page')];
    for (const el of targets) {
      if (!el) continue;
      const inline = el.getAttribute('style') || '';
      if (/transform\\s*:/i.test(inline)) {
        el.style.removeProperty('transform');
        el.style.removeProperty('-webkit-transform');
      }
    }
  };
  const init = () => {
    const isMobile = window.matchMedia && window.matchMedia('(max-width: 860px)').matches;
    if (!isMobile) return;
    stripBodyTransform();
    try {
      const obs = new MutationObserver(() => stripBodyTransform());
      obs.observe(document.documentElement, { attributes: true, attributeFilter: ['style'] });
      obs.observe(document.body, { attributes: true, attributeFilter: ['style'] });
    } catch (_) {}
    window.addEventListener('pageshow', stripBodyTransform);
    window.addEventListener('orientationchange', stripBodyTransform);
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
</script>
""".strip()


def fix_known_mojibake(html: str) -> str:
    for bad, good in MOJIBAKE_TEXT_REPLACEMENTS.items():
        html = html.replace(bad, good)
    return html


def normalize_header_html(header_html: str, settings: dict[str, bool]) -> str:
    header_html = header_html.replace('<a href="">', '<a href="/">', 1)
    if not settings["show_new_year_menu_link"]:
        header_html = remove_matching_list_items(header_html, SEASONAL_LINKS)
    header_html = header_html.replace('href="tg://resolve?phone=998998926565"', 'href="/register/"', 1)
    header_html = header_html.replace("Заказать праздник", "Зарегистрироваться", 1)
    header_html = replace_show_program_navigation_links(header_html)
    header_html = replace_live_button_icons(replace_instagram_references(header_html))
    return fix_known_mojibake(header_html)


def personalize_header_html(header_html: str, is_authenticated: bool) -> str:
    if not is_authenticated:
        return header_html

    header_html = header_html.replace('href="/register/"', 'href="/account/"', 1)
    header_html = header_html.replace("Зарегистрироваться", "Личный кабинет", 1)
    return replace_live_button_icons(header_html)


def replace_show_program_navigation_links(html: str) -> str:
    anchor_re = re.compile(
        r"<a\b(?=[^>]*\bhref=(['\"])/prices/?\1)[^>]*>.*?</a>",
        re.IGNORECASE | re.DOTALL,
    )

    def replace_anchor(match: re.Match[str]) -> str:
        anchor_html = match.group(0)
        anchor_text = BeautifulSoup(anchor_html, "html.parser").get_text(" ", strip=True)
        if not anchor_text:
            return anchor_html
        return re.sub(
            r"\bhref=(['\"])/prices/?\1",
            'href="/show-programs/"',
            anchor_html,
            count=1,
            flags=re.IGNORECASE,
        )

    return anchor_re.sub(replace_anchor, html)


def rewrite_legacy_public_urls(text: str) -> str:
    for old_value, new_value in LEGACY_PUBLIC_URL_REPLACEMENTS:
        text = text.replace(old_value, new_value)
    text = text.replace('<a href="">', '<a href="/">')
    return text


def build_runtime_page_bundle(page: PageBundle, *, is_authenticated: bool) -> PageBundle:
    if "v2" in (page.body_class or "").split():
        # v2 pages carry a clean chrome: only resolve the auth templates in the
        # header and skip every legacy WP transformation (head/header/footer/suffix
        # normalizers, seasonal assets, URL rewrites).
        from .v2_theme import personalize as personalize_v2_header

        return replace(page, header_html=personalize_v2_header(page.header_html, is_authenticated))

    runtime_page = replace(page, header_html=personalize_header_html(page.header_html, is_authenticated))
    return replace(
        runtime_page,
        head_html=rewrite_legacy_public_urls(runtime_page.head_html),
        body_prefix_html=rewrite_legacy_public_urls(runtime_page.body_prefix_html),
        header_html=rewrite_legacy_public_urls(runtime_page.header_html),
        content_html=rewrite_legacy_public_urls(runtime_page.content_html),
        footer_html=rewrite_legacy_public_urls(runtime_page.footer_html),
        body_suffix_html=rewrite_legacy_public_urls(runtime_page.body_suffix_html),
    )


def _strip_asset_tags(pattern: re.Pattern[str], html: str, asset_hints: tuple[str, ...]) -> str:
    if not asset_hints:
        return html

    def keep_or_remove(match: re.Match[str]) -> str:
        url = match.group("url")
        return "" if any(hint in url for hint in asset_hints) else match.group(0)

    return pattern.sub(keep_or_remove, html)


def optimize_managed_page_assets(head_html: str, body_suffix_html: str) -> tuple[str, str]:
    optimized_head = _strip_asset_tags(LINK_ASSET_TAG_RE, head_html, MANAGED_HEAD_ASSET_HINTS)
    optimized_head = _strip_asset_tags(SCRIPT_ASSET_TAG_RE, optimized_head, MANAGED_BODY_SCRIPT_HINTS)
    optimized_head = ROCKET_BEACON_INLINE_RE.sub("", optimized_head)
    optimized_head = MANAGED_WOO_EXTRA_INLINE_RE.sub("", optimized_head)
    optimized_body = _strip_asset_tags(SCRIPT_ASSET_TAG_RE, body_suffix_html, MANAGED_BODY_SCRIPT_HINTS)
    optimized_body = ROCKET_BEACON_INLINE_RE.sub("", optimized_body)
    optimized_body = MANAGED_WOO_EXTRA_INLINE_RE.sub("", optimized_body)
    return optimized_head, optimized_body


def strip_snow_assets(head_html: str, settings: dict[str, bool]) -> str:
    if settings["show_snow"]:
        return head_html
    head_html = SNOW_STYLE_RE.sub("", head_html)
    return SNOW_SCRIPT_RE.sub("", head_html)


def build_seasonal_override_css(settings: dict[str, bool]) -> str:
    visibility_rules: list[str] = []
    if not settings["show_snow"]:
        visibility_rules.append(
            """
.snow-container,
.snowflake {
    display: none !important;
}
""".strip()
        )
    if not settings["show_promotions"]:
        visibility_rules.append(
            """
.c-sales {
    display: none !important;
}
""".strip()
        )

    if visibility_rules:
        return SEASONAL_OVERRIDE_CSS_BASE.replace(
            '<style id="seasonal-site-overrides">',
            '<style id="seasonal-site-overrides">\n' + "\n\n".join(visibility_rules) + "\n",
            1,
        )
    return SEASONAL_OVERRIDE_CSS_BASE


def ensure_seasonal_override_css(head_html: str, settings: dict[str, bool]) -> str:
    if 'id="seasonal-site-overrides"' in head_html:
        return head_html
    return f"{head_html}\n{build_seasonal_override_css(settings)}"


EARLY_BODY_TRANSFORM_GUARD = """<style>html body{transform:none!important;-webkit-transform:none!important;perspective:none!important;filter:none!important;will-change:auto!important}</style>
<script>(function(){function f(){var b=document.body;if(!b)return;var s=getComputedStyle(b);if(s.transform&&s.transform!=='none'){b.style.setProperty('transform','none','important');b.style.setProperty('-webkit-transform','none','important')}}var t=setInterval(f,50);setTimeout(function(){clearInterval(t)},10000);if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',f)}else{f()}})();</script>"""


def normalize_head_html(head_html: str, settings: dict[str, bool]) -> str:
    head_html = ensure_seasonal_override_css(strip_snow_assets(head_html, settings), settings)
    head_html = SHOW_TABS_TELEGRAM_BINDING_RE.sub("", head_html)
    head_html = strip_wp_branding(head_html)
    head_html = replace_instagram_references(head_html)
    # Inject the very early containing-block guard at the very top of <head>
    if EARLY_BODY_TRANSFORM_GUARD not in head_html:
        head_html = EARLY_BODY_TRANSFORM_GUARD + "\n" + head_html
    return head_html


WP_BRANDING_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Yoast SEO comments referencing wordpress
    re.compile(r"<!--\s*This site is optimized with the Yoast SEO.*?-->\s*", re.DOTALL | re.IGNORECASE),
    re.compile(r"<!--\s*/\s*Yoast SEO.*?plugin\.\s*-->\s*", re.DOTALL | re.IGNORECASE),
    # Generator meta tags exposing the stack
    re.compile(r'<meta[^>]+name=["\']generator["\'][^>]*content=["\'][^"\']*(?:Elementor|WordPress|WP Rocket|Yoast)[^"\']*["\'][^>]*/?>\s*', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\'][^"\']*(?:WP Rocket|Yoast)[^"\']*["\'][^>]+name=["\']generator["\'][^>]*/?>\s*', re.IGNORECASE),
    # WP REST API discovery + RSD/EditURI link tags
    re.compile(r'<link[^>]+rel=["\']https://api\.w\.org/["\'][^>]*/?>\s*', re.IGNORECASE),
    re.compile(r'<link[^>]+rel=["\']EditURI["\'][^>]*/?>\s*', re.IGNORECASE),
    re.compile(r'<link[^>]+rel=["\']wlwmanifest["\'][^>]*/?>\s*', re.IGNORECASE),
    re.compile(r'<link[^>]+rel=["\']alternate["\'][^>]*type=["\']application/json["\'][^>]*href=["\'][^"\']*wp-json[^"\']*["\'][^>]*/?>\s*', re.IGNORECASE),
    # WP embed script
    re.compile(r'<script[^>]+id=["\']wp-embed-js["\'][^>]*>.*?</script>\s*', re.DOTALL | re.IGNORECASE),
)


def strip_wp_branding(html: str) -> str:
    """Remove publicly visible WordPress / Yoast / Elementor / WP Rocket markers.

    Keeps internal Elementor configs and asset URLs intact (those are required for
    legacy templates to render). Only strips identifying meta tags, comments and
    discovery links that leak the stack identity in "View Source".
    """
    if not html:
        return html
    for pattern in WP_BRANDING_PATTERNS:
        html = pattern.sub("", html)
    return html


def strip_wp_body_classes(html: str) -> str:
    """Remove cosmetic WordPress class names from <body class="...">.

    Keeps Astra theme classes (ast-*) since the legacy CSS depends on them.
    """
    if not html:
        return html

    def _replace_body_class(match: re.Match[str]) -> str:
        class_value = match.group(1)
        cleaned = re.sub(
            r"\b(?:wp-singular|wp-custom-logo|wp-embed-responsive|wp-theme-[^\s\"']+|theme-astra|woocommerce-no-js|woocommerce-page|woocommerce-js)\b",
            "",
            class_value,
        )
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return f'class="{cleaned}"'

    return re.sub(r'<body[^>]*\bclass="([^"]*)"', _replace_body_class, html, count=1, flags=re.IGNORECASE)


def strip_wp_body_class_string(class_value: str) -> str:
    """Same cleaning, but for the meta.json `body_class` string."""
    if not class_value:
        return class_value
    cleaned = re.sub(
        r"\b(?:wp-singular|wp-custom-logo|wp-embed-responsive|wp-theme-[^\s\"']+|theme-astra|woocommerce-no-js|woocommerce-page|woocommerce-js)\b",
        "",
        class_value,
    )
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def replace_instagram_references(text: str) -> str:
    text = INSTAGRAM_WIDGET_RE.sub(INSTAGRAM_PILL_HTML, text)
    for old_url in INSTAGRAM_URL_REPLACEMENTS:
        text = text.replace(old_url, NEW_INSTAGRAM_URL)
    return text.replace(OLD_INSTAGRAM_HANDLE, NEW_INSTAGRAM_HANDLE)


def replace_live_button_icons(text: str) -> str:
    replacements = {
        '<i aria-hidden="true" class="fas fa-arrow-down"></i>': PRICE_LIST_ICON_SVG,
        '<i aria-hidden="true" class="fas fa-arrow-right"></i>': LONG_ARROW_RIGHT_ICON_SVG,
        '<i aria-hidden="true" class="fas fa-long-arrow-alt-left"></i>': LONG_ARROW_LEFT_ICON_SVG,
        '<i aria-hidden="true" class="fas fa-long-arrow-alt-right"></i>': LONG_ARROW_RIGHT_ICON_SVG,
        '<i aria-hidden="true" class="fas fa-angle-left"></i>': CHEVRON_LEFT_ICON_SVG,
        '<i aria-hidden="true" class="fas fa-angle-right"></i>': CHEVRON_RIGHT_ICON_SVG,
        '<i aria-hidden="true" class="eicon-chevron-left"></i>': CHEVRON_LEFT_ICON_SVG,
        '<i aria-hidden="true" class="eicon-chevron-right"></i>': CHEVRON_RIGHT_ICON_SVG,
        '<i aria-hidden="true" class="fas fa-bars"></i>': MENU_ICON_SVG,
        '<i aria-hidden="true" class="fas fa-minus"></i>': MINUS_ICON_SVG,
        '<i aria-hidden="true" class="far fa-play-circle"></i>': PLAY_CIRCLE_ICON_SVG,
        '<i aria-hidden="true" class="fab fa-telegram-plane"></i>': ACCOUNT_ICON_SVG,
        '<i aria-hidden="true" class="fas fa-user"></i>': ACCOUNT_ICON_SVG,
    }
    for source, replacement in replacements.items():
        text = text.replace(source, replacement)
    return text


def replace_visible_years(text: str) -> str:
    if "2025" not in text:
        return text

    parts = PROTECTED_BLOCK_RE.split(text)
    normalized_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if PROTECTED_BLOCK_RE.fullmatch(part):
            normalized_parts.append(part)
            continue

        html_parts = HTML_TAG_RE.split(part)
        for index in range(0, len(html_parts), 2):
            html_parts[index] = html_parts[index].replace("2025", "2026")
        normalized_parts.append("".join(html_parts))

    return "".join(normalized_parts)


def move_matching_list_items_to_end(html: str, link_fragments: tuple[str, ...]) -> str:
    def reorder(match: re.Match[str]) -> str:
        start_tag, body, end_tag = match.groups()
        items = LI_BLOCK_RE.findall(body)
        if not items or LI_BLOCK_RE.sub("", body).strip():
            return match.group(0)

        regular_items: list[str] = []
        seasonal_items: list[str] = []
        for item in items:
            target = seasonal_items if any(fragment in item for fragment in link_fragments) else regular_items
            target.append(item)

        if not seasonal_items:
            return match.group(0)

        return f"{start_tag}{''.join(regular_items + seasonal_items)}{end_tag}"

    return UL_RE.sub(reorder, html)


def remove_matching_list_items(html: str, link_fragments: tuple[str, ...]) -> str:
    def filter_items(match: re.Match[str]) -> str:
        start_tag, body, end_tag = match.groups()
        items = LI_BLOCK_RE.findall(body)
        if not items or LI_BLOCK_RE.sub("", body).strip():
            return match.group(0)

        kept_items = [item for item in items if not any(fragment in item for fragment in link_fragments)]
        if len(kept_items) == len(items):
            return match.group(0)

        return f"{start_tag}{''.join(kept_items)}{end_tag}"

    return UL_RE.sub(filter_items, html)


def move_seasonal_product_cards_to_end(content_html: str) -> str:
    def reorder(match: re.Match[str]) -> str:
        start_tag, body, end_tag = match.groups()
        items = LI_BLOCK_RE.findall(body)
        if not items or LI_BLOCK_RE.sub("", body).strip():
            return match.group(0)

        regular_items: list[str] = []
        seasonal_items: list[str] = []
        for item in items:
            target = seasonal_items if any(marker in item for marker in SEASONAL_PRODUCT_MARKERS) else regular_items
            target.append(item)

        if not seasonal_items:
            return match.group(0)

        return f"{start_tag}{''.join(regular_items + seasonal_items)}{end_tag}"

    return PRODUCTS_UL_RE.sub(reorder, content_html)


def extract_div_block(html: str, marker: str) -> tuple[int, int] | None:
    marker_index = html.find(marker)
    if marker_index == -1:
        return None

    block_start = html.rfind("<div", 0, marker_index)
    if block_start == -1:
        return None

    depth = 0
    for token_match in re.finditer(r"<div\b|</div>", html[block_start:], re.IGNORECASE):
        token = token_match.group(0).lower()
        if token == "<div":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                block_end = block_start + token_match.end()
                return block_start, block_end

    return None


def extract_button_block(html: str, button_id: str) -> tuple[int, int] | None:
    button_re = re.compile(
        rf"<button\b[^>]*\bid=\"{re.escape(button_id)}\"[^>]*>.*?</button>\s*",
        re.IGNORECASE | re.DOTALL,
    )
    match = button_re.search(html)
    if not match:
        return None
    return match.start(), match.end()


def strip_blocks(html: str, blocks: list[tuple[int, int]]) -> str:
    for start, end in sorted(blocks, reverse=True):
        html = html[:start] + html[end:]
    return html


def insert_before_container_close(html: str, marker: str, inner_html: str) -> str:
    block = extract_div_block(html, marker)
    if not block:
        return html

    start, end = block
    container_html = html[start:end]
    close_index = container_html.rfind("</div>")
    if close_index == -1:
        return html

    updated_container = f"{container_html[:close_index]}{inner_html}{container_html[close_index:]}"
    return f"{html[:start]}{updated_container}{html[end:]}"


def set_tag_attribute(tag_html: str, attribute: str, value: str) -> str:
    return re.sub(rf'({attribute}=")[^"]*(")', rf"\g<1>{value}\2", tag_html, count=1)


def set_tag_order(tag_html: str, order: int) -> str:
    return re.sub(r"(--n-tabs-title-order:\s*)\d+", rf"\g<1>{order}", tag_html, count=1)


def set_tag_class_token(tag_html: str, token: str, enabled: bool) -> str:
    class_match = re.search(r'class="([^"]*)"', tag_html)
    if not class_match:
        return tag_html

    classes = [item for item in class_match.group(1).split() if item]
    if enabled:
        if token not in classes:
            classes.insert(0, token)
    else:
        classes = [item for item in classes if item != token]

    updated_classes = " ".join(classes)
    start, end = class_match.span(1)
    return f"{tag_html[:start]}{updated_classes}{tag_html[end:]}"


def update_tag_by_id(html: str, tag_name: str, tag_id: str, transform: Callable[[str], str]) -> str:
    pattern = re.compile(rf"<{tag_name}\b[^>]*\bid=\"{re.escape(tag_id)}\"[^>]*>", re.IGNORECASE)
    return pattern.sub(lambda match: transform(match.group(0)), html, count=1)


def configure_tab_button(html: str, button_id: str, order: int, active: bool) -> str:
    return update_tag_by_id(
        html,
        "button",
        button_id,
        lambda tag: set_tag_attribute(
            set_tag_attribute(
                set_tag_attribute(set_tag_order(tag, order), "data-tab-index", str(order)),
                "aria-selected",
                "true" if active else "false",
            ),
            "tabindex",
            "0" if active else "-1",
        ),
    )


def configure_tab_panel(html: str, panel_id: str, order: int, active: bool) -> str:
    return update_tag_by_id(
        html,
        "div",
        panel_id,
        lambda tag: set_tag_class_token(
            set_tag_attribute(set_tag_order(tag, order), "data-tab-index", str(order)),
            "e-active",
            active,
        ),
    )


def reorder_tab_widget(
    content_html: str,
    widget_number: str,
    button_order: list[str],
    panel_order: list[str],
    active_button: str,
    active_panel: str,
) -> str:
    widget_block = extract_div_block(content_html, f'data-widget-number="{widget_number}"')
    if not widget_block:
        return content_html

    widget_start, widget_end = widget_block
    widget_html = content_html[widget_start:widget_end]

    button_ranges = [extract_button_block(widget_html, button_id) for button_id in button_order]
    panel_ranges = [extract_div_block(widget_html, f'id="{panel_id}"') for panel_id in panel_order]
    if any(block is None for block in button_ranges) or any(block is None for block in panel_ranges):
        return content_html

    button_blocks = [widget_html[start:end].strip() for start, end in button_ranges if start is not None]
    panel_blocks = [widget_html[start:end].strip() for start, end in panel_ranges if start is not None]
    widget_html = strip_blocks(
        widget_html,
        [*(block for block in button_ranges if block is not None), *(block for block in panel_ranges if block is not None)],
    )
    widget_html = insert_before_container_close(widget_html, 'class="e-n-tabs-heading"', "\n" + "\n".join(button_blocks) + "\n")
    widget_html = insert_before_container_close(widget_html, 'class="e-n-tabs-content"', "\n" + "\n".join(panel_blocks) + "\n")

    for order, button_id in enumerate(button_order, start=1):
        widget_html = configure_tab_button(widget_html, button_id, order=order, active=button_id == active_button)

    for order, panel_id in enumerate(panel_order, start=1):
        widget_html = configure_tab_panel(widget_html, panel_id, order=order, active=panel_id == active_panel)

    return f"{content_html[:widget_start]}{widget_html}{content_html[widget_end:]}"


def normalize_price_list_links(content_html: str) -> str:
    return PRICE_LIST_LINK_RE.sub(
        lambda match: f'<li class="{match.group(1)}">{match.group(2)}</li>',
        content_html,
    )


def _resolve_show_program_slug(raw_text: str) -> str:
    normalized = " ".join(raw_text.casefold().split())
    if "серпантин" in normalized:
        return "streamer-show"
    if "шаров" in normalized or "шаровое" in normalized:
        return "balloon-show"
    if "крио" in normalized:
        return "cryo-show"
    if "ленточ" in normalized or "серебрян" in normalized:
        return "ribbon-show"
    return ""


def _show_program_button_context(link) -> str:
    current = link
    longest_text = ""
    while current is not None:
        if not getattr(current, "get", None):
            current = current.parent
            continue

        classes = set(current.get("class") or [])
        current_text = " ".join(current.stripped_strings)
        if "swiper-slide" in classes and current_text:
            return current_text
        if "e-con" in classes and "e-child" in classes and len(current_text) > len(longest_text):
            longest_text = current_text
        current = current.parent
    return longest_text or " ".join(link.stripped_strings)


def replace_show_program_order_links(content_html: str) -> str:
    soup = BeautifulSoup(content_html, "html.parser")
    is_updated = False

    for link in soup.select("a.elementor-button"):
        button_text = " ".join(link.stripped_strings).casefold()
        if "заказать" not in button_text:
            continue

        program_slug = _resolve_show_program_slug(_show_program_button_context(link))
        link["href"] = f"/party-builder/?program={program_slug}" if program_slug else "/party-builder/"
        is_updated = True

    return str(soup) if is_updated else content_html


def remove_list_item_by_index(html: str, block_marker: str, item_index: int) -> str:
    block = extract_div_block(html, block_marker)
    if not block:
        return html

    block_start, block_end = block
    block_html = html[block_start:block_end]
    ul_match = UL_RE.search(block_html)
    if not ul_match:
        return html

    start_tag, body, end_tag = ul_match.groups()
    items = LI_BLOCK_RE.findall(body)
    if item_index < 0 or item_index >= len(items):
        return html

    del items[item_index]
    updated_ul = f"{start_tag}{''.join(items)}{end_tag}"
    updated_block = f"{block_html[:ul_match.start()]}{updated_ul}{block_html[ul_match.end():]}"
    return f"{html[:block_start]}{updated_block}{html[block_end:]}"


def replace_footer_promo_column(footer_html: str) -> str:
    block = extract_div_block(footer_html, FOOTER_PROMO_COLUMN_MARKER)
    if not block:
        return footer_html

    block_start, block_end = block
    return f"{footer_html[:block_start]}{build_footer_popular_html()}{footer_html[block_end:]}"


def build_footer_popular_html() -> str:
    try:
        from .catalog_store import ENTITY_TYPE_SHOW_PROGRAM, list_characters_for_public

        shows = list_characters_for_public(entity_type=ENTITY_TYPE_SHOW_PROGRAM)
    except Exception:
        shows = []

    cards: list[str] = []
    for show in shows[:2]:
        name = _site_text(show.get("name"), "Шоу-программа")
        slug = _site_text(show.get("slug"))
        if not slug:
            continue
        route = f"/show-programs/{slug}/"
        public_path = str(show.get("hero_file_path") or "").strip()
        if _site_public_file_exists(public_path):
            media = '<img alt="{alt}" class="site-footer-popular-card__image" loading="lazy" src="{src}"/>'.format(
                alt=html_lib.escape(name, quote=True),
                src=html_lib.escape(public_path, quote=True),
            )
        else:
            media = _site_media_html(public_path, name, "site-footer-popular-card__image")
        cards.append(
            """
            <a class="site-footer-popular-card" href="{route}">
              <span class="site-footer-popular-card__media">{media}</span>
              <span class="site-footer-popular-card__content">
                <span class="site-footer-popular-card__copy">
                  <span class="site-footer-popular-card__eyebrow">Шоу-программа</span>
                  <span class="site-footer-popular-card__title">{name}</span>
                </span>
                <span aria-hidden="true" class="site-footer-popular-card__arrow">→</span>
              </span>
            </a>
            """.format(
                route=html_lib.escape(route, quote=True),
                media=media,
                name=html_lib.escape(name),
            )
        )

    if not cards:
        cards.append(
            """
            <a class="site-footer-popular-card" href="/show-programs/">
              <span class="site-footer-popular-card__media">
                <span class="site-footer-popular-card__image surpriz-image-placeholder" role="img" aria-label="Шоу-программы">
                  <span>Surpriz</span><small>Каталог</small>
                </span>
              </span>
              <span class="site-footer-popular-card__content">
                <span class="site-footer-popular-card__copy">
                  <span class="site-footer-popular-card__eyebrow">Каталог</span>
                  <span class="site-footer-popular-card__title">Шоу-программы</span>
                </span>
                <span aria-hidden="true" class="site-footer-popular-card__arrow">→</span>
              </span>
            </a>
            """
        )

    return (
        '<div class="elementor-element elementor-element-09f65f6 e-con-full e-flex e-con e-child" data-element_type="container" data-id="09f65f6">'
        '<div class="elementor-element elementor-element-a007c22 elementor-widget elementor-widget-heading" data-element_type="widget" data-id="a007c22" data-widget_type="heading.default">'
        '<span class="elementor-heading-title elementor-size-default">Популярные:</span> </div>'
        f'<div class="site-footer-popular">{"".join(cards)}</div>'
        "</div>"
    )


def reprioritize_show_tabs(content_html: str) -> str:
    content_html = reorder_tab_widget(
        content_html,
        widget_number="72646540",
        button_order=[
            "price1",
            "e-n-tab-title-726465402",
            "e-n-tab-title-726465404",
            "e-n-tab-title-726465405",
            "e-n-tab-title-726465406",
            "e-n-tab-title-726465401",
        ],
        panel_order=[
            "e-n-tab-content-726465403",
            "e-n-tab-content-726465402",
            "e-n-tab-content-726465404",
            "e-n-tab-content-726465405",
            "e-n-tab-content-726465406",
            "e-n-tab-content-726465401",
        ],
        active_button="price1",
        active_panel="e-n-tab-content-726465403",
    )
    content_html = reorder_tab_widget(
        content_html,
        widget_number="1535721108",
        button_order=[
            "price1",
            "e-n-tab-title-15357211082",
            "e-n-tab-title-15357211083",
            "e-n-tab-title-15357211085",
            "e-n-tab-title-15357211086",
            "e-n-tab-title-15357211087",
            "e-n-tab-title-15357211081",
        ],
        panel_order=[
            "e-n-tab-content-15357211084",
            "e-n-tab-content-15357211082",
            "e-n-tab-content-15357211083",
            "e-n-tab-content-15357211085",
            "e-n-tab-content-15357211086",
            "e-n-tab-content-15357211087",
            "e-n-tab-content-15357211081",
        ],
        active_button="price1",
        active_panel="e-n-tab-content-15357211084",
    )
    return normalize_price_list_links(content_html)


def remove_home_new_year_showcase(content_html: str) -> str:
    blocks: list[tuple[int, int]] = []
    for marker in ('data-id="233f31b"', 'data-id="787a0ed"'):
        block = extract_div_block(content_html, marker)
        if block:
            blocks.append(block)

    for start, end in sorted(blocks, reverse=True):
        content_html = content_html[:start] + content_html[end:]

    return content_html


def replace_home_primary_cta(content_html: str) -> str:
    block = extract_div_block(content_html, 'data-id="a22ba81"')
    if not block:
        return content_html

    start, end = block
    block_html = content_html[start:end]
    block_html = block_html.replace('href="tel:+998%20(99)%20892-65-65"', 'href="/party-builder/"', 1)
    block_html = block_html.replace(" +998 (99) 892-65-65", "Собрать праздник", 1)
    return f"{content_html[:start]}{block_html}{content_html[end:]}"


def _site_public_file_exists(public_path: object) -> bool:
    normalized = str(public_path or "").strip()
    if not normalized:
        return False
    if normalized.startswith(("http://", "https://", "//")):
        return True
    if not normalized.startswith("/"):
        return False

    if normalized.startswith("/_assets/content/"):
        normalized = normalized.replace("/_assets/content/", "/wp-content/", 1)
    elif normalized.startswith("/_assets/includes/"):
        normalized = normalized.replace("/_assets/includes/", "/wp-includes/", 1)

    return (STATIC_ROOT / normalized.lstrip("/")).exists()


def _site_format_money(value: object) -> str:
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return "цену уточним"
    return f"от {amount:,}".replace(",", " ") + " сум"


def _site_format_duration(value: object) -> str:
    try:
        minutes = int(value or 0)
    except (TypeError, ValueError):
        minutes = 0
    if minutes <= 0:
        return "длительность уточним"
    if minutes == 60:
        return "1 час"
    if minutes % 60 == 0:
        return f"{minutes // 60} ч"
    return f"{minutes} мин"


def _site_text(value: object, fallback: str = "") -> str:
    return str(value or fallback).strip() or fallback


def _site_short_text(value: object, fallback: str, limit: int = 190) -> str:
    text = _site_text(value, fallback)
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(".,;:") + "..."


def _site_media_html(public_path: object, alt: str, class_name: str) -> str:
    normalized = str(public_path or "").strip()
    escaped_alt = html_lib.escape(alt, quote=True)
    if _site_public_file_exists(normalized):
        escaped_src = html_lib.escape(normalized, quote=True)
        return f'<img alt="{escaped_alt}" decoding="async" loading="lazy" src="{escaped_src}">'
    return (
        f'<span class="{class_name} surpriz-image-placeholder" role="img" aria-label="{escaped_alt}">'
        "<span>Surpriz</span><small>Фото скоро</small></span>"
    )


def _site_footer_popular_links_html() -> str:
    try:
        from .catalog_store import ENTITY_TYPE_SHOW_PROGRAM, list_characters_for_public

        shows = list_characters_for_public(entity_type=ENTITY_TYPE_SHOW_PROGRAM)
    except Exception:
        shows = []

    links: list[str] = []
    for show in shows[:4]:
        name = _site_text(show.get("name"), "Шоу-программа")
        slug = _site_text(show.get("slug"))
        if not slug:
            continue
        meta = f"{_site_format_duration(show.get('default_duration_minutes'))} · {_site_format_money(show.get('base_price'))}"
        links.append(
            '<a href="{href}"><strong>{name}</strong><span>{meta}</span></a>'.format(
                href=html_lib.escape(f"/show-programs/{slug}/", quote=True),
                name=html_lib.escape(name),
                meta=html_lib.escape(meta),
            )
        )

    if not links:
        links.append(
            '<a href="/show-programs/"><strong>Шоу-программы</strong><span>Каталог скоро появится</span></a>'
        )

    return "".join(links)


def _site_footer_privacy_html() -> str:
    candidates = ("privacy-policy", "politika-konfidencialnosti")
    for candidate in candidates:
        if (ROUTES_ROOT / candidate / "meta.json").exists():
            return f'<a href="/{candidate}/">Политика конфиденциальности</a>'
    return ""


def build_site_footer_html() -> str:
    logo = ""
    if _site_public_file_exists(SITE_LOGO_URL):
        logo = (
            '<img alt="Surpriz" decoding="async" loading="lazy" '
            f'src="{html_lib.escape(SITE_LOGO_URL, quote=True)}">'
        )
    else:
        logo = "<span>Surpriz</span>"

    return f"""
    <footer class="surpriz-site-footer" role="contentinfo">
      <div class="surpriz-site-footer__inner">
        <section class="surpriz-site-footer__brand" aria-label="Surpriz">
          <a class="surpriz-site-footer__logo" href="/">{logo}</a>
          <p>Организуем детские праздники, аниматоров и шоу-программы в Ташкенте.</p>
        </section>

        <section class="surpriz-site-footer__section" aria-label="Контакты">
          <h2 class="surpriz-site-footer__title">Контакты</h2>
          <a class="surpriz-site-footer__contact surpriz-site-footer__contact--phone" href="tel:{SITE_PHONE_TEL}">
            {SITE_PHONE_DISPLAY}
          </a>
          <a class="surpriz-site-footer__contact" href="{SITE_TELEGRAM_URL}" rel="noopener noreferrer" target="_blank">Telegram</a>
          <a class="surpriz-site-footer__contact" href="{NEW_INSTAGRAM_URL}" rel="noopener noreferrer" target="_blank">Instagram</a>
        </section>

        <nav class="surpriz-site-footer__section" aria-label="Навигация">
          <h2 class="surpriz-site-footer__title">Навигация</h2>
          <ul class="surpriz-site-footer__links">
            <li><a href="/">Главная</a></li>
            <li><a href="/show-programs/">Шоу-программы</a></li>
            <li><a href="/catalog/">Каталог персонажей</a></li>
            <li><a href="/o-nas/">О Нас</a></li>
            <li><a href="/contacts/">Контакты</a></li>
          </ul>
        </nav>

        <section class="surpriz-site-footer__section" aria-label="Быстрые действия">
          <h2 class="surpriz-site-footer__title">Быстро</h2>
          <div class="surpriz-site-footer__actions">
            <a class="surpriz-site-footer__button" href="/party-builder/">Собрать праздник</a>
            <a class="surpriz-site-footer__button surpriz-site-footer__button--ghost" href="/account/">Личный кабинет</a>
            <a class="surpriz-site-footer__button surpriz-site-footer__button--ghost" href="/register/">Регистрация</a>
            <a class="surpriz-site-footer__button surpriz-site-footer__button--ghost" href="tel:{SITE_PHONE_TEL}">Позвонить</a>
          </div>
        </section>

        <section class="surpriz-site-footer__section surpriz-site-footer__section--popular" aria-label="Популярные шоу">
          <h2 class="surpriz-site-footer__title">Популярные шоу</h2>
          <div class="surpriz-site-footer__popular">{_site_footer_popular_links_html()}</div>
        </section>
      </div>

      <div class="surpriz-site-footer__bottom">
        <span>© 2026 Surpriz. Детские праздники в Ташкенте.</span>
        {_site_footer_privacy_html()}
      </div>
    </footer>
    """.strip()


def build_home_mobile_funnel_html() -> str:
    actions = (
        ("/show-programs/", "1", "Выбрать шоу", "Готовые программы для праздника"),
        ("/catalog/", "2", "Выбрать персонажа", "Любимые герои и костюмы"),
        ("/party-builder/", "3", "Собрать праздник", "Сценарий под вашу дату"),
        ("tel:+998998926565", "4", "Позвонить", "Быстро уточним детали"),
        (NEW_INSTAGRAM_URL, "5", "Instagram", "Посмотреть живые праздники"),
    )
    action_html = []
    for href, number, title, hint in actions:
        action_html.append(
            '<a class="surpriz-home-funnel__action" href="{href}">'
            '<span class="surpriz-home-funnel__number">{number}</span>'
            '<span class="surpriz-home-funnel__title">{title}</span>'
            '<span class="surpriz-home-funnel__hint">{hint}</span>'
            "</a>".format(
                href=html_lib.escape(href, quote=True),
                number=html_lib.escape(number),
                title=html_lib.escape(title),
                hint=html_lib.escape(hint),
            )
        )
    return (
        '<section class="surpriz-home-funnel" aria-label="Быстрый выбор праздника">'
        '<span class="surpriz-home-funnel__eyebrow">Быстрый старт</span>'
        "<h2>С чего начнём праздник?</h2>"
        "<p>Выберите готовое шоу, персонажа или сразу соберите праздник. Всё важное доступно с первого экрана телефона.</p>"
        f'<div class="surpriz-home-funnel__actions">{"".join(action_html)}</div>'
        "</section>"
    )


def build_home_show_programs_html() -> str:
    try:
        from .catalog_store import ENTITY_TYPE_SHOW_PROGRAM, list_characters_for_public
        from .customer_store import _attach_program_promotions

        shows = list_characters_for_public(entity_type=ENTITY_TYPE_SHOW_PROGRAM)
    except Exception:
        shows = []
        _attach_program_promotions = None

    cards: list[str] = []
    for show in shows[:6]:
        show_item = dict(show)
        if _attach_program_promotions:
            _attach_program_promotions(show_item)

        name = _site_text(show_item.get("name"), "Шоу-программа")
        slug = _site_text(show_item.get("slug"))
        if not slug:
            continue
        route = f"/show-programs/{slug}/"
        builder_url = f"/party-builder/?program={slug}"
        summary = _site_short_text(
            show_item.get("short_description") or show_item.get("description"),
            "Описание шоу-программы скоро появится.",
            limit=180,
        )
        media = _site_media_html(show_item.get("hero_file_path"), name, "surpriz-home-show-card__placeholder")
        promotion_badge_text = ""
        for promo in show_item.get("promotions") or []:
            promotion_badge_text = _site_text((promo or {}).get("badge_text") or (promo or {}).get("title"))
            if promotion_badge_text:
                break
        cards.append(
            """
            <article class="surpriz-home-show-card">
              <a class="surpriz-home-show-card__media" href="{route}">{media}</a>
              <div class="surpriz-home-show-card__body">
                <h3><a href="{route}">{name}</a></h3>
                <div class="surpriz-home-show-card__badges">
                  <span class="surpriz-home-show-card__price">{price}</span>
                  <span class="surpriz-home-show-card__duration">{duration}</span>
                  <span class="surpriz-promo-badge">{promotion_badge_text}</span>
                </div>
                <p>{summary}</p>
                <div class="surpriz-home-show-card__actions">
                  <a class="surpriz-home-show-card__button" href="{builder_url}">Собрать</a>
                  <a class="surpriz-home-show-card__button surpriz-home-show-card__button--ghost" href="{route}">Подробнее</a>
                </div>
              </div>
            </article>
            """.format(
                route=html_lib.escape(route, quote=True),
                builder_url=html_lib.escape(builder_url, quote=True),
                media=media,
                name=html_lib.escape(name),
                price=html_lib.escape(_site_format_money(show_item.get("base_price"))),
                duration=html_lib.escape(_site_format_duration(show_item.get("default_duration_minutes"))),
                summary=html_lib.escape(summary),
                promotion_badge_text=html_lib.escape(promotion_badge_text),
            )
        )

    if cards:
        body = f'<div class="surpriz-home-shows__grid">{"".join(cards)}</div>'
    else:
        body = (
            '<div class="surpriz-home-shows__empty">'
            "<h3>Шоу-программы скоро появятся</h3>"
            "<p>Каталог уже подключён к админке. После добавления активных шоу они появятся здесь автоматически.</p>"
            '<a class="surpriz-home-shows__empty-link" href="/catalog/">Посмотреть персонажей</a>'
            "</div>"
        )

    return (
        '<section class="surpriz-home-shows" aria-labelledby="surpriz-home-shows-title">'
        '<div class="surpriz-home-shows__head">'
        "<div>"
        '<span class="surpriz-home-shows__eyebrow">Каталог праздников</span>'
        '<h2 id="surpriz-home-shows-title">Шоу-программы</h2>'
        '<p class="surpriz-home-shows__lead">Выберите готовую программу из админки, откройте детали или сразу соберите праздник.</p>'
        "</div>"
        '<a class="surpriz-home-shows__all" href="/show-programs/">Все шоу-программы</a>'
        "</div>"
        f"{body}"
        '<a class="surpriz-home-shows__all surpriz-home-shows__all--bottom" href="/show-programs/">Все шоу-программы</a>'
        "</section>"
    )


def insert_home_mobile_funnel(content_html: str) -> str:
    if "surpriz-home-funnel" in content_html:
        return content_html
    block = extract_div_block(content_html, 'data-id="8ee8cbd"')
    if not block:
        return content_html
    _, end = block
    return f"{content_html[:end]}{build_home_mobile_funnel_html()}{content_html[end:]}"


def remove_home_mobile_funnel(content_html: str) -> str:
    block = extract_div_block(content_html, "surpriz-home-funnel")
    if not block:
        return content_html
    start, end = block
    return f"{content_html[:start]}{content_html[end:]}"


def remove_home_legacy_heavy_blocks(content_html: str) -> str:
    blocks: list[tuple[int, int]] = []
    for marker in ('data-id="6e0e1c7"', " c-sales "):
        block = extract_div_block(content_html, marker)
        if block:
            blocks.append(block)

    for start, end in sorted(set(blocks), reverse=True):
        content_html = content_html[:start] + content_html[end:]

    return content_html


def replace_home_secondary_cta(content_html: str) -> str:
    block = extract_div_block(content_html, 'data-id="eb5d43d"')
    if not block:
        return content_html

    start, end = block
    block_html = content_html[start:end]
    block_html = block_html.replace('href="#prices"', 'href="/show-programs/"', 1)
    block_html = block_html.replace("Прайс-лист", "Шоу-программы", 1)
    return f"{content_html[:start]}{block_html}{content_html[end:]}"


def replace_home_show_programs_block(content_html: str) -> str:
    block = extract_div_block(content_html, 'id="prices"')
    if block:
        start, end = block
        return f"{content_html[:start]}{build_home_show_programs_html()}{content_html[end:]}"
    if "surpriz-home-shows" in content_html:
        return content_html
    return f"{content_html}{build_home_show_programs_html()}"


def remove_contacts_instagram_widget(content_html: str) -> str:
    block = extract_div_block(content_html, 'data-id="18c892b"')
    if not block:
        return content_html
    start, end = block
    return f"{content_html[:start]}{content_html[end:]}"


def normalize_content_html(content_html: str, settings: dict[str, bool], requested_path: str) -> str:
    if settings["new_year_season_enabled"]:
        content_html = normalize_price_list_links(content_html)
    else:
        content_html = move_matching_list_items_to_end(content_html, SEASONAL_LINKS)
        content_html = move_seasonal_product_cards_to_end(content_html)
        content_html = reprioritize_show_tabs(content_html)

    if not settings["show_home_new_year_showcase"]:
        content_html = remove_home_new_year_showcase(content_html)

    if requested_path in {"", "index"}:
        content_html = remove_home_legacy_heavy_blocks(content_html)
        content_html = remove_home_mobile_funnel(content_html)
        content_html = replace_home_primary_cta(content_html)
        content_html = replace_home_secondary_cta(content_html)
        content_html = replace_home_show_programs_block(content_html)

    if requested_path.rstrip("/") == "prices":
        content_html = replace_show_program_order_links(content_html)

    if requested_path.rstrip("/") == "contacts":
        content_html = remove_contacts_instagram_widget(content_html)

    content_html = replace_instagram_references(content_html)
    return replace_live_button_icons(replace_visible_years(content_html))


def normalize_footer_html(footer_html: str, settings: dict[str, bool]) -> str:
    return build_site_footer_html()


def normalize_body_suffix_html(body_suffix_html: str, settings: dict[str, bool]) -> str:
    if settings["show_new_year_menu_link"]:
        if not settings["new_year_season_enabled"]:
            body_suffix_html = move_matching_list_items_to_end(body_suffix_html, SEASONAL_LINKS)
    else:
        body_suffix_html = remove_matching_list_items(body_suffix_html, SEASONAL_LINKS)

    body_suffix_html = body_suffix_html.replace('href="tg://resolve?phone=998998926565"', 'href="/register/"')
    body_suffix_html = body_suffix_html.replace("Заказать праздник", "Зарегистрироваться")
    body_suffix_html = replace_show_program_navigation_links(body_suffix_html)
    body_suffix_html = replace_instagram_references(body_suffix_html)
    body_suffix_html = replace_live_button_icons(replace_visible_years(body_suffix_html))
    if 'id="site-show-tabs-swiper-fix"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{SHOW_TABS_SWIPER_FIX_SCRIPT}"
    if 'id="site-mobile-menu-layout-final-fix"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{MOBILE_MENU_LAYOUT_FINAL_STYLE}"
    if 'id="site-mobile-menu-popup-fix"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{MOBILE_MENU_POPUP_FIX_SCRIPT}"
    if 'id="site-video-lightbox-fallback-script"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{VIDEO_LIGHTBOX_FALLBACK_BLOCK}"
    if 'id="site-catalog-menu-dropdown"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{CATALOG_MENU_DROPDOWN_SCRIPT}"
    if 'id="site-mobile-bottom-bar"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{MOBILE_BOTTOM_BAR_BLOCK}"
    if 'id="site-sticky-header-fix-script"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{STICKY_HEADER_FIX_BLOCK}"
    if 'id="home-popular-grid-fix"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{HOME_POPULAR_GRID_BLOCK}"
    if 'id="catalog-mobile-hero"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{CATALOG_MOBILE_HERO_BLOCK}"
    if 'id="catalog-transition"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{CATALOG_TRANSITION_BLOCK}"
    if 'id="global-motion"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{GLOBAL_MOTION_BLOCK}"
    if not get_public_settings().get("hide_easter_egg") and 'id="catalog-easter-egg"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{CATALOG_EASTER_EGG_BLOCK}"
    if os.environ.get("STAGEWISE") == "1" and 'id="surpriz-inspect-overlay"' not in body_suffix_html:
        body_suffix_html = f"{body_suffix_html}\n{INSPECT_OVERLAY_BLOCK}"
    return fix_known_mojibake(body_suffix_html)


@lru_cache(maxsize=512)
def load_page_bundle(requested_path: str) -> PageBundle | None:
    bundle_root = ROUTES_ROOT / route_bundle_path(requested_path)
    meta_path = bundle_root / "meta.json"
    if not meta_path.exists():
        return None

    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    settings = get_public_settings()
    return PageBundle(
        route=meta["route"],
        title=meta["title"].replace("2025", "2026"),
        lang=meta.get("lang", "ru-RU"),
        body_class=strip_wp_body_class_string(meta.get("body_class", "")),
        head_html=normalize_head_html(read_text(bundle_root / "head.html"), settings),
        body_prefix_html=replace_instagram_references(replace_visible_years(strip_wp_body_classes(read_text(bundle_root / "body_prefix.html")))),
        header_html=normalize_header_html(read_text(bundle_root / "header.html"), settings),
        content_html=normalize_content_html(read_text(bundle_root / "content.html"), settings, requested_path),
        footer_html=normalize_footer_html(read_text(bundle_root / "footer.html"), settings),
        body_suffix_html=normalize_body_suffix_html(read_text(bundle_root / "body_suffix.html"), settings),
    )
