from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


def resolve_landing_root(app_root: Path, configured_root: str = "") -> Path:
    configured = str(configured_root or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    root = Path(app_root).expanduser().resolve()
    candidates = (root / "surpriz", root.parent / "surprizopus")
    return next(
        (
            candidate.resolve()
            for candidate in candidates
            if (candidate / "data" / "catalogs.json").is_file()
        ),
        candidates[0].resolve(),
    )


def sync_curated_catalog_for_runtime(
    *,
    landing_root: Path,
    runtime_environment: str,
    sync_catalog: Callable[[Path], dict[str, Any]],
    logger: Any,
) -> dict[str, Any]:
    manifest = Path(landing_root) / "data" / "catalogs.json"
    is_production = str(runtime_environment or "").strip().lower() == "production"
    if not manifest.is_file():
        message = f"Curated character catalog manifest is missing: {manifest}"
        if is_production:
            raise RuntimeError(message)
        logger.warning(message)
        return {"changed": False, "reason": "manifest_missing", "count": 0}

    try:
        result = sync_catalog(manifest)
    except Exception as error:
        if is_production:
            raise RuntimeError("Curated character catalog synchronization failed") from error
        logger.exception("Curated character catalog synchronization failed")
        return {"changed": False, "reason": "sync_failed", "count": 0}

    if result.get("changed"):
        logger.info("Curated character catalog synchronized: %s", result)
    return result
