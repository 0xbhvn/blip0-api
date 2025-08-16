import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DECIMAL, JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db.database import Base

if TYPE_CHECKING:
    from .user import User


class Tenant(Base):
    """
    Tenant model for multi-tenant isolation.
    Represents an organization or account that owns monitors, networks, and triggers.
    """
    __tablename__ = "tenants"

    # Required fields first (no defaults)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True)

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
    )

    # Plan and status with defaults
    plan: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="free",
        server_default="free"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        server_default="active"
    )

    # Settings as JSONB for tenant-specific configurations
    settings: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default_factory=dict,
        server_default="{}",
        comment="Tenant-specific settings and configurations"
    )

    # Timestamps for tracking
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

    # Relationships (excluded from init)
    limits: Mapped["TenantLimits | None"] = relationship(
        "TenantLimits",
        back_populates="tenant",
        cascade="all, delete-orphan",
        uselist=False,
        init=False
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="tenant",
        cascade="all, delete-orphan",
        init=False
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "plan IN ('free', 'starter', 'pro', 'enterprise')",
            name="check_tenant_plan"
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name="check_tenant_status"
        ),
        Index("idx_tenant_status_plan", "status", "plan"),
        Index("idx_tenant_status_created", "status", "created_at"),
    )


class TenantLimits(Base):
    """
    Resource limits for a tenant based on their subscription plan.
    Tracks both limits and current usage.
    """
    __tablename__ = "tenant_limits"

    # Foreign key as primary key (required, no default)
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True
    )

    # Resource limits
    max_monitors: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10"
    )
    max_networks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default="3"
    )
    max_triggers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=20,
        server_default="20"
    )
    max_api_calls_per_hour: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1000,
        server_default="1000"
    )
    max_storage_gb: Mapped[float] = mapped_column(
        DECIMAL(10, 2),
        nullable=False,
        default=1.0,
        server_default="1.0"
    )
    max_concurrent_operations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        server_default="10"
    )

    # Current usage tracking
    current_monitors: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )
    current_networks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )
    current_triggers: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )
    current_storage_gb: Mapped[float] = mapped_column(
        DECIMAL(10, 2),
        nullable=False,
        default=0.0,
        server_default="0.0"
    )

    # Timestamps for tracking
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

    # Relationship (excluded from init)
    tenant: Mapped["Tenant | None"] = relationship(
        "Tenant",
        back_populates="limits",
        init=False
    )
