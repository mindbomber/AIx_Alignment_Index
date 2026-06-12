from __future__ import annotations

from functools import lru_cache

from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


DEVELOPMENT_TOKEN_PEPPER = "development-only-change-me"  # nosec B105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIX_",
        env_file=".env",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = "sqlite:///./aix-platform.db"
    token_pepper: str = Field(default=DEVELOPMENT_TOKEN_PEPPER, min_length=16)
    token_ttl_minutes: int = Field(default=480, ge=5, le=43200)
    session_idle_minutes: int = Field(default=60, ge=5, le=1440)
    session_touch_interval_seconds: int = Field(default=300, ge=30, le=3600)
    max_sessions_per_user: int = Field(default=10, ge=1, le=100)
    api_key_ttl_days: int = Field(default=365, ge=1, le=3650)
    cors_origins: str = "http://localhost:5173"
    auto_create_schema: bool = False
    public_base_url: str = "http://localhost:8000"
    storage_backend: str = "local"
    storage_path: Path = Path("./data/evidence")
    storage_max_bytes: int = Field(default=25 * 1024 * 1024, ge=1024)
    malware_scan_enabled: bool = False
    malware_scan_backend: str = "command"
    malware_scan_command: str = "clamscan"
    malware_scan_host: str = "127.0.0.1"
    malware_scan_port: int = Field(default=3310, ge=1, le=65535)
    malware_scan_timeout_seconds: int = Field(default=60, ge=1, le=600)
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    s3_server_side_encryption: str = "AES256"
    s3_kms_key_id: str | None = None
    redis_url: str | None = None
    job_queue_name: str = "aix:jobs"
    job_retry_base_seconds: int = Field(default=5, ge=1, le=3600)
    rate_limit_enabled: bool = True
    rate_limit_requests: int = Field(default=120, ge=1)
    rate_limit_window_seconds: int = Field(default=60, ge=1)
    request_max_bytes: int = Field(default=2 * 1024 * 1024, ge=1024)
    evidence_retention_days: int = Field(default=365, ge=1, le=3650)
    webhook_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    webhook_secret_pepper: SecretStr = SecretStr("development-webhook-pepper")
    privacy_deletion_delay_hours: int = Field(default=24, ge=1, le=720)
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_redirect_uri: str | None = None
    oidc_web_app_url: str | None = None
    oidc_auto_provision: bool = False
    oidc_default_role: str = "viewer"
    oidc_role_claim: str = "aix_role"
    otlp_endpoint: str | None = None
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]

    @model_validator(mode="after")
    def validate_deployment(self) -> "Settings":
        if self.storage_backend not in {"local", "s3"}:
            raise ValueError("storage_backend must be local or s3")
        if self.malware_scan_backend not in {"command", "clamd"}:
            raise ValueError("malware_scan_backend must be command or clamd")
        if self.storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("s3_bucket is required when storage_backend=s3")
        if self.s3_server_side_encryption == "aws:kms" and not self.s3_kms_key_id:
            raise ValueError(
                "s3_kms_key_id is required when s3_server_side_encryption=aws:kms"
            )
        if self.environment == "production":
            if self.token_pepper == DEVELOPMENT_TOKEN_PEPPER:
                raise ValueError("AIX_TOKEN_PEPPER must be changed in production")
            if self.webhook_secret_pepper.get_secret_value() == "development-webhook-pepper":
                raise ValueError(
                    "AIX_WEBHOOK_SECRET_PEPPER must be changed in production"
                )
            if self.storage_backend == "local":
                raise ValueError("Production deployments require S3 object storage")
            if not self.redis_url:
                raise ValueError("Production deployments require AIX_REDIS_URL")
            if not self.malware_scan_enabled:
                raise ValueError("Production deployments require malware scanning")
        oidc_values = (
            self.oidc_issuer,
            self.oidc_client_id,
            self.oidc_client_secret,
            self.oidc_redirect_uri,
        )
        if any(oidc_values) and not all(oidc_values):
            raise ValueError(
                "OIDC requires issuer, client id, client secret, and redirect URI"
            )
        if (
            self.environment == "production"
            and self.oidc_web_app_url
            and not self.oidc_web_app_url.startswith("https://")
        ):
            raise ValueError("Production OIDC web app URL must use HTTPS")
        if self.oidc_default_role not in {
            "owner",
            "admin",
            "assessor",
            "reviewer",
            "approver",
            "viewer",
        }:
            raise ValueError("Invalid oidc_default_role")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
