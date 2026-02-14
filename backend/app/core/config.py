from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    ENV: str = "dev"

    DATABASE_URL: str

    JWT_SECRET: str
    JWT_ACCESS_MINUTES: int = 60
    JWT_REFRESH_DAYS: int = 30

    OTP_TTL_MINUTES: int = 10
    OTP_PEPPER: str = "CHANGE_ME"

    CONFIRM_WINDOW_HOURS: int = 48

    PROVISIONAL_MATCHES: int = 5
    PROVISIONAL_CAP: int = 30

    ELO_K: int = 32

settings = Settings()
