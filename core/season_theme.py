"""Re-skin public HTML for the active season.

The public site is a mix of static landing files, v2 Jinja pages and legacy page
bundles, so the season is applied in one place: an ``after_request`` hook that
edits the outgoing HTML. It marks ``<html>`` with ``data-season`` (the season
stylesheet keys everything off that attribute), links the season CSS/JS, puts
the season data into an inline JSON block and swaps the images that have the
season baked in (hero banners, logo, favicon, backgrounds) for their seasonal
versions. Swaps only happen for files that exist, so a season without its own
art keeps the regular images.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from flask import Flask, Response, request

from . import seasons

SEASON_ASSET_PREFIX = "/surpriz/assets/seasons"
SKIPPED_PATH_PREFIXES = ("/admin", "/wp-admin", "/api/", "/surpriz/api/", "/__inspect/")

# Swapped URLs sit inside an attribute value, a srcset list or a CSS url() and
# are relative or root-relative; absolute OG/Schema URLs (https://…) stay.
_VERSION = r"(?:\?v=[\w.-]+)?"

# (pattern for the regular asset, seasonal file name). ``{ext}`` keeps the
# format of the matched URL so <picture> sources stay AVIF/WebP/PNG.
ASSET_SWAPS: tuple[tuple[str, str], ...] = (
    (r"(?:/surpriz/|\./)?основа\.(?P<ext>avif|webp|png)", "home-desktop.{ext}"),
    (r"(?:/surpriz/|\./)?mobile\.(?P<ext>avif|webp|png)", "home-mobile.{ext}"),
    (r"(?:/surpriz/)?assets/img/show-programs/hero-desktop\.(?P<ext>avif|webp|png)", "shows-desktop.{ext}"),
    (r"(?:/surpriz/)?assets/img/show-programs/hero-mobile\.(?P<ext>avif|webp|png)", "shows-mobile.{ext}"),
    (r"/v2/assets/account/profile-desktop\.png", "profile-desktop.webp"),
    (r"/v2/assets/account/profile-mobile\.png", "profile-mobile.webp"),
    (r"(?:/surpriz/)?assets/original/logo\.png", "logo.webp"),
    (r"/wp-content/uploads/2025/06/logo\.png", "logo.webp"),
    (r"(?:/surpriz/|\.\./|\./)?favicon\.png", "favicon.png"),
    (r"/v2/show-detail/bg-desktop\.webp", "detail-bg-desktop.webp"),
    (r"/v2/show-detail/bg-mobile\.webp", "detail-bg-mobile.webp"),
)

_SWAP_PATTERNS = tuple(re.compile(pattern + _VERSION) for pattern, _target in ASSET_SWAPS)

# Scanning a whole page (the builder is ~600 KB) with the full patterns is slow,
# so candidates are found by their file names first and only those URLs are
# checked against the swap list.
_CANDIDATE = re.compile(
    r"(?:основа|mobile|hero-desktop|hero-mobile|profile-desktop|profile-mobile|logo|favicon|bg-desktop|bg-mobile)"
    r"\.(?:avif|webp|png)" + _VERSION
)
_URL_BOUNDARY = re.compile(r"[\"'\s,(]")

_HTML_TAG = re.compile(r"<html\b([^>]*)>", re.IGNORECASE)
_THEME_COLOR = re.compile(r"<meta\s+name=[\"']theme-color[\"'][^>]*>", re.IGNORECASE)
_HEAD_END = re.compile(r"</head\s*>", re.IGNORECASE)


@lru_cache(maxsize=256)
def _file_version(path: str, mtime_ns: int) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def _versioned_url(landing_root: Path, relative: str) -> str | None:
    path = landing_root / "assets" / "seasons" / relative
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return None
    return f"{SEASON_ASSET_PREFIX}/{relative}?v={_file_version(str(path), mtime_ns)}"


def _url_start(html: str, end: int) -> int:
    """Index right after the quote, space, comma or parenthesis before ``end``."""
    window_start = max(0, end - 200)
    boundaries = list(_URL_BOUNDARY.finditer(html, window_start, end))
    return boundaries[-1].end() if boundaries else window_start


def _swap_assets(html: str, landing_root: Path, season_id: str) -> str:
    urls: dict[str, str | None] = {}
    parts: list[str] = []
    position = 0
    for candidate in _CANDIDATE.finditer(html):
        start = _url_start(html, candidate.start())
        if start < position:
            continue
        url = html[start : candidate.end()]
        for pattern, (_source, target) in zip(_SWAP_PATTERNS, ASSET_SWAPS):
            match = pattern.fullmatch(url)
            if not match:
                continue
            relative = f"{season_id}/{target.format(ext=match.groupdict().get('ext') or '')}"
            if relative not in urls:
                urls[relative] = _versioned_url(landing_root, relative)
            if urls[relative]:
                parts.append(html[position:start])
                parts.append(urls[relative])
                position = candidate.end()
            break
    parts.append(html[position:])
    return "".join(parts)


def _sprites(landing_root: Path, season_id: str) -> dict[str, str | None]:
    sprite_dir = landing_root / "assets" / "seasons" / season_id / "sprites"
    return {
        path.stem: _versioned_url(landing_root, f"{season_id}/sprites/{path.name}")
        for path in sorted(sprite_dir.glob("*.webp"))
    }


def _season_json(season: seasons.Season, landing_root: Path) -> str:
    payload = seasons.season_public_payload(season) or {}
    payload["characters"] = seasons.seasonal_character_slugs(season)
    payload["sprites"] = _sprites(landing_root, season.id)
    # «</» can not appear inside the script element.
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def decorate_html(html: str, season: seasons.Season, landing_root: Path, *, effects: bool) -> str:
    match = _HTML_TAG.search(html)
    if not match or "data-season=" in match.group(1):
        return html
    attributes = f' data-season="{season.id}" data-season-effects="{"on" if effects else "off"}"'
    html = html[: match.end(1)] + attributes + html[match.end(1) :]

    theme_color = f'<meta name="theme-color" content="{season.theme_color}" />'
    html, replaced = _THEME_COLOR.subn(theme_color, html, count=1)

    head_parts = [] if replaced else [theme_color]
    for relative in ("season.css", f"{season.id}/season.css"):
        stylesheet = _versioned_url(landing_root, relative)
        if stylesheet:
            head_parts.append(f'<link rel="stylesheet" href="{stylesheet}" />')
    head_parts.append(f'<script type="application/json" id="surpriz-season">{_season_json(season, landing_root)}</script>')
    script = _versioned_url(landing_root, "season.js")
    if script:
        head_parts.append(f'<script src="{script}" defer></script>')
    html = _HEAD_END.sub(lambda end: "\n".join(head_parts) + "\n" + end.group(0), html, count=1)
    return _swap_assets(html, landing_root, season.id)


def _is_public_html(response: Response) -> bool:
    return (
        request.method == "GET"
        and response.status_code == 200
        and response.mimetype == "text/html"
        and not request.path.startswith(SKIPPED_PATH_PREFIXES)
    )


def register_season_theme(app: Flask, landing_root: Path) -> None:
    @app.after_request
    def apply_season_theme(response: Response) -> Response:
        # Streamed bodies (send_file) are left alone: buffering them here would
        # replace the file iterator before WSGI gets the chance to close it.
        if not _is_public_html(response) or response.is_streamed:
            return response
        season = seasons.active_season()
        if season is not None:
            html = response.get_data(as_text=True)
            response.set_data(decorate_html(html, season, landing_root, effects=seasons.effects_enabled()))
        if getattr(response, "surpriz_conditional", False):
            # The body depends on the season, so the ETag must come from the
            # final HTML, not from the file on disk.
            response.add_etag(overwrite=True)
            response.make_conditional(request)
        return response
