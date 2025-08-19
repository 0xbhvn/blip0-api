"""
Comprehensive unit tests for CRUDMonitor operations with Redis caching.

Tests cover all CRUD operations including:
- Create operations with cache invalidation
- Read operations (get, get_multi, get_paginated, get_by_slug)
- Update operations including cache refresh
- Delete operations with cache removal
- Redis caching functionality
- Monitor validation operations
- Monitor pause/resume functionality
- Advanced filtering and network-based queries
- Denormalized cache operations
- Monitor cloning functionality
"""

import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.crud.crud_monitor import CRUDMonitor, crud_monitor
from src.app.models.monitor import Monitor
from src.app.schemas.monitor import (
    MonitorCached,
    MonitorCreate,
    MonitorUpdate,
    MonitorValidationRequest,
)
from tests.factories.monitor_factory import MonitorFactory


class TestCRUDMonitorCreate:
    """Test monitor creation operations."""

    @pytest.mark.asyncio
    async def test_create_monitor_basic(self, async_db: AsyncSession) -> None:
        """Test basic monitor creation."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor_create = MonitorCreate(
            tenant_id=tenant_id,
            name="Test Monitor",
            slug="test-monitor",
            description="A test monitor",
            networks=["ethereum"],
            addresses=[{"address": "0x123", "type": "contract"}],
            match_functions=[{"signature": "transfer(address,uint256)"}],
            match_events=[],
            match_transactions=[],
            trigger_conditions=[],
            triggers=[]
        )

        # Act
        created_monitor = await crud_monitor.create(async_db, object=monitor_create)

        # Assert
        assert created_monitor is not None
        assert created_monitor.name == monitor_create.name
        assert created_monitor.slug == monitor_create.slug
        assert created_monitor.tenant_id == tenant_id
        assert created_monitor.networks == ["ethereum"]
        assert len(created_monitor.addresses) == 1
        assert created_monitor.active is True
        assert created_monitor.paused is False
        assert created_monitor.validated is False

    @pytest.mark.asyncio
    async def test_create_monitor_with_cache(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test monitor creation with Redis caching."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor_create = MonitorCreate(
            tenant_id=tenant_id,
            name="Cached Monitor",
            slug="cached-monitor",
            description="A monitor with caching",
            networks=["ethereum", "polygon"],
            addresses=[{"address": "0xabc", "type": "contract"}],
            match_functions=[{"signature": "transfer(address,uint256)"}],
            match_events=[],
            match_transactions=[],
            trigger_conditions=[],
            triggers=[]
        )

        # Act
        created_monitor = await crud_monitor.create_with_cache(
            async_db,
            object=monitor_create,
            redis_client=mock_redis
        )

        # Assert
        assert created_monitor is not None
        assert created_monitor.name == "Cached Monitor"

        # Verify cache operations were called
        mock_redis.set.assert_called()
        mock_redis.sadd.assert_called()  # For active monitors list

    @pytest.mark.asyncio
    async def test_create_monitor_complex_config(self, async_db: AsyncSession) -> None:
        """Test monitor creation with complex configuration."""
        # Arrange
        tenant_id = uuid.uuid4()
        complex_addresses = [
            {
                "address": "0x1234567890123456789012345678901234567890",
                "type": "contract",
                "name": "USDC Token",
                "abi": [
                    {
                        "type": "function",
                        "name": "transfer",
                        "inputs": [
                            {"name": "to", "type": "address"},
                            {"name": "value", "type": "uint256"}
                        ]
                    }
                ]
            }
        ]

        complex_functions = [
            {
                "signature": "transfer(address,uint256)",
                "expression": "args.value > 1000000",
                "description": "Large transfers"
            }
        ]

        monitor_create = MonitorCreate(
            tenant_id=tenant_id,
            name="Complex Monitor",
            slug="complex-monitor",
            description="Monitor with complex configuration",
            networks=["ethereum", "polygon", "bsc"],
            addresses=complex_addresses,
            match_functions=complex_functions,
            match_events=[
                {
                    "signature": "Transfer(address,address,uint256)",
                    "expression": "args.value > 1000000"
                }
            ],
            match_transactions=[
                {
                    "status": "success",
                    "expression": "transaction.value > 1"
                }
            ],
            trigger_conditions=[
                {
                    "type": "filter",
                    "script": "large_transfer"
                }
            ],
            triggers=["email-1", "webhook-2"]
        )

        # Act
        created_monitor = await crud_monitor.create(async_db, object=monitor_create)

        # Assert
        assert created_monitor is not None
        assert len(created_monitor.networks) == 3
        assert len(created_monitor.addresses) == 1
        assert created_monitor.addresses[0]["name"] == "USDC Token"
        assert len(created_monitor.match_functions) == 1
        assert len(created_monitor.match_events) == 1
        assert len(created_monitor.match_transactions) == 1


class TestCRUDMonitorRead:
    """Test monitor read operations."""

    @pytest.mark.asyncio
    async def test_get_monitor_by_id(self, async_db: AsyncSession) -> None:
        """Test getting monitor by ID."""
        # Arrange
        monitor = MonitorFactory.create(name="Get By ID Test")
        async_db.add(monitor)
        await async_db.flush()

        # Act
        retrieved_monitor = await crud_monitor.get(async_db, id=monitor.id)

        # Assert
        assert retrieved_monitor is not None
        assert retrieved_monitor.id == monitor.id
        assert retrieved_monitor.name == "Get By ID Test"

    @pytest.mark.asyncio
    async def test_get_monitor_by_slug(self, async_db: AsyncSession) -> None:
        """Test getting monitor by slug within tenant context."""
        # Arrange
        tenant_id = uuid.uuid4()
        slug = "test-slug-123"
        monitor = MonitorFactory.create(slug=slug, tenant_id=tenant_id)
        async_db.add(monitor)
        await async_db.flush()

        # Act
        retrieved_monitor = await crud_monitor.get_by_slug(
            async_db,
            slug=slug,
            tenant_id=tenant_id
        )

        # Assert
        assert retrieved_monitor is not None
        assert retrieved_monitor.slug == slug
        assert retrieved_monitor.tenant_id == tenant_id

    @pytest.mark.asyncio
    async def test_get_monitor_by_slug_wrong_tenant(self, async_db: AsyncSession) -> None:
        """Test getting monitor by slug with wrong tenant returns None."""
        # Arrange
        tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        slug = "test-slug-456"
        monitor = MonitorFactory.create(slug=slug, tenant_id=tenant_id)
        async_db.add(monitor)
        await async_db.flush()

        # Act
        retrieved_monitor = await crud_monitor.get_by_slug(
            async_db,
            slug=slug,
            tenant_id=other_tenant_id
        )

        # Assert
        assert retrieved_monitor is None

    @pytest.mark.asyncio
    async def test_get_multi_monitors(self, async_db: AsyncSession) -> None:
        """Test getting multiple monitors."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitors = MonitorFactory.create_batch(5, tenant_id=tenant_id)
        for monitor in monitors:
            async_db.add(monitor)
        await async_db.flush()

        # Act
        retrieved_monitors = await crud_monitor.get_multi(async_db, skip=0, limit=10)

        # Assert
        assert len(retrieved_monitors) >= 5
        monitor_ids = [str(m.id) for m in retrieved_monitors]
        for monitor in monitors:
            assert str(monitor.id) in monitor_ids

    @pytest.mark.asyncio
    async def test_get_denormalized_monitor(self, async_db: AsyncSession) -> None:
        """Test getting monitor with denormalized trigger data."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(tenant_id=tenant_id)
        async_db.add(monitor)
        await async_db.flush()

        # Act
        denormalized = await crud_monitor.get_denormalized(
            async_db,
            monitor.id,
            tenant_id
        )

        # Assert
        assert denormalized is not None
        assert isinstance(denormalized, MonitorCached)
        assert denormalized.id == monitor.id
        assert hasattr(denormalized, 'triggers_data')
        assert isinstance(denormalized.triggers_data, list)

    @pytest.mark.asyncio
    async def test_get_active_monitors_by_network(self, async_db: AsyncSession) -> None:
        """Test getting active monitors for a specific network."""
        # Arrange
        tenant_id = uuid.uuid4()
        ethereum_monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            networks=["ethereum", "polygon"],
            active=True,
            paused=False
        )
        polygon_monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            networks=["polygon", "bsc"],
            active=True,
            paused=False
        )
        inactive_monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            networks=["ethereum"],
            active=False
        )

        async_db.add(ethereum_monitor)
        async_db.add(polygon_monitor)
        async_db.add(inactive_monitor)
        await async_db.flush()

        # Act
        ethereum_monitors = await crud_monitor.get_active_monitors_by_network(
            async_db,
            "ethereum",
            tenant_id
        )

        # Assert
        assert len(ethereum_monitors) >= 1
        found_ethereum = any(m.id == ethereum_monitor.id for m in ethereum_monitors)
        assert found_ethereum

        # Should not include inactive monitor
        found_inactive = any(m.id == inactive_monitor.id for m in ethereum_monitors)
        assert not found_inactive

    # @pytest.mark.asyncio
    # async def test_get_paginated_monitors(self, async_db: AsyncSession) -> None:
    #     """Test paginated monitor retrieval."""
    #     # NOTE: FastCRUD doesn't have get_paginated method - commented out
    #     # Arrange
    #     tenant_id = uuid.uuid4()
    #     monitors = MonitorFactory.create_batch(15, tenant_id=tenant_id)
    #     for monitor in monitors:
    #         async_db.add(monitor)
    #     await async_db.flush()

    #     # Act
    #     result = await crud_monitor.get_paginated(
    #         async_db,
    #         page=1,
    #         size=10,
    #         tenant_id=tenant_id
    #     )

    #     # Assert
    #     assert "items" in result
    #     assert "total" in result
    #     assert "page" in result
    #     assert "size" in result
    #     assert result["page"] == 1
    #     assert result["size"] == 10
    #     assert len(result["items"]) == 10
    #     assert result["total"] >= 15


class TestCRUDMonitorUpdate:
    """Test monitor update operations."""

    @pytest.mark.asyncio
    async def test_update_monitor_basic(self, async_db: AsyncSession) -> None:
        """Test basic monitor update."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            name="Original Name"
        )
        async_db.add(monitor)
        await async_db.flush()

        update_data = MonitorUpdate(name="Updated Name")

        # Act
        updated_monitor = await crud_monitor.update(
            async_db,
            db_obj=monitor,
            object=update_data
        )

        # Assert
        assert updated_monitor is not None
        assert updated_monitor.name == "Updated Name"
        assert updated_monitor.updated_at is not None

    @pytest.mark.asyncio
    async def test_update_monitor_with_cache(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test monitor update with cache refresh."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(tenant_id=tenant_id, name="Cached Update")
        async_db.add(monitor)
        await async_db.flush()

        update_data = MonitorUpdate(
            name="Updated Cached Monitor",
            description="Updated description"
        )

        # Act
        updated_monitor = await crud_monitor.update_with_cache(
            async_db,
            monitor.id,
            update_data,
            tenant_id,
            mock_redis
        )

        # Assert
        assert updated_monitor is not None
        assert updated_monitor.name == "Updated Cached Monitor"

        # Verify cache operations
        mock_redis.set.assert_called()  # Cache should be refreshed

    @pytest.mark.asyncio
    async def test_pause_monitor(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test pausing a monitor."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(tenant_id=tenant_id, paused=False)
        async_db.add(monitor)
        await async_db.flush()

        # Act
        paused_monitor = await crud_monitor.pause_monitor(
            async_db,
            monitor.id,
            tenant_id,
            mock_redis
        )

        # Assert
        assert paused_monitor is not None
        assert paused_monitor.paused is True

    @pytest.mark.asyncio
    async def test_resume_monitor(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test resuming a paused monitor."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(tenant_id=tenant_id, paused=True)
        async_db.add(monitor)
        await async_db.flush()

        # Act
        resumed_monitor = await crud_monitor.resume_monitor(
            async_db,
            monitor.id,
            tenant_id,
            mock_redis
        )

        # Assert
        assert resumed_monitor is not None
        assert resumed_monitor.paused is False

    @pytest.mark.asyncio
    async def test_update_monitor_networks(self, async_db: AsyncSession) -> None:
        """Test updating monitor networks configuration."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            networks=["ethereum"]
        )
        async_db.add(monitor)
        await async_db.flush()

        update_data = MonitorUpdate(networks=["ethereum", "polygon", "bsc"])

        # Act
        updated_monitor = await crud_monitor.update(
            async_db,
            db_obj=monitor,
            object=update_data
        )

        # Assert
        assert updated_monitor is not None
        assert len(updated_monitor.networks) == 3
        assert "ethereum" in updated_monitor.networks
        assert "polygon" in updated_monitor.networks
        assert "bsc" in updated_monitor.networks


class TestCRUDMonitorDelete:
    """Test monitor delete operations."""

    @pytest.mark.asyncio
    async def test_soft_delete_monitor(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test soft deletion of monitor."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(tenant_id=tenant_id, active=True)
        async_db.add(monitor)
        await async_db.flush()
        monitor_id = monitor.id

        # Act
        result = await crud_monitor.delete_with_cache(
            async_db,
            monitor_id,
            tenant_id,
            is_hard_delete=False,
            redis_client=mock_redis
        )

        # Assert
        assert result is True

        # Monitor should still exist but be inactive
        db_monitor = await async_db.get(Monitor, monitor_id)
        assert db_monitor is not None
        assert db_monitor.active is False

        # Cache should be updated
        mock_redis.delete.assert_called()
        mock_redis.srem.assert_called()

    @pytest.mark.asyncio
    async def test_hard_delete_monitor(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test hard deletion of monitor."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(tenant_id=tenant_id)
        async_db.add(monitor)
        await async_db.flush()
        monitor_id = monitor.id

        # Act
        result = await crud_monitor.delete_with_cache(
            async_db,
            monitor_id,
            tenant_id,
            is_hard_delete=True,
            redis_client=mock_redis
        )

        # Assert
        assert result is True

        # Monitor should not exist
        db_monitor = await async_db.get(Monitor, monitor_id)
        assert db_monitor is None

        # Cache should be cleared
        mock_redis.delete.assert_called()
        mock_redis.srem.assert_called()

    @pytest.mark.asyncio
    async def test_delete_monitor_wrong_tenant(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test deleting monitor with wrong tenant fails."""
        # Arrange
        tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(tenant_id=tenant_id)
        async_db.add(monitor)
        await async_db.flush()

        # Act
        result = await crud_monitor.delete_with_cache(
            async_db,
            monitor.id,
            other_tenant_id,  # Wrong tenant
            redis_client=mock_redis
        )

        # Assert
        assert result is False


class TestCRUDMonitorValidation:
    """Test monitor validation operations."""

    @pytest.mark.asyncio
    async def test_validate_monitor_success(self, async_db: AsyncSession) -> None:
        """Test successful monitor validation."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            networks=["ethereum"],
            addresses=[{"address": "0x123", "type": "contract"}],
            match_functions=[{"signature": "transfer(address,uint256)"}]
        )
        async_db.add(monitor)
        await async_db.flush()

        validation_request = MonitorValidationRequest(
            monitor_id=monitor.id,
            validate_triggers=False
        )

        # Act
        result = await crud_monitor.validate_monitor(async_db, validation_request)

        # Assert
        assert result.monitor_id == monitor.id
        assert result.is_valid is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_monitor_no_networks(self, async_db: AsyncSession) -> None:
        """Test monitor validation with no networks."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            networks=[],  # No networks
            addresses=[{"address": "0x123", "type": "contract"}]
        )
        async_db.add(monitor)
        await async_db.flush()

        validation_request = MonitorValidationRequest(monitor_id=monitor.id)

        # Act
        result = await crud_monitor.validate_monitor(async_db, validation_request)

        # Assert
        assert result.is_valid is False
        assert any("network" in error.lower() for error in result.errors)

    @pytest.mark.asyncio
    async def test_validate_monitor_no_matching_criteria(
        self,
        async_db: AsyncSession
    ) -> None:
        """Test monitor validation with no matching criteria."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            networks=["ethereum"],
            addresses=[{"address": "0x123", "type": "contract"}],
            match_functions=[],
            match_events=[],
            match_transactions=[]
        )
        async_db.add(monitor)
        await async_db.flush()

        validation_request = MonitorValidationRequest(monitor_id=monitor.id)

        # Act
        result = await crud_monitor.validate_monitor(async_db, validation_request)

        # Assert
        # Should generate a warning, not an error
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_validate_nonexistent_monitor(self, async_db: AsyncSession) -> None:
        """Test validating non-existent monitor."""
        # Arrange
        fake_id = uuid.uuid4()
        validation_request = MonitorValidationRequest(monitor_id=fake_id)

        # Act
        result = await crud_monitor.validate_monitor(async_db, validation_request)

        # Assert
        assert result.is_valid is False
        assert any("not found" in error.lower() for error in result.errors)


class TestCRUDMonitorAdvanced:
    """Test advanced monitor operations."""

    @pytest.mark.asyncio
    async def test_clone_monitor(self, async_db: AsyncSession) -> None:
        """Test cloning an existing monitor."""
        # Arrange
        tenant_id = uuid.uuid4()
        original_monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            name="Original Monitor",
            slug="original-monitor",
            networks=["ethereum"],
            addresses=[{"address": "0x123", "type": "contract"}]
        )
        async_db.add(original_monitor)
        await async_db.flush()

        # Act
        cloned_monitor = await crud_monitor.clone_monitor(
            async_db,
            original_monitor.id,
            tenant_id,
            "Cloned Monitor",
            "cloned-monitor"
        )

        # Assert
        assert cloned_monitor is not None
        assert cloned_monitor.name == "Cloned Monitor"
        assert cloned_monitor.slug == "cloned-monitor"
        assert cloned_monitor.tenant_id == tenant_id
        assert cloned_monitor.networks == original_monitor.networks
        assert cloned_monitor.addresses == original_monitor.addresses
        assert cloned_monitor.paused is True  # Clones start paused
        assert "Cloned from" in cloned_monitor.description

    @pytest.mark.asyncio
    async def test_clone_monitor_wrong_tenant(self, async_db: AsyncSession) -> None:
        """Test cloning monitor with wrong tenant fails."""
        # Arrange
        tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(tenant_id=tenant_id)
        async_db.add(monitor)
        await async_db.flush()

        # Act
        cloned_monitor = await crud_monitor.clone_monitor(
            async_db,
            monitor.id,
            other_tenant_id,  # Wrong tenant
            "Clone Attempt",
            "clone-attempt"
        )

        # Assert
        assert cloned_monitor is None

    @pytest.mark.asyncio
    async def test_cache_operations(
        self,
        async_db: AsyncSession,
        mock_redis: Mock
    ) -> None:
        """Test Redis cache operations."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(tenant_id=tenant_id, active=True, paused=False)

        # Setup mock redis responses
        mock_redis.set = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.srem = AsyncMock()
        mock_redis.delete = AsyncMock()

        # Act - Test cache monitor (private method through create_with_cache)
        created_monitor = await crud_monitor.create_with_cache(
            async_db,
            MonitorCreate(
                tenant_id=tenant_id,
                name=monitor.name,
                slug=monitor.slug,
                description=monitor.description,
                networks=monitor.networks,
                addresses=monitor.addresses,
                match_functions=monitor.match_functions,
                match_events=monitor.match_events,
                match_transactions=monitor.match_transactions,
                trigger_conditions=monitor.trigger_conditions,
                triggers=monitor.triggers
            ),
            mock_redis
        )

        # Assert
        assert created_monitor is not None

        # Verify cache operations
        mock_redis.set.assert_called()  # Monitor data cached
        mock_redis.sadd.assert_called()  # Added to active list

    @pytest.mark.asyncio
    async def test_monitor_factory_variants(self, async_db: AsyncSession) -> None:
        """Test different monitor factory creation methods."""
        # Test ERC20 monitor
        erc20_monitor = MonitorFactory.create_erc20_monitor()
        async_db.add(erc20_monitor)
        assert "ERC20" in erc20_monitor.name
        assert "ethereum" in erc20_monitor.networks

        # Test DeFi monitor
        defi_monitor = MonitorFactory.create_defi_monitor()
        async_db.add(defi_monitor)
        assert "DeFi" in defi_monitor.name
        assert len(defi_monitor.networks) >= 2

        # Test NFT monitor
        nft_monitor = MonitorFactory.create_nft_monitor()
        async_db.add(nft_monitor)
        assert "NFT" in nft_monitor.name
        assert "ethereum" in nft_monitor.networks

        # Test paused monitor
        paused_monitor = MonitorFactory.create_paused_monitor()
        async_db.add(paused_monitor)
        assert paused_monitor.paused is True

        # Test validated monitor
        validated_monitor = MonitorFactory.create_validated_monitor()
        async_db.add(validated_monitor)
        assert validated_monitor.validated is True
        assert validated_monitor.last_validated_at is not None

        # Test invalid monitor
        invalid_monitor = MonitorFactory.create_invalid_monitor()
        async_db.add(invalid_monitor)
        assert invalid_monitor.validated is False
        assert invalid_monitor.validation_errors is not None

        await async_db.flush()

        # Verify all monitors were created
        monitors = [
            erc20_monitor, defi_monitor, nft_monitor,
            paused_monitor, validated_monitor, invalid_monitor
        ]
        for monitor in monitors:
            assert monitor.id is not None

    @pytest.mark.asyncio
    async def test_crud_instance_validation(self) -> None:
        """Test that crud_monitor is properly instantiated."""
        # Assert
        assert isinstance(crud_monitor, CRUDMonitor)
        assert crud_monitor.model is Monitor

    @pytest.mark.asyncio
    async def test_monitor_with_complex_json_fields(
        self,
        async_db: AsyncSession
    ) -> None:
        """Test monitor with complex JSON field configurations."""
        # Arrange
        tenant_id = uuid.uuid4()
        complex_addresses = [
            {
                "address": "0x1234567890123456789012345678901234567890",
                "type": "contract",
                "name": "Complex Contract",
                "abi": [
                    {
                        "type": "function",
                        "name": "complexFunction",
                        "inputs": [
                            {"name": "param1", "type": "address[]"},
                            {"name": "param2", "type": "uint256[]"}
                        ],
                        "outputs": [{"name": "result", "type": "bool"}]
                    }
                ],
                "metadata": {
                    "version": "1.0.0",
                    "description": "A complex smart contract",
                    "tags": ["defi", "lending", "yield"]
                }
            }
        ]

        complex_trigger_conditions = [
            {
                "type": "composite",
                "operator": "AND",
                "conditions": [
                    {
                        "type": "value_threshold",
                        "field": "transaction.value",
                        "operator": "gt",
                        "value": 1000000
                    },
                    {
                        "type": "time_window",
                        "duration": "5m",
                        "count": 3
                    }
                ]
            }
        ]

        monitor_create = MonitorCreate(
            tenant_id=tenant_id,
            name="Complex JSON Monitor",
            slug="complex-json-monitor",
            description="Monitor with complex JSON configurations",
            networks=["ethereum", "polygon"],
            addresses=complex_addresses,
            match_functions=[
                {
                    "signature": "complexFunction(address[],uint256[])",
                    "expression": "args.param1.length > 0 AND args.param2.length > 0",
                    "description": "Complex function calls"
                }
            ],
            match_events=[],
            match_transactions=[],
            trigger_conditions=complex_trigger_conditions,
            triggers=[]
        )

        # Act
        created_monitor = await crud_monitor.create(async_db, object=monitor_create)

        # Assert
        assert created_monitor is not None
        assert len(created_monitor.addresses) == 1
        assert created_monitor.addresses[0]["metadata"]["version"] == "1.0.0"
        assert "defi" in created_monitor.addresses[0]["metadata"]["tags"]
        assert created_monitor.trigger_conditions[0]["type"] == "composite"
        assert len(created_monitor.trigger_conditions[0]["conditions"]) == 2

    @pytest.mark.asyncio
    async def test_error_handling_and_edge_cases(self, async_db: AsyncSession) -> None:
        """Test error handling and edge cases."""
        # Test getting non-existent monitor
        fake_id = uuid.uuid4()
        retrieved = await crud_monitor.get(async_db, id=fake_id)
        assert retrieved is None

        # Test getting by slug with non-existent tenant
        fake_tenant = uuid.uuid4()
        by_slug = await crud_monitor.get_by_slug(async_db, "fake-slug", fake_tenant)
        assert by_slug is None

        # Test updating non-existent monitor
        update_data = MonitorUpdate(name="Should Fail")
        updated = await crud_monitor.update(async_db, id=fake_id, object=update_data)
        assert updated is None

        # Test deleting non-existent monitor
        result = await crud_monitor.delete_with_cache(
            async_db,
            fake_id,
            fake_tenant,
            redis_client=Mock()
        )
        assert result is False

    @pytest.mark.parametrize("network", ["ethereum", "polygon", "bsc", "arbitrum"])
    @pytest.mark.asyncio
    async def test_network_specific_monitors(
        self,
        async_db: AsyncSession,
        network: str
    ) -> None:
        """Test monitor operations for different networks."""
        # Arrange
        tenant_id = uuid.uuid4()
        monitor = MonitorFactory.create(
            tenant_id=tenant_id,
            networks=[network],
            active=True,
            paused=False
        )
        async_db.add(monitor)
        await async_db.flush()

        # Act
        network_monitors = await crud_monitor.get_active_monitors_by_network(
            async_db,
            network,
            tenant_id
        )

        # Assert
        assert len(network_monitors) >= 1
        found_monitor = any(m.id == monitor.id for m in network_monitors)
        assert found_monitor
