"""
Enhanced CRUD operations for tenant management with advanced features.
"""

from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.plan_limits import get_plan_limits_for_db
from ..models.tenant import Tenant, TenantLimits
from ..schemas.tenant import (
    TenantCreate,
    TenantCreateInternal,
    TenantDelete,
    TenantFilter,
    TenantLimitsCreate,
    TenantLimitsRead,
    TenantLimitsUpdate,
    TenantRead,
    TenantSort,
    TenantUpdate,
    TenantUpdateInternal,
    TenantWithLimits,
)
from .base import EnhancedCRUD


class CRUDTenant(
    EnhancedCRUD[
        Tenant,
        TenantCreateInternal,
        TenantUpdate,
        TenantUpdateInternal,
        TenantDelete,
        TenantRead,
        TenantFilter,
        TenantSort,
    ]
):
    """
    Enhanced CRUD operations for Tenant model with business logic.
    Includes limits management, plan validation, and usage tracking.
    """

    async def create_with_limits(
        self, db: AsyncSession, obj_in: TenantCreate, plan_limits: Optional[dict[str, Any]] = None
    ) -> TenantWithLimits:
        """
        Create a new tenant with default limits based on plan.

        Args:
            db: Database session
            obj_in: Tenant creation data
            plan_limits: Optional custom limits for the plan

        Returns:
            Created tenant with limits
        """
        # Create tenant
        tenant_data = TenantCreateInternal(**obj_in.model_dump())
        tenant = Tenant(**tenant_data.model_dump())
        db.add(tenant)
        await db.flush()

        # Set default limits based on plan
        if plan_limits is None:
            plan_limits = self._get_default_limits_for_plan(obj_in.plan)

        # Create limits
        limits_data = TenantLimitsCreate(tenant_id=tenant.id, **plan_limits)
        limits = TenantLimits(**limits_data.model_dump())
        db.add(limits)
        await db.flush()

        # Load with relationships
        await db.refresh(tenant, ["limits"])

        return TenantWithLimits.model_validate(tenant)

    async def get_with_limits(self, db: AsyncSession, tenant_id: Any) -> Optional[TenantWithLimits]:
        """
        Get tenant with limits included.

        Args:
            db: Database session
            tenant_id: Tenant ID

        Returns:
            Tenant with limits or None
        """
        query = select(self.model).where(self.model.id == tenant_id).options(selectinload(self.model.limits))

        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if tenant:
            return TenantWithLimits.model_validate(tenant)
        return None

    async def update_limits(
        self, db: AsyncSession, tenant_id: Any, limits_update: TenantLimitsUpdate
    ) -> Optional[TenantLimitsRead]:
        """
        Update tenant limits.

        Args:
            db: Database session
            tenant_id: Tenant ID
            limits_update: Limits update data

        Returns:
            Updated limits or None
        """
        query = select(TenantLimits).where(TenantLimits.tenant_id == tenant_id)
        result = await db.execute(query)
        limits = result.scalar_one_or_none()

        if not limits:
            return None

        update_dict = limits_update.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(limits, key, value)

        await db.flush()
        await db.refresh(limits)

        return TenantLimitsRead.model_validate(limits)

    async def check_resource_limit(self, db: AsyncSession, tenant_id: Any, resource_type: str) -> tuple[bool, int, int]:
        """
        Check if tenant has capacity for a new resource.

        Args:
            db: Database session
            tenant_id: Tenant ID
            resource_type: Type of resource (monitors, networks, triggers)

        Returns:
            Tuple of (can_create, current_usage, max_limit)
        """
        query = select(TenantLimits).where(TenantLimits.tenant_id == tenant_id)
        result = await db.execute(query)
        limits = result.scalar_one_or_none()

        if not limits:
            return False, 0, 0

        max_field = f"max_{resource_type}"
        current_field = f"current_{resource_type}"

        max_value = getattr(limits, max_field, 0)
        current_value = getattr(limits, current_field, 0)

        can_create = current_value < max_value
        return can_create, current_value, max_value

    async def increment_usage(self, db: AsyncSession, tenant_id: Any, resource_type: str, amount: int = 1) -> bool:
        """
        Increment resource usage for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID
            resource_type: Type of resource
            amount: Amount to increment

        Returns:
            True if successful, False if limit exceeded
        """
        can_create, current, max_limit = await self.check_resource_limit(db, tenant_id, resource_type)

        if not can_create and amount > 0:
            return False

        query = select(TenantLimits).where(TenantLimits.tenant_id == tenant_id)
        result = await db.execute(query)
        limits = result.scalar_one_or_none()

        if limits:
            current_field = f"current_{resource_type}"
            new_value = getattr(limits, current_field, 0) + amount
            setattr(limits, current_field, max(0, new_value))
            await db.flush()

        return True

    async def decrement_usage(self, db: AsyncSession, tenant_id: Any, resource_type: str, amount: int = 1) -> bool:
        """
        Decrement resource usage for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID
            resource_type: Type of resource
            amount: Amount to decrement

        Returns:
            True if successful
        """
        return await self.increment_usage(db, tenant_id, resource_type, -amount)

    async def upgrade_plan(self, db: AsyncSession, tenant_id: Any, new_plan: str) -> Optional[TenantWithLimits]:
        """
        Upgrade tenant to a new plan with updated limits.

        Args:
            db: Database session
            tenant_id: Tenant ID
            new_plan: New plan name

        Returns:
            Updated tenant with new limits
        """
        tenant = await self.get_with_limits(db, tenant_id)
        if not tenant:
            return None

        # Update tenant plan
        update_query = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(update_query)
        tenant_obj = result.scalar_one_or_none()

        if tenant_obj:
            tenant_obj.plan = new_plan

            # Update limits for new plan
            new_limits = self._get_default_limits_for_plan(new_plan)
            await self.update_limits(db, tenant_id, TenantLimitsUpdate(**new_limits))

            await db.flush()
            return await self.get_with_limits(db, tenant_id)

        return None

    async def get_active_tenants(self, db: AsyncSession, page: int = 1, size: int = 50) -> dict[str, Any]:
        """
        Get all active tenants with pagination.

        Args:
            db: Database session
            page: Page number
            size: Page size

        Returns:
            Paginated active tenants
        """
        filters = TenantFilter(
            name=None, slug=None, plan=None, status="active", created_after=None, created_before=None
        )
        return await self.get_paginated(
            db, page=page, size=size, filters=filters, sort=TenantSort(field="created_at", order="desc")
        )

    async def suspend_tenant(
        self, db: AsyncSession, tenant_id: Any, reason: Optional[str] = None
    ) -> Optional[TenantRead]:
        """
        Suspend a tenant account.

        Args:
            db: Database session
            tenant_id: Tenant ID
            reason: Suspension reason

        Returns:
            Updated tenant or None
        """
        query = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if tenant:
            tenant.status = "suspended"
            if reason:
                tenant.settings["suspension_reason"] = reason
                tenant.settings["suspended_at"] = datetime.now(UTC).isoformat()

            await db.flush()
            await db.refresh(tenant)
            return TenantRead.model_validate(tenant)

        return None

    async def reactivate_tenant(self, db: AsyncSession, tenant_id: Any) -> Optional[TenantRead]:
        """
        Reactivate a suspended tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID

        Returns:
            Updated tenant or None
        """
        query = select(Tenant).where(Tenant.id == tenant_id)
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if tenant and tenant.status == "suspended":
            tenant.status = "active"
            # Remove suspension metadata
            tenant.settings.pop("suspension_reason", None)
            tenant.settings.pop("suspended_at", None)

            await db.flush()
            await db.refresh(tenant)
            return TenantRead.model_validate(tenant)

        return None

    async def get_by_slug(self, db: AsyncSession, slug: str, tenant_id: Optional[Any] = None) -> Optional[Tenant]:
        """
        Get tenant by slug.

        Args:
            db: Database session
            slug: Tenant slug
            tenant_id: Optional tenant ID (for consistency, not used for tenants)

        Returns:
            Tenant if found, None otherwise
        """
        # Note: tenant_id is ignored for tenant lookup, but kept for consistent API
        query = select(Tenant).where(Tenant.slug == slug)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    def _get_default_limits_for_plan(self, plan: str) -> dict[str, Any]:
        """
        Get default resource limits for a plan.
        Uses centralized plan limits configuration.

        Args:
            plan: Plan name

        Returns:
            Dictionary of default limits with max_ prefix for database fields
        """
        return get_plan_limits_for_db(plan)


# Export crud instance
crud_tenant = CRUDTenant(Tenant)
