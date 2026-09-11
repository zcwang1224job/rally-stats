"""Application settings, loaded from environment variables (.env in local dev)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    jwt_secret: str
    turnstile_site_key: str
    turnstile_secret_key: str
    password_encryption_key: str
    ably_api_key: str

    # Comma-separated list of origins allowed to call the API directly
    # (bypassing the frontend's Nginx /api proxy). Needed for LAN access
    # only if something calls the backend's published port directly from a
    # browser on another host — the proxied SPA traffic is same-origin and
    # unaffected by this setting.
    cors_allowed_origins: str = "http://localhost:4200"

    admin_pin_max_attempts: int = 10
    admin_pin_lockout_minutes: int = 15
    admin_token_ttl_hours: int = 4
    auto_disband_idle_minutes: int = 60
    turnstile_timeout_seconds: float = 4.0

    # specs/006-member-friends
    frontend_base_url: str = "http://localhost:4200"
    email_backend: Literal["ses", "log"] = "log"
    ses_region: str = "us-east-1"
    ses_from_address: str = "no-reply@rally-stats.example.com"
    member_access_token_ttl_minutes: int = 60
    member_refresh_token_ttl_days: int = 30

    # Production's CloudFront distribution has custom error responses
    # (403/404 -> /index.html, needed for Angular client-side routes that
    # 403 straight from the S3 origin) configured distribution-wide, not
    # scoped to a path pattern — so it also swallows the API's own
    # legitimate 403/404 JSON error bodies. Off by default (local dev/tests
    # never sit behind that CloudFront distribution); set to true via the
    # ECS task definition's environment for the production API only. See
    # app.core.errors.CloudFrontSafeStatusMiddleware.
    remap_403_404_for_cloudfront: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
