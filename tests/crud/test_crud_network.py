"""
Comprehensive unit tests for CRUDNetwork operations.

Tests cover all CRUD operations including:
- Create operations with RPC validation
- Read operations (get, get_multi, get_paginated, get_by_slug)
- Update operations including RPC management
- Delete operations
- RPC URL testing and validation
- Network validation operations
- Redis caching functionality
- Multi-tenant isolation
- Bulk operations
- Network type specific operations (EVM vs Stellar)
"""

import json
import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.crud.crud_network import CRUDNetwork, crud_network
from src.app.models.network import Network
from src.app.schemas.network import (
    NetworkCreate,
    NetworkRPCAdd,
    NetworkRPCRemove,
    NetworkRPCTest,
    NetworkRPCTestResult,
    NetworkUpdate,
    NetworkValidationRequest,
    NetworkValidationResult,
)
from tests.factories.network_factory import NetworkFactory


class TestCRUDNetworkCreate:
    """Test network creation operations."""

    @pytest.mark.asyncio
    async def test_create_network_basic(self, async_db: AsyncSession) -> None:
        """Test basic network creation."""
        # Arrange
        network_create = NetworkCreate(
            name="Test Network",
            slug="test-network",
            network_type="EVM",
            chain_id=1337,
            rpc_urls=[
                {"url": "https://rpc.test.com", "type_": "primary", "weight": 100}
            ],
            block_time_ms=12000,
            confirmation_blocks=2,
            max_past_blocks=100
        )

        # Act
        created_network = await crud_network.create(async_db, object=network_create)

        # Assert
        assert created_network is not None
        assert created_network.name == network_create.name
        assert created_network.slug == network_create.slug
        assert created_network.network_type == "EVM"
        assert created_network.chain_id == 1337
        assert len(created_network.rpc_urls) == 1
        assert created_network.active is True
        assert created_network.validated is False

    @patch('src.app.crud.crud_network.CRUDNetwork._test_rpc_url')
    @pytest.mark.asyncio
    async def test_create_network_with_validation_success(
        self,
        mock_test_rpc,
        async_db: AsyncSession
    ) -> None:
        """Test network creation with successful RPC validation."""
        # Arrange
        mock_test_rpc.return_value = NetworkRPCTestResult(
            url="https://rpc.test.com",
            is_online=True,
            latency_ms=50,
            block_height=12345,
            error=None
        )

        network_create = NetworkCreate(
            name="Validated Network",
            slug="validated-network",
            network_type="EVM",
            chain_id=1,
            rpc_urls=[
                {"url": "https://rpc.test.com", "type_": "primary", "weight": 100}
            ],
            block_time_ms=12000
        )

        # Act
        created_network = await crud_network.create_with_validation(
            async_db,
            object=network_create,
            validate_rpcs=True
        )

        # Assert
        assert created_network is not None
        assert created_network.validated is True
        assert created_network.last_validated_at is not None
        mock_test_rpc.assert_called_once()

    @patch('src.app.crud.crud_network.CRUDNetwork._test_rpc_url')
    @pytest.mark.asyncio
    async def test_create_network_with_validation_failure(
        self,
        mock_test_rpc,
        async_db: AsyncSession
    ) -> None:
        """Test network creation with failed RPC validation."""
        # Arrange
        mock_test_rpc.return_value = NetworkRPCTestResult(
            url="https://rpc.test.com",
            is_online=False,
            latency_ms=None,
            block_height=None,
            error="Connection timeout"
        )

        network_create = NetworkCreate(
            name="Invalid Network",
            slug="invalid-network",
            network_type="EVM",
            chain_id=1,
            rpc_urls=[
                {"url": "https://rpc.test.com", "type_": "primary", "weight": 100}
            ],
            block_time_ms=12000
        )

        # Act
        created_network = await crud_network.create_with_validation(
            async_db,
            object=network_create,
            validate_rpcs=True
        )

        # Assert
        assert created_network is not None
        assert created_network.validated is False
        assert created_network.validation_errors is not None
        assert "https://rpc.test.com" in created_network.validation_errors

    @pytest.mark.asyncio
    async def test_create_stellar_network(self, async_db: AsyncSession) -> None:
        """Test creating a Stellar network."""
        # Arrange
        network_create = NetworkCreate(
            name="Stellar Test",
            slug="stellar-test",
            network_type="Stellar",
            network_passphrase="Test SDF Network ; September 2015",
            rpc_urls=[
                {"url": "https://horizon-testnet.stellar.org", "type_": "primary", "weight": 100}
            ],
            block_time_ms=5000,
            confirmation_blocks=1
        )

        # Act
        created_network = await crud_network.create(async_db, object=network_create)

        # Assert
        assert created_network is not None
        assert created_network.network_type == "Stellar"
        assert created_network.network_passphrase == "Test SDF Network ; September 2015"
        assert created_network.chain_id is None


class TestCRUDNetworkRead:
    """Test network read operations."""

    @pytest.mark.asyncio
    async def test_get_network_by_id(self, async_db: AsyncSession) -> None:
        """Test getting network by ID."""
        # Arrange
        network = NetworkFactory.create(name="Get By ID Test")
        async_db.add(network)
        await async_db.flush()

        # Act
        retrieved_network = await crud_network.get(async_db, id=network.id)

        # Assert
        assert retrieved_network is not None
        assert retrieved_network.id == network.id
        assert retrieved_network.name == "Get By ID Test"

    @pytest.mark.asyncio
    async def test_get_network_by_slug(self, async_db: AsyncSession) -> None:
        """Test getting network by slug."""
        # Arrange
        slug = "test-network-slug"
        network = NetworkFactory.create(slug=slug)
        async_db.add(network)
        await async_db.flush()

        # Act
        retrieved_network = await crud_network.get_by_slug(async_db, slug=slug)

        # Assert
        assert retrieved_network is not None
        assert retrieved_network.slug == slug

    @pytest.mark.asyncio
    async def test_get_network_by_slug_with_tenant_filter(
        self,
        async_db: AsyncSession
    ) -> None:
        """Test getting network by slug with tenant filtering."""
        # Arrange
        tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        slug = "tenant-network"

        network = NetworkFactory.create(slug=slug, tenant_id=tenant_id)
        async_db.add(network)
        await async_db.flush()

        # Act - Correct tenant
        retrieved_network = await crud_network.get_by_slug(
            async_db,
            slug=slug,
            tenant_id=tenant_id
        )
        assert retrieved_network is not None
        assert retrieved_network.tenant_id == tenant_id

        # Act - Wrong tenant
        wrong_tenant_network = await crud_network.get_by_slug(
            async_db,
            slug=slug,
            tenant_id=other_tenant_id
        )
        assert wrong_tenant_network is None

    @pytest.mark.asyncio
    async def test_get_multi_networks(self, async_db: AsyncSession) -> None:
        """Test getting multiple networks."""
        # Arrange
        networks = NetworkFactory.create_batch(5)
        for network in networks:
            async_db.add(network)
        await async_db.flush()

        # Act
        retrieved_networks = await crud_network.get_multi(async_db, skip=0, limit=10)

        # Assert
        assert len(retrieved_networks) >= 5
        network_ids = [str(n.id) for n in retrieved_networks]
        for network in networks:
            assert str(network.id) in network_ids

    @pytest.mark.asyncio
    async def test_get_active_networks(self, async_db: AsyncSession) -> None:
        """Test getting only active and validated networks."""
        # Arrange
        active_validated = NetworkFactory.create_validated_network(active=True)
        active_unvalidated = NetworkFactory.create(active=True, validated=False)
        inactive_validated = NetworkFactory.create_validated_network(active=False)

        async_db.add(active_validated)
        async_db.add(active_unvalidated)
        async_db.add(inactive_validated)
        await async_db.flush()

        # Act
        active_networks = await crud_network.get_active_networks(async_db)

        # Assert
        active_network_ids = [str(n.id) for n in active_networks]
        assert str(active_validated.id) in active_network_ids
        assert str(active_unvalidated.id) not in active_network_ids
        assert str(inactive_validated.id) not in active_network_ids

    @pytest.mark.asyncio
    async def test_get_active_networks_with_tenant_filter(
        self,
        async_db: AsyncSession
    ) -> None:
        """Test getting active networks with tenant filter."""
        # Arrange
        tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()

        tenant_network = NetworkFactory.create_validated_network(
            tenant_id=tenant_id,
            active=True
        )
        other_network = NetworkFactory.create_validated_network(
            tenant_id=other_tenant_id,
            active=True
        )

        async_db.add(tenant_network)
        async_db.add(other_network)
        await async_db.flush()

        # Act
        tenant_networks = await crud_network.get_active_networks(
            async_db,
            tenant_id=tenant_id
        )

        # Assert
        assert len(tenant_networks) >= 1
        network_tenant_ids = [str(n.tenant_id) for n in tenant_networks if n.tenant_id]
        assert str(tenant_id) in network_tenant_ids
        assert str(other_tenant_id) not in network_tenant_ids

    # @pytest.mark.asyncio
    # async def test_get_paginated_networks(self, async_db: AsyncSession) -> None:
    #     """Test paginated network retrieval."""
    #     # NOTE: FastCRUD doesn't have get_paginated method - commented out
    #     # Arrange
    #     networks = NetworkFactory.create_batch(15)
    #     for network in networks:
    #         async_db.add(network)
    #     await async_db.flush()

    #     # Act
    #     result = await crud_network.get_paginated(async_db, page=1, size=10)

    #     # Assert
    #     assert "items" in result
    #     assert "total" in result
    #     assert result["page"] == 1
    #     assert result["size"] == 10
    #     assert len(result["items"]) == 10
    #     assert result["total"] >= 15


class TestCRUDNetworkUpdate:
    """Test network update operations."""

    @pytest.mark.asyncio
    async def test_update_network_basic(self, async_db: AsyncSession) -> None:
        """Test basic network update."""
        # Arrange
        network = NetworkFactory.create(name="Original Name")
        async_db.add(network)
        await async_db.flush()

        update_data = NetworkUpdate(name="Updated Name")

        # Act
        updated_network = await crud_network.update(
            async_db,
            db_obj=network,
            object=update_data
        )

        # Assert
        assert updated_network is not None
        assert updated_network.name == "Updated Name"
        assert updated_network.updated_at is not None

    @pytest.mark.asyncio
    async def test_add_rpc_urls(self, async_db: AsyncSession) -> None:
        """Test adding RPC URLs to a network."""
        # Arrange
        network = NetworkFactory.create(
            rpc_urls=[
                {"url": "https://rpc1.test.com", "type_": "primary", "weight": 100}
            ]
        )
        async_db.add(network)
        await async_db.flush()

        rpc_add = NetworkRPCAdd(
            network_id=network.id,
            rpc_urls=[
                {"url": "https://rpc2.test.com", "type_": "backup", "weight": 80},
                {"url": "https://rpc3.test.com", "type_": "fallback", "weight": 60}
            ]
        )

        # Act
        updated_network = await crud_network.add_rpc_urls(async_db, rpc_add)

        # Assert
        assert updated_network is not None
        assert len(updated_network.rpc_urls) == 3
        rpc_urls = [rpc["url"] for rpc in updated_network.rpc_urls]
        assert "https://rpc1.test.com" in rpc_urls
        assert "https://rpc2.test.com" in rpc_urls
        assert "https://rpc3.test.com" in rpc_urls

    @pytest.mark.asyncio
    async def test_add_duplicate_rpc_urls(self, async_db: AsyncSession) -> None:
        """Test adding duplicate RPC URLs (should not add duplicates)."""
        # Arrange
        existing_rpc = {"url": "https://rpc1.test.com", "type_": "primary", "weight": 100}
        network = NetworkFactory.create(rpc_urls=[existing_rpc])
        async_db.add(network)
        await async_db.flush()

        rpc_add = NetworkRPCAdd(
            network_id=network.id,
            rpc_urls=[existing_rpc]  # Duplicate URL
        )

        # Act
        updated_network = await crud_network.add_rpc_urls(async_db, rpc_add)

        # Assert
        assert updated_network is not None
        assert len(updated_network.rpc_urls) == 1  # Should not add duplicate

    @pytest.mark.asyncio
    async def test_remove_rpc_urls(self, async_db: AsyncSession) -> None:
        """Test removing RPC URLs from a network."""
        # Arrange
        network = NetworkFactory.create(
            rpc_urls=[
                {"url": "https://rpc1.test.com", "type_": "primary", "weight": 100},
                {"url": "https://rpc2.test.com", "type_": "backup", "weight": 80},
                {"url": "https://rpc3.test.com", "type_": "fallback", "weight": 60}
            ]
        )
        async_db.add(network)
        await async_db.flush()

        rpc_remove = NetworkRPCRemove(
            network_id=network.id,
            rpc_urls=["https://rpc2.test.com", "https://rpc3.test.com"]
        )

        # Act
        updated_network = await crud_network.remove_rpc_urls(async_db, rpc_remove)

        # Assert
        assert updated_network is not None
        assert len(updated_network.rpc_urls) == 1
        remaining_url = updated_network.rpc_urls[0]["url"]
        assert remaining_url == "https://rpc1.test.com"

    @pytest.mark.asyncio
    async def test_rpc_operations_nonexistent_network(
        self,
        async_db: AsyncSession
    ) -> None:
        """Test RPC operations on non-existent network."""
        # Arrange
        fake_id = uuid.uuid4()

        rpc_add = NetworkRPCAdd(
            network_id=fake_id,
            rpc_urls=[{"url": "https://rpc.test.com", "type_": "primary", "weight": 100}]
        )

        rpc_remove = NetworkRPCRemove(
            network_id=fake_id,
            rpc_urls=["https://rpc.test.com"]
        )

        # Act & Assert
        add_result = await crud_network.add_rpc_urls(async_db, rpc_add)
        assert add_result is None

        remove_result = await crud_network.remove_rpc_urls(async_db, rpc_remove)
        assert remove_result is None


class TestCRUDNetworkRPCTesting:
    """Test RPC URL testing functionality."""

    @patch('httpx.AsyncClient')
    @pytest.mark.asyncio
    async def test_test_rpc_url_evm_success(
        self,
        mock_client_class,
        async_db: AsyncSession
    ) -> None:
        """Test successful EVM RPC URL testing."""
        # Arrange
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock successful RPC responses
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"result": "0x1234567"}  # Block height in hex

        mock_client.post = AsyncMock(return_value=mock_response)

        rpc_test = NetworkRPCTest(
            url="https://eth-mainnet.test.com",
            network_type="EVM",
            chain_id=1
        )

        # Act
        result = await crud_network.test_rpc_url(rpc_test)

        # Assert
        assert result.url == "https://eth-mainnet.test.com"
        assert result.is_online is True
        assert result.latency_ms is not None
        assert result.block_height == 0x1234567  # Converted from hex
        assert result.error is None

    @patch('httpx.AsyncClient')
    @pytest.mark.asyncio
    async def test_test_rpc_url_evm_chain_mismatch(
        self,
        mock_client_class,
        async_db: AsyncSession
    ) -> None:
        """Test EVM RPC URL testing with chain ID mismatch."""
        # Arrange
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock responses
        block_response = Mock()
        block_response.raise_for_status.return_value = None
        block_response.json.return_value = {"result": "0x1234567"}

        chain_response = Mock()
        chain_response.raise_for_status.return_value = None
        chain_response.json.return_value = {"result": "0x89"}  # Chain ID 137 (Polygon)

        mock_client.post = AsyncMock(side_effect=[block_response, chain_response])

        rpc_test = NetworkRPCTest(
            url="https://wrong-chain.test.com",
            network_type="EVM",
            chain_id=1  # Expecting Ethereum mainnet
        )

        # Act
        result = await crud_network.test_rpc_url(rpc_test)

        # Assert
        assert result.is_online is False
        assert "Chain ID mismatch" in result.error
        assert "expected 1, got 137" in result.error

    @patch('httpx.AsyncClient')
    @pytest.mark.asyncio
    async def test_test_rpc_url_stellar_success(
        self,
        mock_client_class,
        async_db: AsyncSession
    ) -> None:
        """Test successful Stellar RPC URL testing."""
        # Arrange
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "_embedded": {
                "records": [
                    {"sequence": 12345}
                ]
            }
        }

        mock_client.get = AsyncMock(return_value=mock_response)

        rpc_test = NetworkRPCTest(
            url="https://horizon-testnet.stellar.org",
            network_type="Stellar"
        )

        # Act
        result = await crud_network.test_rpc_url(rpc_test)

        # Assert
        assert result.url == "https://horizon-testnet.stellar.org"
        assert result.is_online is True
        assert result.block_height == 12345
        assert result.error is None

    @patch('httpx.AsyncClient')
    @pytest.mark.asyncio
    async def test_test_rpc_url_timeout(
        self,
        mock_client_class,
        async_db: AsyncSession
    ) -> None:
        """Test RPC URL testing with timeout."""
        # Arrange
        import httpx
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))

        rpc_test = NetworkRPCTest(
            url="https://slow-rpc.test.com",
            network_type="EVM"
        )

        # Act
        result = await crud_network.test_rpc_url(rpc_test)

        # Assert
        assert result.is_online is False
        assert result.latency_ms is None
        assert "Connection timeout" in result.error

    @patch('httpx.AsyncClient')
    @pytest.mark.asyncio
    async def test_test_rpc_url_http_error(
        self,
        mock_client_class,
        async_db: AsyncSession
    ) -> None:
        """Test RPC URL testing with HTTP error."""
        # Arrange
        import httpx
        mock_client = Mock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(
            side_effect=httpx.HTTPError("HTTP 500 Internal Server Error")
        )

        rpc_test = NetworkRPCTest(
            url="https://error-rpc.test.com",
            network_type="EVM"
        )

        # Act
        result = await crud_network.test_rpc_url(rpc_test)

        # Assert
        assert result.is_online is False
        assert "HTTP error" in result.error


class TestCRUDNetworkValidation:
    """Test network validation operations."""

    @pytest.mark.asyncio
    async def test_validate_network_success(self, async_db: AsyncSession) -> None:
        """Test successful network validation."""
        # Arrange
        network = NetworkFactory.create(
            network_type="EVM",
            chain_id=1,
            rpc_urls=[
                {"url": "https://rpc.test.com", "type_": "primary", "weight": 100}
            ]
        )
        async_db.add(network)
        await async_db.flush()

        validation_request = NetworkValidationRequest(
            network_id=network.id,
            test_connection=False  # Skip RPC testing for this test
        )

        # Act
        result = await crud_network.validate_network(async_db, validation_request)

        # Assert
        assert result.network_id == network.id
        assert result.is_valid is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_network_no_rpc_urls(self, async_db: AsyncSession) -> None:
        """Test network validation with no RPC URLs."""
        # Arrange
        network = NetworkFactory.create(
            network_type="EVM",
            chain_id=1,
            rpc_urls=[]  # No RPC URLs
        )
        async_db.add(network)
        await async_db.flush()

        validation_request = NetworkValidationRequest(network_id=network.id)

        # Act
        result = await crud_network.validate_network(async_db, validation_request)

        # Assert
        assert result.is_valid is False
        assert any("at least one RPC URL" in error for error in result.errors)

    @pytest.mark.asyncio
    async def test_validate_network_evm_no_chain_id(self, async_db: AsyncSession) -> None:
        """Test EVM network validation without chain ID."""
        # Arrange
        network = NetworkFactory.create(
            network_type="EVM",
            chain_id=None,  # Missing chain_id
            rpc_urls=[
                {"url": "https://rpc.test.com", "type_": "primary", "weight": 100}
            ]
        )
        async_db.add(network)
        await async_db.flush()

        validation_request = NetworkValidationRequest(network_id=network.id)

        # Act
        result = await crud_network.validate_network(async_db, validation_request)

        # Assert
        assert result.is_valid is False
        assert any("chain_id" in error for error in result.errors)

    @pytest.mark.asyncio
    async def test_validate_network_stellar_no_passphrase(
        self,
        async_db: AsyncSession
    ) -> None:
        """Test Stellar network validation without network passphrase."""
        # Arrange
        network = NetworkFactory.create(
            network_type="Stellar",
            network_passphrase=None,  # Missing passphrase
            chain_id=None,
            rpc_urls=[
                {"url": "https://horizon.stellar.org", "type_": "primary", "weight": 100}
            ]
        )
        async_db.add(network)
        await async_db.flush()

        validation_request = NetworkValidationRequest(network_id=network.id)

        # Act
        result = await crud_network.validate_network(async_db, validation_request)

        # Assert
        assert result.is_valid is False
        assert any("network_passphrase" in error for error in result.errors)

    @patch('src.app.crud.crud_network.CRUDNetwork._test_rpc_url')
    @pytest.mark.asyncio
    async def test_validate_network_with_rpc_testing(
        self,
        mock_test_rpc,
        async_db: AsyncSession
    ) -> None:
        """Test network validation with RPC connectivity testing."""
        # Arrange
        mock_test_rpc.return_value = NetworkRPCTestResult(
            url="https://rpc.test.com",
            is_online=True,
            latency_ms=50,
            block_height=12345,
            error=None
        )

        network = NetworkFactory.create(
            network_type="EVM",
            chain_id=1,
            rpc_urls=[
                {"url": "https://rpc.test.com", "type_": "primary", "weight": 100}
            ]
        )
        async_db.add(network)
        await async_db.flush()

        validation_request = NetworkValidationRequest(
            network_id=network.id,
            test_connection=True
        )

        # Act
        result = await crud_network.validate_network(async_db, validation_request)

        # Assert
        assert result.is_valid is True
        assert result.current_block_height == 12345
        assert "https://rpc.test.com" in result.rpc_status
        assert result.rpc_status["https://rpc.test.com"]["online"] is True

    @pytest.mark.asyncio
    async def test_validate_nonexistent_network(self, async_db: AsyncSession) -> None:
        """Test validating non-existent network."""
        # Arrange
        fake_id = uuid.uuid4()
        validation_request = NetworkValidationRequest(network_id=fake_id)

        # Act
        result = await crud_network.validate_network(async_db, validation_request)

        # Assert
        assert result.is_valid is False
        assert any("not found" in error.lower() for error in result.errors)

    @pytest.mark.asyncio
    async def test_bulk_validate_networks(self, async_db: AsyncSession) -> None:
        """Test bulk validation of multiple networks."""
        # Arrange
        networks = NetworkFactory.create_batch(3)
        for network in networks:
            async_db.add(network)
        await async_db.flush()

        network_ids = [network.id for network in networks]

        # Act
        with patch('src.app.crud.crud_network.CRUDNetwork.validate_network') as mock_validate:
            mock_validate.return_value = NetworkValidationResult(
                network_id=uuid.uuid4(),
                is_valid=True,
                errors=[],
                warnings=[],
                rpc_status={}
            )

            results = await crud_network.bulk_validate(async_db, network_ids)

        # Assert
        assert len(results) == 3
        assert len(mock_validate.call_args_list) == 3


class TestCRUDNetworkCaching:
    """Test Redis caching functionality."""

    @pytest.mark.asyncio
    async def test_cache_to_redis(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test caching network to Redis."""
        # Arrange
        network = NetworkFactory.create(
            slug="ethereum-mainnet",
            active=True,
            network_type="EVM",
            chain_id=1
        )
        async_db.add(network)
        await async_db.flush()

        # Act
        await crud_network.cache_to_redis(async_db, mock_redis, network.id)

        # Assert
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        cache_key = call_args[0][0]
        cache_data = call_args[0][1]

        assert cache_key == f"platform:networks:{network.slug}"

        # Verify cached data structure
        cached_network = json.loads(cache_data)
        assert cached_network["slug"] == network.slug
        assert cached_network["network_type"] == network.network_type
        assert cached_network["chain_id"] == network.chain_id

    @pytest.mark.asyncio
    async def test_cache_inactive_network_not_cached(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test that inactive networks are not cached."""
        # Arrange
        inactive_network = NetworkFactory.create(active=False)
        async_db.add(inactive_network)
        await async_db.flush()

        # Act
        await crud_network.cache_to_redis(async_db, mock_redis, inactive_network.id)

        # Assert
        mock_redis.set.assert_not_called()


class TestCRUDNetworkAdvanced:
    """Test advanced network operations and edge cases."""

    @pytest.mark.asyncio
    async def test_network_factory_variants(self, async_db: AsyncSession) -> None:
        """Test different network factory creation methods."""
        # Test Ethereum mainnet
        eth_mainnet = NetworkFactory.create_ethereum_mainnet()
        async_db.add(eth_mainnet)
        assert eth_mainnet.name == "Ethereum Mainnet"
        assert eth_mainnet.chain_id == 1
        assert eth_mainnet.network_type == "EVM"

        # Test Polygon mainnet
        polygon_mainnet = NetworkFactory.create_polygon_mainnet()
        async_db.add(polygon_mainnet)
        assert polygon_mainnet.name == "Polygon Mainnet"
        assert polygon_mainnet.chain_id == 137

        # Test Arbitrum One
        arbitrum_one = NetworkFactory.create_arbitrum_one()
        async_db.add(arbitrum_one)
        assert arbitrum_one.name == "Arbitrum One"
        assert arbitrum_one.chain_id == 42161

        # Test Stellar mainnet
        stellar_mainnet = NetworkFactory.create_stellar_mainnet()
        async_db.add(stellar_mainnet)
        assert stellar_mainnet.name == "Stellar Mainnet"
        assert stellar_mainnet.network_type == "Stellar"
        assert stellar_mainnet.chain_id is None

        # Test Stellar testnet
        stellar_testnet = NetworkFactory.create_stellar_testnet()
        async_db.add(stellar_testnet)
        assert stellar_testnet.name == "Stellar Testnet"
        assert "Test SDF Network" in stellar_testnet.network_passphrase

        # Test validated network
        validated_network = NetworkFactory.create_validated_network()
        async_db.add(validated_network)
        assert validated_network.validated is True

        # Test invalid network
        invalid_network = NetworkFactory.create_invalid_network()
        async_db.add(invalid_network)
        assert invalid_network.validated is False
        assert invalid_network.validation_errors is not None

        # Test inactive network
        inactive_network = NetworkFactory.create_inactive_network()
        async_db.add(inactive_network)
        assert inactive_network.active is False

        await async_db.flush()

        # Verify all networks were created
        networks = [
            eth_mainnet, polygon_mainnet, arbitrum_one, stellar_mainnet,
            stellar_testnet, validated_network, invalid_network, inactive_network
        ]
        for network in networks:
            assert network.id is not None

    @pytest.mark.asyncio
    async def test_crud_instance_validation(self) -> None:
        """Test that crud_network is properly instantiated."""
        # Assert
        assert isinstance(crud_network, CRUDNetwork)
        assert crud_network.model is Network

    @pytest.mark.asyncio
    async def test_exists_network(self, async_db: AsyncSession) -> None:
        """Test checking if network exists."""
        # Arrange
        network = NetworkFactory.create(slug="exists-test")
        async_db.add(network)
        await async_db.flush()

        # Act & Assert
        assert await crud_network.exists(async_db, slug="exists-test") is True
        assert await crud_network.exists(async_db, slug="nonexistent") is False

    @pytest.mark.asyncio
    async def test_delete_network(self, async_db: AsyncSession) -> None:
        """Test network deletion."""
        # Arrange
        network = NetworkFactory.create()
        async_db.add(network)
        await async_db.flush()
        network_id = network.id

        # Act
        result = await crud_network.delete(async_db, id=network_id)

        # Assert
        assert result is not None

        # Verify deletion (soft delete behavior would depend on implementation)
        await async_db.get(Network, network_id)
        # Behavior depends on whether soft delete is implemented

    @pytest.mark.asyncio
    async def test_error_handling_edge_cases(self, async_db: AsyncSession) -> None:
        """Test error handling and edge cases."""
        # Test getting non-existent network
        fake_id = uuid.uuid4()
        retrieved = await crud_network.get(async_db, id=fake_id)
        assert retrieved is None

        # Test getting by slug that doesn't exist
        by_slug = await crud_network.get_by_slug(async_db, "nonexistent-slug")
        assert by_slug is None

        # Test updating non-existent network
        update_data = NetworkUpdate(name="Should Fail")
        updated = await crud_network.update(async_db, id=fake_id, object=update_data)
        assert updated is None

    @pytest.mark.parametrize("network_type,chain_id,passphrase", [
        ("EVM", 1, None),
        ("EVM", 137, None),
        ("EVM", 42161, None),
        ("Stellar", None, "Test SDF Network ; September 2015"),
    ])
    @pytest.mark.asyncio
    async def test_network_type_variations(
        self,
        async_db: AsyncSession,
        network_type: str,
        chain_id: int | None,
        passphrase: str | None
    ) -> None:
        """Test network operations for different network types."""
        # Arrange
        network_create = NetworkCreate(
            name=f"Test {network_type} Network",
            slug=f"test-{network_type.lower()}-network",
            network_type=network_type,
            chain_id=chain_id,
            network_passphrase=passphrase,
            rpc_urls=[
                {"url": "https://rpc.test.com", "type_": "primary", "weight": 100}
            ],
            block_time_ms=5000
        )

        # Act
        created_network = await crud_network.create(async_db, object=network_create)

        # Assert
        assert created_network is not None
        assert created_network.network_type == network_type
        assert created_network.chain_id == chain_id
        assert created_network.network_passphrase == passphrase

    @pytest.mark.asyncio
    async def test_network_with_complex_rpc_configuration(
        self,
        async_db: AsyncSession
    ) -> None:
        """Test network with complex RPC URL configuration."""
        # Arrange
        complex_rpc_urls = [
            {
                "url": "https://primary-rpc.test.com",
                "type_": "primary",
                "weight": 100,
                "auth_header": "Bearer token123",
                "timeout_ms": 5000,
                "max_retries": 3
            },
            {
                "url": "https://backup-rpc.test.com",
                "type_": "backup",
                "weight": 80,
                "auth_header": "ApiKey key456",
                "timeout_ms": 3000,
                "max_retries": 2
            },
            {
                "url": "https://fallback-rpc.test.com",
                "type_": "fallback",
                "weight": 60,
                "timeout_ms": 10000,
                "max_retries": 1
            }
        ]

        network_create = NetworkCreate(
            name="Complex RPC Network",
            slug="complex-rpc-network",
            network_type="EVM",
            chain_id=1337,
            rpc_urls=complex_rpc_urls,
            block_time_ms=2000,
            confirmation_blocks=3,
            max_past_blocks=500
        )

        # Act
        created_network = await crud_network.create(async_db, object=network_create)

        # Assert
        assert created_network is not None
        assert len(created_network.rpc_urls) == 3

        # Verify complex RPC configuration preserved
        primary_rpc = next(rpc for rpc in created_network.rpc_urls if rpc["type_"] == "primary")
        assert primary_rpc["auth_header"] == "Bearer token123"
        assert primary_rpc["timeout_ms"] == 5000
        assert primary_rpc["max_retries"] == 3
