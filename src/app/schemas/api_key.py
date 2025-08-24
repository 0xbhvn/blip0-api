"""Schemas for API Key management."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class APIKeyBase(BaseModel):
    """Base schema for API keys."""

    name: str = Field(..., min_length=1, max_length=255, description="Descriptive name for the API key")
    scopes: Optional[str] = Field(None, description="Space-separated list of scopes/permissions")
    expires_at: Optional[datetime] = Field(None, description="Optional expiration timestamp")


class APIKeyCreate(APIKeyBase):
    """Schema for creating a new API key."""

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: Optional[str]) -> Optional[str]:
        """Validate and normalize scopes."""
        if not v:
            return None

        # Normalize scopes (remove duplicates, sort)
        scopes = set(v.split())
        return " ".join(sorted(scopes))


class APIKeyUpdate(BaseModel):
    """Schema for updating an API key."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    scopes: Optional[str] = Field(None)
    is_active: Optional[bool] = Field(None)
    expires_at: Optional[datetime] = Field(None)

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: Optional[str]) -> Optional[str]:
        """Validate and normalize scopes."""
        if not v:
            return None

        scopes = set(v.split())
        return " ".join(sorted(scopes))


class APIKeyRead(APIKeyBase):
    """Schema for reading API key information (without sensitive data)."""

    id: uuid.UUID
    prefix: str
    last_four: str
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    is_active: bool
    last_used_at: Optional[datetime]
    usage_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class APIKeyResponse(BaseModel):
    """Schema for API key creation response (includes the actual key once)."""

    key: str = Field(..., description="The actual API key (only shown once)")
    key_info: APIKeyRead = Field(..., description="API key information")

    model_config = {"from_attributes": True}


class APIKeyValidation(BaseModel):
    """Schema for API key validation response."""

    valid: bool
    user_id: Optional[uuid.UUID] = None
    tenant_id: Optional[uuid.UUID] = None
    scopes: Optional[list[str]] = None
    expires_at: Optional[datetime] = None
