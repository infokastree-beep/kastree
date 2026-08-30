"""Pydantic Settings and environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+asyncpg://findraft:local@localhost/findraft_dev"
    database_url_sync: str = "postgresql://findraft:local@localhost/findraft_dev"

    # Clerk — production/request auth verifies session JWTs via JWKS (RS256 only).
    clerk_secret_key: str | None = None
    clerk_publishable_key: str | None = None
    clerk_webhook_secret: str | None = None
    # JWKS URL for Clerk RS256. When unset, derived from clerk_publishable_key.
    clerk_jwks_url: str | None = None
    # HS256 secret used ONLY by pytest (decode_test_hs256_token / make_access_token).
    # Never accepted by the live request auth path (decode_clerk_rs256_token).
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

    # Stripe billing (§4.5). Webhook signature verification uses stripe_webhook_secret.
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_id_starter: str | None = None
    stripe_price_id_pro: str | None = None
    stripe_price_id_scale: str | None = None

    class Config:
        env_file = ".env"


settings = Settings()
