import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "kangaroo-dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///kangaroo.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "1") != "0"
    WTF_CSRF_TIME_LIMIT = None
    # Chat video attach allows up to 50 MB (see video_attach.MAX_VIDEO_BYTES).
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", str(50 * 1024 * 1024)))
    # Empty by default — set explicitly in env for local/dev bypass only.
    PROFILE_NAME_CONFIRM_CODE = os.environ.get("PROFILE_NAME_CONFIRM_CODE", "")
    # Demo OTP login (/login/demo) — off in production unless ALLOW_DEMO_LOGIN=1.
    ALLOW_DEMO_LOGIN = os.environ.get("ALLOW_DEMO_LOGIN", "0") == "1"
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    # Stronger vision for photo/video attach; falls back to OPENAI_MODEL if unset.
    OPENAI_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")
    ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "")
    ASSET_VERSION = os.environ.get("ASSET_VERSION", "205")

    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
    VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@kangaroo.kz")
    TASK_TOKEN = os.environ.get("TASK_TOKEN", "")

    # SMS / OTP
    SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "mock")
    SMS_API_KEY = os.environ.get("SMS_API_KEY", "")
    SMS_SENDER = os.environ.get("SMS_SENDER", "Kangaroo")
    OTP_TTL_SECONDS = int(os.environ.get("OTP_TTL_SECONDS", "300"))
    OTP_LENGTH = int(os.environ.get("OTP_LENGTH", "4"))
    OTP_DEMO_CODE = os.environ.get("OTP_DEMO_CODE", "")

    # Cascade OTP (https://otp.kztusdt.kz) — primary when OTP_API_TOKEN set
    OTP_API_BASE_URL = os.environ.get("OTP_API_BASE_URL", "https://cascade.kz/api")
    OTP_API_TOKEN = os.environ.get("OTP_API_TOKEN", "")
    OTP_PROVIDER = os.environ.get("OTP_PROVIDER", "cascade")  # cascade | mock
    OTP_CHANNEL = os.environ.get("OTP_CHANNEL", "")  # empty = cabinet default
    OTP_PURPOSE_LOGIN = os.environ.get("OTP_PURPOSE_LOGIN", "login")
    OTP_SEND_LIMIT_PHONE = int(os.environ.get("OTP_SEND_LIMIT_PHONE", "5"))
    OTP_SEND_WINDOW_SECONDS = int(os.environ.get("OTP_SEND_WINDOW_SECONDS", "3600"))
    OTP_SEND_LIMIT_IP = int(os.environ.get("OTP_SEND_LIMIT_IP", "15"))
    OTP_SEND_IP_WINDOW_SECONDS = int(os.environ.get("OTP_SEND_IP_WINDOW_SECONDS", "3600"))
    OTP_VERIFY_LIMIT_PHONE = int(os.environ.get("OTP_VERIFY_LIMIT_PHONE", "10"))
    OTP_VERIFY_WINDOW_SECONDS = int(os.environ.get("OTP_VERIFY_WINDOW_SECONDS", "900"))

    # Redis
    REDIS_URL = os.environ.get("REDIS_URL", "")

    # AI limits (freemium)
    AI_FREE_MONTHLY_LIMIT = int(os.environ.get("AI_FREE_MONTHLY_LIMIT", "30"))
    AI_PREMIUM_MONTHLY_LIMIT = int(os.environ.get("AI_PREMIUM_MONTHLY_LIMIT", "9999"))

    # Investor invite codes (comma-separated)
    INVESTOR_INVITE_CODES = os.environ.get("INVESTOR_INVITE_CODES", "INVEST2026")

    # Analytics
    ANALYTICS_ENABLED = os.environ.get("ANALYTICS_ENABLED", "1") == "1"

    # i18n
    BABEL_DEFAULT_LOCALE = "ru"
    BABEL_SUPPORTED_LOCALES = ["ru", "kk", "en"]
    LANGUAGES = {"ru": "Русский", "kk": "Қазақша", "en": "English"}

    # Uploads
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")
    DOCUMENTS_FOLDER = os.environ.get("DOCUMENTS_FOLDER", "uploads/documents")
