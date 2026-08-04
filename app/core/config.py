

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    environment: str = "development"


# Instantiated once at import time and reused everywhere (a singleton).
# Creating Settings() is cheap but re-parsing env vars on every request
# would be wasteful and could theoretically see a value change mid-request.
settings = Settings()
