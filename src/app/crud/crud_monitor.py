"""
Enhanced CRUD operations for monitor management with Redis caching.
"""

import json
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.monitor import Monitor
from ..schemas.monitor import (
    MonitorCached,
    MonitorCreate,
    MonitorCreateInternal,
    MonitorDelete,
    MonitorFilter,
    MonitorRead,
    MonitorSort,
    MonitorUpdate,
    MonitorUpdateInternal,
    MonitorValidationRequest,
    MonitorValidationResult,
)
from .base import EnhancedCRUD


class CRUDMonitor(
    EnhancedCRUD[
        Monitor,
        MonitorCreateInternal,
        MonitorUpdate,
        MonitorUpdateInternal,
        MonitorDelete,
        MonitorRead,
        MonitorFilter,
        MonitorSort
    ]
):
    """
    Enhanced CRUD operations for Monitor model with Redis caching.
    Implements denormalized caching for high-performance reads by Rust monitor.
    """

    async def create_with_cache(
        self,
        db: AsyncSession,
        obj_in: MonitorCreate,
        redis_client: Optional[Any] = None
    ) -> MonitorRead:
        """
        Create monitor and cache in Redis for fast access.

        Args:
            db: Database session
            obj_in: Monitor creation data
            redis_client: Redis client for caching

        Returns:
            Created monitor
        """
        # Create monitor
        monitor_data = MonitorCreateInternal(**obj_in.model_dump())
        monitor = Monitor(**monitor_data.model_dump())
        db.add(monitor)
        await db.flush()
        await db.refresh(monitor)

        # Cache to Redis if available
        if redis_client:
            await self._cache_monitor(redis_client, monitor, obj_in.tenant_id)

        return MonitorRead.model_validate(monitor)

    async def update_with_cache(
        self,
        db: AsyncSession,
        monitor_id: Any,
        obj_in: MonitorUpdate,
        tenant_id: Any,
        redis_client: Optional[Any] = None
    ) -> Optional[MonitorRead]:
        """
        Update monitor and refresh cache.

        Args:
            db: Database session
            monitor_id: Monitor ID
            obj_in: Update data
            tenant_id: Tenant ID for security
            redis_client: Redis client for caching

        Returns:
            Updated monitor or None
        """
        query = select(Monitor).where(
            Monitor.id == monitor_id,
            Monitor.tenant_id == tenant_id
        )
        result = await db.execute(query)
        monitor = result.scalar_one_or_none()

        if not monitor:
            return None

        update_dict = obj_in.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(monitor, key, value)

        monitor.updated_at = datetime.now(UTC)
        await db.flush()
        await db.refresh(monitor)

        # Update cache
        if redis_client:
            await self._cache_monitor(redis_client, monitor, tenant_id)

        return MonitorRead.model_validate(monitor)

    async def delete_with_cache(
        self,
        db: AsyncSession,
        monitor_id: Any,
        tenant_id: Any,
        is_hard_delete: bool = False,
        redis_client: Optional[Any] = None
    ) -> bool:
        """
        Delete monitor and remove from cache.

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID for security
            is_hard_delete: Whether to hard delete
            redis_client: Redis client for caching

        Returns:
            True if deleted, False otherwise
        """
        query = select(Monitor).where(
            Monitor.id == monitor_id,
            Monitor.tenant_id == tenant_id
        )
        result = await db.execute(query)
        monitor = result.scalar_one_or_none()

        if not monitor:
            return False

        if is_hard_delete:
            await db.delete(monitor)
        else:
            monitor.active = False
            monitor.updated_at = datetime.now(UTC)

        await db.flush()

        # Remove from cache
        if redis_client:
            await self._remove_from_cache(redis_client, monitor_id, tenant_id)

        return True

    async def get_denormalized(
        self,
        db: AsyncSession,
        monitor_id: Any,
        tenant_id: Any
    ) -> Optional[MonitorCached]:
        """
        Get monitor with denormalized trigger data for caching.

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID

        Returns:
            Monitor with denormalized data
        """
        # Get monitor with triggers relationship
        query = (
            select(Monitor)
            .where(
                Monitor.id == monitor_id,
                Monitor.tenant_id == tenant_id
            )
        )  # Note: trigger_instances relationship would need to be defined in the model
        result = await db.execute(query)
        monitor = result.scalar_one_or_none()

        if not monitor:
            return None

        # Build denormalized structure
        monitor_dict = MonitorRead.model_validate(monitor).model_dump()

        # Add denormalized trigger data
        triggers_data = []
        # Note: This would need the relationship to be defined in the model
        # For now, we'll just return empty triggers_data
        if False:  # hasattr(monitor, 'trigger_instances'):
            for trigger in []:
                trigger_data = {
                    "id": str(trigger.id),
                    "name": trigger.name,
                    "slug": trigger.slug,
                    "trigger_type": trigger.trigger_type,
                    "active": trigger.active,
                    "validated": trigger.validated,
                }

                # Include email or webhook config based on type
                if trigger.trigger_type == "email" and hasattr(trigger, 'email_config'):
                    trigger_data["email_config"] = trigger.email_config
                elif trigger.trigger_type == "webhook" and hasattr(trigger, 'webhook_config'):
                    trigger_data["webhook_config"] = trigger.webhook_config

                triggers_data.append(trigger_data)

        monitor_dict["triggers_data"] = triggers_data
        return MonitorCached(**monitor_dict)

    async def validate_monitor(
        self,
        db: AsyncSession,
        validation_request: MonitorValidationRequest
    ) -> MonitorValidationResult:
        """
        Validate monitor configuration.

        Args:
            db: Database session
            validation_request: Validation request

        Returns:
            Validation result
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Get monitor
        query = select(Monitor).where(
            Monitor.id == validation_request.monitor_id)
        result = await db.execute(query)
        monitor = result.scalar_one_or_none()

        if not monitor:
            errors.append("Monitor not found")
            return MonitorValidationResult(
                monitor_id=validation_request.monitor_id,
                is_valid=False,
                errors=errors,
                warnings=warnings
            )

        # Validate networks exist
        if not monitor.networks:
            errors.append("Monitor must have at least one network")

        # Validate has matching criteria
        if (not monitor.match_functions and
            not monitor.match_events and
                not monitor.match_transactions):
            warnings.append("Monitor has no matching criteria defined")

        # Validate triggers if requested
        if validation_request.validate_triggers:
            if not monitor.triggers:
                warnings.append("Monitor has no triggers configured")

        # Validate addresses format
        for addr in monitor.addresses:
            if not isinstance(addr, dict) or "address" not in addr:
                errors.append(f"Invalid address format: {addr}")

        # Update validation status
        monitor.validated = len(errors) == 0
        monitor.validation_errors = {"errors": errors, "warnings": warnings}
        monitor.last_validated_at = datetime.now(UTC)

        await db.flush()

        return MonitorValidationResult(
            monitor_id=validation_request.monitor_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def pause_monitor(
        self,
        db: AsyncSession,
        monitor_id: Any,
        tenant_id: Any,
        redis_client: Optional[Any] = None
    ) -> Optional[MonitorRead]:
        """
        Pause a monitor.

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID
            redis_client: Redis client

        Returns:
            Updated monitor or None
        """
        update_data = MonitorUpdate()
        update_data.paused = True
        return await self.update_with_cache(
            db,
            monitor_id,
            update_data,
            tenant_id,
            redis_client
        )

    async def resume_monitor(
        self,
        db: AsyncSession,
        monitor_id: Any,
        tenant_id: Any,
        redis_client: Optional[Any] = None
    ) -> Optional[MonitorRead]:
        """
        Resume a paused monitor.

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID
            redis_client: Redis client

        Returns:
            Updated monitor or None
        """
        update_data = MonitorUpdate()
        update_data.paused = False
        return await self.update_with_cache(
            db,
            monitor_id,
            update_data,
            tenant_id,
            redis_client
        )

    async def get_active_monitors_by_network(
        self,
        db: AsyncSession,
        network_slug: str,
        tenant_id: Optional[Any] = None
    ) -> list[MonitorRead]:
        """
        Get all active monitors for a specific network.

        Args:
            db: Database session
            network_slug: Network slug
            tenant_id: Optional tenant filter

        Returns:
            List of active monitors
        """
        query = select(Monitor).where(
            Monitor.active == True,  # noqa: E712
            Monitor.paused == False,  # noqa: E712
            Monitor.networks.contains([network_slug])
        )

        if tenant_id:
            query = query.where(Monitor.tenant_id == tenant_id)

        result = await db.execute(query)
        monitors = result.scalars().all()

        return [MonitorRead.model_validate(m) for m in monitors]

    async def clone_monitor(
        self,
        db: AsyncSession,
        monitor_id: Any,
        tenant_id: Any,
        new_name: str,
        new_slug: str
    ) -> Optional[MonitorRead]:
        """
        Clone an existing monitor with a new name.

        Args:
            db: Database session
            monitor_id: Source monitor ID
            tenant_id: Tenant ID
            new_name: New monitor name
            new_slug: New monitor slug

        Returns:
            Cloned monitor or None
        """
        # Get source monitor
        query = select(Monitor).where(
            Monitor.id == monitor_id,
            Monitor.tenant_id == tenant_id
        )
        result = await db.execute(query)
        source = result.scalar_one_or_none()

        if not source:
            return None

        # Create clone
        clone_data = {
            "tenant_id": tenant_id,
            "name": new_name,
            "slug": new_slug,
            "description": f"Cloned from {source.name}",
            "paused": True,  # Start paused
            "networks": source.networks,
            "addresses": source.addresses,
            "match_functions": source.match_functions,
            "match_events": source.match_events,
            "match_transactions": source.match_transactions,
            "trigger_conditions": source.trigger_conditions,
            "triggers": source.triggers,
        }

        return await self.create_with_cache(
            db,
            MonitorCreate(**clone_data),
            None
        )

    # Private helper methods

    async def _cache_monitor(
        self,
        redis_client: Any,
        monitor: Monitor,
        tenant_id: Any
    ) -> None:
        """
        Cache monitor to Redis with denormalized data.

        Args:
            redis_client: Redis client
            monitor: Monitor to cache
            tenant_id: Tenant ID
        """
        # Get denormalized data only if we have a valid db session
        if hasattr(redis_client, 'db') and redis_client.db:
            monitor_cached = await self.get_denormalized(
                redis_client.db,
                monitor.id,
                tenant_id
            )
        else:
            # Fallback to basic monitor read if no db available
            monitor_cached = MonitorCached(**MonitorRead.model_validate(monitor).model_dump(), triggers_data=[])

        if monitor_cached:
            # Cache keys following the schema design
            tenant_key = f"tenant:{tenant_id}:monitor:{monitor.id}"
            active_key = f"tenant:{tenant_id}:monitors:active"

            # Store monitor data
            await redis_client.set(
                tenant_key,
                json.dumps(monitor_cached.model_dump(), default=str),
                ex=1800  # 30 minute TTL
            )

            # Add to active list if active
            if monitor.active and not monitor.paused:
                await redis_client.sadd(active_key, str(monitor.id))
            else:
                await redis_client.srem(active_key, str(monitor.id))

    async def _remove_from_cache(
        self,
        redis_client: Any,
        monitor_id: Any,
        tenant_id: Any
    ) -> None:
        """
        Remove monitor from Redis cache.

        Args:
            redis_client: Redis client
            monitor_id: Monitor ID
            tenant_id: Tenant ID
        """
        tenant_key = f"tenant:{tenant_id}:monitor:{monitor_id}"
        active_key = f"tenant:{tenant_id}:monitors:active"

        await redis_client.delete(tenant_key)
        await redis_client.srem(active_key, str(monitor_id))


# Export crud instance
crud_monitor = CRUDMonitor(Monitor)
