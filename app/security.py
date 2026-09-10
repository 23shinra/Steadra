"""Small security helpers: session rotation, path checks, response headers."""

from __future__ import annotations

import hmac
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, abort, send_from_directory, session

_SECRET_RE = re.compile(
    r"(?i)(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9\-_\.=]+|"
    r"(?:OPENAI_API_KEY|OTP_API_TOKEN|TASK_TOKEN|SECRET_KEY|VAPID_PRIVATE_KEY)"
    r"\s*[:=]\s*\S+)"
)


def redact_secrets(text: str) -> str:
    return _SECRET_RE.sub("[redacted]", text)


class RedactSecretsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: redact_secrets(value) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(arg) if isinstance(arg, str) else arg for arg in record.args
                )
        if record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)
        return True


class _RedactingFormatter(logging.Formatter):
    def __init__(self, wrapped: logging.Formatter):
        super().__init__()
        self._wrapped = wrapped

    def format(self, record: logging.LogRecord) -> str:
        return redact_secrets(self._wrapped.format(record))


class PublicConfig:
    """Template-safe config: only values that may appear in HTML."""

    def __init__(self, data: dict[str, object]):
        self._data = data

    def __getattr__(self, name: str) -> object:
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __getitem__(self, name: str) -> object:
        return self._data[name]

    def get(self, name: str, default: object = None) -> object:
        return self._data.get(name, default)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()


def install_safe_jinja_config(app: Flask) -> None:
    public = PublicConfig({"ASSET_VERSION": app.config.get("ASSET_VERSION", "")})
    app.jinja_env.globals["config"] = public

    @app.context_processor
    def _public_config():
        return {"config": public}


def install_log_redaction(app: Flask) -> None:
    filt = RedactSecretsFilter()
    logging.getLogger().addFilter(filt)
    app.logger.addFilter(filt)
    for name in ("gunicorn.error", "gunicorn.access", "openai", "httpx", "httpcore"):
        logging.getLogger(name).addFilter(filt)
    for handler in logging.getLogger().handlers + app.logger.handlers:
        handler.addFilter(filt)
        formatter = handler.formatter
        if formatter and not isinstance(formatter, _RedactingFormatter):
            handler.setFormatter(_RedactingFormatter(formatter))


def rotate_session(**keep: object) -> None:
    """Drop session fixation tokens; keep only explicitly passed keys."""
    session.clear()
    for key, value in keep.items():
        if value is not None:
            session[key] = value
    session.modified = True


def tokens_match(expected: str, provided: str) -> bool:
    if not expected or not provided:
        return False
    left = str(expected)
    right = str(provided)
    if len(left) != len(right):
        return False
    return hmac.compare_digest(left, right)


def path_is_under(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def send_contained_file(root: Path, target: Path, download_name: str | None = None) -> Response:
    if not path_is_under(root, target) or not target.is_file():
        abort(404)
    response = send_from_directory(
        target.parent,
        target.name,
        as_attachment=True,
        download_name=download_name or target.name,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


def safe_internal_path(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url.startswith("/") or url.startswith("//") or "\\" in url:
        return None
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        return None
    return url


def install_security_headers(app: Flask) -> None:
    @app.after_request
    def _security_headers(response: Response) -> Response:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if session.get("user_id") or session.get("admin"):
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type:
                response.headers["Cache-Control"] = "private, no-store"
        return response
