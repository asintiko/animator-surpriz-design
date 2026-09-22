from __future__ import annotations

from pathlib import Path, PurePosixPath

from .admin_store import get_public_settings
from .config import ROUTES_ROOT

EXPLICIT_REDIRECTS = {
    "author/admin": "/",
}
PROMOTION_PATHS = {
    "promotions",
    "category/promo",
    "akcija-1",
    "akcija-2",
    "akcija-3",
}


def normalize_requested_path(requested_path: str) -> str:
    return requested_path.strip("/")


def route_bundle_path(requested_path: str) -> Path:
    cleaned = normalize_requested_path(requested_path)
    if not cleaned:
        return Path("index")
    return Path(*PurePosixPath(cleaned).parts)


def route_exists(requested_path: str) -> bool:
    return (ROUTES_ROOT / route_bundle_path(requested_path) / "meta.json").exists()


def resolve_route_redirect(requested_path: str) -> str | None:
    cleaned = normalize_requested_path(requested_path)
    if cleaned in EXPLICIT_REDIRECTS:
        return EXPLICIT_REDIRECTS[cleaned]

    if cleaned in PROMOTION_PATHS and not get_public_settings()["show_promotions"]:
        return "/"

    parts = PurePosixPath(cleaned).parts
    if len(parts) >= 2 and parts[-2:] == ("page", "1"):
        canonical_path = "/".join(parts[:-2])
        if route_exists(canonical_path):
            return "/" if not canonical_path else f"/{canonical_path}/"

    return None
