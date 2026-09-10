from __future__ import annotations

from urllib.parse import urlparse

from .i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES

# Public URL segment for each locale (`kk` is exposed as `/kz`).
LOCALE_URL_SEGMENTS: dict[str, str] = {
    "ru": "ru",
    "en": "en",
    "kk": "kz",
}
URL_SEGMENT_TO_LOCALE: dict[str, str] = {
    segment: locale for locale, segment in LOCALE_URL_SEGMENTS.items()
}
URL_SEGMENT_TO_LOCALE["kk"] = "kk"
LOCALE_EXEMPT_PREFIXES = (
    "/admin",
    "/static",
    "/uploads",
    "/investor",
    "/service-worker.js",
    "/offline",
)


def locale_url_segment(locale: str | None = None) -> str:
    from .i18n import resolve_locale

    code = resolve_locale(locale)
    return LOCALE_URL_SEGMENTS.get(code, LOCALE_URL_SEGMENTS[DEFAULT_LOCALE])


def locale_from_segment(segment: str | None) -> str | None:
    if not segment:
        return None
    key = segment.strip().lower()
    if key in URL_SEGMENT_TO_LOCALE:
        return URL_SEGMENT_TO_LOCALE[key]
    if key in SUPPORTED_LOCALES:
        return key
    return None


def strip_locale_prefix(path: str) -> str:
    clean = (path or "/").split("?", 1)[0].split("#", 1)[0] or "/"
    if not clean.startswith("/"):
        clean = f"/{clean}"
    parts = clean.lstrip("/").split("/", 1)
    if parts and parts[0].lower() in URL_SEGMENT_TO_LOCALE:
        tail = parts[1] if len(parts) > 1 else ""
        return f"/{tail}" if tail else "/"
    return clean


def is_locale_exempt_path(path: str) -> bool:
    clean = strip_locale_prefix(path)
    if clean in {"/service-worker.js", "/offline"}:
        return True
    return any(clean.startswith(prefix) for prefix in LOCALE_EXEMPT_PREFIXES)


def is_locale_exempt_endpoint(endpoint: str | None, url: str) -> bool:
    if not endpoint:
        return is_locale_exempt_path(url)
    if endpoint.startswith("admin.") or endpoint.startswith("static."):
        return True
    return is_locale_exempt_path(url)


def path_with_locale(
    path: str,
    locale: str | None = None,
    *,
    query_string: str = "",
    hash_fragment: str = "",
) -> str:
    segment = locale_url_segment(locale)
    base = strip_locale_prefix(path)
    if base != "/" and base.endswith("/"):
        base = base.rstrip("/")
    localized = f"/{segment}" if base == "/" else f"/{segment}{base}"
    if query_string:
        localized = f"{localized}?{query_string.lstrip('?')}"
    if hash_fragment:
        localized = f"{localized}#{hash_fragment.lstrip('#')}"
    return localized


def localize_existing_path(path: str, locale: str | None = None) -> str:
    if not path:
        return path_with_locale("/", locale)
    parsed = urlparse(path)
    if parsed.scheme or parsed.netloc:
        return path
    base = parsed.path or "/"
    query = parsed.query
    fragment = parsed.fragment
    rebuilt = path_with_locale(base, locale, query_string=query, hash_fragment=fragment)
    return rebuilt


def apply_locale_from_environ(environ: dict) -> tuple[str | None, str | None]:
    path = environ.get("PATH_INFO", "") or "/"
    parts = path.lstrip("/").split("/", 1)
    first = parts[0].lower() if parts and parts[0] else ""
    locale = locale_from_segment(first)
    if not locale:
        return None, None
    segment = "kz" if locale == "kk" else locale
    environ["PATH_INFO"] = "/" + parts[1] if len(parts) > 1 else "/"
    environ["kangaroo.locale"] = locale
    environ["kangaroo.locale_segment"] = segment
    return locale, segment


def localized_url_for(
    endpoint: str,
    *,
    _external: bool = False,
    locale: str | None = None,
    **values,
) -> str:
    from flask import g, url_for as flask_url_for

    url = flask_url_for(endpoint, _external=_external, **values)
    if _external or is_locale_exempt_endpoint(endpoint, url):
        return url
    segment = locale_url_segment(locale) if locale else (
        getattr(g, "locale_segment", None) or locale_url_segment()
    )
    if url == f"/{segment}" or url.startswith(f"/{segment}/"):
        return url
    return f"/{segment}{url}"


class LocalePrefixMiddleware:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        apply_locale_from_environ(environ)
        return self.wsgi_app(environ, start_response)
