from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Mapping

from flask import Request, jsonify

from .config import FORMS_ROOT

SUCCESS_MESSAGE = "Ваша заявка успешно отправлена!"


def _to_serializable(form: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in form.items()}


def persist_form_submission(request: Request) -> None:
    FORMS_ROOT.mkdir(parents=True, exist_ok=True)
    record = {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "path": request.path,
        "remote_addr": request.headers.get("X-Forwarded-For", request.remote_addr or ""),
        "user_agent": request.headers.get("User-Agent", ""),
        "action": request.form.get("action", ""),
        "payload": _to_serializable(request.form),
    }
    target = FORMS_ROOT / "elementor_forms.jsonl"
    with target.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def handle_admin_ajax(request: Request):
    action = request.form.get("action", "")
    if action == "elementor_pro_forms_send_form":
        persist_form_submission(request)
        return jsonify({"success": True, "data": {"message": SUCCESS_MESSAGE, "data": []}})

    return jsonify({"success": True, "data": {}})
