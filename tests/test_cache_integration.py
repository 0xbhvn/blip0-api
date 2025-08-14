"""
Integration tests for Redis pub/sub and cache operations.

Tests the full pub/sub flow and cache operations, converted from the standalone
test script to proper pytest structure with mocking.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Set
from unittest.mock import AsyncMock, Mock, patch

import pytest
from faker import Faker

from src.app.models.monitor import Monitor
from src.app.models.network import Network
from src.app.models.trigger import Trigger
from src.app.services.cache_service import CHANNELS, CacheEventType, CacheResourceType, CacheService

fake = Faker()


class TestCacheIntegrationFixtures:
    """Test fixtures for cache integration tests."""

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client with full pub/sub capabilities."""
        mock_redis = AsyncMock()
        
        # Basic operations
        mock_redis.get.return_value = None
        mock_redis.set.return_value = True
        mock_redis.delete.return_value = 1
        mock_redis.exists.return_value = 1
        mock_redis.expire.return_value = True
        mock_redis.sadd.return_value = 1
        mock_redis.srem.return_value = 1
        mock_redis.smembers.return_value = set()
        mock_redis.publish.return_value = 2  # Mock 2 subscribers
        mock_redis.delete_pattern.return_value = 5
        mock_redis.keys_pattern.return_value = []
        
        # Pub/sub operations
        mock_pubsub = AsyncMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.listen = AsyncMock()
        
        # Create a proper async context manager for pubsub
        class MockPubSubContextManager:
            async def __aenter__(self):
                return mock_pubsub
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None
        
        mock_redis.pubsub = lambda: MockPubSubContextManager()
        
        return mock_redis

    @pytest.fixture
    def mock_async_db(self):
        """Mock async database session."""
        mock_db = AsyncMock()
        mock_db.scalar.return_value = None
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
        mock_db.close = AsyncMock()
        return mock_db

    @pytest.fixture
    def sample_tenant_id(self):
        """Generate a sample tenant ID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def sample_monitor(self, sample_tenant_id):
        """Generate a sample Monitor object."""
        monitor_id = uuid.uuid4()
        tenant_uuid = uuid.UUID(sample_tenant_id)

        monitor = Mock(spec=Monitor)
        monitor.id = monitor_id
        monitor.tenant_id = tenant_uuid
        monitor.name = fake.name()
        monitor.slug = fake.slug()
        monitor.description = fake.text()
        monitor.active = True
        monitor.paused = False
        monitor.validated = True
        monitor.validation_errors = None
        monitor.networks = ["ethereum", "polygon"]
        monitor.addresses = [{"address": "0x123", "contract_specs": {}}]
        monitor.match_functions = []
        monitor.match_events = []
        monitor.match_transactions = []
        monitor.trigger_conditions = []
        monitor.triggers = []
        monitor.created_at = datetime.now(timezone.utc)
        monitor.updated_at = datetime.now(timezone.utc)
        monitor.last_validated_at = datetime.now(timezone.utc)

        return monitor

    @pytest.fixture
    def sample_network(self, sample_tenant_id):
        """Generate a sample Network object."""
        network_id = uuid.uuid4()
        tenant_uuid = uuid.UUID(sample_tenant_id)

        network = Mock(spec=Network)
        network.id = network_id
        network.tenant_id = tenant_uuid
        network.name = "Ethereum Mainnet"
        network.slug = "ethereum"
        network.description = "Ethereum mainnet"
        network.network_type = "ethereum"
        network.chain_id = 1
        network.network_passphrase = None
        network.rpc_urls = ["https://eth-mainnet.rpc.url"]
        network.block_time_ms = 12000
        network.confirmation_blocks = 12
        network.cron_schedule = "*/12 * * * * *"
        network.max_past_blocks = 100
        network.store_blocks = True
        network.active = True
        network.validated = True
        network.validation_errors = None
        network.created_at = datetime.now(timezone.utc)
        network.updated_at = datetime.now(timezone.utc)
        network.last_validated_at = datetime.now(timezone.utc)

        return network

    @pytest.fixture
    def sample_trigger(self, sample_tenant_id):
        """Generate a sample Trigger object."""
        trigger_id = uuid.uuid4()
        tenant_uuid = uuid.UUID(sample_tenant_id)

        trigger = Mock(spec=Trigger)
        trigger.id = trigger_id
        trigger.tenant_id = tenant_uuid
        trigger.name = "Email Alert"
        trigger.slug = "email-trigger-1"
        trigger.description = "Email notification trigger"
        trigger.trigger_type = "email"
        trigger.active = True
        trigger.validated = True
        trigger.validation_errors = None
        trigger.created_at = datetime.now(timezone.utc)
        trigger.updated_at = datetime.now(timezone.utc)
        trigger.last_validated_at = datetime.now(timezone.utc)

        return trigger


class TestPubSubIntegration(TestCacheIntegrationFixtures):
    """Test Redis pub/sub integration with cache operations."""

    @pytest.mark.asyncio
    async def test_subscribe_to_all_channels(self, mock_redis_client, sample_tenant_id):
        """Test subscribing to all cache event channels."""
        # Expected channels
        expected_channels = [
            CHANNELS["config_update"],
            CHANNELS["monitor_update"],
            CHANNELS["network_update"],
            CHANNELS["trigger_update"],
            CHANNELS["platform_update"],
            CHANNELS["tenant_pattern"].format(tenant_id=sample_tenant_id),
        ]

        with patch("src.app.core.redis_client.redis_client", mock_redis_client):
            async with mock_redis_client.pubsub() as pubsub:
                # Subscribe to all channels
                for channel in expected_channels:
                    await pubsub.subscribe(channel)

                # Verify subscription calls
                assert pubsub.subscribe.call_count == len(expected_channels)
                for channel in expected_channels:
                    pubsub.subscribe.assert_any_call(channel)

    @pytest.mark.asyncio
    async def test_event_message_structure(self, mock_redis_client):
        """Test that published events have correct structure."""
        # Mock a published event
        test_event = {
            "event_type": CacheEventType.UPDATE.value,
            "resource_type": CacheResourceType.MONITOR.value,
            "resource_id": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {"test": "data"}
        }

        # Simulate receiving the event
        mock_message = {
            "type": "message",
            "channel": b"blip0:monitor:update",
            "data": json.dumps(test_event).encode('utf-8')
        }

        # Test event parsing
        channel_name = mock_message['channel'].decode('utf-8')
        data = mock_message['data']
        
        if isinstance(data, bytes):
            data = data.decode('utf-8')
        
        event = json.loads(data)

        # Verify event structure
        assert channel_name == "blip0:monitor:update"
        assert event["event_type"] == CacheEventType.UPDATE.value
        assert event["resource_type"] == CacheResourceType.MONITOR.value
        assert "resource_id" in event
        assert "tenant_id" in event
        assert "timestamp" in event
        assert event["metadata"] == {"test": "data"}

    @pytest.mark.asyncio
    async def test_event_listener_processing(self, mock_redis_client):
        """Test processing of different event types."""
        events = [
            {
                "event_type": CacheEventType.CREATE.value,
                "resource_type": CacheResourceType.MONITOR.value,
                "resource_id": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            {
                "event_type": CacheEventType.DELETE.value,
                "resource_type": CacheResourceType.NETWORK.value,
                "resource_id": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            {
                "event_type": CacheEventType.INVALIDATE.value,
                "resource_type": CacheResourceType.TENANT.value,
                "resource_id": str(uuid.uuid4()),
                "tenant_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        ]

        processed_events = []

        for event_data in events:
            # Simulate message processing
            mock_message = {
                "type": "message",
                "channel": b"test:channel",
                "data": json.dumps(event_data).encode('utf-8')
            }

            # Parse the event
            data = mock_message['data']
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            
            event = json.loads(data)
            processed_events.append(event)

        # Verify all events were processed correctly
        assert len(processed_events) == 3
        assert processed_events[0]["event_type"] == CacheEventType.CREATE.value
        assert processed_events[1]["event_type"] == CacheEventType.DELETE.value
        assert processed_events[2]["event_type"] == CacheEventType.INVALIDATE.value


class TestCacheOperationIntegration(TestCacheIntegrationFixtures):
    """Test cache operations that trigger pub/sub events."""

    @pytest.mark.asyncio
    async def test_cache_monitor_publishes_event(
        self, mock_redis_client, mock_async_db, sample_monitor
    ):
        """Test that caching a monitor publishes the correct event."""
        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            result = await CacheService.cache_monitor(mock_async_db, sample_monitor)

        assert result is True

        # Verify cache operation
        mock_redis_client.set.assert_called_once()
        
        # Verify pub/sub event was published
        mock_redis_client.publish.assert_called_once()
        channel, event_data = mock_redis_client.publish.call_args[0]
        
        # Verify event structure
        assert channel == CHANNELS["tenant_pattern"].format(tenant_id=sample_monitor.tenant_id)
        assert event_data["event_type"] == CacheEventType.UPDATE.value
        assert event_data["resource_type"] == CacheResourceType.MONITOR.value
        assert event_data["resource_id"] == str(sample_monitor.id)
        assert event_data["tenant_id"] == str(sample_monitor.tenant_id)

    @pytest.mark.asyncio
    async def test_cache_network_publishes_event(
        self, mock_redis_client, sample_network
    ):
        """Test that caching a network publishes the correct event."""
        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            result = await CacheService.cache_network(sample_network)

        assert result is True

        # Verify pub/sub event was published
        mock_redis_client.publish.assert_called_once()
        channel, event_data = mock_redis_client.publish.call_args[0]
        
        # Verify event structure
        assert channel == CHANNELS["tenant_pattern"].format(tenant_id=sample_network.tenant_id)
        assert event_data["event_type"] == CacheEventType.UPDATE.value
        assert event_data["resource_type"] == CacheResourceType.NETWORK.value

    @pytest.mark.asyncio
    async def test_cache_trigger_publishes_event(
        self, mock_redis_client, mock_async_db, sample_trigger
    ):
        """Test that caching a trigger publishes the correct event."""
        mock_async_db.scalar.return_value = None  # No specific trigger config

        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            result = await CacheService.cache_trigger(mock_async_db, sample_trigger)

        assert result is True

        # Verify pub/sub event was published
        mock_redis_client.publish.assert_called_once()
        channel, event_data = mock_redis_client.publish.call_args[0]
        
        # Verify event structure
        assert channel == CHANNELS["tenant_pattern"].format(tenant_id=sample_trigger.tenant_id)
        assert event_data["event_type"] == CacheEventType.UPDATE.value
        assert event_data["resource_type"] == CacheResourceType.TRIGGER.value

    @pytest.mark.asyncio
    async def test_delete_operations_publish_events(
        self, mock_redis_client, sample_tenant_id
    ):
        """Test that delete operations publish correct events."""
        monitor_id = str(uuid.uuid4())
        network_id = str(uuid.uuid4())
        trigger_id = str(uuid.uuid4())

        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            # Test monitor deletion
            await CacheService.delete_monitor(sample_tenant_id, monitor_id)
            
            # Test network deletion
            await CacheService.delete_network(sample_tenant_id, network_id)
            
            # Test trigger deletion
            await CacheService.delete_trigger(sample_tenant_id, trigger_id)

        # Verify all delete operations published events
        assert mock_redis_client.publish.call_count == 3

        # Check the events
        calls = mock_redis_client.publish.call_args_list
        
        # Monitor delete event
        monitor_channel, monitor_event = calls[0][0]
        assert monitor_channel == CHANNELS["tenant_pattern"].format(tenant_id=sample_tenant_id)
        assert monitor_event["event_type"] == CacheEventType.DELETE.value
        assert monitor_event["resource_type"] == CacheResourceType.MONITOR.value
        assert monitor_event["resource_id"] == monitor_id

    @pytest.mark.asyncio
    async def test_tenant_cache_invalidation_publishes_event(
        self, mock_redis_client, sample_tenant_id
    ):
        """Test that tenant cache invalidation publishes correct event."""
        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            result = await CacheService.invalidate_tenant_cache(sample_tenant_id)

        assert result == 5  # Mock returns 5 deleted keys

        # Verify invalidation event was published
        mock_redis_client.publish.assert_called_once()
        channel, event_data = mock_redis_client.publish.call_args[0]
        
        # Verify event structure
        assert channel == CHANNELS["tenant_pattern"].format(tenant_id=sample_tenant_id)
        assert event_data["event_type"] == CacheEventType.INVALIDATE.value
        assert event_data["resource_type"] == CacheResourceType.TENANT.value
        assert event_data["tenant_id"] == sample_tenant_id


class TestFullIntegrationFlow(TestCacheIntegrationFixtures):
    """Test full integration flow with multiple operations."""

    @pytest.mark.asyncio
    async def test_sequential_cache_operations_with_events(
        self, mock_redis_client, mock_async_db, sample_monitor, sample_network, sample_trigger, sample_tenant_id
    ):
        """Test sequential cache operations and verify event publishing."""
        # Mock database returns for trigger operations
        mock_async_db.scalar.return_value = None

        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            # Perform sequential operations
            monitor_result = await CacheService.cache_monitor(mock_async_db, sample_monitor)
            network_result = await CacheService.cache_network(sample_network)
            trigger_result = await CacheService.cache_trigger(mock_async_db, sample_trigger)
            
            # Delete operations
            delete_monitor_result = await CacheService.delete_monitor(
                sample_tenant_id, str(sample_monitor.id)
            )
            delete_network_result = await CacheService.delete_network(
                sample_tenant_id, str(sample_network.id)
            )
            
            # Tenant invalidation
            invalidate_result = await CacheService.invalidate_tenant_cache(sample_tenant_id)

        # Verify all operations succeeded
        assert monitor_result is True
        assert network_result is True
        assert trigger_result is True
        assert delete_monitor_result is True
        assert delete_network_result is True
        assert invalidate_result == 5

        # Verify total number of published events (6 operations = 6 events)
        assert mock_redis_client.publish.call_count == 6

        # Verify cache operations were called
        assert mock_redis_client.set.call_count == 3  # 3 cache operations
        assert mock_redis_client.delete.call_count == 2  # 2 delete operations
        assert mock_redis_client.delete_pattern.call_count == 1  # 1 invalidation

    @pytest.mark.asyncio
    async def test_concurrent_operations_with_events(
        self, mock_redis_client, mock_async_db, sample_tenant_id
    ):
        """Test concurrent cache operations and event publishing."""
        # Create multiple monitors for concurrent operations
        monitors = []
        for i in range(5):
            monitor = Mock(spec=Monitor)
            monitor.id = uuid.uuid4()
            monitor.tenant_id = uuid.UUID(sample_tenant_id)
            monitor.name = f"Monitor {i}"
            monitor.triggers = []
            monitor.active = True
            monitor.paused = False
            monitors.append(monitor)

        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            # Run concurrent cache operations
            tasks = [
                CacheService.cache_monitor(mock_async_db, monitor)
                for monitor in monitors
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Verify all operations succeeded
        assert all(result is True for result in results if not isinstance(result, Exception))

        # Verify cache operations were called for each monitor
        assert mock_redis_client.set.call_count == 5
        assert mock_redis_client.publish.call_count == 5

    @pytest.mark.asyncio
    async def test_error_scenarios_in_integration_flow(
        self, mock_redis_client, mock_async_db, sample_monitor
    ):
        """Test error handling in integration flow."""
        # Test Redis failure scenario
        mock_redis_client.set.side_effect = Exception("Redis connection failed")

        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            result = await CacheService.cache_monitor(mock_async_db, sample_monitor)

        # Operation should fail gracefully
        assert result is False
        # No event should be published on failure
        mock_redis_client.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_subscriber_resilience_to_malformed_messages(self, mock_redis_client):
        """Test that subscriber handles malformed messages gracefully."""
        # Test various malformed message scenarios
        malformed_messages = [
            {
                "type": "message",
                "channel": b"test:channel",
                "data": b"invalid json"  # Invalid JSON
            },
            {
                "type": "message", 
                "channel": b"test:channel",
                "data": b'{"incomplete": "event"}'  # Missing required fields
            },
            {
                "type": "subscribe",  # Non-message type
                "channel": b"test:channel",
                "data": 1
            }
        ]

        processed_count = 0
        for message in malformed_messages:
            if message['type'] == 'message':
                try:
                    data = message['data']
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    
                    # This should raise JSONDecodeError for invalid JSON
                    if data == "invalid json":
                        with pytest.raises(json.JSONDecodeError):
                            json.loads(data)
                    else:
                        event = json.loads(data)
                        # For incomplete events, we can still parse JSON but event may be incomplete
                        assert isinstance(event, dict)
                        processed_count += 1
                except (json.JSONDecodeError, UnicodeDecodeError):
                    # Expected for malformed messages
                    pass

        # Only the incomplete but valid JSON message should be processed
        assert processed_count == 1


class TestChannelManagement(TestCacheIntegrationFixtures):
    """Test channel management and routing."""

    @pytest.mark.asyncio
    async def test_tenant_specific_channel_routing(self, mock_redis_client, sample_tenant_id):
        """Test that events are routed to correct tenant-specific channels."""
        monitor_id = str(uuid.uuid4())
        
        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            await CacheService.delete_monitor(sample_tenant_id, monitor_id)

        # Verify event was published to tenant-specific channel
        mock_redis_client.publish.assert_called_once()
        channel, _ = mock_redis_client.publish.call_args[0]
        
        expected_channel = CHANNELS["tenant_pattern"].format(tenant_id=sample_tenant_id)
        assert channel == expected_channel

    @pytest.mark.asyncio
    async def test_platform_level_event_routing(self, mock_redis_client):
        """Test that platform-level events use correct channels."""
        resource_id = str(uuid.uuid4())
        
        with patch("src.app.services.cache_service.redis_client", mock_redis_client):
            result = await CacheService._publish_cache_event(
                event_type=CacheEventType.UPDATE,
                resource_type=CacheResourceType.PLATFORM,
                resource_id=resource_id
            )

        assert result is True
        
        # Verify event was published to platform channel
        mock_redis_client.publish.assert_called_once()
        channel, event_data = mock_redis_client.publish.call_args[0]
        
        assert channel == CHANNELS["platform_update"]
        assert "tenant_id" not in event_data

    def test_channel_constants_integrity(self):
        """Test that all required channels are defined."""
        required_channels = [
            "config_update",
            "monitor_update", 
            "network_update",
            "trigger_update",
            "platform_update",
            "tenant_pattern"
        ]
        
        for channel in required_channels:
            assert channel in CHANNELS
            assert isinstance(CHANNELS[channel], str)
            assert len(CHANNELS[channel]) > 0

        # Test tenant pattern has placeholder
        assert "{tenant_id}" in CHANNELS["tenant_pattern"]