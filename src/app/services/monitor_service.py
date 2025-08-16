"""
Service layer for Monitor operations with Redis write-through caching.
Implements denormalized caching for high-performance reads by Rust monitor.
"""

import json
import uuid as uuid_pkg
from typing import Any, Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.logger import logging
from ..core.redis_client import RedisClient
from ..crud.crud_monitor import CRUDMonitor
from ..crud.crud_trigger import CRUDTrigger
from ..models.monitor import Monitor
from ..schemas.monitor import (
    MonitorCreate,
    MonitorCreateInternal,
    MonitorFilter,
    MonitorRead,
    MonitorSort,
    MonitorUpdate,
)
from ..schemas.trigger import TriggerRead

logger = logging.getLogger(__name__)


class MonitorService:
    """
    Service layer for Monitor operations.
    Handles business logic, Redis caching, and denormalization.
    """

    def __init__(self, crud_monitor: CRUDMonitor, crud_trigger: CRUDTrigger):
        """Initialize monitor service with CRUD dependencies."""
        self.crud_monitor = crud_monitor
        self.crud_trigger = crud_trigger

    async def create_monitor(
        self,
        db: AsyncSession,
        monitor_in: MonitorCreate,
        tenant_id: Union[str, uuid_pkg.UUID],
    ) -> MonitorRead:
        """
        Create a new monitor with write-through caching.

        Args:
            db: Database session
            monitor_in: Monitor creation data
            tenant_id: Tenant ID for multi-tenancy

        Returns:
            Created monitor
        """
        # Create monitor in PostgreSQL (source of truth)
        # Ensure tenant_id is a UUID
        if isinstance(tenant_id, str):
            tenant_id = uuid_pkg.UUID(tenant_id)

        monitor_internal = MonitorCreateInternal(
            **monitor_in.model_dump(),
            tenant_id=tenant_id
        )

        db_monitor = await self.crud_monitor.create(
            db=db,
            object=monitor_internal
        )

        # Write-through to Redis for fast access
        await self._cache_monitor(db_monitor, str(tenant_id))

        # Add to active monitors list for this tenant
        await self._add_to_active_monitors(str(tenant_id), str(db_monitor.id))

        logger.info(f"Created monitor {db_monitor.id} for tenant {tenant_id}")
        return MonitorRead.model_validate(db_monitor)

    async def get_monitor(
        self,
        db: AsyncSession,
        monitor_id: str,
        tenant_id: str,
        use_cache: bool = True,
    ) -> Optional[MonitorRead]:
        """
        Get a monitor by ID with cache support.

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID for security
            use_cache: Whether to try cache first

        Returns:
            Monitor if found and authorized
        """
        # Try cache first if enabled
        if use_cache:
            cached = await self._get_cached_monitor(tenant_id, monitor_id)
            if cached:
                logger.debug(f"Cache hit for monitor {monitor_id}")
                return cached

        # Fallback to database
        db_monitor = await self.crud_monitor.get(
            db=db,
            id=monitor_id,
            tenant_id=tenant_id
        )

        if not db_monitor:
            return None

        # Refresh cache on cache miss
        if use_cache:
            await self._cache_monitor(db_monitor, tenant_id)

        return MonitorRead.model_validate(db_monitor)

    async def update_monitor(
        self,
        db: AsyncSession,
        monitor_id: str,
        monitor_update: MonitorUpdate,
        tenant_id: str,
    ) -> Optional[MonitorRead]:
        """
        Update a monitor with cache invalidation.

        Args:
            db: Database session
            monitor_id: Monitor ID
            monitor_update: Update data
            tenant_id: Tenant ID for security

        Returns:
            Updated monitor if found and authorized
        """
        # Update in PostgreSQL
        db_monitor = await self.crud_monitor.update(
            db=db,
            object=monitor_update,
            id=monitor_id,
            tenant_id=tenant_id
        )

        if not db_monitor:
            return None

        # Invalidate and refresh cache
        await self._invalidate_monitor_cache(tenant_id, monitor_id)
        await self._cache_monitor(db_monitor, tenant_id)

        logger.info(f"Updated monitor {monitor_id} for tenant {tenant_id}")
        return MonitorRead.model_validate(db_monitor)

    async def delete_monitor(
        self,
        db: AsyncSession,
        monitor_id: str,
        tenant_id: str,
        is_hard_delete: bool = False,
    ) -> bool:
        """
        Delete a monitor with cache cleanup.

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID for security
            is_hard_delete: If True, permanently delete

        Returns:
            True if deleted successfully
        """
        # Delete from PostgreSQL
        try:
            await self.crud_monitor.delete(
                db=db,
                id=monitor_id,
                is_hard_delete=is_hard_delete
            )
            deleted = True
        except Exception:
            deleted = False

        if deleted:
            # Remove from cache
            await self._invalidate_monitor_cache(tenant_id, monitor_id)
            await self._remove_from_active_monitors(tenant_id, monitor_id)
            logger.info(f"Deleted monitor {monitor_id} for tenant {tenant_id}")

        return bool(deleted)

    async def list_monitors(
        self,
        db: AsyncSession,
        tenant_id: str,
        page: int = 1,
        size: int = 50,
        filters: Optional[MonitorFilter] = None,
        sort: Optional[MonitorSort] = None,
    ) -> dict[str, Any]:
        """
        List monitors with pagination, filtering, and sorting.

        Args:
            db: Database session
            tenant_id: Tenant ID
            page: Page number
            size: Page size
            filters: Filter criteria
            sort: Sort criteria

        Returns:
            Paginated monitor list
        """
        result = await self.crud_monitor.get_paginated(
            db=db,
            page=page,
            size=size,
            filters=filters,
            sort=sort,
            tenant_id=tenant_id
        )

        # Convert models to schemas
        result["items"] = [
            MonitorRead.model_validate(item) for item in result["items"]
        ]

        return result

    async def get_monitor_with_triggers(
        self,
        db: AsyncSession,
        monitor_id: str,
        tenant_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Get a monitor with its associated triggers (denormalized).

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID

        Returns:
            Monitor with embedded triggers
        """
        # Query monitor with triggers using join
        query = (
            select(Monitor)
            .options(selectinload(Monitor.triggers))
            .where(
                Monitor.id == monitor_id,
                Monitor.tenant_id == tenant_id
            )
        )

        result = await db.execute(query)
        db_monitor = result.scalar_one_or_none()

        if not db_monitor:
            return None

        # Create denormalized structure
        monitor_dict = MonitorRead.model_validate(db_monitor).model_dump()
        monitor_dict["triggers"] = [
            TriggerRead.model_validate(trigger).model_dump()
            for trigger in db_monitor.triggers
        ]

        # Cache the denormalized structure
        await self._cache_monitor_denormalized(monitor_dict, tenant_id, monitor_id)

        return monitor_dict

    # Redis caching helper methods
    async def _cache_monitor(self, monitor: Any, tenant_id: str) -> None:
        """Cache monitor in Redis with tenant-specific key."""
        try:
            key = f"tenant:{tenant_id}:monitor:{monitor.id}"
            monitor_dict = MonitorRead.model_validate(monitor).model_dump_json()

            # Cache for 30 minutes (Rust monitor refreshes every 30 seconds)
            await RedisClient.set(key, monitor_dict, expiration=1800)
        except Exception as e:
            logger.error(f"Failed to cache monitor {monitor.id}: {e}")

    async def _cache_monitor_denormalized(
        self,
        monitor_dict: dict,
        tenant_id: str,
        monitor_id: str
    ) -> None:
        """Cache denormalized monitor with triggers."""
        try:
            key = f"tenant:{tenant_id}:monitor:{monitor_id}"
            await RedisClient.set(key, json.dumps(monitor_dict), expiration=1800)
        except Exception as e:
            logger.error(f"Failed to cache denormalized monitor {monitor_id}: {e}")

    async def _get_cached_monitor(
        self,
        tenant_id: str,
        monitor_id: str
    ) -> Optional[MonitorRead]:
        """Get monitor from cache."""
        try:
            key = f"tenant:{tenant_id}:monitor:{monitor_id}"
            cached = await RedisClient.get(key)

            if cached:
                if isinstance(cached, str):
                    cached = json.loads(cached)
                return MonitorRead.model_validate(cached)
            return None
        except Exception as e:
            logger.error(f"Failed to get cached monitor {monitor_id}: {e}")
            return None

    async def _invalidate_monitor_cache(
        self,
        tenant_id: str,
        monitor_id: str
    ) -> None:
        """Invalidate monitor cache."""
        try:
            key = f"tenant:{tenant_id}:monitor:{monitor_id}"
            await RedisClient.delete(key)
        except Exception as e:
            logger.error(f"Failed to invalidate monitor cache {monitor_id}: {e}")

    async def _add_to_active_monitors(
        self,
        tenant_id: str,
        monitor_id: str
    ) -> None:
        """Add monitor to tenant's active monitors list."""
        try:
            key = f"tenant:{tenant_id}:monitors:active"
            await RedisClient.sadd(key, monitor_id)
            await RedisClient.expire(key, 3600)  # Expire after 1 hour
        except Exception as e:
            logger.error(f"Failed to add monitor {monitor_id} to active list: {e}")

    async def _remove_from_active_monitors(
        self,
        tenant_id: str,
        monitor_id: str
    ) -> None:
        """Remove monitor from tenant's active monitors list."""
        try:
            key = f"tenant:{tenant_id}:monitors:active"
            await RedisClient.srem(key, monitor_id)
        except Exception as e:
            logger.error(f"Failed to remove monitor {monitor_id} from active list: {e}")

    async def get_active_monitor_ids(self, tenant_id: str) -> set[str]:
        """Get all active monitor IDs for a tenant from cache."""
        try:
            key = f"tenant:{tenant_id}:monitors:active"
            monitor_ids = await RedisClient.smembers(key)
            return {str(mid) for mid in monitor_ids}
        except Exception as e:
            logger.error(f"Failed to get active monitors for tenant {tenant_id}: {e}")
            return set()

    async def refresh_all_tenant_monitors(
        self,
        db: AsyncSession,
        tenant_id: str
    ) -> int:
        """
        Refresh all monitors for a tenant in Redis cache.
        Used for periodic cache refresh or manual sync.

        Args:
            db: Database session
            tenant_id: Tenant ID

        Returns:
            Number of monitors refreshed
        """
        # Get all monitors for tenant with triggers
        query = (
            select(Monitor)
            .options(selectinload(Monitor.triggers))
            .where(Monitor.tenant_id == tenant_id)
        )

        result = await db.execute(query)
        monitors = result.scalars().all()

        # Clear existing cache
        pattern = f"tenant:{tenant_id}:monitor:*"
        await RedisClient.delete_pattern(pattern)

        # Clear active monitors set
        active_key = f"tenant:{tenant_id}:monitors:active"
        await RedisClient.delete(active_key)

        # Re-cache all monitors
        count = 0
        for monitor in monitors:
            # Create denormalized structure
            monitor_dict = MonitorRead.model_validate(monitor).model_dump()
            monitor_dict["triggers"] = [
                TriggerRead.model_validate(trigger).model_dump()
                for trigger in monitor.triggers
            ]

            # Cache denormalized monitor
            await self._cache_monitor_denormalized(
                monitor_dict, tenant_id, str(monitor.id)
            )

            # Add to active list
            await self._add_to_active_monitors(tenant_id, str(monitor.id))
            count += 1

        logger.info(f"Refreshed {count} monitors for tenant {tenant_id}")
        return count
