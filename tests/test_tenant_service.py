"""
Comprehensive unit tests for TenantService class.
Tests multi-tenant operations, cache management, and tenant lifecycle.
"""

import json
import uuid
from datetime import UTC
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.schemas.tenant import TenantCreate, TenantCreateInternal, TenantRead, TenantUpdate
from src.app.services.tenant_service import TenantService


class TestTenantService:
    """Test suite for TenantService."""

    @pytest.fixture
    def mock_crud_tenant(self):
        """Mock tenant CRUD operations."""
        mock = Mock()
        mock.create = AsyncMock()
        mock.get = AsyncMock()
        mock.update = AsyncMock()
        mock.delete = AsyncMock()
        mock.get_paginated = AsyncMock()
        mock.get_by_slug = AsyncMock()
        return mock

    @pytest.fixture
    def tenant_service(self, mock_crud_tenant):
        """Create tenant service instance."""
        return TenantService(mock_crud_tenant)

    @pytest.fixture
    def sample_tenant_create(self):
        """Sample tenant creation data."""
        return TenantCreate(
            name="Test Company",
            slug="test-company",
            plan="free",
            settings={"timezone": "UTC"}
        )

    @pytest.fixture
    def sample_tenant_db(self):
        """Sample tenant database entity."""
        from datetime import datetime

        # Create a simple object with attributes instead of Mock
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        return MockDBObject(
            id=uuid.uuid4(),
            name="Test Company",
            slug="test-company",
            plan="free",
            settings={"timezone": "UTC"},
            status="active",
            is_active=True,
            created_at=now,
            updated_at=now
        )

    @pytest.fixture
    def sample_tenant_read(self, sample_tenant_db):
        """Sample tenant read schema."""
        return TenantRead(
            id=sample_tenant_db.id,
            name=sample_tenant_db.name,
            slug=sample_tenant_db.slug,
            plan=sample_tenant_db.plan,
            settings=sample_tenant_db.settings,
            status=sample_tenant_db.status,
            is_active=sample_tenant_db.is_active,
            created_at=sample_tenant_db.created_at,
            updated_at=sample_tenant_db.updated_at
        )

    @pytest.fixture
    def sample_tenant_update(self):
        """Sample tenant update data."""
        return TenantUpdate(
            name="Updated Company",
            description="Updated description",
            is_active=False
        )

    @pytest.mark.asyncio
    async def test_create_tenant_success(
        self,
        tenant_service,
        sample_tenant_create,
        sample_tenant_db,
        mock_db
    ):
        """Test successful tenant creation with caching."""
        # Mock CRUD create
        tenant_service.crud_tenant.create.return_value = sample_tenant_db

        with patch.object(tenant_service, "_cache_tenant") as mock_cache:
            result = await tenant_service.create_tenant(mock_db, sample_tenant_create)

            # Verify CRUD create was called with TenantCreateInternal
            tenant_service.crud_tenant.create.assert_called_once()
            call_args = tenant_service.crud_tenant.create.call_args
            assert call_args[1]["db"] == mock_db

            created_obj = call_args[1]["object"]
            assert isinstance(created_obj, TenantCreateInternal)

            # Verify caching
            mock_cache.assert_called_once_with(sample_tenant_db)

            # Verify result
            assert isinstance(result, TenantRead)
            assert result.name == sample_tenant_create.name

    @pytest.mark.asyncio
    async def test_get_tenant_cache_hit(self, tenant_service, sample_tenant_read, mock_db):
        """Test get_tenant with cache hit."""
        tenant_id = sample_tenant_read.id

        with patch.object(tenant_service, "_get_cached_tenant") as mock_get_cached:
            mock_get_cached.return_value = sample_tenant_read

            result = await tenant_service.get_tenant(mock_db, tenant_id)

            # Verify cache was checked
            mock_get_cached.assert_called_once_with(str(tenant_id))

            # Verify CRUD get was NOT called (cache hit)
            tenant_service.crud_tenant.get.assert_not_called()

            # Verify result
            assert result == sample_tenant_read

    @pytest.mark.asyncio
    async def test_get_tenant_cache_miss(
        self,
        tenant_service,
        sample_tenant_db,
        sample_tenant_read,
        mock_db
    ):
        """Test get_tenant with cache miss."""
        tenant_id = sample_tenant_db.id

        # Mock cache miss and database hit
        tenant_service.crud_tenant.get.return_value = sample_tenant_db

        with patch.object(tenant_service, "_get_cached_tenant") as mock_get_cached, \
             patch.object(tenant_service, "_cache_tenant") as mock_cache:
            mock_get_cached.return_value = None

            result = await tenant_service.get_tenant(mock_db, tenant_id)

            # Verify cache was checked
            mock_get_cached.assert_called_once_with(str(tenant_id))

            # Verify CRUD get was called
            tenant_service.crud_tenant.get.assert_called_once_with(db=mock_db, id=tenant_id)

            # Verify cache was refreshed
            mock_cache.assert_called_once_with(sample_tenant_db)

            # Verify result
            assert isinstance(result, TenantRead)

    @pytest.mark.asyncio
    async def test_get_tenant_with_string_id(
        self,
        tenant_service,
        sample_tenant_db,
        mock_db
    ):
        """Test get_tenant with string UUID."""
        tenant_id = "550e8400-e29b-41d4-a716-446655440000"

        tenant_service.crud_tenant.get.return_value = sample_tenant_db

        with patch.object(tenant_service, "_get_cached_tenant") as mock_get_cached, \
             patch.object(tenant_service, "_cache_tenant"):
            mock_get_cached.return_value = None

            result = await tenant_service.get_tenant(mock_db, tenant_id)

            # Verify cache was checked with string ID
            mock_get_cached.assert_called_once_with(tenant_id)

            # Verify CRUD get was called with original ID (string or UUID)
            tenant_service.crud_tenant.get.assert_called_once_with(db=mock_db, id=tenant_id)

            assert isinstance(result, TenantRead)

    @pytest.mark.asyncio
    async def test_get_tenant_not_found(self, tenant_service, mock_db):
        """Test get_tenant when tenant not found."""
        tenant_id = uuid.uuid4()

        # Mock cache miss and database miss
        tenant_service.crud_tenant.get.return_value = None

        with patch.object(tenant_service, "_get_cached_tenant") as mock_get_cached:
            mock_get_cached.return_value = None

            result = await tenant_service.get_tenant(mock_db, tenant_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_tenant_cache_disabled(
        self,
        tenant_service,
        sample_tenant_db,
        mock_db
    ):
        """Test get_tenant with caching disabled."""
        tenant_id = sample_tenant_db.id

        tenant_service.crud_tenant.get.return_value = sample_tenant_db

        with patch.object(tenant_service, "_get_cached_tenant") as mock_get_cached:
            result = await tenant_service.get_tenant(
                mock_db,
                tenant_id,
                use_cache=False
            )

            # Verify cache was NOT checked
            mock_get_cached.assert_not_called()

            # Verify CRUD get was called
            tenant_service.crud_tenant.get.assert_called_once()

            # Verify result
            assert isinstance(result, TenantRead)

    @pytest.mark.asyncio
    async def test_update_tenant_success(
        self,
        tenant_service,
        sample_tenant_update,
        sample_tenant_db,
        mock_db
    ):
        """Test successful tenant update with cache refresh."""
        tenant_id = sample_tenant_db.id

        # Create updated tenant with actual values for Pydantic validation
        from datetime import datetime

        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        # Merge the existing values with updates
        updated_tenant = MockDBObject(
            id=sample_tenant_db.id,
            name=sample_tenant_update.name or sample_tenant_db.name,
            slug=sample_tenant_db.slug,
            plan=sample_tenant_db.plan,
            settings=sample_tenant_db.settings,
            status=sample_tenant_db.status,
            description=sample_tenant_update.description if hasattr(sample_tenant_update, 'description') and sample_tenant_update.description is not None else getattr(sample_tenant_db, 'description', None),
            is_active=sample_tenant_update.is_active if hasattr(sample_tenant_update, 'is_active') and sample_tenant_update.is_active is not None else sample_tenant_db.is_active,
            created_at=sample_tenant_db.created_at,
            updated_at=now
        )
        tenant_service.crud_tenant.update.return_value = updated_tenant

        with patch.object(tenant_service, "_invalidate_tenant_cache") as mock_invalidate, \
             patch.object(tenant_service, "_cache_tenant") as mock_cache:

            result = await tenant_service.update_tenant(
                mock_db,
                tenant_id,
                sample_tenant_update
            )

            # Verify CRUD update was called
            tenant_service.crud_tenant.update.assert_called_once_with(
                db=mock_db,
                object=sample_tenant_update,
                id=tenant_id
            )

            # Verify cache operations
            mock_invalidate.assert_called_once_with(str(tenant_id))
            mock_cache.assert_called_once_with(updated_tenant)

            # Verify result
            assert isinstance(result, TenantRead)

    @pytest.mark.asyncio
    async def test_update_tenant_not_found(
        self,
        tenant_service,
        sample_tenant_update,
        mock_db
    ):
        """Test update_tenant when tenant not found."""
        tenant_id = uuid.uuid4()

        tenant_service.crud_tenant.update.return_value = None

        result = await tenant_service.update_tenant(
            mock_db,
            tenant_id,
            sample_tenant_update
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_tenant_success(
        self,
        tenant_service,
        sample_tenant_db,
        mock_db
    ):
        """Test successful tenant deletion with cache cleanup."""
        tenant_id = sample_tenant_db.id

        with patch.object(tenant_service, "_invalidate_tenant_cache") as mock_invalidate, \
             patch.object(tenant_service, "_cleanup_tenant_cache") as mock_cleanup:

            result = await tenant_service.delete_tenant(mock_db, tenant_id)

            # Verify CRUD delete was called
            tenant_service.crud_tenant.delete.assert_called_once_with(
                db=mock_db,
                id=tenant_id,
                is_hard_delete=False
            )

            # Verify cache cleanup
            mock_invalidate.assert_called_once_with(str(tenant_id))
            mock_cleanup.assert_called_once_with(str(tenant_id))

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_tenant_hard_delete(
        self,
        tenant_service,
        sample_tenant_db,
        mock_db
    ):
        """Test tenant hard deletion."""
        tenant_id = sample_tenant_db.id

        with patch.object(tenant_service, "_invalidate_tenant_cache"), \
             patch.object(tenant_service, "_cleanup_tenant_cache"):

            result = await tenant_service.delete_tenant(
                mock_db,
                tenant_id,
                is_hard_delete=True
            )

            # Verify hard delete was passed through
            tenant_service.crud_tenant.delete.assert_called_once_with(
                db=mock_db,
                id=tenant_id,
                is_hard_delete=True
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_tenant_failure(
        self,
        tenant_service,
        sample_tenant_db,
        mock_db
    ):
        """Test tenant deletion failure."""
        tenant_id = sample_tenant_db.id

        # Mock deletion failure
        tenant_service.crud_tenant.delete.side_effect = Exception("Database error")

        with patch.object(tenant_service, "_invalidate_tenant_cache") as mock_invalidate, \
             patch.object(tenant_service, "_cleanup_tenant_cache") as mock_cleanup:

            result = await tenant_service.delete_tenant(mock_db, tenant_id)

            # Verify cache was NOT cleaned up on failure
            mock_invalidate.assert_not_called()
            mock_cleanup.assert_not_called()

            assert result is False

    @pytest.mark.asyncio
    async def test_list_tenants_success(self, tenant_service, mock_db):
        """Test listing tenants with pagination."""
        # Mock paginated result
        from datetime import datetime

        # Create a simple object with attributes instead of Mock
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        mock_tenants = [MockDBObject(
            id=uuid.uuid4(),
            name=f"Tenant {i}",
            slug=f"tenant-{i}",
            plan="free",
            settings={"timezone": "UTC"},
            status="active",
            is_active=True,
            created_at=now,
            updated_at=now
        ) for i in range(3)]
        paginated_result = {
            "items": mock_tenants,
            "total": 3,
            "page": 1,
            "size": 50,
            "pages": 1
        }
        tenant_service.crud_tenant.get_paginated.return_value = paginated_result

        result = await tenant_service.list_tenants(mock_db, page=1, size=50)

        # Verify CRUD get_paginated was called
        tenant_service.crud_tenant.get_paginated.assert_called_once_with(
            db=mock_db,
            page=1,
            size=50,
            filters=None,
            sort=None
        )

        # Verify result structure
        assert "items" in result
        assert len(result["items"]) == 3
        assert all(isinstance(item, TenantRead) for item in result["items"])

    @pytest.mark.asyncio
    async def test_get_tenant_by_slug_success(
        self,
        tenant_service,
        sample_tenant_db,
        mock_db
    ):
        """Test getting tenant by slug."""
        slug = "test-company"

        tenant_service.crud_tenant.get_by_slug.return_value = sample_tenant_db

        with patch.object(tenant_service, "_cache_tenant") as mock_cache:
            result = await tenant_service.get_tenant_by_slug(mock_db, slug)

            # Verify CRUD get_by_slug was called
            tenant_service.crud_tenant.get_by_slug.assert_called_once_with(
                db=mock_db,
                slug=slug
            )

            # Verify caching
            mock_cache.assert_called_once_with(sample_tenant_db)

            # Verify result
            assert isinstance(result, TenantRead)

    @pytest.mark.asyncio
    async def test_get_tenant_by_slug_not_found(self, tenant_service, mock_db):
        """Test get_tenant_by_slug when tenant not found."""
        slug = "nonexistent-slug"

        tenant_service.crud_tenant.get_by_slug.return_value = None

        result = await tenant_service.get_tenant_by_slug(mock_db, slug)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_tenant_by_slug_cache_disabled(
        self,
        tenant_service,
        sample_tenant_db,
        mock_db
    ):
        """Test get_tenant_by_slug with caching disabled."""
        slug = "test-company"

        tenant_service.crud_tenant.get_by_slug.return_value = sample_tenant_db

        with patch.object(tenant_service, "_cache_tenant") as mock_cache:
            result = await tenant_service.get_tenant_by_slug(
                mock_db,
                slug,
                use_cache=False
            )

            # Verify no caching
            mock_cache.assert_not_called()

            # Verify result
            assert isinstance(result, TenantRead)

    @pytest.mark.asyncio
    async def test_get_tenant_stats_success(
        self,
        tenant_service,
        sample_tenant_read,
        mock_db
    ):
        """Test getting tenant statistics."""
        tenant_id = sample_tenant_read.id

        with patch.object(tenant_service, "get_tenant") as mock_get_tenant, \
             patch("src.app.services.tenant_service.redis_client.smembers") as mock_smembers:

            mock_get_tenant.return_value = sample_tenant_read
            mock_smembers.return_value = {"monitor1", "monitor2", "monitor3"}

            result = await tenant_service.get_tenant_stats(mock_db, tenant_id)

            # Verify tenant lookup
            mock_get_tenant.assert_called_once_with(mock_db, tenant_id)

            # Verify result structure
            assert result["tenant_id"] == str(tenant_id)
            assert result["tenant_name"] == sample_tenant_read.name
            assert result["active_monitors"] == 3
            assert result["is_active"] == sample_tenant_read.is_active

    @pytest.mark.asyncio
    async def test_get_tenant_stats_tenant_not_found(self, tenant_service, mock_db):
        """Test get_tenant_stats when tenant not found."""
        tenant_id = uuid.uuid4()

        with patch.object(tenant_service, "get_tenant") as mock_get_tenant:
            mock_get_tenant.return_value = None

            result = await tenant_service.get_tenant_stats(mock_db, tenant_id)

            assert result == {}

    @pytest.mark.asyncio
    async def test_get_tenant_stats_redis_error(
        self,
        tenant_service,
        sample_tenant_read,
        mock_db
    ):
        """Test get_tenant_stats with Redis error."""
        tenant_id = sample_tenant_read.id

        with patch.object(tenant_service, "get_tenant") as mock_get_tenant, \
             patch("src.app.services.tenant_service.redis_client.smembers") as mock_smembers:

            mock_get_tenant.return_value = sample_tenant_read
            mock_smembers.side_effect = Exception("Redis error")

            result = await tenant_service.get_tenant_stats(mock_db, tenant_id)

            # Should still return basic stats with 0 monitors
            assert result["active_monitors"] == 0


class TestTenantServiceCachingMethods:
    """Test Redis caching helper methods."""

    @pytest.fixture
    def tenant_service(self):
        """Create tenant service for testing cache methods."""
        return TenantService(Mock())

    @pytest.fixture
    def sample_tenant(self):
        """Sample tenant for caching tests."""
        from datetime import datetime

        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        return MockDBObject(
            id=uuid.uuid4(),
            name="Test Tenant",
            slug="test-tenant",
            plan="free",
            settings={"timezone": "UTC"},
            status="active",
            is_active=True,
            created_at=now,
            updated_at=now
        )

    @pytest.mark.asyncio
    async def test_cache_tenant_success(self, tenant_service, sample_tenant):
        """Test successful tenant caching."""
        with patch("src.app.services.tenant_service.redis_client.set") as mock_set:
            await tenant_service._cache_tenant(sample_tenant)

            # Verify Redis set was called
            mock_set.assert_called_once()
            call_args = mock_set.call_args

            # Check cache key
            expected_key = f"tenant:{sample_tenant.id}:config"
            assert call_args[0][0] == expected_key

            # Check expiration
            assert call_args[1]["expiration"] == 3600

    @pytest.mark.asyncio
    async def test_cache_tenant_error(self, tenant_service, sample_tenant):
        """Test error handling in _cache_tenant."""
        with patch("src.app.services.tenant_service.redis_client.set") as mock_set:
            mock_set.side_effect = Exception("Redis error")

            # Should not raise exception
            await tenant_service._cache_tenant(sample_tenant)

    @pytest.mark.asyncio
    async def test_get_cached_tenant_hit(self, tenant_service):
        """Test cache hit in _get_cached_tenant."""
        tenant_id = str(uuid.uuid4())

        from datetime import datetime
        now = datetime.now(UTC)

        cached_data = {
            "id": tenant_id,
            "name": "Cached Tenant",
            "slug": "cached-tenant",
            "plan": "free",
            "settings": {"timezone": "UTC"},
            "status": "active",
            "is_active": True,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }

        with patch("src.app.services.tenant_service.redis_client.get") as mock_get:
            mock_get.return_value = json.dumps(cached_data)

            result = await tenant_service._get_cached_tenant(tenant_id)

            assert result is not None
            assert isinstance(result, TenantRead)
            assert result.name == "Cached Tenant"

    @pytest.mark.asyncio
    async def test_get_cached_tenant_miss(self, tenant_service):
        """Test cache miss in _get_cached_tenant."""
        tenant_id = str(uuid.uuid4())

        with patch("src.app.services.tenant_service.redis_client.get") as mock_get:
            mock_get.return_value = None

            result = await tenant_service._get_cached_tenant(tenant_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_tenant_with_dict(self, tenant_service):
        """Test _get_cached_tenant with dictionary data."""
        tenant_id = str(uuid.uuid4())

        from datetime import datetime
        now = datetime.now(UTC)

        cached_data = {
            "id": tenant_id,
            "name": "Dict Tenant",
            "slug": "dict-tenant",
            "plan": "free",
            "settings": {"timezone": "UTC"},
            "status": "active",
            "is_active": True,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }

        with patch("src.app.services.tenant_service.redis_client.get") as mock_get:
            mock_get.return_value = cached_data

            result = await tenant_service._get_cached_tenant(tenant_id)

            assert result is not None
            assert isinstance(result, TenantRead)

    @pytest.mark.asyncio
    async def test_get_cached_tenant_error(self, tenant_service):
        """Test error handling in _get_cached_tenant."""
        tenant_id = str(uuid.uuid4())

        with patch("src.app.services.tenant_service.redis_client.get") as mock_get:
            mock_get.side_effect = Exception("Redis error")

            result = await tenant_service._get_cached_tenant(tenant_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_tenant_cache(self, tenant_service):
        """Test tenant cache invalidation."""
        tenant_id = str(uuid.uuid4())

        with patch("src.app.services.tenant_service.redis_client.delete") as mock_delete:
            await tenant_service._invalidate_tenant_cache(tenant_id)

            expected_key = f"tenant:{tenant_id}:config"
            mock_delete.assert_called_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_invalidate_tenant_cache_error(self, tenant_service):
        """Test error handling in _invalidate_tenant_cache."""
        tenant_id = str(uuid.uuid4())

        with patch("src.app.services.tenant_service.redis_client.delete") as mock_delete:
            mock_delete.side_effect = Exception("Redis error")

            # Should not raise exception
            await tenant_service._invalidate_tenant_cache(tenant_id)

    @pytest.mark.asyncio
    async def test_cleanup_tenant_cache_success(self, tenant_service):
        """Test successful tenant cache cleanup."""
        tenant_id = str(uuid.uuid4())

        with patch("src.app.services.tenant_service.redis_client.delete_pattern") as mock_delete_pattern:
            mock_delete_pattern.return_value = 5

            await tenant_service._cleanup_tenant_cache(tenant_id)

            # Verify pattern deletion was called
            expected_pattern = f"tenant:{tenant_id}:*"
            mock_delete_pattern.assert_called_once_with(expected_pattern)

    @pytest.mark.asyncio
    async def test_cleanup_tenant_cache_error(self, tenant_service):
        """Test error handling in _cleanup_tenant_cache."""
        tenant_id = str(uuid.uuid4())

        with patch("src.app.services.tenant_service.redis_client.delete_pattern") as mock_delete_pattern:
            mock_delete_pattern.side_effect = Exception("Redis error")

            # Should not raise exception
            await tenant_service._cleanup_tenant_cache(tenant_id)


class TestTenantServiceInitialization:
    """Test TenantService initialization and dependency injection."""

    def test_tenant_service_initialization(self):
        """Test service initialization with dependencies."""
        mock_crud_tenant = Mock()

        service = TenantService(mock_crud_tenant)

        assert service.crud_tenant == mock_crud_tenant


class TestTenantServiceEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.fixture
    def tenant_service(self):
        """Create tenant service for edge case testing."""
        return TenantService(Mock())

    @pytest.mark.asyncio
    async def test_get_tenant_with_uuid_object(self, tenant_service, mock_db):
        """Test get_tenant with UUID object."""
        tenant_id = uuid.uuid4()

        # Create mock tenant with all required fields
        from datetime import datetime

        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        mock_tenant = MockDBObject(
            id=tenant_id,
            name="Test Tenant",
            slug="test-tenant",
            plan="free",
            settings={"timezone": "UTC"},
            status="active",
            is_active=True,
            created_at=now,
            updated_at=now
        )
        # Use AsyncMock for async method
        tenant_service.crud_tenant.get = AsyncMock(return_value=mock_tenant)

        with patch.object(tenant_service, "_get_cached_tenant") as mock_get_cached, \
             patch.object(tenant_service, "_cache_tenant"):
            mock_get_cached.return_value = None

            result = await tenant_service.get_tenant(mock_db, tenant_id)

            # Verify cache was checked with string conversion
            mock_get_cached.assert_called_once_with(str(tenant_id))

            assert isinstance(result, TenantRead)

    @pytest.mark.asyncio
    async def test_update_tenant_with_string_id(self, tenant_service, mock_db):
        """Test update_tenant with string UUID."""
        tenant_id = "550e8400-e29b-41d4-a716-446655440000"
        update_data = TenantUpdate(name="Updated Tenant")

        from datetime import datetime

        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        mock_tenant = MockDBObject(
            id=uuid.UUID(tenant_id),
            name="Updated Tenant",
            slug="updated-tenant",
            plan="free",
            settings={"timezone": "UTC"},
            status="active",
            is_active=True,
            created_at=now,
            updated_at=now
        )
        # Use AsyncMock for async method
        tenant_service.crud_tenant.update = AsyncMock(return_value=mock_tenant)

        with patch.object(tenant_service, "_invalidate_tenant_cache") as mock_invalidate, \
             patch.object(tenant_service, "_cache_tenant"):

            result = await tenant_service.update_tenant(mock_db, tenant_id, update_data)

            # Verify cache invalidation used string ID
            mock_invalidate.assert_called_once_with(tenant_id)

            assert isinstance(result, TenantRead)

    @pytest.mark.asyncio
    async def test_get_tenant_stats_with_string_id(self, tenant_service, mock_db):
        """Test get_tenant_stats with string UUID."""
        tenant_id = "550e8400-e29b-41d4-a716-446655440000"

        from datetime import datetime
        now = datetime.now(UTC)

        mock_tenant = TenantRead(
            id=uuid.UUID(tenant_id),
            name="Test Tenant",
            slug="test-tenant",
            plan="free",
            settings={"timezone": "UTC"},
            status="active",
            is_active=True,
            created_at=now,
            updated_at=now
        )

        with patch.object(tenant_service, "get_tenant") as mock_get_tenant, \
             patch("src.app.services.tenant_service.redis_client.smembers") as mock_smembers:

            mock_get_tenant.return_value = mock_tenant
            mock_smembers.return_value = set()

            result = await tenant_service.get_tenant_stats(mock_db, tenant_id)

            # Verify stats returned with string ID
            assert result["tenant_id"] == tenant_id
