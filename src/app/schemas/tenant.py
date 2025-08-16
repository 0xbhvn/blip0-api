"""
Tenant schemas for multi-tenant isolation.
"""

import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.schemas import TimestampSchema


# Base schemas
class TenantBase(BaseModel):
    """Base schema for tenant with common fields."""
    name: str = Field(..., min_length=1, max_length=255,
                      description="Tenant organization name")
    slug: str = Field(..., min_length=1, max_length=255,
                      description="URL-safe tenant identifier")
    plan: str = Field(
        default="free", description="Subscription plan: free, starter, pro, enterprise")
    settings: dict[str, Any] = Field(
        default_factory=dict, description="Tenant-specific settings")

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v: str) -> str:
        allowed_plans = {"free", "starter", "pro", "enterprise"}
        if v not in allowed_plans:
            raise ValueError(
                f"Plan must be one of: {', '.join(allowed_plans)}")
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError(
                "Slug must be lowercase alphanumeric with hyphens only")
        return v


class TenantLimitsBase(BaseModel):
    """Base schema for tenant resource limits."""
    max_monitors: int = Field(
        default=10, ge=0, description="Maximum number of monitors")
    max_networks: int = Field(
        default=3, ge=0, description="Maximum number of networks")
    max_triggers: int = Field(
        default=20, ge=0, description="Maximum number of triggers")
    max_api_calls_per_hour: int = Field(
        default=1000, ge=0, description="API rate limit per hour")
    max_storage_gb: float = Field(
        default=1.0, ge=0.0, description="Maximum storage in GB")
    max_concurrent_operations: int = Field(
        default=10, ge=0, description="Maximum concurrent operations")


# Create schemas
class TenantCreate(TenantBase):
    """Schema for creating a new tenant."""
    pass


class TenantLimitsCreate(TenantLimitsBase):
    """Schema for creating tenant limits."""
    tenant_id: uuid_pkg.UUID


class TenantCreateInternal(TenantBase):
    """Internal schema for tenant creation with defaults."""
    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4)
    status: str = Field(default="active")


# Update schemas
class TenantUpdate(BaseModel):
    """Schema for updating a tenant."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    plan: Optional[str] = None
    status: Optional[str] = None
    settings: Optional[dict[str, Any]] = None

    @field_validator("plan")
    @classmethod
    def validate_plan(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed_plans = {"free", "starter", "pro", "enterprise"}
            if v not in allowed_plans:
                raise ValueError(
                    f"Plan must be one of: {', '.join(allowed_plans)}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed_statuses = {"active", "suspended", "deleted"}
            if v not in allowed_statuses:
                raise ValueError(
                    f"Status must be one of: {', '.join(allowed_statuses)}")
        return v


class TenantUpdateInternal(TenantUpdate):
    """Internal schema for tenant updates."""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TenantLimitsUpdate(BaseModel):
    """Schema for updating tenant limits."""
    max_monitors: Optional[int] = Field(None, ge=0)
    max_networks: Optional[int] = Field(None, ge=0)
    max_triggers: Optional[int] = Field(None, ge=0)
    max_api_calls_per_hour: Optional[int] = Field(None, ge=0)
    max_storage_gb: Optional[float] = Field(None, ge=0.0)
    max_concurrent_operations: Optional[int] = Field(None, ge=0)
    current_monitors: Optional[int] = Field(None, ge=0)
    current_networks: Optional[int] = Field(None, ge=0)
    current_triggers: Optional[int] = Field(None, ge=0)
    current_storage_gb: Optional[float] = Field(None, ge=0.0)


# Read schemas
class TenantRead(TenantBase, TimestampSchema):
    """Schema for reading tenant data."""
    id: uuid_pkg.UUID
    status: str
    is_active: bool = Field(default=True, description="Whether tenant is active")
    model_config = ConfigDict(from_attributes=True)


class TenantLimitsRead(TenantLimitsBase):
    """Schema for reading tenant limits with usage."""
    tenant_id: uuid_pkg.UUID
    current_monitors: int
    current_networks: int
    current_triggers: int
    current_storage_gb: float
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TenantWithLimits(TenantRead):
    """Schema for tenant with associated limits."""
    limits: Optional[TenantLimitsRead] = None


# Delete schema
class TenantDelete(BaseModel):
    """Schema for soft-deleting a tenant."""
    is_hard_delete: bool = Field(
        default=False, description="If true, permanently delete the tenant")


# Filter and pagination schemas
class TenantFilter(BaseModel):
    """Schema for filtering tenants."""
    name: Optional[str] = Field(
        None, description="Filter by name (partial match)")
    slug: Optional[str] = Field(
        None, description="Filter by slug (exact match)")
    plan: Optional[str] = Field(None, description="Filter by plan")
    status: Optional[str] = Field(None, description="Filter by status")
    created_after: Optional[datetime] = Field(
        None, description="Filter by creation date")
    created_before: Optional[datetime] = Field(
        None, description="Filter by creation date")


class TenantSort(BaseModel):
    """Schema for sorting tenants."""
    field: str = Field(default="created_at", description="Field to sort by")
    order: str = Field(default="desc", pattern="^(asc|desc)$",
                       description="Sort order")

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed_fields = {"name", "slug", "plan",
                          "status", "created_at", "updated_at"}
        if v not in allowed_fields:
            raise ValueError(
                f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v


class TenantPagination(BaseModel):
    """Schema for paginated tenant response."""
    items: list[TenantRead]
    total: int
    page: int
    size: int
    pages: int


# Bulk operations
class TenantBulkUpdate(BaseModel):
    """Schema for bulk updating tenants."""
    ids: list[uuid_pkg.UUID]
    update: TenantUpdate


class TenantBulkDelete(BaseModel):
    """Schema for bulk deleting tenants."""
    ids: list[uuid_pkg.UUID]
    is_hard_delete: bool = Field(default=False)
