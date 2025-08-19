"""Factory for RateLimit model."""

from datetime import UTC, datetime
from typing import Any

import factory
from faker import Faker

from src.app.models.rate_limit import RateLimit

from .base import BaseFactory

fake = Faker()


class RateLimitFactory(BaseFactory):
    """Factory for creating RateLimit instances with realistic test data."""

    class Meta:
        model = RateLimit

    # Core rate limit fields
    tier_id = factory.Faker('random_int', min=1, max=10)
    name = factory.Sequence(lambda n: f"rate-limit-{n}")
    path = factory.Iterator([
        "/api/v1/monitors",
        "/api/v1/triggers",
        "/api/v1/networks",
        "/api/v1/users",
        "/api/v1/*",  # Wildcard
        "/api/v1/admin/*",  # Admin paths
    ])
    limit = factory.Iterator([10, 50, 100, 500, 1000, 5000])
    period = factory.Iterator([60, 300, 3600, 86400])  # 1min, 5min, 1hour, 1day

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = None

    @classmethod
    def create_free_tier_limits(cls, tier_id: int = 1, **kwargs: Any) -> list[RateLimit]:
        """
        Create rate limits for free tier.

        Args:
            tier_id: The tier ID to associate with
            **kwargs: Additional rate limit attributes

        Returns:
            List of RateLimit instances for free tier
        """
        limits = [
            cls.create(
                tier_id=tier_id,
                name="Free - Monitor API",
                path="/api/v1/monitors",
                limit=10,
                period=3600,  # 10 per hour
                **kwargs
            ),
            cls.create(
                tier_id=tier_id,
                name="Free - Trigger API",
                path="/api/v1/triggers",
                limit=5,
                period=3600,  # 5 per hour
                **kwargs
            ),
            cls.create(
                tier_id=tier_id,
                name="Free - General API",
                path="/api/v1/*",
                limit=100,
                period=3600,  # 100 per hour
                **kwargs
            ),
        ]
        return limits

    @classmethod
    def create_pro_tier_limits(cls, tier_id: int = 2, **kwargs: Any) -> list[RateLimit]:
        """
        Create rate limits for pro tier.

        Args:
            tier_id: The tier ID to associate with
            **kwargs: Additional rate limit attributes

        Returns:
            List of RateLimit instances for pro tier
        """
        limits = [
            cls.create(
                tier_id=tier_id,
                name="Pro - Monitor API",
                path="/api/v1/monitors",
                limit=100,
                period=3600,  # 100 per hour
                **kwargs
            ),
            cls.create(
                tier_id=tier_id,
                name="Pro - Trigger API",
                path="/api/v1/triggers",
                limit=50,
                period=3600,  # 50 per hour
                **kwargs
            ),
            cls.create(
                tier_id=tier_id,
                name="Pro - General API",
                path="/api/v1/*",
                limit=1000,
                period=3600,  # 1000 per hour
                **kwargs
            ),
        ]
        return limits

    @classmethod
    def create_enterprise_tier_limits(cls, tier_id: int = 3, **kwargs: Any) -> list[RateLimit]:
        """
        Create rate limits for enterprise tier.

        Args:
            tier_id: The tier ID to associate with
            **kwargs: Additional rate limit attributes

        Returns:
            List of RateLimit instances for enterprise tier
        """
        limits = [
            cls.create(
                tier_id=tier_id,
                name="Enterprise - Monitor API",
                path="/api/v1/monitors",
                limit=1000,
                period=3600,  # 1000 per hour
                **kwargs
            ),
            cls.create(
                tier_id=tier_id,
                name="Enterprise - Trigger API",
                path="/api/v1/triggers",
                limit=500,
                period=3600,  # 500 per hour
                **kwargs
            ),
            cls.create(
                tier_id=tier_id,
                name="Enterprise - General API",
                path="/api/v1/*",
                limit=10000,
                period=3600,  # 10000 per hour
                **kwargs
            ),
            cls.create(
                tier_id=tier_id,
                name="Enterprise - Admin API",
                path="/api/v1/admin/*",
                limit=500,
                period=3600,  # 500 per hour
                **kwargs
            ),
        ]
        return limits

    @classmethod
    def create_strict_limit(cls, **kwargs: Any) -> RateLimit:
        """
        Create a strict rate limit.

        Args:
            **kwargs: Additional rate limit attributes

        Returns:
            RateLimit instance with strict limits
        """
        defaults = {
            'name': 'Strict Rate Limit',
            'limit': 5,
            'period': 60,  # 5 per minute
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_generous_limit(cls, **kwargs: Any) -> RateLimit:
        """
        Create a generous rate limit.

        Args:
            **kwargs: Additional rate limit attributes

        Returns:
            RateLimit instance with generous limits
        """
        defaults = {
            'name': 'Generous Rate Limit',
            'limit': 10000,
            'period': 3600,  # 10000 per hour
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_daily_limit(cls, **kwargs: Any) -> RateLimit:
        """
        Create a daily rate limit.

        Args:
            **kwargs: Additional rate limit attributes

        Returns:
            RateLimit instance with daily limits
        """
        defaults = {
            'name': 'Daily Rate Limit',
            'limit': fake.random_int(min=100, max=10000),
            'period': 86400,  # 24 hours
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_minute_limit(cls, **kwargs: Any) -> RateLimit:
        """
        Create a per-minute rate limit.

        Args:
            **kwargs: Additional rate limit attributes

        Returns:
            RateLimit instance with per-minute limits
        """
        defaults = {
            'name': 'Per-Minute Rate Limit',
            'limit': fake.random_int(min=5, max=100),
            'period': 60,  # 1 minute
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different rate limit types
    class Params:
        """Parameters for factory traits."""
        free_tier = factory.Trait(
            limit=factory.Iterator([10, 50, 100]),
            period=3600  # 1 hour
        )

        pro_tier = factory.Trait(
            limit=factory.Iterator([100, 500, 1000]),
            period=3600  # 1 hour
        )

        enterprise_tier = factory.Trait(
            limit=factory.Iterator([1000, 5000, 10000]),
            period=3600  # 1 hour
        )

        strict = factory.Trait(
            limit=factory.Iterator([5, 10, 20]),
            period=60  # 1 minute
        )

        generous = factory.Trait(
            limit=factory.Iterator([5000, 10000, 50000]),
            period=3600  # 1 hour
        )

        daily = factory.Trait(
            period=86400  # 24 hours
        )

        hourly = factory.Trait(
            period=3600  # 1 hour
        )

        per_minute = factory.Trait(
            period=60  # 1 minute
        )

        monitor_api = factory.Trait(
            path="/api/v1/monitors",
            name="Monitor API Rate Limit"
        )

        trigger_api = factory.Trait(
            path="/api/v1/triggers",
            name="Trigger API Rate Limit"
        )

        admin_api = factory.Trait(
            path="/api/v1/admin/*",
            name="Admin API Rate Limit"
        )

        wildcard = factory.Trait(
            path="/api/v1/*",
            name="General API Rate Limit"
        )
