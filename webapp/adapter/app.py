from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterator

from flask import Flask, jsonify, request, session
from werkzeug.middleware.proxy_fix import ProxyFix


WEBAPP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WEBAPP_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.addon_store import (  # noqa: E402
    create_addon,
    delete_addon,
    get_program_addon_settings,
    init_addon_store,
    list_addons,
    list_active_addons,
    set_program_addons,
    update_addon,
    update_addon_status,
)
from core.admin_notifications import (  # noqa: E402
    add_recipient,
    bot_token_masked,
    delete_recipient,
    gateway_token_masked,
    init_admin_notifications_store,
    is_notifications_configured,
    list_recipients,
    send_order_notification,
    send_test_message,
    set_setting,
    toggle_recipient,
)
from core.admin_store import (  # noqa: E402
    authenticate_admin,
    get_admin_by_id,
    get_customer_list,
    get_dashboard_stats,
    list_admin_visitors,
    get_party_builder_settings,
    get_popular_characters,
    get_popular_programs,
    get_public_settings,
    get_revenue_stats,
    apply_new_year_preset,
    unblock_customer,
    update_public_settings,
)
from core.catalog_store import (  # noqa: E402
    ENTITY_TYPE_CHARACTER,
    ENTITY_TYPE_SHOW_PROGRAM,
    create_category,
    create_character,
    create_tag,
    delete_category,
    delete_tag,
    get_character_by_slug,
    get_character_by_id,
    list_categories,
    list_characters,
    list_tags,
    parse_ensemble_members,
    update_category,
    update_character,
    delete_character,
    update_tag,
)
from core.customer_store import (  # noqa: E402
    create_party_order,
    get_customer_by_id,
    get_order_by_id,
    get_order_by_public_id,
    get_order_summary,
    init_customer_store,
    list_admin_orders,
    list_customer_orders,
    list_show_programs_for_public,
    update_order_status,
    ORDER_STATUS_LABELS,
)
from core.google_calendar import (  # noqa: E402
    MANUAL_SYNC_WAIT_SECONDS,
    GoogleCalendarError,
    GoogleCalendarSyncBusy,
    add_alias as add_calendar_alias,
    build_authorization_url,
    complete_authorization,
    disconnect as disconnect_calendar,
    enqueue_upcoming_confirmed_orders,
    get_admin_payload as get_calendar_admin_payload,
    import_now as import_calendar_now,
    init_google_calendar,
    list_calendars,
    preview_recognition,
    remove_alias as remove_calendar_alias,
    resolve_redirect_uri,
    run_sync_cycle,
    save_client_credentials,
    save_sync_settings,
    select_calendar,
    set_event_ignored,
)
from core.google_calendar_store import get_order_event_links  # noqa: E402
from core.partner_store import (  # noqa: E402
    create_partner,
    delete_partner,
    init_partner_store,
    list_partners,
    update_partner,
)
from core.recommendation_store import (  # noqa: E402
    HOMEPAGE_SLOTS,
    get_featured_slugs,
    init_recommendation_store,
    set_featured_slugs,
)
from core.promotion_store import (  # noqa: E402
    create_promotion,
    delete_promotion,
    get_promotion_by_id,
    init_promotion_store,
    list_promotions,
    update_promotion,
)
from core.tashkent_geo import is_inside_tashkent  # noqa: E402


CUSTOMER_SESSION_KEY = "customer_user_id"
ADMIN_SESSION_KEY = "admin_user_id"
DATA_DIR = Path(
    os.environ.get("SURPRIZ_ADAPTER_DATA_DIR", str(WEBAPP_ROOT / "data"))
).expanduser()
IDEMPOTENCY_DATABASE = DATA_DIR / "adapter.sqlite3"
ORDER_LOCK = DATA_DIR / "order-create.lock"
CANONICAL_DATABASE = Path(
    os.environ.get(
        "SURPRIZ_CANONICAL_DATABASE",
        str(PROJECT_ROOT / "content" / "data" / "admin" / "site_admin.sqlite3"),
    )
).expanduser()


def _required_secret() -> str:
    value = os.environ.get("SURPRIZ_ADMIN_SECRET", "").strip()
    if not value:
        raise RuntimeError("SURPRIZ_ADMIN_SECRET is required so legacy and adapter sessions match.")
    return value


def _initialize_idempotency_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(IDEMPOTENCY_DATABASE) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS order_idempotency(
                idempotency_key TEXT PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                public_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS media_assets(
                media_id INTEGER PRIMARY KEY,
                entity_id INTEGER NOT NULL,
                source_sha256 TEXT NOT NULL,
                manifest_path TEXT NOT NULL,
                original_path TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS media_trash(
                media_id INTEGER PRIMARY KEY,
                entity_id INTEGER NOT NULL,
                media_json TEXT NOT NULL,
                deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.commit()


def _ensure_customer_admin_columns() -> None:
    with sqlite3.connect(CANONICAL_DATABASE) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(customer_accounts)")}
        migrations = {
            "is_blocked": "ALTER TABLE customer_accounts ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0",
            "blocked_until": "ALTER TABLE customer_accounts ADD COLUMN blocked_until TEXT",
            "block_reason": "ALTER TABLE customer_accounts ADD COLUMN block_reason TEXT NOT NULL DEFAULT ''",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)
        connection.commit()


@contextmanager
def _serialized_order_creation() -> Iterator[None]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with ORDER_LOCK.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _lookup_idempotency(key: str, customer_id: int) -> str | None:
    if not key:
        return None
    with sqlite3.connect(IDEMPOTENCY_DATABASE) as connection:
        row = connection.execute(
            "SELECT public_id FROM order_idempotency WHERE idempotency_key = ? AND customer_id = ?",
            (key, customer_id),
        ).fetchone()
    return str(row[0]) if row else None


def _save_idempotency(key: str, customer_id: int, public_id: str) -> None:
    if not key:
        return
    with sqlite3.connect(IDEMPOTENCY_DATABASE) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO order_idempotency(idempotency_key, customer_id, public_id)
            VALUES (?, ?, ?)
            """,
            (key, customer_id, public_id),
        )
        connection.commit()


def _current_customer() -> dict[str, Any] | None:
    customer_id = session.get(CUSTOMER_SESSION_KEY)
    if not customer_id:
        return None
    return get_customer_by_id(int(customer_id))


def _current_admin() -> dict[str, Any] | None:
    admin_id = session.get(ADMIN_SESSION_KEY)
    if not admin_id:
        return None
    return get_admin_by_id(int(admin_id))


def _admin_denied():
    return jsonify(success=False, authenticated=False, message="Войдите в панель управления."), 401


#: Only the /crop route owns these. The card form keeps a snapshot of the entity
#: taken when the page loaded, so letting it write them back reverted whatever the
#: crop editor had just saved.
CROP_FIELDS = (
    "cover_offset_x",
    "cover_offset_y",
    "cover_fit",
    "image_zoom",
    "mobile_cover_offset_x",
    "mobile_cover_offset_y",
    "mobile_cover_fit",
    "mobile_image_zoom",
)


def _entity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    data.pop("addons", None)
    for key in CROP_FIELDS:
        data.pop(key, None)
    members = parse_ensemble_members(data.get("ensemble_members"))
    if str(data.get("entity_type") or "character") == "character" and len(members) == 1:
        raise ValueError("Для групповой карточки нужны минимум два уникальных участника.")
    category_slugs = {str(value) for value in data.pop("categories", [])}
    tag_slugs = {str(value) for value in data.pop("tags", [])}
    categories = list_categories(include_hidden=True)
    tags = list_tags(include_hidden=True)
    data["category_ids"] = [int(item["id"]) for item in categories if item["slug"] in category_slugs]
    data["tag_ids"] = [int(item["id"]) for item in tags if item["slug"] in tag_slugs]
    if not data["category_ids"]:
        data["category_ids"] = [int(item["id"]) for item in categories if item["slug"] == "all"]
    if not data["tag_ids"]:
        data["tag_ids"] = [int(item["id"]) for item in tags if item["slug"] == "all"]
    return data


def _clamp_image_zoom(value: object) -> int:
    try:
        return max(100, min(200, int(value)))
    except (TypeError, ValueError):
        return 100


def _admin_entity_json(entity: dict[str, Any], *, include_relations: bool = True) -> dict[str, Any]:
    data = dict(entity)
    for key, fallback_key in (("categories", "category_slugs"), ("tags", "tag_slugs")):
        values = data.get(key) or data.get(fallback_key) or []
        data[key] = [
            str(value.get("slug", "")) if isinstance(value, dict) else str(value)
            for value in values
            if (value.get("slug") if isinstance(value, dict) else value)
        ]
    data.setdefault("media", [])
    data.setdefault("linked_character_slugs", [])
    if include_relations and data.get("entity_type") == "show_program":
        settings = get_program_addon_settings(int(data.get("id") or 0))
        data["addons"] = [
            {
                **addon,
                **settings.get(
                    int(addon["id"]),
                    {
                        "is_available": False,
                        "is_recommended": False,
                        "is_default": False,
                        "is_free_choice": False,
                        "gift_mode": "none",
                        "gift_group": "",
                        "sort_order": int(addon.get("sort_order") or 0),
                    },
                ),
            }
            for addon in list_active_addons()
        ]
    else:
        data.setdefault("addons", [])
    data.setdefault("promotions", [])
    return data


def _admin_entity_list_item(entity: dict[str, Any]) -> dict[str, Any]:
    data = _admin_entity_json(entity, include_relations=False)
    return {
        key: data.get(key)
        for key in (
            "id",
            "name",
            "status",
            "hero_file_path",
            "cover_fit",
            "cover_offset_x",
            "cover_offset_y",
            "image_zoom",
            "mobile_cover_fit",
            "mobile_cover_offset_x",
            "mobile_cover_offset_y",
            "mobile_image_zoom",
            "base_price",
            "default_duration_minutes",
            "categories",
            "variant_group_slug",
            "variant_group_name",
            "variant_label",
        )
    }


def _save_program_addon_settings(program_id: int, payload_addons: object) -> None:
    if not isinstance(payload_addons, list):
        return
    active_addon_ids = {int(addon["id"]) for addon in list_active_addons()}
    selections: list[dict[str, Any]] = []
    for raw_selection in payload_addons:
        if not isinstance(raw_selection, dict) or not raw_selection.get("is_available"):
            continue
        try:
            addon_id = int(raw_selection.get("addon_id") or raw_selection.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if addon_id not in active_addon_ids:
            continue
        selections.append({**raw_selection, "addon_id": addon_id})

    current = get_program_addon_settings(program_id)
    for addon_id, settings in current.items():
        if addon_id not in active_addon_ids:
            selections.append({"addon_id": addon_id, **settings})
    set_program_addons(program_id, selections)


def _media_library() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for entity in list_characters():
        detailed = get_character_by_id(int(entity["id"]))
        if not detailed:
            continue
        for item in detailed.get("media", []):
            pipeline: dict[str, Any] = {}
            with sqlite3.connect(IDEMPOTENCY_DATABASE) as connection:
                row = connection.execute(
                    "SELECT payload_json FROM media_assets WHERE media_id = ?",
                    (int(item["id"]),),
                ).fetchone()
            if row:
                try:
                    pipeline = json.loads(str(row[0]))
                except json.JSONDecodeError:
                    pipeline = {}
            result.append(
                {
                    **item,
                    "owner_id": detailed["id"],
                    "owner_name": detailed["name"],
                    "owner_type": detailed["entity_type"],
                    "entity_id": detailed["id"],
                    "entity_name": detailed["name"],
                    "entity_type": detailed["entity_type"],
                    "is_hero": item["id"] == detailed.get("hero_media_id"),
                    "cover_offset_x": detailed.get("cover_offset_x", 50),
                    "cover_offset_y": detailed.get("cover_offset_y", 50),
                    "cover_fit": detailed.get("cover_fit", "cover"),
                    "image_zoom": detailed.get("image_zoom", 100),
                    "mobile_cover_offset_x": detailed.get("mobile_cover_offset_x", 50),
                    "mobile_cover_offset_y": detailed.get("mobile_cover_offset_y", 50),
                    "mobile_cover_fit": detailed.get("mobile_cover_fit", "cover"),
                    "mobile_image_zoom": detailed.get("mobile_image_zoom", 100),
                    "processing_status": "ready",
                    "width": pipeline.get("original", {}).get("width"),
                    "height": pipeline.get("original", {}).get("height"),
                    "bytes": pipeline.get("original", {}).get("bytes"),
                    "mime_type": pipeline.get("original", {}).get("mimeType"),
                }
            )
    return result


def _media_owners() -> list[dict[str, Any]]:
    return [
        {"id": item["id"], "name": item["name"], "owner_type": item["entity_type"]}
        for item in list_characters()
    ]


def _attach_generated_media(payload: dict[str, Any]) -> int:
    entity_id = int(payload.get("owner_id") or payload.get("entity_id") or 0)
    entity = get_character_by_id(entity_id)
    if not entity:
        raise ValueError("Карточка для фотографии не найдена.")
    media_payload = payload.get("media") if isinstance(payload.get("media"), dict) else {
        "sourceSha256": payload.get("source_sha256", ""),
        "manifestPath": payload.get("manifest_path", ""),
        "original": {
            "path": payload.get("original_path", ""),
            "width": payload.get("width"),
            "height": payload.get("height"),
            "bytes": payload.get("bytes"),
            "mimeType": payload.get("mime_type"),
        },
        "variants": payload.get("variants", []),
    }
    variants = media_payload.get("variants") if isinstance(media_payload.get("variants"), list) else []
    webp_variants = [item for item in variants if isinstance(item, dict) and item.get("format") == "webp"]
    selected = max(webp_variants or variants, key=lambda item: int(item.get("width", 0)), default=None)
    file_path = str(payload.get("file_path") or (selected or {}).get("path") or "").strip()
    if not file_path.startswith("/media/generated/"):
        raise ValueError("Оптимизированный файл не найден.")

    with sqlite3.connect(CANONICAL_DATABASE) as connection:
        next_sort_order = connection.execute(
            "SELECT COALESCE(MAX(sort_order), 0) + 1 FROM managed_character_media WHERE character_id = ?",
            (entity_id,),
        ).fetchone()[0]
        cursor = connection.execute(
            """
            INSERT INTO managed_character_media(
                character_id, media_type, file_path, alt_text, caption, sort_order, created_at, updated_at
            ) VALUES (?, 'image', ?, ?, '', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (entity_id, file_path, str(payload.get("alt_text") or entity["name"]), next_sort_order),
        )
        media_id = int(cursor.lastrowid)
        if not entity.get("hero_media_id"):
            connection.execute(
                "UPDATE managed_characters SET hero_media_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (media_id, entity_id),
            )
        connection.commit()

    with sqlite3.connect(IDEMPOTENCY_DATABASE) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO media_assets(
                media_id, entity_id, source_sha256, manifest_path, original_path, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                media_id,
                entity_id,
                str(media_payload.get("sourceSha256", "")),
                str(media_payload.get("manifestPath", "")),
                str(media_payload.get("original", {}).get("path", "")),
                json.dumps(media_payload, ensure_ascii=False),
            ),
        )
        connection.commit()
    return media_id


def _soft_delete_media(media_id: int) -> bool:
    with sqlite3.connect(CANONICAL_DATABASE) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM managed_character_media WHERE id = ?",
            (media_id,),
        ).fetchone()
        if not row:
            return False
        entity_id = int(row["character_id"])
        media_json = json.dumps(dict(row), ensure_ascii=False)
        connection.execute("DELETE FROM managed_character_media WHERE id = ?", (media_id,))
        current = connection.execute(
            "SELECT hero_media_id FROM managed_characters WHERE id = ?",
            (entity_id,),
        ).fetchone()
        if current and current[0] == media_id:
            replacement = connection.execute(
                "SELECT id FROM managed_character_media WHERE character_id = ? ORDER BY sort_order, id LIMIT 1",
                (entity_id,),
            ).fetchone()
            connection.execute(
                "UPDATE managed_characters SET hero_media_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (replacement[0] if replacement else None, entity_id),
            )
        connection.commit()
    with sqlite3.connect(IDEMPOTENCY_DATABASE) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO media_trash(media_id, entity_id, media_json) VALUES (?, ?, ?)",
            (media_id, entity_id, media_json),
        )
        connection.commit()
    return True


def _update_party_builder_settings(values: dict[str, Any]) -> dict[str, int]:
    allowed = set(get_party_builder_settings())
    with sqlite3.connect(CANONICAL_DATABASE) as connection:
        for key, value in values.items():
            if key not in allowed:
                continue
            try:
                normalized = max(0, int(value))
            except (TypeError, ValueError):
                continue
            connection.execute(
                """
                INSERT INTO site_settings(key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, str(normalized)),
            )
        connection.commit()
    return get_party_builder_settings()


def _private_adapter_request() -> bool:
    expected = os.environ.get("SURPRIZ_ADAPTER_TOKEN", "").strip()
    supplied = request.headers.get("X-Adapter-Token", "")
    if expected:
        return bool(supplied) and supplied == expected
    return request.remote_addr in {"127.0.0.1", "::1"}


def _normalize_order_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    for key in ("celebrant_age", "children_count", "map_lat", "map_lng"):
        if data.get(key) is not None:
            data[key] = str(data[key])
    data["character_slugs"] = [
        str(slug).strip()
        for slug in data.get("character_slugs", [])
        if str(slug).strip()
    ]
    raw_addon_slugs = data.get("addon_slugs", [])
    if isinstance(raw_addon_slugs, str):
        raw_addon_slugs = [raw_addon_slugs]
    data["addon_slugs"] = [
        str(slug).strip()
        for slug in raw_addon_slugs
        if str(slug).strip()
    ]
    return data


def _order_for_json(order: dict[str, Any]) -> dict[str, Any]:
    value = dict(order)
    value["total_amount"] = int(order.get("total_price") or 0)
    return value


def _attach_calendar_links(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links = get_order_event_links(int(order["id"]) for order in orders if order.get("id"))
    for order in orders:
        order["calendar_event_link"] = links.get(int(order.get("id") or 0), "")
    return orders


def _calendar_sync_message(result: dict[str, Any]) -> tuple[bool, str]:
    errors = [str(result[key]) for key in ("import_error", "export_error") if result.get(key)]
    if errors:
        return False, " ".join(errors)
    parts: list[str] = []
    imported = result.get("import") or {}
    if not imported.get("skipped") and "total" in imported:
        parts.append(f"Прочитано событий: {imported.get('total', 0)}, закрывают время: {imported.get('matched', 0)}.")
    exported = result.get("export") or {}
    if exported.get("processed"):
        parts.append(f"Выгружено заказов: {exported.get('succeeded', 0)} из {exported.get('processed', 0)}.")
    return True, " ".join(parts) or "Синхронизация выполнена."


def _refresh_calendar_events() -> str:
    """Re-read the calendar after an admin change; returns an error message or ''."""
    try:
        import_calendar_now()
    except GoogleCalendarSyncBusy:
        # The running cycle or the next worker tick picks the change up.
        return ""
    except GoogleCalendarError as exc:
        return str(exc)
    return ""


def _calendar_mutation(action: str, payload: dict[str, Any]):
    if action == "save_client":
        save_client_credentials(str(payload.get("client_id", "")), str(payload.get("client_secret", "")))
        return jsonify(success=True, message="Данные приложения Google сохранены.")
    if action == "oauth_start":
        auth_url = build_authorization_url(resolve_redirect_uri(request.host_url))
        return jsonify(success=True, auth_url=auth_url, message="Открываем Google…")
    if action == "disconnect":
        disconnect_calendar()
        return jsonify(success=True, message="Google Календарь отключён.")
    if action == "list_calendars":
        return jsonify(success=True, calendars=list_calendars(), message="Календари загружены.")
    if action == "select_calendar":
        selected = select_calendar(str(payload.get("calendar_id", "")))
        error = _refresh_calendar_events()
        if error:
            return jsonify(success=False, message=f"Календарь выбран, но прочитать события не удалось: {error}")
        return jsonify(success=True, message=f"Выбран календарь «{selected['summary']}».")
    if action == "save_settings":
        values = payload.get("settings") if isinstance(payload.get("settings"), dict) else payload
        save_sync_settings(values)
        return jsonify(success=True, message="Настройки синхронизации сохранены.")
    if action == "sync_now":
        ok, message = _calendar_sync_message(
            run_sync_cycle(force_import=True, wait_seconds=MANUAL_SYNC_WAIT_SECONDS)
        )
        return jsonify(success=ok, message=message)
    if action == "backfill":
        count = enqueue_upcoming_confirmed_orders()
        try:
            ok, message = _calendar_sync_message(run_sync_cycle(wait_seconds=MANUAL_SYNC_WAIT_SECONDS))
        except GoogleCalendarSyncBusy:
            ok, message = True, "Заказы выгрузятся в течение минуты."
        prefix = f"В очередь поставлено подтверждённых заказов: {count}."
        return jsonify(success=ok, message=f"{prefix} {message}")
    if action == "toggle_ignore":
        set_event_ignored(str(payload.get("event_key", "")), bool(payload.get("ignored")))
        _refresh_calendar_events()
        return jsonify(success=True, message="Событие обновлено.")
    if action == "add_alias":
        add_calendar_alias(str(payload.get("phrase", "")), str(payload.get("entity_slug", "")))
        _refresh_calendar_events()
        return jsonify(success=True, message="Слово добавлено в словарь.")
    if action == "delete_alias":
        removed = remove_calendar_alias(int(payload.get("id") or 0))
        return jsonify(success=removed, message="Слово удалено." if removed else "Слово не найдено.")
    if action == "preview":
        return jsonify(success=True, recognition=preview_recognition(str(payload.get("text", ""))), message="Готово.")
    return jsonify(success=False, message="Операция не поддерживается."), 400


def create_app() -> Flask:
    _initialize_idempotency_database()
    init_customer_store()
    _ensure_customer_admin_columns()
    init_addon_store()
    init_partner_store()
    init_recommendation_store()
    init_promotion_store()
    init_admin_notifications_store()
    init_google_calendar()
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.secret_key = _required_secret()
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=os.environ.get("SURPRIZ_SECURE_COOKIES", "0") == "1",
        SESSION_COOKIE_SAMESITE="Lax",
        JSON_AS_ASCII=False,
    )

    @app.before_request
    def require_private_adapter():
        if request.path == "/health":
            return None
        if not _private_adapter_request():
            return jsonify(success=False, message="Adapter access denied."), 403
        return None

    @app.get("/health")
    def health():
        return jsonify(success=True, service="surpriz-adapter")

    @app.get("/api/v2/catalog")
    def catalog():
        return jsonify(
            success=True,
            characters=list_characters(status="active", entity_type="character"),
            shows=list_show_programs_for_public(),
        )

    @app.post("/api/v2/admin/login")
    def admin_login():
        payload = request.get_json(silent=True) or {}
        result = authenticate_admin(
            str(payload.get("username", "")),
            str(payload.get("password", "")),
            request.remote_addr or "unknown",
        )
        if not result.get("success"):
            return jsonify(result), 401
        session[ADMIN_SESSION_KEY] = int(result["admin"]["id"])
        session.permanent = True
        return jsonify(success=True, admin=result["admin"])

    @app.get("/api/v2/admin/session")
    def admin_session():
        admin = _current_admin()
        if not admin:
            return _admin_denied()
        return jsonify(success=True, authenticated=True, admin=admin)

    @app.post("/api/v2/admin/logout")
    def admin_logout():
        session.pop(ADMIN_SESSION_KEY, None)
        return jsonify(success=True)

    @app.get("/api/v2/admin/dashboard")
    def admin_dashboard():
        admin = _current_admin()
        if not admin:
            return _admin_denied()
        visits = get_dashboard_stats()
        order_summary = get_order_summary()
        revenue = get_revenue_stats()
        catalog_counts = visits.get("catalog_counts", {})
        return jsonify(
            success=True,
            authenticated=True,
            admin=admin,
            stats={
                "total_visits": visits.get("total_page_views", 0),
                "orders_total": order_summary.get("total", 0),
                "customers_total": len(get_customer_list()),
                "characters_total": catalog_counts.get("character", 0),
                "shows_total": catalog_counts.get("show_program", 0),
                "revenue_total": revenue.get("total", 0),
            },
            recent_orders=list_admin_orders(limit=8),
            popular_programs=[
                {**item, "orders_count": item.get("order_count", 0)}
                for item in get_popular_programs(6)
            ],
        )

    @app.get("/api/v2/admin/entities")
    def admin_list_entities():
        if not _current_admin():
            return _admin_denied()
        entity_type = str(request.args.get("entity_type", "")).strip()
        if entity_type not in {"character", "show_program"}:
            return jsonify(success=False, message="Неизвестный тип карточки."), 400
        items = list_characters(entity_type=entity_type)
        return jsonify(success=True, items=[_admin_entity_list_item(item) for item in items])

    @app.get("/api/v2/admin/entities/<int:entity_id>")
    def admin_get_entity(entity_id: int):
        if not _current_admin():
            return _admin_denied()
        entity = get_character_by_id(entity_id)
        if not entity:
            return jsonify(success=False, message="Карточка не найдена."), 404
        return jsonify(success=True, entity=_admin_entity_json(entity))

    @app.post("/api/v2/admin/entities")
    def admin_create_entity():
        if not _current_admin():
            return _admin_denied()
        payload = request.get_json(silent=True) or {}
        addon_settings = payload.get("addons")
        if not str(payload.get("name", "")).strip():
            return jsonify(success=False, message="Укажите название карточки."), 400
        try:
            entity_id = create_character(_entity_payload(payload))
            if str(payload.get("entity_type") or "character") == "show_program" and isinstance(addon_settings, list):
                _save_program_addon_settings(entity_id, addon_settings)
        except ValueError as error:
            return jsonify(success=False, message=str(error)), 400
        return jsonify(success=True, id=entity_id), 201

    @app.post("/api/v2/admin/entities/<int:entity_id>")
    def admin_update_entity(entity_id: int):
        if not _current_admin():
            return _admin_denied()
        current = get_character_by_id(entity_id)
        if not current:
            return jsonify(success=False, message="Карточка не найдена."), 404
        try:
            raw_payload = request.get_json(silent=True) or {}
            addon_settings = raw_payload.get("addons")
            payload = _entity_payload(raw_payload)
            update_character(entity_id, {**current, **payload})
            if current.get("entity_type") == "show_program" and isinstance(addon_settings, list):
                _save_program_addon_settings(entity_id, addon_settings)
        except ValueError as error:
            return jsonify(success=False, message=str(error)), 400
        return jsonify(success=True, id=entity_id)

    @app.post("/api/v2/admin/entities/reorder")
    def admin_reorder_entities():
        if not _current_admin():
            return _admin_denied()
        payload = request.get_json(silent=True) or {}
        ids = [int(value) for value in payload.get("ids", []) if str(value).strip().isdigit()]
        if len(ids) < 2:
            return jsonify(success=False, message="Нужно хотя бы две карточки."), 400
        # Reuse the slots the group already occupies, so reordering formats inside a
        # group never collides with the ordering of the standalone programmes.
        with sqlite3.connect(CANONICAL_DATABASE) as connection:
            placeholders = ",".join("?" for _ in ids)
            rows = connection.execute(
                f"SELECT id, sort_order FROM managed_characters WHERE id IN ({placeholders})",
                ids,
            ).fetchall()
            if len(rows) != len(ids):
                return jsonify(success=False, message="Карточка не найдена."), 404
            slots = sorted(int(row[1] or 0) for row in rows)
            for entity_id, slot in zip(ids, slots):
                connection.execute(
                    "UPDATE managed_characters SET sort_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (slot, entity_id),
                )
            connection.commit()
        return jsonify(success=True, order=ids)

    @app.delete("/api/v2/admin/entities/<int:entity_id>")
    def admin_delete_entity(entity_id: int):
        if not _current_admin():
            return _admin_denied()
        current = get_character_by_id(entity_id)
        if not current:
            return jsonify(success=False, message="Карточка не найдена."), 404
        delete_character(entity_id)
        return jsonify(success=True, id=entity_id, title=current.get("name") or "")

    @app.post("/api/v2/admin/entities/<int:entity_id>/crop")
    def admin_update_crop(entity_id: int):
        if not _current_admin():
            return _admin_denied()
        current = get_character_by_id(entity_id)
        if not current:
            return jsonify(success=False, message="Карточка не найдена."), 404
        payload = request.get_json(silent=True) or {}
        current.update(
            cover_offset_x=payload.get("cover_offset_x", current.get("cover_offset_x", 50)),
            cover_offset_y=payload.get("cover_offset_y", current.get("cover_offset_y", 50)),
            cover_fit=payload.get("cover_fit", current.get("cover_fit", "cover")),
            image_zoom=_clamp_image_zoom(payload.get("image_zoom", current.get("image_zoom", 100))),
            mobile_cover_offset_x=payload.get("mobile_cover_offset_x", current.get("mobile_cover_offset_x", 50)),
            mobile_cover_offset_y=payload.get("mobile_cover_offset_y", current.get("mobile_cover_offset_y", 50)),
            mobile_cover_fit=payload.get("mobile_cover_fit", current.get("mobile_cover_fit", "cover")),
            mobile_image_zoom=_clamp_image_zoom(payload.get("mobile_image_zoom", current.get("mobile_image_zoom", 100))),
        )
        update_character(entity_id, current)
        return jsonify(success=True, id=entity_id)

    @app.get("/api/v2/admin/section/<section>")
    def admin_section(section: str):
        if not _current_admin():
            return _admin_denied()
        if section == "orders":
            orders = list_admin_orders(
                status=request.args.get("status", ""),
                search=request.args.get("search", ""),
                date_from=request.args.get("date_from", ""),
                date_to=request.args.get("date_to", ""),
                customer_id=int(request.args["customer_id"]) if request.args.get("customer_id", "").isdigit() else None,
            )
            _attach_calendar_links(orders)
            return jsonify(
                success=True,
                items=orders,
                orders=orders,
                summary=get_order_summary(),
                status_labels=ORDER_STATUS_LABELS,
            )
        if section == "visitors":
            report = list_admin_visitors(
                search=request.args.get("search", ""),
                page=int(request.args.get("page", "1")) if request.args.get("page", "1").isdigit() else 1,
                per_page=30,
            )
            return jsonify(success=True, **report)
        if section == "media":
            media = _media_library()
            return jsonify(
                success=True,
                items=media,
                media=media,
                owners=_media_owners(),
                stats={
                    "originals": len(media),
                    "optimized": sum(1 for item in media if str(item.get("file_path", "")).startswith("/media/generated/")),
                    "processing": 0,
                    "bytes_saved": 0,
                },
            )
        if section == "taxonomy":
            return jsonify(success=True, categories=list_categories(True), tags=list_tags(True))
        if section == "addons":
            addons = list_addons(search=request.args.get("search", ""), status=request.args.get("status", ""))
            return jsonify(success=True, items=addons, addons=addons, promotions=list_promotions(include_hidden=True))
        if section == "partners":
            partners = list_partners()
            return jsonify(success=True, items=partners, partners=partners)
        if section == "recommendations":
            characters = list_characters(entity_type=ENTITY_TYPE_CHARACTER)
            shows = list_characters(entity_type=ENTITY_TYPE_SHOW_PROGRAM)
            simplify = lambda rows: [
                {"slug": str(row.get("slug") or ""), "name": str(row.get("name") or ""), "status": str(row.get("status") or "active")}
                for row in rows
                if row.get("slug")
            ]
            return jsonify(
                success=True,
                homepage_slots=HOMEPAGE_SLOTS,
                characters={"items": simplify(characters), "featured": get_featured_slugs(ENTITY_TYPE_CHARACTER)},
                shows={"items": simplify(shows), "featured": get_featured_slugs(ENTITY_TYPE_SHOW_PROGRAM)},
            )
        if section == "customers":
            customers = get_customer_list()
            search = request.args.get("search", "").strip().casefold()
            status = request.args.get("status", "").strip()
            if search:
                customers = [item for item in customers if search in f"{item.get('name', '')} {item.get('phone', '')}".casefold()]
            if status == "blocked":
                customers = [item for item in customers if item.get("is_blocked")]
            elif status == "active":
                customers = [item for item in customers if not item.get("is_blocked")]
            elif status == "repeat":
                customers = [item for item in customers if int(item.get("order_count") or 0) > 1]
            return jsonify(success=True, items=customers, customers=customers)
        if section == "analytics":
            visits = get_dashboard_stats()
            orders = get_order_summary()
            return jsonify(
                success=True,
                visits=visits,
                metrics={**visits, "orders_total": orders.get("total", 0)},
                top_pages=visits.get("top_pages", []),
                recent_visits=visits.get("recent_visits", []),
                revenue=get_revenue_stats(),
                popular_programs=get_popular_programs(10),
                popular_characters=get_popular_characters(10),
                orders=orders,
            )
        if section == "notifications":
            return jsonify(
                success=True,
                configured=is_notifications_configured(),
                bot_token_masked=bot_token_masked(),
                gateway_token_masked=gateway_token_masked(),
                recipients=list_recipients(),
            )
        if section == "calendar":
            return jsonify(success=True, **get_calendar_admin_payload(request.host_url))
        if section == "settings":
            public_settings = get_public_settings()
            party_builder_settings = get_party_builder_settings()
            return jsonify(
                success=True,
                settings=public_settings,
                party_builder=party_builder_settings,
                public_settings=public_settings,
                party_builder_settings=party_builder_settings,
            )
        return jsonify(success=False, message="Раздел не найден."), 404

    @app.post("/api/v2/admin/section/<section>")
    def admin_section_mutation(section: str):
        if not _current_admin():
            return _admin_denied()
        payload = request.get_json(silent=True) or {}
        action = str(payload.get("action", "save"))

        if section == "orders" and action in {"status", "update_status"}:
            updated = update_order_status(int(payload.get("id") or payload.get("order_id") or 0), str(payload.get("status", "")))
            return jsonify(success=updated, message="Статус обновлён." if updated else "Заказ не найден."), 200 if updated else 404

        if section == "orders" and action == "notify":
            order = get_order_by_id(int(payload.get("order_id") or 0))
            if not order:
                return jsonify(success=False, message="Заказ не найден."), 404
            result = send_order_notification(order)
            return jsonify(result), 200 if result.get("success") else 502

        if section == "settings":
            if action == "season_preset":
                settings = apply_new_year_preset(bool(payload.get("enabled")))
                return jsonify(success=True, settings=settings, party_builder=get_party_builder_settings())
            combined = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
            public_keys = set(get_public_settings())
            party_keys = set(get_party_builder_settings())
            public_values = payload.get("public_settings") or {key: value for key, value in combined.items() if key in public_keys}
            party_values = payload.get("party_builder_settings") or {key: value for key, value in combined.items() if key in party_keys}
            updated_public = update_public_settings({str(key): bool(value) for key, value in public_values.items()})
            updated_party = _update_party_builder_settings(party_values)
            return jsonify(
                success=True,
                settings=updated_public,
                party_builder=updated_party,
                public_settings=updated_public,
                party_builder_settings=updated_party,
            )

        if section == "taxonomy":
            resource = str(payload.get("resource") or payload.get("taxonomy") or "category")
            item_id = int(payload.get("id", 0) or 0)
            if resource == "category":
                if action == "delete":
                    return jsonify(success=delete_category(item_id))
                values = payload.get("values") or payload
                if item_id:
                    update_category(item_id, values.get("name", ""), values.get("slug", ""), values.get("description", ""), bool(values.get("is_visible", True)), linked_tag_id=values.get("linked_tag_id"))
                    return jsonify(success=True, id=item_id)
                new_id = create_category(values.get("name", ""), values.get("slug", ""), values.get("description", ""), bool(values.get("is_visible", True)), linked_tag_id=values.get("linked_tag_id"))
                return jsonify(success=True, id=new_id), 201
            if action == "delete":
                return jsonify(success=delete_tag(item_id))
            values = payload.get("values") or payload
            if item_id:
                update_tag(item_id, values.get("name", ""), values.get("slug", ""), values.get("description", ""), bool(values.get("is_visible", True)))
                return jsonify(success=True, id=item_id)
            new_id = create_tag(values.get("name", ""), values.get("slug", ""), values.get("description", ""), bool(values.get("is_visible", True)))
            return jsonify(success=True, id=new_id), 201

        if section == "recommendations":
            entity_type = str(payload.get("entity_type") or "")
            if entity_type not in {ENTITY_TYPE_CHARACTER, ENTITY_TYPE_SHOW_PROGRAM}:
                return jsonify(success=False, message="Неизвестный каталог."), 400
            raw = payload.get("featured")
            if not isinstance(raw, list):
                return jsonify(success=False, message="Ожидался список слагов."), 400
            saved = set_featured_slugs(entity_type, raw)
            return jsonify(success=True, featured=saved)

        if section == "partners":
            item_id = int(payload.get("id", 0) or 0)
            try:
                if action == "delete":
                    if not delete_partner(item_id):
                        return jsonify(success=False, message="Партнёр не найден."), 404
                    return jsonify(success=True, id=item_id)
                values = payload.get("values") if isinstance(payload.get("values"), dict) else payload
                if item_id:
                    return jsonify(success=True, partner=update_partner(item_id, values))
                return jsonify(success=True, partner=create_partner(values)), 201
            except ValueError as error:
                return jsonify(success=False, message=str(error)), 400

        if section == "addons":
            if str(payload.get("resource", "addon")) == "promotion":
                item_id = int(payload.get("id", 0) or 0)
                if action == "delete":
                    delete_promotion(item_id)
                    return jsonify(success=True)
                if action == "status":
                    current = get_promotion_by_id(item_id)
                    if not current:
                        return jsonify(success=False, message="Акция не найдена."), 404
                    update_promotion(item_id, {**current, "status": str(payload.get("status", "hidden"))})
                    return jsonify(success=True, id=item_id)
                values = payload.get("values") or payload
                if item_id:
                    update_promotion(item_id, values)
                    return jsonify(success=True, id=item_id)
                new_id = create_promotion(values)
                return jsonify(success=True, id=new_id), 201
            item_id = int(payload.get("id", 0) or 0)
            if action == "delete":
                return jsonify(success=delete_addon(item_id))
            if action == "status":
                return jsonify(success=update_addon_status(item_id, str(payload.get("status", "draft"))))
            values = payload.get("values") or payload
            if item_id:
                update_addon(item_id, values)
                return jsonify(success=True, id=item_id)
            new_id = create_addon(values)
            return jsonify(success=True, id=new_id), 201

        if section == "customers" and action == "unblock":
            updated = unblock_customer(int(payload.get("customer_id") or 0))
            return jsonify(success=updated, message="Клиент разблокирован." if updated else "Клиент не найден."), 200 if updated else 404

        if section == "media":
            if action in {"attach_generated", "upload"}:
                try:
                    media_id = _attach_generated_media(payload)
                except ValueError as error:
                    return jsonify(success=False, message=str(error)), 400
                return jsonify(success=True, media_id=media_id, message="Фотография добавлена."), 201
            media_id = int(payload.get("media_id") or 0)
            if action == "delete":
                updated = _soft_delete_media(media_id)
                return jsonify(success=updated, message="Медиа перемещено в корзину." if updated else "Медиа не найдено."), 200 if updated else 404
            entity_id = int(payload.get("owner_id") or payload.get("entity_id") or 0)
            entity = get_character_by_id(entity_id)
            if not entity:
                return jsonify(success=False, message="Карточка не найдена."), 404
            if action == "replace_hero":
                # The client used to pick which photo to drop from a snapshot taken
                # when the page loaded. Reading the current cover here means a stale
                # tab can never delete the wrong photo.
                with sqlite3.connect(CANONICAL_DATABASE) as connection:
                    row = connection.execute(
                        "SELECT hero_media_id FROM managed_characters WHERE id = ?",
                        (entity_id,),
                    ).fetchone()
                    previous = int(row[0]) if row and row[0] else None
                    valid = connection.execute(
                        "SELECT id FROM managed_character_media WHERE id = ? AND character_id = ?",
                        (media_id, entity_id),
                    ).fetchone()
                    if not valid:
                        return jsonify(success=False, message="Медиа не найдено."), 404
                    connection.execute(
                        "UPDATE managed_characters SET hero_media_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (media_id, entity_id),
                    )
                    connection.commit()
                if previous and previous != media_id:
                    _soft_delete_media(previous)
                return jsonify(success=True, replaced=previous)

            if action == "set_hero":
                with sqlite3.connect(CANONICAL_DATABASE) as connection:
                    valid = connection.execute(
                        "SELECT id FROM managed_character_media WHERE id = ? AND character_id = ?",
                        (media_id, entity_id),
                    ).fetchone()
                    if not valid:
                        return jsonify(success=False, message="Медиа не найдено."), 404
                    connection.execute(
                        "UPDATE managed_characters SET hero_media_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (media_id, entity_id),
                    )
                    connection.commit()
                return jsonify(success=True)
            if action == "update":
                with sqlite3.connect(CANONICAL_DATABASE) as connection:
                    cursor = connection.execute(
                        """
                        UPDATE managed_character_media
                        SET alt_text = ?, caption = ?, sort_order = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND character_id = ?
                        """,
                        (
                            str(payload.get("alt_text", "")).strip(),
                            str(payload.get("caption", "")).strip(),
                            int(payload.get("sort_order") or 0),
                            media_id,
                            entity_id,
                        ),
                    )
                    connection.commit()
                return jsonify(success=cursor.rowcount > 0)

        if section == "calendar":
            try:
                return _calendar_mutation(action, payload)
            except GoogleCalendarError as exc:
                return jsonify(success=False, message=str(exc)), 400

        if section == "notifications":
            if action == "add_recipient":
                return jsonify(add_recipient(str(payload.get("chat_id", "")), str(payload.get("label", ""))))
            if action == "delete_recipient":
                return jsonify(delete_recipient(int(payload.get("id") or payload.get("recipient_id") or 0)))
            if action == "toggle_recipient":
                return jsonify(toggle_recipient(int(payload.get("id") or payload.get("recipient_id") or 0), bool(payload.get("is_active"))))
            if action in {"test", "test_recipient"}:
                chat_id = str(payload.get("chat_id", ""))
                if not chat_id and payload.get("recipient_id"):
                    recipient = next((item for item in list_recipients() if item["id"] == int(payload["recipient_id"])), None)
                    chat_id = str((recipient or {}).get("chat_id", ""))
                return jsonify(send_test_message(chat_id))
            if action == "save_bot_token":
                set_setting("telegram_bot_token", str(payload.get("token", "")).strip())
                return jsonify(success=True)
            if action == "save_gateway_token":
                set_setting("telegram_gateway_token", str(payload.get("token", "")).strip())
                return jsonify(success=True)
            for key in ("telegram_bot_token", "telegram_gateway_token"):
                if str(payload.get(key, "")).strip():
                    set_setting(key, str(payload[key]).strip())
            return jsonify(success=True)

        return jsonify(success=False, message="Операция не поддерживается."), 400

    @app.get("/api/v2/admin/google-calendar/callback")
    def google_calendar_callback():
        if not _current_admin():
            return _admin_denied()
        if request.args.get("error"):
            return jsonify(success=False, message="Доступ к Google Календарю не выдан."), 400
        try:
            result = complete_authorization(request.args.get("code", ""), request.args.get("state", ""))
        except GoogleCalendarError as exc:
            return jsonify(success=False, message=str(exc)), 400
        _refresh_calendar_events()
        return jsonify(success=True, account_email=result.get("account_email", ""), message="Google Календарь подключён.")

    @app.get("/api/v2/account")
    def account():
        customer = _current_customer()
        if not customer:
            return jsonify(authenticated=False, orders=[])
        orders = [_order_for_json(order) for order in list_customer_orders(int(customer["id"]))]
        return jsonify(
            authenticated=True,
            customer={
                "id": customer["id"],
                "full_name": customer.get("full_name", ""),
                "phone_display": customer.get("phone_display", ""),
            },
            orders=orders,
        )

    @app.post("/api/v2/orders")
    def create_order():
        customer = _current_customer()
        if not customer:
            return jsonify(success=False, message="Подтвердите номер телефона перед заказом."), 401

        payload = request.get_json(silent=True) or {}
        lat = payload.get("map_lat")
        lng = payload.get("map_lng")
        if not is_inside_tashkent(lat, lng):
            return jsonify(success=False, message="Выбранный адрес находится вне доступной зоны Ташкента."), 400

        idempotency_key = str(payload.pop("idempotency_key", "")).strip()[:128]
        customer_id = int(customer["id"])
        with _serialized_order_creation():
            existing_public_id = _lookup_idempotency(idempotency_key, customer_id)
            if existing_public_id:
                return jsonify(success=True, public_id=existing_public_id, duplicate=True)

            result = create_party_order(customer_id, _normalize_order_payload(payload))
            if not result.get("success"):
                errors = result.get("errors") or {}
                message = next(iter(errors.values()), "Проверьте данные заказа.")
                return jsonify(success=False, message=message, errors=errors), 400

            order = result["order"]
            public_id = str(order["public_id"])
            _save_idempotency(idempotency_key, customer_id, public_id)

        try:
            send_order_notification(order)
        except Exception:
            app.logger.exception("Order %s was created, but Telegram notification failed.", public_id)
        return jsonify(success=True, public_id=public_id, order=_order_for_json(order)), 201

    @app.get("/api/v2/orders/<public_id>")
    def order_detail(public_id: str):
        customer = _current_customer()
        if not customer:
            return jsonify(success=False, message="Войдите в личный кабинет."), 401
        order = get_order_by_public_id(public_id, customer_id=int(customer["id"]))
        if not order:
            return jsonify(success=False, message="Заказ не найден."), 404
        return jsonify(success=True, order=_order_for_json(order))

    @app.post("/api/v2/auth/logout")
    def logout():
        session.pop(CUSTOMER_SESSION_KEY, None)
        return jsonify(success=True)

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(
        host=os.environ.get("SURPRIZ_ADAPTER_HOST", "127.0.0.1"),
        port=int(os.environ.get("SURPRIZ_ADAPTER_PORT", "5051")),
        debug=False,
    )
