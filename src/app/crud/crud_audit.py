"""
Enhanced CRUD operations for audit entities (BlockState, MissedBlock, MonitorMatch, TriggerExecution).
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.audit import BlockState, MissedBlock, MonitorMatch, TriggerExecution
from pydantic import BaseModel

from ..schemas.audit import (
    BlockProcessingStats,
    BlockStateCreate,
    BlockStateFilter,
    BlockStateRead,
    BlockStateSort,
    BlockStateUpdate,
    MissedBlockCreate,
    MissedBlockFilter,
    MissedBlockRead,
    MissedBlockSort,
    MissedBlockUpdate,
    MonitorMatchCreate,
    MonitorMatchFilter,
    MonitorMatchRead,
    MonitorMatchSort,
    MonitorMatchUpdate,
    TriggerExecutionCreate,
    TriggerExecutionFilter,
    TriggerExecutionRead,
    TriggerExecutionSort,
    TriggerExecutionStats,
    TriggerExecutionUpdate,
)
from .base import EnhancedCRUD


# Create a dummy delete schema for audit entities
class AuditDeleteSchema(BaseModel):
    """Dummy delete schema for audit entities (not used)."""
    pass


class CRUDBlockState(
    EnhancedCRUD[
        BlockState,
        BlockStateCreate,
        BlockStateUpdate,
        BlockStateUpdate,  # Using same for internal
        AuditDeleteSchema,  # Dummy delete schema for audit
        BlockStateRead,
        BlockStateFilter,
        BlockStateSort
    ]
):
    """
    CRUD operations for BlockState tracking.
    """

    async def get_or_create(
        self,
        db: AsyncSession,
        tenant_id: Any,
        network_id: Any
    ) -> BlockStateRead:
        """
        Get existing block state or create new one.

        Args:
            db: Database session
            tenant_id: Tenant ID
            network_id: Network ID

        Returns:
            Block state
        """
        query = select(BlockState).where(
            BlockState.tenant_id == tenant_id,
            BlockState.network_id == network_id
        )
        result = await db.execute(query)
        state = result.scalar_one_or_none()

        if not state:
            # Create with defaults from schema
            create_data = BlockStateCreate(
                tenant_id=tenant_id,
                network_id=network_id,
                processing_status="idle",
                error_count=0
            )
            state = BlockState(**create_data.model_dump())
            db.add(state)
            await db.flush()
            await db.refresh(state)

        return BlockStateRead.model_validate(state)

    async def update_processing_status(
        self,
        db: AsyncSession,
        tenant_id: Any,
        network_id: Any,
        status: str,
        error: Optional[str] = None
    ) -> Optional[BlockStateRead]:
        """
        Update processing status for a network.

        Args:
            db: Database session
            tenant_id: Tenant ID
            network_id: Network ID
            status: New status
            error: Optional error message

        Returns:
            Updated block state
        """
        query = select(BlockState).where(
            BlockState.tenant_id == tenant_id,
            BlockState.network_id == network_id
        )
        result = await db.execute(query)
        state = result.scalar_one_or_none()

        if state:
            state.processing_status = status

            if status == "error" and error:
                state.last_error = error
                state.last_error_at = datetime.now(UTC)
                state.error_count += 1
            elif status == "processing":
                state.last_processed_at = datetime.now(UTC)
            elif status == "idle":
                state.error_count = 0
                state.last_error = None

            await db.flush()
            await db.refresh(state)
            return BlockStateRead.model_validate(state)

        return None

    async def update_block_metrics(
        self,
        db: AsyncSession,
        tenant_id: Any,
        network_id: Any,
        block_number: int,
        processing_time_ms: int
    ) -> Optional[BlockStateRead]:
        """
        Update block processing metrics.

        Args:
            db: Database session
            tenant_id: Tenant ID
            network_id: Network ID
            block_number: Processed block number
            processing_time_ms: Processing time

        Returns:
            Updated block state
        """
        query = select(BlockState).where(
            BlockState.tenant_id == tenant_id,
            BlockState.network_id == network_id
        )
        result = await db.execute(query)
        state = result.scalar_one_or_none()

        if state:
            state.last_processed_block = block_number
            state.last_processed_at = datetime.now(UTC)

            # Update average processing time
            if state.average_processing_time_ms:
                # Rolling average
                state.average_processing_time_ms = int(
                    (state.average_processing_time_ms * 0.9) +
                    (processing_time_ms * 0.1)
                )
            else:
                state.average_processing_time_ms = processing_time_ms

            await db.flush()
            await db.refresh(state)
            return BlockStateRead.model_validate(state)

        return None

    async def get_processing_stats(
        self,
        db: AsyncSession,
        tenant_id: Any,
        network_id: Any,
        period_hours: int = 24
    ) -> BlockProcessingStats:
        """
        Get block processing statistics for a period.

        Args:
            db: Database session
            tenant_id: Tenant ID
            network_id: Network ID
            period_hours: Period in hours

        Returns:
            Processing statistics
        """
        period_start = datetime.now(UTC) - timedelta(hours=period_hours)
        period_end = datetime.now(UTC)

        # Get block state
        state = await self.get_or_create(db, tenant_id, network_id)

        # Count missed blocks in period
        missed_query = select(func.count()).select_from(MissedBlock).where(
            MissedBlock.tenant_id == tenant_id,
            MissedBlock.network_id == network_id,
            MissedBlock.created_at >= period_start
        )
        missed_result = await db.execute(missed_query)
        missed_count = missed_result.scalar() or 0

        # Calculate metrics
        total_blocks = state.last_processed_block or 0
        blocks_per_minute = state.blocks_per_minute or Decimal(0)
        avg_processing_time = state.average_processing_time_ms or 0

        # Calculate error rate
        error_rate = Decimal(0)
        if total_blocks > 0:
            error_rate = Decimal(state.error_count) / \
                Decimal(total_blocks) * 100

        # Calculate uptime percentage
        uptime_percentage = Decimal(100)
        if state.last_error_at and state.last_processed_at:
            downtime = (state.last_error_at -
                        state.last_processed_at).total_seconds()
            total_time = period_hours * 3600
            uptime_percentage = Decimal(
                (total_time - downtime) / total_time * 100)

        return BlockProcessingStats(
            tenant_id=tenant_id,
            network_id=network_id,
            period_start=period_start,
            period_end=period_end,
            total_blocks_processed=total_blocks,
            total_missed_blocks=missed_count,
            average_blocks_per_minute=blocks_per_minute,
            average_processing_time_ms=avg_processing_time,
            error_rate=error_rate,
            uptime_percentage=uptime_percentage
        )


class CRUDMissedBlock(
    EnhancedCRUD[
        MissedBlock,
        MissedBlockCreate,
        MissedBlockUpdate,
        MissedBlockUpdate,  # Using same for internal
        AuditDeleteSchema,  # Dummy delete schema for audit
        MissedBlockRead,
        MissedBlockFilter,
        MissedBlockSort
    ]
):
    """
    CRUD operations for MissedBlock tracking.
    """

    async def record_missed_block(
        self,
        db: AsyncSession,
        tenant_id: Any,
        network_id: Any,
        block_number: int,
        reason: str
    ) -> MissedBlockRead:
        """
        Record a missed block.

        Args:
            db: Database session
            tenant_id: Tenant ID
            network_id: Network ID
            block_number: Block number
            reason: Reason for missing

        Returns:
            Created missed block record
        """
        # Check if already recorded
        query = select(MissedBlock).where(
            MissedBlock.tenant_id == tenant_id,
            MissedBlock.network_id == network_id,
            MissedBlock.block_number == block_number
        )
        result = await db.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            # Update retry count
            existing.retry_count += 1
            existing.reason = reason
            await db.flush()
            await db.refresh(existing)
            return MissedBlockRead.model_validate(existing)

        # Create new record
        create_data = MissedBlockCreate(
            tenant_id=tenant_id,
            network_id=network_id,
            block_number=block_number,
            reason=reason
        )
        missed = MissedBlock(**create_data.model_dump())
        db.add(missed)
        await db.flush()
        await db.refresh(missed)

        return MissedBlockRead.model_validate(missed)

    async def mark_processed(
        self,
        db: AsyncSession,
        missed_block_id: Any
    ) -> Optional[MissedBlockRead]:
        """
        Mark a missed block as processed.

        Args:
            db: Database session
            missed_block_id: Missed block ID

        Returns:
            Updated missed block
        """
        query = select(MissedBlock).where(MissedBlock.id == missed_block_id)
        result = await db.execute(query)
        missed = result.scalar_one_or_none()

        if missed:
            missed.processed = True
            missed.processed_at = datetime.now(UTC)
            await db.flush()
            await db.refresh(missed)
            return MissedBlockRead.model_validate(missed)

        return None

    async def get_unprocessed_blocks(
        self,
        db: AsyncSession,
        tenant_id: Any,
        network_id: Any,
        limit: int = 100
    ) -> list[MissedBlockRead]:
        """
        Get unprocessed missed blocks.

        Args:
            db: Database session
            tenant_id: Tenant ID
            network_id: Network ID
            limit: Maximum results

        Returns:
            List of unprocessed blocks
        """
        query = select(MissedBlock).where(
            MissedBlock.tenant_id == tenant_id,
            MissedBlock.network_id == network_id,
            MissedBlock.processed == False  # noqa: E712
        ).order_by(MissedBlock.block_number).limit(limit)

        result = await db.execute(query)
        blocks = result.scalars().all()

        return [MissedBlockRead.model_validate(b) for b in blocks]

    async def bulk_retry(
        self,
        db: AsyncSession,
        missed_block_ids: list[Any],
        max_retries: int = 3
    ) -> int:
        """
        Bulk retry missed blocks.

        Args:
            db: Database session
            missed_block_ids: List of missed block IDs
            max_retries: Maximum retry attempts

        Returns:
            Number of blocks marked for retry
        """
        query = select(MissedBlock).where(
            MissedBlock.id.in_(missed_block_ids),
            MissedBlock.processed == False,  # noqa: E712
            MissedBlock.retry_count < max_retries
        )
        result = await db.execute(query)
        blocks = result.scalars().all()

        for block in blocks:
            block.retry_count = 0  # Reset for retry
            block.reason = "Marked for retry"

        await db.flush()
        return len(blocks)


class CRUDMonitorMatch(
    EnhancedCRUD[
        MonitorMatch,
        MonitorMatchCreate,
        MonitorMatchUpdate,
        MonitorMatchUpdate,  # Using same for internal
        AuditDeleteSchema,  # Dummy delete schema for audit
        MonitorMatchRead,
        MonitorMatchFilter,
        MonitorMatchSort
    ]
):
    """
    CRUD operations for MonitorMatch tracking.
    """

    async def record_match(
        self,
        db: AsyncSession,
        tenant_id: Any,
        monitor_id: Any,
        network_id: Any,
        block_number: int,
        match_data: dict[str, Any],
        transaction_hash: Optional[str] = None
    ) -> MonitorMatchRead:
        """
        Record a monitor match.

        Args:
            db: Database session
            tenant_id: Tenant ID
            monitor_id: Monitor ID
            network_id: Network ID
            block_number: Block number
            match_data: Match details
            transaction_hash: Optional transaction hash

        Returns:
            Created match record
        """
        create_data = MonitorMatchCreate(
            tenant_id=tenant_id,
            monitor_id=monitor_id,
            network_id=network_id,
            block_number=block_number,
            transaction_hash=transaction_hash,
            match_data=match_data
        )
        match = MonitorMatch(**create_data.model_dump())
        db.add(match)
        await db.flush()
        await db.refresh(match)

        return MonitorMatchRead.model_validate(match)

    async def update_trigger_counts(
        self,
        db: AsyncSession,
        match_id: Any,
        executed: int = 0,
        failed: int = 0
    ) -> Optional[MonitorMatchRead]:
        """
        Update trigger execution counts for a match.

        Args:
            db: Database session
            match_id: Match ID
            executed: Number of successful triggers
            failed: Number of failed triggers

        Returns:
            Updated match
        """
        query = select(MonitorMatch).where(MonitorMatch.id == match_id)
        result = await db.execute(query)
        match = result.scalar_one_or_none()

        if match:
            match.triggers_executed += executed
            match.triggers_failed += failed
            await db.flush()
            await db.refresh(match)
            return MonitorMatchRead.model_validate(match)

        return None

    async def get_recent_matches(
        self,
        db: AsyncSession,
        tenant_id: Any,
        monitor_id: Optional[Any] = None,
        hours: int = 24,
        limit: int = 100
    ) -> list[MonitorMatchRead]:
        """
        Get recent monitor matches.

        Args:
            db: Database session
            tenant_id: Tenant ID
            monitor_id: Optional monitor filter
            hours: Hours to look back
            limit: Maximum results

        Returns:
            List of recent matches
        """
        since = datetime.now(UTC) - timedelta(hours=hours)

        query = select(MonitorMatch).where(
            MonitorMatch.tenant_id == tenant_id,
            MonitorMatch.created_at >= since
        )

        if monitor_id:
            query = query.where(MonitorMatch.monitor_id == monitor_id)

        query = query.order_by(MonitorMatch.created_at.desc()).limit(limit)

        result = await db.execute(query)
        matches = result.scalars().all()

        return [MonitorMatchRead.model_validate(m) for m in matches]


class CRUDTriggerExecution(
    EnhancedCRUD[
        TriggerExecution,
        TriggerExecutionCreate,
        TriggerExecutionUpdate,
        TriggerExecutionUpdate,  # Using same for internal
        AuditDeleteSchema,  # Dummy delete schema for audit
        TriggerExecutionRead,
        TriggerExecutionFilter,
        TriggerExecutionSort
    ]
):
    """
    CRUD operations for TriggerExecution tracking.
    """

    async def record_execution(
        self,
        db: AsyncSession,
        tenant_id: Any,
        trigger_id: Any,
        execution_type: str,
        execution_data: dict[str, Any],
        monitor_match_id: Optional[Any] = None
    ) -> TriggerExecutionRead:
        """
        Record a trigger execution.

        Args:
            db: Database session
            tenant_id: Tenant ID
            trigger_id: Trigger ID
            execution_type: Type of execution
            execution_data: Execution details
            monitor_match_id: Optional match ID

        Returns:
            Created execution record
        """
        create_data = TriggerExecutionCreate(
            tenant_id=tenant_id,
            trigger_id=trigger_id,
            monitor_match_id=monitor_match_id,
            execution_type=execution_type,
            execution_data=execution_data,
            status="pending",
            retry_count=0
        )
        execution = TriggerExecution(**create_data.model_dump())
        db.add(execution)
        await db.flush()
        await db.refresh(execution)

        return TriggerExecutionRead.model_validate(execution)

    async def update_status(
        self,
        db: AsyncSession,
        execution_id: Any,
        status: str,
        error_message: Optional[str] = None
    ) -> Optional[TriggerExecutionRead]:
        """
        Update execution status.

        Args:
            db: Database session
            execution_id: Execution ID
            status: New status
            error_message: Optional error message

        Returns:
            Updated execution
        """
        query = select(TriggerExecution).where(
            TriggerExecution.id == execution_id)
        result = await db.execute(query)
        execution = result.scalar_one_or_none()

        if execution:
            execution.status = status

            if status == "running" and not execution.started_at:
                execution.started_at = datetime.now(UTC)
            elif status in ["success", "failed", "timeout"]:
                execution.completed_at = datetime.now(UTC)
                if execution.started_at and execution.completed_at:
                    duration = (execution.completed_at -
                                execution.started_at).total_seconds()
                    execution.duration_ms = int(duration * 1000)

            if error_message:
                execution.error_message = error_message

            await db.flush()
            await db.refresh(execution)
            return TriggerExecutionRead.model_validate(execution)

        return None

    async def retry_execution(
        self,
        db: AsyncSession,
        execution_id: Any
    ) -> Optional[TriggerExecutionRead]:
        """
        Mark execution for retry.

        Args:
            db: Database session
            execution_id: Execution ID

        Returns:
            Updated execution
        """
        query = select(TriggerExecution).where(
            TriggerExecution.id == execution_id)
        result = await db.execute(query)
        execution = result.scalar_one_or_none()

        if execution:
            execution.status = "pending"
            execution.retry_count += 1
            execution.error_message = None
            execution.started_at = None
            execution.completed_at = None
            execution.duration_ms = None

            await db.flush()
            await db.refresh(execution)
            return TriggerExecutionRead.model_validate(execution)

        return None

    async def get_execution_stats(
        self,
        db: AsyncSession,
        tenant_id: Any,
        trigger_id: Optional[Any] = None,
        period_hours: int = 24
    ) -> TriggerExecutionStats:
        """
        Get trigger execution statistics.

        Args:
            db: Database session
            tenant_id: Tenant ID
            trigger_id: Optional trigger filter
            period_hours: Period in hours

        Returns:
            Execution statistics
        """
        period_start = datetime.now(UTC) - timedelta(hours=period_hours)
        period_end = datetime.now(UTC)

        # Build base query
        query = select(TriggerExecution).where(
            TriggerExecution.tenant_id == tenant_id,
            TriggerExecution.created_at >= period_start
        )

        if trigger_id:
            query = query.where(TriggerExecution.trigger_id == trigger_id)

        result = await db.execute(query)
        executions = result.scalars().all()

        # Calculate stats
        total = len(executions)
        successful = sum(1 for e in executions if e.status == "success")
        failed = sum(1 for e in executions if e.status == "failed")
        timeout = sum(1 for e in executions if e.status == "timeout")

        # Calculate average duration
        durations = [e.duration_ms for e in executions if e.duration_ms]
        avg_duration = int(sum(durations) / len(durations)) if durations else 0

        # Calculate rates
        success_rate = Decimal(successful / total *
                               100) if total > 0 else Decimal(0)
        retry_rate = Decimal(
            sum(1 for e in executions if e.retry_count > 0) / total * 100
        ) if total > 0 else Decimal(0)

        return TriggerExecutionStats(
            tenant_id=tenant_id,
            trigger_id=trigger_id,
            period_start=period_start,
            period_end=period_end,
            total_executions=total,
            successful_executions=successful,
            failed_executions=failed,
            timeout_executions=timeout,
            average_duration_ms=avg_duration,
            success_rate=success_rate,
            retry_rate=retry_rate
        )

    async def bulk_retry(
        self,
        db: AsyncSession,
        execution_ids: list[Any],
        max_retries: int = 3
    ) -> int:
        """
        Bulk retry failed executions.

        Args:
            db: Database session
            execution_ids: List of execution IDs
            max_retries: Maximum retry attempts

        Returns:
            Number of executions marked for retry
        """
        query = select(TriggerExecution).where(
            TriggerExecution.id.in_(execution_ids),
            TriggerExecution.status.in_(["failed", "timeout"]),
            TriggerExecution.retry_count < max_retries
        )
        result = await db.execute(query)
        executions = result.scalars().all()

        for execution in executions:
            execution.status = "pending"
            execution.retry_count += 1
            execution.error_message = None
            execution.started_at = None
            execution.completed_at = None
            execution.duration_ms = None

        await db.flush()
        return len(executions)


# Export crud instances
crud_block_state = CRUDBlockState(BlockState)
crud_missed_block = CRUDMissedBlock(MissedBlock)
crud_monitor_match = CRUDMonitorMatch(MonitorMatch)
crud_trigger_execution = CRUDTriggerExecution(TriggerExecution)
