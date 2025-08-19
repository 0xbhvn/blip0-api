"""Factory for Tier model."""

from datetime import UTC, datetime
from typing import Any

import factory
from faker import Faker

from src.app.models.tier import Tier

from .base import BaseFactory

fake = Faker()


class TierFactory(BaseFactory):
    """Factory for creating Tier instances with realistic test data."""

    class Meta:
        model = Tier

    # Core tier fields
    name = factory.Sequence(lambda n: f"tier-{n}")

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = None

    @classmethod
    def create_free_tier(cls, **kwargs: Any) -> Tier:
        """
        Create a free tier instance.

        Args:
            **kwargs: Additional tier attributes

        Returns:
            Free Tier instance
        """
        defaults = {
            'name': 'free',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_starter_tier(cls, **kwargs: Any) -> Tier:
        """
        Create a starter tier instance.

        Args:
            **kwargs: Additional tier attributes

        Returns:
            Starter Tier instance
        """
        defaults = {
            'name': 'starter',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_pro_tier(cls, **kwargs: Any) -> Tier:
        """
        Create a pro tier instance.

        Args:
            **kwargs: Additional tier attributes

        Returns:
            Pro Tier instance
        """
        defaults = {
            'name': 'pro',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_enterprise_tier(cls, **kwargs: Any) -> Tier:
        """
        Create an enterprise tier instance.

        Args:
            **kwargs: Additional tier attributes

        Returns:
            Enterprise Tier instance
        """
        defaults = {
            'name': 'enterprise',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different tier types
    class Params:
        """Parameters for factory traits."""
        free = factory.Trait(name="free")
        starter = factory.Trait(name="starter")
        pro = factory.Trait(name="pro")
        enterprise = factory.Trait(name="enterprise")

        recently_updated = factory.Trait(
            updated_at=factory.LazyFunction(lambda: datetime.now(UTC))
        )
