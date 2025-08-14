#!/usr/bin/env python
"""
Test script to verify Redis pub/sub integration in CacheService.
Run with: uv run python -m src.scripts.test_cache_pubsub
"""

import asyncio
import json

from sqlalchemy import select

from ..app.core.db.database import async_get_db
from ..app.core.logger import logging
from ..app.core.redis_client import redis_client
from ..app.models.monitor import Monitor
from ..app.models.network import Network
from ..app.models.trigger import Trigger
from ..app.services.cache_service import CHANNELS, cache_service

logger = logging.getLogger(__name__)


async def subscribe_to_events(tenant_ids=None):
    """Subscribe to cache events and print them."""
    logger.info("Starting event subscriber...")

    # Subscribe to all channels
    channels = [
        CHANNELS["config_update"],
        CHANNELS["monitor_update"],
        CHANNELS["network_update"],
        CHANNELS["trigger_update"],
        CHANNELS["platform_update"],
    ]

    # Add tenant-specific channels if provided
    if tenant_ids:
        for tenant_id in tenant_ids:
            tenant_channel = CHANNELS["tenant_pattern"].format(tenant_id=tenant_id)
            channels.append(tenant_channel)

    logger.info(f"Subscribing to channels: {channels}")

    # Use the pubsub context manager
    async with redis_client.pubsub() as pubsub:
        # Subscribe to all channels
        for channel in channels:
            await pubsub.subscribe(channel)

        logger.info("Subscriber ready. Waiting for events...")

        # Listen for messages
        try:
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    channel_name = message['channel'].decode('utf-8')
                    data = message['data']

                    # Parse JSON message
                    try:
                        if isinstance(data, bytes):
                            data = data.decode('utf-8')
                        event = json.loads(data) if isinstance(data, str) else data

                        logger.info(f"Event received on channel '{channel_name}':")
                        logger.info(f"  Event Type: {event.get('event_type')}")
                        logger.info(f"  Resource Type: {event.get('resource_type')}")
                        logger.info(f"  Resource ID: {event.get('resource_id')}")
                        logger.info(f"  Tenant ID: {event.get('tenant_id')}")
                        logger.info(f"  Timestamp: {event.get('timestamp')}")
                        if event.get('metadata'):
                            logger.info(f"  Metadata: {json.dumps(event.get('metadata'), indent=2)}")
                        logger.info("-" * 50)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse message: {data}")
        except asyncio.CancelledError:
            logger.info("Stopping subscriber...")
            raise


async def test_cache_operations():
    """Test various cache operations to trigger pub/sub events."""
    logger.info("Starting cache operation tests...")

    async for db in async_get_db():
        try:
            # Test 1: Cache a monitor
            logger.info("\n=== Test 1: Caching a monitor ===")
            stmt = select(Monitor).limit(1)
            monitor = await db.scalar(stmt)

            if monitor:
                success = await cache_service.cache_monitor(db, monitor)
                logger.info(f"Monitor cached: {success}")
                await asyncio.sleep(1)  # Give time for event to be received
            else:
                logger.warning("No monitor found for testing")

            # Test 2: Cache a network
            logger.info("\n=== Test 2: Caching a network ===")
            stmt = select(Network).limit(1)
            network = await db.scalar(stmt)

            if network:
                success = await cache_service.cache_network(network)
                logger.info(f"Network cached: {success}")
                await asyncio.sleep(1)
            else:
                logger.warning("No network found for testing")

            # Test 3: Cache a trigger
            logger.info("\n=== Test 3: Caching a trigger ===")
            stmt = select(Trigger).limit(1)
            trigger = await db.scalar(stmt)

            if trigger:
                success = await cache_service.cache_trigger(db, trigger)
                logger.info(f"Trigger cached: {success}")
                await asyncio.sleep(1)
            else:
                logger.warning("No trigger found for testing")

            # Test 4: Delete cached items
            if monitor:
                logger.info("\n=== Test 4: Deleting monitor from cache ===")
                success = await cache_service.delete_monitor(
                    str(monitor.tenant_id), str(monitor.id)
                )
                logger.info(f"Monitor deleted: {success}")
                await asyncio.sleep(1)

            if network:
                logger.info("\n=== Test 5: Deleting network from cache ===")
                success = await cache_service.delete_network(
                    str(network.tenant_id), str(network.id)
                )
                logger.info(f"Network deleted: {success}")
                await asyncio.sleep(1)

            # Test 5: Invalidate tenant cache (using monitor's tenant if available)
            if monitor:
                logger.info("\n=== Test 6: Invalidating tenant cache ===")
                deleted_count = await cache_service.invalidate_tenant_cache(str(monitor.tenant_id))
                logger.info(f"Tenant cache invalidated, {deleted_count} entries deleted")
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Error during testing: {e}")
        finally:
            await db.close()


async def main():
    """Main test function."""
    logger.info("Redis Pub/Sub Integration Test")
    logger.info("=" * 60)

    # Initialize Redis client with URL from environment
    import os

    from dotenv import load_dotenv
    load_dotenv("src/.env")

    redis_url = os.getenv("REDIS_URL", "redis://default:ozredispass@localhost:6380/0")
    await redis_client.initialize(redis_url)

    try:
        # First, get a monitor to find the tenant ID
        tenant_ids = []
        async for db in async_get_db():
            stmt = select(Monitor).limit(1)
            monitor = await db.scalar(stmt)
            tenant_ids = [str(monitor.tenant_id)] if monitor else []
            await db.close()
            break

        # Run subscriber in background with tenant channels
        subscriber_task = asyncio.create_task(subscribe_to_events(tenant_ids))

        # Give subscriber more time to connect and subscribe
        await asyncio.sleep(3)

        # Run cache operations to trigger events
        await test_cache_operations()

        # Keep running for a bit to see any remaining events
        logger.info("\nWaiting 5 seconds for any remaining events...")
        await asyncio.sleep(5)

        # Cancel subscriber
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass

    finally:
        # Clean up
        await redis_client.close()

    logger.info("\nTest completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
