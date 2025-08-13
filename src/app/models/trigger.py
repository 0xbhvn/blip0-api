import uuid as uuid_pkg
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db.database import Base


class Trigger(Base):
    """
    Base trigger model for action configurations.
    Supports email and webhook trigger types through separate detail tables.
    """
    __tablename__ = "triggers"

    # Required fields first (no defaults)
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=False,
        index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )

    # Optional fields
    description: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None)

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
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
        default=lambda: datetime.now(UTC),
        server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
        onupdate=lambda: datetime.now(UTC)
    )

    # Relationships to specific trigger types (excluded from init)
    email_config: Mapped["EmailTrigger | None"] = relationship(
        "EmailTrigger",
        back_populates="trigger",
        cascade="all, delete-orphan",
        uselist=False,
        init=False
    )
    webhook_config: Mapped["WebhookTrigger | None"] = relationship(
        "WebhookTrigger",
        back_populates="trigger",
        cascade="all, delete-orphan",
        uselist=False,
        init=False
    )

    # Table constraints
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "slug",
            name="unique_active_trigger",
            deferrable=True,
            initially="DEFERRED"
        ),
        CheckConstraint(
            "trigger_type IN ('email', 'webhook')",
            name="check_trigger_type"
        ),
        # Composite indexes for common query patterns
        Index("idx_trigger_tenant_active", "tenant_id", "active"),
        Index("idx_trigger_tenant_type", "tenant_id", "trigger_type"),
        Index("idx_trigger_tenant_slug", "tenant_id", "slug"),
        Index("idx_trigger_tenant_type_active",
              "tenant_id", "trigger_type", "active"),
        {"comment": "Normalized trigger configurations from configurations table"},
    )


class EmailTrigger(Base):
    """
    Email-specific trigger configuration.
    Stores SMTP settings and email composition details.
    """
    __tablename__ = "email_triggers"

    # Required fields first (Foreign key as primary key)
    trigger_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("triggers.id", ondelete="CASCADE"),
        primary_key=True
    )

    # Required SMTP configuration
    host: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="SMTP server hostname"
    )
    username_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="How username is stored: Plain, Environment, HashicorpCloudVault"
    )
    username_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Username value or reference based on type"
    )
    password_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="How password is stored: Plain, Environment, HashicorpCloudVault"
    )
    password_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Password value or reference based on type"
    )
    sender: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="From email address"
    )
    message_title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Email subject template"
    )
    message_body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Email body template"
    )

    # Fields with defaults
    port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=465,
        server_default="465",
        comment="SMTP server port"
    )
    recipients: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default="[]",
        comment="Array of recipient email addresses"
    )

    # Timestamps for tracking
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
        onupdate=lambda: datetime.now(UTC)
    )

    # Relationship (excluded from init)
    trigger: Mapped["Trigger | None"] = relationship(
        "Trigger",
        back_populates="email_config",
        init=False
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "username_type IN ('Plain', 'Environment', 'HashicorpCloudVault')",
            name="check_email_username_type"
        ),
        CheckConstraint(
            "password_type IN ('Plain', 'Environment', 'HashicorpCloudVault')",
            name="check_email_password_type"
        ),
        {"comment": "Email-specific trigger configuration with recipients array"},
    )


class WebhookTrigger(Base):
    """
    Webhook-specific trigger configuration.
    Stores HTTP endpoint settings and request details.
    """
    __tablename__ = "webhook_triggers"

    # Required fields first (Foreign key as primary key)
    trigger_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("triggers.id", ondelete="CASCADE"),
        primary_key=True
    )
    url_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="How URL is stored: Plain, Environment, HashicorpCloudVault"
    )
    url_value: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="URL value or reference based on type"
    )
    message_title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Webhook payload title template"
    )
    message_body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Webhook payload body template"
    )

    # Optional fields
    secret_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        default=None,
        comment="How secret is stored: Plain, Environment, HashicorpCloudVault"
    )
    secret_value: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Secret value or reference based on type"
    )

    # Fields with defaults
    method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="POST",
        server_default="POST",
        comment="HTTP method to use"
    )
    headers: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
        comment="Additional HTTP headers to send"
    )

    # Timestamps for tracking
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default="NOW()",
        onupdate=lambda: datetime.now(UTC)
    )

    # Relationship (excluded from init)
    trigger: Mapped["Trigger | None"] = relationship(
        "Trigger",
        back_populates="webhook_config",
        init=False
    )

    # Table constraints
    __table_args__ = (
        CheckConstraint(
            "url_type IN ('Plain', 'Environment', 'HashicorpCloudVault')",
            name="check_webhook_url_type"
        ),
        CheckConstraint(
            "method IN ('POST', 'GET', 'PUT', 'PATCH', 'DELETE')",
            name="check_webhook_method"
        ),
        CheckConstraint(
            "secret_type IN ('Plain', 'Environment', 'HashicorpCloudVault')",
            name="check_webhook_secret_type"
        ),
        {"comment": "Webhook-specific trigger configuration"},
    )
