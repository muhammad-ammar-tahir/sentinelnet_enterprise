"""Configuration Management for SentinelNet Backend.

Loads environment variables, defines runtime settings via pydantic-settings,
and exposes strongly-typed configuration objects.

JWT_SECRET policy
-----------------
* Always read from the ``JWT_SECRET`` environment variable (or .env file).
* In *production* (ENVIRONMENT=production):
  - Missing value  → RuntimeError at startup.
  - Value < 32 chars → RuntimeError at startup.
  - Value matches any known-default string → RuntimeError at startup.
* In *development* (any other ENVIRONMENT):
  - If the variable is absent or matches a known default, a loud WARNING is
    logged but startup continues with the dev-only placeholder.
"""

import logging
import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known-weak / placeholder JWT secrets that must never reach production.
# ---------------------------------------------------------------------------
_KNOWN_DEFAULT_SECRETS: set[str] = {
    "sentinelnet-super-secure-production-jwt-secret-key-2026",
    "change-me-to-a-256-bit-secret-key",
    "secret",
    "changeme",
    "your-secret-key",
    "dev-secret",
    "development-secret",
}

_DEV_FALLBACK_SECRET: str = "dev-only-insecure-jwt-secret-not-for-production"


class Settings(BaseSettings):
    """Application settings and configuration parameters."""

    # Project metadata
    PROJECT_NAME: str = "SentinelNet AI Self-Healing Network"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = Field(default=False, description="Debug mode flag")
    ENVIRONMENT: str = Field(default="development", description="Runtime environment (development|staging|production)")

    # Server configuration
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173", "*"]

    # Database & Cache
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/sentinelnet",
        description="Async PostgreSQL connection string (must use postgresql+asyncpg://)"
    )
    DATABASE_URL_SYNC: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/sentinelnet",
        description="Synchronous PostgreSQL connection string for Alembic"
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis cache/queue connection")

    # Security & Authentication
    # NO hardcoded default — read from environment only.
    # Validation logic runs in _validate_jwt_secret() after model construction.
    JWT_SECRET: str = Field(
        default="",
        description=(
            "Secret key for JWT signing. "
            "Must be set via JWT_SECRET env var. "
            "In production: ≥32 chars, not a known default. "
            "In development: defaults to an insecure placeholder with a loud warning."
        )
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SERVICE_API_KEY: str = Field(
        default="sentinelnet-internal-service-key-2026",
        description="Internal service API key for background telemetry and automated tasks"
    )
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="Comma-separated allowed CORS origins"
    )

    # SDN Controller (Ryu REST API)
    RYU_BASE_URL: str = Field(default="http://localhost:8080", description="Ryu REST OpenFlow controller base URL")
    RYU_TIMEOUT_SECONDS: float = 5.0
    CONTROLLER_POLL_INTERVAL: float = 2.0

    # Prometheus & Observability
    PROMETHEUS_URL: str = Field(default="http://localhost:9090", description="Prometheus server base URL")
    METRICS_SCRAPE_INTERVAL: int = 5
    MONITORING_INTERVAL_SECONDS: int = Field(default=5, description="Interval in seconds between telemetry monitoring loops")

    # AI & ML Model Parameters
    ISOLATION_FOREST_CONTAMINATION: float = 0.05
    ANOMALY_THRESHOLD: float = 0.75
    MODEL_STORAGE_PATH: str = "./models"
    SLIDING_WINDOW_SIZE: int = 30

    # Recovery Engine Thresholds
    PACKET_LOSS_CRITICAL_PERCENT: float = 5.0
    LATENCY_CRITICAL_MS: float = 50.0
    CONGESTION_BANDWIDTH_PERCENT: float = 85.0
    AUTO_RECOVERY_ENABLED: bool = True
    MAX_RECOVERY_ATTEMPTS: int = 3
    VERIFICATION_WINDOW_SECONDS: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


def _validate_jwt_secret(settings_obj: Settings) -> Settings:
    """Enforce JWT_SECRET policy at startup.

    Mutates settings_obj.JWT_SECRET in development (applies dev fallback).
    Raises RuntimeError in production when the secret is missing or weak.
    """
    secret = settings_obj.JWT_SECRET
    is_production = settings_obj.ENVIRONMENT.lower() == "production"

    missing = not secret or secret.strip() == ""
    too_short = len(secret) < 32
    is_known_default = secret in _KNOWN_DEFAULT_SECRETS

    if is_production:
        # Hard failures — crash loudly before accepting any traffic.
        if missing:
            raise RuntimeError(
                "[STARTUP FATAL] JWT_SECRET environment variable is not set. "
                "Set a cryptographically random secret of ≥32 characters in production. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if too_short:
            raise RuntimeError(
                f"[STARTUP FATAL] JWT_SECRET is only {len(secret)} characters. "
                "Production requires ≥32 characters. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if is_known_default:
            raise RuntimeError(
                "[STARTUP FATAL] JWT_SECRET matches a known insecure default value. "
                "Replace it with a cryptographically random secret. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
    else:
        # Development / staging — warn loudly but continue.
        if missing or is_known_default:
            logger.warning(
                "⚠️  WARNING: JWT_SECRET is %s. "
                "Using insecure development placeholder. "
                "Set JWT_SECRET in your .env file before deploying to production. "
                "Generate a strong key with: python -c \"import secrets; print(secrets.token_hex(32))\"",
                "not set" if missing else "a known default value",
            )
            # Apply dev-only fallback so the app can still run.
            object.__setattr__(settings_obj, "JWT_SECRET", _DEV_FALLBACK_SECRET)
        elif too_short:
            logger.warning(
                "⚠️  WARNING: JWT_SECRET is only %d characters (minimum 32 recommended for security). "
                "This is acceptable in development but must be fixed before production.",
                len(secret),
            )

    return settings_obj


settings = _validate_jwt_secret(Settings())
logger.info("SentinelNet settings successfully loaded [Env: %s]", settings.ENVIRONMENT)
