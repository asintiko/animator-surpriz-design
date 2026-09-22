from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote

from .config import STATIC_ROOT

PUBLIC_ASSET_ALIASES = (
    ("_assets/content/cache/min/1/_assets/content/", "wp-content/cache/min/1/wp-content/"),
    ("_assets/content/cache/min/1/_assets/includes/", "wp-content/cache/min/1/wp-includes/"),
    (
        "_assets/content/cache/background-css/1/eventsurpriz.uz/_assets/content/cache/min/1/_assets/content/",
        "wp-content/cache/background-css/1/eventsurpriz.uz/wp-content/cache/min/1/wp-content/",
    ),
    (
        "_assets/content/cache/background-css/1/eventsurpriz.uz/_assets/content/cache/min/1/_assets/includes/",
        "wp-content/cache/background-css/1/eventsurpriz.uz/wp-content/cache/min/1/wp-includes/",
    ),
    ("_assets/content/cache/background-css/1/eventsurpriz.uz/_assets/content/", "wp-content/cache/background-css/1/eventsurpriz.uz/wp-content/"),
    ("_assets/content/cache/plugins/", "wp-content/plugins/"),
    ("_assets/content/cache/themes/", "wp-content/themes/"),
    ("_assets/content/cache/uploads/", "wp-content/uploads/"),
    ("_assets/content/cache/includes/", "wp-includes/"),
    ("_assets/content/", "wp-content/"),
    ("_assets/includes/", "wp-includes/"),
)


def _safe_candidate(path_fragment: str) -> Path | None:
    candidate = (STATIC_ROOT / path_fragment).resolve()
    static_root = STATIC_ROOT.resolve()
    if candidate == static_root or static_root in candidate.parents:
        return candidate
    return None


def _variants(requested_path: str) -> list[str]:
    cleaned = requested_path.strip("/")
    if not cleaned:
        return []

    for public_prefix, target_prefix in PUBLIC_ASSET_ALIASES:
        if cleaned.startswith(public_prefix):
            cleaned = f"{target_prefix}{cleaned[len(public_prefix):]}"
            break

    path_obj = Path(cleaned)
    parts = path_obj.parts
    if not parts:
        return []

    decoded_parts = tuple(unquote(part) for part in parts)
    encoded_parts = tuple(quote(part, safe="") for part in decoded_parts)

    candidates = [
        "/".join(parts),
        "/".join(decoded_parts),
        "/".join(encoded_parts),
    ]

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(candidates))


def resolve_static_file(requested_path: str) -> Path | None:
    for variant in _variants(requested_path):
        candidate = _safe_candidate(variant)
        if candidate and candidate.is_file():
            return candidate
    return None
