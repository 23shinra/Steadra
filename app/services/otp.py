from __future__ import annotations

import random
import re
import string

from flask import current_app, has_request_context, request

from .cache import cache_delete, cache_get, cache_incr, cache_set
from .cascade_otp import cascade_enabled, send_otp as cascade_send, verify_otp as cascade_verify
from .sms import send_otp_sms


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    return digits


def _otp_key(phone: str, purpose: str) -> str:
    return f"otp:{purpose}:{phone}"


def _client_ip() -> str:
    if not has_request_context():
        return "local"
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    return forwarded or (request.remote_addr or "unknown")


def _rate_limit(key: str, *, limit: int, window: int, message: str) -> tuple[bool, str | None]:
    if limit <= 0:
        return True, None
    count = cache_incr(key, ttl=window)
    if count > limit:
        return False, message
    return True, None


def check_send_rate_limits(phone: str, purpose: str) -> tuple[bool, str | None]:
    phone_limit = int(current_app.config.get("OTP_SEND_LIMIT_PHONE", 5))
    phone_window = int(current_app.config.get("OTP_SEND_WINDOW_SECONDS", 3600))
    ip_limit = int(current_app.config.get("OTP_SEND_LIMIT_IP", 15))
    ip_window = int(current_app.config.get("OTP_SEND_IP_WINDOW_SECONDS", 3600))
    ok, err = _rate_limit(
        f"otp:rl:send:phone:{purpose}:{phone}",
        limit=phone_limit,
        window=phone_window,
        message="Слишком много запросов кода на этот номер. Подожди около часа.",
    )
    if not ok:
        return ok, err
    return _rate_limit(
        f"otp:rl:send:ip:{_client_ip()}",
        limit=ip_limit,
        window=ip_window,
        message="Слишком много запросов кода с этого устройства. Подожди немного.",
    )


def check_verify_rate_limits(phone: str, purpose: str) -> tuple[bool, str | None]:
    limit = int(current_app.config.get("OTP_VERIFY_LIMIT_PHONE", 10))
    window = int(current_app.config.get("OTP_VERIFY_WINDOW_SECONDS", 900))
    return _rate_limit(
        f"otp:rl:verify:phone:{purpose}:{phone}",
        limit=limit,
        window=window,
        message="Слишком много попыток ввода кода. Подожди 15 минут или запроси новый.",
    )


def generate_code() -> str:
    demo = (current_app.config.get("OTP_DEMO_CODE") or "").strip()
    if demo:
        return demo
    length = int(current_app.config.get("OTP_LENGTH", 4))
    return "".join(random.choices(string.digits, k=length))


def use_cascade(*, force_local: bool = False) -> bool:
    if force_local:
        return False
    provider = (current_app.config.get("OTP_PROVIDER") or "").strip().lower()
    if provider in {"mock", "local", "sms"}:
        return False
    if provider == "cascade":
        return cascade_enabled()
    return cascade_enabled()


def send_otp(phone: str, purpose: str = "login", *, force_local: bool = False) -> tuple[bool, str | None]:
    phone = normalize_phone(phone)
    if len(phone) != 11 or not phone.startswith("7"):
        return False, "Неверный формат номера."

    ok, err = check_send_rate_limits(phone, purpose)
    if not ok:
        return False, err

    if use_cascade(force_local=force_local):
        channel = (current_app.config.get("OTP_CHANNEL") or "").strip() or None
        result = cascade_send(phone, purpose=purpose, channel=channel)
        if not result.get("success"):
            message = str(result.get("message") or "Не удалось отправить код.")
            lowered = message.lower()
            error_code = str(result.get("error_code") or "").lower()
            if error_code == "cooldown" or "подождите" in lowered:
                message = (
                    "Код уже отправляли на этот номер. "
                    "Проверь WhatsApp и Telegram, подожди 1–2 минуты перед новой попыткой."
                )
            elif "whatsapp" in lowered:
                message = (
                    "На этом номере нет WhatsApp, и запасные каналы не сработали. "
                    "Проверь номер или попробуй Demo-вход / напиши в поддержку."
                )
            elif "токен" in lowered and "баланс" in lowered:
                message = "Сейчас не получается отправить код. Попробуй чуть позже."
            return False, message
        return True, None

    code = generate_code()
    ttl = int(current_app.config.get("OTP_TTL_SECONDS", 300))
    cache_set(_otp_key(phone, purpose), code, ttl=ttl)

    if not send_otp_sms(phone, code):
        return False, "Не удалось отправить SMS. Попробуй позже."

    return True, code if current_app.config.get("SMS_PROVIDER") == "mock" else None


def verify_otp(phone: str, code: str, purpose: str = "login", *, force_local: bool = False) -> tuple[bool, str | None]:
    phone = normalize_phone(phone)
    code = (code or "").strip()
    if not code:
        return False, "Введи код из сообщения."

    ok, err = check_verify_rate_limits(phone, purpose)
    if not ok:
        return False, err

    if use_cascade(force_local=force_local):
        result = cascade_verify(phone, code, purpose=purpose)
        if result.get("success"):
            return True, None
        return False, str(result.get("message") or "Неверный или просроченный код.")

    from ..security import tokens_match

    stored = cache_get(_otp_key(phone, purpose))
    if stored and tokens_match(str(stored), code):
        cache_delete(_otp_key(phone, purpose))
        return True, None

    # Dev-only master code — never for admin, never when demo login is off.
    confirm = (current_app.config.get("PROFILE_NAME_CONFIRM_CODE") or "").strip()
    if (
        confirm
        and current_app.config.get("ALLOW_DEMO_LOGIN")
        and purpose not in {"admin_login"}
        and tokens_match(confirm, code)
    ):
        return True, None

    return False, "Неверный или просроченный код."
