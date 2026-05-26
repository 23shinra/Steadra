from __future__ import annotations

from flask import current_app


def send_otp_sms(phone: str, code: str) -> bool:
    provider = (current_app.config.get("SMS_PROVIDER") or "mock").lower()
    message = f"Kangaroo: код {code}. Действует 5 минут."

    if provider == "mock":
        current_app.logger.info("SMS mock → %s: %s", phone, code)
        return True

    if provider == "twilio":
        return _send_twilio(phone, message)

    current_app.logger.warning("Unknown SMS provider: %s", provider)
    return False


def _send_twilio(phone: str, message: str) -> bool:
    api_key = current_app.config.get("SMS_API_KEY", "")
    sender = current_app.config.get("SMS_SENDER", "Kangaroo")
    if not api_key:
        current_app.logger.error("SMS_API_KEY not configured")
        return False
    try:
        from twilio.rest import Client

        account_sid, auth_token = api_key.split(":", 1)
        client = Client(account_sid, auth_token)
        client.messages.create(body=message, from_=sender, to=f"+{phone}")
        return True
    except Exception:
        current_app.logger.exception("Twilio SMS failed")
        return False
