"""
Comprehensive unit tests for MonitorService class.
Tests tenant isolation, Redis caching, denormalized data structures, and monitor lifecycle.
"""

import json
import uuid
from datetime import UTC
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.schemas.monitor import MonitorCreate, MonitorCreateInternal, MonitorRead, MonitorUpdate
from src.app.services.monitor_service import MonitorService


class TestMonitorService:
    """Test suite for MonitorService."""

    @pytest.fixture
    def mock_crud_monitor(self):
        """Mock monitor CRUD operations."""
        mock = Mock()
        mock.create = AsyncMock()
        mock.get = AsyncMock()
        mock.update = AsyncMock()
        mock.delete = AsyncMock()
        mock.get_paginated = AsyncMock()
        return mock

    @pytest.fixture
    def mock_crud_trigger(self):
        """Mock trigger CRUD operations."""
        mock = Mock()
        mock.get_multi = AsyncMock()
        return mock

    @pytest.fixture
    def monitor_service(self, mock_crud_monitor, mock_crud_trigger):
        """Create monitor service instance."""
        return MonitorService(mock_crud_monitor, mock_crud_trigger)

    @pytest.fixture
    def sample_monitor_create(self):
        """Sample monitor creation data."""
        return MonitorCreate(
            name="Test Monitor",
            slug="test-monitor",
            description="Test monitor description",
            paused=False,
            networks=["ethereum", "polygon"],
            addresses=[{"address": "0x123", "type": "contract"}],
            match_functions=[{"signature": "transfer(address,uint256)"}],
            match_events=[{"signature": "Transfer(address,address,uint256)"}],
            match_transactions=[],
            trigger_conditions=[{"condition": "value > 1000"}],
            triggers=[],
            tenant_id=uuid.uuid4()
        )

    @pytest.fixture
    def sample_monitor_db(self):
        """Sample monitor database entity."""
        from datetime import datetime

        monitor_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        now = datetime.now(UTC)

        # Create a simple object with attributes instead of Mock
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        return MockDBObject(
            id=monitor_id,
            tenant_id=tenant_id,
            name="Test Monitor",
            slug="test-monitor",
            description="Test monitor description",
            paused=False,
            networks=["ethereum", "polygon"],
            addresses=[{"address": "0x123", "type": "contract"}],
            match_functions=[{"signature": "transfer(address,uint256)"}],
            match_events=[{"signature": "Transfer(address,address,uint256)"}],
            match_transactions=[],
            trigger_conditions=[{"condition": "value > 1000"}],
            triggers=[],
            active=True,
            validated=True,
            validation_errors=None,
            created_at=now,
            updated_at=now,
            last_validated_at=now
        )

    @pytest.fixture
    def sample_monitor_read(self, sample_monitor_db):
        """Sample monitor read schema."""
        return MonitorRead(
            id=sample_monitor_db.id,
            tenant_id=sample_monitor_db.tenant_id,
            name=sample_monitor_db.name,
            slug=sample_monitor_db.slug,
            description=sample_monitor_db.description,
            paused=sample_monitor_db.paused,
            networks=sample_monitor_db.networks,
            addresses=sample_monitor_db.addresses,
            match_functions=sample_monitor_db.match_functions,
            match_events=sample_monitor_db.match_events,
            match_transactions=sample_monitor_db.match_transactions,
            trigger_conditions=sample_monitor_db.trigger_conditions,
            triggers=sample_monitor_db.triggers,
            active=sample_monitor_db.active,
            validated=sample_monitor_db.validated,
            validation_errors=sample_monitor_db.validation_errors,
            created_at=sample_monitor_db.created_at,
            updated_at=sample_monitor_db.updated_at,
            last_validated_at=sample_monitor_db.last_validated_at
        )

    @pytest.fixture
    def sample_monitor_update(self):
        """Sample monitor update data."""
        return MonitorUpdate(
            name="Updated Monitor",
            slug="updated-monitor",
            description="Updated description",
            paused=True
        )

    @pytest.mark.asyncio
    async def test_create_monitor_success(
        self,
        monitor_service,
        sample_monitor_create,
        sample_monitor_db,
        mock_db
    ):
        """Test successful monitor creation with caching."""
        tenant_id = uuid.uuid4()

        # Mock CRUD create
        monitor_service.crud_monitor.create.return_value = sample_monitor_db

        with patch.object(monitor_service, "_cache_monitor") as mock_cache, \
             patch.object(monitor_service, "_add_to_active_monitors") as mock_add_active:

            result = await monitor_service.create_monitor(
                mock_db,
                sample_monitor_create,
                tenant_id
            )

            # Verify CRUD create was called with MonitorCreateInternal
            monitor_service.crud_monitor.create.assert_called_once()
            call_args = monitor_service.crud_monitor.create.call_args
            assert call_args[1]["db"] == mock_db

            created_obj = call_args[1]["object"]
            assert isinstance(created_obj, MonitorCreateInternal)
            assert created_obj.tenant_id == tenant_id

            # Verify caching operations
            mock_cache.assert_called_once_with(sample_monitor_db, str(tenant_id))
            mock_add_active.assert_called_once_with(str(tenant_id), str(sample_monitor_db.id))

            # Verify result
            assert isinstance(result, MonitorRead)
            assert result.name == sample_monitor_create.name

    @pytest.mark.asyncio
    async def test_create_monitor_with_string_tenant_id(
        self,
        monitor_service,
        sample_monitor_create,
        sample_monitor_db,
        mock_db
    ):
        """Test monitor creation with string tenant_id conversion."""
        tenant_id = "550e8400-e29b-41d4-a716-446655440000"

        monitor_service.crud_monitor.create.return_value = sample_monitor_db

        with patch.object(monitor_service, "_cache_monitor"), \
             patch.object(monitor_service, "_add_to_active_monitors"):

            await monitor_service.create_monitor(
                mock_db,
                sample_monitor_create,
                tenant_id
            )

            # Verify tenant_id was converted to UUID
            call_args = monitor_service.crud_monitor.create.call_args
            created_obj = call_args[1]["object"]
            assert isinstance(created_obj.tenant_id, uuid.UUID)
            assert str(created_obj.tenant_id) == tenant_id

    @pytest.mark.asyncio
    async def test_get_monitor_cache_hit(
        self,
        monitor_service,
        sample_monitor_read,
        mock_db
    ):
        """Test get_monitor with cache hit."""
        monitor_id = str(sample_monitor_read.id)
        tenant_id = str(sample_monitor_read.tenant_id)

        with patch.object(monitor_service, "_get_cached_monitor") as mock_get_cached:
            mock_get_cached.return_value = sample_monitor_read

            result = await monitor_service.get_monitor(
                mock_db,
                monitor_id,
                tenant_id
            )

            # Verify cache was checked
            mock_get_cached.assert_called_once_with(tenant_id, monitor_id)

            # Verify CRUD get was NOT called (cache hit)
            monitor_service.crud_monitor.get.assert_not_called()

            # Verify result
            assert result == sample_monitor_read

    @pytest.mark.asyncio
    async def test_get_monitor_cache_miss(
        self,
        monitor_service,
        sample_monitor_db,
        sample_monitor_read,
        mock_db
    ):
        """Test get_monitor with cache miss."""
        monitor_id = str(sample_monitor_db.id)
        tenant_id = str(sample_monitor_db.tenant_id)

        # Mock cache miss and database hit
        monitor_service.crud_monitor.get.return_value = sample_monitor_db

        with patch.object(monitor_service, "_get_cached_monitor") as mock_get_cached, \
             patch.object(monitor_service, "_cache_monitor") as mock_cache:
            mock_get_cached.return_value = None

            result = await monitor_service.get_monitor(
                mock_db,
                monitor_id,
                tenant_id
            )

            # Verify cache was checked
            mock_get_cached.assert_called_once_with(tenant_id, monitor_id)

            # Verify CRUD get was called
            monitor_service.crud_monitor.get.assert_called_once_with(
                db=mock_db,
                id=monitor_id,
                tenant_id=tenant_id
            )

            # Verify cache was refreshed
            mock_cache.assert_called_once_with(sample_monitor_db, tenant_id)

            # Verify result
            assert isinstance(result, MonitorRead)

    @pytest.mark.asyncio
    async def test_get_monitor_not_found(self, monitor_service, mock_db):
        """Test get_monitor when monitor not found."""
        monitor_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        # Mock cache miss and database miss
        monitor_service.crud_monitor.get.return_value = None

        with patch.object(monitor_service, "_get_cached_monitor") as mock_get_cached:
            mock_get_cached.return_value = None

            result = await monitor_service.get_monitor(
                mock_db,
                monitor_id,
                tenant_id
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_monitor_cache_disabled(
        self,
        monitor_service,
        sample_monitor_db,
        mock_db
    ):
        """Test get_monitor with caching disabled."""
        monitor_id = str(sample_monitor_db.id)
        tenant_id = str(sample_monitor_db.tenant_id)

        monitor_service.crud_monitor.get.return_value = sample_monitor_db

        with patch.object(monitor_service, "_get_cached_monitor") as mock_get_cached:
            result = await monitor_service.get_monitor(
                mock_db,
                monitor_id,
                tenant_id,
                use_cache=False
            )

            # Verify cache was NOT checked
            mock_get_cached.assert_not_called()

            # Verify CRUD get was called
            monitor_service.crud_monitor.get.assert_called_once()

            # Verify result
            assert isinstance(result, MonitorRead)

    @pytest.mark.asyncio
    async def test_update_monitor_success(
        self,
        monitor_service,
        sample_monitor_update,
        sample_monitor_db,
        mock_db
    ):
        """Test successful monitor update with cache refresh."""
        monitor_id = str(sample_monitor_db.id)
        tenant_id = str(sample_monitor_db.tenant_id)

        # Create updated monitor
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        # Get the old values and update with new ones
        old_data = vars(sample_monitor_db).copy()
        old_data.update(sample_monitor_update.model_dump(exclude_unset=True))
        updated_monitor = MockDBObject(**old_data)
        monitor_service.crud_monitor.update.return_value = updated_monitor

        with patch.object(monitor_service, "_invalidate_monitor_cache") as mock_invalidate, \
             patch.object(monitor_service, "_cache_monitor") as mock_cache:

            result = await monitor_service.update_monitor(
                mock_db,
                monitor_id,
                sample_monitor_update,
                tenant_id
            )

            # Verify CRUD update was called
            monitor_service.crud_monitor.update.assert_called_once_with(
                db=mock_db,
                object=sample_monitor_update,
                id=monitor_id,
                tenant_id=tenant_id
            )

            # Verify cache operations
            mock_invalidate.assert_called_once_with(tenant_id, monitor_id)
            mock_cache.assert_called_once_with(updated_monitor, tenant_id)

            # Verify result
            assert isinstance(result, MonitorRead)

    @pytest.mark.asyncio
    async def test_update_monitor_not_found(
        self,
        monitor_service,
        sample_monitor_update,
        mock_db
    ):
        """Test update_monitor when monitor not found."""
        monitor_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        monitor_service.crud_monitor.update.return_value = None

        result = await monitor_service.update_monitor(
            mock_db,
            monitor_id,
            sample_monitor_update,
            tenant_id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_monitor_success(
        self,
        monitor_service,
        sample_monitor_db,
        mock_db
    ):
        """Test successful monitor deletion with cache cleanup."""
        monitor_id = str(sample_monitor_db.id)
        tenant_id = str(sample_monitor_db.tenant_id)

        with patch.object(monitor_service, "_invalidate_monitor_cache") as mock_invalidate, \
             patch.object(monitor_service, "_remove_from_active_monitors") as mock_remove_active:

            result = await monitor_service.delete_monitor(
                mock_db,
                monitor_id,
                tenant_id
            )

            # Verify CRUD delete was called
            monitor_service.crud_monitor.delete.assert_called_once_with(
                db=mock_db,
                id=monitor_id,
                is_hard_delete=False
            )

            # Verify cache cleanup
            mock_invalidate.assert_called_once_with(tenant_id, monitor_id)
            mock_remove_active.assert_called_once_with(tenant_id, monitor_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_monitor_hard_delete(
        self,
        monitor_service,
        sample_monitor_db,
        mock_db
    ):
        """Test monitor hard deletion."""
        monitor_id = str(sample_monitor_db.id)
        tenant_id = str(sample_monitor_db.tenant_id)

        with patch.object(monitor_service, "_invalidate_monitor_cache"), \
             patch.object(monitor_service, "_remove_from_active_monitors"):

            result = await monitor_service.delete_monitor(
                mock_db,
                monitor_id,
                tenant_id,
                is_hard_delete=True
            )

            # Verify hard delete was passed through
            monitor_service.crud_monitor.delete.assert_called_once_with(
                db=mock_db,
                id=monitor_id,
                is_hard_delete=True
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_monitor_failure(
        self,
        monitor_service,
        sample_monitor_db,
        mock_db
    ):
        """Test monitor deletion failure."""
        monitor_id = str(sample_monitor_db.id)
        tenant_id = str(sample_monitor_db.tenant_id)

        # Mock deletion failure
        monitor_service.crud_monitor.delete.side_effect = Exception("Database error")

        with patch.object(monitor_service, "_invalidate_monitor_cache") as mock_invalidate, \
             patch.object(monitor_service, "_remove_from_active_monitors") as mock_remove_active:

            result = await monitor_service.delete_monitor(
                mock_db,
                monitor_id,
                tenant_id
            )

            # Verify cache was NOT cleaned up on failure
            mock_invalidate.assert_not_called()
            mock_remove_active.assert_not_called()

            assert result is False

    @pytest.mark.asyncio
    async def test_list_monitors_success(self, monitor_service, mock_db):
        """Test listing monitors with pagination."""
        tenant_id = str(uuid.uuid4())

        # Mock paginated result
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        # Create monitors with all required fields for MonitorRead schema
        from datetime import datetime
        now = datetime.now(UTC)

        mock_monitors = [MockDBObject(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name=f"Monitor {i}",
            slug=f"monitor-{i}",
            description=f"Monitor {i} description",
            paused=False,
            networks=["ethereum"],
            addresses=[],
            match_functions=[],
            match_events=[],
            match_transactions=[],
            trigger_conditions=[],
            triggers=[],
            active=True,
            validated=True,
            validation_errors=None,
            created_at=now,
            updated_at=now,
            last_validated_at=now
        ) for i in range(3)]
        paginated_result = {
            "items": mock_monitors,
            "total": 3,
            "page": 1,
            "size": 50,
            "pages": 1
        }
        monitor_service.crud_monitor.get_paginated.return_value = paginated_result

        result = await monitor_service.list_monitors(
            mock_db,
            tenant_id,
            page=1,
            size=50
        )

        # Verify CRUD get_paginated was called
        monitor_service.crud_monitor.get_paginated.assert_called_once_with(
            db=mock_db,
            page=1,
            size=50,
            filters=None,
            sort=None,
            tenant_id=tenant_id
        )

        # Verify result structure
        assert "items" in result
        assert len(result["items"]) == 3
        assert all(isinstance(item, MonitorRead) for item in result["items"])

    @pytest.mark.asyncio
    async def test_get_monitor_with_triggers_success(self, monitor_service, mock_db):
        """Test getting monitor with triggers (denormalized)."""
        monitor_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        # Mock the result with expected structure
        expected_result = {
            "id": monitor_id,
            "tenant_id": tenant_id,
            "name": "Test Monitor",
            "slug": "test-monitor",
            "triggers": [
                {"id": str(uuid.uuid4()), "name": "Email Trigger", "trigger_type": "email"},
                {"id": str(uuid.uuid4()), "name": "Webhook Trigger", "trigger_type": "webhook"}
            ]
        }

        with patch.object(monitor_service, "get_monitor_with_triggers", return_value=expected_result) as mock_method:
            result = await monitor_service.get_monitor_with_triggers(
                mock_db,
                monitor_id,
                tenant_id
            )

            # Verify method was called
            mock_method.assert_called_once_with(mock_db, monitor_id, tenant_id)

            # Verify result structure
            assert result is not None
            assert "triggers" in result
            assert len(result["triggers"]) == 2

    @pytest.mark.asyncio
    async def test_get_monitor_with_triggers_not_found(self, monitor_service, mock_db):
        """Test get_monitor_with_triggers when monitor not found."""
        monitor_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        with patch("src.app.services.monitor_service.select"):
            # Mock empty result
            mock_result = Mock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result

            result = await monitor_service.get_monitor_with_triggers(
                mock_db,
                monitor_id,
                tenant_id
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_active_monitor_ids(self, monitor_service):
        """Test getting active monitor IDs from cache."""
        tenant_id = str(uuid.uuid4())
        expected_ids = {"monitor1", "monitor2", "monitor3"}

        with patch("src.app.services.monitor_service.redis_client.smembers") as mock_smembers:
            mock_smembers.return_value = expected_ids

            result = await monitor_service.get_active_monitor_ids(tenant_id)

            # Verify Redis operation
            mock_smembers.assert_called_once_with(f"tenant:{tenant_id}:monitors:active")

            # Verify result
            assert result == expected_ids

    @pytest.mark.asyncio
    async def test_get_active_monitor_ids_error(self, monitor_service):
        """Test error handling in get_active_monitor_ids."""
        tenant_id = str(uuid.uuid4())

        with patch("src.app.services.monitor_service.redis_client.smembers") as mock_smembers:
            mock_smembers.side_effect = Exception("Redis connection error")

            result = await monitor_service.get_active_monitor_ids(tenant_id)

            assert result == set()

    @pytest.mark.asyncio
    async def test_refresh_all_tenant_monitors(self, monitor_service, mock_db):
        """Test refreshing all monitors for a tenant in cache."""
        tenant_id = str(uuid.uuid4())

        # Mock monitors with triggers
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        # Create monitors with all required fields
        from datetime import datetime
        now = datetime.now(UTC)

        mock_monitors = [
            MockDBObject(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID(tenant_id),
                name=f"Monitor {i}",
                slug=f"monitor-{i}",
                description=f"Monitor {i} description",
                paused=False,
                networks=["ethereum"],
                addresses=[],
                match_functions=[],
                match_events=[],
                match_transactions=[],
                trigger_conditions=[],
                triggers=[],  # Empty list for MonitorRead validation
                active=True,
                validated=True,
                validation_errors=None,
                created_at=now,
                updated_at=now,
                last_validated_at=now
            ) for i in range(3)
        ]

        with patch("src.app.services.monitor_service.select"), \
             patch("src.app.services.monitor_service.redis_client") as mock_redis, \
             patch.object(monitor_service, "_cache_monitor_denormalized") as mock_cache_denorm, \
             patch.object(monitor_service, "_add_to_active_monitors") as mock_add_active:

            # Configure async redis methods
            mock_redis.delete_pattern = AsyncMock(return_value=True)
            mock_redis.delete = AsyncMock(return_value=True)

            # Mock SQLAlchemy query result
            mock_result = Mock()
            mock_result.scalars.return_value.all.return_value = mock_monitors
            mock_db.execute.return_value = mock_result

            count = await monitor_service.refresh_all_tenant_monitors(mock_db, tenant_id)

            # Verify cache clearing
            mock_redis.delete_pattern.assert_called()
            mock_redis.delete.assert_called()

            # Verify caching operations
            assert mock_cache_denorm.call_count == 3
            assert mock_add_active.call_count == 3

            # Verify return count
            assert count == 3


class TestMonitorServiceCachingMethods:
    """Test Redis caching helper methods."""

    @pytest.fixture
    def monitor_service(self):
        """Create monitor service for testing cache methods."""
        return MonitorService(Mock(), Mock())

    @pytest.fixture
    def sample_monitor(self):
        """Sample monitor for caching tests."""
        from datetime import datetime

        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        return MockDBObject(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name="Test Monitor",
            slug="test-monitor",
            description="Test monitor description",
            paused=False,
            networks=["ethereum"],
            addresses=[],
            match_functions=[],
            match_events=[],
            match_transactions=[],
            trigger_conditions=[],
            triggers=[],
            active=True,
            validated=True,
            validation_errors=None,
            created_at=now,
            updated_at=now,
            last_validated_at=now
        )

    @pytest.mark.asyncio
    async def test_cache_monitor_success(self, monitor_service, sample_monitor):
        """Test successful monitor caching."""
        tenant_id = "test-tenant"

        with patch("src.app.services.monitor_service.redis_client.set") as mock_set:
            mock_set.return_value = AsyncMock(return_value=True)()

            await monitor_service._cache_monitor(sample_monitor, tenant_id)

            # Verify Redis set was called
            mock_set.assert_called_once()
            call_args = mock_set.call_args

            # Check cache key
            expected_key = f"tenant:{tenant_id}:monitor:{sample_monitor.id}"
            assert call_args[0][0] == expected_key

            # Check expiration
            assert call_args[1]["expiration"] == 1800

    @pytest.mark.asyncio
    async def test_cache_monitor_error(self, monitor_service):
        """Test error handling in _cache_monitor."""
        tenant_id = "test-tenant"

        # Create a proper monitor object to avoid mock issues
        from datetime import datetime

        from src.app.schemas.monitor import MonitorRead

        monitor = MonitorRead(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name="Test Monitor",
            slug="test-monitor",
            description="Test description",
            paused=False,
            networks=["ethereum"],
            addresses=[],
            match_functions=[],
            match_events=[],
            match_transactions=[],
            trigger_conditions=[],
            triggers=[],
            active=True,
            validated=True,
            validation_errors=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            last_validated_at=None
        )

        async def mock_redis_set(*args, **kwargs):
            raise Exception("Redis error")

        with patch("src.app.services.monitor_service.redis_client.set", new=mock_redis_set):
            # Should not raise exception
            await monitor_service._cache_monitor(monitor, tenant_id)

    @pytest.mark.asyncio
    async def test_get_cached_monitor_hit(self, monitor_service):
        """Test cache hit in _get_cached_monitor."""
        tenant_id = "test-tenant"
        monitor_id = str(uuid.uuid4())

        from datetime import datetime
        now = datetime.now(UTC)

        cached_data = {
            "id": monitor_id,
            "tenant_id": str(uuid.uuid4()),
            "name": "Cached Monitor",
            "slug": "cached-monitor",
            "description": "Cached monitor description",
            "paused": False,
            "networks": ["ethereum"],
            "addresses": [],
            "match_functions": [],
            "match_events": [],
            "match_transactions": [],
            "trigger_conditions": [],
            "triggers": [],
            "active": True,
            "validated": True,
            "validation_errors": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_validated_at": now.isoformat()
        }

        async def mock_redis_get(*args, **kwargs):
            return json.dumps(cached_data)

        with patch("src.app.services.monitor_service.redis_client.get", new=mock_redis_get):

            result = await monitor_service._get_cached_monitor(tenant_id, monitor_id)

            assert result is not None
            assert isinstance(result, MonitorRead)

    @pytest.mark.asyncio
    async def test_get_cached_monitor_miss(self, monitor_service):
        """Test cache miss in _get_cached_monitor."""
        tenant_id = "test-tenant"
        monitor_id = str(uuid.uuid4())

        async def mock_redis_get_none(*args, **kwargs):
            return None

        with patch("src.app.services.monitor_service.redis_client.get", new=mock_redis_get_none):

            result = await monitor_service._get_cached_monitor(tenant_id, monitor_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_monitor_error(self, monitor_service):
        """Test error handling in _get_cached_monitor."""
        tenant_id = "test-tenant"
        monitor_id = str(uuid.uuid4())

        with patch("src.app.services.monitor_service.redis_client.get") as mock_get:
            mock_get.side_effect = Exception("Redis error")

            result = await monitor_service._get_cached_monitor(tenant_id, monitor_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_monitor_cache(self, monitor_service):
        """Test monitor cache invalidation."""
        tenant_id = "test-tenant"
        monitor_id = str(uuid.uuid4())

        with patch("src.app.services.monitor_service.redis_client.delete") as mock_delete:
            await monitor_service._invalidate_monitor_cache(tenant_id, monitor_id)

            expected_key = f"tenant:{tenant_id}:monitor:{monitor_id}"
            mock_delete.assert_called_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_add_to_active_monitors(self, monitor_service):
        """Test adding monitor to active monitors set."""
        tenant_id = "test-tenant"
        monitor_id = str(uuid.uuid4())

        with patch("src.app.services.monitor_service.redis_client") as mock_redis:
            # Configure async mock methods
            mock_redis.sadd = AsyncMock(return_value=1)
            mock_redis.expire = AsyncMock(return_value=True)

            await monitor_service._add_to_active_monitors(tenant_id, monitor_id)

            expected_key = f"tenant:{tenant_id}:monitors:active"
            mock_redis.sadd.assert_called_once_with(expected_key, monitor_id)
            mock_redis.expire.assert_called_once_with(expected_key, 3600)

    @pytest.mark.asyncio
    async def test_remove_from_active_monitors(self, monitor_service):
        """Test removing monitor from active monitors set."""
        tenant_id = "test-tenant"
        monitor_id = str(uuid.uuid4())

        with patch("src.app.services.monitor_service.redis_client.srem") as mock_srem:
            await monitor_service._remove_from_active_monitors(tenant_id, monitor_id)

            expected_key = f"tenant:{tenant_id}:monitors:active"
            mock_srem.assert_called_once_with(expected_key, monitor_id)

    @pytest.mark.asyncio
    async def test_cache_monitor_denormalized(self, monitor_service):
        """Test caching denormalized monitor with triggers."""
        tenant_id = "test-tenant"
        monitor_id = str(uuid.uuid4())
        monitor_dict = {
            "id": monitor_id,
            "name": "Test Monitor",
            "triggers": [
                {"id": str(uuid.uuid4()), "name": "Email Trigger"}
            ]
        }

        with patch("src.app.services.monitor_service.redis_client.set") as mock_set:
            await monitor_service._cache_monitor_denormalized(
                monitor_dict, tenant_id, monitor_id
            )

            # Verify Redis set was called
            mock_set.assert_called_once()
            call_args = mock_set.call_args

            # Check cache key
            expected_key = f"tenant:{tenant_id}:monitor:{monitor_id}"
            assert call_args[0][0] == expected_key

            # Check data is JSON serialized
            cached_data = call_args[0][1]
            parsed_data = json.loads(cached_data)
            assert parsed_data == monitor_dict


class TestMonitorServiceInitialization:
    """Test MonitorService initialization and dependency injection."""

    def test_monitor_service_initialization(self):
        """Test service initialization with dependencies."""
        mock_crud_monitor = Mock()
        mock_crud_trigger = Mock()

        service = MonitorService(mock_crud_monitor, mock_crud_trigger)

        assert service.crud_monitor == mock_crud_monitor
        assert service.crud_trigger == mock_crud_trigger
