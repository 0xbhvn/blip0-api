"""
Service layer for Trigger operations with Redis write-through caching.
"""

import uuid as uuid_pkg
from typing import Any, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.redis_client import redis_client
from ..crud.crud_trigger import crud_trigger
from ..models.trigger import Trigger
from ..schemas.trigger import (
    TriggerCreate,
    TriggerCreateInternal,
    TriggerRead,
    TriggerTestRequest,
    TriggerTestResult,
    TriggerUpdate,
    TriggerValidationRequest,
    TriggerValidationResult,
)
from .base_service import BaseService


class TriggerService(BaseService[Trigger, TriggerCreate, TriggerUpdate, TriggerRead]):
    """Service layer for trigger operations with Redis caching."""

    def __init__(self, crud_trigger):
        """Initialize the trigger service."""
        super().__init__(crud_trigger)
        self.crud_trigger = crud_trigger

    @property
    def read_schema(self) -> type[TriggerRead]:
        """Get the read schema class for validation."""
        return TriggerRead

    def get_cache_key(self, entity_id: str, **kwargs) -> str:
        """Generate cache key for a trigger.

        Args:
            entity_id: Trigger ID
            **kwargs: Additional parameters (tenant_id required)

        Returns:
            Redis cache key
        """
        tenant_id = kwargs.get("tenant_id")
        if not tenant_id:
            raise ValueError("tenant_id is required for trigger cache key")
        return f"tenant:{tenant_id}:trigger:{entity_id}"

    def get_cache_ttl(self) -> int:
        """Get cache TTL for triggers.

        Returns:
            Cache TTL in seconds
        """
        return 3600  # 1 hour

    async def create_trigger(
        self,
        db: AsyncSession,
        trigger_in: TriggerCreate,
        tenant_id: Union[str, uuid_pkg.UUID]
    ) -> TriggerRead:
        """Create a new trigger with Redis caching.

        Args:
            db: Database session
            trigger_in: Trigger creation data
            tenant_id: Tenant ID

        Returns:
            Created trigger
        """
        # Convert tenant_id to UUID if string
        if isinstance(tenant_id, str):
            tenant_id = uuid_pkg.UUID(tenant_id)

        # Create in PostgreSQL (source of truth)
        TriggerCreateInternal(
            **trigger_in.model_dump(),
            tenant_id=tenant_id
        )
        db_trigger = await self.crud_trigger.create_with_config(
            db=db,
            obj_in=trigger_in
        )

        # Write-through to Redis
        await self._cache_trigger(db_trigger, str(tenant_id))

        return TriggerRead.model_validate(db_trigger) if not isinstance(db_trigger, TriggerRead) else db_trigger

    async def update_trigger(
        self,
        db: AsyncSession,
        trigger_id: Union[str, uuid_pkg.UUID],
        trigger_in: TriggerUpdate,
        tenant_id: Union[str, uuid_pkg.UUID]
    ) -> Optional[TriggerRead]:
        """Update trigger and refresh cache.

        Args:
            db: Database session
            trigger_id: Trigger ID
            trigger_in: Update data
            tenant_id: Tenant ID

        Returns:
            Updated trigger or None
        """
        # Convert IDs to UUID if string
        if isinstance(trigger_id, str):
            trigger_id = uuid_pkg.UUID(trigger_id)
        if isinstance(tenant_id, str):
            tenant_id = uuid_pkg.UUID(tenant_id)

        # Update in PostgreSQL
        db_trigger = await self.crud_trigger.update_with_config(
            db=db,
            trigger_id=trigger_id,
            obj_in=trigger_in,
            tenant_id=tenant_id
        )

        if db_trigger:
            # Update Redis cache
            await self._cache_trigger(db_trigger, str(tenant_id))

        if db_trigger and not isinstance(db_trigger, TriggerRead):
            return TriggerRead.model_validate(db_trigger)
        return db_trigger  # type: ignore[no-any-return]

    async def delete_trigger(
        self,
        db: AsyncSession,
        trigger_id: Union[str, uuid_pkg.UUID],
        tenant_id: Union[str, uuid_pkg.UUID],
        is_hard_delete: bool = False
    ) -> bool:
        """Delete trigger and remove from cache.

        Args:
            db: Database session
            trigger_id: Trigger ID
            tenant_id: Tenant ID
            is_hard_delete: Whether to hard delete

        Returns:
            True if deleted, False otherwise
        """
        # Convert IDs to UUID if string
        if isinstance(trigger_id, str):
            trigger_id = uuid_pkg.UUID(trigger_id)
        if isinstance(tenant_id, str):
            tenant_id = uuid_pkg.UUID(tenant_id)

        # Delete from PostgreSQL
        deleted = False
        try:
            await self.crud_trigger.delete(
                db=db,
                id=trigger_id,
                is_hard_delete=is_hard_delete
            )
            deleted = True
        except Exception:
            deleted = False

        if deleted:
            # Remove from Redis cache
            await self._remove_from_cache(str(trigger_id), str(tenant_id))

        return deleted

    async def get_trigger_by_id(
        self,
        db: AsyncSession,
        trigger_id: Union[str, uuid_pkg.UUID],
        tenant_id: Union[str, uuid_pkg.UUID]
    ) -> Optional[TriggerRead]:
        """Get trigger by ID with cache check.

        Args:
            db: Database session
            trigger_id: Trigger ID
            tenant_id: Tenant ID

        Returns:
            Trigger or None
        """
        # Convert IDs to string for cache key
        trigger_id_str = str(trigger_id)
        tenant_id_str = str(tenant_id)

        # Check Redis cache first
        cache_key = self.get_cache_key(trigger_id_str, tenant_id=tenant_id_str)
        cached_data = await redis_client.get(cache_key)

        if cached_data:
            return TriggerRead.model_validate_json(cached_data)

        # Fallback to database
        if isinstance(trigger_id, str):
            trigger_id = uuid_pkg.UUID(trigger_id)

        db_trigger = await self.crud_trigger._get_trigger_with_config(
            db=db,
            trigger_id=trigger_id
        )

        if db_trigger:
            # Cache for next time
            await self._cache_trigger(db_trigger, tenant_id_str)

        if db_trigger and not isinstance(db_trigger, TriggerRead):
            return TriggerRead.model_validate(db_trigger)
        return db_trigger  # type: ignore[no-any-return]

    async def get_trigger_by_slug(
        self,
        db: AsyncSession,
        slug: str,
        tenant_id: Union[str, uuid_pkg.UUID]
    ) -> Optional[TriggerRead]:
        """Get trigger by slug.

        Args:
            db: Database session
            slug: Trigger slug
            tenant_id: Tenant ID

        Returns:
            Trigger or None
        """
        # Convert tenant_id to UUID if string
        if isinstance(tenant_id, str):
            tenant_id = uuid_pkg.UUID(tenant_id)

        db_trigger = await self.crud_trigger.get_by_slug(
            db=db,
            slug=slug,
            tenant_id=tenant_id
        )

        if db_trigger:
            # Get full trigger with config
            trigger_read = await self.crud_trigger._get_trigger_with_config(
                db=db,
                trigger_id=db_trigger.id
            )
            if trigger_read:
                # Cache for future use
                await self._cache_trigger(trigger_read, str(tenant_id))
                if not isinstance(trigger_read, TriggerRead):
                    return TriggerRead.model_validate(trigger_read)
                return trigger_read

        return None

    async def validate_trigger(
        self,
        db: AsyncSession,
        validation_request: TriggerValidationRequest
    ) -> TriggerValidationResult:
        """Validate trigger configuration.

        Args:
            db: Database session
            validation_request: Validation request

        Returns:
            Validation result
        """
        result = await self.crud_trigger.validate_trigger(
            db=db,
            validation_request=validation_request
        )

        # Update cache if validation status changed
        if validation_request.trigger_id:
            # Get trigger to update cache
            db_trigger = await self.crud_trigger._get_trigger_with_config(
                db=db,
                trigger_id=validation_request.trigger_id
            )
            if db_trigger and hasattr(db_trigger, "tenant_id"):
                await self._cache_trigger(db_trigger, str(db_trigger.tenant_id))

        if not isinstance(result, TriggerValidationResult):
            return TriggerValidationResult.model_validate(result)
        return result

    async def test_trigger(
        self,
        db: AsyncSession,
        test_request: TriggerTestRequest
    ) -> TriggerTestResult:
        """Test trigger with sample data.

        Args:
            db: Database session
            test_request: Test request

        Returns:
            Test result
        """
        result = await self.crud_trigger.test_trigger(
            db=db,
            test_request=test_request
        )
        return TriggerTestResult.model_validate(result) if not isinstance(result, TriggerTestResult) else result

    async def activate_trigger(
        self,
        db: AsyncSession,
        trigger_id: Union[str, uuid_pkg.UUID],
        tenant_id: Union[str, uuid_pkg.UUID]
    ) -> Optional[TriggerRead]:
        """Activate a trigger.

        Args:
            db: Database session
            trigger_id: Trigger ID
            tenant_id: Tenant ID

        Returns:
            Updated trigger or None
        """
        # Convert IDs to UUID if string
        if isinstance(trigger_id, str):
            trigger_id = uuid_pkg.UUID(trigger_id)
        if isinstance(tenant_id, str):
            tenant_id = uuid_pkg.UUID(tenant_id)

        db_trigger = await self.crud_trigger.activate_trigger(
            db=db,
            trigger_id=trigger_id,
            tenant_id=tenant_id
        )

        if db_trigger:
            # Update cache
            await self._cache_trigger(db_trigger, str(tenant_id))

        if db_trigger and not isinstance(db_trigger, TriggerRead):
            return TriggerRead.model_validate(db_trigger)
        return db_trigger  # type: ignore[no-any-return]

    async def deactivate_trigger(
        self,
        db: AsyncSession,
        trigger_id: Union[str, uuid_pkg.UUID],
        tenant_id: Union[str, uuid_pkg.UUID]
    ) -> Optional[TriggerRead]:
        """Deactivate a trigger.

        Args:
            db: Database session
            trigger_id: Trigger ID
            tenant_id: Tenant ID

        Returns:
            Updated trigger or None
        """
        # Convert IDs to UUID if string
        if isinstance(trigger_id, str):
            trigger_id = uuid_pkg.UUID(trigger_id)
        if isinstance(tenant_id, str):
            tenant_id = uuid_pkg.UUID(tenant_id)

        db_trigger = await self.crud_trigger.deactivate_trigger(
            db=db,
            trigger_id=trigger_id,
            tenant_id=tenant_id
        )

        if db_trigger:
            # Update cache
            await self._cache_trigger(db_trigger, str(tenant_id))

        if db_trigger and not isinstance(db_trigger, TriggerRead):
            return TriggerRead.model_validate(db_trigger)
        return db_trigger  # type: ignore[no-any-return]

    async def get_active_triggers_by_type(
        self,
        db: AsyncSession,
        trigger_type: str,
        tenant_id: Optional[Union[str, uuid_pkg.UUID]] = None
    ) -> list[TriggerRead]:
        """Get all active triggers of a specific type.

        Args:
            db: Database session
            trigger_type: Trigger type (email or webhook)
            tenant_id: Optional tenant filter

        Returns:
            List of active triggers
        """
        # Convert tenant_id to UUID if string
        if tenant_id and isinstance(tenant_id, str):
            tenant_id = uuid_pkg.UUID(tenant_id)

        results = await self.crud_trigger.get_active_triggers_by_type(
            db=db,
            trigger_type=trigger_type,
            tenant_id=tenant_id
        )
        return [TriggerRead.model_validate(r) if not isinstance(r, TriggerRead) else r for r in results]

    async def get_multi(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 50,
        filters: Optional[Any] = None,
        sort: Optional[Any] = None,
        tenant_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get paginated list of triggers.

        Args:
            db: Database session
            page: Page number
            size: Page size
            filters: Filter criteria
            sort: Sort criteria
            tenant_id: Tenant ID

        Returns:
            Paginated response with triggers
        """
        result: dict[str, Any] = await self.crud_trigger.get_paginated(
            db=db,
            page=page,
            size=size,
            filters=filters,
            sort=sort,
            tenant_id=tenant_id,
        )

        # Convert models to schemas
        result["items"] = [
            TriggerRead.model_validate(item) if not isinstance(item, TriggerRead) else item
            for item in result["items"]
        ]

        return result

    async def _cache_trigger(
        self,
        trigger: TriggerRead,
        tenant_id: str
    ) -> None:
        """Cache trigger to Redis.

        Args:
            trigger: Trigger to cache
            tenant_id: Tenant ID
        """
        cache_key = self.get_cache_key(str(trigger.id), tenant_id=tenant_id)
        await redis_client.set(
            cache_key,
            trigger.model_dump_json(),
            expiration=self.get_cache_ttl()
        )

    async def _remove_from_cache(
        self,
        trigger_id: str,
        tenant_id: str
    ) -> None:
        """Remove trigger from Redis cache.

        Args:
            trigger_id: Trigger ID
            tenant_id: Tenant ID
        """
        cache_key = self.get_cache_key(trigger_id, tenant_id=tenant_id)
        await redis_client.delete(cache_key)

    async def bulk_cache_triggers(
        self,
        db: AsyncSession,
        tenant_id: Union[str, uuid_pkg.UUID]
    ) -> int:
        """Cache all triggers for a tenant.

        Args:
            db: Database session
            tenant_id: Tenant ID

        Returns:
            Number of triggers cached
        """
        # Convert tenant_id to UUID if string
        if isinstance(tenant_id, str):
            tenant_id = uuid_pkg.UUID(tenant_id)

        # Get all triggers for tenant
        triggers_result = await self.crud_trigger.get_multi(
            db=db,
            filters={"tenant_id": tenant_id}
        )

        # Extract data from result
        triggers = triggers_result.get("data", []) if isinstance(
            triggers_result, dict) else []

        cached_count = 0
        for trigger in triggers:
            trigger_read = await self.crud_trigger._get_trigger_with_config(
                db=db,
                trigger_id=trigger.id
            )
            if trigger_read:
                await self._cache_trigger(trigger_read, str(tenant_id))
                cached_count += 1

        return cached_count


# Export service instance

trigger_service = TriggerService(crud_trigger)
