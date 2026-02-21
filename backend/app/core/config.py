from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    ENV: str = "dev"
    
    MAX_SCORE_PROPOSALS: int = 2

    DATABASE_URL: str

    JWT_SECRET: str
    JWT_ACCESS_MINUTES: int = 60
    JWT_REFRESH_DAYS: int = 30

    OTP_TTL_MINUTES: int = 10
    OTP_PEPPER: str = "CHANGE_ME"
    OTP_REQUEST_COOLDOWN_SECONDS: int = 120

    CONFIRM_WINDOW_HOURS: int = 48

    PROVISIONAL_MATCHES: int = 5
    PROVISIONAL_CAP: int = 30

    ELO_K: int = 32

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT_SECONDS: int = 30
    DB_POOL_RECYCLE_SECONDS: int = 1800

    API_WORKERS: int = 4
    ALLOWED_HOSTS: str = "localhost,127.0.0.1"
    SECURITY_HEADERS_ENABLED: bool = True

settings = Settings()
