"""Configuration management for Kibotos."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    database_url: str = Field(
        default="postgresql+asyncpg://kibotos:secret@localhost:5432/kibotos",
        alias="DATABASE_URL",
    )


class S3Settings(BaseSettings):
    """S3 storage configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    s3_bucket: str = Field(default="kibotos-videos", alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    aws_access_key_id: str | None = Field(default=None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = Field(default=None, alias="AWS_SECRET_ACCESS_KEY")

    @property
    def upload_expiration(self) -> int:
        """Presigned URL expiration in seconds (1 hour)."""
        return 3600


class VLMSettings(BaseSettings):
    """VLM API configuration."""

    model_config = SettingsConfigDict(env_prefix="VLM_")

    api_url: str = Field(default="https://llm.chutes.ai/v1")
    api_key: str | None = Field(default=None)
    model: str = Field(default="Qwen/Qwen2.5-VL-72B-Instruct-TEE")


class BittensorSettings(BaseSettings):
    """Bittensor chain configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    netuid: int | None = Field(default=None, alias="NETUID")
    network: str = Field(default="test", alias="NETWORK")
    wallet_name: str = Field(default="default", alias="WALLET_NAME")
    hotkey_name: str = Field(default="default", alias="HOTKEY_NAME")


class APISettings(BaseSettings):
    """API server configuration."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)


class SchedulerSettings(BaseSettings):
    """Scheduler configuration."""

    model_config = SettingsConfigDict(env_prefix="")

    cycle_duration_minutes: int = Field(default=60, alias="CYCLE_DURATION_MINUTES")
    prompts_per_cycle: int = Field(default=50, alias="PROMPTS_PER_CYCLE")
    max_submissions_per_hour: int = Field(default=4, alias="MAX_SUBMISSIONS_PER_HOUR")


class Settings(BaseSettings):
    """Combined settings for all components."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-settings
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    vlm: VLMSettings = Field(default_factory=VLMSettings)
    bittensor: BittensorSettings = Field(default_factory=BittensorSettings)
    api: APISettings = Field(default_factory=APISettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
