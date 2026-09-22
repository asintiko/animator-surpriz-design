from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    jsonify,
    redirect,
    request,
    send_file,
    send_from_directory,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename


PROJECT_ROOT = Path(__file__).resolve().parent
LEGACY_ROOT = PROJECT_ROOT.parent / "animator"
PUBLIC_ROOT_FILES = {
    "auth.js",
    "catalogs.js",
    "favicon.png",
    "mobile.avif",
    "mobile.webp",
    "mobile.png",
    "navigation.js",
    "styles.css",
    "основа.avif",
    "основа.webp",
    "основа.png",
}
PUBLIC_ASSET_DIRS = {"assets", "data"}
CATALOGS_PATH = PROJECT_ROOT / "data" / "catalogs.json"
CATALOG_UPLOAD_DIR = PROJECT_ROOT / "assets" / "img" / "catalogs"
ALLOWED_IMAGE_EXTENSIONS = {"gif", "jpeg", "jpg", "png", "webp"}
ALLOWED_CATALOG_PLACEMENTS = {"homepage", "catalog", "party_builder"}
ALLOWED_CHARACTER_CATEGORIES = {"superheroes", "princesses", "boys", "girls", "cartoons"}

if not LEGACY_ROOT.is_dir():
    raise RuntimeError(f"Legacy backend not found: {LEGACY_ROOT}")

load_dotenv(LEGACY_ROOT / ".env", override=False)
sys.path.insert(0, str(LEGACY_ROOT))

from core import catalog_store, customer_store  # noqa: E402
from core.catalog_site import build_frontend_catalog_payload  # noqa: E402
from core.customer_panel import register_customer_routes  # noqa: E402
from core.static_assets import resolve_static_file  # noqa: E402


app = Flask(__name__, static_folder=None, template_folder=str(LEGACY_ROOT / "templates"))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = (
    os.environ.get("SURPRIZ_PREVIEW_SECRET")
    or os.environ.get("SURPRIZ_ADMIN_SECRET")
    or "surpriz-local-preview-secret"
)
app.config.update(
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SURPRIZ_PUBLIC_HTTPS", "0") == "1",
    SURPRIZ_UNIFIED_HOME_URL="/surpriz/",
)

preview_db_override = os.environ.get("SURPRIZ_PREVIEW_DB_PATH", "").strip()
preview_db_path = (
    Path(preview_db_override).expanduser().resolve()
    if preview_db_override
    else Path(tempfile.gettempdir()) / "surpriz-preview" / "site_admin.sqlite3"
)
customer_store.DB_PATH = preview_db_path
customer_store.DB_ROOT = preview_db_path.parent
catalog_store.DB_PATH = preview_db_path
catalog_store.DB_ROOT = preview_db_path.parent

customer_store.init_customer_store()
catalog_store.init_catalog_store()
catalog_store.sync_curated_character_catalog(CATALOGS_PATH)
register_customer_routes(app)


def _is_local_request() -> bool:
    return request.remote_addr in {"127.0.0.1", "::1"}


def _read_catalogs() -> dict[str, object]:
    return json.loads(CATALOGS_PATH.read_text(encoding="utf-8"))


def _normalize_text(value: object, *, maximum: int, required: bool = True) -> str:
    normalized = " ".join(str(value or "").split())
    if required and not normalized:
        raise ValueError("Обязательное поле не заполнено")
    if len(normalized) > maximum:
        raise ValueError(f"Текст длиннее {maximum} символов")
    return normalized


def _normalize_percentage(value: object) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = 50
    return max(0, min(100, number))


def _normalize_zoom(value: object) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = 100
    return max(100, min(200, number))


def _normalize_catalog_item(item: object, *, kind: str, position: int) -> dict[str, object]:
    if not isinstance(item, dict):
        raise ValueError("Карточка должна быть объектом")

    raw_id = _normalize_text(item.get("id"), maximum=100)
    item_id = re.sub(r"[^a-z0-9-]+", "-", raw_id.lower()).strip("-")
    if not item_id:
        item_id = f"{kind}-{position + 1}"

    image = _normalize_text(item.get("image"), maximum=2048)
    if image.startswith("assets/"):
        if ".." in Path(image).parts:
            raise ValueError("Недопустимый путь к изображению")
    elif not image.startswith("https://"):
        raise ValueError("Изображение должно быть локальным assets/… или HTTPS-ссылкой")

    href = _normalize_text(item.get("href") or "#order", maximum=240)
    if not href.startswith(("#", "/", "https://")):
        raise ValueError("Ссылка кнопки должна начинаться с #, / или https://")

    title_color = _normalize_text(item.get("title_color") or "#21165b", maximum=7).lower()
    if not re.fullmatch(r"#[0-9a-f]{6}", title_color):
        raise ValueError("Цвет названия должен быть в формате #RRGGBB")

    raw_position = item.get("image_position")
    image_position = raw_position if isinstance(raw_position, dict) else {}
    raw_placements = item.get("placements")
    if not isinstance(raw_placements, list):
        raise ValueError("Области показа должны быть списком")
    placements = []
    for placement in raw_placements:
        normalized_placement = str(placement)
        if normalized_placement not in ALLOWED_CATALOG_PLACEMENTS:
            raise ValueError(f"Неизвестная область показа: {normalized_placement}")
        if normalized_placement not in placements:
            placements.append(normalized_placement)

    raw_categories = item.get("categories", [])
    if not isinstance(raw_categories, list):
        raise ValueError("Категории персонажа должны быть списком")
    categories = []
    for category in raw_categories:
        normalized_category = str(category)
        if normalized_category not in ALLOWED_CHARACTER_CATEGORIES:
            raise ValueError(f"Неизвестная категория персонажа: {normalized_category}")
        if normalized_category not in categories:
            categories.append(normalized_category)

    return {
        "id": item_id,
        "title": _normalize_text(item.get("title"), maximum=60),
        "description": _normalize_text(item.get("description"), maximum=180),
        "image": image,
        "alt": _normalize_text(item.get("alt"), maximum=120),
        "cta_label": _normalize_text(item.get("cta_label") or "Заказать", maximum=32),
        "href": href,
        "active": bool(item.get("active", True)),
        "title_color": title_color,
        "image_position": {
            "x": _normalize_percentage(image_position.get("x")),
            "y": _normalize_percentage(image_position.get("y")),
        },
        "image_zoom": _normalize_zoom(item.get("image_zoom")),
        "categories": categories if kind == "characters" else [],
        "placements": placements,
    }


def _normalize_catalogs(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("Ожидался JSON-объект")

    normalized: dict[str, object] = {"version": 2}
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    try:
        autoplay_speed = int(settings.get("autoplay_speed", 18))
    except (TypeError, ValueError):
        autoplay_speed = 18
    normalized["settings"] = {
        "autoplay_enabled": bool(settings.get("autoplay_enabled", True)),
        "autoplay_speed": max(8, min(60, autoplay_speed)),
    }

    seen_ids: set[str] = set()
    for kind in ("characters", "shows"):
        raw_items = payload.get(kind)
        if not isinstance(raw_items, list):
            raise ValueError(f"Раздел {kind} должен быть списком")
        if len(raw_items) > 200:
            raise ValueError("В одном каталоге может быть не больше 200 карточек")
        items = []
        for position, raw_item in enumerate(raw_items):
            item = _normalize_catalog_item(raw_item, kind=kind, position=position)
            if item["id"] in seen_ids:
                raise ValueError(f"Повторяется идентификатор {item['id']}")
            seen_ids.add(str(item["id"]))
            items.append(item)
        normalized[kind] = items
    return normalized


def _stage_catalog_bytes(data: bytes) -> Path:
    CATALOGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_path = tempfile.mkstemp(
        dir=CATALOGS_PATH.parent,
        prefix="catalogs-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
        return Path(temporary_path)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


def _stage_catalogs(data: dict[str, object]) -> Path:
    serialized = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    return _stage_catalog_bytes(serialized)


@app.before_request
def reject_cross_origin_mutations():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and origin != request.host_url.rstrip("/"):
        abort(403)
    return None


@app.after_request
def add_public_response_headers(response):
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


@app.get("/")
def preview_root():
    return redirect("/surpriz/")


@app.get("/surpriz/")
def preview_home():
    response = send_from_directory(PROJECT_ROOT, "index.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/surpriz/admin/")
def preview_home_admin():
    if not _is_local_request():
        abort(404)
    response = send_from_directory(PROJECT_ROOT, "admin.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.route("/api/catalogs", methods=["GET"])
@app.route("/surpriz/api/catalogs", methods=["GET", "PUT"])
def preview_catalogs():
    if request.method == "GET":
        response = jsonify(build_frontend_catalog_payload())
        response.headers["Cache-Control"] = "no-store"
        return response

    if not _is_local_request():
        abort(404)
    try:
        payload = request.get_json(silent=False)
        normalized = _normalize_catalogs(payload)
    except (ValueError, TypeError) as error:
        return jsonify({"error": str(error)}), 400

    staged_catalog = _stage_catalogs(normalized)
    try:
        # The published manifest is used by production startup, so reject a
        # candidate before replacing the last known-good file.
        catalog_store.validate_curated_character_catalog(staged_catalog)
    except (ValueError, UnicodeDecodeError) as error:
        staged_catalog.unlink(missing_ok=True)
        return jsonify({"error": str(error)}), 400
    except Exception:
        staged_catalog.unlink(missing_ok=True)
        app.logger.exception("Curated catalog validation failed")
        return jsonify({"error": "Не удалось проверить каталог. Повторите попытку."}), 503

    try:
        previous_catalog = CATALOGS_PATH.read_bytes()
    except OSError:
        staged_catalog.unlink(missing_ok=True)
        app.logger.exception("Curated catalog backup failed")
        return jsonify({"error": "Не удалось подготовить резервную копию каталога."}), 503

    try:
        os.replace(staged_catalog, CATALOGS_PATH)
        catalog_store.sync_curated_character_catalog(CATALOGS_PATH)
    except Exception:
        app.logger.exception("Curated catalog publication failed")
        staged_catalog.unlink(missing_ok=True)
        restored = False
        try:
            os.replace(_stage_catalog_bytes(previous_catalog), CATALOGS_PATH)
            restored = True
        except Exception:
            app.logger.exception("Curated catalog rollback failed")
        error = (
            "Не удалось синхронизировать каталог. Предыдущая версия восстановлена."
            if restored
            else "Не удалось синхронизировать каталог. Обратитесь к разработчику."
        )
        return jsonify({"error": error}), 503
    return jsonify(normalized)


@app.post("/surpriz/api/catalogs/upload")
def preview_catalog_upload():
    if not _is_local_request():
        abort(404)
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify({"error": "Выберите изображение"}), 400
    safe_name = secure_filename(upload.filename)
    extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if extension not in ALLOWED_IMAGE_EXTENSIONS or not (upload.mimetype or "").startswith("image/"):
        return jsonify({"error": "Поддерживаются PNG, JPG, WebP и GIF"}), 400

    CATALOG_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"catalog-{uuid.uuid4().hex[:16]}.{extension}"
    upload.save(CATALOG_UPLOAD_DIR / filename)
    return jsonify({"path": f"assets/img/catalogs/{filename}"})


@app.get("/surpriz/<path:asset_path>")
def preview_asset(asset_path: str):
    asset_parts = Path(asset_path).parts
    is_public_asset = bool(asset_parts) and asset_parts[0] in PUBLIC_ASSET_DIRS and ".." not in asset_parts
    if asset_path not in PUBLIC_ROOT_FILES and not is_public_asset:
        abort(404)
    return send_from_directory(PROJECT_ROOT, asset_path)


@app.get("/show-programs/")
def preview_show_programs():
    response = send_from_directory(PROJECT_ROOT, "show-programs.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/catalog/")
def preview_catalog():
    response = send_from_directory(PROJECT_ROOT, "catalog.html")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/<path:requested_path>")
def legacy_asset(requested_path: str):
    public_file = resolve_static_file(requested_path)
    if public_file:
        return send_file(public_file, conditional=True)
    abort(404)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "4173")), debug=False)
