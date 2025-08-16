"""
Comprehensive unit tests for NetworkService class.
Tests platform-managed resources, slug-based access, and network lifecycle.
"""

import json
import uuid
from datetime import UTC
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.schemas.network import NetworkCreate, NetworkCreateInternal, NetworkRead, NetworkUpdate
from src.app.services.network_service import NetworkService


class TestNetworkService:
    """Test suite for NetworkService."""

    @pytest.fixture
    def mock_crud_network(self):
        """Mock network CRUD operations."""
        mock = Mock()
        mock.create = AsyncMock()
        mock.get = AsyncMock()
        mock.update = AsyncMock()
        mock.delete = AsyncMock()
        mock.get_paginated = AsyncMock()
        mock.get_multi = AsyncMock()
        mock.get_by_slug = AsyncMock()
        return mock

    @pytest.fixture
    def network_service(self, mock_crud_network):
        """Create network service instance."""
        return NetworkService(mock_crud_network)

    @pytest.fixture
    def sample_network_create(self):
        """Sample network creation data."""
        return NetworkCreate(
            name="Ethereum Mainnet",
            slug="ethereum",
            network_type="EVM",
            block_time_ms=12000,
            chain_id=1,
            rpc_urls=[{"url": "https://eth-mainnet.g.alchemy.com/v2/xxx", "type_": "primary", "weight": 1}],
            tenant_id=uuid.uuid4()
        )

    @pytest.fixture
    def sample_network_db(self):
        """Sample network database entity."""
        from datetime import datetime

        # Create a simple object with attributes instead of Mock
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        return MockDBObject(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name="Ethereum Mainnet",
            slug="ethereum",
            network_type="EVM",
            block_time_ms=12000,
            chain_id=1,
            rpc_urls=[{"url": "https://eth-mainnet.g.alchemy.com/v2/xxx", "type_": "primary", "weight": 1}],
            active=True,
            validated=True,
            validation_errors=None,
            last_validated_at=now,
            created_at=now,
            updated_at=now
        )

    @pytest.fixture
    def sample_network_read(self, sample_network_db):
        """Sample network read schema."""
        return NetworkRead(
            id=sample_network_db.id,
            tenant_id=sample_network_db.tenant_id,
            name=sample_network_db.name,
            slug=sample_network_db.slug,
            network_type=sample_network_db.network_type,
            block_time_ms=sample_network_db.block_time_ms,
            chain_id=sample_network_db.chain_id,
            rpc_urls=sample_network_db.rpc_urls,
            active=sample_network_db.active,
            validated=sample_network_db.validated,
            validation_errors=sample_network_db.validation_errors,
            last_validated_at=sample_network_db.last_validated_at,
            created_at=sample_network_db.created_at,
            updated_at=sample_network_db.updated_at
        )

    @pytest.fixture
    def sample_network_update(self):
        """Sample network update data."""
        return NetworkUpdate(
            name="Ethereum Mainnet Updated",
            rpc_urls=[{"url": "https://eth-mainnet.g.alchemy.com/v2/yyy", "type_": "primary", "weight": 1}]
        )

    @pytest.mark.asyncio
    async def test_create_network_success(
        self,
        network_service,
        sample_network_create,
        sample_network_db,
        mock_db
    ):
        """Test successful network creation with caching."""
        # Mock CRUD create
        network_service.crud_network.create.return_value = sample_network_db

        with patch.object(network_service, "_cache_network") as mock_cache:
            result = await network_service.create_network(mock_db, sample_network_create)

            # Verify CRUD create was called with NetworkCreateInternal
            network_service.crud_network.create.assert_called_once()
            call_args = network_service.crud_network.create.call_args
            assert call_args[1]["db"] == mock_db

            created_obj = call_args[1]["object"]
            assert isinstance(created_obj, NetworkCreateInternal)

            # Verify caching
            mock_cache.assert_called_once_with(sample_network_db)

            # Verify result
            assert isinstance(result, NetworkRead)
            assert result.name == sample_network_create.name

    @pytest.mark.asyncio
    async def test_get_network_cache_hit(
        self,
        network_service,
        sample_network_read,
        mock_db
    ):
        """Test get_network with cache hit."""
        network_id = str(sample_network_read.id)

        with patch.object(network_service, "_get_cached_network_by_id") as mock_get_cached:
            mock_get_cached.return_value = sample_network_read

            result = await network_service.get_network(mock_db, network_id)

            # Verify cache was checked
            mock_get_cached.assert_called_once_with(network_id)

            # Verify CRUD get was NOT called (cache hit)
            network_service.crud_network.get.assert_not_called()

            # Verify result
            assert result == sample_network_read

    @pytest.mark.asyncio
    async def test_get_network_cache_miss(
        self,
        network_service,
        sample_network_db,
        sample_network_read,
        mock_db
    ):
        """Test get_network with cache miss."""
        network_id = str(sample_network_db.id)

        # Mock cache miss and database hit
        network_service.crud_network.get.return_value = sample_network_db

        with patch.object(network_service, "_get_cached_network_by_id") as mock_get_cached, \
             patch.object(network_service, "_cache_network") as mock_cache:
            mock_get_cached.return_value = None

            result = await network_service.get_network(mock_db, network_id)

            # Verify cache was checked
            mock_get_cached.assert_called_once_with(network_id)

            # Verify CRUD get was called
            network_service.crud_network.get.assert_called_once_with(db=mock_db, id=network_id)

            # Verify cache was refreshed
            mock_cache.assert_called_once_with(sample_network_db)

            # Verify result
            assert isinstance(result, NetworkRead)

    @pytest.mark.asyncio
    async def test_get_network_not_found(self, network_service, mock_db):
        """Test get_network when network not found."""
        network_id = str(uuid.uuid4())

        # Mock cache miss and database miss
        network_service.crud_network.get.return_value = None

        with patch.object(network_service, "_get_cached_network_by_id") as mock_get_cached:
            mock_get_cached.return_value = None

            result = await network_service.get_network(mock_db, network_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_network_cache_disabled(
        self,
        network_service,
        sample_network_db,
        mock_db
    ):
        """Test get_network with caching disabled."""
        network_id = str(sample_network_db.id)

        network_service.crud_network.get.return_value = sample_network_db

        with patch.object(network_service, "_get_cached_network_by_id") as mock_get_cached:
            result = await network_service.get_network(
                mock_db,
                network_id,
                use_cache=False
            )

            # Verify cache was NOT checked
            mock_get_cached.assert_not_called()

            # Verify CRUD get was called
            network_service.crud_network.get.assert_called_once()

            # Verify result
            assert isinstance(result, NetworkRead)

    @pytest.mark.asyncio
    async def test_get_network_by_slug_cache_hit(
        self,
        network_service,
        sample_network_read,
        mock_db
    ):
        """Test get_network_by_slug with cache hit."""
        slug = "ethereum"

        with patch.object(network_service, "_get_cached_network_by_slug") as mock_get_cached:
            mock_get_cached.return_value = sample_network_read

            result = await network_service.get_network_by_slug(mock_db, slug)

            # Verify cache was checked
            mock_get_cached.assert_called_once_with(slug)

            # Verify CRUD get_by_slug was NOT called (cache hit)
            network_service.crud_network.get_by_slug.assert_not_called()

            # Verify result
            assert result == sample_network_read

    @pytest.mark.asyncio
    async def test_get_network_by_slug_cache_miss(
        self,
        network_service,
        sample_network_db,
        mock_db
    ):
        """Test get_network_by_slug with cache miss."""
        slug = "ethereum"

        # Mock cache miss and database hit
        network_service.crud_network.get_by_slug.return_value = sample_network_db

        with patch.object(network_service, "_get_cached_network_by_slug") as mock_get_cached, \
             patch.object(network_service, "_cache_network") as mock_cache:
            mock_get_cached.return_value = None

            result = await network_service.get_network_by_slug(mock_db, slug)

            # Verify cache was checked
            mock_get_cached.assert_called_once_with(slug)

            # Verify CRUD get_by_slug was called
            network_service.crud_network.get_by_slug.assert_called_once_with(db=mock_db, slug=slug)

            # Verify cache was refreshed
            mock_cache.assert_called_once_with(sample_network_db)

            # Verify result
            assert isinstance(result, NetworkRead)

    @pytest.mark.asyncio
    async def test_get_network_by_slug_not_found(self, network_service, mock_db):
        """Test get_network_by_slug when network not found."""
        slug = "nonexistent-network"

        # Mock cache miss and database miss
        network_service.crud_network.get_by_slug.return_value = None

        with patch.object(network_service, "_get_cached_network_by_slug") as mock_get_cached:
            mock_get_cached.return_value = None

            result = await network_service.get_network_by_slug(mock_db, slug)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_network_by_slug_cache_disabled(
        self,
        network_service,
        sample_network_db,
        mock_db
    ):
        """Test get_network_by_slug with caching disabled."""
        slug = "ethereum"

        network_service.crud_network.get_by_slug.return_value = sample_network_db

        with patch.object(network_service, "_get_cached_network_by_slug") as mock_get_cached:
            result = await network_service.get_network_by_slug(
                mock_db,
                slug,
                use_cache=False
            )

            # Verify cache was NOT checked
            mock_get_cached.assert_not_called()

            # Verify CRUD get_by_slug was called
            network_service.crud_network.get_by_slug.assert_called_once()

            # Verify result
            assert isinstance(result, NetworkRead)

    @pytest.mark.asyncio
    async def test_update_network_success(
        self,
        network_service,
        sample_network_update,
        sample_network_db,
        mock_db
    ):
        """Test successful network update with cache refresh."""
        network_id = str(sample_network_db.id)
        old_slug = "ethereum"

        # Mock existing network lookup
        existing_network = Mock(slug=old_slug)
        network_service.crud_network.get.return_value = existing_network

        # Create updated network
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        # Get the old values and update with new ones
        old_data = vars(sample_network_db).copy()
        old_data.update(sample_network_update.model_dump(exclude_unset=True))
        updated_network = MockDBObject(**old_data)
        updated_network.slug = old_slug  # Slug typically doesn't change
        network_service.crud_network.update.return_value = updated_network

        with patch.object(network_service, "_invalidate_network_cache") as mock_invalidate, \
             patch.object(network_service, "_cache_network") as mock_cache:

            result = await network_service.update_network(
                mock_db,
                network_id,
                sample_network_update
            )

            # Verify existing network was fetched for slug
            network_service.crud_network.get.assert_called_with(db=mock_db, id=network_id)

            # Verify CRUD update was called
            network_service.crud_network.update.assert_called_once_with(
                db=mock_db,
                object=sample_network_update,
                id=network_id
            )

            # Verify cache operations
            mock_invalidate.assert_called_once_with(old_slug, network_id)
            mock_cache.assert_called_once_with(updated_network)

            # Verify result
            assert isinstance(result, NetworkRead)

    @pytest.mark.asyncio
    async def test_update_network_not_found(
        self,
        network_service,
        sample_network_update,
        mock_db
    ):
        """Test update_network when network not found initially."""
        network_id = str(uuid.uuid4())

        # Mock existing network lookup failure
        network_service.crud_network.get.return_value = None

        result = await network_service.update_network(
            mock_db,
            network_id,
            sample_network_update
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_network_update_fails(
        self,
        network_service,
        sample_network_update,
        sample_network_db,
        mock_db
    ):
        """Test update_network when update operation fails."""
        network_id = str(sample_network_db.id)

        # Mock existing network lookup success but update failure
        existing_network = Mock(slug="ethereum")
        network_service.crud_network.get.return_value = existing_network
        network_service.crud_network.update.return_value = None

        result = await network_service.update_network(
            mock_db,
            network_id,
            sample_network_update
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_network_success(
        self,
        network_service,
        sample_network_db,
        mock_db
    ):
        """Test successful network deletion with cache cleanup."""
        network_id = str(sample_network_db.id)
        slug = "ethereum"

        # Mock existing network lookup
        existing_network = Mock(slug=slug)
        network_service.crud_network.get.return_value = existing_network

        with patch.object(network_service, "_invalidate_network_cache") as mock_invalidate:
            result = await network_service.delete_network(mock_db, network_id)

            # Verify existing network was fetched for slug
            network_service.crud_network.get.assert_called_once_with(db=mock_db, id=network_id)

            # Verify CRUD delete was called
            network_service.crud_network.delete.assert_called_once_with(
                db=mock_db,
                id=network_id,
                is_hard_delete=False
            )

            # Verify cache cleanup
            mock_invalidate.assert_called_once_with(slug, network_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_network_not_found(self, network_service, mock_db):
        """Test delete_network when network not found initially."""
        network_id = str(uuid.uuid4())

        # Mock existing network lookup failure
        network_service.crud_network.get.return_value = None

        result = await network_service.delete_network(mock_db, network_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_network_hard_delete(
        self,
        network_service,
        sample_network_db,
        mock_db
    ):
        """Test network hard deletion."""
        network_id = str(sample_network_db.id)
        slug = "ethereum"

        # Mock existing network lookup
        existing_network = Mock(slug=slug)
        network_service.crud_network.get.return_value = existing_network

        with patch.object(network_service, "_invalidate_network_cache"):
            result = await network_service.delete_network(
                mock_db,
                network_id,
                is_hard_delete=True
            )

            # Verify hard delete was passed through
            network_service.crud_network.delete.assert_called_once_with(
                db=mock_db,
                id=network_id,
                is_hard_delete=True
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_network_failure(
        self,
        network_service,
        sample_network_db,
        mock_db
    ):
        """Test network deletion failure."""
        network_id = str(sample_network_db.id)
        slug = "ethereum"

        # Mock existing network lookup
        existing_network = Mock(slug=slug)
        network_service.crud_network.get.return_value = existing_network

        # Mock deletion failure
        network_service.crud_network.delete.side_effect = Exception("Database error")

        with patch.object(network_service, "_invalidate_network_cache") as mock_invalidate:
            result = await network_service.delete_network(mock_db, network_id)

            # Verify cache was NOT cleaned up on failure
            mock_invalidate.assert_not_called()

            assert result is False

    @pytest.mark.asyncio
    async def test_list_networks_success(self, network_service, mock_db):
        """Test listing networks with pagination."""
        # Mock paginated result
        from datetime import datetime

        # Create a simple object with attributes instead of Mock
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        mock_networks = [MockDBObject(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name=f"Network {i}",
            slug=f"network-{i}",
            network_type="EVM",
            block_time_ms=12000,
            rpc_urls=[{"url": f"https://rpc{i}.example.com", "type_": "primary", "weight": 1}],
            active=True,
            validated=True,
            validation_errors=None,
            last_validated_at=now,
            created_at=now,
            updated_at=now
        ) for i in range(3)]
        paginated_result = {
            "items": mock_networks,
            "total": 3,
            "page": 1,
            "size": 50,
            "pages": 1
        }
        network_service.crud_network.get_paginated.return_value = paginated_result

        result = await network_service.list_networks(mock_db, page=1, size=50)

        # Verify CRUD get_paginated was called
        network_service.crud_network.get_paginated.assert_called_once_with(
            db=mock_db,
            page=1,
            size=50,
            filters=None,
            sort=None
        )

        # Verify result structure
        assert "items" in result
        assert len(result["items"]) == 3
        assert all(isinstance(item, NetworkRead) for item in result["items"])

    @pytest.mark.asyncio
    async def test_refresh_all_networks(self, network_service, mock_db):
        """Test refreshing all platform networks in cache."""
        # Mock networks
        from datetime import datetime

        # Create a simple object with attributes instead of Mock
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        mock_networks = [
            MockDBObject(
                id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                name=f"Network {i}",
                slug=f"network-{i}",
                network_type="EVM",
                block_time_ms=12000,
                rpc_urls=[{"url": f"https://rpc{i}.example.com", "type_": "primary", "weight": 1}],
                active=True,
                validated=True,
                validation_errors=None,
                last_validated_at=now,
                created_at=now,
                updated_at=now
            )
            for i in range(3)
        ]

        # Mock get_multi result
        networks_result = {"data": mock_networks}
        network_service.crud_network.get_multi.return_value = networks_result

        with patch("src.app.services.network_service.redis_client") as mock_redis, \
             patch.object(network_service, "_cache_network") as mock_cache:

            # Configure async redis methods
            mock_redis.delete_pattern = AsyncMock(return_value=True)

            count = await network_service.refresh_all_networks(mock_db)

            # Verify cache clearing
            assert mock_redis.delete_pattern.call_count == 2  # Two patterns cleared

            # Verify caching operations
            assert mock_cache.call_count == 3

            # Verify return count
            assert count == 3

    @pytest.mark.asyncio
    async def test_refresh_all_networks_with_list_result(self, network_service, mock_db):
        """Test refresh_all_networks when get_multi returns a list."""
        # Mock networks
        from datetime import datetime

        # Create a simple object with attributes instead of Mock
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        mock_networks = [
            MockDBObject(
                id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                name=f"Network {i}",
                slug=f"network-{i}",
                network_type="EVM",
                block_time_ms=12000,
                rpc_urls=[{"url": f"https://rpc{i}.example.com", "type_": "primary", "weight": 1}],
                active=True,
                validated=True,
                validation_errors=None,
                last_validated_at=now,
                created_at=now,
                updated_at=now
            )
            for i in range(2)
        ]

        # Mock get_multi result as list
        network_service.crud_network.get_multi.return_value = mock_networks

        with patch("src.app.services.network_service.redis_client") as mock_redis, \
             patch.object(network_service, "_cache_network") as mock_cache:

            # Configure async redis methods
            mock_redis.delete_pattern = AsyncMock(return_value=True)

            count = await network_service.refresh_all_networks(mock_db)

            # Should handle empty list gracefully
            assert mock_cache.call_count == 0
            assert count == 0

    @pytest.mark.asyncio
    async def test_get_all_network_slugs_success(self, network_service, mock_db):
        """Test getting all network slugs."""
        # Mock networks
        mock_networks = [
            Mock(slug="ethereum"),
            Mock(slug="polygon"),
            Mock(slug="arbitrum")
        ]

        networks_result = {"data": mock_networks}
        network_service.crud_network.get_multi.return_value = networks_result

        result = await network_service.get_all_network_slugs(mock_db)

        # Verify CRUD get_multi was called
        network_service.crud_network.get_multi.assert_called_once_with(db=mock_db)

        # Verify result
        assert result == ["ethereum", "polygon", "arbitrum"]

    @pytest.mark.asyncio
    async def test_get_all_network_slugs_with_list_result(self, network_service, mock_db):
        """Test get_all_network_slugs when get_multi returns a list."""
        # Mock get_multi result as list (not dict)
        mock_networks = [Mock(slug="ethereum")]
        network_service.crud_network.get_multi.return_value = mock_networks

        result = await network_service.get_all_network_slugs(mock_db)

        # Should handle list result gracefully
        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_network_slugs_missing_slug_attr(self, network_service, mock_db):
        """Test get_all_network_slugs with networks missing slug attribute."""
        # Create mock networks where some don't have slug attribute
        # We need to use spec to prevent Mock from auto-creating attributes
        mock1 = Mock(spec=['slug', 'name'])
        mock1.slug = "ethereum"

        mock2 = Mock(spec=['name'])  # No slug in spec
        mock2.name = "Polygon"

        mock3 = Mock(spec=['slug', 'name'])
        mock3.slug = "arbitrum"

        mock_networks = [mock1, mock2, mock3]

        networks_result = {"data": mock_networks}
        network_service.crud_network.get_multi.return_value = networks_result

        result = await network_service.get_all_network_slugs(mock_db)

        # Should only include networks with slug attribute
        assert result == ["ethereum", "arbitrum"]


class TestNetworkServiceCachingMethods:
    """Test Redis caching helper methods."""

    @pytest.fixture
    def network_service(self):
        """Create network service for testing cache methods."""
        return NetworkService(Mock())

    @pytest.fixture
    def sample_network(self):
        """Sample network for caching tests."""
        from datetime import datetime

        # Create a simple object with attributes instead of Mock
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        return MockDBObject(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name="Ethereum Mainnet",
            slug="ethereum",
            network_type="EVM",
            block_time_ms=12000,
            chain_id=1,
            rpc_urls=[{"url": "https://eth-mainnet.g.alchemy.com/v2/xxx", "type_": "primary", "weight": 1}],
            active=True,
            validated=True,
            validation_errors=None,
            last_validated_at=now,
            created_at=now,
            updated_at=now
        )

    @pytest.mark.asyncio
    async def test_cache_network_success(self, network_service, sample_network):
        """Test successful network caching."""
        with patch("src.app.services.network_service.redis_client.set") as mock_set:
            await network_service._cache_network(sample_network)

            # Verify Redis set was called twice (slug and ID keys)
            assert mock_set.call_count == 2

            # Check calls
            calls = mock_set.call_args_list

            # First call should be slug key
            slug_call = calls[0]
            assert slug_call[0][0] == f"platform:networks:{sample_network.slug}"
            assert slug_call[1]["expiration"] == 3600

            # Second call should be ID key
            id_call = calls[1]
            assert id_call[0][0] == f"platform:network:id:{sample_network.id}"
            assert id_call[1]["expiration"] == 3600

    @pytest.mark.asyncio
    async def test_cache_network_error(self, network_service, sample_network):
        """Test error handling in _cache_network."""
        with patch("src.app.services.network_service.redis_client.set") as mock_set:
            mock_set.side_effect = Exception("Redis error")

            # Should not raise exception
            await network_service._cache_network(sample_network)

    @pytest.mark.asyncio
    async def test_get_cached_network_by_slug_hit(self, network_service):
        """Test cache hit in _get_cached_network_by_slug."""
        from datetime import datetime
        slug = "ethereum"
        now = datetime.now(UTC)

        cached_data = {
            "id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "name": "Ethereum Mainnet",
            "slug": slug,
            "network_type": "EVM",
            "block_time_ms": 12000,
            "chain_id": 1,
            "rpc_urls": [{"url": "https://eth.example.com", "type_": "primary", "weight": 1}],
            "active": True,
            "validated": True,
            "validation_errors": None,
            "last_validated_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }

        with patch("src.app.services.network_service.redis_client.get") as mock_get:
            mock_get.return_value = json.dumps(cached_data)

            result = await network_service._get_cached_network_by_slug(slug)

            assert result is not None
            assert isinstance(result, NetworkRead)
            assert result.slug == slug

    @pytest.mark.asyncio
    async def test_get_cached_network_by_slug_miss(self, network_service):
        """Test cache miss in _get_cached_network_by_slug."""
        slug = "ethereum"

        with patch("src.app.services.network_service.redis_client.get") as mock_get:
            mock_get.return_value = None

            result = await network_service._get_cached_network_by_slug(slug)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_network_by_slug_with_dict(self, network_service):
        """Test _get_cached_network_by_slug with dictionary data."""
        from datetime import datetime
        slug = "ethereum"
        now = datetime.now(UTC)

        cached_data = {
            "id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "name": "Ethereum Mainnet",
            "slug": slug,
            "network_type": "EVM",
            "block_time_ms": 12000,
            "chain_id": 1,
            "rpc_urls": [{"url": "https://eth.example.com", "type_": "primary", "weight": 1}],
            "active": True,
            "validated": True,
            "validation_errors": None,
            "last_validated_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }

        with patch("src.app.services.network_service.redis_client.get") as mock_get:
            mock_get.return_value = cached_data

            result = await network_service._get_cached_network_by_slug(slug)

            assert result is not None
            assert isinstance(result, NetworkRead)

    @pytest.mark.asyncio
    async def test_get_cached_network_by_slug_error(self, network_service):
        """Test error handling in _get_cached_network_by_slug."""
        slug = "ethereum"

        with patch("src.app.services.network_service.redis_client.get") as mock_get:
            mock_get.side_effect = Exception("Redis error")

            result = await network_service._get_cached_network_by_slug(slug)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_network_by_id_hit(self, network_service):
        """Test cache hit in _get_cached_network_by_id."""
        from datetime import datetime
        network_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        cached_data = {
            "id": network_id,
            "tenant_id": str(uuid.uuid4()),
            "name": "Ethereum Mainnet",
            "slug": "ethereum",
            "network_type": "EVM",
            "block_time_ms": 12000,
            "chain_id": 1,
            "rpc_urls": [{"url": "https://eth.example.com", "type_": "primary", "weight": 1}],
            "active": True,
            "validated": True,
            "validation_errors": None,
            "last_validated_at": now.isoformat(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }

        with patch("src.app.services.network_service.redis_client.get") as mock_get:
            mock_get.return_value = json.dumps(cached_data)

            result = await network_service._get_cached_network_by_id(network_id)

            assert result is not None
            assert isinstance(result, NetworkRead)
            assert str(result.id) == network_id

    @pytest.mark.asyncio
    async def test_get_cached_network_by_id_miss(self, network_service):
        """Test cache miss in _get_cached_network_by_id."""
        network_id = str(uuid.uuid4())

        with patch("src.app.services.network_service.redis_client.get") as mock_get:
            mock_get.return_value = None

            result = await network_service._get_cached_network_by_id(network_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_get_cached_network_by_id_error(self, network_service):
        """Test error handling in _get_cached_network_by_id."""
        network_id = str(uuid.uuid4())

        with patch("src.app.services.network_service.redis_client.get") as mock_get:
            mock_get.side_effect = Exception("Redis error")

            result = await network_service._get_cached_network_by_id(network_id)

            assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_network_cache(self, network_service):
        """Test network cache invalidation."""
        slug = "ethereum"
        network_id = str(uuid.uuid4())

        with patch("src.app.services.network_service.redis_client.delete") as mock_delete:
            await network_service._invalidate_network_cache(slug, network_id)

            # Verify both keys were deleted
            expected_slug_key = f"platform:networks:{slug}"
            expected_id_key = f"platform:network:id:{network_id}"
            mock_delete.assert_called_once_with(expected_slug_key, expected_id_key)

    @pytest.mark.asyncio
    async def test_invalidate_network_cache_error(self, network_service):
        """Test error handling in _invalidate_network_cache."""
        slug = "ethereum"
        network_id = str(uuid.uuid4())

        with patch("src.app.services.network_service.redis_client.delete") as mock_delete:
            mock_delete.side_effect = Exception("Redis error")

            # Should not raise exception
            await network_service._invalidate_network_cache(slug, network_id)


class TestNetworkServiceInitialization:
    """Test NetworkService initialization and dependency injection."""

    def test_network_service_initialization(self):
        """Test service initialization with dependencies."""
        mock_crud_network = Mock()

        service = NetworkService(mock_crud_network)

        assert service.crud_network == mock_crud_network


class TestNetworkServiceEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.fixture
    def network_service(self):
        """Create network service for edge case testing."""
        mock_crud = Mock()
        mock_crud.get = AsyncMock()
        mock_crud.update = AsyncMock()
        mock_crud.delete = AsyncMock()
        mock_crud.get_multi = AsyncMock()
        return NetworkService(mock_crud)

    @pytest.mark.asyncio
    async def test_update_network_without_slug_attribute(self, network_service, mock_db):
        """Test update_network when existing network has no slug attribute."""
        network_id = str(uuid.uuid4())
        update_data = NetworkUpdate(name="Updated Network")

        # Mock existing network without slug attribute using spec to restrict attributes
        existing_network = Mock(spec=['id', 'name'])  # No slug in spec
        existing_network.id = uuid.UUID(network_id)
        existing_network.name = "Old Network"
        network_service.crud_network.get.return_value = existing_network

        # Mock successful update - also without slug attribute
        from datetime import datetime

        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)
        updated_network = MockDBObject(
            id=uuid.UUID(network_id),
            tenant_id=uuid.uuid4(),
            name="Updated Network",
            slug="some-slug",  # Adding slug to make NetworkRead validation work
            network_type="EVM",
            block_time_ms=12000,
            chain_id=1,
            rpc_urls=[{"url": "https://eth.example.com", "type_": "primary", "weight": 1}],
            active=True,
            validated=True,
            validation_errors=None,
            last_validated_at=now,
            created_at=now,
            updated_at=now
        )
        network_service.crud_network.update.return_value = updated_network

        with patch.object(network_service, "_invalidate_network_cache") as mock_invalidate, \
             patch.object(network_service, "_cache_network"):

            result = await network_service.update_network(mock_db, network_id, update_data)

            # Verify cache invalidation was called with empty string for slug
            mock_invalidate.assert_called_once_with("", network_id)

            assert isinstance(result, NetworkRead)

    @pytest.mark.asyncio
    async def test_delete_network_without_slug_attribute(self, network_service, mock_db):
        """Test delete_network when existing network has no slug attribute."""
        network_id = str(uuid.uuid4())

        # Mock existing network without slug attribute using spec to restrict attributes
        existing_network = Mock(spec=['id', 'name'])  # No slug in spec
        existing_network.id = uuid.UUID(network_id)
        existing_network.name = "Network to Delete"
        network_service.crud_network.get.return_value = existing_network

        with patch.object(network_service, "_invalidate_network_cache") as mock_invalidate:
            result = await network_service.delete_network(mock_db, network_id)

            # Verify cache invalidation was called with empty string for slug
            mock_invalidate.assert_called_once_with("", network_id)

            assert result is True

    @pytest.mark.asyncio
    async def test_refresh_all_networks_empty_result(self, network_service, mock_db):
        """Test refresh_all_networks with empty result."""
        # Mock empty result
        network_service.crud_network.get_multi.return_value = {"data": []}

        with patch("src.app.services.network_service.redis_client") as mock_redis, \
             patch.object(network_service, "_cache_network") as mock_cache:

            # Configure async redis methods
            mock_redis.delete_pattern = AsyncMock(return_value=True)

            count = await network_service.refresh_all_networks(mock_db)

            # Verify cache clearing still happens
            assert mock_redis.delete_pattern.call_count == 2

            # Verify no caching operations
            mock_cache.assert_not_called()

            # Verify return count
            assert count == 0
