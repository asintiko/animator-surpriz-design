from __future__ import annotations

import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from functools import wraps
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from urllib.parse import urlencode

import requests
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from .customer_store import (
    CUSTOMER_SESSION_KEY,
    ORDER_STATUS_LABELS,
    PAYMENT_METHOD_HINTS,
    PAYMENT_METHOD_LABELS,
    SUPPORTED_PAYMENT_METHODS,
    booking_local_now,
    build_available_dates,
    ensure_guest_customer,
    build_character_end_time_availability,
    build_resource_availability_calendar,
    build_character_time_slot_availability,
    build_time_slots,
    check_character_availability,
    complete_customer_phone_auth,
    create_party_order,
    format_phone,
    get_customer_block_status,
    get_customer_by_id,
    get_order_by_public_id,
    get_program_duration_minutes,
    is_demo_availability_enabled,
    list_character_groups_for_builder,
    list_customer_orders,
    list_show_programs_for_public,
    list_show_programs_grouped_for_public,
    normalize_phone_to_e164,
    validate_customer_auth_target,
)
from .catalog_store import get_show_program_character_slug_map
from .catalog_bootstrap import resolve_landing_root
from .config import STATIC_ROOT
from .auth_rate_limit import consume_telegram_otp_send
from .public_api_guard import consume_public_api_request
from .site_page_builder import build_site_page_bundle
from .loader import build_runtime_page_bundle
from .tashkent_geo import TASHKENT_BBOX, TASHKENT_CENTROID, bbox_for_template, mask_outer_for_template, polygon_for_template

AUTH_REFERENCE_ROUTE = "catalog"
TELEGRAM_GATEWAY_SEND_URL = "https://gatewayapi.telegram.org/sendVerificationMessage"
TELEGRAM_GATEWAY_CHECK_URL = "https://gatewayapi.telegram.org/checkVerificationStatus"
TELEGRAM_CODE_TTL_SECONDS = 300
TELEGRAM_CODE_LENGTH = 6
TELEGRAM_RESEND_COOLDOWN_SECONDS = 60
TELEGRAM_MAX_VERIFY_ATTEMPTS = 5
TELEGRAM_REQUEST_TIMEOUT = 12
TELEGRAM_CHALLENGE_SESSION_KEY = "telegram_gateway_challenges"
CUSTOMER_FULL_NAME_MIN_LENGTH = 2
CUSTOMER_FULL_NAME_MAX_LENGTH = 80
PARTY_BUILDER_AVAILABILITY_MAX_CHARACTERS = 12
PARTY_BUILDER_AVAILABILITY_MAX_SLUG_LENGTH = 120

YANDEX_SUGGEST_URL = "https://suggest-maps.yandex.ru/v1/suggest"
YANDEX_GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x/"
YANDEX_SUGGEST_TIMEOUT = 6
YANDEX_SUGGEST_MAX_RESULTS = 8
YANDEX_SUGGEST_MIN_QUERY_LEN = 3
YANDEX_SUGGEST_QUERY_MAX_LEN = 200
_PUBLIC_API_CACHE_MAX_ITEMS = 256
_PUBLIC_API_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_PUBLIC_API_CACHE_LOCK = Lock()
_BUILDER_MEDIA_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_GENERATED_MEDIA_RE = re.compile(
    r"^(?P<base>/media/generated/[^?#]+?)/(?P<width>\d+)\.(?:avif|webp)(?:[?#].*)?$"
)


def _builder_responsive_media_base(
    item: dict[str, Any],
    media_kind: str,
    *,
    landing_root: Path | None = None,
) -> str:
    relative_directory = {
        "character": Path("assets/img/characters"),
        "show": Path("assets/img/show-programs/cards"),
    }.get(media_kind)
    if relative_directory is None:
        return ""
    public_directory = {
        "character": "/surpriz/assets/img/characters",
        "show": "/surpriz/assets/img/show-programs/cards",
    }[media_kind]
    hero_path = str(item.get("hero_file_path") or "").strip()
    hero_match = re.fullmatch(
        rf"{re.escape(public_directory)}/(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)-(?:800|1200)\.webp(?:[?#].*)?",
        hero_path,
    )
    if hero_path and not hero_match and not hero_path.startswith("/wp-content/"):
        return ""
    slug = (
        hero_match.group("slug")
        if hero_match
        else str(item.get("slug") or "").strip().lower()
    )
    if not _BUILDER_MEDIA_SLUG_RE.fullmatch(slug):
        return ""
    root = landing_root or resolve_landing_root(
        STATIC_ROOT.parent,
        os.environ.get("SURPRIZ_LANDING_ROOT", ""),
    )
    base = Path(root).resolve() / relative_directory / slug
    variants = (
        base.with_name(f"{slug}-480.avif"),
        base.with_name(f"{slug}-768.avif"),
        base.with_name(f"{slug}-1200.avif"),
        base.with_name(f"{slug}-480.webp"),
        base.with_name(f"{slug}-768.webp"),
        base.with_name(f"{slug}-1200.webp"),
    )
    if not all(path.is_file() for path in variants):
        return ""
    return f"{public_directory}/{slug}"


def _decorate_builder_media(
    shows_grouped: list[dict[str, Any]],
    character_groups: list[dict[str, Any]],
) -> None:
    def decorate(item: dict[str, Any], media_kind: str) -> None:
        responsive_base = _builder_responsive_media_base(item, media_kind)
        if responsive_base:
            widths = (480, 768, 1200)
        else:
            match = _GENERATED_MEDIA_RE.fullmatch(str(item.get("hero_file_path") or "").strip())
            if not match:
                return
            maximum_width = int(match.group("width"))
            widths = tuple(
                sorted({width for width in (480, 768, 1280, maximum_width) if width <= maximum_width})
            )
            responsive_base = match.group("base")
        item["responsive_avif_srcset"] = ", ".join(
            f"{responsive_base}/{width}.avif {width}w"
            if responsive_base.startswith("/media/generated/")
            else f"{responsive_base}-{width}.avif {width}w"
            for width in widths
        )
        item["responsive_webp_srcset"] = ", ".join(
            f"{responsive_base}/{width}.webp {width}w"
            if responsive_base.startswith("/media/generated/")
            else f"{responsive_base}-{width}.webp {width}w"
            for width in widths
        )
        maximum_width = widths[-1]
        item["responsive_media_fallback"] = (
            f"{responsive_base}/{maximum_width}.webp"
            if responsive_base.startswith("/media/generated/")
            else f"{responsive_base}-{maximum_width}.webp"
        )

    for group in shows_grouped:
        primary = group.get("primary")
        if isinstance(primary, dict):
            decorate(primary, "show")
        for variant in group.get("variants") or []:
            if isinstance(variant, dict):
                decorate(variant, "show")
    for group in character_groups:
        for character in group.get("items") or []:
            if isinstance(character, dict):
                decorate(character, "character")


def _safe_next_url(value: str | None, fallback: str = "/account/") -> str:
    candidate = value or ""
    if (
        "\\" in candidate
        or any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in candidate)
    ):
        return fallback
    candidate = candidate.strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    return candidate


PARTY_DRAFT_SESSION_KEY = "customer_party_draft"
#: Заказы, оформленные без входа. Даёт гостю доступ к своей странице «заказ принят»,
#: не выдавая сессию покупателя: сессия открыла бы кабинет с чужой историей любому,
#: кто ввёл чужой номер.
GUEST_ORDERS_SESSION_KEY = "customer_guest_orders"
GUEST_ORDERS_REMEMBERED = 10


def _remember_guest_order(public_id: str) -> None:
    known = [str(item) for item in session.get(GUEST_ORDERS_SESSION_KEY, []) if str(item).strip()]
    if public_id in known:
        known.remove(public_id)
    known.insert(0, public_id)
    session[GUEST_ORDERS_SESSION_KEY] = known[:GUEST_ORDERS_REMEMBERED]


def _owns_guest_order(public_id: str) -> bool:
    known = session.get(GUEST_ORDERS_SESSION_KEY, [])
    return isinstance(known, list) and public_id in [str(item) for item in known]


def _save_party_draft(form_data: dict[str, Any]) -> None:
    safe_draft: dict[str, Any] = {}
    for key, value in form_data.items():
        if isinstance(value, list):
            safe_draft[key] = [str(item) for item in value]
        elif isinstance(value, dict):
            safe_draft[key] = {
                str(item_key): str(item_value)
                for item_key, item_value in value.items()
            }
        elif value is None:
            safe_draft[key] = ""
        else:
            safe_draft[key] = str(value)
    session[PARTY_DRAFT_SESSION_KEY] = safe_draft


def _pop_party_draft() -> dict[str, Any] | None:
    draft = session.pop(PARTY_DRAFT_SESSION_KEY, None)
    if not isinstance(draft, dict):
        return None
    return draft


def _has_party_draft() -> bool:
    return isinstance(session.get(PARTY_DRAFT_SESSION_KEY), dict)


def _get_current_customer() -> dict[str, Any] | None:
    customer_id = session.get(CUSTOMER_SESSION_KEY)
    if not customer_id:
        return None
    return get_customer_by_id(int(customer_id))


def _public_customer_auth_payload(customer: dict[str, Any]) -> dict[str, str]:
    full_name = str(customer.get("full_name") or "").strip()
    phone_display = str(customer.get("phone_display") or "").strip()
    return {
        "display_name": full_name or phone_display or "Личный кабинет",
        "full_name": full_name,
    }


def _is_local_request() -> bool:
    host = request.host.split(":", 1)[0].lower()
    return host in {"127.0.0.1", "localhost"}


def _json_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    if isinstance(payload, dict):
        return payload
    return request.form.to_dict()


def _guard_public_api(
    bucket: str,
    *,
    per_ip_limit: int,
    global_limit: int,
    window_seconds: int = 60,
):
    try:
        decision = consume_public_api_request(
            bucket=bucket,
            client_ip=request.remote_addr,
            per_ip_limit=per_ip_limit,
            global_limit=global_limit,
            window_seconds=window_seconds,
        )
    except sqlite3.Error:
        return jsonify({
            "success": False,
            "error_code": "rate_limit_unavailable",
            "message": "Сервис временно недоступен.",
        }), 503
    if decision.allowed:
        return None
    response = jsonify({
        "success": False,
        "error_code": "rate_limited",
        "retry_after": decision.retry_after,
    })
    response.headers["Retry-After"] = str(decision.retry_after)
    return response, 429


def _public_api_cache_key(namespace: str, value: str) -> str:
    normalized = " ".join(str(value or "").strip().lower().split())
    return sha256(f"{namespace}\0{normalized}".encode("utf-8")).hexdigest()


def _public_api_cache_get(cache_key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    with _PUBLIC_API_CACHE_LOCK:
        cached = _PUBLIC_API_CACHE.get(cache_key)
        if not cached:
            return None
        expires_at, payload = cached
        if expires_at <= now:
            _PUBLIC_API_CACHE.pop(cache_key, None)
            return None
        return payload


def _public_api_cache_set(cache_key: str, payload: dict[str, Any], ttl_seconds: int) -> None:
    now = time.monotonic()
    with _PUBLIC_API_CACHE_LOCK:
        if len(_PUBLIC_API_CACHE) >= _PUBLIC_API_CACHE_MAX_ITEMS:
            expired_keys = [key for key, (expires_at, _) in _PUBLIC_API_CACHE.items() if expires_at <= now]
            for key in expired_keys:
                _PUBLIC_API_CACHE.pop(key, None)
            while len(_PUBLIC_API_CACHE) >= _PUBLIC_API_CACHE_MAX_ITEMS:
                _PUBLIC_API_CACHE.pop(next(iter(_PUBLIC_API_CACHE)))
        _PUBLIC_API_CACHE[cache_key] = (now + max(1, int(ttl_seconds)), payload)


def _telegram_gateway_token() -> str:
    # Priority: DB-stored setting (set via admin UI) → env var.
    try:
        from .admin_notifications import get_setting
        db_token = get_setting("telegram_gateway_token")
        if db_token:
            return db_token
    except Exception:
        pass
    return os.environ.get("TELEGRAM_GATEWAY_TOKEN", "").strip()


def _telegram_api_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_telegram_gateway_token()}",
        "Content-Type": "application/json",
    }


def _telegram_gateway_configured() -> bool:
    return bool(_telegram_gateway_token())


def _check_send_rate(phone_e164: str) -> tuple[bool, int]:
    return consume_telegram_otp_send(phone_e164, request.remote_addr)


def _get_challenges() -> dict[str, Any]:
    challenges = session.get(TELEGRAM_CHALLENGE_SESSION_KEY, {})
    return challenges if isinstance(challenges, dict) else {}


def _store_challenge(request_id: str, *, phone_e164: str, phone_display: str, purpose: str, full_name: str, next_url: str) -> None:
    now = time.time()
    challenges = {
        key: value
        for key, value in _get_challenges().items()
        if isinstance(value, dict) and float(value.get("expires_at", 0)) > now
    }
    challenges[request_id] = {
        "phone_e164": phone_e164,
        "phone_display": phone_display,
        "purpose": purpose,
        "full_name": full_name,
        "next_url": _safe_next_url(next_url, "/account/"),
        "expires_at": now + TELEGRAM_CODE_TTL_SECONDS,
        "sent_at": now,
        "attempts": 0,
    }
    session[TELEGRAM_CHALLENGE_SESSION_KEY] = challenges


def _remaining_resend_cooldown(challenge: dict[str, Any]) -> int:
    try:
        sent_at = float(challenge.get("sent_at", 0))
    except (TypeError, ValueError):
        sent_at = 0
    if sent_at <= 0:
        return TELEGRAM_RESEND_COOLDOWN_SECONDS
    return max(0, int(TELEGRAM_RESEND_COOLDOWN_SECONDS - (time.time() - sent_at)))


def _load_challenge(request_id: str, phone_e164: str) -> dict[str, Any] | None:
    challenges = _get_challenges()
    challenge = challenges.get(request_id)
    if not isinstance(challenge, dict):
        return None
    if challenge.get("phone_e164") != phone_e164:
        return None
    if float(challenge.get("expires_at", 0)) < time.time():
        challenges.pop(request_id, None)
        session[TELEGRAM_CHALLENGE_SESSION_KEY] = challenges
        return None
    return challenge


def _update_challenge(request_id: str, challenge: dict[str, Any] | None) -> None:
    challenges = _get_challenges()
    if challenge is None:
        challenges.pop(request_id, None)
    else:
        challenges[request_id] = challenge
    session[TELEGRAM_CHALLENGE_SESSION_KEY] = challenges


def _send_gateway_code(phone_e164: str) -> dict[str, Any]:
    # Dev-bypass: when env flag CUSTOMER_AUTH_DEV_BYPASS=1, OTP is faked and the magic code "000000" passes.
    # Set CUSTOMER_AUTH_DEV_BYPASS=0 (or remove the var) before deploying to production.
    if os.environ.get("CUSTOMER_AUTH_DEV_BYPASS", "0") == "1" and _is_local_request():
        return {"success": True, "request_id": f"dev:{phone_e164}", "dev": True}
    if not _telegram_gateway_configured():
        return {"success": False, "message": "Сервис отправки кодов не настроен. Свяжитесь с администратором."}

    try:
        response = requests.post(
            TELEGRAM_GATEWAY_SEND_URL,
            headers=_telegram_api_headers(),
            json={
                "phone_number": phone_e164,
                "code_length": TELEGRAM_CODE_LENGTH,
                "ttl": TELEGRAM_CODE_TTL_SECONDS,
            },
            timeout=TELEGRAM_REQUEST_TIMEOUT,
        )
        payload = response.json()
    except (requests.RequestException, ValueError):
        return {"success": False, "message": "Не удалось отправить код в Telegram. Попробуйте позже."}

    if not response.ok or not payload.get("ok"):
        return {"success": False, "message": "Telegram не принял запрос на отправку кода. Попробуйте позже."}

    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    request_id = result.get("request_id") or payload.get("request_id")
    if not request_id:
        return {"success": False, "message": "Telegram не вернул идентификатор проверки. Попробуйте позже."}

    return {"success": True, "request_id": request_id}


def _check_gateway_code(request_id: str, code: str) -> dict[str, Any]:
    # Dev-bypass: dev request ids accept the magic code "000000".
    if (
        str(request_id).startswith("dev:")
        and os.environ.get("CUSTOMER_AUTH_DEV_BYPASS", "0") == "1"
        and _is_local_request()
    ):
        if str(code).strip() == "000000":
            return {"success": True, "verified": True, "status": "code_valid", "message": "Код подтверждён (dev mode)."}
        return {"success": True, "verified": False, "status": "code_invalid", "message": "Неверный код. В dev-режиме введите 000000."}
    if not _telegram_gateway_configured():
        return {"success": False, "verified": False, "message": "Сервис отправки кодов не настроен."}

    try:
        response = requests.post(
            TELEGRAM_GATEWAY_CHECK_URL,
            headers=_telegram_api_headers(),
            json={"request_id": request_id, "code": code},
            timeout=TELEGRAM_REQUEST_TIMEOUT,
        )
        payload = response.json()
    except (requests.RequestException, ValueError):
        return {"success": False, "verified": False, "message": "Не удалось проверить код. Попробуйте позже."}

    if not response.ok or not payload.get("ok"):
        return {"success": False, "verified": False, "message": "Неверный или просроченный код."}

    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    verification_status = result.get("verification_status") if isinstance(result.get("verification_status"), dict) else result
    status = verification_status.get("status") if isinstance(verification_status, dict) else ""
    return {
        "success": True,
        "verified": status == "code_valid",
        "status": status,
        "message": "Код подтверждён." if status == "code_valid" else "Неверный или просроченный код.",
    }


def _start_telegram_auth(phone: str, purpose: str, *, full_name: str = "", next_url: str = "/account/") -> dict[str, Any]:
    target = validate_customer_auth_target(phone, purpose)
    if not target["success"]:
        return target

    normalized_full_name = " ".join(full_name.split())
    if purpose.strip().lower() == "register" and not (
        CUSTOMER_FULL_NAME_MIN_LENGTH <= len(normalized_full_name) <= CUSTOMER_FULL_NAME_MAX_LENGTH
    ):
        return {
            "success": False,
            "error_code": "invalid_full_name",
            "message": "Укажите имя длиной от 2 до 80 символов.",
        }

    phone_e164 = target["phone_e164"]
    try:
        allowed, retry_after = _check_send_rate(phone_e164)
    except sqlite3.Error:
        return {
            "success": False,
            "error_code": "rate_limit_unavailable",
            "message": "Сервис авторизации временно недоступен. Попробуйте позже.",
        }
    if not allowed:
        return {
            "success": False,
            "error_code": "rate_limited",
            "message": f"Код уже отправлен. Повторить можно через {retry_after} сек.",
            "retry_after": retry_after,
        }

    sent = _send_gateway_code(phone_e164)
    if not sent["success"]:
        return sent

    _store_challenge(
        sent["request_id"],
        phone_e164=phone_e164,
        phone_display=target["phone_display"],
        purpose=purpose,
        full_name=normalized_full_name,
        next_url=next_url,
    )
    return {
        "success": True,
        "request_id": sent["request_id"],
        "phone_e164": phone_e164,
        "phone_display": target["phone_display"],
        "ttl": TELEGRAM_CODE_TTL_SECONDS,
        "cooldown": TELEGRAM_RESEND_COOLDOWN_SECONDS,
    }


def _verify_telegram_auth(phone: str, request_id: str, code: str) -> dict[str, Any]:
    phone_e164 = normalize_phone_to_e164(phone)
    normalized_code = "".join(ch for ch in code if ch.isdigit())
    request_id = request_id.strip()

    if not phone_e164:
        return {"success": False, "verified": False, "message": "Укажите корректный номер телефона."}
    if not request_id:
        return {"success": False, "verified": False, "message": "Сначала запросите код подтверждения."}
    if len(normalized_code) != TELEGRAM_CODE_LENGTH:
        return {"success": False, "verified": False, "message": "Введите 6-значный код из Telegram."}

    challenge = _load_challenge(request_id, phone_e164)
    if not challenge:
        return {"success": False, "verified": False, "message": "Код устарел. Запросите новый код."}
    if int(challenge.get("attempts", 0)) >= TELEGRAM_MAX_VERIFY_ATTEMPTS:
        _update_challenge(request_id, None)
        return {"success": False, "verified": False, "message": "Лимит попыток исчерпан. Запросите новый код."}

    gateway_result = _check_gateway_code(request_id, normalized_code)
    if not gateway_result.get("success"):
        return {
            "success": False,
            "verified": False,
            "message": gateway_result.get("message") or "Не удалось проверить код. Попробуйте позже.",
        }
    if not gateway_result.get("verified"):
        challenge["attempts"] = int(challenge.get("attempts", 0)) + 1
        _update_challenge(request_id, challenge)
        return {
            "success": False,
            "verified": False,
            "message": gateway_result.get("message") or "Неверный или просроченный код.",
        }

    completed = complete_customer_phone_auth(
        phone_e164,
        str(challenge.get("purpose") or "login"),
        full_name=str(challenge.get("full_name") or ""),
        channel="telegram",
    )
    if not completed["success"]:
        return {"success": False, "verified": False, "message": completed["message"]}

    _update_challenge(request_id, None)
    session[CUSTOMER_SESSION_KEY] = completed["customer"]["id"]
    session.permanent = True
    fallback_next = "/party-builder/?resume=review" if _has_party_draft() else "/account/"
    redirect_url = _safe_next_url(str(challenge.get("next_url") or fallback_next), fallback_next)
    if _has_party_draft():
        redirect_url = "/party-builder/?resume=review"
    return {
        "success": True,
        "verified": True,
        "message": "Номер подтверждён.",
        "customer": completed["customer"],
        "redirect_url": redirect_url,
    }


def _deny_to_auth():
    """Единый отказ для страниц, требующих входа.

    Без flash: /register/ уводит на главную с модалкой входа, а главная —
    статический файл, который флеши не выводит. Сообщение зависало в сессии и
    всплывало пачкой уже после входа, на странице, где оно бессмысленно.
    Модалка и так объясняет, что нужно сделать.
    """
    next_target = request.full_path if request.query_string else request.path
    return redirect(url_for("customer_register", next=_safe_next_url(next_target, "/party-builder/")))


def customer_required(view: Callable):
    @wraps(view)
    def wrapped(*args, **kwargs):
        customer = _get_current_customer()
        if not customer:
            return _deny_to_auth()
        return view(customer=customer, *args, **kwargs)

    return wrapped


def order_access_required(view: Callable):
    """Заказ показывается владельцу аккаунта либо гостю, оформившему его в этом
    браузере. Один public_id ключом быть не может: номера идут подряд (SRP-00001),
    и по ним перебирались бы чужие заказы с адресом и телефоном."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        public_id = str(kwargs.get("public_id") or "")
        customer = _get_current_customer()
        if customer:
            return view(customer=customer, *args, **kwargs)
        if public_id and _owns_guest_order(public_id):
            return view(customer=None, *args, **kwargs)
        return _deny_to_auth()

    return wrapped


def _build_site_page(
    *,
    route: str,
    title: str,
    description: str,
    template_name: str,
    extra_body_class: str = "",
    **context: Any,
):
    content_html = render_template(template_name, **context)
    return build_site_page_bundle(
        reference_route=AUTH_REFERENCE_ROUTE,
        route=route,
        title=title,
        description=description,
        content_html=content_html,
        extra_body_class=extra_body_class,
    )


def _render_customer_page(page):
    runtime_page = build_runtime_page_bundle(page, is_authenticated=bool(session.get(CUSTOMER_SESSION_KEY)))
    return render_template("base.html", page=runtime_page)


def _auth_page_context(
    mode: str,
    *,
    next_url: str,
    phone: str = "",
    full_name: str = "",
    request_id: str = "",
    phone_display: str = "",
    cooldown: int = TELEGRAM_RESEND_COOLDOWN_SECONDS,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "next_url": next_url,
        "phone": phone,
        "full_name": full_name,
        "request_id": request_id,
        "phone_display": phone_display or format_phone(phone),
        "cooldown": cooldown,
    }


def _add_duration_to_time(start_time: str, duration_minutes: int) -> str:
    try:
        start = datetime.strptime(start_time, "%H:%M")
    except ValueError:
        start = datetime.strptime("12:00", "%H:%M")
    finish = start + timedelta(minutes=max(0, duration_minutes))
    return finish.strftime("%H:%M")


def _builder_defaults(program_slug: str = "", character_slugs: list[str] | None = None) -> dict[str, Any]:
    time_from = "12:00"
    time_to = _add_duration_to_time(time_from, get_program_duration_minutes(program_slug))
    return {
        "program_slug": program_slug,
        "character_slugs": list(dict.fromkeys(character_slugs or [])),
        "ensemble_members": [],
        "celebration_date": "",
        "time_from": time_from,
        "time_to": time_to,
        "celebrant_name": "",
        "celebrant_age": "",
        "children_count": "",
        "address_text": "",
        "map_label": "",
        "map_lat": "",
        "map_lng": "",
        "yandex_map_url": "",
        "payment_method": "cash",
        "payment_provider": "",
        "notes": "",
        "addon_slugs": [],
        "free_addon_slug": "",
        "gift_choices": {},
    }


def _collect_gift_choices_from_form() -> dict[str, str]:
    choices: dict[str, str] = {}
    for key in request.form:
        if not key.startswith("gift_choice_"):
            continue
        group_key = key[len("gift_choice_") :].strip()
        value = request.form.get(key, "").strip()
        if group_key and value:
            choices[group_key] = value
    return choices


def _collect_builder_form() -> dict[str, Any]:
    return {
        "program_slug": request.form.get("program_slug", "").strip(),
        "character_slugs": request.form.getlist("character_slugs"),
        "ensemble_members": request.form.getlist("ensemble_members"),
        "celebration_date": request.form.get("celebration_date", "").strip(),
        "time_from": request.form.get("time_from", "").strip(),
        "time_to": request.form.get("time_to", "").strip(),
        "celebrant_name": request.form.get("celebrant_name", "").strip(),
        "celebrant_age": request.form.get("celebrant_age", "").strip(),
        "children_count": request.form.get("children_count", "").strip(),
        "contact_name": request.form.get("contact_name", "").strip(),
        "contact_phone": request.form.get("contact_phone", "").strip(),
        "address_text": request.form.get("address_text", "").strip(),
        "map_label": request.form.get("map_label", "").strip(),
        "map_lat": request.form.get("map_lat", "").strip(),
        "map_lng": request.form.get("map_lng", "").strip(),
        "yandex_map_url": request.form.get("yandex_map_url", "").strip(),
        "payment_method": request.form.get("payment_method", "").strip(),
        "payment_provider": request.form.get("payment_provider", "").strip(),
        "notes": request.form.get("notes", "").strip(),
        "addon_slugs": request.form.getlist("addon_slugs"),
        "free_addon_slug": request.form.get("free_addon_slug", "").strip(),
        "gift_choices": _collect_gift_choices_from_form(),
    }


BUILDER_DATE_LOOKAHEAD_DAYS = 120


def _parse_builder_date_arg(raw: str) -> str:
    """Validate ?date=YYYY-MM-DD deep link; return ISO date or "" on garbage."""
    value = (raw or "").strip()
    if not value:
        return ""
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return ""
    today = datetime.now().date()
    if parsed < today or parsed >= today + timedelta(days=BUILDER_DATE_LOOKAHEAD_DAYS):
        return ""
    return parsed.isoformat()


def _builder_query_defaults() -> dict[str, Any]:
    program_slug = request.args.get("program", "").strip()
    character_values = [value.strip() for value in request.args.getlist("character") if value.strip()]
    defaults = _builder_defaults(program_slug=program_slug, character_slugs=character_values)
    date_value = _parse_builder_date_arg(request.args.get("date", ""))
    if date_value:
        defaults["celebration_date"] = date_value
    return defaults


def _is_admin_availability_preview() -> bool:
    """Keep fake availability visible only in an authenticated admin session."""
    return bool(session.get("admin_user_id"))


def _filtered_busy_dates(
    form_data: dict[str, Any],
    *,
    include_demo: bool = False,
) -> dict[str, Any]:
    """Return busy dates filtered by user's selected program / characters.

    Privacy: only show bookings that conflict with what the user is building.
    If user has not picked a program or any character, return an empty calendar
    so competitors cannot harvest our booking volume from the public page.
    """
    return build_resource_availability_calendar(
        program_slug=str(form_data.get("program_slug") or "").strip(),
        character_slugs=[
            str(slug).strip()
            for slug in (form_data.get("character_slugs") or [])
            if str(slug).strip()
        ],
        include_demo=include_demo,
    )


def _clock_minutes(value: object) -> int | None:
    try:
        hours, minutes = (int(part) for part in str(value or "").split(":", 1))
    except (TypeError, ValueError):
        return None
    if not 0 <= hours < 24 or not 0 <= minutes < 60:
        return None
    return hours * 60 + minutes


def _demo_preview_conflicts(
    busy_dates: dict[str, Any],
    *,
    celebration_date: str,
    time_from: object,
    time_to: object,
) -> list[dict[str, Any]]:
    """Return display-only conflicts for the explicitly requested admin preview."""
    entry = (busy_dates.get("by_date") or {}).get(celebration_date) or {}
    if not entry.get("is_demo"):
        return []
    start_minutes = _clock_minutes(time_from)
    end_minutes = _clock_minutes(time_to)
    if start_minutes is None or end_minutes is None or end_minutes <= start_minutes:
        return []
    windows = entry.get("blocked_windows") or []
    matched = [
        window
        for window in windows
        if (window_start := _clock_minutes(window.get("from"))) is not None
        and (window_end := _clock_minutes(window.get("to"))) is not None
        and start_minutes < window_end
        and end_minutes > window_start
    ]
    if not matched:
        return []
    return [{
        "slug": "demo-preview",
        "name": "Демо-бронь",
        "capacity": 1,
        "used": 1,
        "duplicate_count": 0,
        "orders": [
            {
                "time_from": str(window.get("from") or ""),
                "time_to": str(window.get("to") or ""),
                "blocked_from": str(window.get("from") or ""),
                "blocked_to": str(window.get("to") or ""),
                "is_demo": True,
            }
            for window in matched
        ],
    }]


def _apply_demo_preview_to_time_slots(
    slots: list[dict[str, Any]],
    *,
    busy_dates: dict[str, Any],
    celebration_date: str,
    fixed_time_from: str = "",
) -> list[dict[str, Any]]:
    """Overlay fake blocked ranges for the admin preview without persisting them."""
    for slot in slots:
        time_from = fixed_time_from or str(slot.get("value") or "")
        time_to = str(slot.get("value") if fixed_time_from else slot.get("time_to") or "")
        conflicts = _demo_preview_conflicts(
            busy_dates,
            celebration_date=celebration_date,
            time_from=time_from,
            time_to=time_to,
        )
        if not conflicts:
            continue
        slot["available"] = False
        slot["reason"] = "demo"
        slot["conflicts"] = [*(slot.get("conflicts") or []), *conflicts]
    return slots


def _payment_options() -> list[dict[str, Any]]:
    return [
        {
            "value": "cash",
            "label": PAYMENT_METHOD_LABELS["cash"],
            "hint": PAYMENT_METHOD_HINTS["cash"],
        },
        {
            "value": "bank",
            "label": PAYMENT_METHOD_LABELS["bank"],
            "hint": PAYMENT_METHOD_HINTS["bank"],
        },
    ]


def register_customer_routes(app: Flask) -> None:
    def unified_auth_shell_redirect(mode: str, next_url: str):
        home_url = str(app.config.get("SURPRIZ_UNIFIED_HOME_URL") or "").strip()
        if not home_url:
            return None
        query = urlencode({"auth": mode, "next": next_url})
        separator = "&" if "?" in home_url else "?"
        return redirect(f"{home_url}{separator}{query}")

    @app.get("/api/auth/session")
    def api_auth_session():
        customer = _get_current_customer()
        payload: dict[str, Any] = {"authenticated": bool(customer)}
        if customer:
            payload["customer"] = _public_customer_auth_payload(customer)
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/auth/send-telegram-code")
    def api_send_telegram_code():
        payload = _json_payload()
        purpose = str(payload.get("purpose") or "register").strip().lower()
        result = _start_telegram_auth(
            str(payload.get("phone") or ""),
            purpose,
            full_name=str(payload.get("full_name") or ""),
            next_url=_safe_next_url(str(payload.get("next") or ""), "/account/"),
        )
        if result["success"]:
            return jsonify(result), 200
        if result.get("error_code") == "rate_limited":
            response = jsonify(result)
            response.headers["Retry-After"] = str(max(1, int(result.get("retry_after") or 1)))
            return response, 429
        status_code = 503 if result.get("error_code") == "rate_limit_unavailable" else 400
        return jsonify(result), status_code

    @app.post("/api/auth/verify-telegram-code")
    def api_verify_telegram_code():
        payload = _json_payload()
        result = _verify_telegram_auth(
            str(payload.get("phone") or ""),
            str(payload.get("request_id") or ""),
            str(payload.get("code") or ""),
        )
        status_code = 200 if result["success"] else 400
        safe_result = {
            "success": bool(result.get("success")),
            "verified": bool(result.get("verified")),
            "message": result.get("message", ""),
        }
        if result.get("redirect_url"):
            safe_result["redirect_url"] = result["redirect_url"]
        customer = result.get("customer")
        if isinstance(customer, dict):
            safe_result["customer"] = _public_customer_auth_payload(customer)
        return jsonify(safe_result), status_code

    @app.post("/api/party-builder/check-availability")
    def api_party_builder_check_availability():
        limited = _guard_public_api(
            "party-builder-availability",
            per_ip_limit=90,
            global_limit=1200,
        )
        if limited is not None:
            return limited
        payload = _json_payload()
        availability_preview = bool(payload.get("availability_preview")) and _is_admin_availability_preview()
        raw_slugs = payload.get("character_slugs") or []
        if not isinstance(raw_slugs, list):
            raw_slugs = [raw_slugs]
        if len(raw_slugs) > PARTY_BUILDER_AVAILABILITY_MAX_CHARACTERS:
            return jsonify({
                "success": False,
                "error_code": "invalid_character_selection",
                "message": "Выбрано слишком много персонажей.",
            }), 400
        character_slugs: list[str] = []
        for value in raw_slugs:
            slug = str(value or "").strip()
            if not slug:
                continue
            if len(slug) > PARTY_BUILDER_AVAILABILITY_MAX_SLUG_LENGTH:
                return jsonify({
                    "success": False,
                    "error_code": "invalid_character_selection",
                    "message": "Некорректный идентификатор персонажа.",
                }), 400
            if slug not in character_slugs:
                character_slugs.append(slug)
        program_slug = str(payload.get("program_slug") or "")
        try:
            duration_minutes = int(payload.get("duration_minutes") or get_program_duration_minutes(program_slug))
        except (TypeError, ValueError):
            duration_minutes = get_program_duration_minutes(program_slug)
        result = check_character_availability(
            character_slugs=character_slugs,
            celebration_date=str(payload.get("celebration_date") or ""),
            time_from=str(payload.get("time_from") or ""),
            time_to=str(payload.get("time_to") or ""),
            program_slug=program_slug,
        )
        time_slots = build_time_slots()
        slots_result = build_character_time_slot_availability(
            character_slugs=character_slugs,
            celebration_date=str(payload.get("celebration_date") or ""),
            duration_minutes=duration_minutes,
            time_slots=time_slots,
            program_slug=program_slug,
        )
        if slots_result.get("success"):
            result["time_slots"] = slots_result.get("time_slots", [])
        end_slots_result = build_character_end_time_availability(
            character_slugs=character_slugs,
            celebration_date=str(payload.get("celebration_date") or ""),
            time_from=str(payload.get("time_from") or ""),
            time_slots=time_slots,
            extra_time_to=str(payload.get("time_to") or ""),
            program_slug=program_slug,
        )
        if end_slots_result.get("success"):
            result["time_to_slots"] = end_slots_result.get("time_to_slots", [])
        busy_dates = build_resource_availability_calendar(
            character_slugs=character_slugs,
            program_slug=program_slug,
            include_demo=availability_preview,
        )
        result["busy_dates"] = busy_dates
        if availability_preview:
            selected_date = str(payload.get("celebration_date") or "")
            result["time_slots"] = _apply_demo_preview_to_time_slots(
                list(result.get("time_slots") or []),
                busy_dates=busy_dates,
                celebration_date=selected_date,
            )
            result["time_to_slots"] = _apply_demo_preview_to_time_slots(
                list(result.get("time_to_slots") or []),
                busy_dates=busy_dates,
                celebration_date=selected_date,
                fixed_time_from=str(payload.get("time_from") or ""),
            )
            demo_conflicts = _demo_preview_conflicts(
                busy_dates,
                celebration_date=selected_date,
                time_from=payload.get("time_from"),
                time_to=payload.get("time_to"),
            )
            if demo_conflicts:
                result["available"] = False
                result["reason"] = "demo"
                result["message"] = "В демо-предпросмотре этот промежуток занят. Реальный заказ не создавался."
                result["conflicts"] = [*(result.get("conflicts") or []), *demo_conflicts]
        status_code = 200 if result.get("success") else 400
        return jsonify(result), status_code

    @app.post("/api/party-builder/suggest-address")
    def api_party_builder_suggest_address():
        payload = _json_payload()
        text = str(payload.get("text") or "").strip()[:YANDEX_SUGGEST_QUERY_MAX_LEN]
        if len(text) < YANDEX_SUGGEST_MIN_QUERY_LEN:
            return jsonify({"configured": True, "results": []}), 200

        key = os.environ.get("YANDEX_SUGGEST_API_KEY", "").strip()
        if not key:
            return jsonify({"configured": False, "results": []}), 200

        cache_key = _public_api_cache_key("suggest-address", text)
        cached_payload = _public_api_cache_get(cache_key)
        if cached_payload is not None:
            return jsonify(cached_payload), 200
        limited = _guard_public_api(
            "party-builder-suggest-address",
            per_ip_limit=30,
            global_limit=300,
        )
        if limited is not None:
            return limited

        ll = f"{TASHKENT_CENTROID[1]:.6f},{TASHKENT_CENTROID[0]:.6f}"
        ll_lon, ll_lat = TASHKENT_BBOX[0][1], TASHKENT_BBOX[0][0]
        ur_lon, ur_lat = TASHKENT_BBOX[1][1], TASHKENT_BBOX[1][0]
        bbox = f"{ll_lon:.6f},{ll_lat:.6f}~{ur_lon:.6f},{ur_lat:.6f}"

        params = {
            "apikey": key,
            "text": text,
            "lang": "ru_RU",
            "results": YANDEX_SUGGEST_MAX_RESULTS,
            "ll": ll,
            "bbox": bbox,
            "types": "geo,biz",
            "print_address": 1,
            "attrs": "uri",
        }

        try:
            response = requests.get(YANDEX_SUGGEST_URL, params=params, timeout=YANDEX_SUGGEST_TIMEOUT)
        except requests.RequestException:
            return jsonify({"configured": True, "results": [], "error": "network"}), 200

        if response.status_code == 403:
            return jsonify({"configured": False, "results": [], "error": "forbidden"}), 200
        if not response.ok:
            return jsonify({"configured": True, "results": [], "error": f"http_{response.status_code}"}), 200

        try:
            data = response.json()
        except ValueError:
            return jsonify({"configured": True, "results": [], "error": "bad_json"}), 200

        raw_results = data.get("results") or []
        normalized: list[dict[str, Any]] = []
        for entry in raw_results:
            if not isinstance(entry, dict):
                continue
            title = ""
            subtitle = ""
            title_block = entry.get("title")
            if isinstance(title_block, dict):
                title = str(title_block.get("text") or "").strip()
            subtitle_block = entry.get("subtitle")
            if isinstance(subtitle_block, dict):
                subtitle = str(subtitle_block.get("text") or "").strip()
            tags = entry.get("tags") or []
            kind = ""
            if isinstance(tags, list) and tags:
                kind = str(tags[0] or "").strip()
            uri = str(entry.get("uri") or "").strip()
            address = entry.get("address") or {}
            formatted = ""
            if isinstance(address, dict):
                formatted = str(address.get("formatted_address") or "").strip()
            if not title:
                continue
            normalized.append({
                "title": title,
                "subtitle": subtitle or formatted,
                "uri": uri,
                "kind": kind,
                "value": (formatted or (f"{title}, {subtitle}" if subtitle else title)).strip(", "),
            })

        result_payload = {"configured": True, "results": normalized}
        _public_api_cache_set(cache_key, result_payload, 120)
        return jsonify(result_payload), 200

    @app.post("/api/party-builder/resolve-address")
    def api_party_builder_resolve_address():
        payload = _json_payload()
        uri = str(payload.get("uri") or "").strip()
        text = str(payload.get("text") or "").strip()[:YANDEX_SUGGEST_QUERY_MAX_LEN]
        if not uri and not text:
            return jsonify({"success": False, "message": "empty_query"}), 400

        key = os.environ.get("YANDEX_MAPS_API_KEY", "").strip()
        if not key:
            return jsonify({"success": False, "message": "not_configured"}), 200

        cache_key = _public_api_cache_key("resolve-address", uri or text)
        cached_payload = _public_api_cache_get(cache_key)
        if cached_payload is not None:
            return jsonify(cached_payload), 200
        limited = _guard_public_api(
            "party-builder-resolve-address",
            per_ip_limit=12,
            global_limit=120,
        )
        if limited is not None:
            return limited

        params: dict[str, Any] = {
            "apikey": key,
            "format": "json",
            "results": 1,
            "lang": "ru_RU",
        }
        if uri:
            params["uri"] = uri
        else:
            params["geocode"] = text
            ll_lon, ll_lat = TASHKENT_BBOX[0][1], TASHKENT_BBOX[0][0]
            ur_lon, ur_lat = TASHKENT_BBOX[1][1], TASHKENT_BBOX[1][0]
            params["bbox"] = f"{ll_lon:.6f},{ll_lat:.6f}~{ur_lon:.6f},{ur_lat:.6f}"
            params["rspn"] = 0

        try:
            response = requests.get(YANDEX_GEOCODER_URL, params=params, timeout=YANDEX_SUGGEST_TIMEOUT)
            data = response.json()
        except (requests.RequestException, ValueError):
            return jsonify({"success": False, "message": "network"}), 200

        if not response.ok:
            return jsonify({"success": False, "message": f"http_{response.status_code}"}), 200

        try:
            collection = data["response"]["GeoObjectCollection"]
            feature_members = collection.get("featureMember") or []
            geo_object = feature_members[0]["GeoObject"]
            pos = str(geo_object["Point"]["pos"]).split()
            lon = float(pos[0])
            lat = float(pos[1])
        except (KeyError, IndexError, TypeError, ValueError):
            return jsonify({"success": False, "message": "no_result"}), 200

        label = (
            geo_object.get("metaDataProperty", {})
            .get("GeocoderMetaData", {})
            .get("text")
            or geo_object.get("name")
            or text
            or "Адрес"
        )

        result_payload = {
            "success": True,
            "lat": lat,
            "lng": lon,
            "label": label,
        }
        _public_api_cache_set(cache_key, result_payload, 600)
        return jsonify(result_payload), 200

    @app.route("/register/", methods=["GET", "POST"])
    def customer_register():
        current_customer = _get_current_customer()
        if current_customer:
            if _has_party_draft():
                return redirect("/party-builder/?resume=review")
            return redirect(url_for("customer_account"))

        next_url = _safe_next_url(request.values.get("next"), "/account/")
        if request.method == "GET":
            unified_redirect = unified_auth_shell_redirect("register", next_url)
            if unified_redirect is not None:
                return unified_redirect
        context = _auth_page_context("register", next_url=next_url)

        if request.method == "POST":
            context["phone"] = request.form.get("phone", "").strip()
            context["full_name"] = request.form.get("full_name", "").strip()
            result = _start_telegram_auth(
                context["phone"],
                "register",
                full_name=context["full_name"],
                next_url=next_url,
            )
            if result["success"]:
                flash(f"Код отправлен в Telegram на номер {result['phone_display']}.", "success")
                return redirect(
                    url_for(
                        "customer_telegram_code",
                        mode="register",
                        request_id=result["request_id"],
                        phone=result["phone_e164"],
                    )
                )
            flash(result["message"], "error")

        page = _build_site_page(
            route="/register/",
            title="Регистрация | Surpriz",
            description="Создайте аккаунт Surpriz по номеру телефона и собирайте праздники прямо на сайте.",
            template_name="site/account_auth_content.html",
            **context,
        )
        return _render_customer_page(page)

    @app.route("/login/", methods=["GET", "POST"])
    def customer_login():
        current_customer = _get_current_customer()
        if current_customer:
            if _has_party_draft():
                return redirect("/party-builder/?resume=review")
            return redirect(url_for("customer_account"))

        next_url = _safe_next_url(request.values.get("next"), "/account/")
        if request.method == "GET":
            unified_redirect = unified_auth_shell_redirect("login", next_url)
            if unified_redirect is not None:
                return unified_redirect
        context = _auth_page_context("login", next_url=next_url)

        if request.method == "POST":
            context["phone"] = request.form.get("phone", "").strip()
            result = _start_telegram_auth(
                context["phone"],
                "login",
                next_url=next_url,
            )
            if result["success"]:
                flash(f"Код отправлен в Telegram на номер {result['phone_display']}.", "success")
                return redirect(
                    url_for(
                        "customer_telegram_code",
                        mode="login",
                        request_id=result["request_id"],
                        phone=result["phone_e164"],
                    )
                )
            flash(result["message"], "error")

        page = _build_site_page(
            route="/login/",
            title="Вход | Surpriz",
            description="Войдите в аккаунт Surpriz по номеру телефона и управляйте заказами праздников.",
            template_name="site/account_auth_content.html",
            **context,
        )
        return _render_customer_page(page)

    @app.route("/auth/telegram-code/", methods=["GET", "POST"])
    def customer_telegram_code():
        current_customer = _get_current_customer()
        if current_customer:
            return redirect(url_for("customer_account"))

        mode = request.values.get("mode", "login").strip().lower()
        if mode not in {"register", "login"}:
            mode = "login"
        request_id = request.values.get("request_id", "").strip()
        phone = request.values.get("phone", "").strip()
        next_url = "/account/"

        phone_e164 = normalize_phone_to_e164(phone)
        challenge = _load_challenge(request_id, phone_e164) if phone_e164 and request_id else None
        if not challenge:
            flash("Код устарел или не найден. Запросите новый код.", "error")
            return redirect(url_for("customer_register" if mode == "register" else "customer_login"))

        next_url = _safe_next_url(str(challenge.get("next_url") or "/account/"), "/account/")
        context = _auth_page_context(
            mode,
            next_url=next_url,
            phone=phone_e164,
            full_name=str(challenge.get("full_name") or ""),
            request_id=request_id,
            phone_display=str(challenge.get("phone_display") or ""),
            cooldown=_remaining_resend_cooldown(challenge),
        )

        if request.method == "POST":
            result = _verify_telegram_auth(
                request.form.get("phone", "").strip(),
                request.form.get("request_id", "").strip(),
                request.form.get("code", "").strip(),
            )
            if result["success"]:
                flash("Номер подтверждён.", "success")
                return redirect(result.get("redirect_url") or next_url)
            flash(result["message"], "error")

        page = _build_site_page(
            route="/auth/telegram-code/",
            title="Код Telegram | Surpriz",
            description="Введите код подтверждения Telegram Gateway, чтобы войти или завершить регистрацию.",
            template_name="site/account_auth_content.html",
            verify_only=True,
            **context,
        )
        return _render_customer_page(page)

    @app.post("/logout/")
    @customer_required
    def customer_logout(customer):
        session.pop(CUSTOMER_SESSION_KEY, None)
        flash("Вы вышли из аккаунта.", "success")
        return redirect(url_for("customer_login"))

    @app.get("/account/")
    @customer_required
    def customer_account(customer):
        orders = list_customer_orders(customer["id"])
        active_statuses = {"new", "contacted", "confirmed"}
        local_now = booking_local_now()
        scheduled_active_orders: list[tuple[datetime, dict[str, Any]]] = []
        for order in orders:
            if order.get("status") not in active_statuses:
                continue
            date_value = str(order.get("celebration_date") or "").strip()
            start_value = str(order.get("time_from") or "00:00").strip()
            end_value = str(order.get("time_to") or start_value or "23:59").strip()
            if not date_value:
                continue
            try:
                starts_at = datetime.strptime(f"{date_value} {start_value}", "%Y-%m-%d %H:%M")
                ends_at = datetime.strptime(f"{date_value} {end_value}", "%Y-%m-%d %H:%M")
            except ValueError:
                continue
            if ends_at < starts_at:
                ends_at += timedelta(days=1)
            if ends_at >= local_now:
                scheduled_active_orders.append((starts_at, order))
        upcoming_entry = min(scheduled_active_orders, key=lambda item: item[0], default=None)
        upcoming_order = upcoming_entry[1] if upcoming_entry else None
        history_orders = [
            order
            for order in orders
            if upcoming_order is None or order.get("id") != upcoming_order.get("id")
        ]
        page = _build_site_page(
            route="/account/",
            title="Личный кабинет | Surpriz",
            description="Личный кабинет клиента Surpriz: заказы, статусы и быстрый переход к сборке праздника.",
            template_name="site/account_dashboard_content.html",
            extra_body_class="v2-profile-page",
            customer=customer,
            orders=orders,
            upcoming_order=upcoming_order,
            history_orders=history_orders,
            order_status_labels=ORDER_STATUS_LABELS,
        )
        return _render_customer_page(page)

    @app.get("/account/orders/<public_id>/accepted/")
    @order_access_required
    def customer_order_accepted(customer, public_id: str):
        order = get_order_by_public_id(
            public_id,
            customer_id=customer["id"] if customer else None,
        )
        if not order:
            flash("Заказ не найден.", "error")
            return redirect(url_for("customer_account") if customer else "/party-builder/")
        page = _build_site_page(
            route=f"/account/orders/{public_id}/accepted/",
            title="Заказ принят | Surpriz",
            description=f"Заявка {public_id} принята Surpriz.",
            template_name="site/order_accepted_content.html",
            extra_body_class="v2-order-accepted-page",
            customer=customer,
            order=order,
        )
        return _render_customer_page(page)

    @app.get("/account/orders/<public_id>/")
    @customer_required
    def customer_order_detail(customer, public_id: str):
        order = get_order_by_public_id(public_id, customer_id=customer["id"])
        if not order:
            flash("Заказ не найден.", "error")
            return redirect(url_for("customer_account"))
        page = _build_site_page(
            route=f"/account/orders/{public_id}/",
            title=f"Заказ {public_id} | Surpriz",
            description=f"Детали заказа {public_id} в личном кабинете Surpriz.",
            template_name="site/account_order_content.html",
            customer=customer,
            order=order,
        )
        return _render_customer_page(page)

    @app.route("/party-builder/", methods=["GET", "POST"])
    def customer_party_builder():
        customer = _get_current_customer()
        shows = list_show_programs_for_public()
        shows_grouped = list_show_programs_grouped_for_public()
        character_groups = list_character_groups_for_builder()
        _decorate_builder_media(shows_grouped, character_groups)
        draft_restored = False
        resume_step = 0
        availability_preview = (
            request.args.get("preview", "").strip() == "availability"
            and _is_admin_availability_preview()
        )
        if request.method == "GET":
            form_data = _builder_query_defaults()
            url_has_intent = bool(
                request.args.get("program", "").strip()
                or request.args.get("date", "").strip()
                or any(v.strip() for v in request.args.getlist("character"))
            )
            if customer and not url_has_intent:
                draft = _pop_party_draft()
                if draft:
                    merged = dict(form_data)
                    merged.update(draft)
                    if "character_slugs" not in draft:
                        merged["character_slugs"] = form_data.get("character_slugs", [])
                    elif not isinstance(merged.get("character_slugs"), list):
                        merged["character_slugs"] = []
                    if not isinstance(merged.get("addon_slugs"), list):
                        merged["addon_slugs"] = []
                    form_data = merged
                    draft_restored = True
                    if request.args.get("resume", "").strip() == "review":
                        resume_step = 6
                        flash(
                            "Вся сборка заказа сохранена: программа, персонажи, дата и адрес на месте. "
                            "Проверьте поля и подтвердите заказ.",
                            "success",
                        )
                    else:
                        flash("Мы вернули вашу заявку — проверьте поля и подтвердите заказ.", "success")
        else:
            form_data = _collect_builder_form()
        errors: dict[str, str] = {}

        if request.method == "POST":
            order_customer = customer
            if not order_customer:
                # Заказ принимается без регистрации: гость заводится как аккаунт с
                # неподтверждённым телефоном. Сессию покупателя здесь НЕ выдаём —
                # она открыла бы кабинет с чужой историей любому, кто ввёл чужой номер.
                guest = ensure_guest_customer(
                    form_data.get("contact_phone", ""),
                    form_data.get("contact_name", ""),
                )
                if not guest["success"]:
                    errors["contact_phone"] = guest["message"]
                    flash(guest["message"], "error")
                else:
                    order_customer = guest["customer"]
            if order_customer and not errors:
                result = create_party_order(order_customer["id"], form_data)
                if result["success"]:
                    order = result["order"]
                    if not customer:
                        _remember_guest_order(str(order["public_id"]))
                    return redirect(url_for("customer_order_accepted", public_id=order["public_id"]))
                errors = result["errors"]
                flash("Проверьте поля формы: есть незаполненные или некорректные данные.", "error")

        page = _build_site_page(
            route="/party-builder/",
            title="Собрать праздник | Surpriz",
            description="Соберите праздник на сайте Surpriz: выберите шоу-программу, персонажей, дату, время и сохраните заказ.",
            template_name="site/order_builder_content.html",
            extra_body_class="v2-builder-page",
            customer=customer,
            shows=shows,
            shows_grouped=shows_grouped,
            character_groups=character_groups,
            program_character_map=get_show_program_character_slug_map(),
            form_data=form_data,
            errors=errors,
            payment_options=_payment_options(),
            time_slots=build_time_slots(),
            available_dates=build_available_dates(),
            busy_dates=_filtered_busy_dates(form_data, include_demo=availability_preview),
            demo_availability_enabled=availability_preview or is_demo_availability_enabled(),
            availability_preview=availability_preview,
            yandex_maps_api_key=os.environ.get("YANDEX_MAPS_API_KEY", ""),
            yandex_suggest_enabled=bool(os.environ.get("YANDEX_SUGGEST_API_KEY", "").strip()),
            builder_block=get_customer_block_status(customer["id"]) if customer else None,
            draft_restored=draft_restored,
            resume_step=resume_step,
            tashkent_map_polygon=polygon_for_template(),
            tashkent_map_mask_outer=mask_outer_for_template(),
            tashkent_map_bbox=bbox_for_template(),
        )
        return _render_customer_page(page)
