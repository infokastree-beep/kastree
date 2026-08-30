"""Pydantic Settings and environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+asyncpg://findraft:local@localhost/findraft_dev"
    database_url_sync: str = "postgresql://findraft:local@localhost/findraft_dev"

    # Clerk — JWT verification (HS256 local/test secret; production uses Clerk JWKS).
    clerk_secret_key: str | None = None
    clerk_publishable_key: str | None = None
    clerk_webhook_secret: str | None = None
    # Shared HS256 secret for issuing/verifying Bearer tokens in tests and local MVP.
    auth_jwt_secret: str = "findraft-dev-jwt-secret-change-me"
    auth_jwt_algorithm: str = "HS256"

    # Local upload storage until S3 wiring for TB files lands with export storage.
    upload_dir: str = "/tmp/findraft-uploads"

    # Object storage (S3 or R2). 30-day export deletion requires bucket lifecycle
    # via scripts/configure_s3_lifecycle.py — not put_object(Expires=...).
    s3_bucket: str = "findraft-uploads-dev"
    s3_region: str = "eu-west-1"
    s3_endpoint_url: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    export_file_ttl_days: int = 30
    export_signed_url_ttl_seconds: int = 3600

    class Config:
        env_file = ".env"


settings = Settings()
