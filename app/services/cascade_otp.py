from __future__ import annotations

from typing import Any

import requests
from flask import current_app


def _base_url() -> str:
    # otp.kztusdt.kz 308 → cascade.kz; prefer cascade to keep Authorization header
    return (current_app.config.get("OTP_API_BASE_URL") or "https://cascade.kz/api").rstrip("/")


def _token() -> str:
    return (current_app.config.get("OTP_API_TOKEN") or "").strip()


def cascade_enabled() -> bool:
    return bool(_token())


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _parse_response(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if response.status_code == 401:
        return {"success": False, "message": "Ошибка авторизации OTP-сервиса."}
    if "success" not in data:
        message = data.get("message") or data.get("error")
        if isinstance(data.get("errors"), dict):
            first = next(iter(data["errors"].values()), None)
            if isinstance(first, list) and first:
                message = first[0]
            elif first:
                message = first
        return {
            "success": False,
            "message": str(message or f"OTP API error ({response.status_code})"),
        }
    return data


def _whatsapp_unavailable(result: dict[str, Any]) -> bool:
    message = str(result.get("message") or "").lower()
    code = str(result.get("error_code") or "").lower()
    if "whatsapp" not in message and "whatsapp" not in code:
        return False
    markers = ("нет", "не подключ", "другой канал", "unavailable", "not found")
    return any(marker in message or marker in code for marker in markers)


def _post_send(
    phone: str,
    *,
    purpose: str,
    channel: str | None = None,
    link: str | None = None,
    link_expires_in: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"phone": phone, "purpose": purpose}
    if channel:
        payload["channel"] = channel
    if link:
        payload["link"] = link
    if link_expires_in is not None:
        payload["link_expires_in"] = link_expires_in

    try:
        response = requests.post(
            f"{_base_url()}/otp/send",
            json=payload,
            headers=_headers(),
            timeout=30,
        )
    except requests.RequestException:
        current_app.logger.exception("Cascade OTP send failed")
        return {"success": False, "message": "Не удалось отправить код. Попробуй позже."}

    return _parse_response(response)


def send_otp(
    phone: str,
    *,
    purpose: str = "login",
    channel: str | None = None,
    link: str | None = None,
    link_expires_in: int | None = None,
) -> dict[str, Any]:
    if not cascade_enabled():
        return {"success": False, "message": "OTP_API_TOKEN не настроен."}

    result = _post_send(
        phone,
        purpose=purpose,
        channel=channel,
        link=link,
        link_expires_in=link_expires_in,
    )
    if result.get("success"):
        return result

    # Cabinet default is often WhatsApp-only. Retry Telegram/SMS when WA is missing.
    if channel or not _whatsapp_unavailable(result):
        current_app.logger.warning(
            "Cascade OTP send failed phone=…%s purpose=%s message=%s",
            phone[-4:] if len(phone) >= 4 else phone,
            purpose,
            result.get("message"),
        )
        return result

    last = result
    for fallback in ("telegram",):
        retry = _post_send(
            phone,
            purpose=purpose,
            channel=fallback,
            link=link,
            link_expires_in=link_expires_in,
        )
        if retry.get("success"):
            current_app.logger.info("Cascade OTP sent via %s after WhatsApp miss", fallback)
            return retry
        last = retry
        if "подождите" in str(retry.get("message") or "").lower():
            break

    current_app.logger.warning(
        "Cascade OTP send failed phone=…%s purpose=%s message=%s",
        phone[-4:] if len(phone) >= 4 else phone,
        purpose,
        last.get("message"),
    )
    return last


def verify_otp(phone: str, code: str, *, purpose: str = "login") -> dict[str, Any]:
    if not cascade_enabled():
        return {"success": False, "message": "OTP_API_TOKEN не настроен."}

    try:
        response = requests.post(
            f"{_base_url()}/otp/verify",
            json={"phone": phone, "code": code, "purpose": purpose},
            headers=_headers(),
            timeout=30,
        )
    except requests.RequestException:
        current_app.logger.exception("Cascade OTP verify failed")
        return {"success": False, "message": "Не удалось проверить код. Попробуй позже."}

    return _parse_response(response)
