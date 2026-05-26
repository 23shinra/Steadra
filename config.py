import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "kangaroo-dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///kangaroo.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_TIME_LIMIT = None
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024
    PROFILE_NAME_CONFIRM_CODE = os.environ.get("PROFILE_NAME_CONFIRM_CODE", "1234")
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "79999999999")
    ASSET_VERSION = os.environ.get("ASSET_VERSION", "61")
    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
    VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "mailto:admin@kangaroo.kz")

    # SMS / OTP
    SMS_PROVIDER = os.environ.get("SMS_PROVIDER", "mock")
    SMS_API_KEY = os.environ.get("SMS_API_KEY", "")
    SMS_SENDER = os.environ.get("SMS_SENDER", "Kangaroo")
    OTP_TTL_SECONDS = int(os.environ.get("OTP_TTL_SECONDS", "300"))
    OTP_LENGTH = int(os.environ.get("OTP_LENGTH", "4"))
    OTP_DEMO_CODE = os.environ.get("OTP_DEMO_CODE", "")

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
