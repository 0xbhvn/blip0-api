"""Test-specific configuration settings."""

import os
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class TestDatabaseSettings(BaseSettings):
    """Database settings for testing with isolation."""

    # Use a separate test database to avoid affecting production/development data
    TEST_POSTGRES_USER: str = os.getenv("TEST_POSTGRES_USER", "ozuser")
    TEST_POSTGRES_PASSWORD: str = os.getenv("TEST_POSTGRES_PASSWORD", "ozpassword")
    TEST_POSTGRES_SERVER: str = os.getenv("TEST_POSTGRES_SERVER", "localhost")
    TEST_POSTGRES_PORT: int = int(os.getenv("TEST_POSTGRES_PORT", "5433"))
    TEST_POSTGRES_DB: str = os.getenv("TEST_POSTGRES_DB", "blip0_test")

    # Connection string components
    TEST_POSTGRES_SYNC_PREFIX: str = "postgresql://"
    TEST_POSTGRES_ASYNC_PREFIX: str = "postgresql+asyncpg://"

    @property
    def TEST_DATABASE_URI(self) -> str:
        """Get the test database URI."""
        return f"{self.TEST_POSTGRES_USER}:{self.TEST_POSTGRES_PASSWORD}@{self.TEST_POSTGRES_SERVER}:{self.TEST_POSTGRES_PORT}/{self.TEST_POSTGRES_DB}"

    @property
    def TEST_DATABASE_SYNC_URL(self) -> str:
        """Get the synchronous test database URL."""
        return f"{self.TEST_POSTGRES_SYNC_PREFIX}{self.TEST_DATABASE_URI}"

    @property
    def TEST_DATABASE_ASYNC_URL(self) -> str:
        """Get the asynchronous test database URL."""
        return f"{self.TEST_POSTGRES_ASYNC_PREFIX}{self.TEST_DATABASE_URI}"


class TestRedisSettings(BaseSettings):
    """Redis settings for testing."""

    TEST_REDIS_HOST: str = os.getenv("TEST_REDIS_HOST", "localhost")
    TEST_REDIS_PORT: int = int(os.getenv("TEST_REDIS_PORT", "6379"))
    TEST_REDIS_PASSWORD: Optional[str] = os.getenv("TEST_REDIS_PASSWORD", None)
    TEST_REDIS_DB: int = int(os.getenv("TEST_REDIS_DB", "15"))  # Use DB 15 for tests

    @property
    def TEST_REDIS_URL(self) -> str:
        """Get the test Redis URL."""
        if self.TEST_REDIS_PASSWORD:
            return f"redis://:{self.TEST_REDIS_PASSWORD}@{self.TEST_REDIS_HOST}:{self.TEST_REDIS_PORT}/{self.TEST_REDIS_DB}"
        return f"redis://{self.TEST_REDIS_HOST}:{self.TEST_REDIS_PORT}/{self.TEST_REDIS_DB}"


class TestSettings(TestDatabaseSettings, TestRedisSettings):
    """Combined test settings."""

    # Test environment settings
    TESTING: bool = True

    # Disable rate limiting in tests
    DISABLE_RATE_LIMIT: bool = True

    # Use shorter token expiry for tests
    TEST_ACCESS_TOKEN_EXPIRE_MINUTES: int = 5
    TEST_REFRESH_TOKEN_EXPIRE_DAYS: int = 1

    # Test secret key (not for production!)
    TEST_SECRET_KEY: SecretStr = SecretStr("test-secret-key-only-for-tests-do-not-use-in-production")

    # Disable background workers in tests by default
    DISABLE_BACKGROUND_TASKS: bool = True

    # Use smaller pagination limits for tests
    TEST_DEFAULT_PAGE_SIZE: int = 10
    TEST_MAX_PAGE_SIZE: int = 50

    # Disable caching in tests by default (can be enabled per test)
    DISABLE_CACHE: bool = True

    # Test user credentials
    TEST_USER_EMAIL: str = "test@example.com"
    TEST_USER_PASSWORD: str = "TestPassword123!"
    TEST_SUPERUSER_EMAIL: str = "admin@example.com"
    TEST_SUPERUSER_PASSWORD: str = "AdminPassword123!"


# Singleton instance
test_settings = TestSettings()
