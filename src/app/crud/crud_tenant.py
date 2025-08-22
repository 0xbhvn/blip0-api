"""
Enhanced CRUD operations for tenant management with advanced features.
"""

import json
import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import Any, Optional, Union

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.logger import logging
from ..core.plan_limits import get_plan_limits, get_plan_limits_for_db
from ..core.redis_client import redis_client
from ..models.tenant import Tenant, TenantLimits
from ..schemas.tenant import (
    TenantActivateRequest,
    TenantAdminPagination,
    TenantAdminRead,
    TenantCreate,
    TenantCreateInternal,
    TenantDelete,
    TenantFilter,
    TenantLimitsCreate,
    TenantLimitsRead,
    TenantLimitsUpdate,
    TenantRead,
    TenantSelfServiceUpdate,
    TenantSort,
    TenantSuspendRequest,
    TenantUpdate,
    TenantUpdateInternal,
    TenantUsageStats,
    TenantWithLimits,
)
from .base import EnhancedCRUD

logger = logging.getLogger(__name__)


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

    async def create_with_cache(
        self,
        db: AsyncSession,
        obj_in: TenantCreate,
    ) -> TenantRead:
        """
        Create a new tenant with write-through caching.

        Args:
            db: Database session
            obj_in: Tenant creation data

        Returns:
            Created tenant
        """
        # Create tenant in PostgreSQL (source of truth)
        tenant_internal = TenantCreateInternal(**obj_in.model_dump())

        db_tenant = await self.create(db=db, object=tenant_internal)

        # Write-through to Redis for fast access
        await self._cache_tenant(db_tenant)

        logger.info(f"Created tenant {db_tenant.id} ({db_tenant.name})")
        return TenantRead.model_validate(db_tenant)

    async def get_with_cache(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
        use_cache: bool = True,
    ) -> Optional[TenantRead]:
        """
        Get a tenant by ID with cache support.

        Args:
            db: Database session
            tenant_id: Tenant ID
            use_cache: Whether to try cache first

        Returns:
            Tenant if found
        """
        # Ensure tenant_id is a string for cache key
        tenant_id_str = str(tenant_id)

        # Try cache first if enabled
        if use_cache:
            cached = await self._get_cached_tenant(tenant_id_str)
            if cached:
                logger.debug(f"Cache hit for tenant {tenant_id_str}")
                return cached

        # Fallback to database
        db_tenant = await self.get(db=db, id=tenant_id)

        if not db_tenant:
            return None

        # Refresh cache on cache miss
        if use_cache:
            await self._cache_tenant(db_tenant)

        return TenantRead.model_validate(db_tenant)

    async def update_with_cache(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
        obj_in: TenantUpdate,
    ) -> Optional[TenantRead]:
        """
        Update a tenant with cache invalidation.

        Args:
            db: Database session
            tenant_id: Tenant ID
            obj_in: Update data

        Returns:
            Updated tenant if found
        """
        # Update in PostgreSQL
        db_tenant = await self.update(db=db, object=obj_in, id=tenant_id)

        if not db_tenant:
            return None

        # Invalidate and refresh cache
        tenant_id_str = str(tenant_id)
        await self._invalidate_tenant_cache(tenant_id_str)
        await self._cache_tenant(db_tenant)

        logger.info(f"Updated tenant {tenant_id_str}")
        return TenantRead.model_validate(db_tenant)

    async def delete_with_cache(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
        is_hard_delete: bool = False,
    ) -> bool:
        """
        Delete a tenant with cache cleanup.

        WARNING: This will also clean up all tenant-specific cached data.

        Args:
            db: Database session
            tenant_id: Tenant ID
            is_hard_delete: If True, permanently delete

        Returns:
            True if deleted successfully
        """
        tenant_id_str = str(tenant_id)

        # Delete from PostgreSQL
        try:
            await self.delete(db=db, id=tenant_id, is_hard_delete=is_hard_delete)
            deleted = True
        except Exception:
            deleted = False

        if deleted:
            # Remove from cache
            await self._invalidate_tenant_cache(tenant_id_str)

            # Clean up all tenant-specific data from cache
            await self._cleanup_tenant_cache(tenant_id_str)

            logger.info(f"Deleted tenant {tenant_id_str}")

        return bool(deleted)

    async def get_tenant_stats(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
    ) -> dict[str, Any]:
        """
        Get statistics for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID

        Returns:
            Tenant statistics including monitor count, trigger count, etc.
        """
        tenant_id_str = str(tenant_id)

        # Get tenant to ensure it exists
        tenant = await self.get_with_cache(db, tenant_id)
        if not tenant:
            return {}

        # Get counts from cache if available
        stats = {
            "tenant_id": tenant_id_str,
            "tenant_name": tenant.name,
            "active_monitors": 0,
            "total_triggers": 0,
            "is_active": tenant.is_active,
        }

        # Get active monitor count from cache
        try:
            monitor_key = f"tenant:{tenant_id_str}:monitors:active"
            monitor_ids = await redis_client.smembers(monitor_key)
            stats["active_monitors"] = len(monitor_ids)
        except Exception:
            pass

        return stats

    async def suspend_tenant_with_request(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
        request: TenantSuspendRequest,
    ) -> Optional[TenantRead]:
        """
        Suspend a tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID
            request: Suspension request details

        Returns:
            Updated tenant if found
        """
        tenant_update = TenantUpdate(
            status="suspended",
            name=None,
            slug=None,
            settings={"suspension_reason": request.reason, "suspended_at": datetime.now(UTC).isoformat()}
            if request.reason
            else {"suspended_at": datetime.now(UTC).isoformat()},
        )

        updated_tenant = await self.update_with_cache(db, tenant_id, tenant_update)

        if updated_tenant and request.notify_users:
            # TODO: Implement user notification logic
            logger.info(f"Would notify users of tenant {tenant_id} about suspension")

        return updated_tenant

    async def activate_tenant_with_request(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
        request: TenantActivateRequest,
    ) -> Optional[TenantRead]:
        """
        Activate a suspended tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID
            request: Activation request details

        Returns:
            Updated tenant if found
        """
        tenant_update = TenantUpdate(
            status="active",
            name=None,
            slug=None,
            settings={"activation_reason": request.reason, "activated_at": datetime.now(UTC).isoformat()}
            if request.reason
            else {"activated_at": datetime.now(UTC).isoformat()},
        )

        updated_tenant = await self.update_with_cache(db, tenant_id, tenant_update)

        if updated_tenant and request.notify_users:
            # TODO: Implement user notification logic
            logger.info(f"Would notify users of tenant {tenant_id} about activation")

        return updated_tenant

    async def get_tenant_usage(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
    ) -> Optional[TenantUsageStats]:
        """
        Get detailed usage statistics for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID

        Returns:
            Tenant usage statistics
        """
        from ..models.monitor import Monitor
        from ..models.trigger import Trigger

        tenant_id_uuid = uuid_pkg.UUID(str(tenant_id)) if isinstance(tenant_id, str) else tenant_id

        # Get tenant with limits
        tenant = await self.get_with_limits(db, tenant_id_uuid)
        if not tenant:
            return None

        # Get current counts from database
        monitor_count_query = select(func.count(Monitor.id)).where(
            Monitor.tenant_id == tenant_id_uuid,
            Monitor.active == True,  # noqa: E712
        )
        trigger_count_query = select(func.count(Trigger.id)).where(
            Trigger.tenant_id == tenant_id_uuid,
            Trigger.active == True,  # noqa: E712
        )

        monitor_count_result = await db.execute(monitor_count_query)
        monitor_count = monitor_count_result.scalar() or 0

        trigger_count_result = await db.execute(trigger_count_query)
        trigger_count = trigger_count_result.scalar() or 0

        # Get API calls from Redis (last hour)
        api_calls_key = f"tenant:{tenant_id}:api_calls:hour"
        try:
            api_calls = await redis_client.get(api_calls_key)
            api_calls_last_hour = int(api_calls) if api_calls else 0
        except Exception:
            api_calls_last_hour = 0

        # Get limits (use defaults if not set)
        limits = tenant.limits if hasattr(tenant, "limits") and tenant.limits else None

        # Use centralized plan limits
        plan_limits = get_plan_limits(tenant.plan)

        monitors_limit = int(limits.max_monitors) if limits else int(plan_limits["monitors"])
        networks_limit = int(limits.max_networks) if limits else int(plan_limits["networks"])
        triggers_limit = int(limits.max_triggers) if limits else int(plan_limits["triggers"])
        api_calls_limit = int(limits.max_api_calls_per_hour) if limits else int(plan_limits["api_calls"])
        storage_limit = float(limits.max_storage_gb) if limits else float(plan_limits["storage"])

        # Calculate current storage (placeholder - would need actual calculation)
        storage_used = float(limits.current_storage_gb) if limits and hasattr(limits, "current_storage_gb") else 0.0

        # Calculate remaining quotas
        monitors_remaining = max(0, monitors_limit - monitor_count)
        triggers_remaining = max(0, triggers_limit - trigger_count)
        api_calls_remaining = max(0, api_calls_limit - api_calls_last_hour)
        storage_remaining = max(0.0, storage_limit - storage_used)

        # Calculate usage percentages
        def calc_percent(used: float, limit: float) -> float:
            return min(100.0, (used / limit * 100) if limit > 0 else 0.0)

        return TenantUsageStats(
            tenant_id=tenant_id_uuid,
            # Current usage
            monitors_count=monitor_count,
            networks_count=0,  # TODO: Implement network counting
            triggers_count=trigger_count,
            storage_gb_used=storage_used,
            api_calls_last_hour=api_calls_last_hour,
            # Limits
            monitors_limit=monitors_limit,
            networks_limit=networks_limit,
            triggers_limit=triggers_limit,
            storage_gb_limit=storage_limit,
            api_calls_per_hour_limit=api_calls_limit,
            # Remaining
            monitors_remaining=monitors_remaining,
            networks_remaining=networks_limit,  # TODO: Calculate actual remaining
            triggers_remaining=triggers_remaining,
            storage_gb_remaining=storage_remaining,
            api_calls_remaining=api_calls_remaining,
            # Percentages
            monitors_usage_percent=calc_percent(monitor_count, monitors_limit),
            networks_usage_percent=0.0,  # TODO: Calculate actual percentage
            triggers_usage_percent=calc_percent(trigger_count, triggers_limit),
            storage_usage_percent=calc_percent(storage_used, storage_limit),
            api_calls_usage_percent=calc_percent(api_calls_last_hour, api_calls_limit),
            calculated_at=datetime.now(UTC),
        )

    async def get_tenant_limits(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
    ) -> Optional[TenantLimitsRead]:
        """
        Get tenant limits and quotas.

        Args:
            db: Database session
            tenant_id: Tenant ID

        Returns:
            Tenant limits if found
        """
        from ..models.tenant import TenantLimits

        tenant_id_uuid = uuid_pkg.UUID(str(tenant_id)) if isinstance(tenant_id, str) else tenant_id

        # Get limits from database
        limits_query = select(TenantLimits).where(TenantLimits.tenant_id == tenant_id_uuid)
        result = await db.execute(limits_query)
        limits = result.scalar_one_or_none()

        if limits:
            return TenantLimitsRead.model_validate(limits)

        # Return default limits based on tenant plan
        tenant = await self.get_with_cache(db, tenant_id)
        if not tenant:
            return None

        # Use centralized plan limits
        # Note: Keys differ here (max_ prefix) for TenantLimitsRead compatibility
        plan_limits_raw = get_plan_limits(tenant.plan)
        plan_limits = {
            "max_monitors": plan_limits_raw["monitors"],
            "max_networks": plan_limits_raw["networks"],
            "max_triggers": plan_limits_raw["triggers"],
            "max_api_calls_per_hour": plan_limits_raw["api_calls"],
            "max_storage_gb": plan_limits_raw["storage"],
        }

        return TenantLimitsRead(
            tenant_id=tenant_id_uuid,
            max_monitors=int(plan_limits["max_monitors"]),
            max_networks=int(plan_limits["max_networks"]),
            max_triggers=int(plan_limits["max_triggers"]),
            max_api_calls_per_hour=int(plan_limits["max_api_calls_per_hour"]),
            max_storage_gb=float(plan_limits["max_storage_gb"]),
            max_concurrent_operations=10,
            current_monitors=0,
            current_networks=0,
            current_triggers=0,
            current_storage_gb=0.0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def update_tenant_self_service(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
        update_data: TenantSelfServiceUpdate,
    ) -> Optional[TenantRead]:
        """
        Update tenant with limited self-service fields.

        Args:
            db: Database session
            tenant_id: Tenant ID
            update_data: Self-service update data

        Returns:
            Updated tenant if found
        """
        # Convert to regular update but only with allowed fields
        tenant_update = TenantUpdate(
            name=update_data.name,
            slug=None,
            settings=update_data.settings,
        )

        return await self.update_with_cache(db, tenant_id, tenant_update)

    async def list_all_tenants(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 50,
        filters: Optional[TenantFilter] = None,
        sort: Optional[TenantSort] = None,
    ) -> TenantAdminPagination:
        """
        List all tenants for admin with enhanced information.

        Args:
            db: Database session
            page: Page number
            size: Page size
            filters: Filter criteria
            sort: Sort criteria

        Returns:
            Paginated tenant list with admin details
        """
        from ..models.monitor import Monitor
        from ..models.tenant import TenantLimits
        from ..models.trigger import Trigger
        from ..models.user import User

        # Get base pagination
        result = await self.get_paginated(db, page, size, filters, sort)

        if not result["items"]:
            return TenantAdminPagination(
                items=[],
                total=result["total"],
                page=result["page"],
                size=result["size"],
                pages=result["pages"],
            )

        # Collect all tenant IDs for batch queries
        tenant_ids = [tenant.id for tenant in result["items"]]

        # Batch query for user counts
        user_counts_query = (
            select(User.tenant_id, func.count(User.id).label("count"))
            .where(User.tenant_id.in_(tenant_ids), ~User.is_deleted)
            .group_by(User.tenant_id)
        )
        user_counts_result = await db.execute(user_counts_query)
        user_counts = {row.tenant_id: int(row.count) for row in user_counts_result}  # type: ignore[call-overload]

        # Batch query for monitor counts
        monitor_counts_query = (
            select(Monitor.tenant_id, func.count(Monitor.id).label("count"))
            .where(Monitor.tenant_id.in_(tenant_ids), Monitor.active == True)  # noqa: E712
            .group_by(Monitor.tenant_id)
        )
        monitor_counts_result = await db.execute(monitor_counts_query)
        monitor_counts = {row.tenant_id: int(row.count) for row in monitor_counts_result}  # type: ignore[call-overload]

        # Batch query for trigger counts
        trigger_counts_query = (
            select(Trigger.tenant_id, func.count(Trigger.id).label("count"))
            .where(Trigger.tenant_id.in_(tenant_ids), Trigger.active == True)  # noqa: E712
            .group_by(Trigger.tenant_id)
        )
        trigger_counts_result = await db.execute(trigger_counts_query)
        trigger_counts = {row.tenant_id: int(row.count) for row in trigger_counts_result}  # type: ignore[call-overload]

        # Batch query for tenant limits
        limits_query = select(TenantLimits).where(TenantLimits.tenant_id.in_(tenant_ids))
        limits_result = await db.execute(limits_query)
        tenant_limits = {limit.tenant_id: limit for limit in limits_result.scalars()}

        # Build enhanced items with batch-fetched data
        enhanced_items = []
        for tenant in result["items"]:
            # Get counts from batch results (default to 0 if not found)
            user_count = user_counts.get(tenant.id, 0)
            monitor_count = monitor_counts.get(tenant.id, 0)
            trigger_count = trigger_counts.get(tenant.id, 0)

            # Get limits from batch results or create defaults
            limits: Optional[TenantLimitsRead]
            if tenant.id in tenant_limits:
                limits = TenantLimitsRead.model_validate(tenant_limits[tenant.id])
            else:
                # Use the existing method for default limits (won't cause N+1 since it's just defaults)
                limits = await self.get_tenant_limits(db, tenant.id)

            # Create admin read schema
            admin_tenant = TenantAdminRead(
                **TenantRead.model_validate(tenant).model_dump(),
                limits=limits,
                user_count=user_count,
                monitor_count=monitor_count,
                trigger_count=trigger_count,
                last_activity=None,  # TODO: Track last activity
                suspended_at=tenant.settings.get("suspended_at") if tenant.settings else None,
                suspension_reason=tenant.settings.get("suspension_reason") if tenant.settings else None,
            )
            enhanced_items.append(admin_tenant)

        return TenantAdminPagination(
            items=enhanced_items,
            total=result["total"],
            page=result["page"],
            size=result["size"],
            pages=result["pages"],
        )

    # Redis caching helper methods
    async def _cache_tenant(self, tenant: Union[Tenant, TenantRead, dict[str, Any]]) -> None:
        """Cache tenant configuration in Redis."""
        try:
            # Handle different types that might be passed
            if isinstance(tenant, dict):
                tenant_id = tenant.get("id")
                tenant_dict = TenantRead.model_validate(tenant).model_dump_json()
            else:
                tenant_id = tenant.id
                tenant_dict = TenantRead.model_validate(tenant).model_dump_json()

            key = f"tenant:{tenant_id}:config"

            # Cache for 1 hour (3600 seconds)
            # oz-multi-tenant refreshes every 30 seconds but cache TTL is longer
            await redis_client.set(key, tenant_dict, expiration=3600)
        except Exception as e:
            logger.error(f"Failed to cache tenant {tenant_id}: {e}")

    async def _get_cached_tenant(self, tenant_id: str) -> Optional[TenantRead]:
        """Get tenant from cache."""
        try:
            key = f"tenant:{tenant_id}:config"
            cached = await redis_client.get(key)

            if cached:
                if isinstance(cached, str):
                    cached = json.loads(cached)
                return TenantRead.model_validate(cached)
            return None
        except Exception as e:
            logger.error(f"Failed to get cached tenant {tenant_id}: {e}")
            return None

    async def _invalidate_tenant_cache(self, tenant_id: str) -> None:
        """Invalidate tenant cache."""
        try:
            key = f"tenant:{tenant_id}:config"
            await redis_client.delete(key)
        except Exception as e:
            logger.error(f"Failed to invalidate tenant cache {tenant_id}: {e}")

    async def _cleanup_tenant_cache(self, tenant_id: str) -> None:
        """
        Clean up all tenant-specific data from cache.
        This includes monitors, triggers, and any other tenant-scoped data.
        """
        try:
            # Delete all tenant-specific keys
            patterns = [
                f"tenant:{tenant_id}:*",  # All tenant-specific keys
            ]

            deleted_count = 0
            for pattern in patterns:
                count = await redis_client.delete_pattern(pattern)
                deleted_count += count

            logger.info(f"Cleaned up {deleted_count} cache keys for tenant {tenant_id}")
        except Exception as e:
            logger.error(f"Failed to cleanup tenant cache {tenant_id}: {e}")


# Export crud instance
crud_tenant = CRUDTenant(Tenant)
