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

    # Browser CORS — frontend origin(s) only (Product Spec §12 / Cursor Rules).
    # Comma-separated list, e.g. "http://127.0.0.1:43123,http://localhost:43123"
    cors_origins: str = "http://127.0.0.1:43123,http://localhost:43123"

    # Trial balance upload storage (local path). Override with UPLOAD_DIR env var —
    # e.g. mount a Railway volume at /data/uploads and set UPLOAD_DIR=/data/uploads.
    # S3 for TB files is a tracked gap; exports already use S3 below.
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

    # Public POST /waitlist — per-IP cap (in-memory, process-local).
    waitlist_rate_limit_per_ip_per_hour: int = 10

    # Resend — waitlist confirmation + founder notification emails (optional).
    resend_api_key: str | None = None
    # Verified sender in Resend (e.g. "Kastree <hello@kastree.ie>").
    # Defaults to Resend's onboarding address until your domain is verified.
    resend_from_email: str = "Kastree <onboarding@resend.dev>"
    # Founder inbox for new waitlist / signup alerts (optional; skip if unset).
    founder_notification_email: str | None = None

    # Platform admin allowlist — comma-separated emails permitted to access /admin
    # in addition to require_roles("owner"). Example: mark@example.com,other@example.com
    platform_admin_emails: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
