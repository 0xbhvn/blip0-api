"""
Comprehensive unit tests for BaseService class.
Tests abstract methods, cache operations, and CRUD operations with mocking.
"""

import json
import uuid
from typing import Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import BaseModel

from src.app.services.base_service import BaseService


# Test models for BaseService testing
class MockEntity(BaseModel):
    """Mock entity model for testing."""
    id: uuid.UUID
    name: str
    description: Optional[str] = None


class MockEntityCreate(BaseModel):
    """Mock entity creation schema for testing."""
    name: str
    description: Optional[str] = None


class MockEntityUpdate(BaseModel):
    """Mock entity update schema for testing."""
    name: Optional[str] = None
    description: Optional[str] = None


class MockEntityRead(BaseModel):
    """Mock entity read schema for testing."""
    id: uuid.UUID
    name: str
    description: Optional[str] = None


# Concrete implementation for testing
class ConcreteService(BaseService[MockEntity, MockEntityCreate, MockEntityUpdate, MockEntityRead]):
    """Concrete implementation of BaseService for testing."""

    def get_cache_key(self, entity_id: str, **kwargs) -> str:
        """Generate cache key for test entity."""
        tenant_id = kwargs.get("tenant_id", "default")
        return f"test:{tenant_id}:entity:{entity_id}"

    def get_cache_ttl(self) -> int:
        """Get cache TTL for test entities."""
        return 3600  # 1 hour

    @property
    def read_schema(self) -> type[MockEntityRead]:
        """Get the read schema class."""
        return MockEntityRead


class TestBaseService:
    """Test suite for BaseService abstract class."""

    @pytest.fixture
    def mock_crud(self):
        """Mock CRUD operations."""
        mock = Mock()
        mock.create = AsyncMock()
        mock.get = AsyncMock()
        mock.update = AsyncMock()
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def service(self, mock_crud):
        """Create concrete service instance for testing."""
        return ConcreteService(mock_crud)

    @pytest.fixture
    def sample_entity(self):
        """Sample entity for testing."""
        # For testing, we'll use MockEntityRead directly since that's what the service expects
        return MockEntityRead(
            id=uuid.uuid4(),
            name="Test Entity",
            description="Test description"
        )

    @pytest.fixture
    def sample_entity_create(self):
        """Sample entity creation data."""
        return MockEntityCreate(
            name="New Entity",
            description="New description"
        )

    @pytest.fixture
    def sample_entity_update(self):
        """Sample entity update data."""
        return MockEntityUpdate(
            name="Updated Entity",
            description="Updated description"
        )

    def test_service_initialization(self, mock_crud):
        """Test service initialization with CRUD dependency."""
        service = ConcreteService(mock_crud)
        assert service.crud == mock_crud

    def test_abstract_methods_implemented(self, service):
        """Test that all abstract methods are properly implemented."""
        # Test get_cache_key
        cache_key = service.get_cache_key("123", tenant_id="tenant1")
        assert cache_key == "test:tenant1:entity:123"

        # Test get_cache_key with default tenant
        cache_key_default = service.get_cache_key("123")
        assert cache_key_default == "test:default:entity:123"

        # Test get_cache_ttl
        ttl = service.get_cache_ttl()
        assert ttl == 3600

        # Test read_schema property
        assert service.read_schema == MockEntityRead

    @pytest.mark.asyncio
    async def test_cache_entity_success(self, service, sample_entity):
        """Test successful entity caching."""
        with patch("src.app.services.base_service.RedisClient.set") as mock_set:
            mock_set.return_value = True

            await service.cache_entity(sample_entity, tenant_id="test-tenant")

            # Verify Redis set was called with correct parameters
            mock_set.assert_called_once()
            call_args = mock_set.call_args

            # Check cache key
            assert call_args[0][0] == "test:test-tenant:entity:" + str(sample_entity.id)

            # Check serialized data is valid JSON
            serialized_data = call_args[0][1]
            parsed_data = json.loads(serialized_data)
            assert parsed_data["name"] == sample_entity.name
            assert parsed_data["description"] == sample_entity.description

            # Check TTL
            assert call_args[1]["expiration"] == 3600

    @pytest.mark.asyncio
    async def test_cache_entity_with_custom_key(self, service, sample_entity):
        """Test entity caching with custom cache key."""
        with patch("src.app.services.base_service.RedisClient.set") as mock_set:
            custom_key = "custom:entity:key"

            await service.cache_entity(sample_entity, cache_key=custom_key)

            mock_set.assert_called_once()
            call_args = mock_set.call_args
            assert call_args[0][0] == custom_key

    @pytest.mark.asyncio
    async def test_cache_entity_error_handling(self, service, sample_entity):
        """Test error handling in cache_entity."""
        with patch("src.app.services.base_service.RedisClient.set") as mock_set:
            mock_set.side_effect = Exception("Redis connection error")

            # Should not raise exception, only log error
            await service.cache_entity(sample_entity, tenant_id="test-tenant")

            mock_set.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cached_entity_hit(self, service, sample_entity):
        """Test cache hit in get_cached_entity."""
        cached_data = MockEntityRead.model_validate(sample_entity).model_dump_json()

        with patch("src.app.services.base_service.RedisClient.get") as mock_get:
            mock_get.return_value = cached_data

            result = await service.get_cached_entity(
                str(sample_entity.id),
                tenant_id="test-tenant"
            )

            assert result is not None
            assert result.id == sample_entity.id
            assert result.name == sample_entity.name
            assert result.description == sample_entity.description

    @pytest.mark.asyncio
    async def test_get_cached_entity_miss(self, service):
        """Test cache miss in get_cached_entity."""
        with patch("src.app.services.base_service.RedisClient.get") as mock_get:
            mock_get.return_value = None

            result = await service.get_cached_entity("123", tenant_id="test-tenant")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_entity_with_dict_data(self, service, sample_entity):
        """Test get_cached_entity with dictionary data."""
        cached_data = MockEntityRead.model_validate(sample_entity).model_dump()

        with patch("src.app.services.base_service.RedisClient.get") as mock_get:
            mock_get.return_value = cached_data

            result = await service.get_cached_entity(
                str(sample_entity.id),
                tenant_id="test-tenant"
            )

            assert result is not None
            assert result.id == sample_entity.id

    @pytest.mark.asyncio
    async def test_get_cached_entity_error_handling(self, service):
        """Test error handling in get_cached_entity."""
        with patch("src.app.services.base_service.RedisClient.get") as mock_get:
            mock_get.side_effect = Exception("Redis connection error")

            result = await service.get_cached_entity("123", tenant_id="test-tenant")

            assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_cache_success(self, service):
        """Test successful cache invalidation."""
        with patch("src.app.services.base_service.RedisClient.delete") as mock_delete:
            mock_delete.return_value = 1

            await service.invalidate_cache("123", tenant_id="test-tenant")

            mock_delete.assert_called_once_with("test:test-tenant:entity:123")

    @pytest.mark.asyncio
    async def test_invalidate_cache_with_custom_key(self, service):
        """Test cache invalidation with custom key."""
        with patch("src.app.services.base_service.RedisClient.delete") as mock_delete:
            custom_key = "custom:cache:key"

            await service.invalidate_cache("123", cache_key=custom_key)

            mock_delete.assert_called_once_with(custom_key)

    @pytest.mark.asyncio
    async def test_invalidate_cache_error_handling(self, service):
        """Test error handling in invalidate_cache."""
        with patch("src.app.services.base_service.RedisClient.delete") as mock_delete:
            mock_delete.side_effect = Exception("Redis connection error")

            # Should not raise exception
            await service.invalidate_cache("123", tenant_id="test-tenant")

            mock_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_pattern_success(self, service):
        """Test successful pattern invalidation."""
        with patch("src.app.services.base_service.RedisClient.delete_pattern") as mock_delete_pattern:
            mock_delete_pattern.return_value = 5

            count = await service.invalidate_pattern("test:*:entity:*")

            assert count == 5
            mock_delete_pattern.assert_called_once_with("test:*:entity:*")

    @pytest.mark.asyncio
    async def test_invalidate_pattern_error_handling(self, service):
        """Test error handling in invalidate_pattern."""
        with patch("src.app.services.base_service.RedisClient.delete_pattern") as mock_delete_pattern:
            mock_delete_pattern.side_effect = Exception("Redis connection error")

            count = await service.invalidate_pattern("test:*:entity:*")

            assert count == 0

    @pytest.mark.asyncio
    async def test_create_with_cache_success(self, service, sample_entity_create, sample_entity, mock_db):
        """Test successful create_with_cache operation."""
        # Mock CRUD create
        service.crud.create.return_value = sample_entity

        with patch.object(service, "cache_entity") as mock_cache:
            result = await service.create_with_cache(
                mock_db,
                sample_entity_create,
                tenant_id="test-tenant"
            )

            # Verify CRUD create was called
            service.crud.create.assert_called_once_with(db=mock_db, object=sample_entity_create)

            # Verify cache_entity was called
            mock_cache.assert_called_once_with(sample_entity, tenant_id="test-tenant")

            # Verify result
            assert isinstance(result, MockEntityRead)
            assert result.id == sample_entity.id

    @pytest.mark.asyncio
    async def test_get_with_cache_hit(self, service, sample_entity, mock_db):
        """Test get_with_cache with cache hit."""
        cached_entity = MockEntityRead.model_validate(sample_entity)

        with patch.object(service, "get_cached_entity") as mock_get_cached:
            mock_get_cached.return_value = cached_entity

            result = await service.get_with_cache(
                mock_db,
                str(sample_entity.id),
                tenant_id="test-tenant"
            )

            # Verify cache was checked
            mock_get_cached.assert_called_once_with(str(sample_entity.id), tenant_id="test-tenant")

            # Verify CRUD get was NOT called (cache hit)
            service.crud.get.assert_not_called()

            # Verify result
            assert result == cached_entity

    @pytest.mark.asyncio
    async def test_get_with_cache_miss(self, service, sample_entity, mock_db):
        """Test get_with_cache with cache miss."""
        service.crud.get.return_value = sample_entity

        with patch.object(service, "get_cached_entity") as mock_get_cached, \
             patch.object(service, "cache_entity") as mock_cache:
            mock_get_cached.return_value = None

            result = await service.get_with_cache(
                mock_db,
                str(sample_entity.id),
                tenant_id="test-tenant"
            )

            # Verify cache was checked
            mock_get_cached.assert_called_once()

            # Verify CRUD get was called (cache miss)
            service.crud.get.assert_called_once_with(db=mock_db, id=str(sample_entity.id))

            # Verify cache was refreshed
            mock_cache.assert_called_once_with(sample_entity, tenant_id="test-tenant")

            # Verify result
            assert isinstance(result, MockEntityRead)
            assert result.id == sample_entity.id

    @pytest.mark.asyncio
    async def test_get_with_cache_disabled(self, service, sample_entity, mock_db):
        """Test get_with_cache with caching disabled."""
        service.crud.get.return_value = sample_entity

        with patch.object(service, "get_cached_entity") as mock_get_cached:
            result = await service.get_with_cache(
                mock_db,
                str(sample_entity.id),
                use_cache=False,
                tenant_id="test-tenant"
            )

            # Verify cache was NOT checked
            mock_get_cached.assert_not_called()

            # Verify CRUD get was called
            service.crud.get.assert_called_once_with(db=mock_db, id=str(sample_entity.id))

            # Verify result
            assert isinstance(result, MockEntityRead)

    @pytest.mark.asyncio
    async def test_get_with_cache_not_found(self, service, mock_db):
        """Test get_with_cache when entity not found."""
        service.crud.get.return_value = None

        with patch.object(service, "get_cached_entity") as mock_get_cached:
            mock_get_cached.return_value = None

            result = await service.get_with_cache(
                mock_db,
                "nonexistent-id",
                tenant_id="test-tenant"
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_update_with_cache_success(self, service, sample_entity_update, sample_entity, mock_db):
        """Test successful update_with_cache operation."""
        # Mock CRUD update
        updated_entity = MockEntityRead(
            id=sample_entity.id,
            name=sample_entity_update.name or sample_entity.name,
            description=sample_entity_update.description or sample_entity.description
        )
        service.crud.update.return_value = updated_entity

        with patch.object(service, "invalidate_cache") as mock_invalidate, \
             patch.object(service, "cache_entity") as mock_cache:

            result = await service.update_with_cache(
                mock_db,
                str(sample_entity.id),
                sample_entity_update,
                tenant_id="test-tenant"
            )

            # Verify CRUD update was called
            service.crud.update.assert_called_once_with(
                db=mock_db,
                object=sample_entity_update,
                id=str(sample_entity.id)
            )

            # Verify cache was invalidated and refreshed
            mock_invalidate.assert_called_once_with(str(sample_entity.id), tenant_id="test-tenant")
            mock_cache.assert_called_once_with(updated_entity, tenant_id="test-tenant")

            # Verify result
            assert isinstance(result, MockEntityRead)
            assert result.name == sample_entity_update.name

    @pytest.mark.asyncio
    async def test_update_with_cache_not_found(self, service, sample_entity_update, mock_db):
        """Test update_with_cache when entity not found."""
        service.crud.update.return_value = None

        result = await service.update_with_cache(
            mock_db,
            "nonexistent-id",
            sample_entity_update,
            tenant_id="test-tenant"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_with_cache_success(self, service, sample_entity, mock_db):
        """Test successful delete_with_cache operation."""
        service.crud.delete.return_value = True

        with patch.object(service, "invalidate_cache") as mock_invalidate:
            result = await service.delete_with_cache(
                mock_db,
                str(sample_entity.id),
                tenant_id="test-tenant"
            )

            # Verify CRUD delete was called
            service.crud.delete.assert_called_once_with(
                db=mock_db,
                id=str(sample_entity.id),
                db_obj=None,
                is_hard_delete=False
            )

            # Verify cache was invalidated
            mock_invalidate.assert_called_once_with(str(sample_entity.id), tenant_id="test-tenant")

            # Verify result
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_with_cache_hard_delete(self, service, sample_entity, mock_db):
        """Test delete_with_cache with hard delete."""
        service.crud.delete.return_value = True

        with patch.object(service, "invalidate_cache"):
            result = await service.delete_with_cache(
                mock_db,
                str(sample_entity.id),
                is_hard_delete=True,
                tenant_id="test-tenant"
            )

            # Verify CRUD delete was called with hard delete
            service.crud.delete.assert_called_once_with(
                db=mock_db,
                id=str(sample_entity.id),
                db_obj=None,
                is_hard_delete=True
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_with_cache_failed(self, service, sample_entity, mock_db):
        """Test delete_with_cache when deletion fails."""
        service.crud.delete.return_value = False

        with patch.object(service, "invalidate_cache") as mock_invalidate:
            result = await service.delete_with_cache(
                mock_db,
                str(sample_entity.id),
                tenant_id="test-tenant"
            )

            # Verify cache was NOT invalidated on failed delete
            mock_invalidate.assert_not_called()

            # Verify result
            assert result is False


class TestAbstractBaseService:
    """Test that BaseService cannot be instantiated directly."""

    def test_cannot_instantiate_abstract_class(self):
        """Test that BaseService cannot be instantiated directly."""
        mock_crud = Mock()

        with pytest.raises(TypeError, match="Can't instantiate abstract class BaseService"):
            BaseService(mock_crud)  # type: ignore[abstract]


class TestCacheKeyGeneration:
    """Test cache key generation in different scenarios."""

    @pytest.fixture
    def service(self):
        """Create service with mock CRUD."""
        return ConcreteService(Mock())

    def test_cache_key_with_tenant(self, service):
        """Test cache key generation with tenant."""
        key = service.get_cache_key("entity-123", tenant_id="tenant-456")
        assert key == "test:tenant-456:entity:entity-123"

    def test_cache_key_without_tenant(self, service):
        """Test cache key generation without tenant (default)."""
        key = service.get_cache_key("entity-123")
        assert key == "test:default:entity:entity-123"

    def test_cache_key_with_additional_kwargs(self, service):
        """Test cache key generation ignores additional kwargs."""
        key = service.get_cache_key("entity-123", tenant_id="tenant-456", extra_param="value")
        assert key == "test:tenant-456:entity:entity-123"
