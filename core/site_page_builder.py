from __future__ import annotations

from .loader import PageBundle
from .v2_theme import render_v2_page

DEFAULT_OG_IMAGE = "/surpriz/assets/img/show-programs/hero-desktop.webp"


def _guess_active(route: str) -> str:
    """Map a site-page route to a v2 header active key."""
    normalized = route.strip().lower()
    if normalized.startswith("/party-builder"):
        return "builder"
    if normalized.startswith("/account"):
        return "account"
    if normalized.startswith(("/login", "/register")):
        return "auth"
    if normalized.startswith("/show-programs"):
        return "shows"
    if normalized.startswith(("/catalog", "/character")):
        return "catalog"
    if normalized.startswith("/contacts"):
        return "contacts"
    if normalized.startswith("/prices"):
        return "prices"
    return ""


def build_site_page_bundle(
    *,
    reference_route: str = "",
    route: str,
    title: str,
    description: str,
    content_html: str,
    og_image: str = "",
    extra_head_html: str = "",
    active: str = "",
    extra_body_class: str = "",
) -> PageBundle:
    """Assemble a customer/site page on the clean v2 chrome.

    ``reference_route`` is kept for backward compatibility and ignored: the v2
    chrome no longer derives from a frozen WordPress bundle.
    """
    canonical_path = route if route.startswith("/") else f"/{route.lstrip('/')}"
    return render_v2_page(
        content_html,
        title=title,
        description=description,
        canonical_path=canonical_path,
        og_image=og_image or DEFAULT_OG_IMAGE,
        active=active or _guess_active(canonical_path),
        extra_head_html=extra_head_html,
        extra_body_class=extra_body_class,
    )
