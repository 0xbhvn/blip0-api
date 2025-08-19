"""Base factory configuration for all model factories."""

from typing import Any

import factory
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.app.core.db.database import Base


class BaseFactory(factory.alchemy.SQLAlchemyModelFactory):
    """
    Base factory for all model factories.

    Provides common configuration and utilities for creating test data
    with proper SQLAlchemy session handling and realistic data generation.
    """

    class Meta:
        abstract = True
        sqlalchemy_session_persistence = "commit"

    @classmethod
    def _setup_next_sequence(cls) -> int:
        """Set up the next sequence number to avoid conflicts."""
        return 0

    @classmethod
    def _create(cls, model_class: type[Base], *args: Any, **kwargs: Any) -> Base:
        """Override create to handle session properly."""
        # Get the session from the Meta class
        session = cls._meta.sqlalchemy_session
        if session is None:
            raise RuntimeError("No SQLAlchemy session provided to factory")

        # Create the instance
        instance = model_class(*args, **kwargs)

        # Add to session and flush to get the ID
        session.add(instance)
        session.flush()

        return instance

    @classmethod
    def _after_postgeneration(cls, obj: Base, create: bool, results: dict[str, Any] | None = None) -> None:
        """Hook called after post-generation methods."""
        if create and results:
            # Flush after post-generation to ensure relationships are saved
            session = cls._meta.sqlalchemy_session
            if session:
                session.flush()

    @classmethod
    async def create_async(cls, async_db: AsyncSession, **kwargs: Any) -> Base:
        """Create instance using async session."""
        # Temporarily set the async session for this factory
        original_session = cls._meta.sqlalchemy_session
        cls._meta.sqlalchemy_session = async_db
        try:
            instance = cls.create(**kwargs)
            await async_db.flush()
            await async_db.refresh(instance)
            return instance
        finally:
            cls._meta.sqlalchemy_session = original_session


def use_session(session: Session) -> None:
    """
    Configure all factories to use the provided SQLAlchemy session.

    This should be called in test setup to ensure all factories
    use the same test database session.

    Args:
        session: SQLAlchemy session to use for creating test data
    """
    # Import factory classes here to avoid circular imports
    from .api_key_factory import ApiKeyFactory
    from .audit_factory import (
        BlockStateFactory,
        MissedBlockFactory,
        MonitorMatchFactory,
        TriggerExecutionFactory,
        UserAuditLogFactory,
    )
    from .filter_script_factory import FilterScriptFactory
    from .monitor_factory import MonitorFactory
    from .network_factory import NetworkFactory
    from .post_factory import PostFactory
    from .rate_limit_factory import RateLimitFactory
    from .tenant_factory import TenantFactory, TenantLimitsFactory
    from .tier_factory import TierFactory
    from .trigger_factory import EmailTriggerFactory, TriggerFactory, WebhookTriggerFactory
    from .user_factory import UserFactory

    # Set session for all factory classes
    factory_classes = [
        UserFactory,
        TenantFactory,
        TenantLimitsFactory,
        TierFactory,
        MonitorFactory,
        NetworkFactory,
        TriggerFactory,
        EmailTriggerFactory,
        WebhookTriggerFactory,
        FilterScriptFactory,
        UserAuditLogFactory,
        BlockStateFactory,
        MissedBlockFactory,
        MonitorMatchFactory,
        TriggerExecutionFactory,
        ApiKeyFactory,
        PostFactory,
        RateLimitFactory,
    ]

    for factory_class in factory_classes:
        factory_class._meta.sqlalchemy_session = session
