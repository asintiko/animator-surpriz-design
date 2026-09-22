from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


WEBAPP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WEBAPP_ROOT.parent
SOURCE_ROOTS = [
    PROJECT_ROOT / "static" / "wp-content" / "uploads",
    PROJECT_ROOT / "static" / "admin-media",
]
OUTPUT_PATH = WEBAPP_ROOT / "data" / "media-manifest.json"
DERIVATIVE_PATTERN = re.compile(r"-\d+x\d+(?=\.[^.]+$)", re.IGNORECASE)
ALLOWED_SUFFIXES = {".avif", ".jpeg", ".jpg", ".png", ".webp"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    entries: list[dict[str, object]] = []
    for source_root in SOURCE_ROOTS:
        if not source_root.exists():
            continue
        for path in sorted(source_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            stat = path.stat()
            relative = path.relative_to(PROJECT_ROOT).as_posix()
            entries.append(
                {
                    "path": relative,
                    "bytes": stat.st_size,
                    "sha256": sha256(path),
                    "suffix": path.suffix.lower(),
                    "is_wordpress_derivative": bool(DERIVATIVE_PATTERN.search(path.name)),
                    "modified_at": datetime.fromtimestamp(
                        stat.st_mtime,
                        tz=timezone.utc,
                    ).isoformat(),
                }
            )

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_roots": [path.relative_to(PROJECT_ROOT).as_posix() for path in SOURCE_ROOTS],
        "file_count": len(entries),
        "files": entries,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Indexed {len(entries)} media files into {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
