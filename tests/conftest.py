from collections.abc import Callable, Generator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from faker import Faker
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session

from src.app.core.config import settings
from src.app.main import app

DATABASE_URI = settings.POSTGRES_URI
DATABASE_PREFIX = settings.POSTGRES_SYNC_PREFIX

sync_engine = create_engine(DATABASE_PREFIX + DATABASE_URI)
local_session = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)


fake = Faker()


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, Any, None]:
    with TestClient(app) as _client:
        yield _client
    app.dependency_overrides = {}
    sync_engine.dispose()


@pytest.fixture
def db() -> Generator[Session, Any, None]:
    session = local_session()
    yield session
    session.close()


def override_dependency(dependency: Callable[..., Any], mocked_response: Any) -> None:
    app.dependency_overrides[dependency] = lambda: mocked_response


@pytest.fixture
def mock_db():
    """Mock database session for unit tests."""
    mock = Mock(spec=AsyncSession)
    # Add async context manager support for transactions
    mock.begin = Mock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=None),
            __aexit__=AsyncMock(return_value=None)
        )
    )
    mock.flush = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def mock_redis():
    """Mock Redis connection for unit tests."""
    mock_redis = Mock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=True)
    return mock_redis


@pytest.fixture
def sample_user_data():
    """Generate sample user data for tests."""
    return {
        "name": fake.name(),
        "username": fake.user_name(),
        "email": fake.email(),
        "password": fake.password(),
    }


@pytest.fixture
def sample_user_read():
    """Generate a sample UserRead object."""
    from src.app.schemas.user import UserRead

    return UserRead(
        id=1,
        name=fake.name(),
        username=fake.user_name(),
        email=fake.email(),
        profile_image_url=fake.image_url(),
        tier_id=None,
    )


@pytest.fixture
def current_user_dict():
    """Mock current user from auth dependency."""
    return {
        "id": 1,
        "username": fake.user_name(),
        "email": fake.email(),
        "name": fake.name(),
        "is_superuser": False,
    }


# Additional fixtures for service layer testing


@pytest.fixture
def mock_redis_client():
    """Enhanced Redis client mock for service testing."""
    mock_redis = Mock()

    # Mock all Redis operations used by services
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.delete_pattern = AsyncMock(return_value=1)
    mock_redis.sadd = AsyncMock(return_value=1)
    mock_redis.srem = AsyncMock(return_value=1)
    mock_redis.smembers = AsyncMock(return_value=set())
    mock_redis.expire = AsyncMock(return_value=True)

    return mock_redis


@pytest.fixture
def sample_tenant_data():
    """Generate sample tenant data for tests."""
    import uuid

    return {
        "id": uuid.uuid4(),
        "name": fake.company(),
        "slug": fake.slug(),
        "description": fake.text(max_nb_chars=100),
        "is_active": True,
        "created_at": fake.date_time(),
        "updated_at": fake.date_time(),
    }


@pytest.fixture
def sample_monitor_data():
    """Generate sample monitor data for tests."""
    import uuid

    return {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "name": fake.name(),
        "slug": fake.slug(),
        "description": fake.text(max_nb_chars=100),
        "paused": False,
        "networks": ["ethereum", "polygon"],
        "addresses": [{"address": "0x123", "type": "contract"}],
        "match_functions": [{"signature": "transfer(address,uint256)"}],
        "match_events": [{"signature": "Transfer(address,address,uint256)"}],
        "match_transactions": [],
        "trigger_conditions": [{"condition": "value > 1000"}],
        "triggers": [],
        "created_at": fake.date_time(),
        "updated_at": fake.date_time(),
    }


@pytest.fixture
def sample_network_data():
    """Generate sample network data for tests."""
    import uuid

    return {
        "id": uuid.uuid4(),
        "name": fake.name(),
        "slug": fake.slug(),
        "chain_id": fake.random_int(min=1, max=999999),
        "rpc_urls": [fake.url(), fake.url()],
        "explorer_url": fake.url(),
        "is_active": True,
        "created_at": fake.date_time(),
        "updated_at": fake.date_time(),
    }


@pytest.fixture
def sample_trigger_data():
    """Generate sample trigger data for tests."""
    import uuid

    return {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "monitor_id": uuid.uuid4(),
        "name": fake.name(),
        "slug": fake.slug(),
        "trigger_type": "email",
        "config": {"email": fake.email(), "subject": fake.sentence()},
        "is_active": True,
        "created_at": fake.date_time(),
        "updated_at": fake.date_time(),
    }


@pytest.fixture
def mock_crud_monitor():
    """Mock CRUD operations for Monitor."""
    mock_crud = Mock()
    mock_crud.create = AsyncMock()
    mock_crud.get = AsyncMock()
    mock_crud.update = AsyncMock()
    mock_crud.delete = AsyncMock()
    mock_crud.get_paginated = AsyncMock()
    mock_crud.get_multi = AsyncMock()
    return mock_crud


@pytest.fixture
def mock_crud_tenant():
    """Mock CRUD operations for Tenant."""
    mock_crud = Mock()
    mock_crud.create = AsyncMock()
    mock_crud.get = AsyncMock()
    mock_crud.update = AsyncMock()
    mock_crud.delete = AsyncMock()
    mock_crud.get_paginated = AsyncMock()
    mock_crud.get_multi = AsyncMock()
    mock_crud.get_by_slug = AsyncMock()
    return mock_crud


@pytest.fixture
def mock_crud_network():
    """Mock CRUD operations for Network."""
    mock_crud = Mock()
    mock_crud.create = AsyncMock()
    mock_crud.get = AsyncMock()
    mock_crud.update = AsyncMock()
    mock_crud.delete = AsyncMock()
    mock_crud.get_paginated = AsyncMock()
    mock_crud.get_multi = AsyncMock()
    mock_crud.get_by_slug = AsyncMock()
    return mock_crud


@pytest.fixture
def mock_crud_trigger():
    """Mock CRUD operations for Trigger."""
    mock_crud = Mock()
    mock_crud.create = AsyncMock()
    mock_crud.get = AsyncMock()
    mock_crud.update = AsyncMock()
    mock_crud.delete = AsyncMock()
    mock_crud.get_paginated = AsyncMock()
    mock_crud.get_multi = AsyncMock()
    mock_crud.get_by_slug = AsyncMock()
    mock_crud.create_with_config = AsyncMock()
    mock_crud.update_with_config = AsyncMock()
    mock_crud._get_trigger_with_config = AsyncMock()
    mock_crud.validate_trigger = AsyncMock()
    mock_crud.test_trigger = AsyncMock()
    mock_crud.activate_trigger = AsyncMock()
    mock_crud.deactivate_trigger = AsyncMock()
    mock_crud.get_active_triggers_by_type = AsyncMock()
    return mock_crud


# Security test fixtures


@pytest.fixture
def mock_user():
    """Mock user object for tests."""
    import uuid
    return {
        "id": 1,
        "username": "testuser",
        "email": "test@example.com",
        "name": "Test User",
        "tenant_id": uuid.uuid4(),
        "is_superuser": False,
        "role": "user",
        "permissions": ["monitor:read", "monitor:write"]
    }


@pytest.fixture
def mock_viewer_user():
    """Mock viewer user for tests."""
    import uuid
    return {
        "id": 2,
        "username": "viewer",
        "email": "viewer@example.com",
        "name": "Viewer User",
        "tenant_id": uuid.uuid4(),
        "is_superuser": False,
        "role": "viewer",
        "permissions": ["monitor:read"]
    }


@pytest.fixture
def mock_admin_user():
    """Mock admin user for tests."""
    import uuid
    return {
        "id": 3,
        "username": "admin",
        "email": "admin@example.com",
        "name": "Admin User",
        "tenant_id": uuid.uuid4(),
        "is_superuser": False,
        "role": "admin",
        "permissions": ["monitor:read", "monitor:write", "monitor:delete", "admin:access"]
    }


@pytest.fixture
def mock_superuser():
    """Mock superuser for tests."""
    import uuid
    return {
        "id": 4,
        "username": "superuser",
        "email": "superuser@example.com",
        "name": "Super User",
        "tenant_id": uuid.uuid4(),
        "is_superuser": True,
        "role": "superuser",
        "permissions": ["*"]
    }


@pytest.fixture
def viewer_headers(mock_viewer_user):
    """Mock headers for viewer user."""
    return {"Authorization": "Bearer mock_viewer_token"}


@pytest.fixture
def admin_headers(mock_admin_user):
    """Mock headers for admin user."""
    return {"Authorization": "Bearer mock_admin_token"}


@pytest.fixture
def auth_headers(mock_user):
    """Mock auth headers for regular user."""
    return {"Authorization": "Bearer mock_user_token"}


@pytest.fixture
def superuser_headers(mock_superuser):
    """Mock headers for superuser."""
    return {"Authorization": "Bearer mock_superuser_token"}


@pytest.fixture
def tenant_headers(mock_user):
    """Mock headers for tenant user."""
    return {"Authorization": "Bearer mock_tenant_token"}


@pytest.fixture
def user_headers_by_role():
    """Mock headers for different user roles."""
    return {
        "viewer": {"Authorization": "Bearer mock_viewer_token"},
        "user": {"Authorization": "Bearer mock_user_token"},
        "admin": {"Authorization": "Bearer mock_admin_token"}
    }


@pytest.fixture
def auth_headers_multi():
    """Mock headers for multiple users."""
    return {
        "user_a": {"Authorization": "Bearer mock_user_a_token"},
        "user_b": {"Authorization": "Bearer mock_user_b_token"},
        "tenant_a": {"Authorization": "Bearer mock_tenant_a_token"},
        "tenant_b": {"Authorization": "Bearer mock_tenant_b_token"}
    }


@pytest.fixture
def free_tier_headers():
    """Mock headers for free tier user."""
    return {"Authorization": "Bearer mock_free_tier_token"}


@pytest.fixture
def pro_tier_headers():
    """Mock headers for pro tier user."""
    return {"Authorization": "Bearer mock_pro_tier_token"}


@pytest.fixture
def test_user():
    """Mock test user with password for login tests."""
    return {
        "username": "testuser",
        "email": "test@example.com",
        "password": "TestPassword123!",
        "name": "Test User"
    }


@pytest.fixture
def test_api_key():
    """Mock API key for testing."""
    return "blp0_test_key_1234567890abcdef"


@pytest.fixture
def expired_api_key():
    """Mock expired API key for testing."""
    return "blp0_expired_key_abcdef1234567890"


@pytest.fixture
def scoped_api_key():
    """Mock scoped API key for testing."""
    return {
        "key": "blp0_scoped_key_abcdef1234567890",
        "scopes": ["monitor:read", "trigger:read"]
    }


@pytest.fixture
def tenant_a_api_key():
    """Mock API key for tenant A."""
    return "blp0_tenant_a_key_1234567890abcdef"


@pytest.fixture
def tenant_b_api_key():
    """Mock API key for tenant B."""
    return "blp0_tenant_b_key_abcdef1234567890"
