"""v3 cinematic scroll-driven microsite (/v3/).

Standalone page: does not use v2_theme/PageBundle. Collects real show-program
data for the final interactive catalog rail and renders
templates/site/v3_cinematic.html.
"""

from __future__ import annotations

from flask import render_template

from .catalog_site import _show_program_summary
from .config import STATIC_ROOT
from .customer_store import list_show_programs_grouped_for_public


_CARD_THUMBNAILS = {
    "paper-ribbon-show": "/v3/assets/shows/paper-ribbon-show.webp",
    "cryo-show": "/v3/assets/shows/cryo-show.webp",
    "balloon-show": "/v3/assets/shows/balloon-show.webp",
    "jesters": "/v3/assets/shows/jesters.webp",
    "neon-jesters": "/v3/assets/shows/neon-jesters.webp",
}


def _asset_version(relative_path: str) -> str:
    try:
        return str(int((STATIC_ROOT / relative_path).stat().st_mtime))
    except OSError:
        return "1"


def _collect_rail_shows(limit: int = 12) -> list[dict[str, object]]:
    """Build card data for the catalog rail from grouped show programs."""
    shows: list[dict[str, object]] = []
    try:
        groups = list_show_programs_grouped_for_public()
    except Exception:
        groups = []
    for group in groups:
        primary = group.get("primary") or {}
        summary = _show_program_summary(dict(primary))
        photo = str(summary.get("hero_file_path") or "").strip()
        slug = str(summary.get("slug") or "").strip()
        shows.append(
            {
                "slug": slug,
                "name": str(summary.get("name") or group.get("name") or "Шоу-программа").strip(),
                "price_label": str(summary.get("price_label") or "").strip(),
                "duration_label": str(summary.get("duration_label") or "").strip(),
                "age_label": str(summary.get("age_label") or "").strip(),
                "summary_text": str(summary.get("summary_text") or "").strip(),
                "photo": _CARD_THUMBNAILS.get(slug, photo),
                "has_image": bool(summary.get("has_image")) and bool(photo),
                "route": str(summary.get("route") or "/show-programs/").strip(),
                "builder_url": f"/party-builder/?program={slug}",
            }
        )
        if len(shows) >= limit:
            break
    return shows


def build_cinematic_page() -> str:
    """Render the standalone cinematic scroll page."""
    shows = _collect_rail_shows()
    return render_template(
        "site/v3_cinematic.html",
        shows=shows,
        css_version=_asset_version("v3/v3.css"),
        js_version=_asset_version("v3/v3.js"),
    )
