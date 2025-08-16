"""
Service layer for Tenant operations with Redis write-through caching.
Manages multi-tenant isolation and configuration.
"""

import json
import uuid as uuid_pkg
from typing import Any, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import logging
from ..core.redis_client import RedisClient
from ..crud.crud_tenant import CRUDTenant
from ..schemas.tenant import (
    TenantCreate,
    TenantCreateInternal,
    TenantFilter,
    TenantRead,
    TenantSort,
    TenantUpdate,
)

logger = logging.getLogger(__name__)


class TenantService:
    """
    Service layer for Tenant operations.
    Handles tenant management with Redis caching for configuration access.
    """

    def __init__(self, crud_tenant: CRUDTenant):
        """Initialize tenant service with CRUD dependency."""
        self.crud_tenant = crud_tenant

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

        db_tenant = await self.crud_tenant.create(
            db=db,
            object=tenant_internal
        )

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
        db_tenant = await self.crud_tenant.update(
            db=db,
            object=tenant_update,
            id=tenant_id
        )

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
            await self.crud_tenant.delete(
                db=db,
                id=tenant_id,
                is_hard_delete=is_hard_delete
            )
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
        result = await self.crud_tenant.get_paginated(
            db=db,
            page=page,
            size=size,
            filters=filters,
            sort=sort
        )

        # Convert models to schemas
        result["items"] = [
            TenantRead.model_validate(item) for item in result["items"]
        ]

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
    async def _cache_tenant(self, tenant: Any) -> None:
        """Cache tenant configuration in Redis."""
        try:
            key = f"tenant:{tenant.id}:config"
            tenant_dict = TenantRead.model_validate(tenant).model_dump_json()

            # Cache for 1 hour (tenant config changes infrequently)
            await RedisClient.set(key, tenant_dict, expiration=3600)
        except Exception as e:
            logger.error(f"Failed to cache tenant {tenant.id}: {e}")

    async def _get_cached_tenant(self, tenant_id: str) -> Optional[TenantRead]:
        """Get tenant from cache."""
        try:
            key = f"tenant:{tenant_id}:config"
            cached = await RedisClient.get(key)

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
            await RedisClient.delete(key)
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
                count = await RedisClient.delete_pattern(pattern)
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
            monitor_ids = await RedisClient.smembers(monitor_key)
            stats["active_monitors"] = len(monitor_ids)
        except Exception:
            pass

        return stats
