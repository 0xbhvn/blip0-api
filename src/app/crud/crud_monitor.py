"""
Enhanced CRUD operations for monitor management with Redis caching.
"""

import json
from datetime import UTC, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.logger import logging
from ..core.redis_client import redis_client
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

logger = logging.getLogger(__name__)


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

    async def create_with_tenant(
        self,
        db: AsyncSession,
        obj_in: MonitorCreate,
        tenant_id: Any
    ) -> MonitorRead:
        """
        Create monitor with tenant isolation and Redis caching.

        Args:
            db: Database session
            obj_in: Monitor creation data
            tenant_id: Tenant ID for multi-tenancy

        Returns:
            Created monitor
        """
        # Create monitor with tenant_id
        monitor_data = obj_in.model_dump()
        monitor_data["tenant_id"] = tenant_id
        monitor_internal = MonitorCreateInternal(**monitor_data)

        db_monitor = await self.create(db=db, object=monitor_internal)

        # Write-through to Redis for fast access
        await self._cache_monitor(db_monitor, str(tenant_id))

        # Add to active monitors list for this tenant
        await self._add_to_active_monitors(str(tenant_id), str(db_monitor.id))

        logger.info(f"Created monitor {db_monitor.id} for tenant {tenant_id}")
        return MonitorRead.model_validate(db_monitor)

    async def update_with_tenant(
        self,
        db: AsyncSession,
        monitor_id: Any,
        obj_in: MonitorUpdate,
        tenant_id: Any
    ) -> Optional[MonitorRead]:
        """
        Update monitor with tenant isolation and refresh cache.

        Args:
            db: Database session
            monitor_id: Monitor ID
            obj_in: Update data
            tenant_id: Tenant ID for security

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
        await self._cache_monitor(monitor, str(tenant_id))

        return MonitorRead.model_validate(monitor)

    async def delete_with_tenant(
        self,
        db: AsyncSession,
        monitor_id: Any,
        tenant_id: Any,
        is_hard_delete: bool = False
    ) -> bool:
        """
        Delete monitor with tenant isolation and remove from cache.

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID for security
            is_hard_delete: Whether to hard delete

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
        await self._remove_from_cache(monitor_id, str(tenant_id))

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
        triggers_data: list[dict[str, Any]] = []
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

    async def get_by_slug(
        self,
        db: AsyncSession,
        slug: str,
        tenant_id: Any
    ) -> Optional[Monitor]:
        """
        Get monitor by slug within tenant context.

        Args:
            db: Database session
            slug: Monitor slug
            tenant_id: Tenant ID for multi-tenant isolation

        Returns:
            Monitor if found and authorized, None otherwise
        """
        query = select(Monitor).where(
            Monitor.slug == slug,
            Monitor.tenant_id == tenant_id
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

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
        from ..schemas.trigger import TriggerRead
        monitor_dict = MonitorRead.model_validate(db_monitor).model_dump()
        monitor_dict["triggers"] = [
            TriggerRead.model_validate(trigger).model_dump()
            for trigger in db_monitor.triggers
        ]

        # Cache the denormalized structure
        await self._cache_monitor_denormalized(monitor_dict, tenant_id, monitor_id)

        return monitor_dict

    async def pause_monitor(
        self,
        db: AsyncSession,
        monitor_id: Any,
        tenant_id: Any
    ) -> Optional[MonitorRead]:
        """
        Pause a monitor.

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID

        Returns:
            Updated monitor or None
        """
        update_data = MonitorUpdate(
            name=None,
            slug=None,
            paused=True
        )
        return await self.update_with_tenant(
            db,
            monitor_id,
            update_data,
            tenant_id
        )

    async def resume_monitor(
        self,
        db: AsyncSession,
        monitor_id: Any,
        tenant_id: Any
    ) -> Optional[MonitorRead]:
        """
        Resume a paused monitor.

        Args:
            db: Database session
            monitor_id: Monitor ID
            tenant_id: Tenant ID

        Returns:
            Updated monitor or None
        """
        update_data = MonitorUpdate(
            name=None,
            slug=None,
            paused=False
        )
        return await self.update_with_tenant(
            db,
            monitor_id,
            update_data,
            tenant_id
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

        return await self.create_with_tenant(
            db,
            MonitorCreate(**clone_data),
            tenant_id
        )

    # Private helper methods

    async def _add_to_active_monitors(self, tenant_id: str, monitor_id: str) -> None:
        """Add monitor to active monitors list for tenant."""
        try:
            active_key = f"tenant:{tenant_id}:monitors:active"
            await redis_client.sadd(active_key, monitor_id)
        except Exception as e:
            logger.error(f"Failed to add monitor {monitor_id} to active list: {e}")

    async def _cache_monitor_denormalized(
        self,
        monitor_dict: dict,
        tenant_id: str,
        monitor_id: str,
    ) -> None:
        """Cache denormalized monitor structure."""
        try:
            key = f"tenant:{tenant_id}:monitor:{monitor_id}"
            await redis_client.set(key, json.dumps(monitor_dict, default=str), expiration=1800)
        except Exception as e:
            logger.error(f"Failed to cache denormalized monitor {monitor_id}: {e}")

    async def _cache_monitor(
        self,
        monitor: Monitor,
        tenant_id: str
    ) -> None:
        """
        Cache monitor to Redis.

        Args:
            monitor: Monitor to cache
            tenant_id: Tenant ID
        """
        try:
            key = f"tenant:{tenant_id}:monitor:{monitor.id}"
            monitor_dict = MonitorRead.model_validate(monitor).model_dump_json()

            # Cache for 30 minutes (Rust monitor refreshes every 30 seconds)
            await redis_client.set(key, monitor_dict, expiration=1800)

            # Update active monitors list
            active_key = f"tenant:{tenant_id}:monitors:active"
            if monitor.active and not monitor.paused:
                await redis_client.sadd(active_key, str(monitor.id))
            else:
                await redis_client.srem(active_key, str(monitor.id))
        except Exception as e:
            logger.error(f"Failed to cache monitor {monitor.id}: {e}")

    async def _remove_from_cache(
        self,
        monitor_id: str,
        tenant_id: str
    ) -> None:
        """
        Remove monitor from Redis cache.

        Args:
            monitor_id: Monitor ID
            tenant_id: Tenant ID
        """
        try:
            tenant_key = f"tenant:{tenant_id}:monitor:{monitor_id}"
            active_key = f"tenant:{tenant_id}:monitors:active"

            await redis_client.delete(tenant_key)
            await redis_client.srem(active_key, str(monitor_id))
        except Exception as e:
            logger.error(f"Failed to remove monitor {monitor_id} from cache: {e}")


# Export crud instance
crud_monitor = CRUDMonitor(Monitor)
