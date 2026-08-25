from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "TradoVera API"
    API_V1_STR: str = "/api/v1"

    # Environment variables overrides
    DATABASE_URL: str = "postgresql://postgres:password@db:5432/tradovera"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "supersecretjwtkeyforlocaldevelopment123!"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    model_config = ConfigDict(case_sensitive=True)


settings = Settings()
