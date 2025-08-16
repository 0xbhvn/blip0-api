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
    return Mock(spec=AsyncSession)


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
    import uuid

    from src.app.schemas.user import UserRead

    return UserRead(
        id=1,
        uuid=uuid.uuid4(),
        name=fake.name(),
        username=fake.user_name(),
        email=fake.email(),
        profile_image_url=fake.image_url(),
        is_superuser=False,
        created_at=fake.date_time(),
        updated_at=fake.date_time(),
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
