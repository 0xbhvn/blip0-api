"""
Redis pub/sub consumer for real-time configuration updates.
This demonstrates how oz-multi-tenant could subscribe to configuration changes.
"""

import asyncio
import json
from collections.abc import Callable
from typing import Any, Optional

from ..core.logger import logging
from ..core.redis_client import redis_client

logger = logging.getLogger(__name__)


class RedisConfigConsumer:
    """Consumer for Redis pub/sub configuration updates."""

    def __init__(self):
        self.handlers: dict[str, Callable] = {}
        self.running = False
        self._task: Optional[asyncio.Task] = None

    def register_handler(self, channel: str, handler: Callable) -> None:
        """Register a handler for a specific channel.

        Args:
            channel: Channel name
            handler: Async function to handle messages
        """
        self.handlers[channel] = handler
        logger.info(f"Registered handler for channel: {channel}")

    async def handle_config_update(self, message: dict[str, Any]) -> None:
        """Handle configuration update messages.

        Args:
            message: Update message with tenant_id, entity_id, action
        """
        tenant_id = message.get("tenant_id")
        action = message.get("action")

        if action == "update":
            entity_type = None
            entity_id = None

            if "monitor_id" in message:
                entity_type = "monitor"
                entity_id = message["monitor_id"]
            elif "network_id" in message:
                entity_type = "network"
                entity_id = message["network_id"]
            elif "trigger_id" in message:
                entity_type = "trigger"
                entity_id = message["trigger_id"]

            if entity_type and entity_id:
                logger.info(
                    f"Configuration updated - Tenant: {tenant_id}, "
                    f"{entity_type.capitalize()}: {entity_id}"
                )
                # In oz-multi-tenant, this would trigger a configuration reload
                # await self.reload_configuration(tenant_id, entity_type, entity_id)

        elif action == "delete":
            entity_type = None
            entity_id = None

            if "monitor_id" in message:
                entity_type = "monitor"
                entity_id = message["monitor_id"]
            elif "network_id" in message:
                entity_type = "network"
                entity_id = message["network_id"]
            elif "trigger_id" in message:
                entity_type = "trigger"
                entity_id = message["trigger_id"]

            if entity_type and entity_id:
                logger.info(
                    f"Configuration deleted - Tenant: {tenant_id}, "
                    f"{entity_type.capitalize()}: {entity_id}"
                )
                # In oz-multi-tenant, this would remove the configuration
                # await self.remove_configuration(tenant_id, entity_type, entity_id)

        elif action == "invalidate_all":
            logger.info(f"All configurations invalidated for tenant: {tenant_id}")
            # In oz-multi-tenant, this would trigger a full reload for the tenant
            # await self.reload_tenant_configuration(tenant_id)

    async def handle_monitor_update(self, message: dict[str, Any]) -> None:
        """Handle monitor-specific update messages.

        Args:
            message: Monitor update message
        """
        tenant_id = message.get("tenant_id")
        monitor_id = message.get("monitor_id")
        action = message.get("action")

        logger.info(
            f"Monitor {action} - Tenant: {tenant_id}, Monitor: {monitor_id}"
        )

        # In oz-multi-tenant, this would update the specific monitor
        # await self.update_monitor(tenant_id, monitor_id)

    async def handle_network_update(self, message: dict[str, Any]) -> None:
        """Handle network-specific update messages.

        Args:
            message: Network update message
        """
        tenant_id = message.get("tenant_id")
        network_id = message.get("network_id")
        action = message.get("action")

        logger.info(
            f"Network {action} - Tenant: {tenant_id}, Network: {network_id}"
        )

        # In oz-multi-tenant, this would update the specific network
        # await self.update_network(tenant_id, network_id)

    async def handle_trigger_update(self, message: dict[str, Any]) -> None:
        """Handle trigger-specific update messages.

        Args:
            message: Trigger update message
        """
        tenant_id = message.get("tenant_id")
        trigger_id = message.get("trigger_id")
        action = message.get("action")

        logger.info(
            f"Trigger {action} - Tenant: {tenant_id}, Trigger: {trigger_id}"
        )

        # In oz-multi-tenant, this would update the specific trigger
        # await self.update_trigger(tenant_id, trigger_id)

    async def _consumer_loop(self, channels: list[str]) -> None:
        """Main consumer loop for pub/sub messages.

        Args:
            channels: List of channels to subscribe to
        """
        try:
            async with redis_client.pubsub() as pubsub:
                # Subscribe to channels
                for channel in channels:
                    await pubsub.subscribe(channel)
                    logger.info(f"Subscribed to channel: {channel}")

                # Listen for messages
                while self.running:
                    try:
                        message = await asyncio.wait_for(
                            pubsub.get_message(ignore_subscribe_messages=True),
                            timeout=1.0
                        )

                        if message and message["type"] == "message":
                            channel = message["channel"].decode("utf-8")
                            data = message["data"]

                            # Decode message
                            try:
                                if isinstance(data, bytes):
                                    data = data.decode("utf-8")
                                payload = json.loads(data)
                            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                                logger.error(f"Failed to decode message: {e}")
                                continue

                            # Call registered handler
                            if channel in self.handlers:
                                try:
                                    await self.handlers[channel](payload)
                                except Exception as e:
                                    logger.error(
                                        f"Error in handler for channel {channel}: {e}"
                                    )
                            else:
                                logger.warning(f"No handler for channel: {channel}")

                    except TimeoutError:
                        # Timeout is normal, continue loop
                        continue
                    except Exception as e:
                        logger.error(f"Error in consumer loop: {e}")
                        await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Fatal error in consumer loop: {e}")
        finally:
            self.running = False
            logger.info("Consumer loop stopped")

    async def start(self, channels: Optional[list[str]] = None) -> None:
        """Start the consumer.

        Args:
            channels: List of channels to subscribe to (uses registered handlers if None)
        """
        if self.running:
            logger.warning("Consumer already running")
            return

        if channels is None:
            channels = list(self.handlers.keys())

        if not channels:
            logger.error("No channels to subscribe to")
            return

        self.running = True
        self._task = asyncio.create_task(self._consumer_loop(channels))
        logger.info("Consumer started")

    async def stop(self) -> None:
        """Stop the consumer."""
        if not self.running:
            logger.warning("Consumer not running")
            return

        self.running = False

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                logger.warning("Consumer stop timeout, cancelling task")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        logger.info("Consumer stopped")


# Example usage for oz-multi-tenant integration
async def example_oz_multi_tenant_consumer():
    """Example of how oz-multi-tenant would use the consumer."""

    consumer = RedisConfigConsumer()

    # Register handlers for different channels
    consumer.register_handler("blip0:config:update", consumer.handle_config_update)
    consumer.register_handler("blip0:monitor:update", consumer.handle_monitor_update)
    consumer.register_handler("blip0:network:update", consumer.handle_network_update)
    consumer.register_handler("blip0:trigger:update", consumer.handle_trigger_update)

    # Start consumer
    await consumer.start()

    try:
        # Keep running until interrupted
        while True:
            await asyncio.sleep(30)
            # In oz-multi-tenant, this could also trigger periodic cache refresh
            # await refresh_all_configurations()

    except KeyboardInterrupt:
        logger.info("Shutting down consumer...")
    finally:
        await consumer.stop()


if __name__ == "__main__":
    # This would be run by oz-multi-tenant as a separate process
    asyncio.run(example_oz_multi_tenant_consumer())
