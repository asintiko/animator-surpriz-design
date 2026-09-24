from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
except Exception:
    pass

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, send_from_directory, session
from flask_compress import Compress
from werkzeug.middleware.proxy_fix import ProxyFix

from core.admin_panel import register_admin_routes
from core.admin_notifications import init_admin_notifications_store
from core.addon_store import init_addon_store
from core.partner_store import init_partner_store
from core.recommendation_store import init_recommendation_store
from core.promotion_store import init_promotion_store
from core.catalog_site import (
    build_catalog_page,
    build_character_page,
    build_frontend_catalog_payload,
    build_frontend_show_payload,
    build_show_program_page,
    build_show_programs_page,
)
from core.catalog_bootstrap import resolve_landing_root, sync_curated_catalog_for_runtime
from core.catalog_store import list_characters_for_public, sync_curated_character_catalog
from core.config import STATIC_ROOT
from core.admin_store import init_admin_store, log_visit
from core.customer_panel import register_customer_routes
from core.customer_store import CUSTOMER_SESSION_KEY, init_customer_store
from core.forms import handle_admin_ajax
from core.loader import build_runtime_page_bundle, load_page_bundle
from core.routing import resolve_route_redirect
from core.static_assets import resolve_static_file
from core.v2_pages import build_home_page


def load_local_env() -> None:
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()

app = Flask(__name__, template_folder="templates", static_folder=None)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
runtime_environment = os.environ.get("SURPRIZ_ENV", "development").strip().lower()
configured_secret = os.environ.get("SURPRIZ_ADMIN_SECRET", "").strip()
if runtime_environment == "production" and not configured_secret:
    raise RuntimeError("SURPRIZ_ADMIN_SECRET must be configured in production")
app.secret_key = configured_secret or "surpriz-local-admin-secret"
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=runtime_environment == "production" or os.environ.get("SURPRIZ_PUBLIC_HTTPS") == "1",
)
app.config["SURPRIZ_UNIFIED_HOME_URL"] = "/"
app.config["COMPRESS_MIMETYPES"] = [
    "text/html",
    "text/css",
    "text/xml",
    "text/plain",
    "application/json",
    # Werkzeug serves .js as text/javascript, so the application/* spelling alone
    # left every script uncompressed.
    "text/javascript",
    "application/javascript",
    "application/x-javascript",
    "application/xml+rss",
    "image/svg+xml",
]
app.config["COMPRESS_LEVEL"] = 6
app.config["COMPRESS_MIN_SIZE"] = 500
Compress(app)
init_admin_store()
init_addon_store()
init_partner_store()
init_recommendation_store()
init_promotion_store()
init_customer_store()
init_admin_notifications_store()
register_admin_routes(app)
register_customer_routes(app)


@app.context_processor
def _inject_picker_flag():
    enabled = False
    try:
        from core.admin_store import get_public_settings
        enabled = bool(get_public_settings().get("picker_enabled", False))
    except Exception:
        enabled = False
    version = "0"
    if enabled:
        try:
            picker_path = Path(__file__).parent / "static" / "dev-picker.js"
            version = str(int(picker_path.stat().st_mtime))
        except Exception:
            pass
    def static_asset_version(relative_path: str) -> str:
        try:
            return str(int((STATIC_ROOT / relative_path).stat().st_mtime_ns))
        except OSError:
            return "0"

    return {
        "picker_enabled": enabled,
        "picker_version": version,
        "static_asset_version": static_asset_version,
    }


# Production runs exactly one dedicated Telegram polling process. The opt-in is
# kept for local development and single-process installations.
if os.environ.get("SURPRIZ_TELEGRAM_POLLING", "0") == "1":
    try:
        from core.admin_notifications import start_polling_in_background

        start_polling_in_background()
    except Exception:
        pass


def render_public_page(page, status_code: int = 200):
    runtime_page = build_runtime_page_bundle(page, is_authenticated=bool(session.get(CUSTOMER_SESSION_KEY)))
    return render_template("base.html", page=runtime_page), status_code


def _is_cacheable_static_response(path: str, mimetype: str) -> bool:
    if "." in path.rsplit("/", 1)[-1]:
        return True

    return (
        mimetype.startswith("text/css")
        or mimetype.startswith("application/javascript")
        or mimetype.startswith("image/")
        or mimetype.startswith("font/")
        or mimetype.startswith("audio/")
        or mimetype.startswith("video/")
        or mimetype in {
            "image/svg+xml",
            "application/font-woff",
            "application/font-woff2",
            "application/octet-stream",
        }
    )


@app.before_request
def reject_cross_site_mutations():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None
    if request.path.startswith("/__inspect/") and os.environ.get("STAGEWISE") == "1":
        return None

    fetch_site = request.headers.get("Sec-Fetch-Site", "").strip().lower()
    if fetch_site == "cross-site":
        abort(403)

    origin = request.headers.get("Origin", "").rstrip("/")
    if origin and origin != request.host_url.rstrip("/"):
        abort(403)
    return None


@app.after_request
def disable_local_cache(response):
    request_path = request.path or "/"
    is_short_cache_public_api = (
        request.method in {"GET", "HEAD"}
        and response.status_code in {200, 304}
        and request_path in {
            "/api/catalogs",
            "/surpriz/api/catalogs",
            "/api/shows",
            "/surpriz/api/shows",
        }
    )
    is_public_html = (
        request.method == "GET"
        and response.status_code == 200
        and response.mimetype == "text/html"
        and not request_path.startswith("/admin")
        and not request_path.startswith("/wp-admin/")
    )
    is_cacheable_static = (
        request.method in {"GET", "HEAD"}
        and response.status_code in {200, 304}
        and _is_cacheable_static_response(request_path, response.mimetype)
    )

    if is_short_cache_public_api:
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
    elif is_public_html:
        response.headers["Cache-Control"] = "private, no-cache, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Vary"] = "Cookie"
    elif is_cacheable_static:
        query_params = parse_qs(request.query_string.decode("utf-8", errors="ignore"))
        has_version_token = any(query_params.get(key) for key in ("ver", "v", "wpr_t"))
        is_mutable_landing_asset = (
            request_path.startswith("/surpriz/")
            or _is_landing_asset_path(request_path.lstrip("/"))
        )
        max_age = (
            31536000
            if has_version_token or request_path.startswith(("/wp-content/cache/", "/wp-includes/", "/_assets/content/cache/", "/_assets/includes/"))
            else 3600
            if is_mutable_landing_asset
            else 604800
        )
        cache_control = f"public, max-age={max_age}"
        if max_age >= 31536000:
            cache_control += ", immutable"
        else:
            cache_control += ", stale-while-revalidate=86400"

        response.headers["Cache-Control"] = cache_control
        response.headers.pop("Pragma", None)
        response.headers.pop("Expires", None)
    else:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    if is_public_html:
        visitor_id = request.cookies.get("surpriz_vid", "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", visitor_id):
            visitor_id = secrets.token_urlsafe(18)
            response.set_cookie(
                "surpriz_vid",
                visitor_id,
                max_age=63072000,
                secure=request.is_secure or app.config.get("SESSION_COOKIE_SECURE", False),
                httponly=True,
                samesite="Lax",
            )
        raw_customer_id = session.get(CUSTOMER_SESSION_KEY)
        try:
            customer_id = int(raw_customer_id) if raw_customer_id else None
        except (TypeError, ValueError):
            customer_id = None
        try:
            log_visit(
                path=request_path,
                remote_addr=request.remote_addr or "",
                user_agent=request.headers.get("User-Agent", ""),
                visitor_id=visitor_id,
                customer_id=customer_id,
                referrer=request.referrer or "",
                site_host=request.host,
            )
        except Exception:
            app.logger.exception("Unable to record visit")

    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(self)")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    return response


INSPECT_INBOX_PATH = Path(__file__).parent / ".inspect" / "inbox.jsonl"


@app.post("/__inspect/comment")
def inspect_comment():
    if os.environ.get("STAGEWISE") != "1":
        abort(404)
    payload = request.get_json(silent=True) or {}
    comment = (payload.get("comment") or "").strip()
    if not comment:
        return jsonify({"ok": False, "error": "empty"}), 400
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "comment": comment[:4000],
        "meta": payload.get("meta") or {},
        "ua": request.headers.get("User-Agent", "")[:200],
        "ip": request.remote_addr,
    }
    INSPECT_INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INSPECT_INBOX_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return jsonify({"ok": True})


@app.post("/__inspect/clear")
def inspect_clear():
    if os.environ.get("STAGEWISE") != "1":
        abort(404)
    if INSPECT_INBOX_PATH.exists():
        INSPECT_INBOX_PATH.unlink()
    return jsonify({"ok": True})


@app.post("/__inspect/batch")
def inspect_batch():
    if os.environ.get("STAGEWISE") != "1":
        abort(404)
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"ok": False, "error": "no items"}), 400
    INSPECT_INBOX_PATH.parent.mkdir(parents=True, exist_ok=True)
    batch_ts = datetime.now().isoformat(timespec="seconds")
    record = {
        "ts": batch_ts,
        "kind": "batch",
        "url": payload.get("url") or "",
        "viewport": payload.get("viewport") or {},
        "ua": request.headers.get("User-Agent", "")[:200],
        "ip": request.remote_addr,
        "items": [
            {
                "index": int(it.get("index") or i + 1),
                "comment": str(it.get("comment") or "")[:4000],
                "meta": it.get("meta") or {},
            }
            for i, it in enumerate(items)
            if isinstance(it, dict)
        ],
    }
    with INSPECT_INBOX_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return jsonify({"ok": True, "count": len(record["items"])})


@app.post("/api/tg/webhook")
def tg_webhook():
    """Telegram webhook for authenticated bot updates."""
    secret_expected = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "").strip()
    if not secret_expected:
        abort(503)
    if not secrets.compare_digest(secret_header, secret_expected):
        abort(401)
    try:
        update = request.get_json(force=True, silent=True) or {}
    except Exception:
        update = {}
    try:
        from core.admin_notifications import handle_callback
        result = handle_callback(update)
    except Exception:
        app.logger.exception("Telegram webhook processing failed")
        return jsonify({"ok": False}), 503
    return jsonify({"ok": bool(result.get("success"))})


@app.post("/wp-admin/admin-ajax.php")
@app.post("/forms/submit/")
def admin_ajax():
    return handle_admin_ajax(request)


@app.get("/wp-admin")
@app.get("/wp-admin/")
@app.get("/wp-login.php")
@app.get("/admin.html")
@app.get("/surpriz/admin.html")
@app.get("/surpriz/admin/")
def legacy_admin_entry():
    """Keep legacy admin bookmarks pointed at the active Surpriz panel."""
    return redirect("/admin/", code=302)


@app.get("/api/catalog/search")
def api_catalog_search():
    query = request.args.get("q", "").strip()
    characters = list_characters_for_public(search=query)
    return jsonify(
        {
            "success": True,
            "query": query,
            "total": len(characters),
            "items": [
                {
                    "name": character["name"],
                    "route": character["route"],
                    "hero_file_path": character.get("hero_file_path") or "",
                    "description": (character.get("short_description") or character.get("description") or "")[:220],
                    "cover_offset_x": character.get("cover_offset_x") if character.get("cover_offset_x") is not None else 50,
                    "cover_offset_y": character.get("cover_offset_y") if character.get("cover_offset_y") is not None else 50,
                    "cover_fit": character.get("cover_fit") or "cover",
                }
                for character in characters
            ],
        }
    )


app_root = Path(__file__).resolve().parent
SURPRIZ_LANDING_ROOT = resolve_landing_root(
    app_root,
    os.environ.get("SURPRIZ_LANDING_ROOT", ""),
)
curated_sync = sync_curated_catalog_for_runtime(
    landing_root=SURPRIZ_LANDING_ROOT,
    runtime_environment=runtime_environment,
    sync_catalog=sync_curated_character_catalog,
    logger=app.logger,
)
SURPRIZ_LANDING_FILES = {
    "auth.js",
    "catalogs.js",
    "favicon.png",
    "mobile.png",
    "mobile.avif",
    "mobile.webp",
    "navigation.js",
    "styles.css",
    "основа.png",
    "основа.avif",
    "основа.webp",
}
SURPRIZ_LANDING_ASSET_DIRS = {"assets"}


def _is_landing_asset_path(asset_path: str) -> bool:
    """Allow only the public landing bundle outside its /surpriz/ alias too.

    The landing HTML intentionally uses relative asset URLs so it can be opened
    from both / and /surpriz/. Keep those URLs working through Flask instead of
    relying on an nginx document root from a previous release.
    """
    normalized = asset_path.strip("/")
    parts = Path(normalized).parts
    if not parts or any(part in {".", ".."} for part in parts):
        return False
    return normalized in SURPRIZ_LANDING_FILES or parts[0] in SURPRIZ_LANDING_ASSET_DIRS


def _landing_page_exists(filename: str) -> bool:
    return (SURPRIZ_LANDING_ROOT / filename).is_file()


def _serve_landing_page(filename: str):
    response = send_from_directory(SURPRIZ_LANDING_ROOT, filename)
    response.headers["Cache-Control"] = "private, no-cache, max-age=0, must-revalidate"
    return response


@app.get("/api/catalogs")
@app.get("/surpriz/api/catalogs")
def frontend_catalogs():
    response = jsonify(build_frontend_catalog_payload())
    response.add_etag()
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return response.make_conditional(request)


@app.get("/api/shows")
@app.get("/surpriz/api/shows")
def frontend_shows():
    response = jsonify(build_frontend_show_payload())
    response.add_etag()
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return response.make_conditional(request)


@app.errorhandler(404)
def page_not_found(error):
    requested_path = request.path.lstrip("/")
    if "." in requested_path.rsplit("/", 1)[-1] or requested_path.startswith(("wp-content/", "wp-includes/", "wp-admin/", "_assets/content/", "_assets/includes/")):
        return "Not Found", 404

    page = load_page_bundle("errors/404")
    if not page:
        return "Not Found", 404

    return render_public_page(page, 404)


@app.get("/catalog/")
def managed_catalog():
    if _landing_page_exists("catalog.html"):
        return _serve_landing_page("catalog.html")
    page, redirect_target = build_catalog_page(search_query=request.args.get("q", ""))
    if redirect_target:
        return redirect(redirect_target, code=302)
    if not page:
        abort(404)
    return render_public_page(page)[0]


@app.get("/catalog/page/<int:page_number>/")
def managed_catalog_paged(page_number: int):
    page, redirect_target = build_catalog_page(page_number=page_number, search_query=request.args.get("q", ""))
    if redirect_target:
        return redirect(redirect_target, code=301 if page_number <= 1 else 302)
    if not page:
        abort(404)
    return render_public_page(page)[0]


@app.get("/character-category/<slug>/")
def managed_catalog_category(slug: str):
    if request.args.get("q", "").strip():
        return redirect(f"/catalog/?{urlencode({'q': request.args.get('q', '').strip()})}", code=302)
    page, redirect_target = build_catalog_page(category_slug=slug)
    if redirect_target:
        return redirect(redirect_target, code=302)
    if not page:
        abort(404)
    return render_public_page(page)[0]


@app.get("/character-category/<slug>/page/<int:page_number>/")
def managed_catalog_category_paged(slug: str, page_number: int):
    if request.args.get("q", "").strip():
        return redirect(f"/catalog/?{urlencode({'q': request.args.get('q', '').strip()})}", code=302)
    page, redirect_target = build_catalog_page(category_slug=slug, page_number=page_number)
    if redirect_target:
        return redirect(redirect_target, code=301 if page_number <= 1 else 302)
    if not page:
        abort(404)
    return render_public_page(page)[0]


@app.get("/character-tag/<slug>/")
def managed_catalog_tag(slug: str):
    if request.args.get("q", "").strip():
        return redirect(f"/catalog/?{urlencode({'q': request.args.get('q', '').strip()})}", code=302)
    page, redirect_target = build_catalog_page(tag_slug=slug)
    if redirect_target:
        return redirect(redirect_target, code=302)
    if not page:
        abort(404)
    return render_public_page(page)[0]


@app.get("/character-tag/<slug>/page/<int:page_number>/")
def managed_catalog_tag_paged(slug: str, page_number: int):
    if request.args.get("q", "").strip():
        return redirect(f"/catalog/?{urlencode({'q': request.args.get('q', '').strip()})}", code=302)
    page, redirect_target = build_catalog_page(tag_slug=slug, page_number=page_number)
    if redirect_target:
        return redirect(redirect_target, code=301 if page_number <= 1 else 302)
    if not page:
        abort(404)
    return render_public_page(page)[0]


@app.get("/character/<slug>/")
def managed_character(slug: str):
    page = build_character_page(slug)
    if not page:
        abort(404)
    return render_public_page(page)[0]


@app.get("/show-programs/")
def managed_show_programs():
    if _landing_page_exists("show-programs.html"):
        return _serve_landing_page("show-programs.html")
    page = build_show_programs_page()
    if not page:
        abort(404)
    return render_public_page(page)[0]


@app.get("/show-programs/<slug>/")
def managed_show_program(slug: str):
    page = build_show_program_page(slug)
    if not page:
        abort(404)
    return render_public_page(page)[0]


@app.get("/surpriz/")
def surpriz_landing():
    return redirect("/", code=302)


@app.get("/surpriz/<path:asset_path>")
def surpriz_landing_asset(asset_path: str):
    if not _is_landing_asset_path(asset_path):
        abort(404)
    return send_from_directory(SURPRIZ_LANDING_ROOT, asset_path)


@app.get("/")
def v2_home():
    if _landing_page_exists("index.html"):
        return _serve_landing_page("index.html")
    page = build_home_page()
    if not page:
        abort(404)
    return render_public_page(page)[0]


LEGACY_SITE_REDIRECTS = {
    "prices": "/show-programs/",
    "contacts": "/",
    "o-nas": "/",
    "v3": "/",
    "v4": "/",
    "v5": "/",
}


_TEXT_STATIC_MIMETYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".xml": "application/xml; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


@app.route("/", defaults={"requested_path": ""})
@app.route("/<path:requested_path>")
def site_route(requested_path: str):
    if _is_landing_asset_path(requested_path):
        return send_from_directory(SURPRIZ_LANDING_ROOT, requested_path)

    public_file = resolve_static_file(requested_path)
    if public_file:
        mimetype = _TEXT_STATIC_MIMETYPES.get(public_file.suffix.lower())
        if mimetype:
            response = app.make_response(public_file.read_bytes())
            response.headers["Content-Type"] = mimetype
            response.headers["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
            return response
        return send_file(public_file, conditional=True)

    redirect_target = resolve_route_redirect(requested_path)
    if redirect_target:
        return redirect(redirect_target, code=301)

    page = load_page_bundle(requested_path)
    if not page:
        abort(404)

    return render_public_page(page)[0]


@app.post("/__picker_select")
def picker_select():
    if os.environ.get("STAGEWISE") != "1":
        abort(404)
    if (request.content_length or 0) > 64 * 1024:
        abort(413)
    try:
        data = request.get_json(silent=True) or {}
    except Exception:
        data = {}
    log_path = Path(__file__).parent / "picker.log"
    line = json.dumps(data, ensure_ascii=False)
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print("[picker]", line, flush=True)
    return jsonify({"ok": True})


if __name__ == "__main__":
    host = os.environ.get("SURPRIZ_HOST", "0.0.0.0")
    port = int(os.environ.get("SURPRIZ_PORT", "5000"))
    ssl_context = "adhoc" if os.environ.get("SURPRIZ_SSL") == "1" else None
    app.run(host=host, port=port, debug=False, ssl_context=ssl_context)
