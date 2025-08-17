"""
Service layer for Tenant operations with Redis write-through caching.
Manages multi-tenant isolation and configuration.
"""

import json
import uuid as uuid_pkg
from datetime import UTC, datetime
from typing import Any, Optional, Union

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import logging
from ..core.plan_limits import get_plan_limits
from ..core.redis_client import redis_client
from ..crud.crud_tenant import CRUDTenant, crud_tenant
from ..models.tenant import Tenant
from ..schemas.tenant import (
    TenantActivateRequest,
    TenantAdminPagination,
    TenantAdminRead,
    TenantCreate,
    TenantCreateInternal,
    TenantFilter,
    TenantLimitsRead,
    TenantRead,
    TenantSelfServiceUpdate,
    TenantSort,
    TenantSuspendRequest,
    TenantUpdate,
    TenantUsageStats,
)
from .base_service import BaseService

logger = logging.getLogger(__name__)


class TenantService(BaseService[Tenant, TenantCreate, TenantUpdate, TenantRead]):
    """
    Service layer for Tenant operations.
    Handles tenant management with Redis caching for configuration access.
    """

    def __init__(self, crud_tenant: CRUDTenant):
        """Initialize tenant service with CRUD dependency."""
        super().__init__(crud_tenant)
        self.crud_tenant = crud_tenant

    def get_cache_key(self, entity_id: str, **kwargs) -> str:
        """
        Get Redis cache key for tenant.

        Args:
            entity_id: Tenant ID
            **kwargs: Additional key parameters

        Returns:
            Redis key string
        """
        key_type = kwargs.get("key_type", "config")
        return f"tenant:{entity_id}:{key_type}"

    def get_cache_ttl(self) -> int:
        """
        Get cache TTL in seconds.
        Cache TTL is 1 hour. The Rust monitor refreshes every 30 seconds,
        but the cache itself has a longer TTL for efficiency.

        Returns:
            TTL in seconds (3600)
        """
        return 3600

    @property
    def read_schema(self) -> type[TenantRead]:
        """Get the read schema class for validation."""
        return TenantRead

    async def create_tenant(
        self,
        db: AsyncSession,
        tenant_in: TenantCreate,
    ) -> TenantRead:
        """
        Create a new tenant with write-through caching.

        Args:
            db: Database session
            tenant_in: Tenant creation data

        Returns:
            Created tenant
        """
        # Create tenant in PostgreSQL (source of truth)
        tenant_internal = TenantCreateInternal(**tenant_in.model_dump())

        db_tenant = await self.crud_tenant.create(db=db, object=tenant_internal)

        # Write-through to Redis for fast access
        await self._cache_tenant(db_tenant)

        logger.info(f"Created tenant {db_tenant.id} ({db_tenant.name})")
        return TenantRead.model_validate(db_tenant)

    async def get_tenant(
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
        db_tenant = await self.crud_tenant.get(db=db, id=tenant_id)

        if not db_tenant:
            return None

        # Refresh cache on cache miss
        if use_cache:
            await self._cache_tenant(db_tenant)

        return TenantRead.model_validate(db_tenant)

    async def update_tenant(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID],
        tenant_update: TenantUpdate,
    ) -> Optional[TenantRead]:
        """
        Update a tenant with cache invalidation.

        Args:
            db: Database session
            tenant_id: Tenant ID
            tenant_update: Update data

        Returns:
            Updated tenant if found
        """
        # Update in PostgreSQL
        db_tenant = await self.crud_tenant.update(db=db, object=tenant_update, id=tenant_id)

        if not db_tenant:
            return None

        # Invalidate and refresh cache
        tenant_id_str = str(tenant_id)
        await self._invalidate_tenant_cache(tenant_id_str)
        await self._cache_tenant(db_tenant)

        logger.info(f"Updated tenant {tenant_id_str}")
        return TenantRead.model_validate(db_tenant)

    async def delete_tenant(
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
            await self.crud_tenant.delete(db=db, id=tenant_id, is_hard_delete=is_hard_delete)
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

    async def list_tenants(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 50,
        filters: Optional[TenantFilter] = None,
        sort: Optional[TenantSort] = None,
    ) -> dict[str, Any]:
        """
        List tenants with pagination, filtering, and sorting.

        Args:
            db: Database session
            page: Page number
            size: Page size
            filters: Filter criteria
            sort: Sort criteria

        Returns:
            Paginated tenant list
        """
        result = await self.crud_tenant.get_paginated(db=db, page=page, size=size, filters=filters, sort=sort)

        # Convert models to schemas
        result["items"] = [TenantRead.model_validate(item) for item in result["items"]]

        return result

    async def get_tenant_by_slug(
        self,
        db: AsyncSession,
        slug: str,
        use_cache: bool = True,
    ) -> Optional[TenantRead]:
        """
        Get a tenant by slug.

        Args:
            db: Database session
            slug: Tenant slug
            use_cache: Whether to use cache

        Returns:
            Tenant if found
        """
        # For now, fallback to database query
        # In future, could cache slug->id mapping
        db_tenant = await self.crud_tenant.get_by_slug(db=db, slug=slug)

        if not db_tenant:
            return None

        # Cache the tenant
        if use_cache:
            await self._cache_tenant(db_tenant)

        return TenantRead.model_validate(db_tenant)

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
        tenant = await self.get_tenant(db, tenant_id)
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

    async def suspend_tenant(
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

        updated_tenant = await self.update_tenant(db, tenant_id, tenant_update)

        if updated_tenant and request.notify_users:
            # TODO: Implement user notification logic
            logger.info(f"Would notify users of tenant {tenant_id} about suspension")

        return updated_tenant

    async def activate_tenant(
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

        updated_tenant = await self.update_tenant(db, tenant_id, tenant_update)

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
        tenant = await self.crud_tenant.get_with_limits(db, tenant_id_uuid)
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
        tenant = await self.get_tenant(db, tenant_id)
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

        return await self.update_tenant(db, tenant_id, tenant_update)

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
        result = await self.list_tenants(db, page, size, filters, sort)

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
                **tenant.model_dump(),
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


# Export service instance

tenant_service = TenantService(crud_tenant)
