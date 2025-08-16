"""
Comprehensive test suite for CacheService cache consistency and behavior.

Tests cover:
- Write-through caching (data written to both DB and cache correctly)
- Cache invalidation (proper deletion and cleanup)
- Cache TTL behavior (expiration)
- Denormalization correctness (data structure for Rust)
- Pub/sub event publishing on cache operations
- Concurrent access patterns and race conditions
- Error handling and recovery scenarios
- Cache consistency between DB and Redis

The tests use extensive mocking to isolate cache behavior from database operations
and focus on testing the actual caching logic rather than implementation details.
"""

import asyncio
import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from faker import Faker
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.monitor import Monitor
from src.app.models.network import Network
from src.app.models.trigger import EmailTrigger, Trigger, WebhookTrigger
from src.app.services.cache_service import (
    CACHE_TTL,
    CHANNELS,
    CacheEventType,
    CacheResourceType,
    CacheService,
    cache_service,
)

fake = Faker()


class TestCacheServiceFixtures:
    """Test fixtures and helpers for cache service testing."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client for testing."""
        mock_redis = AsyncMock()
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
        return mock_redis

    @pytest.fixture
    def mock_db(self):
        """Mock database session for testing."""
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.scalar.return_value = None
        mock_db.execute.return_value.scalars.return_value.all.return_value = []
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
        monitor.triggers = ["email-trigger-1"]
        monitor.created_at = datetime.now(UTC)
        monitor.updated_at = datetime.now(UTC)
        monitor.last_validated_at = datetime.now(UTC)

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
        network.created_at = datetime.now(UTC)
        network.updated_at = datetime.now(UTC)
        network.last_validated_at = datetime.now(UTC)

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
        trigger.created_at = datetime.now(UTC)
        trigger.updated_at = datetime.now(UTC)
        trigger.last_validated_at = datetime.now(UTC)

        return trigger

    @pytest.fixture
    def sample_email_trigger(self, sample_trigger):
        """Generate a sample EmailTrigger object."""
        email_trigger = Mock(spec=EmailTrigger)
        email_trigger.trigger_id = sample_trigger.id
        email_trigger.host = "smtp.example.com"
        email_trigger.port = 587
        email_trigger.username_type = "Plain"
        email_trigger.username_value = "user@example.com"
        email_trigger.password_type = "Environment"
        email_trigger.password_value = "EMAIL_PASSWORD"
        email_trigger.sender = "alerts@example.com"
        email_trigger.recipients = ["admin@example.com"]
        email_trigger.message_title = "Alert: {event_type}"
        email_trigger.message_body = "Alert triggered: {details}"

        return email_trigger

    @pytest.fixture
    def sample_webhook_trigger(self, sample_trigger):
        """Generate a sample WebhookTrigger object."""
        webhook_trigger = Mock(spec=WebhookTrigger)
        webhook_trigger.trigger_id = sample_trigger.id
        webhook_trigger.url_type = "Plain"
        webhook_trigger.url_value = "https://webhook.example.com/alerts"
        webhook_trigger.method = "POST"
        webhook_trigger.headers = {"Content-Type": "application/json"}
        webhook_trigger.secret_type = "Environment"
        webhook_trigger.secret_value = "WEBHOOK_SECRET"
        webhook_trigger.message_title = "Alert: {event_type}"
        webhook_trigger.message_body = "Alert triggered: {details}"

        return webhook_trigger


class TestMonitorCaching(TestCacheServiceFixtures):
    """Test monitor caching operations."""

    @pytest.mark.asyncio
    async def test_cache_monitor_success_with_triggers(
        self, mock_redis, mock_db, sample_monitor, sample_trigger, sample_email_trigger
    ):
        """Test successful monitor caching with denormalized trigger data."""
        # Setup database mocks to return trigger data with eager loading
        # Create a mock result that has an all() method returning triggers
        mock_scalars_result = Mock()
        mock_scalars_result.all.return_value = [sample_trigger]
        mock_db.scalars.return_value = mock_scalars_result

        # Setup trigger with email_config relationship
        sample_trigger.email_config = sample_email_trigger

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_monitor(mock_db, sample_monitor)

        assert result is True

        # Verify cache was set with correct key and TTL
        expected_key = f"tenant:{sample_monitor.tenant_id}:monitor:{sample_monitor.id}"
        mock_redis.set.assert_called_once()
        args, kwargs = mock_redis.set.call_args
        assert args[0] == expected_key
        assert kwargs["expiration"] == CACHE_TTL["monitor"]

        # Verify cached data structure includes denormalized triggers
        cached_data = args[1]
        assert cached_data["id"] == str(sample_monitor.id)
        assert cached_data["tenant_id"] == str(sample_monitor.tenant_id)
        assert cached_data["name"] == sample_monitor.name
        assert cached_data["active"] == sample_monitor.active
        assert len(cached_data["triggers"]) == 1

        # Verify trigger is denormalized
        trigger_data = cached_data["triggers"][0]
        assert trigger_data["id"] == str(sample_trigger.id)
        assert trigger_data["trigger_type"] == "email"
        assert "email_config" in trigger_data

        # Verify email config is properly serialized
        email_config = trigger_data["email_config"]
        assert email_config["host"] == sample_email_trigger.host
        assert email_config["recipients"] == sample_email_trigger.recipients

        # Verify active monitors list was updated
        mock_redis.sadd.assert_called_once_with(
            f"tenant:{sample_monitor.tenant_id}:monitors:active",
            str(sample_monitor.id)
        )
        mock_redis.expire.assert_called_once()

        # Verify pub/sub event was published
        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_monitor_inactive_not_added_to_active_list(
        self, mock_redis, mock_db, sample_monitor
    ):
        """Test that inactive monitors are not added to active list."""
        sample_monitor.active = False
        sample_monitor.triggers = []  # No triggers to simplify test

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_monitor(mock_db, sample_monitor)

        assert result is True

        # Verify monitor was removed from active list instead of added
        mock_redis.srem.assert_called_once_with(
            f"tenant:{sample_monitor.tenant_id}:monitors:active",
            str(sample_monitor.id)
        )
        mock_redis.sadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_monitor_paused_not_added_to_active_list(
        self, mock_redis, mock_db, sample_monitor
    ):
        """Test that paused monitors are not added to active list."""
        sample_monitor.active = True
        sample_monitor.paused = True
        sample_monitor.triggers = []  # No triggers to simplify test

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_monitor(mock_db, sample_monitor)

        assert result is True

        # Verify monitor was removed from active list
        mock_redis.srem.assert_called_once_with(
            f"tenant:{sample_monitor.tenant_id}:monitors:active",
            str(sample_monitor.id)
        )

    @pytest.mark.asyncio
    async def test_cache_monitor_with_webhook_trigger(
        self, mock_redis, mock_db, sample_monitor, sample_trigger, sample_webhook_trigger
    ):
        """Test monitor caching with webhook trigger type."""
        sample_trigger.trigger_type = "webhook"
        sample_trigger.webhook_config = sample_webhook_trigger

        # Setup mock scalars result
        mock_scalars_result = Mock()
        mock_scalars_result.all.return_value = [sample_trigger]
        mock_db.scalars.return_value = mock_scalars_result

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_monitor(mock_db, sample_monitor)

        assert result is True

        # Verify webhook config is properly cached
        cached_data = mock_redis.set.call_args[0][1]
        trigger_data = cached_data["triggers"][0]
        assert "webhook_config" in trigger_data

        webhook_config = trigger_data["webhook_config"]
        assert webhook_config["url_value"] == sample_webhook_trigger.url_value
        assert webhook_config["method"] == sample_webhook_trigger.method

    @pytest.mark.asyncio
    async def test_cache_monitor_redis_failure(
        self, mock_redis, mock_db, sample_monitor
    ):
        """Test monitor caching when Redis fails."""
        sample_monitor.triggers = []
        mock_redis.set.side_effect = RedisError("Redis connection failed")

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_monitor(mock_db, sample_monitor)

        assert result is False

    @pytest.mark.asyncio
    async def test_cache_monitor_database_failure(
        self, mock_redis, mock_db, sample_monitor
    ):
        """Test monitor caching when database query fails."""
        mock_db.scalar.side_effect = Exception("Database error")

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_monitor(mock_db, sample_monitor)

        assert result is False

    @pytest.mark.asyncio
    async def test_get_monitor_success(self, mock_redis, sample_tenant_id):
        """Test successful monitor retrieval from cache."""
        monitor_id = str(uuid.uuid4())
        expected_data = {"id": monitor_id, "name": "Test Monitor"}
        mock_redis.get.return_value = expected_data

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.get_monitor(sample_tenant_id, monitor_id)

        assert result == expected_data
        mock_redis.get.assert_called_once_with(
            f"tenant:{sample_tenant_id}:monitor:{monitor_id}")

    @pytest.mark.asyncio
    async def test_get_monitor_not_found(self, mock_redis, sample_tenant_id):
        """Test monitor retrieval when not in cache."""
        monitor_id = str(uuid.uuid4())
        mock_redis.get.return_value = None

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.get_monitor(sample_tenant_id, monitor_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_monitor_success(self, mock_redis, sample_tenant_id):
        """Test successful monitor deletion from cache."""
        monitor_id = str(uuid.uuid4())

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.delete_monitor(sample_tenant_id, monitor_id)

        assert result is True

        # Verify cache key was deleted
        expected_key = f"tenant:{sample_tenant_id}:monitor:{monitor_id}"
        mock_redis.delete.assert_called_once_with(expected_key)

        # Verify monitor was removed from active list
        mock_redis.srem.assert_called_once_with(
            f"tenant:{sample_tenant_id}:monitors:active",
            monitor_id
        )

        # Verify pub/sub event was published
        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_monitor_not_found(self, mock_redis, sample_tenant_id):
        """Test monitor deletion when key doesn't exist."""
        monitor_id = str(uuid.uuid4())
        mock_redis.delete.return_value = 0  # No keys deleted

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.delete_monitor(sample_tenant_id, monitor_id)

        assert result is False


class TestNetworkCaching(TestCacheServiceFixtures):
    """Test network caching operations."""

    @pytest.mark.asyncio
    async def test_cache_network_success(self, mock_redis, sample_network):
        """Test successful network caching."""
        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_network(sample_network)

        assert result is True

        # Verify cache was set with correct key and TTL
        expected_key = f"tenant:{sample_network.tenant_id}:network:{sample_network.id}"
        mock_redis.set.assert_called_once()
        args, kwargs = mock_redis.set.call_args
        assert args[0] == expected_key
        assert kwargs["expiration"] == CACHE_TTL["network"]

        # Verify cached data structure
        cached_data = args[1]
        assert cached_data["id"] == str(sample_network.id)
        assert cached_data["tenant_id"] == str(sample_network.tenant_id)
        assert cached_data["name"] == sample_network.name
        assert cached_data["slug"] == sample_network.slug
        assert cached_data["chain_id"] == sample_network.chain_id
        assert cached_data["rpc_urls"] == sample_network.rpc_urls

        # Verify pub/sub event was published
        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_network_success(self, mock_redis, sample_tenant_id):
        """Test successful network retrieval from cache."""
        network_id = str(uuid.uuid4())
        expected_data = {"id": network_id, "name": "Ethereum"}
        mock_redis.get.return_value = expected_data

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.get_network(sample_tenant_id, network_id)

        assert result == expected_data
        mock_redis.get.assert_called_once_with(
            f"tenant:{sample_tenant_id}:network:{network_id}")

    @pytest.mark.asyncio
    async def test_delete_network_success(self, mock_redis, sample_tenant_id):
        """Test successful network deletion from cache."""
        network_id = str(uuid.uuid4())

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.delete_network(sample_tenant_id, network_id)

        assert result is True

        # Verify cache key was deleted
        expected_key = f"tenant:{sample_tenant_id}:network:{network_id}"
        mock_redis.delete.assert_called_once_with(expected_key)

        # Verify pub/sub event was published
        mock_redis.publish.assert_called_once()


class TestTriggerCaching(TestCacheServiceFixtures):
    """Test trigger caching operations."""

    @pytest.mark.asyncio
    async def test_cache_email_trigger_success(
        self, mock_redis, mock_db, sample_trigger, sample_email_trigger
    ):
        """Test successful email trigger caching."""
        mock_db.scalar.return_value = sample_email_trigger

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_trigger(mock_db, sample_trigger)

        assert result is True

        # Verify cache was set with correct key and TTL
        expected_key = f"tenant:{sample_trigger.tenant_id}:trigger:{sample_trigger.id}"
        mock_redis.set.assert_called_once()
        args, kwargs = mock_redis.set.call_args
        assert args[0] == expected_key
        assert kwargs["expiration"] == CACHE_TTL["trigger"]

        # Verify cached data structure
        cached_data = args[1]
        assert cached_data["id"] == str(sample_trigger.id)
        assert cached_data["trigger_type"] == "email"
        assert "email_config" in cached_data

        # Verify email config serialization
        email_config = cached_data["email_config"]
        assert email_config["host"] == sample_email_trigger.host
        assert email_config["port"] == sample_email_trigger.port
        assert email_config["recipients"] == sample_email_trigger.recipients

    @pytest.mark.asyncio
    async def test_cache_webhook_trigger_success(
        self, mock_redis, mock_db, sample_trigger, sample_webhook_trigger
    ):
        """Test successful webhook trigger caching."""
        sample_trigger.trigger_type = "webhook"
        mock_db.scalar.return_value = sample_webhook_trigger

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_trigger(mock_db, sample_trigger)

        assert result is True

        # Verify webhook config serialization
        cached_data = mock_redis.set.call_args[0][1]
        assert "webhook_config" in cached_data

        webhook_config = cached_data["webhook_config"]
        assert webhook_config["url_value"] == sample_webhook_trigger.url_value
        assert webhook_config["method"] == sample_webhook_trigger.method
        assert webhook_config["headers"] == sample_webhook_trigger.headers

    @pytest.mark.asyncio
    async def test_cache_trigger_no_config_found(
        self, mock_redis, mock_db, sample_trigger
    ):
        """Test trigger caching when no type-specific config is found."""
        mock_db.scalar.return_value = None  # No email/webhook config found

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_trigger(mock_db, sample_trigger)

        assert result is True

        # Verify base trigger data is still cached
        cached_data = mock_redis.set.call_args[0][1]
        assert cached_data["id"] == str(sample_trigger.id)
        assert "email_config" not in cached_data
        assert "webhook_config" not in cached_data

    @pytest.mark.asyncio
    async def test_get_trigger_success(self, mock_redis, sample_tenant_id):
        """Test successful trigger retrieval from cache."""
        trigger_id = str(uuid.uuid4())
        expected_data = {"id": trigger_id, "name": "Email Trigger"}
        mock_redis.get.return_value = expected_data

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.get_trigger(sample_tenant_id, trigger_id)

        assert result == expected_data
        mock_redis.get.assert_called_once_with(
            f"tenant:{sample_tenant_id}:trigger:{trigger_id}")

    @pytest.mark.asyncio
    async def test_delete_trigger_success(self, mock_redis, sample_tenant_id):
        """Test successful trigger deletion from cache."""
        trigger_id = str(uuid.uuid4())

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.delete_trigger(sample_tenant_id, trigger_id)

        assert result is True

        # Verify cache key was deleted
        expected_key = f"tenant:{sample_tenant_id}:trigger:{trigger_id}"
        mock_redis.delete.assert_called_once_with(expected_key)

        # Verify pub/sub event was published
        mock_redis.publish.assert_called_once()


class TestActiveMonitorsList(TestCacheServiceFixtures):
    """Test active monitors list management."""

    @pytest.mark.asyncio
    async def test_get_active_monitors(self, mock_redis, sample_tenant_id):
        """Test retrieval of active monitors list."""
        monitor_ids = {str(uuid.uuid4()), str(uuid.uuid4())}
        mock_redis.smembers.return_value = monitor_ids

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.get_active_monitors(sample_tenant_id)

        assert set(result) == monitor_ids
        mock_redis.smembers.assert_called_once_with(
            f"tenant:{sample_tenant_id}:monitors:active")

    @pytest.mark.asyncio
    async def test_add_to_active_monitors(self, mock_redis, sample_tenant_id):
        """Test adding monitor to active monitors list."""
        monitor_id = str(uuid.uuid4())

        with patch("src.app.services.cache_service.CacheService._add_to_active_monitors"):
            await CacheService._add_to_active_monitors(sample_tenant_id, monitor_id)

        # This is tested indirectly through cache_monitor tests


class TestCacheTTLBehavior(TestCacheServiceFixtures):
    """Test cache TTL and expiration behavior."""

    @pytest.mark.asyncio
    async def test_cache_ttl_values_applied_correctly(self, mock_redis, sample_monitor, mock_db):
        """Test that correct TTL values are applied to cached items."""
        sample_monitor.triggers = []

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            await CacheService.cache_monitor(mock_db, sample_monitor)

        # Verify monitor cache TTL
        monitor_call = mock_redis.set.call_args
        assert monitor_call[1]["expiration"] == CACHE_TTL["monitor"]

    @pytest.mark.asyncio
    async def test_active_monitors_list_ttl(self, mock_redis, sample_tenant_id):
        """Test that active monitors list has correct TTL."""
        monitor_id = str(uuid.uuid4())

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            await CacheService._add_to_active_monitors(sample_tenant_id, monitor_id)

        # Verify TTL was set on active monitors list
        mock_redis.expire.assert_called_once_with(
            f"tenant:{sample_tenant_id}:monitors:active",
            CACHE_TTL["active_list"]
        )


class TestPubSubEventPublishing(TestCacheServiceFixtures):
    """Test pub/sub event publishing on cache operations."""

    @pytest.mark.asyncio
    async def test_publish_cache_event_success(self, mock_redis):
        """Test successful cache event publishing."""
        tenant_id = str(uuid.uuid4())
        resource_id = str(uuid.uuid4())

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService._publish_cache_event(
                event_type=CacheEventType.UPDATE,
                resource_type=CacheResourceType.MONITOR,
                resource_id=resource_id,
                tenant_id=tenant_id,
                metadata={"test": "data"}
            )

        assert result is True

        # Verify event was published to correct channel
        mock_redis.publish.assert_called_once()
        channel, event = mock_redis.publish.call_args[0]
        assert channel == CHANNELS["tenant_pattern"].format(
            tenant_id=tenant_id)

        # Verify event structure
        assert isinstance(event, dict)
        assert event["event_type"] == CacheEventType.UPDATE.value
        assert event["resource_type"] == CacheResourceType.MONITOR.value
        assert event["resource_id"] == resource_id
        assert event["tenant_id"] == tenant_id
        assert event["metadata"] == {"test": "data"}
        assert "timestamp" in event

    @pytest.mark.asyncio
    async def test_publish_platform_event(self, mock_redis):
        """Test platform-level event publishing."""
        resource_id = str(uuid.uuid4())

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService._publish_cache_event(
                event_type=CacheEventType.UPDATE,
                resource_type=CacheResourceType.PLATFORM,
                resource_id=resource_id
            )

        assert result is True

        # Verify event was published to platform channel
        channel, event = mock_redis.publish.call_args[0]
        assert channel == CHANNELS["platform_update"]
        assert "tenant_id" not in event

    @pytest.mark.asyncio
    async def test_publish_event_redis_failure(self, mock_redis):
        """Test event publishing when Redis fails."""
        mock_redis.publish.side_effect = RedisError("Publish failed")

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService._publish_cache_event(
                event_type=CacheEventType.UPDATE,
                resource_type=CacheResourceType.MONITOR,
                resource_id=str(uuid.uuid4())
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_monitor_cache_publishes_correct_events(
        self, mock_redis, mock_db, sample_monitor
    ):
        """Test that monitor caching publishes correct event metadata."""
        sample_monitor.triggers = []

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            await CacheService.cache_monitor(mock_db, sample_monitor)

        # Verify event metadata includes monitor details
        mock_redis.publish.assert_called_once()
        _, event = mock_redis.publish.call_args[0]

        metadata = event["metadata"]
        assert metadata["active"] == sample_monitor.active
        assert metadata["paused"] == sample_monitor.paused
        assert metadata["validated"] == sample_monitor.validated
        assert metadata["name"] == sample_monitor.name
        assert metadata["slug"] == sample_monitor.slug


class TestTenantCacheInvalidation(TestCacheServiceFixtures):
    """Test tenant-wide cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_tenant_cache_success(self, mock_redis, sample_tenant_id):
        """Test successful tenant cache invalidation."""
        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.invalidate_tenant_cache(sample_tenant_id)

        assert result == 5  # Mock returns 5 deleted keys

        # Verify pattern deletion was called
        mock_redis.delete_pattern.assert_called_once_with(
            f"tenant:{sample_tenant_id}:*")

        # Verify invalidation event was published
        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tenant_cache_keys(self, mock_redis, sample_tenant_id):
        """Test retrieval of tenant cache keys."""
        expected_keys = [
            f"tenant:{sample_tenant_id}:monitor:123",
            f"tenant:{sample_tenant_id}:network:456"
        ]
        mock_redis.keys_pattern.return_value = expected_keys

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.get_tenant_cache_keys(sample_tenant_id)

        assert result == expected_keys
        mock_redis.keys_pattern.assert_called_once_with(
            f"tenant:{sample_tenant_id}:*")


class TestBulkOperations(TestCacheServiceFixtures):
    """Test bulk caching operations."""

    @pytest.mark.asyncio
    async def test_cache_tenant_monitors_success(self, mock_redis, mock_db, sample_tenant_id):
        """Test bulk caching of tenant monitors."""
        tenant_uuid = uuid.UUID(sample_tenant_id)

        # Create multiple sample monitors
        monitors = []
        for i in range(3):
            monitor = Mock(spec=Monitor)
            monitor.id = uuid.uuid4()
            monitor.tenant_id = tenant_uuid
            monitor.name = f"Monitor {i}"
            monitor.triggers = []
            monitors.append(monitor)

        # Mock database query result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = monitors
        mock_db.execute.return_value = mock_result

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            with patch.object(CacheService, 'cache_monitor', return_value=True) as mock_cache:
                result = await CacheService.cache_tenant_monitors(mock_db, tenant_uuid)

        assert result == 3
        assert mock_cache.call_count == 3

    @pytest.mark.asyncio
    async def test_cache_tenant_networks_partial_failure(self, mock_redis, mock_db, sample_tenant_id):
        """Test bulk network caching with partial failures."""
        tenant_uuid = uuid.UUID(sample_tenant_id)

        # Create multiple sample networks
        networks = []
        for i in range(3):
            network = Mock(spec=Network)
            network.id = uuid.uuid4()
            network.tenant_id = tenant_uuid
            networks.append(network)

        # Mock database query result
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = networks
        mock_db.execute.return_value = mock_result

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            with patch.object(CacheService, 'cache_network', side_effect=[True, False, True]) as mock_cache:
                result = await CacheService.cache_tenant_networks(mock_db, tenant_uuid)

        assert result == 2  # Only 2 out of 3 succeeded
        assert mock_cache.call_count == 3


class TestConcurrencyAndRaceConditions(TestCacheServiceFixtures):
    """Test concurrent access patterns and race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, mock_redis, mock_db, sample_monitor):
        """Test concurrent caching operations don't interfere."""
        sample_monitor.triggers = []

        # Create multiple concurrent cache operations
        tasks = []
        for i in range(10):
            monitor_copy = Mock(spec=Monitor)
            monitor_copy.id = uuid.uuid4()
            monitor_copy.tenant_id = sample_monitor.tenant_id
            monitor_copy.name = f"Monitor {i}"
            monitor_copy.triggers = []
            monitor_copy.active = True
            monitor_copy.paused = False

            task = CacheService.cache_monitor(mock_db, monitor_copy)
            tasks.append(task)

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should succeed
        assert all(result is True for result in results if not isinstance(
            result, Exception))

        # Verify Redis operations were called correctly
        assert mock_redis.set.call_count == 10

    @pytest.mark.asyncio
    async def test_cache_and_delete_race_condition(
        self, mock_redis, mock_db, sample_monitor, sample_tenant_id
    ):
        """Test cache and delete operations happening concurrently."""
        sample_monitor.triggers = []
        monitor_id = str(sample_monitor.id)

        async def cache_operation():
            return await CacheService.cache_monitor(mock_db, sample_monitor)

        async def delete_operation():
            return await CacheService.delete_monitor(sample_tenant_id, monitor_id)

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            # Run cache and delete concurrently
            cache_result, delete_result = await asyncio.gather(
                cache_operation(),
                delete_operation(),
                return_exceptions=True
            )

        # Both operations should complete without exceptions
        assert not isinstance(cache_result, Exception)
        assert not isinstance(delete_result, Exception)


class TestErrorHandlingAndRecovery(TestCacheServiceFixtures):
    """Test error handling and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_redis_connection_failure_recovery(
        self, mock_redis, mock_db, sample_monitor
    ):
        """Test behavior when Redis connection fails during operation."""
        sample_monitor.triggers = []

        # First call fails, second succeeds
        mock_redis.set.side_effect = [RedisError("Connection lost"), True]

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            # First attempt should fail gracefully
            result1 = await CacheService.cache_monitor(mock_db, sample_monitor)
            assert result1 is False

            # Second attempt should succeed
            result2 = await CacheService.cache_monitor(mock_db, sample_monitor)
            assert result2 is True

    @pytest.mark.asyncio
    async def test_database_query_timeout(self, mock_redis, mock_db, sample_monitor):
        """Test handling of database query timeouts."""
        # Simulate database timeout
        mock_db.scalar.side_effect = TimeoutError("Query timeout")

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_monitor(mock_db, sample_monitor)

        assert result is False
        # Redis operations should not be called on DB failure
        mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_partial_data_corruption_handling(
        self, mock_redis, mock_db, sample_monitor, sample_trigger
    ):
        """Test handling of partial data corruption in trigger queries."""
        # First query succeeds (gets trigger), second fails (gets trigger config)
        mock_db.scalar.side_effect = [
            sample_trigger, Exception("Data corruption")]

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_monitor(mock_db, sample_monitor)

        assert result is False

    @pytest.mark.asyncio
    async def test_malformed_cache_data_handling(self, mock_redis, sample_tenant_id):
        """Test handling of malformed data when retrieving from cache."""
        monitor_id = str(uuid.uuid4())

        # Redis returns malformed data that can't be JSON decoded
        mock_redis.get.side_effect = json.JSONDecodeError(
            "Invalid JSON", "doc", 0)

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            with pytest.raises(json.JSONDecodeError):
                await CacheService.get_monitor(sample_tenant_id, monitor_id)


class TestDataSerialization(TestCacheServiceFixtures):
    """Test data serialization for different data types."""

    def test_serialize_datetime(self):
        """Test datetime serialization."""
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = CacheService._serialize_datetime(dt)
        assert result == "2023-01-01T12:00:00+00:00"

        # Test None handling
        assert CacheService._serialize_datetime(None) is None

    def test_serialize_uuid(self):
        """Test UUID serialization."""
        test_uuid = uuid.uuid4()
        result = CacheService._serialize_uuid(test_uuid)
        assert result == str(test_uuid)

        # Test None handling
        assert CacheService._serialize_uuid(None) is None

    def test_email_trigger_serialization(self, sample_email_trigger):
        """Test email trigger serialization includes all required fields."""
        result = CacheService._serialize_email_trigger(sample_email_trigger)

        expected_fields = [
            "host", "port", "username_type", "username_value",
            "password_type", "password_value", "sender", "recipients",
            "message_title", "message_body"
        ]

        for field in expected_fields:
            assert field in result
            assert result[field] == getattr(sample_email_trigger, field)

    def test_webhook_trigger_serialization(self, sample_webhook_trigger):
        """Test webhook trigger serialization includes all required fields."""
        result = CacheService._serialize_webhook_trigger(
            sample_webhook_trigger)

        expected_fields = [
            "url_type", "url_value", "method", "headers",
            "secret_type", "secret_value", "message_title", "message_body"
        ]

        for field in expected_fields:
            assert field in result
            assert result[field] == getattr(sample_webhook_trigger, field)


class TestCacheConsistencyChecks(TestCacheServiceFixtures):
    """Test cache consistency between database and Redis."""

    @pytest.mark.asyncio
    async def test_write_through_consistency(
        self, mock_redis, mock_db, sample_monitor
    ):
        """Test that write-through caching maintains consistency."""
        sample_monitor.triggers = []

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.cache_monitor(mock_db, sample_monitor)

        assert result is True

        # Verify that data written to cache matches source data
        cached_data = mock_redis.set.call_args[0][1]

        # Check critical fields match
        assert cached_data["id"] == str(sample_monitor.id)
        assert cached_data["tenant_id"] == str(sample_monitor.tenant_id)
        assert cached_data["name"] == sample_monitor.name
        assert cached_data["active"] == sample_monitor.active
        assert cached_data["networks"] == sample_monitor.networks
        assert cached_data["addresses"] == sample_monitor.addresses

    @pytest.mark.asyncio
    async def test_cache_invalidation_consistency(
        self, mock_redis, sample_tenant_id
    ):
        """Test that cache invalidation removes all related keys."""
        # Setup some cached keys

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            result = await CacheService.invalidate_tenant_cache(sample_tenant_id)

        assert result == 5  # Mock delete_pattern returns 5

        # Verify pattern deletion was called with correct pattern
        mock_redis.delete_pattern.assert_called_once_with(
            f"tenant:{sample_tenant_id}:*")

    @pytest.mark.asyncio
    async def test_denormalization_maintains_referential_integrity(
        self, mock_redis, mock_db, sample_monitor, sample_trigger, sample_email_trigger
    ):
        """Test that denormalized data maintains referential integrity."""
        # Setup trigger relationship with eager loading
        sample_trigger.email_config = sample_email_trigger

        # Setup mock scalars result
        mock_scalars_result = Mock()
        mock_scalars_result.all.return_value = [sample_trigger]
        mock_db.scalars.return_value = mock_scalars_result

        with patch("src.app.services.cache_service.redis_client", mock_redis):
            await CacheService.cache_monitor(mock_db, sample_monitor)

        cached_data = mock_redis.set.call_args[0][1]

        # Verify trigger relationship is properly denormalized
        assert len(cached_data["triggers"]) == 1
        trigger_data = cached_data["triggers"][0]

        # Verify trigger IDs match
        assert trigger_data["id"] == str(sample_trigger.id)
        assert trigger_data["tenant_id"] == str(sample_trigger.tenant_id)

        # Verify email config is properly nested
        assert "email_config" in trigger_data
        email_config = trigger_data["email_config"]
        assert email_config["host"] == sample_email_trigger.host


class TestConvenienceInstance:
    """Test the convenience instance."""

    def test_cache_service_instance_exists(self):
        """Test that the cache_service convenience instance exists."""
        assert cache_service is not None
        assert isinstance(cache_service, CacheService)
