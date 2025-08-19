"""API Key model for API authentication."""

import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db.database import Base

if TYPE_CHECKING:
    from .tenant import Tenant
    from .user import User


class APIKey(Base):
    """API Key model for programmatic access to the API.

    API keys provide an alternative authentication method to JWT tokens,
    useful for server-to-server communication and automation.
    """

    __tablename__ = "api_keys"

    # Required fields (no defaults)
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Descriptive name for the API key"
    )
    key_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Hashed version of the API key"
    )
    prefix: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="Key prefix for identification (e.g., 'blp0_')"
    )
    last_four: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
        comment="Last 4 characters of the key for identification"
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False
    )
    tenant_id: Mapped[uuid_pkg.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False
    )

    # Primary key with default
    id: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4,
        primary_key=True,
        unique=True
    )

    # Optional fields (have implicit None default)
    scopes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Space-separated list of scopes/permissions"
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Optional expiration timestamp"
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        comment="Last time the key was used"
    )

    # Fields with defaults
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true"
    )
    usage_count: Mapped[int] = mapped_column(
        default=0,
        server_default="0",
        comment="Number of times the key has been used"
    )
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

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="api_keys",
        init=False
    )
    tenant: Mapped["Tenant"] = relationship(
        "Tenant",
        init=False
    )

    # Table configuration
    __table_args__ = (
        Index("idx_api_key_user_tenant", "user_id", "tenant_id"),
        Index("idx_api_key_tenant_active", "tenant_id", "is_active"),
        Index("idx_api_key_expires", "expires_at"),
    )

    def is_expired(self) -> bool:
        """Check if the API key has expired.

        Returns
        -------
        bool
            True if the key has expired, False otherwise.
        """
        if not self.expires_at:
            return False
        return datetime.now(UTC) > self.expires_at

    def has_scope(self, required_scope: str) -> bool:
        """Check if the API key has a specific scope.

        Parameters
        ----------
        required_scope : str
            The scope to check for.

        Returns
        -------
        bool
            True if the key has the scope, False otherwise.
        """
        if not self.scopes:
            return False

        key_scopes = set(self.scopes.split())
        return required_scope in key_scopes or "*" in key_scopes
