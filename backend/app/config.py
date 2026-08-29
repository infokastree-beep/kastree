"""Pydantic Settings and environment variables. Implementation pending."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+asyncpg://findraft:local@localhost/findraft_dev"
    database_url_sync: str = "postgresql://findraft:local@localhost/findraft_dev"

    class Config:
        env_file = ".env"


settings = Settings()
