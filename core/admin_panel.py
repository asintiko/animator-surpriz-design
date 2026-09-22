from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from flask import Flask, flash, redirect, render_template, request, session, url_for

from .admin_store import (
    apply_new_year_preset,
    authenticate_admin,
    get_admin_by_id,
    get_customer_list,
    get_dashboard_stats,
    get_login_attempt_state,
    get_popular_characters,
    get_popular_programs,
    get_public_settings,
    get_revenue_stats,
    list_admin_visitors,
    unblock_customer,
    update_public_settings,
)
from .promotion_store import (
    create_promotion,
    delete_promotion,
    get_program_promotion_ids,
    get_promotion_by_id,
    list_promotions,
    set_program_promotions,
    update_promotion,
)
from .addon_store import (
    create_addon,
    delete_addon,
    get_addon_by_id,
    get_program_addon_settings,
    list_active_addons,
    list_addons,
    set_program_addons,
    update_addon,
    update_addon_status,
    upload_addon_image,
)
from .catalog_store import (
    DEFAULT_EXTRA_CHARACTER_PRICE,
    DEFAULT_EXTRA_MEMBER_PRICE,
    DEFAULT_INCLUDED_CHARACTERS_COUNT,
    DEFAULT_INCLUDED_MEMBERS_COUNT,
    DEFAULT_SHOW_PROGRAM_DURATION_MINUTES,
    DEFAULT_SHOW_PROGRAM_PRICE,
    ENTITY_TYPE_CHARACTER,
    ENTITY_TYPE_SHOW_PROGRAM,
    attach_media_counts,
    create_category,
    create_character,
    create_tag,
    delete_category,
    delete_character,
    delete_media,
    delete_tag,
    get_character_by_id,
    get_show_program_character_ids,
    list_categories,
    list_categories_with_characters,
    list_characters,
    list_tags,
    set_show_program_characters,
    update_category,
    update_character,
    update_character_status,
    update_media_metadata,
    update_tag,
    upload_character_media,
)
from .customer_store import ORDER_STATUS_LABELS, get_order_summary, list_admin_orders, update_order_status
from .admin_notifications import (
    add_recipient as _notify_add_recipient,
    delete_recipient as _notify_delete_recipient,
    is_notifications_configured,
    list_recipients as _notify_list_recipients,
    send_test_message as _notify_send_test,
    toggle_recipient as _notify_toggle_recipient,
    bot_token_masked as _notify_bot_token_masked,
    gateway_token_masked as _notify_gateway_token_masked,
)

ADMIN_SESSION_KEY = "admin_user_id"
ENTITY_TYPE_LABELS = {
    ENTITY_TYPE_CHARACTER: {
        "singular": "персонаж",
        "singular_title": "Персонаж",
        "plural_title": "Персонажи",
        "new_title": "Новый персонаж",
        "edit_prefix": "Редактирование персонажа",
        "tab": "catalog",
        "back_label": "Назад к каталогу",
        "submit_create": "Создать карточку",
        "submit_save": "Сохранить карточку",
        "delete_confirm": "Удалить персонажа?",
        "media_delete_confirm": "Удалить это медиа?",
        "create_flash": "Персонаж создан.",
        "save_flash": "Карточка сохранена.",
        "delete_flash": "Персонаж удалён.",
        "not_found_flash": "Персонаж не найден.",
    },
    ENTITY_TYPE_SHOW_PROGRAM: {
        "singular": "шоу-программа",
        "singular_title": "Шоу-программа",
        "plural_title": "Шоу-программы",
        "new_title": "Новая шоу-программа",
        "edit_prefix": "Редактирование шоу-программы",
        "tab": "show_programs",
        "back_label": "Назад к шоу-программам",
        "submit_create": "Создать шоу-программу",
        "submit_save": "Сохранить шоу-программу",
        "delete_confirm": "Удалить шоу-программу?",
        "media_delete_confirm": "Удалить это медиа?",
        "create_flash": "Шоу-программа создана.",
        "save_flash": "Шоу-программа сохранена.",
        "delete_flash": "Шоу-программа удалена.",
        "not_found_flash": "Шоу-программа не найдена.",
    },
}
SHOW_PROGRAM_STATUS_LABELS = {
    "active": "Активна",
    "draft": "Черновик",
    "hidden": "Скрыта",
}
ADDON_STATUS_LABELS = {
    "active": "Активна",
    "hidden": "Скрыта",
}
SETTING_LABELS = {
    "new_year_season_enabled": {
        "title": "Сезон Нового года",
        "description": "Главный сезонный режим. Используй как общий переключатель на зимний период.",
    },
    "show_new_year_menu_link": {
        "title": "Показывать пункт 'Новый год' в верхнем меню",
        "description": "Возвращает сезонную вкладку в шапку сайта и мобильное меню.",
    },
    "show_home_new_year_showcase": {
        "title": "Показывать новогодний блок на главной",
        "description": "Возвращает скрытую новогоднюю витрину на главную страницу.",
    },
    "show_snow": {
        "title": "Включить снег",
        "description": "Включает снежный эффект на сайте.",
    },
    "show_promotions": {
        "title": "Показывать акции",
        "description": "Возвращает promo-страницы, ссылки на акции и правый блок в футере.",
    },
    "hide_easter_egg": {
        "title": "Скрыть пасхалку в каталоге",
        "description": "Прячет видео-пасхалку (Лабубу) на десктопе. Если выключено — на 5-й карточке /catalog/ при наведении автоматически проигрывается видео со звуком.",
    },
    "picker_enabled": {
        "title": "Picker (dev): показывать инструмент выбора элементов",
        "description": "Включает плавающую панель в правом верхнем углу для разметки UI-багов и отправки их разработчику. Используется только локально/при отладке.",
    },
}


def _get_client_ip() -> str:
    # ProxyFix has already reduced the trusted nginx hop to remote_addr.
    # Reading raw X-Forwarded-For here would let clients rotate lockout keys.
    return request.remote_addr or ""


def _clear_site_cache() -> None:
    from .loader import load_page_bundle

    load_page_bundle.cache_clear()


def _get_current_admin() -> dict[str, object] | None:
    admin_id = session.get(ADMIN_SESSION_KEY)
    if not admin_id:
        return None
    return get_admin_by_id(int(admin_id))


def _normalize_bool(value: str | None) -> bool:
    return value == "on"


def _normalize_int_list(values: list[str]) -> list[int]:
    normalized: list[int] = []
    for value in values:
        try:
            normalized.append(int(value))
        except (TypeError, ValueError):
            continue
    return normalized


def _normalize_optional_int(value: str | None) -> int | None:
    try:
        return int(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


def _normalize_show_status(value: str | None) -> str:
    return value if value in SHOW_PROGRAM_STATUS_LABELS else "draft"


def _format_admin_money(value: Any) -> str:
    try:
        amount = int(value or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return "Цена не указана"
    return f"{amount:,}".replace(",", " ") + " сум"


def _format_admin_duration(value: Any) -> str:
    try:
        minutes = int(value or 0)
    except (TypeError, ValueError):
        minutes = 0
    if minutes <= 0:
        return "Длительность не указана"
    if minutes == 60:
        return "1 час"
    if minutes % 60 == 0:
        return f"{minutes // 60} ч"
    return f"{minutes} минут"


def _format_admin_age(age_from: Any, age_to: Any) -> str:
    start = _normalize_optional_int(str(age_from)) if age_from not in {None, ""} else None
    end = _normalize_optional_int(str(age_to)) if age_to not in {None, ""} else None
    if start is not None and end is not None:
        return f"{start}-{end} лет"
    if start is not None:
        return f"от {start} лет"
    if end is not None:
        return f"до {end} лет"
    return "Возраст не указан"


def _show_completeness(show: dict[str, Any]) -> dict[str, Any]:
    checks = [
        bool(show.get("name")),
        bool(show.get("slug")),
        bool(show.get("hero_file_path")),
        bool(show.get("short_description")),
        bool(show.get("description")),
        int(show.get("base_price") or 0) > 0,
        int(show.get("default_duration_minutes") or 0) > 0,
        bool(show.get("included_items")),
        bool(show.get("suitable_for")),
        bool(show.get("seo_title") or show.get("seo_description")),
    ]
    complete = sum(1 for item in checks if item)
    total = len(checks)
    return {
        "complete": complete,
        "total": total,
        "percent": int(round((complete / total) * 100)) if total else 0,
    }


def _decorate_show_programs_for_admin(show_programs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for show in show_programs:
        show["status_label"] = SHOW_PROGRAM_STATUS_LABELS.get(show.get("status"), "Черновик")
        show["price_label"] = _format_admin_money(show.get("base_price"))
        show["duration_label"] = _format_admin_duration(show.get("default_duration_minutes"))
        show["age_label"] = _format_admin_age(show.get("age_from"), show.get("age_to"))
        show["completeness"] = _show_completeness(show)
    return show_programs


def _decorate_addons_for_admin(addons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for addon in addons:
        addon["status_label"] = ADDON_STATUS_LABELS.get(addon.get("status"), "Скрыта")
        addon["price_label"] = _format_admin_money(addon.get("price"))
        addon["cost_label"] = _format_admin_money(addon.get("cost"))
        addon["duration_label"] = _format_admin_duration(addon.get("duration_minutes"))
    return addons


def _decorate_characters_for_show_links(characters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for character in characters:
        category_names = [name for name in character.get("category_names", []) if name and name != "Все"]
        character["category_label"] = ", ".join(category_names) or "Общая витрина"
        character["duplicate_label"] = (
            f"{int(character.get('duplicate_count') or 0)} дубликат(а)"
            if int(character.get("duplicate_count") or 0) > 0
            else "Без дубликатов"
        )
    return characters


def _addon_form_defaults(addon: dict[str, Any] | None = None) -> dict[str, Any]:
    if addon:
        return addon
    return {
        "id": None,
        "name": "",
        "slug": "",
        "status": "active",
        "sort_order": 0,
        "image_path": "",
        "short_description": "",
        "description": "",
        "price": 0,
        "cost": 0,
        "duration_minutes": 0,
        "type": "",
        "seo_title": "",
        "seo_description": "",
        "program_ids": [],
    }


def _collect_addon_form_data() -> dict[str, Any]:
    return {
        "name": request.form.get("name", "").strip(),
        "slug": request.form.get("slug", "").strip(),
        "status": request.form.get("status", "hidden").strip(),
        "sort_order": request.form.get("sort_order", "0").strip(),
        "short_description": request.form.get("short_description", "").strip(),
        "description": request.form.get("description", "").strip(),
        "price": request.form.get("price", "0").strip(),
        "cost": request.form.get("cost", "0").strip(),
        "duration_minutes": request.form.get("duration_minutes", "0").strip(),
        "type": request.form.get("type", "").strip(),
        "seo_title": request.form.get("seo_title", "").strip(),
        "seo_description": request.form.get("seo_description", "").strip(),
    }


def _collect_show_addon_selections() -> list[dict[str, Any]]:
    selections: list[dict[str, Any]] = []
    available_ids = set(_normalize_int_list(request.form.getlist("addon_available")))
    for addon_id in available_ids:
        selections.append(
            {
                "addon_id": addon_id,
                "is_recommended": request.form.get(f"addon_recommended_{addon_id}") == "on",
                "is_default": request.form.get(f"addon_default_{addon_id}") == "on",
                "is_free_choice": request.form.get(f"addon_free_choice_{addon_id}") == "on",
                "gift_mode": request.form.get(f"addon_gift_mode_{addon_id}", "none").strip() or "none",
                "gift_group": request.form.get(f"addon_gift_group_{addon_id}", "").strip(),
                "sort_order": request.form.get(f"addon_sort_{addon_id}", "0").strip(),
            }
        )
    return selections


def _get_entity_labels(entity_type: str) -> dict[str, str]:
    return ENTITY_TYPE_LABELS[ENTITY_TYPE_SHOW_PROGRAM if entity_type == ENTITY_TYPE_SHOW_PROGRAM else ENTITY_TYPE_CHARACTER]


def _character_form_defaults(
    character: dict[str, Any] | None = None,
    *,
    entity_type: str = ENTITY_TYPE_CHARACTER,
) -> dict[str, Any]:
    if character:
        return character
    return {
        "id": None,
        "entity_type": entity_type,
        "name": "",
        "slug": "",
        "short_description": "",
        "description": "",
        "seo_title": "",
        "seo_description": "",
        "search_terms": "",
        "duplicate_count": 0,
        "contact_phone": "+998 (99) 892-65-65",
        "telegram_url": "tg://resolve?phone=998998926565",
        "base_price": DEFAULT_SHOW_PROGRAM_PRICE if entity_type == ENTITY_TYPE_SHOW_PROGRAM else 0,
        "default_duration_minutes": DEFAULT_SHOW_PROGRAM_DURATION_MINUTES,
        "included_characters_count": DEFAULT_INCLUDED_CHARACTERS_COUNT,
        "extra_character_price_3": DEFAULT_EXTRA_CHARACTER_PRICE,
        "extra_character_price_4_plus": DEFAULT_EXTRA_CHARACTER_PRICE,
        "ensemble_members": [],
        "ensemble_included_count": DEFAULT_INCLUDED_MEMBERS_COUNT,
        "ensemble_extra_member_price": DEFAULT_EXTRA_MEMBER_PRICE,
        "sort_order": 0,
        "age_from": None,
        "age_to": None,
        "show_category": "",
        "format_tags": "",
        "included_items": "",
        "suitable_for": "",
        "restrictions": "",
        "video_url": "",
        "status": "active",
        "media": [],
        "category_ids": [],
        "tag_ids": [],
        "hero_media_id": None,
    }


def _collect_character_form_data(*, entity_type: str) -> dict[str, Any]:
    return {
        "entity_type": entity_type,
        "name": request.form.get("name", "").strip(),
        "slug": request.form.get("slug", "").strip(),
        "short_description": request.form.get("short_description", "").strip(),
        "description": request.form.get("description", "").strip(),
        "seo_title": request.form.get("seo_title", "").strip(),
        "seo_description": request.form.get("seo_description", "").strip(),
        "search_terms": request.form.get("search_terms", "").strip(),
        "duplicate_count": request.form.get("duplicate_count", "0").strip(),
        "ensemble_members": request.form.get("ensemble_members", "").strip(),
        "ensemble_included_count": request.form.get("ensemble_included_count", "").strip(),
        "ensemble_extra_member_price": request.form.get("ensemble_extra_member_price", "").strip(),
        "contact_phone": request.form.get("contact_phone", "").strip(),
        "telegram_url": request.form.get("telegram_url", "").strip(),
        "base_price": request.form.get("base_price", "").strip(),
        "default_duration_minutes": request.form.get("default_duration_minutes", "").strip(),
        "status": request.form.get("status", "active").strip() or "active",
        "category_ids": _normalize_int_list(request.form.getlist("category_ids")),
        "tag_ids": _normalize_int_list(request.form.getlist("tag_ids")),
        "cover_offset_x": request.form.get("cover_offset_x", "50").strip() or "50",
        "cover_offset_y": request.form.get("cover_offset_y", "50").strip() or "50",
        "cover_fit": request.form.get("cover_fit", "cover").strip() or "cover",
    }


def _collect_show_program_form_data() -> dict[str, Any]:
    return {
        "entity_type": ENTITY_TYPE_SHOW_PROGRAM,
        "name": request.form.get("name", "").strip(),
        "slug": request.form.get("slug", "").strip(),
        "status": _normalize_show_status(request.form.get("status", "draft").strip()),
        "sort_order": request.form.get("sort_order", "0").strip(),
        "short_description": request.form.get("short_description", "").strip(),
        "description": request.form.get("description", "").strip(),
        "seo_title": request.form.get("seo_title", "").strip(),
        "seo_description": request.form.get("seo_description", "").strip(),
        "base_price": request.form.get("base_price", "").strip(),
        "default_duration_minutes": request.form.get("default_duration_minutes", "").strip(),
        "included_characters_count": request.form.get("included_characters_count", "").strip(),
        "extra_character_price_3": request.form.get("extra_character_price_3", "").strip(),
        "extra_character_price_4_plus": request.form.get("extra_character_price_4_plus", "").strip(),
        "age_from": request.form.get("age_from", "").strip(),
        "age_to": request.form.get("age_to", "").strip(),
        "show_category": request.form.get("show_category", "").strip(),
        "format_tags": request.form.get("format_tags", "").strip(),
        "variant_group_slug": request.form.get("variant_group_slug", "").strip(),
        "variant_group_name": request.form.get("variant_group_name", "").strip(),
        "variant_label": request.form.get("variant_label", "").strip(),
        "included_items": request.form.get("included_items", "").strip(),
        "suitable_for": request.form.get("suitable_for", "").strip(),
        "restrictions": request.form.get("restrictions", "").strip(),
        "video_url": request.form.get("video_url", "").strip(),
        "search_terms": "",
        "duplicate_count": 0,
        "contact_phone": "",
        "telegram_url": "",
        "category_ids": [],
        "tag_ids": [],
        "cover_offset_x": request.form.get("cover_offset_x", "50").strip() or "50",
        "cover_offset_y": request.form.get("cover_offset_y", "50").strip() or "50",
        "cover_fit": request.form.get("cover_fit", "cover").strip() or "cover",
    }


def _collect_media_updates(character: dict[str, Any]) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for media in character.get("media", []):
        media_id = int(media["id"])
        try:
            sort_order = int(request.form.get(f"media_sort_{media_id}", media["sort_order"]))
        except (TypeError, ValueError):
            sort_order = int(media["sort_order"])
        updates.append(
            {
                "id": media_id,
                "alt_text": request.form.get(f"media_alt_{media_id}", media.get("alt_text", "")).strip(),
                "caption": request.form.get(f"media_caption_{media_id}", media.get("caption", "")).strip(),
                "sort_order": sort_order,
            }
        )
    return updates


def _render_dashboard(admin: dict[str, Any], *, active_tab: str = "info"):
    settings = get_public_settings()
    stats = get_dashboard_stats()
    stats["popular_programs"] = get_popular_programs(5)
    stats["popular_characters"] = get_popular_characters(5)
    stats["revenue"] = get_revenue_stats()
    stats["customers"] = get_customer_list()
    visitor_search = request.args.get("visitor_search", "").strip()
    raw_visitor_page = request.args.get("visitor_page", "1").strip()
    visitor_page = int(raw_visitor_page) if raw_visitor_page.isdigit() else 1
    visitors = (
        list_admin_visitors(search=visitor_search, page=visitor_page)
        if active_tab == "visitors"
        else None
    )
    catalog_search = request.args.get("search", "").strip()
    catalog_status = request.args.get("status", "").strip()
    show_search = request.args.get("show_search", "").strip()
    show_status = request.args.get("show_status", "").strip()
    addon_search = request.args.get("addon_search", "").strip()
    addon_status = request.args.get("addon_status", "").strip()
    order_status = request.args.get("order_status", "").strip()
    order_search = request.args.get("order_search", "").strip()
    order_date_from = request.args.get("order_date_from", "").strip()
    order_date_to = request.args.get("order_date_to", "").strip()
    _raw_cid = request.args.get("order_customer_id", "").strip()
    order_customer_id = int(_raw_cid) if _raw_cid.isdigit() else None
    show_programs = _decorate_show_programs_for_admin(
        attach_media_counts(list_characters(search=show_search, status=show_status, entity_type=ENTITY_TYPE_SHOW_PROGRAM))
    )
    addons = _decorate_addons_for_admin(list_addons(search=addon_search, status=addon_status))
    promotions = list_promotions(include_hidden=True)

    return render_template(
        "admin/dashboard.html",
        title="Админка Surpriz",
        admin=admin,
        active_tab=active_tab,
        stats=stats,
        settings=settings,
        visitors=visitors,
        visitor_filters={"search": visitor_search},
        setting_labels=SETTING_LABELS,
        characters=attach_media_counts(list_characters(search=catalog_search, status=catalog_status, entity_type=ENTITY_TYPE_CHARACTER)),
        show_programs=show_programs,
        addons=addons,
        promotions=promotions,
        categories=list_categories_with_characters(include_hidden=True),
        tags=list_tags(include_hidden=True),
        catalog_filters={"search": catalog_search, "status": catalog_status},
        show_filters={"search": show_search, "status": show_status},
        addon_filters={"search": addon_search, "status": addon_status},
        show_status_labels=SHOW_PROGRAM_STATUS_LABELS,
        addon_status_labels=ADDON_STATUS_LABELS,
        orders=list_admin_orders(
            status=order_status,
            limit=120,
            search=order_search,
            date_from=order_date_from,
            date_to=order_date_to,
            customer_id=order_customer_id,
        ),
        order_summary=get_order_summary(),
        order_status_filter=order_status,
        order_customer_id=order_customer_id,
        order_filters={
            "status": order_status,
            "search": order_search,
            "date_from": order_date_from,
            "date_to": order_date_to,
            "customer_id": order_customer_id,
        },
        order_status_labels=ORDER_STATUS_LABELS,
        notification_recipients=_notify_list_recipients(),
        notifications_configured=is_notifications_configured(),
        bot_token_masked=_notify_bot_token_masked(),
        gateway_token_masked=_notify_gateway_token_masked(),
    )


def admin_required(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        admin = _get_current_admin()
        if not admin:
            flash("Сначала войдите в админку.", "warning")
            return redirect(url_for("admin_login"))
        return view(admin=admin, *args, **kwargs)

    return wrapped


def register_admin_routes(app: Flask) -> None:
    @app.get("/admin")
    def admin_root():
        return redirect(url_for("admin_dashboard"))

    @app.get("/admin/addons/")
    @admin_required
    def admin_addons_redirect(admin):
        return redirect(url_for("admin_dashboard", tab="addons"))

    @app.get("/admin/show-programs/")
    @admin_required
    def admin_show_programs_redirect(admin):
        return redirect(url_for("admin_dashboard", tab="show_programs"))

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        current_admin = _get_current_admin()
        if current_admin:
            return redirect(url_for("admin_dashboard"))

        username = request.form.get("username", "").strip() if request.method == "POST" else ""
        attempt_state = get_login_attempt_state(username, _get_client_ip()) if username else None

        if request.method == "POST":
            password = request.form.get("password", "")
            auth_result = authenticate_admin(username=username, password=password, ip_address=_get_client_ip())
            if auth_result["success"]:
                session[ADMIN_SESSION_KEY] = auth_result["admin"]["id"]
                flash("Вход выполнен.", "success")
                return redirect(url_for("admin_dashboard"))

            flash(auth_result["message"], "error")
            attempt_state = get_login_attempt_state(username, _get_client_ip())

        return render_template(
            "admin/login.html",
            title="Вход в админку Surpriz",
            username=username,
            attempt_state=attempt_state,
        )

    @app.post("/admin/logout")
    @admin_required
    def admin_logout(admin):
        session.pop(ADMIN_SESSION_KEY, None)
        flash("Вы вышли из админки.", "success")
        return redirect(url_for("admin_login"))

    @app.get("/admin/")
    @admin_required
    def admin_dashboard(admin):
        active_tab = request.args.get("tab", "info")
        if active_tab not in {
            "info",
            "settings",
            "catalog",
            "show_programs",
            "addons",
            "promotions",
            "orders",
            "notifications",
            "customers",
            "visitors",
        }:
            active_tab = "info"
        return _render_dashboard(admin, active_tab=active_tab)

    @app.post("/admin/settings")
    @admin_required
    def admin_update_settings(admin):
        values = {key: _normalize_bool(request.form.get(key)) for key in SETTING_LABELS}
        update_public_settings(values)
        _clear_site_cache()
        flash("Настройки сохранены.", "success")
        return redirect(url_for("admin_dashboard", tab="settings"))

    @app.post("/admin/settings/season-preset")
    @admin_required
    def admin_apply_season_preset(admin):
        enabled = request.form.get("enabled") == "1"
        apply_new_year_preset(enabled=enabled)
        _clear_site_cache()
        flash(
            "Новогодний сезон включён." if enabled else "Новогодний сезон выключен.",
            "success",
        )
        return redirect(url_for("admin_dashboard", tab="settings"))

    @app.post("/admin/notifications/recipients")
    @admin_required
    def admin_notifications_add(admin):
        chat_id = request.form.get("chat_id", "").strip()
        label = request.form.get("label", "").strip()
        result = _notify_add_recipient(chat_id, label)
        flash(result["message"], "success" if result["success"] else "error")
        return redirect(url_for("admin_dashboard", tab="notifications"))

    @app.post("/admin/notifications/recipients/<int:recipient_id>/delete")
    @admin_required
    def admin_notifications_delete(admin, recipient_id: int):
        result = _notify_delete_recipient(recipient_id)
        flash(result["message"], "success" if result["success"] else "error")
        return redirect(url_for("admin_dashboard", tab="notifications"))

    @app.post("/admin/notifications/recipients/<int:recipient_id>/toggle")
    @admin_required
    def admin_notifications_toggle(admin, recipient_id: int):
        is_active = request.form.get("is_active") == "1"
        result = _notify_toggle_recipient(recipient_id, is_active)
        flash(result["message"], "success" if result["success"] else "error")
        return redirect(url_for("admin_dashboard", tab="notifications"))

    @app.post("/admin/notifications/recipients/<int:recipient_id>/test")
    @admin_required
    def admin_notifications_test(admin, recipient_id: int):
        recipients = _notify_list_recipients()
        recipient = next((item for item in recipients if item["id"] == recipient_id), None)
        if not recipient:
            flash("Получатель не найден.", "error")
            return redirect(url_for("admin_dashboard", tab="notifications"))
        result = _notify_send_test(recipient["chat_id"])
        flash(result["message"], "success" if result["success"] else "error")
        return redirect(url_for("admin_dashboard", tab="notifications"))

    @app.post("/admin/notifications/bot-token")
    @admin_required
    def admin_notifications_bot_token(admin):
        from .admin_notifications import set_setting as _notify_set_setting
        token = request.form.get("bot_token", "").strip()
        _notify_set_setting("bot_token", token)
        flash("Токен бота сохранён." if token else "Токен бота очищен.", "success")
        return redirect(url_for("admin_dashboard", tab="notifications"))

    @app.post("/admin/notifications/gateway-token")
    @admin_required
    def admin_notifications_gateway_token(admin):
        from .admin_notifications import set_setting as _notify_set_setting
        token = request.form.get("gateway_token", "").strip()
        _notify_set_setting("telegram_gateway_token", token)
        flash("Токен Telegram Gateway сохранён." if token else "Токен Telegram Gateway очищен.", "success")
        return redirect(url_for("admin_dashboard", tab="notifications"))

    @app.post("/admin/orders/<int:order_id>/status")
    @admin_required
    def admin_update_order_status(admin, order_id: int):
        status = request.form.get("status", "").strip().lower()
        admin_actor = f"{admin.get('username') or 'admin'} (admin:{admin.get('id')})"
        if update_order_status(order_id, status, source="admin", actor=admin_actor):
            flash("Статус заказа обновлен.", "success")
        else:
            flash("Не удалось обновить статус заказа.", "error")
        return redirect(url_for("admin_dashboard", tab="orders", order_status=request.args.get("order_status", "").strip()))

    @app.post("/admin/orders/<int:order_id>/notify")
    @admin_required
    def admin_resend_order_notification(admin, order_id: int):
        from .customer_store import get_order_by_id
        from .admin_notifications import send_order_notification
        order = get_order_by_id(order_id)
        if not order:
            flash("Заказ не найден.", "error")
            return redirect(url_for("admin_dashboard", tab="orders"))
        result = send_order_notification(order)
        flash(result["message"], "success" if result["success"] else "error")
        return redirect(url_for("admin_dashboard", tab="orders"))

    @app.post("/admin/customers/<int:customer_id>/unblock")
    @admin_required
    def admin_unblock_customer(admin, customer_id: int):
        if unblock_customer(customer_id):
            flash("Блокировка снята.", "success")
        else:
            flash("Клиент не найден.", "error")
        return redirect(url_for("admin_dashboard", tab="customers"))

    @app.route("/admin/addons/new", methods=["GET", "POST"])
    @admin_required
    def admin_addon_create(admin):
        if request.method == "POST":
            payload = _collect_addon_form_data()
            if not payload["name"]:
                flash("У доп. услуги должно быть название.", "error")
            else:
                addon_id = create_addon(payload)
                image_path = upload_addon_image(addon_id, request.files.get("image_file"))
                _clear_site_cache()
                flash("Доп. услуга создана." + (" Обложка загружена." if image_path else ""), "success")
                return redirect(url_for("admin_addon_edit", addon_id=addon_id))

        return render_template(
            "admin/addon_form.html",
            title="Новая доп. услуга",
            admin=admin,
            active_tab="addons",
            addon=_addon_form_defaults(),
            is_new=True,
            addon_status_labels=ADDON_STATUS_LABELS,
            show_programs=_decorate_show_programs_for_admin(
                attach_media_counts(list_characters(entity_type=ENTITY_TYPE_SHOW_PROGRAM))
            ),
        )

    @app.route("/admin/addons/<int:addon_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_addon_edit(addon_id: int, admin):
        addon = get_addon_by_id(addon_id)
        if not addon:
            flash("Доп. услуга не найдена.", "error")
            return redirect(url_for("admin_dashboard", tab="addons"))

        if request.method == "POST":
            payload = _collect_addon_form_data()
            if not payload["name"]:
                flash("У доп. услуги должно быть название.", "error")
            else:
                update_addon(addon_id, payload)
                image_path = upload_addon_image(addon_id, request.files.get("image_file"))
                _clear_site_cache()
                flash("Доп. услуга сохранена." + (" Обложка обновлена." if image_path else ""), "success")
                return redirect(url_for("admin_addon_edit", addon_id=addon_id))

        addon = _addon_form_defaults(get_addon_by_id(addon_id) or addon)
        show_programs = _decorate_show_programs_for_admin(
            attach_media_counts(list_characters(entity_type=ENTITY_TYPE_SHOW_PROGRAM))
        )
        used_program_ids = []
        for program in show_programs:
            addon_settings = get_program_addon_settings(int(program["id"]))
            if addon_id in addon_settings:
                used_program_ids.append(int(program["id"]))
        addon["program_ids"] = used_program_ids
        return render_template(
            "admin/addon_form.html",
            title=f"Редактирование доп. услуги: {addon['name']}",
            admin=admin,
            active_tab="addons",
            addon=addon,
            is_new=False,
            addon_status_labels=ADDON_STATUS_LABELS,
            show_programs=show_programs,
        )

    @app.post("/admin/addons/<int:addon_id>/status")
    @admin_required
    def admin_addon_status(addon_id: int, admin):
        next_status = request.form.get("status", "hidden").strip()
        if update_addon_status(addon_id, next_status):
            _clear_site_cache()
            flash(f"Статус доп. услуги изменён: {ADDON_STATUS_LABELS.get(next_status, 'Скрыта')}.", "success")
        else:
            flash("Доп. услуга не найдена.", "error")
        return redirect(url_for("admin_dashboard", tab="addons"))

    @app.post("/admin/addons/<int:addon_id>/delete")
    @admin_required
    def admin_addon_delete(addon_id: int, admin):
        if delete_addon(addon_id):
            _clear_site_cache()
            flash("Доп. услуга удалена.", "success")
        else:
            flash("Доп. услуга не найдена.", "error")
        return redirect(url_for("admin_dashboard", tab="addons"))

    @app.route("/admin/promotions/new", methods=["GET", "POST"])
    @admin_required
    def admin_promotion_create(admin):
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            if not title:
                flash("У акции должно быть название.", "error")
            else:
                promotion_id = create_promotion(
                    {
                        "title": title,
                        "short_text": request.form.get("short_text", "").strip(),
                        "badge_text": request.form.get("badge_text", "").strip(),
                        "tooltip_text": request.form.get("tooltip_text", "").strip(),
                        "status": request.form.get("status", "active").strip(),
                        "sort_order": request.form.get("sort_order", "0").strip(),
                    }
                )
                _clear_site_cache()
                flash("Акция создана.", "success")
                return redirect(url_for("admin_promotion_edit", promotion_id=promotion_id))
        return render_template(
            "admin/promotion_form.html",
            title="Новая акция",
            admin=admin,
            active_tab="promotions",
            promotion={
                "title": "",
                "short_text": "",
                "badge_text": "",
                "tooltip_text": "",
                "status": "active",
                "sort_order": 0,
            },
            is_new=True,
        )

    @app.route("/admin/promotions/<int:promotion_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_promotion_edit(promotion_id: int, admin):
        promotion = get_promotion_by_id(promotion_id)
        if not promotion:
            flash("Акция не найдена.", "error")
            return redirect(url_for("admin_dashboard", tab="promotions"))
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            if not title:
                flash("У акции должно быть название.", "error")
            else:
                update_promotion(
                    promotion_id,
                    {
                        "title": title,
                        "short_text": request.form.get("short_text", "").strip(),
                        "badge_text": request.form.get("badge_text", "").strip(),
                        "tooltip_text": request.form.get("tooltip_text", "").strip(),
                        "status": request.form.get("status", "active").strip(),
                        "sort_order": request.form.get("sort_order", "0").strip(),
                    },
                )
                _clear_site_cache()
                flash("Акция сохранена.", "success")
                return redirect(url_for("admin_promotion_edit", promotion_id=promotion_id))
        return render_template(
            "admin/promotion_form.html",
            title=f"Акция: {promotion['title']}",
            admin=admin,
            active_tab="promotions",
            promotion=promotion,
            is_new=False,
        )

    @app.post("/admin/promotions/<int:promotion_id>/delete")
    @admin_required
    def admin_promotion_delete(promotion_id: int, admin):
        delete_promotion(promotion_id)
        _clear_site_cache()
        flash("Акция удалена.", "success")
        return redirect(url_for("admin_dashboard", tab="promotions"))

    @app.post("/admin/catalog/categories/create")
    @admin_required
    def admin_category_create(admin):
        name = request.form.get("name", "").strip()
        if not name:
            flash("У категории должно быть название.", "error")
            return redirect(url_for("admin_dashboard", tab="catalog"))
        create_category(
            name=name,
            slug=request.form.get("slug", "").strip(),
            description=request.form.get("description", "").strip(),
            is_visible=_normalize_bool(request.form.get("is_visible")),
            linked_tag_id=_normalize_optional_int(request.form.get("linked_tag_id")),
            linked_tag_name=request.form.get("linked_tag_name", "").strip(),
            linked_tag_slug=request.form.get("linked_tag_slug", "").strip(),
        )
        _clear_site_cache()
        flash("Категория создана.", "success")
        return redirect(url_for("admin_dashboard", tab="catalog"))

    @app.post("/admin/catalog/categories/<int:category_id>/update")
    @admin_required
    def admin_category_update(category_id: int, admin):
        name = request.form.get("name", "").strip()
        if not name:
            flash("У категории должно быть название.", "error")
            return redirect(url_for("admin_dashboard", tab="catalog"))
        update_category(
            category_id=category_id,
            name=name,
            slug=request.form.get("slug", "").strip(),
            description=request.form.get("description", "").strip(),
            is_visible=_normalize_bool(request.form.get("is_visible")),
            linked_tag_id=_normalize_optional_int(request.form.get("linked_tag_id")),
            linked_tag_name=request.form.get("linked_tag_name", "").strip(),
            linked_tag_slug=request.form.get("linked_tag_slug", "").strip(),
        )
        _clear_site_cache()
        flash("Категория обновлена.", "success")
        return redirect(url_for("admin_dashboard", tab="catalog"))

    @app.post("/admin/catalog/categories/<int:category_id>/delete")
    @admin_required
    def admin_category_delete(category_id: int, admin):
        if delete_category(category_id):
            flash("Категория удалена.", "success")
        else:
            flash("Системную категорию удалить нельзя.", "warning")
        _clear_site_cache()
        return redirect(url_for("admin_dashboard", tab="catalog"))

    @app.post("/admin/catalog/tags/create")
    @admin_required
    def admin_tag_create(admin):
        name = request.form.get("name", "").strip()
        if not name:
            flash("У тега должно быть название.", "error")
            return redirect(url_for("admin_dashboard", tab="catalog"))
        create_tag(
            name=name,
            slug=request.form.get("slug", "").strip(),
            description=request.form.get("description", "").strip(),
            is_visible=_normalize_bool(request.form.get("is_visible")),
        )
        _clear_site_cache()
        flash("Тег создан.", "success")
        return redirect(url_for("admin_dashboard", tab="catalog"))

    @app.post("/admin/catalog/tags/<int:tag_id>/update")
    @admin_required
    def admin_tag_update(tag_id: int, admin):
        name = request.form.get("name", "").strip()
        if not name:
            flash("У тега должно быть название.", "error")
            return redirect(url_for("admin_dashboard", tab="catalog"))
        update_tag(
            tag_id=tag_id,
            name=name,
            slug=request.form.get("slug", "").strip(),
            description=request.form.get("description", "").strip(),
            is_visible=_normalize_bool(request.form.get("is_visible")),
        )
        _clear_site_cache()
        flash("Тег обновлён.", "success")
        return redirect(url_for("admin_dashboard", tab="catalog"))

    @app.post("/admin/catalog/tags/<int:tag_id>/delete")
    @admin_required
    def admin_tag_delete(tag_id: int, admin):
        if delete_tag(tag_id):
            _clear_site_cache()
            flash("Тег удалён.", "success")
        else:
            flash("Системный тег удалить нельзя.", "warning")
        return redirect(url_for("admin_dashboard", tab="catalog"))

    @app.route("/admin/catalog/characters/new", methods=["GET", "POST"])
    @admin_required
    def admin_character_create(admin):
        entity_type = ENTITY_TYPE_CHARACTER
        entity_labels = _get_entity_labels(entity_type)
        if request.method == "POST":
            payload = _collect_character_form_data(entity_type=entity_type)
            if not payload["name"]:
                flash(f"{entity_labels['singular_title']}: укажите название.", "error")
            else:
                character_id = create_character(payload)
                upload_count = upload_character_media(character_id, request.files.getlist("media_files"))
                set_program_addons(character_id, _collect_show_addon_selections())
                _clear_site_cache()
                flash(
                    entity_labels["create_flash"] + (f" Загружено файлов: {upload_count}." if upload_count else ""),
                    "success",
                )
                return redirect(url_for("admin_character_edit", character_id=character_id))

        return render_template(
            "admin/character_form.html",
            title=entity_labels["new_title"],
            admin=admin,
            active_tab=entity_labels["tab"],
            character=_character_form_defaults(entity_type=entity_type),
            categories=list_categories(include_hidden=True),
            tags=list_tags(include_hidden=True),
            is_new=True,
            entity_type=entity_type,
            entity_labels=entity_labels,
            show_taxonomy=True,
        )

    @app.route("/admin/catalog/characters/<int:character_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_character_edit(character_id: int, admin):
        character = get_character_by_id(character_id)
        entity_type = ENTITY_TYPE_CHARACTER
        entity_labels = _get_entity_labels(entity_type)
        if not character or character.get("entity_type") != entity_type:
            flash(entity_labels["not_found_flash"], "error")
            return redirect(url_for("admin_dashboard", tab="catalog"))

        if request.method == "POST":
            payload = _collect_character_form_data(entity_type=entity_type)
            if not payload["name"]:
                flash(f"{entity_labels['singular_title']}: укажите название.", "error")
            else:
                update_character(character_id, payload)
                upload_count = upload_character_media(character_id, request.files.getlist("media_files"))
                refreshed = get_character_by_id(character_id) or character
                hero_media_id = request.form.get("hero_media_id", "").strip()
                update_media_metadata(
                    character_id,
                    _collect_media_updates(refreshed),
                    int(hero_media_id) if hero_media_id.isdigit() else None,
                )
                _clear_site_cache()
                flash(
                    entity_labels["save_flash"] + (f" Загружено файлов: {upload_count}." if upload_count else ""),
                    "success",
                )
                return redirect(url_for("admin_character_edit", character_id=character_id))

        return render_template(
            "admin/character_form.html",
            title=f"{entity_labels['edit_prefix']}: {character['name']}",
            admin=admin,
            active_tab=entity_labels["tab"],
            character=_character_form_defaults(character),
            categories=list_categories(include_hidden=True),
            tags=list_tags(include_hidden=True),
            is_new=False,
            entity_type=entity_type,
            entity_labels=entity_labels,
            show_taxonomy=True,
        )

    @app.post("/admin/catalog/characters/<int:character_id>/delete")
    @admin_required
    def admin_character_delete(character_id: int, admin):
        entity_labels = _get_entity_labels(ENTITY_TYPE_CHARACTER)
        if delete_character(character_id):
            _clear_site_cache()
            flash(entity_labels["delete_flash"], "success")
        else:
            flash(entity_labels["not_found_flash"], "error")
        return redirect(url_for("admin_dashboard", tab="catalog"))

    @app.post("/admin/catalog/characters/<int:character_id>/media/<int:media_id>/delete")
    @admin_required
    def admin_character_media_delete(character_id: int, media_id: int, admin):
        if delete_media(character_id, media_id):
            _clear_site_cache()
            flash("Медиа удалено.", "success")
        else:
            flash("Медиа не найдено.", "error")
        return redirect(url_for("admin_character_edit", character_id=character_id))

    @app.route("/admin/show-programs/new", methods=["GET", "POST"])
    @admin_required
    def admin_show_program_create(admin):
        entity_type = ENTITY_TYPE_SHOW_PROGRAM
        entity_labels = _get_entity_labels(entity_type)
        if request.method == "POST":
            payload = _collect_show_program_form_data()
            if not payload["name"]:
                flash(f"{entity_labels['singular_title']}: укажите название.", "error")
            else:
                character_id = create_character(payload)
                upload_count = upload_character_media(character_id, request.files.getlist("media_files"))
                set_show_program_characters(character_id, _normalize_int_list(request.form.getlist("linked_character_ids")))
                set_program_addons(character_id, _collect_show_addon_selections())
                set_program_promotions(character_id, _normalize_int_list(request.form.getlist("linked_promotion_ids")))
                _clear_site_cache()
                flash(
                    entity_labels["create_flash"] + (f" Загружено файлов: {upload_count}." if upload_count else ""),
                    "success",
                )
                return redirect(url_for("admin_show_program_edit", character_id=character_id))

        return render_template(
            "admin/show_program_form.html",
            title=entity_labels["new_title"],
            admin=admin,
            active_tab=entity_labels["tab"],
            character=_character_form_defaults(entity_type=entity_type),
            is_new=True,
            entity_type=entity_type,
            entity_labels=entity_labels,
            show_status_labels=SHOW_PROGRAM_STATUS_LABELS,
            available_characters=_decorate_characters_for_show_links(
                attach_media_counts(list_characters(status="active", entity_type=ENTITY_TYPE_CHARACTER))
            ),
            linked_character_ids=set(),
            available_addons=_decorate_addons_for_admin(list_active_addons()),
            addon_settings={},
            available_promotions=list_promotions(include_hidden=False),
            linked_promotion_ids=set(),
        )

    @app.route("/admin/show-programs/<int:character_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_show_program_edit(character_id: int, admin):
        character = get_character_by_id(character_id)
        entity_type = ENTITY_TYPE_SHOW_PROGRAM
        entity_labels = _get_entity_labels(entity_type)
        if not character or character.get("entity_type") != entity_type:
            flash(entity_labels["not_found_flash"], "error")
            return redirect(url_for("admin_dashboard", tab="show_programs"))

        if request.method == "POST":
            payload = _collect_show_program_form_data()
            if not payload["name"]:
                flash(f"{entity_labels['singular_title']}: укажите название.", "error")
            else:
                update_character(character_id, payload)
                upload_count = upload_character_media(character_id, request.files.getlist("media_files"))
                set_show_program_characters(character_id, _normalize_int_list(request.form.getlist("linked_character_ids")))
                set_program_addons(character_id, _collect_show_addon_selections())
                set_program_promotions(character_id, _normalize_int_list(request.form.getlist("linked_promotion_ids")))
                refreshed = get_character_by_id(character_id) or character
                hero_media_id = request.form.get("hero_media_id", "").strip()
                update_media_metadata(
                    character_id,
                    _collect_media_updates(refreshed),
                    int(hero_media_id) if hero_media_id.isdigit() else None,
                )
                _clear_site_cache()
                flash(
                    entity_labels["save_flash"] + (f" Загружено файлов: {upload_count}." if upload_count else ""),
                    "success",
                )
                return redirect(url_for("admin_show_program_edit", character_id=character_id))

        return render_template(
            "admin/show_program_form.html",
            title=f"{entity_labels['edit_prefix']}: {character['name']}",
            admin=admin,
            active_tab=entity_labels["tab"],
            character=_character_form_defaults(character),
            is_new=False,
            entity_type=entity_type,
            entity_labels=entity_labels,
            show_status_labels=SHOW_PROGRAM_STATUS_LABELS,
            available_characters=_decorate_characters_for_show_links(
                attach_media_counts(list_characters(status="active", entity_type=ENTITY_TYPE_CHARACTER))
            ),
            linked_character_ids=set(get_show_program_character_ids(character_id)),
            available_addons=_decorate_addons_for_admin(list_active_addons()),
            addon_settings=get_program_addon_settings(character_id),
            available_promotions=list_promotions(include_hidden=False),
            linked_promotion_ids=set(get_program_promotion_ids(character_id)),
        )

    @app.post("/admin/show-programs/<int:character_id>/status")
    @admin_required
    def admin_show_program_status(character_id: int, admin):
        next_status = _normalize_show_status(request.form.get("status", "draft"))
        entity_labels = _get_entity_labels(ENTITY_TYPE_SHOW_PROGRAM)
        if update_character_status(character_id, ENTITY_TYPE_SHOW_PROGRAM, next_status):
            _clear_site_cache()
            flash(f"Статус шоу-программы изменён: {SHOW_PROGRAM_STATUS_LABELS[next_status]}.", "success")
        else:
            flash(entity_labels["not_found_flash"], "error")
        return redirect(url_for("admin_dashboard", tab="show_programs"))

    @app.post("/admin/show-programs/<int:character_id>/delete")
    @admin_required
    def admin_show_program_delete(character_id: int, admin):
        entity_labels = _get_entity_labels(ENTITY_TYPE_SHOW_PROGRAM)
        if delete_character(character_id):
            _clear_site_cache()
            flash(entity_labels["delete_flash"], "success")
        else:
            flash(entity_labels["not_found_flash"], "error")
        return redirect(url_for("admin_dashboard", tab="show_programs"))

    @app.post("/admin/show-programs/<int:character_id>/media/<int:media_id>/delete")
    @admin_required
    def admin_show_program_media_delete(character_id: int, media_id: int, admin):
        if delete_media(character_id, media_id):
            _clear_site_cache()
            flash("Медиа удалено.", "success")
        else:
            flash("Медиа не найдено.", "error")
        return redirect(url_for("admin_show_program_edit", character_id=character_id))
