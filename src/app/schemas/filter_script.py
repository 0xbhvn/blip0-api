"""
Filter script schemas for managing custom filter scripts.
"""

import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..core.schemas import TimestampSchema


# Base schemas
class FilterScriptBase(BaseModel):
    """Base schema for filter script with common fields."""
    name: str = Field(..., min_length=1, max_length=255,
                      description="Display name for the filter script")
    slug: str = Field(..., min_length=1, max_length=255,
                      description="URL-safe unique identifier")
    language: str = Field(..., description="Script language: bash, python, or javascript")
    description: Optional[str] = Field(None, description="Description of what the filter does")
    arguments: Optional[list[str]] = Field(
        None, description="Default arguments to pass to the script")
    timeout_ms: int = Field(
        default=1000, ge=1, le=30000,
        description="Script execution timeout in milliseconds")

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        allowed_languages = {"bash", "python", "javascript"}
        if v.lower() not in allowed_languages:
            raise ValueError(
                f"Language must be one of: {', '.join(allowed_languages)}")
        return v.lower()

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        import re
        if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
            raise ValueError(
                "Slug must be lowercase alphanumeric with hyphens only")
        return v


# Create schemas
class FilterScriptCreate(FilterScriptBase):
    """Schema for creating a new filter script."""
    script_content: str = Field(..., min_length=1,
                                description="The actual script content to save")


class FilterScriptCreateInternal(FilterScriptBase):
    """Internal schema for filter script creation."""
    script_path: str  # Required field first
    id: uuid_pkg.UUID = Field(default_factory=uuid_pkg.uuid4)
    active: bool = Field(default=True)
    validated: bool = Field(default=False)
    file_size_bytes: Optional[int] = None
    file_hash: Optional[str] = None


# Update schemas
class FilterScriptUpdate(BaseModel):
    """Schema for updating a filter script."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=255)
    language: Optional[str] = None
    description: Optional[str] = None
    arguments: Optional[list[str]] = None
    timeout_ms: Optional[int] = Field(None, ge=1, le=30000)
    script_content: Optional[str] = Field(None, min_length=1,
                                          description="New script content")
    active: Optional[bool] = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed_languages = {"bash", "python", "javascript"}
            if v.lower() not in allowed_languages:
                raise ValueError(
                    f"Language must be one of: {', '.join(allowed_languages)}")
            return v.lower()
        return v

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            import re
            if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", v):
                raise ValueError(
                    "Slug must be lowercase alphanumeric with hyphens only")
        return v


class FilterScriptUpdateInternal(FilterScriptUpdate):
    """Internal schema for filter script updates."""
    script_path: Optional[str] = None
    validated: Optional[bool] = None
    validation_errors: Optional[dict] = None
    last_validated_at: Optional[datetime] = None
    file_size_bytes: Optional[int] = None
    file_hash: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Delete schemas
class FilterScriptDelete(BaseModel):
    """Schema for deleting a filter script."""
    model_config = ConfigDict(extra="forbid")
    is_hard_delete: bool = Field(default=False)
    delete_file: bool = Field(
        default=False, description="Also delete the script file from filesystem")


# Read schemas
class FilterScriptRead(FilterScriptBase, TimestampSchema):
    """Schema for reading filter script data."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid_pkg.UUID
    script_path: str
    active: bool
    validated: bool
    validation_errors: Optional[dict] = None
    last_validated_at: Optional[datetime] = None
    file_size_bytes: Optional[int] = None
    file_hash: Optional[str] = None


class FilterScriptWithContent(FilterScriptRead):
    """Schema for filter script with actual script content."""
    script_content: Optional[str] = Field(
        None, description="The actual script content from filesystem")


# Filter and sort schemas
class FilterScriptFilter(BaseModel):
    """Schema for filtering filter scripts."""
    name: Optional[str] = Field(None, description="Filter by name (partial match)")
    slug: Optional[str] = Field(None, description="Filter by slug (exact match)")
    language: Optional[str] = Field(None, description="Filter by language")
    active: Optional[bool] = Field(None, description="Filter by active status")
    validated: Optional[bool] = Field(None, description="Filter by validation status")
    created_after: Optional[datetime] = Field(None, description="Created after this date")
    created_before: Optional[datetime] = Field(None, description="Created before this date")

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed_languages = {"bash", "python", "javascript"}
            if v.lower() not in allowed_languages:
                raise ValueError(
                    f"Language must be one of: {', '.join(allowed_languages)}")
            return v.lower()
        return v


class FilterScriptSort(BaseModel):
    """Schema for sorting filter scripts."""
    field: str = Field(
        default="created_at",
        description="Field to sort by (name, slug, language, created_at, updated_at)")
    order: str = Field(
        default="desc",
        pattern="^(asc|desc)$",
        description="Sort order (asc or desc)")

    @field_validator("field")
    @classmethod
    def validate_field(cls, v: str) -> str:
        allowed_fields = {"name", "slug", "language", "created_at", "updated_at"}
        if v not in allowed_fields:
            raise ValueError(
                f"Sort field must be one of: {', '.join(allowed_fields)}")
        return v


# Validation schemas
class FilterScriptValidationRequest(BaseModel):
    """Request schema for filter script validation."""
    test_input: Optional[dict[str, Any]] = Field(
        default=None, description="Sample input JSON to test the script with")


class FilterScriptValidationResult(BaseModel):
    """Result schema for filter script validation."""
    valid: bool = Field(..., description="Whether the script is valid")
    errors: Optional[list[str]] = Field(default=None, description="List of validation errors")
    warnings: Optional[list[str]] = Field(default=None, description="List of warnings")
    test_output: Optional[str] = Field(
        default=None, description="Output from test execution if test_input was provided")
    execution_time_ms: Optional[int] = Field(
        default=None, description="Execution time in milliseconds if test was run")


# Pagination schemas
class FilterScriptPagination(BaseModel):
    """Paginated response for filter scripts."""
    items: list[FilterScriptRead]
    total: int
    page: int
    size: int
    pages: int


class FilterScriptAdminPagination(BaseModel):
    """Paginated response for admin filter script listing with additional details."""
    items: list[FilterScriptWithContent]
    total: int
    page: int
    size: int
    pages: int
