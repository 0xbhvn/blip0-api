from collections.abc import AsyncGenerator, Callable, Generator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from faker import Faker
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from sqlalchemy.pool import StaticPool

from src.app.core.db.database import Base
from src.app.main import app
from tests.test_config import test_settings

# Use test database configuration
DATABASE_URI = test_settings.TEST_DATABASE_URI
DATABASE_SYNC_PREFIX = test_settings.TEST_POSTGRES_SYNC_PREFIX
DATABASE_ASYNC_PREFIX = test_settings.TEST_POSTGRES_ASYNC_PREFIX

# Create test engines with connection pooling optimized for tests
sync_engine = create_engine(
    DATABASE_SYNC_PREFIX + DATABASE_URI,
    poolclass=StaticPool,  # Use StaticPool for testing
    connect_args={"options": "-c timezone=utc"},
)
async_engine = create_async_engine(
    DATABASE_ASYNC_PREFIX + DATABASE_URI,
    poolclass=StaticPool,
    connect_args={"server_settings": {"timezone": "utc"}},
)

# Session factories
local_session = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)
async_session_factory = async_sessionmaker(
    async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


fake = Faker()


@pytest.fixture(scope="session")
def setup_test_database():
    """Create test database tables before running tests."""
    # Create all tables in the test database
    Base.metadata.create_all(bind=sync_engine)
    yield
    # Drop all tables after tests complete
    Base.metadata.drop_all(bind=sync_engine)
    sync_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_db(setup_test_database) -> AsyncGenerator[AsyncSession, None]:
    """
    Async database session with transaction rollback for test isolation.

    Each test runs in its own transaction that gets rolled back after the test,
    ensuring complete isolation between tests.
    """
    async with async_engine.connect() as connection:
        # Begin a transaction
        async with connection.begin() as transaction:
            # Create a session bound to this connection
            async_session = async_session_factory(bind=connection)

            # Make the session available to the test
            yield async_session

            # Rollback the transaction after the test
            await transaction.rollback()
            await async_session.close()


@pytest.fixture(scope="function")
def db(setup_test_database) -> Generator[Session, Any, None]:
    """
    Synchronous database session with transaction rollback for test isolation.
    """
    connection = sync_engine.connect()
    transaction = connection.begin()

    # Configure the session to use our connection
    session = Session(bind=connection)

    # Make session available to test
    yield session

    # Rollback and cleanup
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, Any, None]:
    """Test client for the FastAPI application."""
    with TestClient(app) as _client:
        yield _client
    app.dependency_overrides = {}


def override_dependency(dependency: Callable[..., Any], mocked_response: Any) -> None:
    app.dependency_overrides[dependency] = lambda: mocked_response


@pytest.fixture
def override_get_db(async_db):
    """Override the database dependency for tests that need it."""
    from src.app.api.dependencies import get_db

    async def _override_get_db():
        yield async_db

    # Store original dependency
    original = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db

    yield _override_get_db

    # Clean up override after test
    if original is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = original


@pytest.fixture
def mock_db():
    """Mock database session for unit tests."""
    mock = AsyncMock(spec=AsyncSession)

    # Create a proper async context manager for transactions
    class AsyncContextManager:
        async def __aenter__(self):
            return None
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return None

    # Make begin() return an async context manager instance
    mock.begin.return_value = AsyncContextManager()
    mock.flush = AsyncMock(return_value=None)
    mock.commit = AsyncMock(return_value=None)
    mock.rollback = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def mock_redis():
    """Mock Redis connection for unit tests."""
    mock_redis = AsyncMock()
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

# Performance optimization for bcrypt in tests
@pytest.fixture(autouse=True)
def optimize_bcrypt_for_tests(monkeypatch):
    """Optimize bcrypt for faster test execution while maintaining functionality."""
    import bcrypt

    # Use minimum rounds for testing (4 rounds = ~1ms vs 12 rounds = 500ms)
    original_gensalt = bcrypt.gensalt

    def fast_gensalt(rounds: int = 4, prefix: bytes = b'2b'):
        return original_gensalt(rounds=rounds, prefix=prefix)

    monkeypatch.setattr(bcrypt, 'gensalt', fast_gensalt)


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


# Performance-optimized security fixtures
@pytest.fixture(scope="session")
def precomputed_password_hash():
    """Pre-computed password hash to avoid bcrypt in every test."""
    import bcrypt
    password = "TestPassword123!"
    # Use fast rounds for testing
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture(scope="session")
def precomputed_api_key_hash():
    """Pre-computed API key hash to avoid bcrypt in every test."""
    import bcrypt
    api_key = "blp0_test_key_1234567890abcdef"
    return bcrypt.hashpw(api_key.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture(scope="session")
def mock_jwt_tokens():
    """Pre-generated JWT tokens for testing."""
    from datetime import UTC, datetime, timedelta

    import jwt

    secret = "test-secret-key"

    # Access token (valid for 30 minutes)
    access_payload = {
        "sub": "testuser",
        "token_type": "access",
        "exp": datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=30)
    }

    # Refresh token (valid for 7 days)
    refresh_payload = {
        "sub": "testuser",
        "token_type": "refresh",
        "exp": datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
    }

    # Expired token
    expired_payload = {
        "sub": "testuser",
        "token_type": "access",
        "exp": datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5)
    }

    return {
        "access_token": jwt.encode(access_payload, secret, algorithm="HS256"),
        "refresh_token": jwt.encode(refresh_payload, secret, algorithm="HS256"),
        "expired_token": jwt.encode(expired_payload, secret, algorithm="HS256")
    }


@pytest.fixture
def fast_redis_mock():
    """High-performance Redis mock with instant responses."""
    from unittest.mock import AsyncMock, Mock

    mock_redis = Mock()

    # Instant responses for all Redis operations
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=1)
    mock_redis.sadd = AsyncMock(return_value=1)
    mock_redis.srem = AsyncMock(return_value=1)
    mock_redis.smembers = AsyncMock(return_value=set())

    return mock_redis
