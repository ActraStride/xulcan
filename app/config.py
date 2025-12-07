"""Application configuration management via pydantic-settings.

Centralize all configuration parameters for the Xulcan project. Load settings from
environment variables and/or a `.env` file. Provide type validation, default values,
and dynamic construction of sensitive connection strings (DSNs).
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import (
    PostgresDsn,
    RedisDsn,
    SecretStr,
    ValidationInfo,
    computed_field,
    field_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration settings.

    Attributes:
        PROJECT_NAME: Display name for the application.
        VERSION: Semantic version string.
        ENVIRONMENT: Deployment environment identifier.
        LOG_LEVEL: Minimum logging verbosity level.
        API_V1_STR: Base path prefix for API v1 endpoints.
        SECRET_KEY: Cryptographic key for signing tokens and sessions.
        POSTGRES_USER: PostgreSQL database user.
        POSTGRES_SERVER: PostgreSQL server hostname.
        POSTGRES_DB: PostgreSQL database name.
        POSTGRES_PORT: PostgreSQL server port.
        POSTGRES_PASSWORD_FILE: Path to Docker secret containing the password.
        POSTGRES_PASSWORD: Environment variable fallback for the password.
        REDIS_HOST: Redis server hostname.
        REDIS_PORT: Redis server port.
        REDIS_PASSWORD_FILE: Path to Docker secret containing the password.
        REDIS_PASSWORD: Environment variable fallback for the password.
        OPENAI_API_KEY: API key for OpenAI services.
        GEMINI_API_KEY: API key for Google Gemini services.
        ANTHROPIC_API_KEY: API key for Anthropic services.
    """

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        case_sensitive=True,
        extra="ignore"
    )

    # ==========================================================================
    # PROJECT METADATA
    # ==========================================================================
    PROJECT_NAME: str = "Xulcan"
    VERSION: str = "0.1.0"

    # ==========================================================================
    # ENVIRONMENT & LOGGING
    # ==========================================================================
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    LOG_LEVEL: Literal["debug", "info", "warning", "error", "critical"] = "info"
    LOGGING_NOISY_MODULES: list[str] = [
        "uvicorn.access",
        "uvicorn.error",
        "httpx",
        "httpcore",
        "asyncio",
    ]

    # ==========================================================================
    # SECURITY
    # ==========================================================================
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: SecretStr = SecretStr("changeme_in_production")

    # ==========================================================================
    # POSTGRESQL CONFIGURATION
    # ==========================================================================
    # Password resolution priority: FILE (Docker Secret) > ENV VAR > None
    POSTGRES_USER: str = "xulcan"
    POSTGRES_SERVER: str = "postgres"
    POSTGRES_DB: str = "xulcan_db"
    POSTGRES_PORT: int = 5432
    POSTGRES_PASSWORD_FILE: Optional[str] = None
    POSTGRES_PASSWORD: Optional[SecretStr] = None

    # ==========================================================================
    # REDIS CONFIGURATION
    # ==========================================================================
    # Password resolution priority: FILE (Docker Secret) > ENV VAR > None
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD_FILE: Optional[str] = None
    REDIS_PASSWORD: Optional[SecretStr] = None

    # ==========================================================================
    # LLM PROVIDER API KEYS
    # ==========================================================================
    OPENAI_API_KEY: Optional[SecretStr] = None
    GEMINI_API_KEY: Optional[SecretStr] = None
    ANTHROPIC_API_KEY: Optional[SecretStr] = None

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: SecretStr, info: ValidationInfo) -> SecretStr:
        """Validate that SECRET_KEY is not the default value in production.

        Args:
            v: The SECRET_KEY value to validate.
            info: Pydantic validation context containing other field data.

        Returns:
            The validated SECRET_KEY.

        Raises:
            ValueError: If the default SECRET_KEY is used in production environment.
        """
        if info.data.get("ENVIRONMENT") == "production":
            if v.get_secret_value() == "changeme_in_production":
                raise ValueError(
                    "CRITICAL SECURITY ERROR: Cannot use default SECRET_KEY in production. "
                    "Set a strong, unique SECRET_KEY via environment variable."
                )
        return v

    @computed_field(return_type=PostgresDsn)
    @property
    def DATABASE_URL(self) -> str:
        """Construct the PostgreSQL connection DSN dynamically.

        Password resolution priority:
            1. POSTGRES_PASSWORD_FILE (Docker Secrets)
            2. POSTGRES_PASSWORD (environment variable)
            3. No password (trust authentication)

        Returns:
            A fully-qualified PostgreSQL connection string using asyncpg driver.

        Raises:
            ValueError: If POSTGRES_PASSWORD_FILE is defined but the file is missing.
        """
        password = ""

        if self.POSTGRES_PASSWORD_FILE:
            try:
                with open(self.POSTGRES_PASSWORD_FILE, "r") as f:
                    password = f.read().strip()
            except FileNotFoundError:
                raise ValueError(
                    f"CRITICAL: Database password file defined at '{self.POSTGRES_PASSWORD_FILE}' but not found."
                )
        elif self.POSTGRES_PASSWORD:
            password = self.POSTGRES_PASSWORD.get_secret_value()

        # Conditionally append password to avoid malformed "user:@host" syntax.
        auth_string = f"{self.POSTGRES_USER}"
        if password:
            auth_string += f":{password}"

        return (
            f"postgresql+asyncpg://{auth_string}@"
            f"{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field(return_type=RedisDsn)
    @property
    def REDIS_URL(self) -> str:
        """Construct the Redis connection DSN dynamically.

        Password resolution priority:
            1. REDIS_PASSWORD_FILE (Docker Secrets)
            2. REDIS_PASSWORD (environment variable)
            3. No password

        Returns:
            A fully-qualified Redis connection string.

        Raises:
            ValueError: If REDIS_PASSWORD_FILE is defined but the file is missing.
        """
        password = ""

        if self.REDIS_PASSWORD_FILE:
            try:
                with open(self.REDIS_PASSWORD_FILE, "r") as f:
                    password = f.read().strip()
            except FileNotFoundError:
                raise ValueError(
                    f"CRITICAL: Redis password file defined at '{self.REDIS_PASSWORD_FILE}' but not found."
                )
        elif self.REDIS_PASSWORD:
            password = self.REDIS_PASSWORD.get_secret_value()

        # Redis URI syntax for password-only auth: "redis://:password@host:port/db"
        auth_string = ""
        if password:
            auth_string = f":{password}@"

        return f"redis://{auth_string}{self.REDIS_HOST}:{self.REDIS_PORT}/0"


# ==============================================================================
# DEPENDENCY INJECTION
# ==============================================================================


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of the application settings.

    Use as a FastAPI dependency to inject configuration into route handlers.

    Returns:
        The singleton Settings instance.

    Example:
        >>> def get_db(settings: Settings = Depends(get_settings)):
        ...     pass
    """
    return Settings()