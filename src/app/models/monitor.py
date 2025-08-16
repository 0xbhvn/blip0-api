import uuid as uuid_pkg
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base


class Monitor(Base):
    """
    Monitor model for blockchain monitoring configurations.
    Defines what to watch (networks, addresses) and match conditions (functions, events, transactions).
    """
    __tablename__ = "monitors"

    # Required fields first (no defaults)
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Optional/nullable fields
    description: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None)

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
    )

    # Monitor configuration
    paused: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether the monitor is temporarily paused"
    )

    # Networks and addresses to monitor (JSONB arrays)
    networks: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default_factory=list,
        server_default="[]",
        comment="Array of network slugs this monitor watches"
    )
    addresses: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default_factory=list,
        server_default="[]",
        comment="Array of address objects with optional contract specs"
    )

    # Match conditions separated into columns (JSONB arrays)
    match_functions: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default_factory=list,
        server_default="[]",
        comment="Array of function conditions with signature and expression"
    )
    match_events: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default_factory=list,
        server_default="[]",
        comment="Array of event conditions with signature and expression"
    )
    match_transactions: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default_factory=list,
        server_default="[]",
        comment="Array of transaction conditions with optional status and expression"
    )

    # Trigger configuration (JSONB arrays)
    trigger_conditions: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default_factory=list,
        server_default="[]",
        comment="Array of filter scripts to apply before triggering"
    )
    triggers: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default_factory=list,
        server_default="[]",
        comment="Array of trigger slugs to execute when conditions match"
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
        default=None
    )

    # Additional timestamp
    last_validated_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        default=None
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

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "slug",
            name="unique_active_monitor",
            deferrable=True,
            initially="DEFERRED"
        ),
        # Composite indexes for common query patterns
        Index("idx_monitor_tenant_active", "tenant_id", "active"),
        Index("idx_monitor_tenant_paused", "tenant_id", "paused"),
        Index("idx_monitor_tenant_slug", "tenant_id", "slug"),
        Index("idx_monitor_tenant_active_paused",
              "tenant_id", "active", "paused"),
        {"comment": "Normalized monitor configurations with all relationships stored as JSONB fields"},
    )

    # Example of match_functions structure:
    # [
    #   {
    #     "signature": "transfer(address,uint256)",
    #     "expression": "args.value > 1000000000000000000"
    #   }
    # ]

    # Example of addresses structure:
    # [
    #   {
    #     "address": "0x123...",
    #     "contract_specs": {
    #       "abi": [...],
    #       "name": "USDC Token"
    #     }
    #   }
    # ]

    # Example of trigger_conditions structure:
    # [
    #   {
    #     "type": "filter",
    #     "script": "large_transfer_filter",
    #     "params": {"threshold": 1000000}
    #   }
    # ]
