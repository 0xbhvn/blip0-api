"""
Monitor schemas for blockchain monitoring configurations.
"""

import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MonitorBase(BaseModel):
    """Base schema for Monitor."""

    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    description: Optional[str] = None
    paused: bool = False
    networks: list[str] = Field(default_factory=list)
    addresses: list[dict[str, Any]] = Field(default_factory=list)
    match_functions: list[dict[str, Any]] = Field(default_factory=list)
    match_events: list[dict[str, Any]] = Field(default_factory=list)
    match_transactions: list[dict[str, Any]] = Field(default_factory=list)
    trigger_conditions: list[dict[str, Any]] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)


class MonitorCreate(MonitorBase):
    """Schema for creating a Monitor."""

    tenant_id: uuid_pkg.UUID


class MonitorUpdate(BaseModel):
    """Schema for updating a Monitor."""

    name: Optional[str] = Field(None, max_length=255)
    slug: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    paused: Optional[bool] = None
    active: Optional[bool] = None
    networks: Optional[list[str]] = None
    addresses: Optional[list[dict[str, Any]]] = None
    match_functions: Optional[list[dict[str, Any]]] = None
    match_events: Optional[list[dict[str, Any]]] = None
    match_transactions: Optional[list[dict[str, Any]]] = None
    trigger_conditions: Optional[list[dict[str, Any]]] = None
    triggers: Optional[list[str]] = None


class MonitorRead(MonitorBase):
    """Schema for reading a Monitor."""

    id: uuid_pkg.UUID
    tenant_id: uuid_pkg.UUID
    active: bool
    validated: bool
    validation_errors: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    last_validated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class MonitorCached(MonitorRead):
    """Schema for cached Monitor with denormalized data."""

    triggers_data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Denormalized trigger objects"
    )


# Internal schemas
class MonitorCreateInternal(MonitorCreate):
    """Internal schema for monitor creation."""
    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4)
    active: bool = Field(default=True)
    validated: bool = Field(default=False)


class MonitorUpdateInternal(MonitorUpdate):
    """Internal schema for monitor updates."""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Delete schema
class MonitorDelete(BaseModel):
    """Schema for deleting a monitor."""
    is_hard_delete: bool = Field(
        default=False, description="If true, permanently delete the monitor")


# Filter and pagination schemas
class MonitorFilter(BaseModel):
    """Schema for filtering monitors."""
    tenant_id: Optional[uuid_pkg.UUID] = Field(
        None, description="Filter by tenant ID")
    name: Optional[str] = Field(
        None, description="Filter by name (partial match)")
    slug: Optional[str] = Field(
        None, description="Filter by slug (exact match)")
    active: Optional[bool] = Field(None, description="Filter by active status")
    paused: Optional[bool] = Field(None, description="Filter by paused status")
    validated: Optional[bool] = Field(
        None, description="Filter by validation status")
    network_slug: Optional[str] = Field(
        None, description="Filter by network slug in networks array")
    has_triggers: Optional[bool] = Field(
        None, description="Filter monitors with/without triggers")
    created_after: Optional[datetime] = Field(
        None, description="Filter by creation date")
    created_before: Optional[datetime] = Field(
        None, description="Filter by creation date")
    updated_after: Optional[datetime] = Field(
        None, description="Filter by update date")
    updated_before: Optional[datetime] = Field(
        None, description="Filter by update date")


class MonitorSort(BaseModel):
    """Schema for sorting monitors."""
    field: str = Field(default="created_at", description="Field to sort by")
    order: str = Field(default="desc", pattern="^(asc|desc)$",
                       description="Sort order")

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed_fields = {"name", "slug", "active", "paused",
                          "validated", "created_at", "updated_at"}
        if v not in allowed_fields:
            raise ValueError(
                f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v


class MonitorPagination(BaseModel):
    """Schema for paginated monitor response."""
    items: list[MonitorRead]
    total: int
    page: int
    size: int
    pages: int


# Bulk operations
class MonitorBulkUpdate(BaseModel):
    """Schema for bulk updating monitors."""
    ids: list[uuid_pkg.UUID]
    update: MonitorUpdate


class MonitorBulkDelete(BaseModel):
    """Schema for bulk deleting monitors."""
    ids: list[uuid_pkg.UUID]
    is_hard_delete: bool = Field(default=False)


class MonitorBulkPause(BaseModel):
    """Schema for bulk pausing/resuming monitors."""
    ids: list[uuid_pkg.UUID]
    paused: bool


# Validation schemas
class MonitorValidationRequest(BaseModel):
    """Schema for requesting monitor validation."""
    monitor_id: uuid_pkg.UUID
    validate_triggers: bool = Field(
        default=True, description="Also validate associated triggers")
    validate_networks: bool = Field(
        default=True, description="Also validate network configurations")


class MonitorValidationResult(BaseModel):
    """Schema for monitor validation result."""
    monitor_id: uuid_pkg.UUID
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
