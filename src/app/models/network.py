import uuid as uuid_pkg
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base


class Network(Base):
    """
    Network model for blockchain network configurations.
    Supports both EVM and Stellar network types with their specific configurations.
    """
    __tablename__ = "networks"

    # Required fields first (no defaults)
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    network_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )
    block_time_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Average block time in milliseconds"
    )

    # Optional/nullable fields
    description: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None)
    chain_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None,
        comment="Chain ID for EVM networks"
    )
    network_passphrase: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
        comment="Network passphrase for Stellar networks"
    )

    # RPC URLs as JSONB array
    # Format: [{"url": "https://...", "type_": "primary", "weight": 100}]
    rpc_urls: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default_factory=list,
        server_default="[]",
        comment="Array of RPC endpoints with url, type_, and weight"
    )

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
    )

    # Fields with defaults
    confirmation_blocks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="Number of blocks to wait for confirmation"
    )
    cron_schedule: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="*/10 * * * * *",
        server_default="*/10 * * * * *",
        comment="Cron schedule for polling"
    )
    max_past_blocks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default="100",
        comment="Maximum number of past blocks to fetch"
    )
    store_blocks: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="Whether to store all block data"
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
            name="unique_active_network",
            deferrable=True,
            initially="DEFERRED"
        ),
        CheckConstraint(
            "network_type IN ('EVM', 'Stellar')",
            name="check_network_type"
        ),
        # Composite indexes for common query patterns
        Index("idx_network_tenant_active", "tenant_id", "active"),
        Index("idx_network_tenant_type", "tenant_id", "network_type"),
        Index("idx_network_tenant_slug", "tenant_id", "slug"),
        {"comment": "Normalized network configurations from configurations table with RPC URLs as JSONB"},
    )
