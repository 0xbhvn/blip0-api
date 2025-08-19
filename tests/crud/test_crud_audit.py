"""Unit tests for CRUDAudit operations (BlockState, MissedBlock, MonitorMatch, TriggerExecution)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastcrud.paginated import PaginatedListResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.crud.crud_audit import (
    crud_block_state,
    crud_missed_block,
    crud_monitor_match,
    crud_trigger_execution,
)
from src.app.crud.crud_monitor import crud_monitor
from src.app.crud.crud_network import crud_network
from src.app.crud.crud_tenant import crud_tenant
from src.app.schemas.audit import (
    BlockProcessingStats,
    BlockStateCreate,
    BlockStateUpdate,
    MissedBlockCreate,
    MissedBlockUpdate,
    MonitorMatchCreate,
    MonitorMatchUpdate,
    TriggerExecutionCreate,
    TriggerExecutionStats,
    TriggerExecutionUpdate,
)
from src.app.schemas.monitor import MonitorCreate
from src.app.schemas.network import NetworkCreate
from src.app.schemas.tenant import TenantCreate
from tests.factories.audit_factory import (
    BlockStateFactory,
    MissedBlockFactory,
    MonitorMatchFactory,
    TriggerExecutionFactory,
)


@pytest.mark.asyncio
class TestCRUDBlockState:
    """Test suite for CRUDBlockState operations."""

    async def _create_tenant_network(self, async_db, tenant_name="Test Tenant", network_name="Test Network"):
        """Helper to create tenant and network for tests."""
        tenant_data = TenantCreate(name=tenant_name, slug=f"{tenant_name.lower().replace(' ', '-')}")
        tenant = await crud_tenant.create(async_db, object=tenant_data)

        network_data = NetworkCreate(
            tenant_id=tenant.id,
            name=network_name,
            slug=f"{network_name.lower().replace(' ', '-')}",
            network_type="EVM",
            chain_id=1,
            block_time_ms=12000,
            rpc_urls=[{"url": "https://rpc.test.com", "type_": "primary", "weight": 100}]
        )
        network = await crud_network.create(async_db, object=network_data)
        return tenant, network

    async def _create_tenant_network_monitor(self, async_db, tenant_name="Test Tenant",
                                           network_name="Test Network", monitor_name="Test Monitor"):
        """Helper to create tenant, network, and monitor for tests."""
        tenant, network = await self._create_tenant_network(async_db, tenant_name, network_name)

        monitor_data = MonitorCreate(
            tenant_id=tenant.id,
            name=monitor_name,
            slug=f"{monitor_name.lower().replace(' ', '-')}",
            networks=[network.id],
            addresses=[{"address": "0x1234567890123456789012345678901234567890", "type": "contract"}],
            match_functions=[{"signature": "transfer(address,uint256)"}],
            match_events=[{"signature": "Transfer(address,address,uint256)"}],
            match_transactions=[],
            trigger_conditions=[{"condition": "value > 1000"}]
        )
        monitor = await crud_monitor.create(async_db, object=monitor_data)
        return tenant, network, monitor

    async def test_get_or_create_new_block_state(self, async_db: AsyncSession) -> None:
        """
        Test creating new block state when none exists.

        Args:
            async_db: Async database session fixture
        """
        # Arrange - Create required tenant and network
        tenant, network = await self._create_tenant_network(async_db)

        # Act
        result = await crud_block_state.get_or_create(
            async_db, tenant_id=tenant.id, network_id=network.id
        )

        # Assert
        assert result is not None
        assert str(result.tenant_id) == str(tenant.id)
        assert str(result.network_id) == str(network.id)
        assert result.processing_status == "idle"
        assert result.error_count == 0
        assert result.last_processed_block is None
        assert result.blocks_per_minute is None
        assert result.average_processing_time_ms is None

    async def test_get_or_create_existing_block_state(self, async_db: AsyncSession) -> None:
        """
        Test retrieving existing block state.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        existing_state = await BlockStateFactory.create_async(async_db)

        # Act
        result = await crud_block_state.get_or_create(
            async_db, tenant_id=existing_state.tenant_id, network_id=existing_state.network_id
        )

        # Assert
        assert result.id == existing_state.id
        assert result.processing_status == existing_state.processing_status
        assert result.last_processed_block == existing_state.last_processed_block

    async def test_update_processing_status_to_error(self, async_db: AsyncSession) -> None:
        """
        Test updating processing status to error state.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        state = await BlockStateFactory.create_async(
            async_db, processing_status="processing", error_count=2
        )
        error_message = "RPC connection timeout after 30 seconds"

        # Act
        result = await crud_block_state.update_processing_status(
            async_db,
            tenant_id=state.tenant_id,
            network_id=state.network_id,
            status="error",
            error=error_message
        )

        # Assert
        assert result is not None
        assert result.processing_status == "error"
        assert result.last_error == error_message
        assert result.error_count == 3  # Incremented
        assert result.last_error_at is not None
        assert isinstance(result.last_error_at, datetime)

    async def test_update_processing_status_to_processing(self, async_db: AsyncSession) -> None:
        """
        Test updating processing status to processing state.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        state = await BlockStateFactory.create_async(
            async_db, processing_status="idle"
        )

        # Act
        result = await crud_block_state.update_processing_status(
            async_db,
            tenant_id=state.tenant_id,
            network_id=state.network_id,
            status="processing"
        )

        # Assert
        assert result is not None
        assert result.processing_status == "processing"
        assert result.last_processed_at is not None
        # Should not affect error fields
        assert result.error_count == state.error_count

    async def test_update_processing_status_to_idle_clears_errors(self, async_db: AsyncSession) -> None:
        """
        Test updating status to idle clears error information.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        state = await BlockStateFactory.create_error_state_async(
            async_db, error_count=5, last_error="Some error"
        )

        # Act
        result = await crud_block_state.update_processing_status(
            async_db,
            tenant_id=state.tenant_id,
            network_id=state.network_id,
            status="idle"
        )

        # Assert
        assert result is not None
        assert result.processing_status == "idle"
        assert result.error_count == 0  # Reset
        assert result.last_error is None  # Cleared

    async def test_update_processing_status_nonexistent(self, async_db: AsyncSession) -> None:
        """
        Test updating processing status for non-existent state returns None.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_block_state.update_processing_status(
            async_db,
            tenant_id=uuid.uuid4(),
            network_id=uuid.uuid4(),
            status="processing"
        )

        # Assert
        assert result is None

    async def test_update_block_metrics_new_metrics(self, async_db: AsyncSession) -> None:
        """
        Test updating block metrics with new processing time.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        state = await BlockStateFactory.create_async(
            async_db, last_processed_block=1000, average_processing_time_ms=None
        )

        # Act
        result = await crud_block_state.update_block_metrics(
            async_db,
            tenant_id=state.tenant_id,
            network_id=state.network_id,
            block_number=1001,
            processing_time_ms=500
        )

        # Assert
        assert result is not None
        assert result.last_processed_block == 1001
        assert result.average_processing_time_ms == 500  # First time, uses exact value
        assert result.last_processed_at is not None

    async def test_update_block_metrics_rolling_average(self, async_db: AsyncSession) -> None:
        """
        Test updating block metrics calculates rolling average.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        state = await BlockStateFactory.create_async(
            async_db, average_processing_time_ms=1000
        )

        # Act
        result = await crud_block_state.update_block_metrics(
            async_db,
            tenant_id=state.tenant_id,
            network_id=state.network_id,
            block_number=2000,
            processing_time_ms=500
        )

        # Assert
        assert result is not None
        # Rolling average: (1000 * 0.9) + (500 * 0.1) = 900 + 50 = 950
        assert result.average_processing_time_ms == 950
        assert result.last_processed_block == 2000

    async def test_get_processing_stats(self, async_db: AsyncSession) -> None:
        """
        Test getting processing statistics.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()
        network_id = uuid.uuid4()

        # Create block state
        await BlockStateFactory.create_async(
            async_db,
            tenant_id=tenant_id,
            network_id=network_id,
            last_processed_block=10000,
            blocks_per_minute=Decimal('15.5'),
            average_processing_time_ms=750,
            error_count=5
        )

        # Create some missed blocks in the period
        await asyncio.gather(*[
            MissedBlockFactory.create_async(
                async_db,
                tenant_id=tenant_id,
                network_id=network_id,
                created_at=datetime.now(UTC) - timedelta(hours=i)
            )
            for i in range(3)  # 3 missed blocks
        ])

        # Act
        result = await crud_block_state.get_processing_stats(
            async_db, tenant_id=tenant_id, network_id=network_id, period_hours=24
        )

        # Assert
        assert isinstance(result, BlockProcessingStats)
        assert str(result.tenant_id) == str(tenant_id)
        assert str(result.network_id) == str(network_id)
        assert result.total_blocks_processed == 10000
        assert result.total_missed_blocks == 3
        assert result.average_blocks_per_minute == Decimal('15.5')
        assert result.average_processing_time_ms == 750
        assert result.error_rate == Decimal('0.05')  # 5/10000 * 100
        assert result.uptime_percentage == Decimal('100')

    async def test_block_state_crud_operations(self, async_db: AsyncSession) -> None:
        """
        Test basic CRUD operations for block state.

        Args:
            async_db: Async database session fixture
        """
        # Create
        create_data = BlockStateCreate(
            tenant_id=uuid.uuid4(),
            network_id=uuid.uuid4(),
            processing_status="processing",
            error_count=0,
            last_processed_block=5000,
            blocks_per_minute=Decimal('20.0'),
            average_processing_time_ms=600
        )
        created = await crud_block_state.create(async_db, object=create_data)

        # Read
        retrieved = await crud_block_state.get(async_db, id=created.id)
        assert retrieved is not None
        assert retrieved.processing_status == "processing"

        # Update
        update_data = BlockStateUpdate(
            processing_status="idle",
            blocks_per_minute=Decimal('25.0')
        )
        updated = await crud_block_state.update(
            async_db, db_obj=retrieved, object=update_data
        )
        assert updated.processing_status == "idle"
        assert updated.blocks_per_minute == Decimal('25.0')

        # Count
        count = await crud_block_state.count(async_db)
        assert count >= 1


@pytest.mark.asyncio
class TestCRUDMissedBlock:
    """Test suite for CRUDMissedBlock operations."""

    async def test_record_missed_block_new(self, async_db: AsyncSession) -> None:
        """
        Test recording a new missed block.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()
        network_id = uuid.uuid4()
        block_number = 12345
        reason = "Network timeout during block fetch"

        # Act
        result = await crud_missed_block.record_missed_block(
            async_db,
            tenant_id=tenant_id,
            network_id=network_id,
            block_number=block_number,
            reason=reason
        )

        # Assert
        assert result is not None
        assert str(result.tenant_id) == str(tenant_id)
        assert str(result.network_id) == str(network_id)
        assert result.block_number == block_number
        assert result.reason == reason
        assert result.retry_count == 0
        assert result.processed is False
        assert result.processed_at is None

    async def test_record_missed_block_existing_increments_retry(self, async_db: AsyncSession) -> None:
        """
        Test recording existing missed block increments retry count.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        existing = await MissedBlockFactory.create_async(
            async_db, retry_count=2, reason="Original reason"
        )
        new_reason = "Updated timeout reason"

        # Act
        result = await crud_missed_block.record_missed_block(
            async_db,
            tenant_id=existing.tenant_id,
            network_id=existing.network_id,
            block_number=existing.block_number,
            reason=new_reason
        )

        # Assert
        assert result.id == existing.id
        assert result.retry_count == 3  # Incremented
        assert result.reason == new_reason  # Updated

    async def test_mark_processed_success(self, async_db: AsyncSession) -> None:
        """
        Test marking missed block as processed.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        missed_block = await MissedBlockFactory.create_async(
            async_db, processed=False, processed_at=None
        )

        # Act
        result = await crud_missed_block.mark_processed(
            async_db, missed_block_id=missed_block.id
        )

        # Assert
        assert result is not None
        assert result.processed is True
        assert result.processed_at is not None
        assert isinstance(result.processed_at, datetime)

    async def test_mark_processed_nonexistent(self, async_db: AsyncSession) -> None:
        """
        Test marking non-existent missed block returns None.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_missed_block.mark_processed(
            async_db, missed_block_id=uuid.uuid4()
        )

        # Assert
        assert result is None

    async def test_get_unprocessed_blocks(self, async_db: AsyncSession) -> None:
        """
        Test retrieving unprocessed missed blocks.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()
        network_id = uuid.uuid4()

        # Create unprocessed blocks
        unprocessed_blocks = await asyncio.gather(*[
            MissedBlockFactory.create_async(
                async_db,
                tenant_id=tenant_id,
                network_id=network_id,
                block_number=1000 + i,
                processed=False
            )
            for i in range(3)
        ])

        # Create processed blocks (should be excluded)
        await asyncio.gather(*[
            MissedBlockFactory.create_processed_block_async(
                async_db,
                tenant_id=tenant_id,
                network_id=network_id
            )
            for _ in range(2)
        ])

        # Create blocks for different tenant (should be excluded)
        await MissedBlockFactory.create_async(
            async_db, tenant_id=uuid.uuid4(), processed=False
        )

        # Act
        result = await crud_missed_block.get_unprocessed_blocks(
            async_db, tenant_id=tenant_id, network_id=network_id, limit=10
        )

        # Assert
        assert len(result) == 3
        result_block_numbers = {block.block_number for block in result}
        expected_block_numbers = {block.block_number for block in unprocessed_blocks}
        assert result_block_numbers == expected_block_numbers

        # Verify all are unprocessed
        for block in result:
            assert block.processed is False
            assert str(block.tenant_id) == str(tenant_id)

    async def test_get_unprocessed_blocks_with_limit(self, async_db: AsyncSession) -> None:
        """
        Test retrieving unprocessed blocks respects limit.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()
        network_id = uuid.uuid4()

        await asyncio.gather(*[
            MissedBlockFactory.create_async(
                async_db,
                tenant_id=tenant_id,
                network_id=network_id,
                processed=False
            )
            for _ in range(5)
        ])

        # Act
        result = await crud_missed_block.get_unprocessed_blocks(
            async_db, tenant_id=tenant_id, network_id=network_id, limit=2
        )

        # Assert
        assert len(result) == 2

    async def test_bulk_retry_success(self, async_db: AsyncSession) -> None:
        """
        Test bulk retry of missed blocks.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        blocks = await asyncio.gather(*[
            MissedBlockFactory.create_async(
                async_db, processed=False, retry_count=1
            )
            for _ in range(3)
        ])

        # Create a processed block (should be excluded)
        processed_block = await MissedBlockFactory.create_processed_block_async(async_db)

        # Create a block with max retries (should be excluded)
        max_retry_block = await MissedBlockFactory.create_async(
            async_db, processed=False, retry_count=3
        )

        block_ids = [block.id for block in blocks] + [processed_block.id, max_retry_block.id]

        # Act
        retry_count = await crud_missed_block.bulk_retry(
            async_db, missed_block_ids=block_ids, max_retries=3
        )

        # Assert
        assert retry_count == 3  # Only the 3 eligible blocks

        # Verify blocks were updated
        for block in blocks:
            updated_block = await crud_missed_block.get(async_db, id=block.id)
            assert updated_block.retry_count == 0  # Reset for retry
            assert updated_block.reason == "Marked for retry"

    async def test_missed_block_crud_operations(self, async_db: AsyncSession) -> None:
        """
        Test basic CRUD operations for missed blocks.

        Args:
            async_db: Async database session fixture
        """
        # Create
        create_data = MissedBlockCreate(
            tenant_id=uuid.uuid4(),
            network_id=uuid.uuid4(),
            block_number=999999,
            reason="Test timeout"
        )
        created = await crud_missed_block.create(async_db, object=create_data)

        # Read
        retrieved = await crud_missed_block.get(async_db, id=created.id)
        assert retrieved is not None
        assert retrieved.block_number == 999999

        # Update
        update_data = MissedBlockUpdate(retry_count=5)
        updated = await crud_missed_block.update(
            async_db, db_obj=retrieved, object=update_data
        )
        assert updated.retry_count == 5


@pytest.mark.asyncio
class TestCRUDMonitorMatch:
    """Test suite for CRUDMonitorMatch operations."""

    async def test_record_match_success(self, async_db: AsyncSession) -> None:
        """
        Test recording a monitor match.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()
        monitor_id = uuid.uuid4()
        network_id = uuid.uuid4()
        block_number = 18500000
        transaction_hash = "0x1234567890abcdef" * 4  # 64 chars
        match_data = {
            "event": {
                "name": "Transfer",
                "args": {
                    "from": "0x742d35cc6b8f4c6f8a",
                    "to": "0x8ba1f109551bd432",
                    "value": "1000000000000000000"
                }
            },
            "transaction": {
                "hash": transaction_hash,
                "gas_used": 65000
            }
        }

        # Act
        result = await crud_monitor_match.record_match(
            async_db,
            tenant_id=tenant_id,
            monitor_id=monitor_id,
            network_id=network_id,
            block_number=block_number,
            match_data=match_data,
            transaction_hash=transaction_hash
        )

        # Assert
        assert result is not None
        assert str(result.tenant_id) == str(tenant_id)
        assert str(result.monitor_id) == str(monitor_id)
        assert str(result.network_id) == str(network_id)
        assert result.block_number == block_number
        assert result.transaction_hash == transaction_hash
        assert result.match_data == match_data
        assert result.triggers_executed == 0
        assert result.triggers_failed == 0

    async def test_record_match_without_transaction(self, async_db: AsyncSession) -> None:
        """
        Test recording a monitor match without transaction hash.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        match_data = {"block_event": "new_block", "block_hash": "0xabcdef"}

        # Act
        result = await crud_monitor_match.record_match(
            async_db,
            tenant_id=uuid.uuid4(),
            monitor_id=uuid.uuid4(),
            network_id=uuid.uuid4(),
            block_number=12345,
            match_data=match_data
        )

        # Assert
        assert result.transaction_hash is None
        assert result.match_data == match_data

    async def test_update_trigger_counts_success(self, async_db: AsyncSession) -> None:
        """
        Test updating trigger execution counts.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        match = await MonitorMatchFactory.create_async(
            async_db, triggers_executed=2, triggers_failed=1
        )

        # Act
        result = await crud_monitor_match.update_trigger_counts(
            async_db, match_id=match.id, executed=3, failed=2
        )

        # Assert
        assert result is not None
        assert result.triggers_executed == 5  # 2 + 3
        assert result.triggers_failed == 3   # 1 + 2

    async def test_update_trigger_counts_nonexistent(self, async_db: AsyncSession) -> None:
        """
        Test updating trigger counts for non-existent match.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_monitor_match.update_trigger_counts(
            async_db, match_id=uuid.uuid4(), executed=1
        )

        # Assert
        assert result is None

    async def test_get_recent_matches_all_tenant(self, async_db: AsyncSession) -> None:
        """
        Test getting recent matches for a tenant.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()

        # Create recent matches
        recent_matches = await asyncio.gather(*[
            MonitorMatchFactory.create_async(
                async_db,
                tenant_id=tenant_id,
                created_at=datetime.now(UTC) - timedelta(hours=i)
            )
            for i in range(3)
        ])

        # Create old matches (should be excluded)
        await MonitorMatchFactory.create_async(
            async_db,
            tenant_id=tenant_id,
            created_at=datetime.now(UTC) - timedelta(hours=30)
        )

        # Create matches for different tenant (should be excluded)
        await MonitorMatchFactory.create_async(
            async_db, tenant_id=uuid.uuid4()
        )

        # Act
        result = await crud_monitor_match.get_recent_matches(
            async_db, tenant_id=tenant_id, hours=24
        )

        # Assert
        assert len(result) == 3
        result_ids = {str(match.id) for match in result}
        expected_ids = {str(match.id) for match in recent_matches}
        assert result_ids == expected_ids

        # Verify ordering (newest first)
        assert result[0].created_at >= result[1].created_at
        assert result[1].created_at >= result[2].created_at

    async def test_get_recent_matches_specific_monitor(self, async_db: AsyncSession) -> None:
        """
        Test getting recent matches for specific monitor.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()
        monitor_id = uuid.uuid4()

        # Create matches for target monitor
        await asyncio.gather(*[
            MonitorMatchFactory.create_async(
                async_db, tenant_id=tenant_id, monitor_id=monitor_id
            )
            for _ in range(2)
        ])

        # Create matches for different monitor (same tenant)
        await MonitorMatchFactory.create_async(
            async_db, tenant_id=tenant_id, monitor_id=uuid.uuid4()
        )

        # Act
        result = await crud_monitor_match.get_recent_matches(
            async_db, tenant_id=tenant_id, monitor_id=monitor_id, hours=24
        )

        # Assert
        assert len(result) == 2
        for match in result:
            assert str(match.monitor_id) == str(monitor_id)
            assert str(match.tenant_id) == str(tenant_id)

    async def test_get_recent_matches_with_limit(self, async_db: AsyncSession) -> None:
        """
        Test getting recent matches respects limit.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()

        await asyncio.gather(*[
            MonitorMatchFactory.create_async(async_db, tenant_id=tenant_id)
            for _ in range(5)
        ])

        # Act
        result = await crud_monitor_match.get_recent_matches(
            async_db, tenant_id=tenant_id, limit=2
        )

        # Assert
        assert len(result) == 2

    async def test_monitor_match_crud_operations(self, async_db: AsyncSession) -> None:
        """
        Test basic CRUD operations for monitor matches.

        Args:
            async_db: Async database session fixture
        """
        # Create
        create_data = MonitorMatchCreate(
            tenant_id=uuid.uuid4(),
            monitor_id=uuid.uuid4(),
            network_id=uuid.uuid4(),
            block_number=555555,
            transaction_hash="0xtest123",
            match_data={"test": "data"}
        )
        created = await crud_monitor_match.create(async_db, object=create_data)

        # Read
        retrieved = await crud_monitor_match.get(async_db, id=created.id)
        assert retrieved is not None
        assert retrieved.block_number == 555555

        # Update
        update_data = MonitorMatchUpdate(triggers_executed=5)
        updated = await crud_monitor_match.update(
            async_db, db_obj=retrieved, object=update_data
        )
        assert updated.triggers_executed == 5


@pytest.mark.asyncio
class TestCRUDTriggerExecution:
    """Test suite for CRUDTriggerExecution operations."""

    async def test_record_execution_success(self, async_db: AsyncSession) -> None:
        """
        Test recording a trigger execution.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()
        trigger_id = uuid.uuid4()
        monitor_match_id = uuid.uuid4()
        execution_type = "email"
        execution_data = {
            "recipient": "user@example.com",
            "subject": "Monitor Alert: Large Transfer Detected",
            "template_vars": {
                "monitor_name": "ETH Large Transfer Monitor",
                "network": "ethereum",
                "amount": "500 ETH"
            }
        }

        # Act
        result = await crud_trigger_execution.record_execution(
            async_db,
            tenant_id=tenant_id,
            trigger_id=trigger_id,
            execution_type=execution_type,
            execution_data=execution_data,
            monitor_match_id=monitor_match_id
        )

        # Assert
        assert result is not None
        assert str(result.tenant_id) == str(tenant_id)
        assert str(result.trigger_id) == str(trigger_id)
        assert str(result.monitor_match_id) == str(monitor_match_id)
        assert result.execution_type == execution_type
        assert result.execution_data == execution_data
        assert result.status == "pending"
        assert result.retry_count == 0
        assert result.duration_ms is None

    async def test_record_execution_without_match(self, async_db: AsyncSession) -> None:
        """
        Test recording execution without monitor match.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_trigger_execution.record_execution(
            async_db,
            tenant_id=uuid.uuid4(),
            trigger_id=uuid.uuid4(),
            execution_type="webhook",
            execution_data={"url": "https://example.com/hook"}
        )

        # Assert
        assert result.monitor_match_id is None

    async def test_update_status_to_running(self, async_db: AsyncSession) -> None:
        """
        Test updating execution status to running.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        execution = await TriggerExecutionFactory.create_async(
            async_db, status="pending", started_at=None
        )

        # Act
        result = await crud_trigger_execution.update_status(
            async_db, execution_id=execution.id, status="running"
        )

        # Assert
        assert result is not None
        assert result.status == "running"
        assert result.started_at is not None
        assert isinstance(result.started_at, datetime)
        assert result.completed_at is None  # Still running

    async def test_update_status_to_success(self, async_db: AsyncSession) -> None:
        """
        Test updating execution status to success.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        start_time = datetime.now(UTC) - timedelta(seconds=5)
        execution = await TriggerExecutionFactory.create_async(
            async_db, status="running", started_at=start_time
        )

        # Act
        result = await crud_trigger_execution.update_status(
            async_db, execution_id=execution.id, status="success"
        )

        # Assert
        assert result is not None
        assert result.status == "success"
        assert result.completed_at is not None
        assert result.duration_ms is not None
        assert result.duration_ms > 0  # Should have positive duration

    async def test_update_status_to_failed_with_error(self, async_db: AsyncSession) -> None:
        """
        Test updating execution status to failed with error message.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        execution = await TriggerExecutionFactory.create_async(
            async_db, status="running", started_at=datetime.now(UTC) - timedelta(seconds=2)
        )
        error_message = "SMTP authentication failed: Invalid credentials"

        # Act
        result = await crud_trigger_execution.update_status(
            async_db,
            execution_id=execution.id,
            status="failed",
            error_message=error_message
        )

        # Assert
        assert result is not None
        assert result.status == "failed"
        assert result.error_message == error_message
        assert result.completed_at is not None
        assert result.duration_ms is not None

    async def test_update_status_nonexistent(self, async_db: AsyncSession) -> None:
        """
        Test updating status for non-existent execution.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_trigger_execution.update_status(
            async_db, execution_id=uuid.uuid4(), status="success"
        )

        # Assert
        assert result is None

    async def test_retry_execution_success(self, async_db: AsyncSession) -> None:
        """
        Test retrying a failed execution.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        execution = await TriggerExecutionFactory.create_failed_execution_async(
            async_db,
            retry_count=1,
            error_message="Previous error",
            started_at=datetime.now(UTC) - timedelta(minutes=5),
            completed_at=datetime.now(UTC) - timedelta(minutes=4),
            duration_ms=5000
        )

        # Act
        result = await crud_trigger_execution.retry_execution(
            async_db, execution_id=execution.id
        )

        # Assert
        assert result is not None
        assert result.status == "pending"
        assert result.retry_count == 2  # Incremented
        assert result.error_message is None  # Cleared
        assert result.started_at is None      # Reset
        assert result.completed_at is None    # Reset
        assert result.duration_ms is None     # Reset

    async def test_retry_execution_nonexistent(self, async_db: AsyncSession) -> None:
        """
        Test retrying non-existent execution.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_trigger_execution.retry_execution(
            async_db, execution_id=uuid.uuid4()
        )

        # Assert
        assert result is None

    async def test_get_execution_stats_tenant_wide(self, async_db: AsyncSession) -> None:
        """
        Test getting execution statistics for entire tenant.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()

        # Create executions with different statuses
        await asyncio.gather(
            # Successful executions
            TriggerExecutionFactory.create_async(
                async_db, tenant_id=tenant_id, status="success", duration_ms=1000
            ),
            TriggerExecutionFactory.create_async(
                async_db, tenant_id=tenant_id, status="success", duration_ms=2000
            ),
            # Failed execution
            TriggerExecutionFactory.create_async(
                async_db, tenant_id=tenant_id, status="failed"
            ),
            # Timeout execution
            TriggerExecutionFactory.create_async(
                async_db, tenant_id=tenant_id, status="timeout"
            ),
            # Execution with retry
            TriggerExecutionFactory.create_async(
                async_db, tenant_id=tenant_id, status="success", retry_count=1
            ),
        )

        # Create execution for different tenant (should be excluded)
        await TriggerExecutionFactory.create_async(
            async_db, tenant_id=uuid.uuid4(), status="success"
        )

        # Act
        result = await crud_trigger_execution.get_execution_stats(
            async_db, tenant_id=tenant_id, period_hours=24
        )

        # Assert
        assert isinstance(result, TriggerExecutionStats)
        assert str(result.tenant_id) == str(tenant_id)
        assert result.trigger_id is None  # Tenant-wide stats
        assert result.total_executions == 5
        assert result.successful_executions == 3
        assert result.failed_executions == 1
        assert result.timeout_executions == 1
        assert result.average_duration_ms == 1500  # (1000 + 2000) / 2
        assert result.success_rate == Decimal('60')  # 3/5 * 100
        assert result.retry_rate == Decimal('20')    # 1/5 * 100

    async def test_get_execution_stats_specific_trigger(self, async_db: AsyncSession) -> None:
        """
        Test getting execution statistics for specific trigger.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        tenant_id = uuid.uuid4()
        trigger_id = uuid.uuid4()

        # Create executions for target trigger
        await asyncio.gather(
            TriggerExecutionFactory.create_async(
                async_db, tenant_id=tenant_id, trigger_id=trigger_id, status="success"
            ),
            TriggerExecutionFactory.create_async(
                async_db, tenant_id=tenant_id, trigger_id=trigger_id, status="failed"
            ),
        )

        # Create execution for different trigger (same tenant)
        await TriggerExecutionFactory.create_async(
            async_db, tenant_id=tenant_id, trigger_id=uuid.uuid4(), status="success"
        )

        # Act
        result = await crud_trigger_execution.get_execution_stats(
            async_db, tenant_id=tenant_id, trigger_id=trigger_id, period_hours=24
        )

        # Assert
        assert str(result.trigger_id) == str(trigger_id)
        assert result.total_executions == 2
        assert result.successful_executions == 1
        assert result.failed_executions == 1

    async def test_bulk_retry_success(self, async_db: AsyncSession) -> None:
        """
        Test bulk retry of failed executions.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        failed_executions = await asyncio.gather(*[
            TriggerExecutionFactory.create_async(
                async_db, status="failed", retry_count=1
            )
            for _ in range(2)
        ])

        timeout_execution = await TriggerExecutionFactory.create_async(
            async_db, status="timeout", retry_count=0
        )

        # Create executions that shouldn't be retried
        success_execution = await TriggerExecutionFactory.create_async(
            async_db, status="success"
        )
        max_retry_execution = await TriggerExecutionFactory.create_async(
            async_db, status="failed", retry_count=3
        )

        execution_ids = [
            exec.id for exec in failed_executions
        ] + [timeout_execution.id, success_execution.id, max_retry_execution.id]

        # Act
        retry_count = await crud_trigger_execution.bulk_retry(
            async_db, execution_ids=execution_ids, max_retries=3
        )

        # Assert
        assert retry_count == 3  # 2 failed + 1 timeout

        # Verify executions were updated
        for execution in failed_executions + [timeout_execution]:
            updated = await crud_trigger_execution.get(async_db, id=execution.id)
            assert updated.status == "pending"
            assert updated.retry_count == execution.retry_count + 1
            assert updated.error_message is None

    async def test_trigger_execution_crud_operations(self, async_db: AsyncSession) -> None:
        """
        Test basic CRUD operations for trigger executions.

        Args:
            async_db: Async database session fixture
        """
        # Create
        create_data = TriggerExecutionCreate(
            tenant_id=uuid.uuid4(),
            trigger_id=uuid.uuid4(),
            execution_type="webhook",
            execution_data={"url": "https://test.com"},
            status="pending",
            retry_count=0
        )
        created = await crud_trigger_execution.create(async_db, object=create_data)

        # Read
        retrieved = await crud_trigger_execution.get(async_db, id=created.id)
        assert retrieved is not None
        assert retrieved.execution_type == "webhook"

        # Update
        update_data = TriggerExecutionUpdate(status="success", duration_ms=1500)
        updated = await crud_trigger_execution.update(
            async_db, db_obj=retrieved, object=update_data
        )
        assert updated.status == "success"
        assert updated.duration_ms == 1500

    # Factory variant tests

    async def test_factory_variants_audit_models(self, async_db: AsyncSession) -> None:
        """
        Test creating audit models using factory variants.

        Args:
            async_db: Async database session fixture
        """
        # Block state variants
        processing_state = await BlockStateFactory.create_processing_state_async(async_db)
        assert processing_state.processing_status == "processing"
        assert processing_state.blocks_per_minute == Decimal('15.5')

        error_state = await BlockStateFactory.create_error_state_async(async_db)
        assert error_state.processing_status == "error"
        assert error_state.error_count >= 1
        assert error_state.last_error == "RPC connection timeout"

        # Missed block variants
        processed_block = await MissedBlockFactory.create_processed_block_async(async_db)
        assert processed_block.processed is True
        assert processed_block.processed_at is not None

        retry_block = await MissedBlockFactory.create_retry_block_async(async_db)
        assert retry_block.retry_count >= 2
        assert "retrying" in retry_block.reason

        # Monitor match variants
        erc20_match = await MonitorMatchFactory.create_erc20_transfer_match_async(async_db)
        assert erc20_match.match_data["event"]["name"] == "Transfer"
        assert "token" in erc20_match.match_data

        defi_match = await MonitorMatchFactory.create_defi_swap_match_async(async_db)
        assert defi_match.match_data["event"]["name"] == "Swap"
        assert erc20_match.match_data["protocol"] == "uniswap_v2"

        # Trigger execution variants
        email_exec = await TriggerExecutionFactory.create_email_execution_async(async_db)
        assert email_exec.execution_type == "email"
        assert "smtp_host" in email_exec.execution_data

        webhook_exec = await TriggerExecutionFactory.create_webhook_execution_async(async_db)
        assert webhook_exec.execution_type == "webhook"
        assert "url" in webhook_exec.execution_data

        failed_exec = await TriggerExecutionFactory.create_failed_execution_async(async_db)
        assert failed_exec.status == "failed"
        assert failed_exec.error_message is not None

    async def test_concurrent_audit_operations(self, async_db: AsyncSession) -> None:
        """
        Test concurrent operations across audit models.

        Args:
            async_db: Async database session fixture
        """
        # Create related audit records concurrently
        tenant_id = uuid.uuid4()
        network_id = uuid.uuid4()
        monitor_id = uuid.uuid4()

        # Simulate monitoring workflow
        block_state, missed_blocks, matches = await asyncio.gather(
            BlockStateFactory.create_async(
                async_db, tenant_id=tenant_id, network_id=network_id
            ),
            asyncio.gather(*[
                MissedBlockFactory.create_async(
                    async_db, tenant_id=tenant_id, network_id=network_id
                )
                for _ in range(2)
            ]),
            asyncio.gather(*[
                MonitorMatchFactory.create_async(
                    async_db, tenant_id=tenant_id, network_id=network_id, monitor_id=monitor_id
                )
                for _ in range(3)
            ])
        )

        # Verify relationships
        assert str(block_state.tenant_id) == str(tenant_id)
        assert len(missed_blocks) == 2
        assert len(matches) == 3

        for missed_block in missed_blocks:
            assert str(missed_block.tenant_id) == str(tenant_id)

        for match in matches:
            assert str(match.tenant_id) == str(tenant_id)
            assert str(match.monitor_id) == str(monitor_id)

    async def test_audit_models_pagination_and_filtering(self, async_db: AsyncSession) -> None:
        """
        Test pagination and filtering across audit models.

        Args:
            async_db: Async database session fixture
        """
        # Create test data
        tenant_id = uuid.uuid4()

        await asyncio.gather(
            # Block states
            asyncio.gather(*[
                BlockStateFactory.create_async(async_db, tenant_id=tenant_id)
                for _ in range(3)
            ]),
            # Missed blocks
            asyncio.gather(*[
                MissedBlockFactory.create_async(async_db, tenant_id=tenant_id)
                for _ in range(5)
            ]),
            # Monitor matches
            asyncio.gather(*[
                MonitorMatchFactory.create_async(async_db, tenant_id=tenant_id)
                for _ in range(7)
            ]),
            # Trigger executions
            asyncio.gather(*[
                TriggerExecutionFactory.create_async(async_db, tenant_id=tenant_id)
                for _ in range(4)
            ])
        )

        # Test pagination
        paginated_matches = await crud_monitor_match.get_paginated(
            async_db, page=1, items_per_page=3
        )
        assert isinstance(paginated_matches, PaginatedListResponse)
        assert len(paginated_matches.data) == 3
        assert paginated_matches.total_count >= 7

        # Test counting
        execution_count = await crud_trigger_execution.count(async_db)
        assert execution_count >= 4

        missed_block_count = await crud_missed_block.count(async_db)
        assert missed_block_count >= 5

    async def test_complex_audit_workflow_simulation(self, async_db: AsyncSession) -> None:
        """
        Test complex audit workflow simulation.

        Args:
            async_db: Async database session fixture
        """
        # Simulate a complete monitoring workflow
        tenant_id = uuid.uuid4()
        network_id = uuid.uuid4()
        monitor_id = uuid.uuid4()
        trigger_id = uuid.uuid4()

        # 1. Initialize block state
        block_state = await crud_block_state.get_or_create(
            async_db, tenant_id=tenant_id, network_id=network_id
        )
        assert block_state.processing_status == "idle"

        # 2. Start processing
        updated_state = await crud_block_state.update_processing_status(
            async_db, tenant_id=tenant_id, network_id=network_id, status="processing"
        )
        assert updated_state.processing_status == "processing"

        # 3. Record some missed blocks
        missed_block = await crud_missed_block.record_missed_block(
            async_db, tenant_id=tenant_id, network_id=network_id,
            block_number=1000000, reason="Network timeout"
        )
        assert missed_block.processed is False

        # 4. Find a match
        match = await crud_monitor_match.record_match(
            async_db, tenant_id=tenant_id, monitor_id=monitor_id, network_id=network_id,
            block_number=1000001, match_data={"event": "Transfer", "value": 1000}
        )

        # 5. Execute triggers
        execution = await crud_trigger_execution.record_execution(
            async_db, tenant_id=tenant_id, trigger_id=trigger_id,
            execution_type="email", execution_data={"recipient": "test@example.com"},
            monitor_match_id=match.id
        )

        # 6. Update execution to success
        completed_execution = await crud_trigger_execution.update_status(
            async_db, execution_id=execution.id, status="success"
        )
        assert completed_execution.status == "success"

        # 7. Update match trigger counts
        updated_match = await crud_monitor_match.update_trigger_counts(
            async_db, match_id=match.id, executed=1
        )
        assert updated_match.triggers_executed == 1

        # 8. Process missed block
        processed_missed = await crud_missed_block.mark_processed(
            async_db, missed_block_id=missed_block.id
        )
        assert processed_missed.processed is True

        # 9. Update block metrics
        final_state = await crud_block_state.update_block_metrics(
            async_db, tenant_id=tenant_id, network_id=network_id,
            block_number=1000002, processing_time_ms=850
        )
        assert final_state.last_processed_block == 1000002
        assert final_state.average_processing_time_ms == 850

        # 10. Get comprehensive stats
        processing_stats = await crud_block_state.get_processing_stats(
            async_db, tenant_id=tenant_id, network_id=network_id
        )
        execution_stats = await crud_trigger_execution.get_execution_stats(
            async_db, tenant_id=tenant_id
        )

        assert processing_stats.total_blocks_processed == 1000002
        assert execution_stats.total_executions == 1
        assert execution_stats.successful_executions == 1
