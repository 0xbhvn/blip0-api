import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..core.db.database import Base

if TYPE_CHECKING:
    from .tenant import Tenant


class User(Base):
    __tablename__ = "user"

    # Primary key with init=False (doesn't affect dataclass ordering)
    id: Mapped[int] = mapped_column(
        "id", autoincrement=True, nullable=False, unique=True, primary_key=True, init=False)

    # Required fields (no defaults, must come first)
    name: Mapped[str] = mapped_column(String(30))
    username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)

    # Fields with defaults
    uuid: Mapped[uuid_pkg.UUID] = mapped_column(
        default_factory=uuid_pkg.uuid4, primary_key=True, unique=True)
    profile_image_url: Mapped[str] = mapped_column(
        String, default="https://profileimageurl.com")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default_factory=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None)
    is_deleted: Mapped[bool] = mapped_column(default=False, index=True)
    is_superuser: Mapped[bool] = mapped_column(default=False)

    # Tenant relationship for multi-tenancy
    tenant_id: Mapped[uuid_pkg.UUID | None] = mapped_column(
        ForeignKey("tenants.id"),
        index=True,
        default=None,
        nullable=True,
        comment="Associated tenant for multi-tenant isolation"
    )

    # Legacy tier_id (can be removed later when migrating to tenant-based plans)
    tier_id: Mapped[int | None] = mapped_column(
        ForeignKey("tier.id"), index=True, default=None, init=False)

    # Relationship to Tenant (excluded from init)
    tenant: Mapped["Tenant | None"] = relationship(
        "Tenant",
        back_populates="users",
        init=False
    )
