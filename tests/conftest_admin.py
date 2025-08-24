"""Test fixtures for admin API tests."""

from unittest.mock import AsyncMock

import pytest

from src.app.api.dependencies import get_current_user, rate_limiter_dependency
from src.app.main import app


@pytest.fixture
def admin_user():
    """Mock admin user for authentication."""
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "username": "admin",
        "email": "admin@test.com",
        "name": "Admin User",
        "is_superuser": True,
        "tenant_id": "11111111-1111-1111-1111-111111111111",
    }


@pytest.fixture
def normal_user():
    """Mock normal user for authentication."""
    return {
        "id": "22222222-2222-2222-2222-222222222222",
        "username": "user",
        "email": "user@test.com",
        "name": "Normal User",
        "is_superuser": False,
        "tenant_id": "11111111-1111-1111-1111-111111111111",
    }


@pytest.fixture
def admin_user_token(admin_user):
    """Mock admin user token for authentication with dependency override."""
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[rate_limiter_dependency] = lambda: None
    yield {"access_token": "test-admin-token", "token_type": "bearer"}
    # Clean up override after test
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(rate_limiter_dependency, None)


@pytest.fixture
def normal_user_token(normal_user):
    """Mock normal user token for authentication with dependency override."""
    app.dependency_overrides[get_current_user] = lambda: normal_user
    app.dependency_overrides[rate_limiter_dependency] = lambda: None
    yield {"access_token": "test-user-token", "token_type": "bearer"}
    # Clean up override after test
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(rate_limiter_dependency, None)


@pytest.fixture
def db_session():
    """Mock database session for admin tests."""
    mock_session = AsyncMock()
    return mock_session
