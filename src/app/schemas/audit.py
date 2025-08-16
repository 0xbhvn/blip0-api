"""
Audit schemas for tracking blockchain processing and trigger execution.
"""

import uuid as uuid_pkg
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.schemas import TimestampSchema


# BlockState schemas
class BlockStateBase(BaseModel):
    """Base schema for block processing state."""
    tenant_id: uuid_pkg.UUID
    network_id: uuid_pkg.UUID
    processing_status: str = Field(
        default="idle", description="Processing status: idle, processing, error, paused")
    last_processed_block: Optional[int] = Field(
        None, ge=0, description="Last successfully processed block number")
    last_processed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    error_count: int = Field(
        default=0, ge=0, description="Number of consecutive errors")
    blocks_per_minute: Optional[Decimal] = Field(
        None, ge=0, description="Processing speed metric")
    average_processing_time_ms: Optional[int] = Field(
        None, ge=0, description="Average time to process a block")

    @field_validator("processing_status")
    @classmethod
    def validate_processing_status(cls, v: str) -> str:
        allowed_statuses = {"idle", "processing", "error", "paused"}
        if v not in allowed_statuses:
            raise ValueError(
                f"Processing status must be one of: {', '.join(allowed_statuses)}")
        return v


class BlockStateCreate(BlockStateBase):
    """Schema for creating block state."""
    pass


class BlockStateUpdate(BaseModel):
    """Schema for updating block state."""
    processing_status: Optional[str] = None
    last_processed_block: Optional[int] = Field(None, ge=0)
    last_processed_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_error_at: Optional[datetime] = None
    error_count: Optional[int] = Field(None, ge=0)
    blocks_per_minute: Optional[Decimal] = Field(None, ge=0)
    average_processing_time_ms: Optional[int] = Field(None, ge=0)


class BlockStateRead(BlockStateBase, TimestampSchema):
    """Schema for reading block state."""
    id: uuid_pkg.UUID
    model_config = ConfigDict(from_attributes=True)


# MissedBlock schemas
class MissedBlockBase(BaseModel):
    """Base schema for missed blocks."""
    tenant_id: uuid_pkg.UUID
    network_id: uuid_pkg.UUID
    block_number: int = Field(..., ge=0,
                              description="The block number that was missed")
    reason: Optional[str] = Field(
        None, description="Reason why the block was missed")
    retry_count: int = Field(
        default=0, ge=0, description="Number of retry attempts")
    processed: bool = Field(
        default=False, description="Whether the block has been successfully processed")
    processed_at: Optional[datetime] = None


class MissedBlockCreate(MissedBlockBase):
    """Schema for creating missed block record."""
    pass


class MissedBlockUpdate(BaseModel):
    """Schema for updating missed block."""
    reason: Optional[str] = None
    retry_count: Optional[int] = Field(None, ge=0)
    processed: Optional[bool] = None
    processed_at: Optional[datetime] = None


class MissedBlockRead(MissedBlockBase):
    """Schema for reading missed block."""
    id: uuid_pkg.UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# MonitorMatch schemas
class MonitorMatchBase(BaseModel):
    """Base schema for monitor matches."""
    tenant_id: uuid_pkg.UUID
    monitor_id: uuid_pkg.UUID
    network_id: uuid_pkg.UUID
    block_number: int = Field(..., ge=0,
                              description="Block number where match occurred")
    transaction_hash: Optional[str] = Field(
        None, max_length=255, description="Transaction hash if applicable")
    match_data: dict[str, Any] = Field(...,
                                       description="Details of what matched")
    triggers_executed: int = Field(
        default=0, ge=0, description="Number of triggers successfully executed")
    triggers_failed: int = Field(
        default=0, ge=0, description="Number of triggers that failed")


class MonitorMatchCreate(MonitorMatchBase):
    """Schema for creating monitor match."""
    pass


class MonitorMatchUpdate(BaseModel):
    """Schema for updating monitor match."""
    triggers_executed: Optional[int] = Field(None, ge=0)
    triggers_failed: Optional[int] = Field(None, ge=0)


class MonitorMatchRead(MonitorMatchBase):
    """Schema for reading monitor match."""
    id: uuid_pkg.UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# TriggerExecution schemas
class TriggerExecutionBase(BaseModel):
    """Base schema for trigger executions."""
    tenant_id: uuid_pkg.UUID
    trigger_id: uuid_pkg.UUID
    monitor_match_id: Optional[uuid_pkg.UUID] = None
    execution_type: str = Field(...,
                                description="Type of execution: email, webhook")
    execution_data: dict[str, Any] = Field(...,
                                           description="Data sent or used in the execution")
    status: str = Field(
        ..., description="Execution status: pending, running, success, failed, timeout")
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = Field(
        None, ge=0, description="Execution duration in milliseconds")
    retry_count: int = Field(
        default=0, ge=0, description="Number of retry attempts")
    error_message: Optional[str] = None

    @field_validator("execution_type")
    @classmethod
    def validate_execution_type(cls, v: str) -> str:
        allowed_types = {"email", "webhook"}
        if v not in allowed_types:
            raise ValueError(
                f"Execution type must be one of: {', '.join(allowed_types)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed_statuses = {"pending", "running",
                            "success", "failed", "timeout"}
        if v not in allowed_statuses:
            raise ValueError(
                f"Status must be one of: {', '.join(allowed_statuses)}")
        return v


class TriggerExecutionCreate(TriggerExecutionBase):
    """Schema for creating trigger execution."""
    pass


class TriggerExecutionUpdate(BaseModel):
    """Schema for updating trigger execution."""
    status: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = Field(None, ge=0)
    retry_count: Optional[int] = Field(None, ge=0)
    error_message: Optional[str] = None


class TriggerExecutionRead(TriggerExecutionBase):
    """Schema for reading trigger execution."""
    id: uuid_pkg.UUID
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# Filter schemas
class BlockStateFilter(BaseModel):
    """Schema for filtering block states."""
    tenant_id: Optional[uuid_pkg.UUID] = None
    network_id: Optional[uuid_pkg.UUID] = None
    processing_status: Optional[str] = None
    has_error: Optional[bool] = Field(
        None, description="Filter states with/without errors")
    processed_after: Optional[datetime] = None
    processed_before: Optional[datetime] = None


class MissedBlockFilter(BaseModel):
    """Schema for filtering missed blocks."""
    tenant_id: Optional[uuid_pkg.UUID] = None
    network_id: Optional[uuid_pkg.UUID] = None
    processed: Optional[bool] = None
    block_number_gte: Optional[int] = Field(
        None, ge=0, description="Block number greater than or equal")
    block_number_lte: Optional[int] = Field(
        None, ge=0, description="Block number less than or equal")
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class MonitorMatchFilter(BaseModel):
    """Schema for filtering monitor matches."""
    tenant_id: Optional[uuid_pkg.UUID] = None
    monitor_id: Optional[uuid_pkg.UUID] = None
    network_id: Optional[uuid_pkg.UUID] = None
    block_number: Optional[int] = Field(None, ge=0)
    transaction_hash: Optional[str] = None
    has_failed_triggers: Optional[bool] = Field(
        None, description="Filter matches with failed triggers")
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None


class TriggerExecutionFilter(BaseModel):
    """Schema for filtering trigger executions."""
    tenant_id: Optional[uuid_pkg.UUID] = None
    trigger_id: Optional[uuid_pkg.UUID] = None
    monitor_match_id: Optional[uuid_pkg.UUID] = None
    execution_type: Optional[str] = None
    status: Optional[str] = None
    started_after: Optional[datetime] = None
    started_before: Optional[datetime] = None
    completed_after: Optional[datetime] = None
    completed_before: Optional[datetime] = None


# Sort schemas
class AuditSort(BaseModel):
    """Base schema for sorting audit entities."""
    field: str = Field(default="created_at", description="Field to sort by")
    order: str = Field(default="desc", pattern="^(asc|desc)$",
                       description="Sort order")


class BlockStateSort(AuditSort):
    """Schema for sorting block states."""
    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed_fields = {"processing_status", "last_processed_block",
                          "last_processed_at", "error_count", "created_at", "updated_at"}
        if v not in allowed_fields:
            raise ValueError(
                f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v


class MissedBlockSort(AuditSort):
    """Schema for sorting missed blocks."""
    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed_fields = {"block_number",
                          "retry_count", "processed", "created_at"}
        if v not in allowed_fields:
            raise ValueError(
                f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v


class MonitorMatchSort(AuditSort):
    """Schema for sorting monitor matches."""
    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed_fields = {"block_number", "triggers_executed",
                          "triggers_failed", "created_at"}
        if v not in allowed_fields:
            raise ValueError(
                f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v


class TriggerExecutionSort(AuditSort):
    """Schema for sorting trigger executions."""
    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed_fields = {"status", "duration_ms", "retry_count",
                          "started_at", "completed_at", "created_at"}
        if v not in allowed_fields:
            raise ValueError(
                f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v


# Pagination schemas
class BlockStatePagination(BaseModel):
    """Schema for paginated block state response."""
    items: list[BlockStateRead]
    total: int
    page: int
    size: int
    pages: int


class MissedBlockPagination(BaseModel):
    """Schema for paginated missed block response."""
    items: list[MissedBlockRead]
    total: int
    page: int
    size: int
    pages: int


class MonitorMatchPagination(BaseModel):
    """Schema for paginated monitor match response."""
    items: list[MonitorMatchRead]
    total: int
    page: int
    size: int
    pages: int


class TriggerExecutionPagination(BaseModel):
    """Schema for paginated trigger execution response."""
    items: list[TriggerExecutionRead]
    total: int
    page: int
    size: int
    pages: int


# Bulk operations
class MissedBlockBulkRetry(BaseModel):
    """Schema for bulk retrying missed blocks."""
    ids: list[uuid_pkg.UUID]
    max_retries: int = Field(default=3, ge=1, le=10,
                             description="Maximum retry attempts")


class TriggerExecutionBulkRetry(BaseModel):
    """Schema for bulk retrying trigger executions."""
    ids: list[uuid_pkg.UUID]
    max_retries: int = Field(default=3, ge=1, le=10,
                             description="Maximum retry attempts")


# Statistics schemas
class BlockProcessingStats(BaseModel):
    """Schema for block processing statistics."""
    tenant_id: uuid_pkg.UUID
    network_id: uuid_pkg.UUID
    period_start: datetime
    period_end: datetime
    total_blocks_processed: int
    total_missed_blocks: int
    average_blocks_per_minute: Decimal
    average_processing_time_ms: int
    error_rate: Decimal
    uptime_percentage: Decimal


class TriggerExecutionStats(BaseModel):
    """Schema for trigger execution statistics."""
    tenant_id: uuid_pkg.UUID
    trigger_id: Optional[uuid_pkg.UUID] = None
    period_start: datetime
    period_end: datetime
    total_executions: int
    successful_executions: int
    failed_executions: int
    timeout_executions: int
    average_duration_ms: int
    success_rate: Decimal
    retry_rate: Decimal
