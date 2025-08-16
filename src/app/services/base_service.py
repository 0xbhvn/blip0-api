"""
Base service class for common service operations.
Provides Redis caching patterns and common business logic.
"""

import json
from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, TypeVar

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import logging
from ..core.redis_client import RedisClient

logger = logging.getLogger(__name__)

# Type variables for generics
ModelType = TypeVar("ModelType")
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)
ReadSchemaType = TypeVar("ReadSchemaType", bound=BaseModel)
FilterSchemaType = TypeVar("FilterSchemaType", bound=BaseModel)
SortSchemaType = TypeVar("SortSchemaType", bound=BaseModel)


class BaseService(ABC, Generic[ModelType, CreateSchemaType, UpdateSchemaType, ReadSchemaType]):
    """
    Base service class with common Redis caching patterns.
    Provides write-through caching and cache invalidation.
    """

    def __init__(self, crud: Any):
        """Initialize service with CRUD dependency."""
        self.crud = crud

    @abstractmethod
    def get_cache_key(self, entity_id: str, **kwargs) -> str:
        """
        Get Redis cache key for the entity.
        Must be implemented by subclasses.

        Args:
            entity_id: Entity ID
            **kwargs: Additional key parameters

        Returns:
            Redis key string
        """
        pass

    @abstractmethod
    def get_cache_ttl(self) -> int:
        """
        Get cache TTL in seconds.
        Must be implemented by subclasses.

        Returns:
            TTL in seconds
        """
        pass

    async def cache_entity(
        self,
        entity: Any,
        cache_key: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Cache entity in Redis.

        Args:
            entity: Entity to cache
            cache_key: Optional cache key override
            **kwargs: Additional parameters for key generation
        """
        try:
            if not cache_key:
                cache_key = self.get_cache_key(str(entity.id), **kwargs)

            # Convert to schema and serialize
            entity_dict = self.read_schema.model_validate(
                entity).model_dump_json()

            # Cache with TTL
            await RedisClient.set(cache_key, entity_dict, expiration=self.get_cache_ttl())

            logger.debug(f"Cached entity with key: {cache_key}")
        except Exception as e:
            logger.error(f"Failed to cache entity: {e}")

    async def get_cached_entity(
        self,
        entity_id: str,
        cache_key: Optional[str] = None,
        **kwargs
    ) -> Optional[ReadSchemaType]:
        """
        Get entity from cache.

        Args:
            entity_id: Entity ID
            cache_key: Optional cache key override
            **kwargs: Additional parameters for key generation

        Returns:
            Cached entity or None
        """
        try:
            if not cache_key:
                cache_key = self.get_cache_key(entity_id, **kwargs)

            cached = await RedisClient.get(cache_key)

            if cached:
                if isinstance(cached, str):
                    cached = json.loads(cached)
                return self.read_schema.model_validate(cached)
            return None
        except Exception as e:
            logger.error(f"Failed to get cached entity {entity_id}: {e}")
            return None

    async def invalidate_cache(
        self,
        entity_id: str,
        cache_key: Optional[str] = None,
        **kwargs
    ) -> None:
        """
        Invalidate entity cache.

        Args:
            entity_id: Entity ID
            cache_key: Optional cache key override
            **kwargs: Additional parameters for key generation
        """
        try:
            if not cache_key:
                cache_key = self.get_cache_key(entity_id, **kwargs)

            await RedisClient.delete(cache_key)
            logger.debug(f"Invalidated cache key: {cache_key}")
        except Exception as e:
            logger.error(f"Failed to invalidate cache for {entity_id}: {e}")

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all cache keys matching a pattern.

        Args:
            pattern: Redis pattern (e.g., "tenant:*:monitor:*")

        Returns:
            Number of keys deleted
        """
        try:
            count = await RedisClient.delete_pattern(pattern)
            logger.info(
                f"Invalidated {count} cache keys matching pattern: {pattern}")
            return count
        except Exception as e:
            logger.error(f"Failed to invalidate pattern {pattern}: {e}")
            return 0

    @property
    @abstractmethod
    def read_schema(self) -> type[ReadSchemaType]:
        """Get the read schema class for validation."""
        pass

    async def create_with_cache(
        self,
        db: AsyncSession,
        obj_in: CreateSchemaType,
        **kwargs
    ) -> ReadSchemaType:
        """
        Create entity with write-through caching.

        Args:
            db: Database session
            obj_in: Creation data
            **kwargs: Additional parameters

        Returns:
            Created entity
        """
        # Create in database
        db_entity = await self.crud.create(db=db, object=obj_in)

        # Cache the entity
        await self.cache_entity(db_entity, **kwargs)

        return self.read_schema.model_validate(db_entity)

    async def get_with_cache(
        self,
        db: AsyncSession,
        entity_id: str,
        use_cache: bool = True,
        **kwargs
    ) -> Optional[ReadSchemaType]:
        """
        Get entity with cache support.

        Args:
            db: Database session
            entity_id: Entity ID
            use_cache: Whether to use cache
            **kwargs: Additional parameters

        Returns:
            Entity if found
        """
        # Try cache first
        if use_cache:
            cached = await self.get_cached_entity(entity_id, **kwargs)
            if cached:
                return cached

        # Fallback to database
        db_entity = await self.crud.get(db=db, id=entity_id)

        if not db_entity:
            return None

        # Refresh cache on miss
        if use_cache:
            await self.cache_entity(db_entity, **kwargs)

        return self.read_schema.model_validate(db_entity)

    async def update_with_cache(
        self,
        db: AsyncSession,
        entity_id: str,
        obj_in: UpdateSchemaType,
        **kwargs
    ) -> Optional[ReadSchemaType]:
        """
        Update entity with cache invalidation.

        Args:
            db: Database session
            entity_id: Entity ID
            obj_in: Update data
            **kwargs: Additional parameters

        Returns:
            Updated entity if found
        """
        # Update in database
        db_entity = await self.crud.update(
            db=db,
            object=obj_in,
            id=entity_id
        )

        if not db_entity:
            return None

        # Invalidate and refresh cache
        await self.invalidate_cache(entity_id, **kwargs)
        await self.cache_entity(db_entity, **kwargs)

        return self.read_schema.model_validate(db_entity)

    async def delete_with_cache(
        self,
        db: AsyncSession,
        entity_id: str,
        is_hard_delete: bool = False,
        **kwargs
    ) -> bool:
        """
        Delete entity with cache cleanup.

        Args:
            db: Database session
            entity_id: Entity ID
            is_hard_delete: Whether to hard delete
            **kwargs: Additional parameters

        Returns:
            True if deleted
        """
        # Delete from database
        deleted = await self.crud.delete(
            db=db,
            id=entity_id,
            db_obj=None,
            is_hard_delete=is_hard_delete
        )

        if deleted:
            # Remove from cache
            await self.invalidate_cache(entity_id, **kwargs)

        return bool(deleted)
