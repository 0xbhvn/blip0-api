import uuid as uuid_pkg
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base


class FilterScript(Base):
    """
    FilterScript model for managing custom filter scripts used by monitors.
    Scripts are stored in the filesystem while metadata is tracked in the database.
    Tenant-managed resource for custom filtering logic.
    """
    __tablename__ = "filter_scripts"

    # Primary key
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        primary_key=True,
        unique=True
    )

    # Tenant relationship
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        nullable=False,
        index=True,
        comment="Tenant that owns this filter script"
    )

    # Required fields (no defaults)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    language: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Script language: bash, python, or javascript"
    )
    script_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Relative path to script file in config/filters/"
    )

    # Optional fields
    description: Mapped[str | None] = mapped_column(String, nullable=True, default=None)
    arguments: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        comment="Default arguments to pass to the script"
    )
    timeout_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1000,
        server_default="1000",
        comment="Script execution timeout in milliseconds"
    )

    # Status fields
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True
    )
    validated: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false"
    )
    validation_errors: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        default=None,
        comment="Validation errors if script validation failed"
    )
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None
    )

    # File metadata
    file_size_bytes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="Size of the script file in bytes"
    )
    file_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        default=None,
        comment="SHA256 hash of the script file content"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default="NOW()",
        onupdate=lambda: datetime.now(UTC)
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "slug",
            name="unique_filter_script_tenant_slug",
            deferrable=True,
            initially="DEFERRED"
        ),
        CheckConstraint(
            "language IN ('bash', 'python', 'javascript')",
            name="check_filter_script_language"
        ),
        CheckConstraint(
            "timeout_ms > 0 AND timeout_ms <= 30000",
            name="check_filter_script_timeout"
        ),
        # Composite indexes for common query patterns
        Index("idx_filter_script_tenant_active", "tenant_id", "active"),
        Index("idx_filter_script_tenant_slug", "tenant_id", "slug"),
        Index("idx_filter_script_language_active", "language", "active"),
        {"comment": "Metadata for filter scripts stored in filesystem, used by monitors for custom filtering logic"},
    )
