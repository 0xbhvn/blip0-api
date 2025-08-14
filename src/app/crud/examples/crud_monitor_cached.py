"""
CRUD operations for Monitor with integrated caching.
Example of write-through caching integration.
"""

from typing import Optional
from uuid import UUID

from fastcrud import FastCRUD
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.monitor import Monitor
from ...schemas.examples.monitor_cached_example import (
    MonitorDelete,
    MonitorUpdateInternal,
)
from ...schemas.monitor import MonitorCreate, MonitorRead, MonitorUpdate
from ...services.cache_service import cache_service


class CRUDMonitorCached(
    FastCRUD[Monitor, MonitorCreate, MonitorUpdate,
             MonitorUpdateInternal, MonitorDelete, MonitorRead]
):
    """CRUD operations for Monitor with write-through caching."""

    async def create(
        self,
        db: AsyncSession,
        object: MonitorCreate,
        commit: bool = True
    ) -> Monitor:
        """Create a monitor and cache it.

        Args:
            db: Database session
            object: Monitor create schema
            commit: Whether to commit the transaction

        Returns:
            Created monitor instance
        """
        # Create in database
        monitor = await super().create(db=db, object=object, commit=commit)

        # Cache the created monitor (write-through)
        if isinstance(monitor, Monitor):
            await cache_service.cache_monitor(db, monitor)

        return monitor

    async def get_by_id(
        self,
        db: AsyncSession,
        id: UUID,
        tenant_id: Optional[UUID] = None
    ) -> Optional[Monitor]:
        """Get a monitor by ID, checking cache first.

        Args:
            db: Database session
            id: Monitor ID
            tenant_id: Optional tenant ID for cache lookup

        Returns:
            Monitor instance or None
        """
        # Try cache first if tenant_id provided
        if tenant_id:
            cached = await cache_service.get_monitor(str(tenant_id), str(id))
            if cached:
                # Note: In production, you'd deserialize this back to Monitor model
                # For now, we'll still fetch from DB but this shows the pattern
                pass

        # Fetch from database with relationships
        stmt = select(Monitor).where(Monitor.id == id)
        result = await db.execute(stmt)
        monitor = result.scalar_one_or_none()

        # Cache if found and tenant_id provided
        if monitor and tenant_id:
            await cache_service.cache_monitor(db, monitor)

        return monitor

    async def update_by_id(
        self,
        db: AsyncSession,
        id: UUID,
        obj_in: MonitorUpdate,
        commit: bool = True
    ) -> Optional[Monitor]:
        """Update a monitor by ID and refresh cache.

        Args:
            db: Database session
            id: Monitor ID
            obj_in: Update schema
            commit: Whether to commit the transaction

        Returns:
            Updated monitor instance or None
        """
        # Get the existing monitor
        stmt = select(Monitor).where(Monitor.id == id)
        result = await db.execute(stmt)
        monitor = result.scalar_one_or_none()

        if not monitor:
            return None

        # Update using FastCRUD's update method
        updated = await super().update(
            db=db,
            object=obj_in,
            id=id,
            commit=commit
        )

        # Fetch the updated monitor to get the full object
        if updated:
            stmt = select(Monitor).where(Monitor.id == id)
            result = await db.execute(stmt)
            monitor = result.scalar_one_or_none()

            # Update cache (write-through)
            if monitor:
                await cache_service.cache_monitor(db, monitor)

        return monitor

    async def delete_by_id(
        self,
        db: AsyncSession,
        id: UUID,
        commit: bool = True
    ) -> bool:
        """Delete a monitor by ID and remove from cache.

        Args:
            db: Database session
            id: Monitor ID
            commit: Whether to commit the transaction

        Returns:
            True if deleted, False otherwise
        """
        # Get the monitor first to get tenant_id
        stmt = select(Monitor).where(Monitor.id == id)
        result = await db.execute(stmt)
        monitor = result.scalar_one_or_none()

        if not monitor:
            return False

        tenant_id = str(monitor.tenant_id)
        monitor_id = str(monitor.id)

        # Delete from database
        await super().delete(db=db, id=id, commit=commit)

        # Remove from cache
        await cache_service.delete_monitor(tenant_id, monitor_id)

        return True

    async def get_active_by_tenant(
        self,
        db: AsyncSession,
        tenant_id: UUID
    ) -> list[Monitor]:
        """Get all active monitors for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID

        Returns:
            List of active monitors
        """
        # Get active monitor IDs from cache
        active_ids = await cache_service.get_active_monitors(str(tenant_id))

        if active_ids:
            # Fetch monitors by IDs with relationships
            stmt = select(Monitor).where(
                Monitor.id.in_([UUID(id) for id in active_ids])
            )
            result = await db.execute(stmt)
            return list(result.scalars().all())

        # Fallback to database query if cache miss
        stmt = select(Monitor).where(
            Monitor.tenant_id == tenant_id,
            Monitor.active.is_(True),
            Monitor.paused.is_(False)
        )
        result = await db.execute(stmt)
        monitors = list(result.scalars().all())

        # Cache the results
        for monitor in monitors:
            await cache_service.cache_monitor(db, monitor)

        return monitors


# Export instance
crud_monitor_cached = CRUDMonitorCached(Monitor)
