import uuid as uuid_pkg
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base


class UserAuditLog(Base):
    """
    Audit log for user actions, especially administrative and security-critical operations.
    This includes superuser tenant switches, API key operations, and permission changes.
    """
    __tablename__ = "user_audit_logs"

    # Required fields first (no defaults)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id"),
        nullable=False,
        index=True,
        comment="User who performed the action"
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Action type (e.g., 'tenant_switch', 'api_key_create', 'permission_grant')"
    )
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of resource affected (e.g., 'tenant', 'api_key', 'user')"
    )

    # Optional/nullable fields
    resource_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="ID of the affected resource"
    )
    target_tenant_id: Mapped[uuid_pkg.UUID | None] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
        comment="Target tenant for cross-tenant operations"
    )
    details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        comment="Additional details about the action"
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),  # Supports IPv6
        nullable=True,
        comment="IP address of the user"
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        comment="User agent string"
    )

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
    )

    # Timestamp - audit logs should be immutable
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default="NOW()",
        comment="When the action occurred"
    )

    # Table constraints and indexes
    __table_args__ = (
        # Composite indexes for common query patterns
        Index("idx_user_audit_user_action", "user_id", "action"),
        Index("idx_user_audit_created", "created_at"),
        Index("idx_user_audit_target_tenant", "target_tenant_id", "created_at"),
        {"comment": "Immutable audit log for security-critical user actions"},
    )


class BlockState(Base):
    """
    Block processing state per network per tenant.
    Tracks the last processed block and processing status for each network.
    """
    __tablename__ = "block_state"

    # Required fields first (no defaults)
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )
    network_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("networks.id"),
        nullable=False,
        index=True
    )

    # Optional/nullable fields
    last_processed_block: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        default=None
    )
    last_processed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        default=None
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        default=None
    )
    blocks_per_minute: Mapped[Decimal | None] = mapped_column(
        DECIMAL(10, 2),
        nullable=True,
        default=None
    )
    average_processing_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None
    )

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
    )

    # Fields with defaults
    processing_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="idle",
        server_default="idle"
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
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
            "tenant_id", "network_id",
            name="unique_block_state",
            deferrable=True,
            initially="DEFERRED"
        ),
        CheckConstraint(
            "processing_status IN ('idle', 'processing', 'error', 'paused')",
            name="check_block_state_status"
        ),
        # Composite indexes for common query patterns
        Index("idx_blockstate_tenant_network", "tenant_id", "network_id"),
        Index("idx_blockstate_tenant_status", "tenant_id", "processing_status"),
        {"comment": "Block processing state per network per tenant"},
    )


class MissedBlock(Base):
    """
    Tracking for blocks that were missed during processing.
    Allows for retry logic and debugging of processing gaps.
    """
    __tablename__ = "missed_blocks"

    # Required fields first (no defaults)
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )
    network_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("networks.id"),
        nullable=False,
        index=True
    )
    block_number: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False
    )

    # Optional/nullable fields
    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        default=None
    )

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
    )

    # Fields with defaults
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )
    processed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false"
    )

    # Timestamp for when block was missed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default="NOW()",
        comment="When this block was identified as missed"
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "network_id", "block_number",
            name="unique_missed_block"
        ),
        # Composite indexes for common query patterns
        Index("idx_missedblock_tenant_network_processed", "tenant_id", "network_id", "processed"),
        Index("idx_missedblock_tenant_processed", "tenant_id", "processed"),
        {"comment": "Missed blocks tracking for retry logic"},
    )


class MonitorMatch(Base):
    """
    Records of when a monitor's conditions matched blockchain data.
    Stores the match data and tracks trigger execution results.
    """
    __tablename__ = "monitor_matches"

    # Required fields first (no defaults)
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )
    monitor_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("monitors.id"),
        nullable=False,
        index=True
    )
    network_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("networks.id"),
        nullable=False,
        index=True
    )
    block_number: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        index=True
    )
    match_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Details of what matched (event, function, transaction data)"
    )

    # Optional/nullable fields
    transaction_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        default=None,
        index=True
    )

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
    )

    # Execution tracking with defaults
    triggers_executed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )
    triggers_failed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )

    # Timestamp for when match occurred
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default="NOW()",
        comment="When this match was detected"
    )

    # Table constraints
    __table_args__ = (
        # Composite indexes for common query patterns
        Index("idx_monitormatch_tenant_monitor", "tenant_id", "monitor_id"),
        Index("idx_monitormatch_tenant_network_block", "tenant_id", "network_id", "block_number"),
        Index("idx_monitormatch_tenant_created", "tenant_id", "created_at"),
        {"comment": "Monitor execution results when conditions match"},
    )


class TriggerExecution(Base):
    """
    History of trigger executions, tracking success/failure and timing.
    Links to the monitor match that caused the trigger to fire.
    """
    __tablename__ = "trigger_executions"

    # Required fields first (no defaults)
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )
    trigger_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("triggers.id"),
        nullable=False,
        index=True
    )
    execution_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of execution: email, webhook"
    )
    execution_data: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Data sent or used in the execution"
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    # Optional/nullable fields
    monitor_match_id: Mapped[uuid_pkg.UUID | None] = mapped_column(
        ForeignKey("monitor_matches.id"),
        nullable=True,
        default=None,
        index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        nullable=True,
        default=None
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None
    )

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
    )

    # Fields with defaults
    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0"
    )

    # Timestamp for when execution was created
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default_factory=lambda: datetime.now(UTC),
        server_default="NOW()",
        comment="When this execution was initiated"
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "execution_type IN ('email', 'webhook')",
            name="check_trigger_execution_type"
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'success', 'failed', 'timeout')",
            name="check_trigger_execution_status"
        ),
        # Composite indexes for common query patterns
        Index("idx_triggerexec_tenant_trigger_status", "tenant_id", "trigger_id", "status"),
        Index("idx_triggerexec_tenant_status", "tenant_id", "status"),
        Index("idx_triggerexec_tenant_created", "tenant_id", "created_at"),
        Index("idx_triggerexec_match_id", "monitor_match_id"),
        {"comment": "Trigger execution history with status tracking"},
    )
