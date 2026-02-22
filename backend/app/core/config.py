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
    BILLING_PLUS_PLAN_CODE: str = "RIVIO_PLUS"
    BILLING_CHECKOUT_SUCCESS_URL: str = "https://rivio.app/billing/success"
    BILLING_CHECKOUT_CANCEL_URL: str = "https://rivio.app/billing/cancel"

settings = Settings()
