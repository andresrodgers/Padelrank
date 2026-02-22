from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    ENV: str = "prod"
    
    MAX_SCORE_PROPOSALS: int = 2

    DATABASE_URL: str

    JWT_SECRET: str
    JWT_ACCESS_MINUTES: int = 60
    JWT_REFRESH_DAYS: int = 30

    OTP_TTL_MINUTES: int = 10
    OTP_PEPPER: str = "CHANGE_ME"
    OTP_REQUEST_COOLDOWN_SECONDS: int = 120
    AUTH_OTP_RETENTION_DAYS: int = 30
    AUTH_LOGIN_ATTEMPTS_RETENTION_DAYS: int = 30
    USER_CONTACT_CHANGES_RETENTION_DAYS: int = 30

    CONFIRM_WINDOW_HOURS: int = 48

    PROVISIONAL_MATCHES: int = 5
    PROVISIONAL_CAP: int = 30

    ELO_K: int = 32

    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800

    API_WORKERS: int = 2
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    SECURITY_HEADERS_ENABLED: bool = True

    # Rivio foundations
    SUPPORT_CONTACT_EMAIL: str = "soporte@rivio.app"
    SUPPORT_TICKETS_ENABLED: bool = True
    SUPPORT_MAX_TICKETS_PER_DAY: int = 5
    SUPPORT_MIN_SECONDS_BETWEEN_TICKETS: int = 60

    ACCOUNT_DELETION_GRACE_DAYS: int = 7

    AVATAR_UPLOAD_ENABLED: bool = False
    AVATAR_UPLOAD_MAX_SIZE_MB: int = 5
    AVATAR_UPLOAD_ALLOWED_EXT: str = "jpg,jpeg,png,webp"
    AVATAR_UPLOAD_ALLOWED_HOSTS: str = ""

    # Billing scaffold (provider-agnostic)
    BILLING_PROVIDER: str = "none"  # none|stripe|app_store|google_play|manual
    BILLING_WEBHOOK_SECRET: str | None = None
    BILLING_REQUIRE_WEBHOOK_SIGNATURE: bool = False
    BILLING_WEBHOOK_MAX_AGE_SECONDS: int = 300
    BILLING_WEBHOOK_STRIPE_SECRET: str | None = None
    BILLING_WEBHOOK_APP_STORE_SECRET: str | None = None
    BILLING_WEBHOOK_GOOGLE_PLAY_SECRET: str | None = None
    BILLING_PLUS_PLAN_CODE: str = "RIVIO_PLUS"
    BILLING_CHECKOUT_SUCCESS_URL: str = "https://rivio.app/billing/success"
    BILLING_CHECKOUT_CANCEL_URL: str = "https://rivio.app/billing/cancel"
    BILLING_PRODUCT_PLAN_MAP: str = ""

    # App Store Server-side validation (legacy verifyReceipt flow)
    APP_STORE_SHARED_SECRET: str | None = None
    APP_STORE_VERIFY_URL_PROD: str = "https://buy.itunes.apple.com/verifyReceipt"
    APP_STORE_VERIFY_URL_SANDBOX: str = "https://sandbox.itunes.apple.com/verifyReceipt"

    # Google Play Server-side validation (Play Developer API)
    GOOGLE_PLAY_PACKAGE_NAME: str | None = None
    GOOGLE_PLAY_SERVICE_ACCOUNT_EMAIL: str | None = None
    GOOGLE_PLAY_SERVICE_ACCOUNT_PRIVATE_KEY_PEM: str | None = None
    GOOGLE_PLAY_TOKEN_URI: str = "https://oauth2.googleapis.com/token"
    GOOGLE_PLAY_ANDROID_PUBLISHER_SCOPE: str = "https://www.googleapis.com/auth/androidpublisher"

settings = Settings()
