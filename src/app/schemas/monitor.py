"""Pydantic schemas for Monitor model."""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MonitorBase(BaseModel):
    """Base schema for Monitor."""

    name: str = Field(..., max_length=255)
    slug: str = Field(..., max_length=255)
    description: Optional[str] = None
    paused: bool = False
    networks: List[str] = Field(default_factory=list)
    addresses: List[Dict[str, Any]] = Field(default_factory=list)
    match_functions: List[Dict[str, Any]] = Field(default_factory=list)
    match_events: List[Dict[str, Any]] = Field(default_factory=list)
    match_transactions: List[Dict[str, Any]] = Field(default_factory=list)
    trigger_conditions: List[Dict[str, Any]] = Field(default_factory=list)
    triggers: List[str] = Field(default_factory=list)


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
    networks: Optional[List[str]] = None
    addresses: Optional[List[Dict[str, Any]]] = None
    match_functions: Optional[List[Dict[str, Any]]] = None
    match_events: Optional[List[Dict[str, Any]]] = None
    match_transactions: Optional[List[Dict[str, Any]]] = None
    trigger_conditions: Optional[List[Dict[str, Any]]] = None
    triggers: Optional[List[str]] = None


class MonitorRead(MonitorBase):
    """Schema for reading a Monitor."""

    id: UUID
    tenant_id: UUID
    active: bool
    validated: bool
    validation_errors: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    last_validated_at: Optional[datetime]

    class Config:
        from_attributes = True


class MonitorCached(MonitorRead):
    """Schema for cached Monitor with denormalized data."""

    triggers_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Denormalized trigger objects"
    )
