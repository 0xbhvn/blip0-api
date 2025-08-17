"""
Network schemas for blockchain network configurations.
"""

import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.schemas import TimestampSchema


# Base schemas
class NetworkBase(BaseModel):
    """Base schema for network with common fields."""
    name: str = Field(..., min_length=1, max_length=255,
                      description="Network display name")
    slug: str = Field(..., min_length=1, max_length=255,
                      description="URL-safe network identifier")
    network_type: str = Field(..., description="Network type: EVM or Stellar")
    block_time_ms: int = Field(..., gt=0,
                               description="Average block time in milliseconds")
    description: Optional[str] = Field(None, description="Network description")
    chain_id: Optional[int] = Field(
        None, description="Chain ID for EVM networks")
    network_passphrase: Optional[str] = Field(
        None, max_length=255, description="Network passphrase for Stellar networks")
    rpc_urls: list[dict[str, Any]] = Field(
        default_factory=list, description="Array of RPC endpoints with url, type_, and weight")
    confirmation_blocks: int = Field(
        default=1, ge=1, description="Number of blocks to wait for confirmation")
    cron_schedule: str = Field(
        default="*/10 * * * * *", description="Cron schedule for polling")
    max_past_blocks: int = Field(
        default=100, ge=1, description="Maximum number of past blocks to fetch")
    store_blocks: bool = Field(
        default=False, description="Whether to store all block data")

    @field_validator("network_type")
    @classmethod
    def validate_network_type(cls, v: str) -> str:
        allowed_types = {"EVM", "Stellar"}
        if v not in allowed_types:
            raise ValueError(
                f"Network type must be one of: {', '.join(allowed_types)}")
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError(
                "Slug must be lowercase alphanumeric with hyphens only")
        return v

    @field_validator("rpc_urls")
    @classmethod
    def validate_rpc_urls(cls, v: list) -> list:
        for rpc in v:
            if not isinstance(rpc, dict):
                raise ValueError("Each RPC URL must be a dictionary")
            if "url" not in rpc:
                raise ValueError("Each RPC URL must have a 'url' field")
            if not rpc["url"].startswith(("http://", "https://", "ws://", "wss://")):
                raise ValueError(
                    "RPC URL must start with http://, https://, ws://, or wss://")
        return v


# Create schemas
class NetworkCreateAdmin(NetworkBase):
    """Schema for creating a new network via admin API (no tenant_id required)."""
    pass


class NetworkCreate(NetworkBase):
    """Schema for creating a new network."""
    tenant_id: uuid_pkg.UUID


class NetworkCreateInternal(NetworkCreate):
    """Internal schema for network creation."""
    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4)
    active: bool = Field(default=True)
    validated: bool = Field(default=False)


# Update schemas
class NetworkUpdate(BaseModel):
    """Schema for updating a network."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    network_type: Optional[str] = None
    block_time_ms: Optional[int] = Field(None, gt=0)
    description: Optional[str] = None
    chain_id: Optional[int] = None
    network_passphrase: Optional[str] = Field(None, max_length=255)
    rpc_urls: Optional[list[dict[str, Any]]] = None
    confirmation_blocks: Optional[int] = Field(None, ge=1)
    cron_schedule: Optional[str] = None
    max_past_blocks: Optional[int] = Field(None, ge=1)
    store_blocks: Optional[bool] = None
    active: Optional[bool] = None

    @field_validator("network_type")
    @classmethod
    def validate_network_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed_types = {"EVM", "Stellar"}
            if v not in allowed_types:
                raise ValueError(
                    f"Network type must be one of: {', '.join(allowed_types)}")
        return v


class NetworkUpdateInternal(NetworkUpdate):
    """Internal schema for network updates."""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Read schemas
class NetworkRead(NetworkBase, TimestampSchema):
    """Schema for reading network data."""
    id: uuid_pkg.UUID
    tenant_id: uuid_pkg.UUID
    active: bool
    validated: bool
    validation_errors: Optional[dict[str, Any]]
    last_validated_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)


# Delete schema
class NetworkDelete(BaseModel):
    """Schema for deleting a network."""
    is_hard_delete: bool = Field(
        default=False, description="If true, permanently delete the network")


# Filter and pagination schemas
class NetworkFilter(BaseModel):
    """Schema for filtering networks."""
    tenant_id: Optional[uuid_pkg.UUID] = Field(
        None, description="Filter by tenant ID")
    name: Optional[str] = Field(
        None, description="Filter by name (partial match)")
    slug: Optional[str] = Field(
        None, description="Filter by slug (exact match)")
    network_type: Optional[str] = Field(
        None, description="Filter by network type")
    active: Optional[bool] = Field(None, description="Filter by active status")
    validated: Optional[bool] = Field(
        None, description="Filter by validation status")
    chain_id: Optional[int] = Field(
        None, description="Filter by chain ID (EVM networks)")
    has_rpc_urls: Optional[bool] = Field(
        None, description="Filter networks with/without RPC URLs")
    created_after: Optional[datetime] = Field(
        None, description="Filter by creation date")
    created_before: Optional[datetime] = Field(
        None, description="Filter by creation date")


class NetworkSort(BaseModel):
    """Schema for sorting networks."""
    field: str = Field(default="created_at", description="Field to sort by")
    order: str = Field(default="desc", pattern="^(asc|desc)$",
                       description="Sort order")

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed_fields = {"name", "slug", "network_type",
                          "active", "validated", "created_at", "updated_at"}
        if v not in allowed_fields:
            raise ValueError(
                f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v


class NetworkPagination(BaseModel):
    """Schema for paginated network response."""
    items: list[NetworkRead]
    total: int
    page: int
    size: int
    pages: int


# Bulk operations
class NetworkBulkUpdate(BaseModel):
    """Schema for bulk updating networks."""
    ids: list[uuid_pkg.UUID]
    update: NetworkUpdate


class NetworkBulkDelete(BaseModel):
    """Schema for bulk deleting networks."""
    ids: list[uuid_pkg.UUID]
    is_hard_delete: bool = Field(default=False)


# Validation schemas
class NetworkValidationRequest(BaseModel):
    """Schema for requesting network validation."""
    network_id: uuid_pkg.UUID
    test_connection: bool = Field(
        default=True, description="Test RPC connection")
    check_block_height: bool = Field(
        default=True, description="Check current block height")


class NetworkValidationResult(BaseModel):
    """Schema for network validation result."""
    network_id: uuid_pkg.UUID
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rpc_status: dict[str, Any] = Field(
        default_factory=dict, description="Status of each RPC URL")
    current_block_height: Optional[int] = None
    validated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# RPC management schemas
class NetworkRPCAdd(BaseModel):
    """Schema for adding RPC URLs to a network."""
    network_id: uuid_pkg.UUID
    rpc_urls: list[dict[str, Any]]


class NetworkRPCRemove(BaseModel):
    """Schema for removing RPC URLs from a network."""
    network_id: uuid_pkg.UUID
    rpc_urls: list[str]  # List of URLs to remove


class NetworkRPCTest(BaseModel):
    """Schema for testing RPC URLs."""
    url: str
    network_type: str
    chain_id: Optional[int] = None


class NetworkRPCTestResult(BaseModel):
    """Schema for RPC test result."""
    url: str
    is_online: bool
    latency_ms: Optional[int] = None
    block_height: Optional[int] = None
    error: Optional[str] = None
