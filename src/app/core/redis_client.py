"""
Centralized Redis client manager for all Redis operations.
Provides connection pooling, health checks, and pub/sub support.
"""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, Optional, Set  # noqa: UP035

from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from ..core.logger import logging

logger = logging.getLogger(__name__)


class RedisClient:
    """Centralized Redis client manager with connection pooling."""

    _instance: Optional["RedisClient"] = None
    _pool: Optional[ConnectionPool] = None
    _client: Optional[Redis] = None
    _pubsub_client: Optional[Redis] = None

    def __new__(cls) -> "RedisClient":
        """Singleton pattern to ensure single Redis connection pool."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def initialize(cls, redis_url: str) -> None:
        """Initialize Redis connection pool.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
        """
        instance = cls()
        if instance._pool is None:
            # Create connection pool without socket_keepalive_options on macOS
            # as the numeric TCP options cause issues
            import platform
            pool_kwargs = {
                "decode_responses": False,  # We'll handle decoding ourselves
                "max_connections": 50,
                "socket_keepalive": True,
            }

            # Only add socket_keepalive_options on Linux
            if platform.system() == "Linux":
                pool_kwargs["socket_keepalive_options"] = {  # type: ignore[assignment]
                    1: 3,  # TCP_KEEPIDLE
                    2: 3,  # TCP_KEEPINTVL
                    3: 3,  # TCP_KEEPCNT
                }

            instance._pool = ConnectionPool.from_url(redis_url, **pool_kwargs)
            instance._client = Redis(connection_pool=instance._pool)
            instance._pubsub_client = Redis(connection_pool=instance._pool)
            logger.info(f"Redis client initialized with URL: {redis_url}")

    @classmethod
    async def close(cls) -> None:
        """Close Redis connections and cleanup."""
        instance = cls()
        if instance._client:
            await instance._client.close()
        if instance._pubsub_client:
            await instance._pubsub_client.close()
        if instance._pool:
            await instance._pool.disconnect()
        instance._client = None
        instance._pubsub_client = None
        instance._pool = None
        logger.info("Redis client closed")

    @classmethod
    def get_client(cls) -> Redis:
        """Get Redis client instance.

        Returns:
            Redis client instance

        Raises:
            RuntimeError: If client is not initialized
        """
        instance = cls()
        if instance._client is None:
            raise RuntimeError(
                "Redis client not initialized. Call initialize() first.")
        return instance._client

    @classmethod
    async def health_check(cls) -> bool:
        """Check Redis connection health.

        Returns:
            True if Redis is healthy, False otherwise
        """
        try:
            client = cls.get_client()
            await client.ping()
            return True
        except (RedisError, RuntimeError) as e:
            logger.error(f"Redis health check failed: {e}")
            return False

    # Core operations
    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        """Get value from Redis.

        Args:
            key: Redis key

        Returns:
            Decoded value or None if not found
        """
        try:
            client = cls.get_client()
            value = await client.get(key)
            if value:
                try:
                    return json.loads(value.decode('utf-8'))
                except json.JSONDecodeError:
                    # Return raw value if not JSON
                    return value.decode('utf-8')
            return None
        except RedisError as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            raise

    @classmethod
    async def set(
        cls,
        key: str,
        value: Any,
        expiration: Optional[int] = None,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """Set value in Redis.

        Args:
            key: Redis key
            value: Value to store (will be JSON encoded if dict/list)
            expiration: TTL in seconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists

        Returns:
            True if set successfully
        """
        try:
            client = cls.get_client()

            # JSON encode if needed
            if isinstance(value, dict | list):
                value = json.dumps(value)
            elif not isinstance(value, str | bytes):
                value = str(value)

            # Convert to bytes
            if isinstance(value, str):
                value = value.encode('utf-8')

            result = await client.set(key, value, ex=expiration, nx=nx, xx=xx)
            return bool(result)
        except RedisError as e:
            logger.error(f"Redis SET error for key {key}: {e}")
            raise

    @classmethod
    async def delete(cls, *keys: str) -> int:
        """Delete keys from Redis.

        Args:
            *keys: Keys to delete

        Returns:
            Number of keys deleted
        """
        try:
            if not keys:
                return 0
            client = cls.get_client()
            result = await client.delete(*keys)
            return int(result)
        except RedisError as e:
            logger.error(f"Redis DELETE error for keys {keys}: {e}")
            raise

    @classmethod
    async def exists(cls, *keys: str) -> int:
        """Check if keys exist.

        Args:
            *keys: Keys to check

        Returns:
            Number of keys that exist
        """
        try:
            client = cls.get_client()
            result = await client.exists(*keys)
            return int(result)
        except RedisError as e:
            logger.error(f"Redis EXISTS error for keys {keys}: {e}")
            raise

    # List operations
    @classmethod
    async def lpush(cls, key: str, *values: Any) -> int:
        """Push values to the left of a list.

        Args:
            key: List key
            *values: Values to push

        Returns:
            Length of list after push
        """
        try:
            client = cls.get_client()
            encoded_values = []
            for value in values:
                if isinstance(value, dict | list):
                    value = json.dumps(value)
                if isinstance(value, str):
                    value = value.encode('utf-8')
                encoded_values.append(value)
            # redis-py has incomplete async type hints
            result = await client.lpush(key, *encoded_values)  # type: ignore[misc]
            return int(result) if result else 0
        except RedisError as e:
            logger.error(f"Redis LPUSH error for key {key}: {e}")
            raise

    @classmethod
    async def lrange(cls, key: str, start: int = 0, stop: int = -1) -> list:
        """Get range of elements from a list.

        Args:
            key: List key
            start: Start index
            stop: Stop index (-1 for all)

        Returns:
            List of decoded values
        """
        try:
            client = cls.get_client()
            # redis-py has incomplete async type hints
            values = await client.lrange(key, start, stop)  # type: ignore[misc]
            result = []
            for value in values:
                try:
                    decoded = json.loads(value.decode('utf-8'))
                except (json.JSONDecodeError, AttributeError):
                    decoded = value.decode(
                        'utf-8') if isinstance(value, bytes) else value
                result.append(decoded)
            return result
        except RedisError as e:
            logger.error(f"Redis LRANGE error for key {key}: {e}")
            raise

    @classmethod
    async def sadd(cls, key: str, *members: Any) -> int:
        """Add members to a set.

        Args:
            key: Set key
            *members: Members to add

        Returns:
            Number of members added
        """
        try:
            client = cls.get_client()
            encoded_members = []
            for member in members:
                if isinstance(member, dict | list):
                    member = json.dumps(member)
                if isinstance(member, str):
                    member = member.encode('utf-8')
                encoded_members.append(member)
            # redis-py has incomplete async type hints
            result = await client.sadd(key, *encoded_members)  # type: ignore[misc]
            return int(result) if result else 0
        except RedisError as e:
            logger.error(f"Redis SADD error for key {key}: {e}")
            raise

    @classmethod
    async def smembers(cls, key: str) -> Set[Any]:
        """Get all members of a set.

        Args:
            key: Set key

        Returns:
            Set of decoded members
        """
        try:
            client = cls.get_client()
            # redis-py has incomplete async type hints
            members = await client.smembers(key)  # type: ignore[misc]
            result: Set[Any] = set()
            for member in members:
                try:
                    decoded = json.loads(member.decode('utf-8'))
                except (json.JSONDecodeError, AttributeError):
                    decoded = member.decode(
                        'utf-8') if isinstance(member, bytes) else member
                result.add(decoded)
            return result
        except RedisError as e:
            logger.error(f"Redis SMEMBERS error for key {key}: {e}")
            raise

    @classmethod
    async def srem(cls, key: str, *members: Any) -> int:
        """Remove members from a set.

        Args:
            key: Set key
            *members: Members to remove

        Returns:
            Number of members removed
        """
        try:
            client = cls.get_client()
            encoded_members = []
            for member in members:
                if isinstance(member, dict | list):
                    member = json.dumps(member)
                if isinstance(member, str):
                    member = member.encode('utf-8')
                encoded_members.append(member)
            # redis-py has incomplete async type hints
            result = await client.srem(key, *encoded_members)  # type: ignore[misc]
            return int(result) if result else 0
        except RedisError as e:
            logger.error(f"Redis SREM error for key {key}: {e}")
            raise

    @classmethod
    async def expire(cls, key: str, seconds: int) -> bool:
        """Set expiration time for a key.

        Args:
            key: Redis key
            seconds: TTL in seconds

        Returns:
            True if expiration was set
        """
        try:
            client = cls.get_client()
            result = await client.expire(key, seconds)
            return bool(result)
        except RedisError as e:
            logger.error(f"Redis EXPIRE error for key {key}: {e}")
            raise

    # Pattern operations
    @classmethod
    async def delete_pattern(cls, pattern: str) -> int:
        """Delete all keys matching a pattern.

        Args:
            pattern: Pattern to match (e.g., "tenant:*:monitor:*")

        Returns:
            Number of keys deleted
        """
        try:
            client = cls.get_client()
            cursor = 0
            deleted_count = 0

            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted_count += await client.delete(*keys)
                if cursor == 0:
                    break

            return deleted_count
        except RedisError as e:
            logger.error(
                f"Redis DELETE_PATTERN error for pattern {pattern}: {e}")
            raise

    @classmethod
    async def keys_pattern(cls, pattern: str) -> list[str]:
        """Get all keys matching a pattern.

        Args:
            pattern: Pattern to match

        Returns:
            List of matching keys
        """
        try:
            client = cls.get_client()
            cursor = 0
            all_keys = []

            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                all_keys.extend(
                    [k.decode('utf-8') if isinstance(k, bytes) else k for k in keys])
                if cursor == 0:
                    break

            return all_keys
        except RedisError as e:
            logger.error(
                f"Redis KEYS_PATTERN error for pattern {pattern}: {e}")
            raise

    # Pub/Sub operations
    @classmethod
    @asynccontextmanager
    async def pubsub(cls) -> AsyncGenerator:
        """Create a pub/sub context.

        Yields:
            PubSub instance
        """
        client = cls.get_client()
        pubsub = client.pubsub()
        try:
            yield pubsub
        finally:
            await pubsub.close()

    @classmethod
    async def publish(cls, channel: str, message: Any) -> int:
        """Publish message to a channel.

        Args:
            channel: Channel name
            message: Message to publish (will be JSON encoded if dict/list)

        Returns:
            Number of subscribers that received the message
        """
        try:
            client = cls.get_client()

            if isinstance(message, dict | list):
                message = json.dumps(message)
            if isinstance(message, str):
                message = message.encode('utf-8')

            result = await client.publish(channel, message)
            return int(result)
        except RedisError as e:
            logger.error(f"Redis PUBLISH error for channel {channel}: {e}")
            raise

    # Transaction operations
    @classmethod
    @asynccontextmanager
    async def pipeline(cls, transaction: bool = True):
        """Create a pipeline for atomic operations.

        Args:
            transaction: Whether to use MULTI/EXEC

        Yields:
            Pipeline instance
        """
        client = cls.get_client()
        async with client.pipeline(transaction=transaction) as pipe:
            yield pipe


# Convenience instance
redis_client = RedisClient()
