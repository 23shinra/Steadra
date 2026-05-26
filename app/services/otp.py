from __future__ import annotations

import random
import re
import string
from datetime import datetime, timezone

from flask import current_app

from .cache import cache_delete, cache_get, cache_set
from .sms import send_otp_sms


def normalize_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def _otp_key(phone: str, purpose: str) -> str:
    return f"otp:{purpose}:{phone}"


def generate_code() -> str:
    demo = (current_app.config.get("OTP_DEMO_CODE") or "").strip()
    if demo:
        return demo
    length = int(current_app.config.get("OTP_LENGTH", 4))
    return "".join(random.choices(string.digits, k=length))


def send_otp(phone: str, purpose: str = "login") -> tuple[bool, str | None]:
    phone = normalize_phone(phone)
    if len(phone) != 11 or not phone.startswith("7"):
        return False, "Неверный формат номера."

    code = generate_code()
    ttl = int(current_app.config.get("OTP_TTL_SECONDS", 300))
    cache_set(_otp_key(phone, purpose), code, ttl=ttl)

    if not send_otp_sms(phone, code):
        return False, "Не удалось отправить SMS. Попробуй позже."

    return True, code if current_app.config.get("SMS_PROVIDER") == "mock" else None


def verify_otp(phone: str, code: str, purpose: str = "login") -> bool:
    phone = normalize_phone(phone)
    code = (code or "").strip()
    if not code:
        return False

    stored = cache_get(_otp_key(phone, purpose))
    if stored and stored == code:
        cache_delete(_otp_key(phone, purpose))
        return True

    confirm = (current_app.config.get("PROFILE_NAME_CONFIRM_CODE") or "").strip()
    if confirm and code == confirm:
        return True

    return False
