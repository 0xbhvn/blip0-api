"""
Cache service for write-through caching with denormalization.
Optimized for oz-multi-tenant Rust monitor consumption.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.logger import logging
from ..core.redis_client import redis_client
from ..models.monitor import Monitor
from ..models.network import Network
from ..models.trigger import EmailTrigger, Trigger, WebhookTrigger

logger = logging.getLogger(__name__)

# Cache TTL settings (in seconds)
CACHE_TTL = {
    "monitor": 3600,  # 1 hour
    "network": 3600,  # 1 hour
    "trigger": 3600,  # 1 hour
    "tenant": 7200,   # 2 hours
    "active_list": 300,  # 5 minutes for lists
}

# Channel names for pub/sub
CHANNELS = {
    "config_update": "blip0:config:update",
    "monitor_update": "blip0:monitor:update",
    "network_update": "blip0:network:update",
    "trigger_update": "blip0:trigger:update",
    # Platform-wide channels
    "platform_update": "blip0:platform:update",
    # Tenant-specific channel pattern (use with tenant_id)
    "tenant_pattern": "blip0:tenant:{tenant_id}:update",
}


class CacheEventType(str, Enum):
    """Cache event types for pub/sub notifications."""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    INVALIDATE = "invalidate"


class CacheResourceType(str, Enum):
    """Resource types for cache events."""
    MONITOR = "monitor"
    NETWORK = "network"
    TRIGGER = "trigger"
    TENANT = "tenant"
    PLATFORM = "platform"


class CacheService:
    """Service for managing write-through cache with denormalization."""

    @staticmethod
    def _serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO format string."""
        return dt.isoformat() if dt else None

    @staticmethod
    def _serialize_uuid(uid: Optional[uuid.UUID]) -> Optional[str]:
        """Serialize UUID to string."""
        return str(uid) if uid else None

    @classmethod
    async def _publish_cache_event(
        cls,
        event_type: CacheEventType,
        resource_type: CacheResourceType,
        resource_id: str,
        tenant_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> bool:
        """Publish a cache event to the appropriate channel.

        Args:
            event_type: Type of cache event (create, update, delete, invalidate)
            resource_type: Type of resource affected
            resource_id: UUID of the resource
            tenant_id: UUID of the tenant (optional for platform resources)
            metadata: Additional event metadata

        Returns:
            True if published successfully
        """
        try:
            # Build event payload
            event = {
                "event_type": event_type.value,
                "resource_type": resource_type.value,
                "resource_id": resource_id,
                "timestamp": datetime.utcnow().isoformat(),
            }

            if tenant_id:
                event["tenant_id"] = tenant_id

            if metadata:
                event["metadata"] = metadata  # type: ignore[assignment]

            # Determine channel based on resource type
            if resource_type == CacheResourceType.PLATFORM:
                channel = CHANNELS["platform_update"]
            elif tenant_id:
                # Use tenant-specific channel for tenant resources
                channel = CHANNELS["tenant_pattern"].format(
                    tenant_id=tenant_id)
            else:
                # Fallback to resource-specific channel
                channel = CHANNELS.get(
                    f"{resource_type.value}_update", CHANNELS["config_update"])

            # Publish the event
            num_subscribers = await redis_client.publish(channel, event)

            if num_subscribers > 0:
                logger.debug(
                    f"Published {event_type.value} event for {resource_type.value} "
                    f"{resource_id} to channel {channel} ({num_subscribers} subscribers)"
                )

            return num_subscribers > 0

        except Exception as e:
            logger.error(f"Error publishing cache event: {e}")
            return False

    # ============== Monitor Caching ==============

    @classmethod
    async def cache_monitor(cls, db: AsyncSession, monitor: Monitor) -> bool:
        """Cache a monitor with denormalized trigger data.

        Args:
            db: Database session
            monitor: Monitor instance to cache

        Returns:
            True if cached successfully
        """
        try:
            tenant_id = str(monitor.tenant_id)
            monitor_id = str(monitor.id)

            # Fetch associated triggers with eager loading if trigger slugs are present
            triggers_data = []
            if monitor.triggers:
                # Fetch all triggers with their configs in a single query using eager loading
                stmt = (
                    select(Trigger)
                    .options(
                        selectinload(Trigger.email_config),
                        selectinload(Trigger.webhook_config)
                    )
                    .where(
                        Trigger.tenant_id == monitor.tenant_id,
                        Trigger.slug.in_(monitor.triggers)
                    )
                )
                result = await db.scalars(stmt)
                triggers = result.all()

                for trigger in triggers:
                    trigger_dict = cls._denormalize_trigger(trigger)

                    # Add type-specific config (already loaded via eager loading)
                    if trigger.trigger_type == "email" and trigger.email_config:
                        trigger_dict["email_config"] = cls._serialize_email_trigger(
                            trigger.email_config)
                    elif trigger.trigger_type == "webhook" and trigger.webhook_config:
                        trigger_dict["webhook_config"] = cls._serialize_webhook_trigger(
                            trigger.webhook_config)

                    triggers_data.append(trigger_dict)

            # Denormalize monitor data
            monitor_data = {
                "id": monitor_id,
                "tenant_id": tenant_id,
                "name": monitor.name,
                "slug": monitor.slug,
                "description": monitor.description,
                "active": monitor.active,
                "paused": monitor.paused,
                "validated": monitor.validated,
                "validation_errors": monitor.validation_errors,
                "networks": monitor.networks,
                "addresses": monitor.addresses,
                "match_functions": monitor.match_functions,
                "match_events": monitor.match_events,
                "match_transactions": monitor.match_transactions,
                "trigger_conditions": monitor.trigger_conditions,
                "triggers": triggers_data,  # Denormalized trigger objects
                "created_at": cls._serialize_datetime(monitor.created_at),
                "updated_at": cls._serialize_datetime(monitor.updated_at),
                "last_validated_at": cls._serialize_datetime(monitor.last_validated_at),
            }

            # Cache the monitor
            key = f"tenant:{tenant_id}:monitor:{monitor_id}"
            success = await redis_client.set(key, monitor_data, expiration=CACHE_TTL["monitor"])

            if success:
                # Update active monitors list if monitor is active
                if monitor.active and not monitor.paused:
                    await cls._add_to_active_monitors(tenant_id, monitor_id)
                else:
                    await cls._remove_from_active_monitors(tenant_id, monitor_id)

                # Publish update notification using centralized method
                await cls._publish_cache_event(
                    event_type=CacheEventType.UPDATE,
                    resource_type=CacheResourceType.MONITOR,
                    resource_id=monitor_id,
                    tenant_id=tenant_id,
                    metadata={
                        "active": monitor.active,
                        "paused": monitor.paused,
                        "validated": monitor.validated,
                        "name": monitor.name,
                        "slug": monitor.slug
                    }
                )

                logger.info(
                    f"Cached monitor {monitor_id} for tenant {tenant_id}")

            return success

        except Exception as e:
            logger.error(f"Error caching monitor {monitor.id}: {e}")
            return False

    @classmethod
    async def get_monitor(cls, tenant_id: str, monitor_id: str) -> Optional[dict[str, Any]]:
        """Get a cached monitor.

        Args:
            tenant_id: Tenant UUID
            monitor_id: Monitor UUID

        Returns:
            Monitor data or None if not found
        """
        key = f"tenant:{tenant_id}:monitor:{monitor_id}"
        return await redis_client.get(key)

    @classmethod
    async def delete_monitor(cls, tenant_id: str, monitor_id: str) -> bool:
        """Delete a monitor from cache.

        Args:
            tenant_id: Tenant UUID
            monitor_id: Monitor UUID

        Returns:
            True if deleted successfully
        """
        try:
            key = f"tenant:{tenant_id}:monitor:{monitor_id}"
            deleted = await redis_client.delete(key) > 0

            if deleted:
                # Remove from active list
                await cls._remove_from_active_monitors(tenant_id, monitor_id)

                # Publish deletion notification using centralized method
                await cls._publish_cache_event(
                    event_type=CacheEventType.DELETE,
                    resource_type=CacheResourceType.MONITOR,
                    resource_id=monitor_id,
                    tenant_id=tenant_id
                )

                logger.info(f"Deleted monitor {monitor_id} from cache")

            return deleted

        except Exception as e:
            logger.error(f"Error deleting monitor {monitor_id}: {e}")
            return False

    @classmethod
    async def _add_to_active_monitors(cls, tenant_id: str, monitor_id: str) -> None:
        """Add monitor to active monitors list."""
        key = f"tenant:{tenant_id}:monitors:active"
        await redis_client.sadd(key, monitor_id)
        await redis_client.expire(key, CACHE_TTL["active_list"])

    @classmethod
    async def _remove_from_active_monitors(cls, tenant_id: str, monitor_id: str) -> None:
        """Remove monitor from active monitors list."""
        key = f"tenant:{tenant_id}:monitors:active"
        await redis_client.srem(key, monitor_id)

    @classmethod
    async def get_active_monitors(cls, tenant_id: str) -> list[str]:
        """Get list of active monitor IDs for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            List of active monitor UUIDs
        """
        key = f"tenant:{tenant_id}:monitors:active"
        members = await redis_client.smembers(key)
        return list(members)

    # ============== Network Caching ==============

    @classmethod
    async def cache_network(cls, network: Network) -> bool:
        """Cache a network configuration.

        Args:
            network: Network instance to cache

        Returns:
            True if cached successfully
        """
        try:
            tenant_id = str(network.tenant_id)
            network_id = str(network.id)

            # Denormalize network data
            network_data = {
                "id": network_id,
                "tenant_id": tenant_id,
                "name": network.name,
                "slug": network.slug,
                "description": network.description,
                "network_type": network.network_type,
                "chain_id": network.chain_id,
                "network_passphrase": network.network_passphrase,
                "rpc_urls": network.rpc_urls,
                "block_time_ms": network.block_time_ms,
                "confirmation_blocks": network.confirmation_blocks,
                "cron_schedule": network.cron_schedule,
                "max_past_blocks": network.max_past_blocks,
                "store_blocks": network.store_blocks,
                "active": network.active,
                "validated": network.validated,
                "validation_errors": network.validation_errors,
                "created_at": cls._serialize_datetime(network.created_at),
                "updated_at": cls._serialize_datetime(network.updated_at),
                "last_validated_at": cls._serialize_datetime(network.last_validated_at),
            }

            # Cache with tenant-specific key
            tenant_key = f"tenant:{tenant_id}:network:{network_id}"

            # Also cache with platform key if it's a shared network
            # (This would be determined by some platform config logic)

            success = await redis_client.set(tenant_key, network_data, expiration=CACHE_TTL["network"])

            if success:
                # Optionally cache as platform network if shared
                # await redis_client.set(platform_key, network_data, expiration=CACHE_TTL["network"])

                # Publish update notification using centralized method
                await cls._publish_cache_event(
                    event_type=CacheEventType.UPDATE,
                    resource_type=CacheResourceType.NETWORK,
                    resource_id=network_id,
                    tenant_id=tenant_id,
                    metadata={
                        "name": network.name,
                        "slug": network.slug,
                        "network_type": network.network_type,
                        "chain_id": network.chain_id,
                        "active": network.active,
                        "validated": network.validated
                    }
                )

                logger.info(
                    f"Cached network {network_id} for tenant {tenant_id}")

            return success

        except Exception as e:
            logger.error(f"Error caching network {network.id}: {e}")
            return False

    @classmethod
    async def get_network(cls, tenant_id: str, network_id: str) -> Optional[dict[str, Any]]:
        """Get a cached network.

        Args:
            tenant_id: Tenant UUID
            network_id: Network UUID

        Returns:
            Network data or None if not found
        """
        key = f"tenant:{tenant_id}:network:{network_id}"
        return await redis_client.get(key)

    @classmethod
    async def delete_network(cls, tenant_id: str, network_id: str) -> bool:
        """Delete a network from cache.

        Args:
            tenant_id: Tenant UUID
            network_id: Network UUID

        Returns:
            True if deleted successfully
        """
        try:
            key = f"tenant:{tenant_id}:network:{network_id}"
            deleted = await redis_client.delete(key) > 0

            if deleted:
                # Publish deletion notification using centralized method
                await cls._publish_cache_event(
                    event_type=CacheEventType.DELETE,
                    resource_type=CacheResourceType.NETWORK,
                    resource_id=network_id,
                    tenant_id=tenant_id
                )

                logger.info(f"Deleted network {network_id} from cache")

            return deleted

        except Exception as e:
            logger.error(f"Error deleting network {network_id}: {e}")
            return False

    # ============== Trigger Caching ==============

    @classmethod
    def _denormalize_trigger(cls, trigger: Trigger) -> dict[str, Any]:
        """Denormalize trigger base data."""
        return {
            "id": cls._serialize_uuid(trigger.id),
            "tenant_id": cls._serialize_uuid(trigger.tenant_id),
            "name": trigger.name,
            "slug": trigger.slug,
            "description": trigger.description,
            "trigger_type": trigger.trigger_type,
            "active": trigger.active,
            "validated": trigger.validated,
            "validation_errors": trigger.validation_errors,
            "created_at": cls._serialize_datetime(trigger.created_at),
            "updated_at": cls._serialize_datetime(trigger.updated_at),
            "last_validated_at": cls._serialize_datetime(trigger.last_validated_at),
        }

    @classmethod
    def _serialize_email_trigger(cls, email: EmailTrigger) -> dict[str, Any]:
        """Serialize email trigger config."""
        return {
            "host": email.host,
            "port": email.port,
            "username_type": email.username_type,
            "username_value": email.username_value,
            "password_type": email.password_type,
            "password_value": email.password_value,
            "sender": email.sender,
            "recipients": email.recipients,
            "message_title": email.message_title,
            "message_body": email.message_body,
        }

    @classmethod
    def _serialize_webhook_trigger(cls, webhook: WebhookTrigger) -> dict[str, Any]:
        """Serialize webhook trigger config."""
        return {
            "url_type": webhook.url_type,
            "url_value": webhook.url_value,
            "method": webhook.method,
            "headers": webhook.headers,
            "secret_type": webhook.secret_type,
            "secret_value": webhook.secret_value,
            "message_title": webhook.message_title,
            "message_body": webhook.message_body,
        }

    @classmethod
    async def cache_trigger(cls, db: AsyncSession, trigger: Trigger) -> bool:
        """Cache a trigger configuration.

        Args:
            db: Database session
            trigger: Trigger instance to cache

        Returns:
            True if cached successfully
        """
        try:
            tenant_id = str(trigger.tenant_id)
            trigger_id = str(trigger.id)

            # Denormalize trigger data
            trigger_data = cls._denormalize_trigger(trigger)

            # Fetch type-specific config
            if trigger.trigger_type == "email":
                email_stmt = select(EmailTrigger).where(
                    EmailTrigger.trigger_id == trigger.id)
                email_config = await db.scalar(email_stmt)
                if email_config:
                    trigger_data["email_config"] = cls._serialize_email_trigger(
                        email_config)

            elif trigger.trigger_type == "webhook":
                webhook_stmt = select(WebhookTrigger).where(
                    WebhookTrigger.trigger_id == trigger.id)
                webhook_config = await db.scalar(webhook_stmt)
                if webhook_config:
                    trigger_data["webhook_config"] = cls._serialize_webhook_trigger(
                        webhook_config)

            # Cache the trigger
            key = f"tenant:{tenant_id}:trigger:{trigger_id}"
            success = await redis_client.set(key, trigger_data, expiration=CACHE_TTL["trigger"])

            if success:
                # Publish update notification using centralized method
                await cls._publish_cache_event(
                    event_type=CacheEventType.UPDATE,
                    resource_type=CacheResourceType.TRIGGER,
                    resource_id=trigger_id,
                    tenant_id=tenant_id,
                    metadata={
                        "name": trigger.name,
                        "slug": trigger.slug,
                        "trigger_type": trigger.trigger_type,
                        "active": trigger.active,
                        "validated": trigger.validated
                    }
                )

                logger.info(
                    f"Cached trigger {trigger_id} for tenant {tenant_id}")

            return success

        except Exception as e:
            logger.error(f"Error caching trigger {trigger.id}: {e}")
            return False

    @classmethod
    async def get_trigger(cls, tenant_id: str, trigger_id: str) -> Optional[dict[str, Any]]:
        """Get a cached trigger.

        Args:
            tenant_id: Tenant UUID
            trigger_id: Trigger UUID

        Returns:
            Trigger data or None if not found
        """
        key = f"tenant:{tenant_id}:trigger:{trigger_id}"
        return await redis_client.get(key)

    @classmethod
    async def delete_trigger(cls, tenant_id: str, trigger_id: str) -> bool:
        """Delete a trigger from cache.

        Args:
            tenant_id: Tenant UUID
            trigger_id: Trigger UUID

        Returns:
            True if deleted successfully
        """
        try:
            key = f"tenant:{tenant_id}:trigger:{trigger_id}"
            deleted = await redis_client.delete(key) > 0

            if deleted:
                # Publish deletion notification using centralized method
                await cls._publish_cache_event(
                    event_type=CacheEventType.DELETE,
                    resource_type=CacheResourceType.TRIGGER,
                    resource_id=trigger_id,
                    tenant_id=tenant_id
                )

                logger.info(f"Deleted trigger {trigger_id} from cache")

            return deleted

        except Exception as e:
            logger.error(f"Error deleting trigger {trigger_id}: {e}")
            return False

    # ============== Tenant Cache Invalidation ==============

    @classmethod
    async def invalidate_tenant_cache(cls, tenant_id: str) -> int:
        """Invalidate all cache entries for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            Number of keys deleted
        """
        try:
            pattern = f"tenant:{tenant_id}:*"
            deleted = await redis_client.delete_pattern(pattern)

            if deleted > 0:
                # Publish invalidation notification using centralized method
                await cls._publish_cache_event(
                    event_type=CacheEventType.INVALIDATE,
                    resource_type=CacheResourceType.TENANT,
                    resource_id=tenant_id,
                    tenant_id=tenant_id,
                    metadata={
                        "entries_deleted": deleted,
                        "action": "invalidate_all"
                    }
                )

                logger.info(
                    f"Invalidated {deleted} cache entries for tenant {tenant_id}")

            return deleted

        except Exception as e:
            logger.error(f"Error invalidating tenant {tenant_id} cache: {e}")
            return 0

    @classmethod
    async def get_tenant_cache_keys(cls, tenant_id: str) -> list[str]:
        """Get all cache keys for a tenant.

        Args:
            tenant_id: Tenant UUID

        Returns:
            List of cache keys
        """
        pattern = f"tenant:{tenant_id}:*"
        return await redis_client.keys_pattern(pattern)

    # ============== Bulk Operations ==============

    @classmethod
    async def cache_tenant_monitors(cls, db: AsyncSession, tenant_id: uuid.UUID) -> int:
        """Cache all monitors for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant UUID

        Returns:
            Number of monitors cached
        """
        try:
            stmt = select(Monitor).where(Monitor.tenant_id == tenant_id)
            result = await db.execute(stmt)
            monitors = result.scalars().all()

            cached_count = 0
            for monitor in monitors:
                if await cls.cache_monitor(db, monitor):
                    cached_count += 1

            logger.info(
                f"Cached {cached_count} monitors for tenant {tenant_id}")
            return cached_count

        except Exception as e:
            logger.error(f"Error caching tenant {tenant_id} monitors: {e}")
            return 0

    @classmethod
    async def cache_tenant_networks(cls, db: AsyncSession, tenant_id: uuid.UUID) -> int:
        """Cache all networks for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant UUID

        Returns:
            Number of networks cached
        """
        try:
            stmt = select(Network).where(Network.tenant_id == tenant_id)
            result = await db.execute(stmt)
            networks = result.scalars().all()

            cached_count = 0
            for network in networks:
                if await cls.cache_network(network):
                    cached_count += 1

            logger.info(
                f"Cached {cached_count} networks for tenant {tenant_id}")
            return cached_count

        except Exception as e:
            logger.error(f"Error caching tenant {tenant_id} networks: {e}")
            return 0

    @classmethod
    async def cache_tenant_triggers(cls, db: AsyncSession, tenant_id: uuid.UUID) -> int:
        """Cache all triggers for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant UUID

        Returns:
            Number of triggers cached
        """
        try:
            stmt = select(Trigger).where(Trigger.tenant_id == tenant_id)
            result = await db.execute(stmt)
            triggers = result.scalars().all()

            cached_count = 0
            for trigger in triggers:
                if await cls.cache_trigger(db, trigger):
                    cached_count += 1

            logger.info(
                f"Cached {cached_count} triggers for tenant {tenant_id}")
            return cached_count

        except Exception as e:
            logger.error(f"Error caching tenant {tenant_id} triggers: {e}")
            return 0


# Convenience instance
cache_service = CacheService()
