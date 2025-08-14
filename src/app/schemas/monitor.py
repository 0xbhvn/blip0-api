"""Pydantic schemas for Monitor model."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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

    tenant_id: UUID


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

    id: UUID
    tenant_id: UUID
    active: bool
    validated: bool
    validation_errors: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    last_validated_at: Optional[datetime]

    class Config:
        from_attributes = True


class MonitorCached(MonitorRead):
    """Schema for cached Monitor with denormalized data."""

    triggers_data: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Denormalized trigger objects"
    )
