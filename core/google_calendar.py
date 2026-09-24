"""Two-way sync between the booking site and a Google Calendar.

* Calendar -> site: events filled in by managers are read periodically. The
  date and time come from the event itself, program and characters are
  recognised in the title/description against the managed catalog. Every
  recognised event closes that time for those resources on the site.
* Site -> calendar: when an order is confirmed (Telegram bot or admin panel)
  it is written to the calendar in the same format as the Telegram order card;
  unconfirming or cancelling removes the event again.

The admin connects the calendar through OAuth in ``/admin/calendar``. The sync
itself runs in the Telegram worker process (``python -m core.admin_notifications``)
or standalone via ``python -m core.google_calendar``.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import re
import secrets
import socket
import threading
import time as time_module
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable, Iterator
from urllib.parse import quote, urlencode

import requests

from . import google_calendar_store as store
from .catalog_store import (
    ENTITY_TYPE_CHARACTER,
    ENTITY_TYPE_SHOW_PROGRAM,
    _SYNONYM_INDEX,
    list_characters,
    normalize_search_text,
)
from .customer_store import (
    BOOKING_LOCAL_TIMEZONE,
    format_datetime_ru,
    format_money,
    get_order_by_id,
)

LOGGER = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
)
OAUTH_CALLBACK_PATH = "/api/admin/google-calendar/callback"
OAUTH_STATE_TTL = timedelta(minutes=15)
HTTP_TIMEOUT_SECONDS = 15

LOCAL_TIMEZONE = BOOKING_LOCAL_TIMEZONE
LOCAL_TIMEZONE_NAME = "Asia/Tashkent"
LOCAL_UTC_OFFSET = "+05:00"

IMPORT_PAST_DAYS = 1
IMPORT_HORIZON_DAYS = 180
IMPORT_MAX_PAGES = 10
DEFAULT_EVENT_DURATION_MINUTES = 60
DEFAULT_POLL_MINUTES = 5
POLL_MINUTE_CHOICES = (1, 2, 5, 10, 15, 30, 60)
DEFAULT_TITLE_TEMPLATE = "{program} ({characters}) — {celebrant}, {age}"
DEFAULT_COLOR_ID = "6"
TITLE_MAX_LENGTH = 200
WORKER_TICK_SECONDS = 10
SYNC_LEASE_NAME = "sync-worker"
SYNC_LEASE_SECONDS = 90
SYNC_LEASE_RENEW_SECONDS = 20
MANUAL_SYNC_WAIT_SECONDS = 5.0
EVENT_ID_ALPHABET = "0123456789abcdefghijklmnopqrstuv"

EVENT_COLORS: tuple[dict[str, str], ...] = (
    {"id": "", "name": "Цвет календаря", "hex": ""},
    {"id": "1", "name": "Лаванда", "hex": "#7986cb"},
    {"id": "2", "name": "Шалфей", "hex": "#33b679"},
    {"id": "3", "name": "Виноград", "hex": "#8e24aa"},
    {"id": "4", "name": "Фламинго", "hex": "#e67c73"},
    {"id": "5", "name": "Банан", "hex": "#f6bf26"},
    {"id": "6", "name": "Мандарин", "hex": "#f4511e"},
    {"id": "7", "name": "Павлин", "hex": "#039be5"},
    {"id": "8", "name": "Графит", "hex": "#616161"},
    {"id": "9", "name": "Черника", "hex": "#3f51b5"},
    {"id": "10", "name": "Базилик", "hex": "#0b8043"},
    {"id": "11", "name": "Томат", "hex": "#d50000"},
)
TITLE_PLACEHOLDERS: tuple[dict[str, str], ...] = (
    {"key": "program", "label": "Шоу-программа"},
    {"key": "characters", "label": "Персонажи"},
    {"key": "celebrant", "label": "Имя именинника"},
    {"key": "age", "label": "Возраст («6 лет»)"},
    {"key": "children", "label": "Кол-во детей («12 детей»)"},
    {"key": "client", "label": "Имя клиента"},
    {"key": "phone", "label": "Телефон клиента"},
    {"key": "address", "label": "Адрес"},
    {"key": "time", "label": "Время «15:00–16:00»"},
    {"key": "total", "label": "Сумма"},
    {"key": "order", "label": "Номер заказа"},
)
MATCH_STATUS_LABELS = {
    "matched": "Закрывает время",
    "unmatched": "Не распознано",
    "free": "Помечено «свободен»",
    "own": "Заказ с сайта",
    "ignored": "Не учитывается",
}

SETTING_DEFAULTS = {
    "import_enabled": "1",
    "export_enabled": "1",
    "block_unmatched": "0",
    "poll_minutes": str(DEFAULT_POLL_MINUTES),
    "title_template": DEFAULT_TITLE_TEMPLATE,
    "color_id": DEFAULT_COLOR_ID,
}


class GoogleCalendarError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, reason: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason


class GoogleCalendarAuthError(GoogleCalendarError):
    """Google rejected the stored credentials; the admin must reconnect."""


class GoogleCalendarNotConfigured(GoogleCalendarError):
    """The integration is not connected or not fully configured yet."""


class GoogleCalendarSyncBusy(GoogleCalendarError):
    """Another process is running a sync cycle right now."""


def init_google_calendar() -> None:
    store.init_google_calendar_store()


# --- settings -----------------------------------------------------------------


def _settings() -> dict[str, str]:
    values = store.get_settings()
    for key, default in SETTING_DEFAULTS.items():
        if not values.get(key):
            values[key] = default
    return values


def _flag(settings: dict[str, str], key: str) -> bool:
    return str(settings.get(key, SETTING_DEFAULTS.get(key, "0"))).strip() == "1"


def _client_credentials() -> tuple[str, str, str]:
    values = store.get_settings(["client_id", "client_secret"])
    if values["client_id"] and values["client_secret"]:
        return values["client_id"], values["client_secret"], "admin"
    env_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    env_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
    if env_id and env_secret:
        return env_id, env_secret, "env"
    return "", "", ""


def resolve_redirect_uri(request_base: str = "") -> str:
    explicit = os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("ADMIN_PORTAL_BASE", "").strip().rstrip("/") or str(request_base or "").strip().rstrip("/")
    return f"{base}{OAUTH_CALLBACK_PATH}" if base else OAUTH_CALLBACK_PATH


def _is_connected(settings: dict[str, str]) -> bool:
    return bool(settings.get("refresh_token"))


def _import_ready(settings: dict[str, str]) -> bool:
    return (
        _is_connected(settings)
        and bool(settings.get("calendar_id"))
        and _flag(settings, "import_enabled")
        and not settings.get("auth_error")
    )


def _export_ready(settings: dict[str, str]) -> bool:
    return (
        _is_connected(settings)
        and bool(settings.get("calendar_id"))
        and _flag(settings, "export_enabled")
        and not settings.get("auth_error")
    )


def _local_now() -> datetime:
    return datetime.now(LOCAL_TIMEZONE).replace(tzinfo=None)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


# --- HTTP ------------------------------------------------------------------------


def _http_request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Single seam for all Google traffic (patched in tests)."""
    return requests.request(method, url, timeout=HTTP_TIMEOUT_SECONDS, **kwargs)


def _send(method: str, url: str, **kwargs: Any) -> requests.Response:
    try:
        return _http_request(method, url, **kwargs)
    except requests.RequestException as exc:
        raise GoogleCalendarError(f"Нет связи с Google ({type(exc).__name__}). Повторим автоматически.") from exc


def _json(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


_TOKEN_LOCK = threading.Lock()


def _access_token(*, force_refresh: bool = False) -> str:
    with _TOKEN_LOCK:
        values = store.get_settings(["access_token", "access_token_expires_at", "refresh_token"])
        if not values["refresh_token"]:
            raise GoogleCalendarNotConfigured("Google Календарь не подключён.")
        if not force_refresh and values["access_token"]:
            try:
                expires_at = datetime.fromisoformat(values["access_token_expires_at"])
            except ValueError:
                expires_at = None
            if expires_at and expires_at > _utcnow() + timedelta(seconds=60):
                return values["access_token"]

        client_id, client_secret, _ = _client_credentials()
        if not client_id:
            raise GoogleCalendarNotConfigured("Не заданы Client ID и Client Secret приложения Google.")
        response = _send(
            "POST",
            GOOGLE_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": values["refresh_token"],
                "grant_type": "refresh_token",
            },
        )
        payload = _json(response)
        token = str(payload.get("access_token") or "")
        if response.status_code != 200 or not token:
            error = str(payload.get("error") or "")
            if error in {"invalid_grant", "unauthorized_client", "invalid_client"}:
                message = "Google отозвал доступ к календарю. Подключите календарь заново."
                store.set_settings({"auth_error": message, "access_token": ""})
                raise GoogleCalendarAuthError(message, status=response.status_code, reason=error)
            raise GoogleCalendarError(
                f"Не удалось обновить доступ Google ({response.status_code}).",
                status=response.status_code,
                reason=error,
            )
        expires_in = int(payload.get("expires_in") or 3600)
        store.set_settings(
            {
                "access_token": token,
                "access_token_expires_at": (_utcnow() + timedelta(seconds=expires_in)).isoformat(),
                "auth_error": "",
            }
        )
        return token


def _api_error(status: int, payload: dict[str, Any]) -> GoogleCalendarError:
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    errors = error.get("errors") if isinstance(error.get("errors"), list) else []
    reason = str((errors[0] or {}).get("reason") or "") if errors else ""
    detail = str(error.get("message") or "").strip()
    if status == 404:
        message = "Календарь не найден или у аккаунта нет к нему доступа."
    elif status == 403 and reason in {"rateLimitExceeded", "userRateLimitExceeded", "quotaExceeded"}:
        message = "Google временно ограничил число запросов. Повторим автоматически."
    elif status == 403:
        message = "Нет прав на этот календарь. Выберите календарь, который можно изменять."
    else:
        message = f"Google Calendar ответил ошибкой {status}" + (f": {detail}" if detail else ".")
    return GoogleCalendarError(message, status=status, reason=reason)


def _api(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    allow: Iterable[int] = (),
) -> tuple[int, dict[str, Any]]:
    url = f"{CALENDAR_API_BASE}{path}"
    response: requests.Response | None = None
    for attempt in range(2):
        token = _access_token(force_refresh=attempt > 0)
        response = _send(
            method,
            url,
            params=params,
            json=json_body,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if response.status_code != 401:
            break
    assert response is not None
    payload = _json(response)
    if 200 <= response.status_code < 300 or response.status_code in set(allow):
        return response.status_code, payload
    if response.status_code == 401:
        message = "Google не принял доступ к календарю. Подключите календарь заново."
        store.set_settings({"auth_error": message})
        raise GoogleCalendarAuthError(message, status=401)
    raise _api_error(response.status_code, payload)


def _events_path(calendar_id: str, event_id: str = "") -> str:
    path = f"/calendars/{quote(calendar_id, safe='')}/events"
    return f"{path}/{quote(event_id, safe='')}" if event_id else path


# --- OAuth connection -----------------------------------------------------------


def save_client_credentials(client_id: str, client_secret: str) -> None:
    client_id = str(client_id or "").strip()
    client_secret = str(client_secret or "").strip()
    if not client_id or not client_secret:
        raise GoogleCalendarError("Укажите Client ID и Client Secret.")
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise GoogleCalendarError("Client ID должен заканчиваться на .apps.googleusercontent.com.")
    store.set_settings({"client_id": client_id, "client_secret": client_secret})


def build_authorization_url(redirect_uri: str) -> str:
    client_id, _, _ = _client_credentials()
    if not client_id:
        raise GoogleCalendarNotConfigured("Сначала сохраните Client ID и Client Secret приложения Google.")
    state = secrets.token_urlsafe(24)
    store.set_settings(
        {
            "oauth_state": state,
            "oauth_state_created_at": _utcnow().isoformat(),
            "oauth_redirect_uri": redirect_uri,
        }
    )
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def complete_authorization(code: str, state: str) -> dict[str, Any]:
    values = store.get_settings(["oauth_state", "oauth_state_created_at", "oauth_redirect_uri"])
    expected = values["oauth_state"]
    stale_message = "Ссылка подключения устарела. Нажмите «Подключить Google Календарь» ещё раз."
    if not code or not state or not expected or not secrets.compare_digest(str(state), expected):
        raise GoogleCalendarError(stale_message)
    try:
        created_at = datetime.fromisoformat(values["oauth_state_created_at"])
    except ValueError:
        raise GoogleCalendarError(stale_message) from None
    if _utcnow() - created_at > OAUTH_STATE_TTL:
        raise GoogleCalendarError(stale_message)
    store.set_settings({"oauth_state": ""})

    client_id, client_secret, _ = _client_credentials()
    if not client_id:
        raise GoogleCalendarNotConfigured("Не заданы Client ID и Client Secret приложения Google.")
    response = _send(
        "POST",
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": values["oauth_redirect_uri"],
            "grant_type": "authorization_code",
        },
    )
    payload = _json(response)
    if response.status_code != 200 or not payload.get("access_token"):
        detail = str(payload.get("error_description") or payload.get("error") or response.status_code)
        raise GoogleCalendarError(f"Google не подтвердил подключение: {detail}")
    granted = set(str(payload.get("scope") or "").split())
    if granted and not set(OAUTH_SCOPES).issubset(granted):
        raise GoogleCalendarError(
            "Google выдал не все разрешения. Подключите заново и отметьте доступ к календарю и событиям."
        )
    refresh_token = str(payload.get("refresh_token") or "")
    if not refresh_token:
        raise GoogleCalendarError(
            "Google не выдал постоянный доступ. Удалите доступ приложения на myaccount.google.com/permissions "
            "и подключите календарь снова."
        )
    expires_in = int(payload.get("expires_in") or 3600)
    store.set_settings(
        {
            "refresh_token": refresh_token,
            "access_token": str(payload["access_token"]),
            "access_token_expires_at": (_utcnow() + timedelta(seconds=expires_in)).isoformat(),
            "connected_at": _utcnow().isoformat(),
            "auth_error": "",
            "last_import_attempt_at": "",
        }
    )

    account_email = ""
    try:
        calendars = list_calendars()
    except GoogleCalendarError:
        calendars = []
    primary = next((item for item in calendars if item["primary"]), None)
    if primary:
        account_email = primary["id"]
    store.set_settings({"account_email": account_email})
    current_calendar = store.get_setting("calendar_id")
    if primary and not current_calendar:
        store.set_settings({"calendar_id": primary["id"], "calendar_summary": primary["summary"]})
    elif current_calendar:
        match = next((item for item in calendars if item["id"] == current_calendar), None)
        if match:
            store.set_settings({"calendar_summary": match["summary"]})
    return {"account_email": account_email}


def disconnect() -> None:
    refresh_token = store.get_setting("refresh_token")
    if refresh_token:
        try:
            _http_request("POST", GOOGLE_REVOKE_URL, params={"token": refresh_token})
        except requests.RequestException:
            pass
    store.set_settings(
        {
            "refresh_token": "",
            "access_token": "",
            "access_token_expires_at": "",
            "account_email": "",
            "connected_at": "",
            "auth_error": "",
            "last_import_at": "",
            "last_import_attempt_at": "",
            "last_import_error": "",
            "last_import_stats": "",
        }
    )
    store.clear_imported_events()


def list_calendars() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = ""
    for _ in range(5):
        params: dict[str, Any] = {"minAccessRole": "writer", "maxResults": 250}
        if page_token:
            params["pageToken"] = page_token
        _, payload = _api("GET", "/users/me/calendarList", params=params)
        for item in payload.get("items") or []:
            calendar_id = str(item.get("id") or "")
            if not calendar_id:
                continue
            items.append(
                {
                    "id": calendar_id,
                    "summary": str(item.get("summaryOverride") or item.get("summary") or calendar_id),
                    "primary": bool(item.get("primary")),
                    "access_role": str(item.get("accessRole") or ""),
                    "background_color": str(item.get("backgroundColor") or ""),
                    "time_zone": str(item.get("timeZone") or ""),
                }
            )
        page_token = str(payload.get("nextPageToken") or "")
        if not page_token:
            break
    items.sort(key=lambda item: (not item["primary"], item["summary"].casefold()))
    return items


def select_calendar(calendar_id: str) -> dict[str, Any]:
    calendar_id = str(calendar_id or "").strip()
    calendars = list_calendars()
    match = next((item for item in calendars if item["id"] == calendar_id), None)
    if not match:
        raise GoogleCalendarError("Этот календарь недоступен для записи. Выберите другой.")
    previous = store.get_setting("calendar_id")
    store.set_settings(
        {
            "calendar_id": match["id"],
            "calendar_summary": match["summary"],
            "last_import_attempt_at": "",
            "last_import_error": "",
        }
    )
    if previous != match["id"]:
        store.clear_imported_events()
    return match


def save_sync_settings(values: dict[str, Any]) -> dict[str, str]:
    current = _settings()
    updates: dict[str, str] = {}
    for key in ("import_enabled", "export_enabled", "block_unmatched"):
        if key in values:
            updates[key] = "1" if bool(values[key]) else "0"
    if "poll_minutes" in values:
        try:
            minutes = int(values["poll_minutes"])
        except (TypeError, ValueError):
            minutes = DEFAULT_POLL_MINUTES
        updates["poll_minutes"] = str(minutes if minutes in POLL_MINUTE_CHOICES else DEFAULT_POLL_MINUTES)
    if "title_template" in values:
        template = " ".join(str(values["title_template"] or "").split())[:TITLE_MAX_LENGTH]
        updates["title_template"] = template or DEFAULT_TITLE_TEMPLATE
    if "color_id" in values:
        color_id = str(values["color_id"] or "").strip()
        valid_colors = {item["id"] for item in EVENT_COLORS}
        # An empty value means "use the calendar colour"; store a marker so the
        # default (orange) does not come back on the next read.
        updates["color_id"] = (color_id or "none") if color_id in valid_colors else DEFAULT_COLOR_ID
    store.set_settings(updates)

    if updates.get("import_enabled") == "0":
        store.clear_imported_events()
    recognition_changed = updates.get("block_unmatched", current["block_unmatched"]) != current["block_unmatched"]
    if updates.get("import_enabled") == "1" or recognition_changed:
        request_import()
    if updates.get("export_enabled") == "1" and current["export_enabled"] != "1":
        wake_worker()
    return _settings()


# --- recognition ------------------------------------------------------------------

_STOP_TOKENS = frozenset(
    {"i", "s", "so", "v", "vo", "na", "k", "ko", "dlya", "ili", "a", "plus", "plyus", "and", "the", "with"}
)
_GENERIC_TOKENS = frozenset({"shou", "show", "programma", "programmy", "minut", "minuty", "min", "chas", "chasa"})
_QUALIFIER_RE = re.compile(r"\([^)]*\)|№\s*\d+")
_TITLE_SPLIT_RE = re.compile(r"\s[—–-]\s")
_WORD_ENDINGS = frozenset(
    {
        "", "a", "u", "e", "i", "y", "o", "om", "oy", "ey", "em", "ya", "yu", "ov", "ev", "ami", "yami",
        "ah", "yah", "am", "yam", "uyu", "yuyu", "ayu", "aya", "oe", "ogo", "omu", "emu", "iy", "yy", "ie",
        "ye", "ih", "yh", "ym", "im",
    }
)
_QUANTITY_RE = re.compile(r"^[xh](\d)$")

PRIORITY_CUSTOM = 5
PRIORITY_NAME = 4
PRIORITY_MEMBER = 3
PRIORITY_BASE = 2
PRIORITY_SHORT = 1


def _tokens(value: Any) -> list[str]:
    return [token for token in normalize_search_text(value).split() if token and token not in _STOP_TOKENS]


def _strip_qualifiers(value: str) -> str:
    return " ".join(_QUALIFIER_RE.sub(" ", str(value or "")).split())


def _token_matches(alias_token: str, text_token: str) -> bool:
    """Exact match, or the same word with a Russian case ending (паук/паука)."""
    if alias_token == text_token:
        return True
    if len(alias_token) < 4 or alias_token.isdigit() or text_token.isdigit():
        return False
    common = len(os.path.commonprefix([alias_token, text_token]))
    if common < 3 or common < len(alias_token) - 3:
        return False
    return alias_token[common:] in _WORD_ENDINGS and text_token[common:] in _WORD_ENDINGS


@dataclass
class _Entity:
    slug: str
    name: str
    kind: str
    sort_order: int
    duration: int
    name_tokens: frozenset[str]
    number_tokens: frozenset[str]


@dataclass
class RecognizedItem:
    slug: str
    name: str
    kind: str
    alternatives: list[str] = field(default_factory=list)
    quantity: int = 1


@dataclass
class Recognition:
    programs: list[RecognizedItem] = field(default_factory=list)
    characters: list[RecognizedItem] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return bool(self.programs or self.characters)


class CalendarMatcher:
    """Find managed programs and characters mentioned in free calendar text."""

    def __init__(self, entities: list[dict[str, Any]], aliases: Iterable[dict[str, Any]] = ()) -> None:
        self._entities: dict[str, _Entity] = {}
        self._aliases: dict[str, list[tuple[tuple[str, ...], str, int]]] = {}
        for item in entities:
            self._add_entity(item)
        for alias in aliases:
            slug = str(alias.get("entity_slug") or "")
            if slug in self._entities:
                self._add_alias(str(alias.get("phrase") or ""), slug, PRIORITY_CUSTOM)

    @classmethod
    def from_catalog(cls) -> "CalendarMatcher":
        entities = [
            *list_characters(entity_type=ENTITY_TYPE_SHOW_PROGRAM),
            *list_characters(entity_type=ENTITY_TYPE_CHARACTER),
        ]
        return cls(entities, store.list_aliases())

    def entity(self, slug: str) -> _Entity | None:
        return self._entities.get(slug)

    def entities(self) -> list[_Entity]:
        return sorted(self._entities.values(), key=lambda item: (item.kind != "program", item.name.casefold()))

    def _add_alias(self, phrase: str, slug: str, priority: int) -> None:
        tokens = tuple(_tokens(phrase))
        # Admin-defined abbreviations («ЛБ») may be short; catalog-derived ones may not.
        too_short = len(tokens) == 1 and len(tokens[0]) < 3 and priority != PRIORITY_CUSTOM
        if not tokens or too_short:
            return
        if all(token.isdigit() for token in tokens):
            return
        bucket = self._aliases.setdefault(tokens[0][:3], [])
        entry = (tokens, slug, priority)
        if entry not in bucket:
            bucket.append(entry)

    def _add_synonyms(self, phrase: str, slug: str) -> None:
        normalized = normalize_search_text(phrase)
        for key in {normalized, normalized.replace(" ", "")}:
            for synonym in _SYNONYM_INDEX.get(key, ()):
                if len(synonym.replace(" ", "")) >= 4:
                    self._add_alias(synonym, slug, PRIORITY_SHORT)

    def _add_entity(self, item: dict[str, Any]) -> None:
        slug = str(item.get("slug") or "").strip()
        name = str(item.get("name") or "").strip()
        if not slug or not name:
            return
        kind = "program" if item.get("entity_type") == ENTITY_TYPE_SHOW_PROGRAM else "character"
        members = [str(member or "").strip() for member in (item.get("ensemble_members") or []) if str(member or "").strip()]
        name_token_list = _tokens(name)
        member_tokens = [token for member in members for token in _tokens(member)]
        self._entities[slug] = _Entity(
            slug=slug,
            name=name,
            kind=kind,
            sort_order=int(item.get("sort_order") or 0),
            duration=int(item.get("default_duration_minutes") or 0),
            name_tokens=frozenset(
                token
                for token in (*name_token_list, *member_tokens)
                if not token.isdigit() and token not in _GENERIC_TOKENS
            ),
            number_tokens=frozenset(token for token in name_token_list if token.isdigit()),
        )

        self._add_alias(name, slug, PRIORITY_NAME)
        base = _TITLE_SPLIT_RE.split(_strip_qualifiers(name))[0]
        self._add_alias(base, slug, PRIORITY_BASE)
        self._add_synonyms(base, slug)
        if kind == "program":
            core_tokens = [token for token in _tokens(base) if token not in _GENERIC_TOKENS]
            if core_tokens and len("".join(core_tokens)) >= 4:
                self._add_alias(" ".join(core_tokens), slug, PRIORITY_BASE)
        self._add_alias(slug.replace("-", " "), slug, PRIORITY_BASE)
        self._add_synonyms(slug.replace("-", " "), slug)

        for member in members:
            self._add_alias(member, slug, PRIORITY_MEMBER)
            member_base = _strip_qualifiers(member)
            self._add_alias(member_base, slug, PRIORITY_BASE)
            self._add_synonyms(member_base, slug)
        # "Микки Маус" + "Минни Маус" are usually written as "Микки и Минни".
        member_token_lists = [_tokens(_strip_qualifiers(member)) for member in members]
        if len(member_token_lists) >= 2 and all(len(tokens) >= 2 for tokens in member_token_lists):
            if len({tokens[-1] for tokens in member_token_lists}) == 1:
                for tokens in member_token_lists:
                    if len(tokens[0]) >= 4:
                        self._add_alias(tokens[0], slug, PRIORITY_SHORT)

    def recognize(self, text: str, *, duration_minutes: int | None = None) -> Recognition:
        tokens = _tokens(text)
        spans: dict[tuple[int, int], dict[str, int]] = {}
        for index, token in enumerate(tokens):
            for alias_tokens, slug, priority in self._aliases.get(token[:3], ()):
                end = index + len(alias_tokens)
                if end > len(tokens):
                    continue
                if all(_token_matches(alias_tokens[offset], tokens[index + offset]) for offset in range(len(alias_tokens))):
                    candidates = spans.setdefault((index, end), {})
                    candidates[slug] = max(priority, candidates.get(slug, 0))

        accepted: list[tuple[int, int, dict[str, int]]] = []
        covered: set[int] = set()
        for (start, end), candidates in sorted(
            spans.items(),
            key=lambda entry: (-(entry[0][1] - entry[0][0]), -max(entry[1].values()), entry[0][0]),
        ):
            if covered.intersection(range(start, end)):
                continue
            accepted.append((start, end, candidates))
            covered.update(range(start, end))
        accepted.sort(key=lambda entry: entry[0])

        counts = Counter(slug for _, _, candidates in accepted for slug in candidates)
        token_set = set(tokens)
        result = Recognition()
        seen: set[str] = set()
        for start, end, candidates in accepted:
            number_after = tokens[end] if end < len(tokens) and tokens[end].isdigit() else ""

            def rank(slug: str) -> tuple[int, ...]:
                entity = self._entities[slug]
                duration_fit = 0
                if entity.kind == "program" and duration_minutes and entity.duration:
                    duration_fit = -abs(entity.duration - int(duration_minutes))
                return (
                    counts[slug],
                    1 if number_after and number_after in entity.number_tokens else 0,
                    len(entity.name_tokens & token_set),
                    candidates[slug],
                    duration_fit,
                )

            ordered = sorted(
                candidates,
                key=lambda slug: (tuple(-value for value in rank(slug)), self._entities[slug].sort_order, slug),
            )
            best = rank(ordered[0])
            alternatives = [slug for slug in ordered if rank(slug) == best]
            chosen = ordered[0]
            if chosen in seen:
                continue
            seen.add(chosen)

            quantity = 1
            before = tokens[start - 1] if start > 0 else ""
            after = tokens[end] if end < len(tokens) else ""
            if before.isdigit() and 2 <= int(before) <= 5:
                quantity = int(before)
            elif _QUANTITY_RE.match(after):
                quantity = int(_QUANTITY_RE.match(after).group(1))
            elif after in {"x", "h"} and end + 1 < len(tokens) and tokens[end + 1].isdigit():
                quantity = max(1, min(9, int(tokens[end + 1])))

            entity = self._entities[chosen]
            recognized = RecognizedItem(
                slug=chosen,
                name=entity.name,
                kind=entity.kind,
                alternatives=alternatives,
                quantity=max(1, quantity),
            )
            (result.programs if entity.kind == "program" else result.characters).append(recognized)
        return result


# --- calendar -> site import ------------------------------------------------------

_TAG_BREAK_RE = re.compile(r"<\s*(br|/p|/div|/li)\s*/?\s*>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_text(value: str) -> str:
    text = _TAG_BREAK_RE.sub("\n", str(value or ""))
    return html.unescape(_TAG_RE.sub(" ", text))


def _parse_rfc3339(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=LOCAL_TIMEZONE)
    return parsed


def event_local_bounds(event: dict[str, Any]) -> tuple[datetime, datetime, bool] | None:
    """Return naive Tashkent start/end of a Google event plus the all-day flag."""
    start = event.get("start") or {}
    end = event.get("end") or {}
    try:
        if start.get("dateTime"):
            start_at = _parse_rfc3339(start["dateTime"]).astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)
            end_raw = end.get("dateTime") or start["dateTime"]
            end_at = _parse_rfc3339(end_raw).astimezone(LOCAL_TIMEZONE).replace(tzinfo=None)
            all_day = False
        elif start.get("date"):
            start_at = datetime.combine(date.fromisoformat(start["date"]), time())
            end_at = datetime.combine(date.fromisoformat(end.get("date") or start["date"]), time())
            if end_at <= start_at:
                end_at = start_at + timedelta(days=1)
            all_day = True
        else:
            return None
    except (TypeError, ValueError):
        return None
    start_at = start_at.replace(second=0, microsecond=0)
    if end_at.second or end_at.microsecond:
        end_at = end_at.replace(second=0, microsecond=0) + timedelta(minutes=1)
    if end_at <= start_at:
        end_at = start_at + timedelta(minutes=DEFAULT_EVENT_DURATION_MINUTES)
    return start_at, end_at, all_day


def _declined_by_owner(event: dict[str, Any]) -> bool:
    return any(
        bool(attendee.get("self")) and attendee.get("responseStatus") == "declined"
        for attendee in (event.get("attendees") or [])
        if isinstance(attendee, dict)
    )


def _allocate(
    item: RecognizedItem,
    start_at: datetime,
    end_at: datetime,
    allocations: list[tuple[datetime, datetime, str]],
) -> list[str]:
    """Pick concrete costumes for an ambiguous mention (e.g. two «Человек-паук»)."""
    alternatives = item.alternatives or [item.slug]
    if len(alternatives) == 1:
        return alternatives[:1]
    busy = {slug for busy_start, busy_end, slug in allocations if busy_start < end_at and busy_end > start_at}
    ordered = [slug for slug in alternatives if slug not in busy] + [slug for slug in alternatives if slug in busy]
    return ordered[: max(1, min(item.quantity, len(ordered)))]


def build_imported_rows(
    events: list[dict[str, Any]],
    *,
    calendar_id: str,
    matcher: CalendarMatcher,
    own_event_ids: set[str] | None = None,
    ignored_keys: set[str] | None = None,
    block_unmatched: bool = False,
) -> list[dict[str, Any]]:
    own_event_ids = own_event_ids or set()
    ignored_keys = ignored_keys or set()
    prepared: list[tuple[datetime, datetime, bool, dict[str, Any]]] = []
    for event in events:
        if not isinstance(event, dict) or event.get("status") == "cancelled" or not event.get("id"):
            continue
        bounds = event_local_bounds(event)
        if bounds is None:
            continue
        prepared.append((*bounds, event))
    prepared.sort(key=lambda entry: (entry[0], entry[1], str(entry[3].get("id"))))

    allocations: list[tuple[datetime, datetime, str]] = []
    rows: list[dict[str, Any]] = []
    for start_at, end_at, all_day, event in prepared:
        event_id = str(event["id"])
        event_key = f"{calendar_id}|{event_id}"
        private = ((event.get("extendedProperties") or {}).get("private") or {})
        summary = " ".join(str(event.get("summary") or "").split())
        row: dict[str, Any] = {
            "event_key": event_key,
            "calendar_id": calendar_id,
            "event_id": event_id,
            "summary": summary or "(без названия)",
            "html_link": str(event.get("htmlLink") or ""),
            "start_local": start_at.strftime(store.LOCAL_DATETIME_FORMAT),
            "end_local": end_at.strftime(store.LOCAL_DATETIME_FORMAT),
            "all_day": all_day,
            "program_slugs": [],
            "program_names": [],
            "character_slugs": [],
            "character_names": [],
            "match_status": "unmatched",
            "order_public_id": "",
            "blocks_time": False,
            "blocks_all": False,
            "google_updated": str(event.get("updated") or ""),
        }
        if private.get("surprizOrderId") or event_id in own_event_ids:
            # Orders pushed by the site already block time through party_orders.
            row["match_status"] = "own"
            row["order_public_id"] = str(private.get("surprizOrderId") or "")
            rows.append(row)
            continue

        duration = int((end_at - start_at).total_seconds() // 60)
        text = f"{summary}\n{_html_to_text(event.get('description') or '')}"
        recognition = matcher.recognize(text, duration_minutes=None if all_day else duration)
        program_slugs: list[str] = []
        for item in recognition.programs:
            if item.slug not in program_slugs:
                program_slugs.append(item.slug)
        character_slugs: list[str] = []
        for item in recognition.characters:
            for slug in _allocate(item, start_at, end_at, allocations):
                if slug not in character_slugs:
                    character_slugs.append(slug)
        row["program_slugs"] = program_slugs
        row["program_names"] = [matcher.entity(slug).name for slug in program_slugs if matcher.entity(slug)]
        row["character_slugs"] = character_slugs
        row["character_names"] = [matcher.entity(slug).name for slug in character_slugs if matcher.entity(slug)]

        if event_key in ignored_keys:
            row["match_status"] = "ignored"
        elif event.get("transparency") == "transparent" or _declined_by_owner(event):
            row["match_status"] = "free"
        elif recognition.matched:
            row["match_status"] = "matched"
            row["blocks_time"] = True
            allocations.extend((start_at, end_at, slug) for slug in character_slugs)
        else:
            row["blocks_time"] = bool(block_unmatched)
            row["blocks_all"] = bool(block_unmatched)
        rows.append(row)
    return rows


def _fetch_calendar_events(calendar_id: str, time_min: datetime, time_max: datetime) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    page_token = ""
    for _ in range(IMPORT_MAX_PAGES):
        params: dict[str, Any] = {
            "singleEvents": "true",
            "orderBy": "startTime",
            "showDeleted": "false",
            "maxResults": 2500,
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "fields": (
                "items(id,status,summary,description,start,end,transparency,attendees(self,responseStatus),"
                "extendedProperties,htmlLink,updated),nextPageToken"
            ),
        }
        if page_token:
            params["pageToken"] = page_token
        _, payload = _api("GET", _events_path(calendar_id), params=params)
        events.extend(item for item in (payload.get("items") or []) if isinstance(item, dict))
        page_token = str(payload.get("nextPageToken") or "")
        if not page_token:
            break
    return events


def request_import() -> None:
    store.set_settings({"last_import_attempt_at": ""})
    wake_worker()


def import_calendar_events() -> dict[str, Any]:
    settings = _settings()
    if not _import_ready(settings):
        return {"skipped": True}
    calendar_id = settings["calendar_id"]
    store.set_settings({"last_import_attempt_at": _utcnow().isoformat()})
    today = _local_now().date()
    time_min = datetime.combine(today - timedelta(days=IMPORT_PAST_DAYS), time(), tzinfo=LOCAL_TIMEZONE)
    time_max = datetime.combine(today + timedelta(days=IMPORT_HORIZON_DAYS), time(), tzinfo=LOCAL_TIMEZONE)
    try:
        events = _fetch_calendar_events(calendar_id, time_min, time_max)
        rows = build_imported_rows(
            events,
            calendar_id=calendar_id,
            matcher=CalendarMatcher.from_catalog(),
            own_event_ids=store.list_order_event_ids(calendar_id),
            ignored_keys=store.list_ignored_event_keys(),
            block_unmatched=_flag(settings, "block_unmatched"),
        )
    except GoogleCalendarError as exc:
        store.set_settings({"last_import_error": str(exc)})
        raise
    if store.get_setting("calendar_id") != calendar_id or not _import_ready(_settings()):
        # The admin switched calendars or disconnected while we were fetching.
        return {"skipped": True}
    store.replace_imported_events(rows)
    stats = dict(Counter(row["match_status"] for row in rows))
    stats["total"] = len(rows)
    store.set_settings(
        {
            "last_import_at": _utcnow().isoformat(),
            "last_import_error": "",
            "last_import_stats": json.dumps(stats, ensure_ascii=False),
        }
    )
    return stats


def _import_due(settings: dict[str, str]) -> bool:
    if not _import_ready(settings):
        return False
    try:
        last_attempt = datetime.fromisoformat(settings.get("last_import_attempt_at") or "")
    except ValueError:
        return True
    try:
        minutes = int(settings.get("poll_minutes") or DEFAULT_POLL_MINUTES)
    except ValueError:
        minutes = DEFAULT_POLL_MINUTES
    return _utcnow() - last_attempt >= timedelta(minutes=max(1, minutes))


# --- site -> calendar export ------------------------------------------------------


def _plural(value: int, one: str, few: str, many: str) -> str:
    number = abs(int(value))
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def _roster(order: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for raw in order.get("character_names") or []:
        name = str(raw or "").strip().split(" (", 1)[0].strip()
        if name:
            names.append(name)
    return names


def order_title_values(order: dict[str, Any]) -> dict[str, str]:
    age = order.get("celebrant_age")
    children = order.get("children_count")
    return {
        "program": str(order.get("program_name") or "Праздник"),
        "characters": " + ".join(_roster(order)),
        "celebrant": str(order.get("celebrant_name") or "").strip(),
        "age": f"{int(age)} {_plural(int(age), 'год', 'года', 'лет')}" if str(age or "").isdigit() else "",
        "children": (
            f"{int(children)} {_plural(int(children), 'ребёнок', 'ребёнка', 'детей')}"
            if str(children or "").isdigit()
            else ""
        ),
        "client": str(order.get("customer_name") or "").strip(),
        "phone": str(order.get("customer_phone") or "").strip(),
        "address": str(order.get("address_text") or "").strip(),
        "time": f"{order.get('time_from') or ''}–{order.get('time_to') or ''}".strip("–"),
        "total": str(order.get("total_price_label") or format_money(order.get("total_price"))),
        "order": str(order.get("public_id") or ""),
    }


_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")
_SEPARATOR_CHARS = "—–·|,:"


def render_title(template: str, order: dict[str, Any]) -> str:
    values = order_title_values(order)
    title = _PLACEHOLDER_RE.sub(lambda match: values.get(match.group(1), match.group(0)), template or DEFAULT_TITLE_TEMPLATE)
    title = re.sub(r"[(\[]\s*[)\]]", " ", title)
    separators = re.escape(_SEPARATOR_CHARS)
    title = re.sub(rf"\s+([{separators}])", r" \1", title)
    title = re.sub(rf"([{separators}])(?:\s*[{separators}])+", r"\1", title)
    title = re.sub(rf"^[\s{separators}]+|[\s{separators}]+$", "", title)
    title = " ".join(title.replace(" ,", ",").split())
    return title[:TITLE_MAX_LENGTH] or values["program"]


def _telegram_html_to_text(value: str) -> str:
    text = re.sub(
        r'<a\s+href="([^"]*)">([^<]*)</a>',
        lambda match: f"{match.group(2)}: {html.unescape(match.group(1))}",
        str(value or ""),
    )
    return html.unescape(_TAG_RE.sub("", text)).strip()


def format_order_description(order: dict[str, Any]) -> str:
    """The same order card managers already get in Telegram, as plain text."""
    from .admin_notifications import _format_order_message

    lines = [_telegram_html_to_text(_format_order_message(order))]
    addons = [str(addon.get("name") or "") for addon in (order.get("addons") or []) if addon.get("name")]
    if addons:
        lines.append(f"Доп. услуги: {', '.join(addons)}")
    if order.get("payment_method_label"):
        lines.append(f"Оплата: {order['payment_method_label']}")
    return "\n".join(line for line in lines if line)


def build_order_event_body(order: dict[str, Any], settings: dict[str, str] | None = None) -> dict[str, Any]:
    settings = settings or _settings()
    celebration_date = str(order.get("celebration_date") or "")
    location_parts = [str(order.get("address_text") or "").strip()]
    label = str(order.get("location_label") or "").strip()
    if label and label not in location_parts:
        location_parts.append(label)
    body: dict[str, Any] = {
        "summary": render_title(settings.get("title_template") or DEFAULT_TITLE_TEMPLATE, order),
        "description": format_order_description(order),
        "location": ", ".join(part for part in location_parts if part),
        "start": {
            "dateTime": f"{celebration_date}T{order.get('time_from')}:00{LOCAL_UTC_OFFSET}",
            "timeZone": LOCAL_TIMEZONE_NAME,
        },
        "end": {
            "dateTime": f"{celebration_date}T{order.get('time_to')}:00{LOCAL_UTC_OFFSET}",
            "timeZone": LOCAL_TIMEZONE_NAME,
        },
        "status": "confirmed",
        "transparency": "opaque",
        "extendedProperties": {
            "private": {
                "surprizOrderId": str(order.get("public_id") or ""),
                "surprizSource": "site",
            }
        },
    }
    color_id = str(settings.get("color_id") or "")
    if color_id and color_id != "none":
        body["colorId"] = color_id
    return body


def _install_salt() -> str:
    salt = store.get_setting("event_id_salt")
    if not salt:
        salt = "".join(secrets.choice(EVENT_ID_ALPHABET) for _ in range(6))
        store.set_settings({"event_id_salt": salt})
    return salt


def _event_id(order_id: int, generation: int) -> str:
    # Google event ids allow only base32hex characters (0-9, a-v).
    return f"srp{_install_salt()}{int(order_id)}g{int(generation)}"


def _delete_event_quietly(calendar_id: str, event_id: str) -> None:
    try:
        _api("DELETE", _events_path(calendar_id, event_id), allow=(404, 410))
    except GoogleCalendarAuthError:
        raise
    except GoogleCalendarError as exc:
        if exc.status not in {403, 404, 410}:
            raise


def _write_event(calendar_id: str, event_id: str, body: dict[str, Any], *, exists: bool) -> tuple[int, dict[str, Any]]:
    """Create or update the event; returns ``(status, payload)`` of the last call.

    The deterministic id makes retries idempotent: a create that already
    happened answers 409 and is turned into an update.
    """
    if exists:
        return _api("PUT", _events_path(calendar_id, event_id), json_body=body, allow=(404, 410))
    status, payload = _api("POST", _events_path(calendar_id), json_body={**body, "id": event_id}, allow=(409,))
    if status == 409:
        return _api("PUT", _events_path(calendar_id, event_id), json_body=body, allow=(404, 410))
    return status, payload


def sync_order_event(order_id: int, settings: dict[str, str] | None = None) -> str:
    """Bring the calendar event of one order in line with the order state."""
    settings = settings or _settings()
    calendar_id = settings.get("calendar_id") or ""
    order = get_order_by_id(int(order_id))
    mapping = store.get_order_event(int(order_id))
    wanted = bool(order) and order.get("display_status") == "confirmed"
    if wanted and not mapping and str(order.get("celebration_date") or "") < _local_now().date().isoformat():
        wanted = False

    if not wanted:
        if mapping:
            _delete_event_quietly(mapping["calendar_id"], mapping["event_id"])
            store.delete_order_event(int(order_id))
            return "deleted"
        return "skipped"

    body = build_order_event_body(order, settings)
    content_hash = hashlib.sha256(
        (calendar_id + json.dumps(body, sort_keys=True, ensure_ascii=False)).encode("utf-8")
    ).hexdigest()
    if mapping and mapping["calendar_id"] == calendar_id and mapping["content_hash"] == content_hash:
        return "unchanged"
    if mapping and mapping["calendar_id"] != calendar_id:
        _delete_event_quietly(mapping["calendar_id"], mapping["event_id"])
        store.delete_order_event(int(order_id))
        mapping = None

    generation = int(mapping["generation"]) if mapping else 0
    event_id = mapping["event_id"] if mapping else _event_id(int(order_id), generation)
    status, payload = _write_event(calendar_id, event_id, body, exists=bool(mapping))
    if status in {404, 410}:
        # The old event is gone for good (removed from Google's trash): start a new one.
        generation += 1
        event_id = _event_id(int(order_id), generation)
        status, payload = _write_event(calendar_id, event_id, body, exists=False)
        if status in {404, 410}:
            raise GoogleCalendarError("Google не дал создать событие заказа. Повторим позже.", status=status)
    store.save_order_event(
        int(order_id),
        calendar_id=calendar_id,
        event_id=str(payload.get("id") or event_id),
        html_link=str(payload.get("htmlLink") or ""),
        content_hash=content_hash,
        generation=generation,
    )
    return "updated" if mapping else "created"


def process_order_queue(limit: int = 10) -> dict[str, Any]:
    settings = _settings()
    if not _export_ready(settings):
        return {"skipped": True}
    result = {"processed": 0, "succeeded": 0, "failed": 0}
    last_error = ""
    for order_id in store.list_due_orders(limit):
        queue_row = store.get_queue_row(order_id)
        if not queue_row:
            continue
        result["processed"] += 1
        try:
            sync_order_event(order_id, settings)
        except GoogleCalendarAuthError as exc:
            store.defer_order_sync(order_id, str(exc))
            result["failed"] += 1
            last_error = str(exc)
            break
        except GoogleCalendarError as exc:
            store.defer_order_sync(order_id, str(exc))
            result["failed"] += 1
            last_error = str(exc)
            continue
        except Exception as exc:  # noqa: BLE001 - a broken order must not stop the queue
            LOGGER.exception("google_calendar_order_sync_failed", extra={"order_id": order_id})
            store.defer_order_sync(order_id, f"{type(exc).__name__}")
            result["failed"] += 1
            last_error = "Внутренняя ошибка при выгрузке заказа."
            continue
        store.complete_order_sync(order_id, str(queue_row.get("updated_at") or ""))
        result["succeeded"] += 1
    if result["processed"]:
        store.set_settings({"last_export_at": _utcnow().isoformat(), "last_export_error": last_error})
    return result


def enqueue_upcoming_confirmed_orders() -> int:
    today = _local_now().date().isoformat()
    with store.get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id FROM party_orders
            WHERE confirmation_state = 'confirmed'
              AND status != 'cancelled'
              AND celebration_date >= ?
            ORDER BY celebration_date ASC, time_from ASC
            """,
            (today,),
        ).fetchall()
    count = store.enqueue_orders(int(row["id"]) for row in rows)
    wake_worker()
    return count


# --- background worker ------------------------------------------------------------


@contextmanager
def sync_lease(*, wait_seconds: float = 0.0) -> Iterator[str]:
    """Hold the single cross-process sync lease for the whole block.

    Every entry point that talks to Google (background worker, manual sync,
    imports triggered from the admin) runs under this lease, so cycles never
    overlap. A heartbeat keeps renewing it while the block runs, and it is
    released at the end so a manual sync does not wait for the TTL.
    """
    owner = f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}:{secrets.token_hex(3)}"
    deadline = time_module.monotonic() + max(0.0, wait_seconds)
    while not store.claim_lease(SYNC_LEASE_NAME, owner, SYNC_LEASE_SECONDS):
        if time_module.monotonic() >= deadline:
            raise GoogleCalendarSyncBusy("Синхронизация уже выполняется. Обновите страницу через минуту.")
        time_module.sleep(0.5)

    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(SYNC_LEASE_RENEW_SECONDS):
            try:
                store.claim_lease(SYNC_LEASE_NAME, owner, SYNC_LEASE_SECONDS)
            except Exception:  # noqa: BLE001 - a missed renewal is retried on the next beat
                continue

    renewer = threading.Thread(target=heartbeat, name="gcal-lease", daemon=True)
    renewer.start()
    try:
        yield owner
    finally:
        stop.set()
        renewer.join(timeout=5)
        store.release_lease(SYNC_LEASE_NAME, owner)


def _sync_cycle(*, force_import: bool) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        result["export"] = process_order_queue()
    except GoogleCalendarError as exc:
        result["export_error"] = str(exc)
    settings = _settings()
    if force_import or _import_due(settings):
        try:
            result["import"] = import_calendar_events()
        except GoogleCalendarError as exc:
            result["import_error"] = str(exc)
    return result


def run_sync_cycle(*, force_import: bool = False, wait_seconds: float = 0.0) -> dict[str, Any]:
    """Push queued orders and re-read the calendar when due, under the sync lease."""
    with sync_lease(wait_seconds=wait_seconds):
        return _sync_cycle(force_import=force_import)


def import_now(*, wait_seconds: float = MANUAL_SYNC_WAIT_SECONDS) -> dict[str, Any]:
    """Re-read the calendar right away (admin actions), under the sync lease."""
    with sync_lease(wait_seconds=wait_seconds):
        return import_calendar_events()


_WORKER_THREAD: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()
_WORKER_WAKE = threading.Event()


def wake_worker() -> None:
    _WORKER_WAKE.set()


def _worker_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            run_sync_cycle()
        except GoogleCalendarSyncBusy:
            pass
        except Exception as exc:  # noqa: BLE001 - the worker must survive any failure
            print(f"[gcal] sync cycle deferred after {type(exc).__name__}", flush=True)
        _WORKER_WAKE.wait(WORKER_TICK_SECONDS)
        _WORKER_WAKE.clear()


def worker_enabled() -> bool:
    return os.environ.get("GOOGLE_CALENDAR_WORKER", "1").strip().lower() not in {"0", "false", "off", "disabled"}


def start_worker_in_background() -> bool:
    """Start the periodic sync thread once per process."""
    global _WORKER_THREAD
    if not worker_enabled():
        return False
    with _WORKER_LOCK:
        if _WORKER_THREAD is not None and _WORKER_THREAD.is_alive():
            return True
        init_google_calendar()
        thread = threading.Thread(target=_worker_loop, args=(threading.Event(),), name="gcal-sync", daemon=True)
        thread.start()
        _WORKER_THREAD = thread
    return True


def run_worker_forever() -> None:
    init_google_calendar()
    _worker_loop(threading.Event())


# --- admin payloads -----------------------------------------------------------------


def _format_iso_label(value: str) -> str:
    return format_datetime_ru(value) if value else ""


_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def _event_time_labels(item: dict[str, Any]) -> tuple[str, str]:
    try:
        start_at = datetime.strptime(item["start_local"], store.LOCAL_DATETIME_FORMAT)
        end_at = datetime.strptime(item["end_local"], store.LOCAL_DATETIME_FORMAT)
    except ValueError:
        return item["start_local"], ""
    date_label = f"{_WEEKDAYS[start_at.weekday()]}, {start_at:%d.%m}"
    if item["all_day"]:
        days = max(1, (end_at.date() - start_at.date()).days)
        return date_label, "Весь день" if days == 1 else f"Весь день · {days} дн."
    if end_at.date() != start_at.date():
        return date_label, f"{start_at:%H:%M} → {end_at:%d.%m %H:%M}"
    return date_label, f"{start_at:%H:%M}–{end_at:%H:%M}"


def _sample_order() -> dict[str, Any]:
    return {
        "public_id": "SRP-00042",
        "program_name": "Стандарт",
        "character_names": ["Леди Баг + Супер-Кот"],
        "celebrant_name": "Аня",
        "celebrant_age": 6,
        "children_count": 12,
        "customer_name": "Дилноза",
        "customer_phone": "+998 (90) 123-45-67",
        "address_text": "Юнусабад, 4 квартал",
        "time_from": "15:00",
        "time_to": "16:00",
        "total_price_label": "950 000 сум",
    }


def get_admin_payload(request_base: str = "") -> dict[str, Any]:
    settings = _settings()
    client_id, _, client_source = _client_credentials()
    try:
        import_stats = json.loads(settings.get("last_import_stats") or "{}")
    except ValueError:
        import_stats = {}
    today_start = datetime.combine(_local_now().date(), time()).strftime(store.LOCAL_DATETIME_FORMAT)
    events = []
    for item in store.list_imported_events(from_local=today_start, limit=300):
        date_label, time_label = _event_time_labels(item)
        status = item["match_status"]
        events.append(
            {
                "event_key": item["event_key"],
                "date": item["start_local"][:10],
                "date_label": date_label,
                "time_label": time_label,
                "summary": item["summary"],
                "html_link": item["html_link"],
                "program_names": item["program_names"],
                "character_names": item["character_names"],
                "match_status": status,
                "status_label": MATCH_STATUS_LABELS.get(status, status),
                "blocks_time": item["blocks_time"],
                "blocks_all": item["blocks_all"],
                "order_public_id": item["order_public_id"],
            }
        )

    matcher_entities: list[dict[str, str]] = []
    try:
        entities = [
            *list_characters(entity_type=ENTITY_TYPE_SHOW_PROGRAM),
            *list_characters(entity_type=ENTITY_TYPE_CHARACTER),
        ]
        matcher_entities = [
            {
                "slug": str(item.get("slug") or ""),
                "name": str(item.get("name") or ""),
                "kind": "program" if item.get("entity_type") == ENTITY_TYPE_SHOW_PROGRAM else "character",
            }
            for item in entities
            if item.get("slug")
        ]
    except Exception:  # noqa: BLE001 - catalog problems must not hide the settings page
        LOGGER.exception("google_calendar_catalog_unavailable")
    names_by_slug = {item["slug"]: item for item in matcher_entities}
    aliases = [
        {
            "id": int(alias["id"]),
            "phrase": str(alias["phrase"]),
            "entity_slug": str(alias["entity_slug"]),
            "entity_name": (names_by_slug.get(str(alias["entity_slug"])) or {}).get("name", alias["entity_slug"]),
            "kind": (names_by_slug.get(str(alias["entity_slug"])) or {}).get("kind", ""),
        }
        for alias in store.list_aliases()
    ]
    queue = store.queue_stats()
    color_id = settings.get("color_id") or DEFAULT_COLOR_ID
    return {
        "status": {
            "client_configured": bool(client_id),
            "client_source": client_source,
            "client_id": client_id,
            "redirect_uri": resolve_redirect_uri(request_base),
            "connected": _is_connected(settings),
            "account_email": settings.get("account_email", ""),
            "connected_at_label": _format_iso_label(settings.get("connected_at", "")),
            "auth_error": settings.get("auth_error", ""),
            "calendar_id": settings.get("calendar_id", ""),
            "calendar_summary": settings.get("calendar_summary", ""),
            "last_import_at_label": _format_iso_label(settings.get("last_import_at", "")),
            "last_import_error": settings.get("last_import_error", ""),
            "last_export_at_label": _format_iso_label(settings.get("last_export_at", "")),
            "last_export_error": settings.get("last_export_error", "") or queue["last_error"],
            "queue_pending": queue["pending"],
            "queue_failing": queue["failing"],
            "import_stats": import_stats,
            "worker_hint": "Синхронизация идёт в фоне в сервисе Telegram-бота (surpriz-bot).",
        },
        "settings": {
            "import_enabled": _flag(settings, "import_enabled"),
            "export_enabled": _flag(settings, "export_enabled"),
            "block_unmatched": _flag(settings, "block_unmatched"),
            "poll_minutes": int(settings.get("poll_minutes") or DEFAULT_POLL_MINUTES),
            "title_template": settings.get("title_template") or DEFAULT_TITLE_TEMPLATE,
            "color_id": "" if color_id == "none" else color_id,
        },
        "title_preview": render_title(settings.get("title_template") or DEFAULT_TITLE_TEMPLATE, _sample_order()),
        "events": events,
        "event_stats": store.imported_event_stats(),
        "aliases": aliases,
        "entities": matcher_entities,
        "colors": list(EVENT_COLORS),
        "poll_choices": list(POLL_MINUTE_CHOICES),
        "placeholders": list(TITLE_PLACEHOLDERS),
        "default_title_template": DEFAULT_TITLE_TEMPLATE,
    }


def preview_recognition(text: str) -> dict[str, Any]:
    recognition = CalendarMatcher.from_catalog().recognize(str(text or "")[:2000])
    return {
        "programs": [item.name for item in recognition.programs],
        "characters": [item.name for item in recognition.characters],
        "matched": recognition.matched,
    }


def add_alias(phrase: str, entity_slug: str) -> dict[str, Any]:
    phrase = " ".join(str(phrase or "").split())[:80]
    normalized = " ".join(_tokens(phrase))
    if not normalized:
        raise GoogleCalendarError("Введите слово или фразу из календаря.")
    known = {entity.slug for entity in CalendarMatcher.from_catalog().entities()}
    if entity_slug not in known:
        raise GoogleCalendarError("Выберите персонажа или шоу-программу из каталога.")
    alias = store.add_alias(phrase, normalized, entity_slug)
    request_import()
    return alias


def remove_alias(alias_id: int) -> bool:
    removed = store.delete_alias(int(alias_id))
    if removed:
        request_import()
    return removed


def set_event_ignored(event_key: str, ignored: bool) -> None:
    event_key = str(event_key or "").strip()
    if not event_key:
        raise GoogleCalendarError("Событие не найдено.")
    store.set_event_ignored(event_key, bool(ignored))
    request_import()


if __name__ == "__main__":
    run_worker_forever()
