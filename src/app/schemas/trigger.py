"""
Trigger schemas for action configurations.
"""

import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.schemas import TimestampSchema


# Base schemas
class TriggerBase(BaseModel):
    """Base schema for trigger with common fields."""
    name: str = Field(..., min_length=1, max_length=255,
                      description="Trigger display name")
    slug: str = Field(..., min_length=1, max_length=255,
                      description="URL-safe trigger identifier")
    trigger_type: str = Field(...,
                              description="Trigger type: email or webhook")
    description: Optional[str] = Field(None, description="Trigger description")

    @field_validator("trigger_type")
    @classmethod
    def validate_trigger_type(cls, v: str) -> str:
        allowed_types = {"email", "webhook"}
        if v not in allowed_types:
            raise ValueError(
                f"Trigger type must be one of: {', '.join(allowed_types)}")
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError(
                "Slug must be lowercase alphanumeric with hyphens only")
        return v


class EmailTriggerBase(BaseModel):
    """Base schema for email trigger configuration."""
    host: str = Field(..., min_length=1, max_length=255,
                      description="SMTP server hostname")
    port: int = Field(default=465, ge=1, le=65535,
                      description="SMTP server port")
    username_type: str = Field(
        ..., description="How username is stored: Plain, Environment, HashicorpCloudVault")
    username_value: str = Field(..., min_length=1,
                                description="Username value or reference based on type")
    password_type: str = Field(
        ..., description="How password is stored: Plain, Environment, HashicorpCloudVault")
    password_value: str = Field(..., min_length=1,
                                description="Password value or reference based on type")
    sender: str = Field(..., min_length=1, max_length=255,
                        description="From email address")
    recipients: list[str] = Field(
        default_factory=list, description="Array of recipient email addresses")
    message_title: str = Field(..., min_length=1,
                               description="Email subject template")
    message_body: str = Field(..., min_length=1,
                              description="Email body template")

    @field_validator("username_type", "password_type")
    @classmethod
    def validate_credential_type(cls, v: str) -> str:
        allowed_types = {"Plain", "Environment", "HashicorpCloudVault"}
        if v not in allowed_types:
            raise ValueError(
                f"Credential type must be one of: {', '.join(allowed_types)}")
        return v

    @field_validator("recipients")
    @classmethod
    def validate_recipients(cls, v: list[str]) -> list[str]:
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for email in v:
            if not re.match(email_pattern, email):
                raise ValueError(f"Invalid email address: {email}")
        return v


class WebhookTriggerBase(BaseModel):
    """Base schema for webhook trigger configuration."""
    url_type: str = Field(
        ..., description="How URL is stored: Plain, Environment, HashicorpCloudVault")
    url_value: str = Field(..., min_length=1,
                           description="URL value or reference based on type")
    method: str = Field(default="POST", description="HTTP method to use")
    headers: dict[str, str] = Field(
        default_factory=dict, description="Additional HTTP headers to send")
    secret_type: Optional[str] = Field(
        None, description="How secret is stored: Plain, Environment, HashicorpCloudVault")
    secret_value: Optional[str] = Field(
        None, description="Secret value or reference based on type")
    message_title: str = Field(..., min_length=1,
                               description="Webhook payload title template")
    message_body: str = Field(..., min_length=1,
                              description="Webhook payload body template")

    @field_validator("url_type")
    @classmethod
    def validate_url_type(cls, v: str) -> str:
        allowed_types = {"Plain", "Environment", "HashicorpCloudVault"}
        if v not in allowed_types:
            raise ValueError(
                f"URL type must be one of: {', '.join(allowed_types)}")
        return v

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        allowed_methods = {"POST", "GET", "PUT", "PATCH", "DELETE"}
        if v not in allowed_methods:
            raise ValueError(
                f"Method must be one of: {', '.join(allowed_methods)}")
        return v

    @field_validator("secret_type")
    @classmethod
    def validate_secret_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed_types = {"Plain", "Environment", "HashicorpCloudVault"}
            if v not in allowed_types:
                raise ValueError(
                    f"Secret type must be one of: {', '.join(allowed_types)}")
        return v


# Create schemas
class TriggerCreate(TriggerBase):
    """Schema for creating a new trigger."""
    tenant_id: uuid_pkg.UUID
    email_config: Optional[EmailTriggerBase] = None
    webhook_config: Optional[WebhookTriggerBase] = None

    @field_validator("email_config", "webhook_config")
    @classmethod
    def validate_config(cls, v: Any, info) -> Any:
        values = info.data
        if "trigger_type" in values:
            if values["trigger_type"] == "email" and "email_config" in info.field_name and v is None:
                raise ValueError(
                    "email_config is required for email trigger type")
            if values["trigger_type"] == "webhook" and "webhook_config" in info.field_name and v is None:
                raise ValueError(
                    "webhook_config is required for webhook trigger type")
        return v


class TriggerCreateInternal(TriggerCreate):
    """Internal schema for trigger creation."""
    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4)
    active: bool = Field(default=True)
    validated: bool = Field(default=False)


# Update schemas
class TriggerUpdate(BaseModel):
    """Schema for updating a trigger."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    active: Optional[bool] = None
    email_config: Optional[EmailTriggerBase] = None
    webhook_config: Optional[WebhookTriggerBase] = None


class TriggerUpdateInternal(TriggerUpdate):
    """Internal schema for trigger updates."""
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Read schemas
class EmailTriggerRead(EmailTriggerBase):
    """Schema for reading email trigger configuration."""
    trigger_id: uuid_pkg.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WebhookTriggerRead(WebhookTriggerBase):
    """Schema for reading webhook trigger configuration."""
    trigger_id: uuid_pkg.UUID
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TriggerRead(TriggerBase, TimestampSchema):
    """Schema for reading trigger data."""
    id: uuid_pkg.UUID
    tenant_id: uuid_pkg.UUID
    active: bool
    validated: bool
    validation_errors: Optional[dict[str, Any]]
    last_validated_at: Optional[datetime]
    email_config: Optional[EmailTriggerRead] = None
    webhook_config: Optional[WebhookTriggerRead] = None
    model_config = ConfigDict(from_attributes=True)


# Delete schema
class TriggerDelete(BaseModel):
    """Schema for deleting a trigger."""
    is_hard_delete: bool = Field(
        default=False, description="If true, permanently delete the trigger")


# Filter and pagination schemas
class TriggerFilter(BaseModel):
    """Schema for filtering triggers."""
    tenant_id: Optional[uuid_pkg.UUID] = Field(
        None, description="Filter by tenant ID")
    name: Optional[str] = Field(
        None, description="Filter by name (partial match)")
    slug: Optional[str] = Field(
        None, description="Filter by slug (exact match)")
    trigger_type: Optional[str] = Field(
        None, description="Filter by trigger type")
    active: Optional[bool] = Field(None, description="Filter by active status")
    validated: Optional[bool] = Field(
        None, description="Filter by validation status")
    created_after: Optional[datetime] = Field(
        None, description="Filter by creation date")
    created_before: Optional[datetime] = Field(
        None, description="Filter by creation date")


class TriggerSort(BaseModel):
    """Schema for sorting triggers."""
    field: str = Field(default="created_at", description="Field to sort by")
    order: str = Field(default="desc", pattern="^(asc|desc)$",
                       description="Sort order")

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed_fields = {"name", "slug", "trigger_type",
                          "active", "validated", "created_at", "updated_at"}
        if v not in allowed_fields:
            raise ValueError(
                f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v


class TriggerPagination(BaseModel):
    """Schema for paginated trigger response."""
    items: list[TriggerRead]
    total: int
    page: int
    size: int
    pages: int


# Bulk operations
class TriggerBulkUpdate(BaseModel):
    """Schema for bulk updating triggers."""
    ids: list[uuid_pkg.UUID]
    update: TriggerUpdate


class TriggerBulkDelete(BaseModel):
    """Schema for bulk deleting triggers."""
    ids: list[uuid_pkg.UUID]
    is_hard_delete: bool = Field(default=False)


# Test and validation schemas
class TriggerTestRequest(BaseModel):
    """Schema for testing a trigger."""
    trigger_id: uuid_pkg.UUID
    test_data: dict[str, Any] = Field(
        default_factory=dict, description="Sample data to send in test")


class TriggerTestResult(BaseModel):
    """Schema for trigger test result."""
    trigger_id: uuid_pkg.UUID
    success: bool
    response: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    tested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TriggerValidationRequest(BaseModel):
    """Schema for requesting trigger validation."""
    trigger_id: uuid_pkg.UUID
    test_connection: bool = Field(
        default=True, description="Test the trigger connection/credentials")


class TriggerValidationResult(BaseModel):
    """Schema for trigger validation result."""
    trigger_id: uuid_pkg.UUID
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    validated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
