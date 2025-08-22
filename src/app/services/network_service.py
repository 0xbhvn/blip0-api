"""
Service layer for Network operations with Redis write-through caching.
Networks are platform-managed resources shared across tenants.
"""

import json
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import logging
from ..core.redis_client import redis_client
from ..crud.crud_network import CRUDNetwork, crud_network
from ..schemas.network import (
    NetworkCreate,
    NetworkCreateInternal,
    NetworkFilter,
    NetworkRead,
    NetworkSort,
    NetworkUpdate,
)

logger = logging.getLogger(__name__)


class NetworkService:
    """
    Service layer for Network operations.
    Handles platform-managed network configurations with Redis caching.
    """

    def __init__(self, crud_network: CRUDNetwork):
        """Initialize network service with CRUD dependency."""
        self.crud_network = crud_network

    async def create_network(
        self,
        db: AsyncSession,
        network_in: NetworkCreate,
    ) -> NetworkRead:
        """
        Create a new network with write-through caching.
        Networks are platform-managed resources.

        Args:
            db: Database session
            network_in: Network creation data

        Returns:
            Created network
        """
        # Create network in PostgreSQL (source of truth)
        network_internal = NetworkCreateInternal(**network_in.model_dump())

        db_network = await self.crud_network.create(
            db=db,
            object=network_internal
        )

        # Write-through to Redis for fast access by Rust monitor
        await self._cache_network(db_network)

        logger.info(f"Created platform network {db_network.slug}")
        return NetworkRead.model_validate(db_network)

    async def get_network(
        self,
        db: AsyncSession,
        network_id: str,
        use_cache: bool = True,
    ) -> Optional[NetworkRead]:
        """
        Get a network by ID with cache support.

        Args:
            db: Database session
            network_id: Network ID
            use_cache: Whether to try cache first

        Returns:
            Network if found
        """
        # Try cache first if enabled
        if use_cache:
            cached = await self._get_cached_network_by_id(network_id)
            if cached:
                logger.debug(f"Cache hit for network {network_id}")
                return cached

        # Fallback to database
        db_network = await self.crud_network.get(db=db, id=network_id)

        if not db_network:
            return None

        # Refresh cache on cache miss
        if use_cache:
            await self._cache_network(db_network)

        return NetworkRead.model_validate(db_network)

    async def get_network_by_slug(
        self,
        db: AsyncSession,
        slug: str,
        use_cache: bool = True,
    ) -> Optional[NetworkRead]:
        """
        Get a network by slug with cache support.
        Slug is the primary identifier used by Rust monitor.

        Args:
            db: Database session
            slug: Network slug
            use_cache: Whether to try cache first

        Returns:
            Network if found
        """
        # Try cache first if enabled
        if use_cache:
            cached = await self._get_cached_network_by_slug(slug)
            if cached:
                logger.debug(f"Cache hit for network slug {slug}")
                return cached

        # Fallback to database
        db_network = await self.crud_network.get_by_slug(db=db, slug=slug)

        if not db_network:
            return None

        # Refresh cache on cache miss
        if use_cache:
            await self._cache_network(db_network)

        return NetworkRead.model_validate(db_network)

    async def update_network(
        self,
        db: AsyncSession,
        network_id: str,
        network_update: NetworkUpdate,
    ) -> Optional[NetworkRead]:
        """
        Update a network with cache invalidation.

        Args:
            db: Database session
            network_id: Network ID
            network_update: Update data

        Returns:
            Updated network if found
        """
        # Get existing network to find slug for cache invalidation
        existing = await self.crud_network.get(db=db, id=network_id)
        if not existing:
            return None

        old_slug = str(existing.slug) if hasattr(existing, 'slug') else ""  # type: ignore[attr-defined]

        # Update in PostgreSQL
        db_network = await self.crud_network.update(
            db=db,
            object=network_update,
            id=network_id
        )

        if not db_network:
            return None

        # Invalidate old cache entries
        await self._invalidate_network_cache(old_slug, network_id)

        # Refresh cache with new data
        await self._cache_network(db_network)

        if hasattr(db_network, 'slug'):
            logger.info(f"Updated platform network {db_network.slug}")  # type: ignore[attr-defined]
        else:
            logger.info(f"Updated platform network {network_id}")
        return NetworkRead.model_validate(db_network)

    async def delete_network(
        self,
        db: AsyncSession,
        network_id: str,
        is_hard_delete: bool = False,
    ) -> bool:
        """
        Delete a network with cache cleanup.

        Args:
            db: Database session
            network_id: Network ID
            is_hard_delete: If True, permanently delete

        Returns:
            True if deleted successfully
        """
        # Get network for slug before deletion
        existing = await self.crud_network.get(db=db, id=network_id)
        if not existing:
            return False

        slug = str(existing.slug) if hasattr(existing, 'slug') else ""  # type: ignore[attr-defined]

        # Delete from PostgreSQL
        try:
            await self.crud_network.delete(
                db=db,
                id=network_id,
                is_hard_delete=is_hard_delete
            )
            deleted = True
        except Exception:
            deleted = False

        if deleted:
            # Remove from cache
            await self._invalidate_network_cache(slug, network_id)
            logger.info(f"Deleted platform network {slug}")

        return bool(deleted)

    async def list_networks(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 50,
        filters: Optional[NetworkFilter] = None,
        sort: Optional[NetworkSort] = None,
    ) -> dict[str, Any]:
        """
        List networks with pagination, filtering, and sorting.

        Args:
            db: Database session
            page: Page number
            size: Page size
            filters: Filter criteria
            sort: Sort criteria

        Returns:
            Paginated network list
        """
        result = await self.crud_network.get_paginated(
            db=db,
            page=page,
            size=size,
            filters=filters,
            sort=sort
        )

        # Convert models to schemas
        result["items"] = [
            NetworkRead.model_validate(item) for item in result["items"]
        ]

        return result

    # Redis caching helper methods
    async def _cache_network(self, network: Any) -> None:
        """
        Cache network in Redis with platform-managed key pattern.
        Uses both ID and slug for different access patterns.
        """
        try:
            # Cache by slug (primary access pattern for Rust monitor)
            slug_key = f"platform:networks:{network.slug}"
            network_dict = NetworkRead.model_validate(
                network).model_dump_json()

            # Cache for 1 hour (networks change infrequently)
            await redis_client.set(slug_key, network_dict, expiration=3600)

            # Also cache by ID for admin operations
            id_key = f"platform:network:id:{network.id}"
            await redis_client.set(id_key, network_dict, expiration=3600)

        except Exception as e:
            logger.error(f"Failed to cache network {network.slug}: {e}")

    async def _get_cached_network_by_slug(self, slug: str) -> Optional[NetworkRead]:
        """Get network from cache by slug."""
        try:
            key = f"platform:networks:{slug}"
            cached = await redis_client.get(key)

            if cached:
                if isinstance(cached, str):
                    cached = json.loads(cached)
                return NetworkRead.model_validate(cached)
            return None
        except Exception as e:
            logger.error(f"Failed to get cached network by slug {slug}: {e}")
            return None

    async def _get_cached_network_by_id(self, network_id: str) -> Optional[NetworkRead]:
        """Get network from cache by ID."""
        try:
            key = f"platform:network:id:{network_id}"
            cached = await redis_client.get(key)

            if cached:
                if isinstance(cached, str):
                    cached = json.loads(cached)
                return NetworkRead.model_validate(cached)
            return None
        except Exception as e:
            logger.error(
                f"Failed to get cached network by ID {network_id}: {e}")
            return None

    async def _invalidate_network_cache(self, slug: str, network_id: str) -> None:
        """Invalidate network cache entries."""
        try:
            slug_key = f"platform:networks:{slug}"
            id_key = f"platform:network:id:{network_id}"
            await redis_client.delete(slug_key, id_key)
        except Exception as e:
            logger.error(f"Failed to invalidate network cache {slug}: {e}")

    async def refresh_all_networks(self, db: AsyncSession) -> int:
        """
        Refresh all platform networks in Redis cache.
        Used for periodic cache refresh or manual sync.

        Args:
            db: Database session

        Returns:
            Number of networks refreshed
        """
        # Get all networks
        networks_result = await self.crud_network.get_multi(db=db)
        networks = networks_result.get("data", []) if isinstance(
            networks_result, dict) else []

        # Clear existing cache
        pattern = "platform:networks:*"
        await redis_client.delete_pattern(pattern)
        pattern = "platform:network:id:*"
        await redis_client.delete_pattern(pattern)

        # Re-cache all networks
        count = 0
        for network in networks:  # type: ignore[union-attr]
            await self._cache_network(network)
            count += 1

        logger.info(f"Refreshed {count} platform networks in cache")
        return count

    async def get_all_network_slugs(self, db: AsyncSession) -> list[str]:
        """
        Get all network slugs for quick lookups.

        Args:
            db: Database session

        Returns:
            List of network slugs
        """
        networks_result = await self.crud_network.get_multi(db=db)
        networks = networks_result.get("data", []) if isinstance(
            networks_result, dict) else []
        return [str(network.slug) for network in networks if hasattr(network, 'slug')]  # type: ignore[union-attr]


# Export service instance

network_service = NetworkService(crud_network)
