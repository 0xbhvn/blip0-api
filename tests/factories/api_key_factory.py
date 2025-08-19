"""Factory for APIKey model."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import factory
from faker import Faker

from src.app.models.api_key import APIKey

from .base import BaseFactory

fake = Faker()


class ApiKeyFactory(BaseFactory):
    """Factory for creating APIKey instances with realistic test data and hashed keys."""

    class Meta:
        model = APIKey

    # Core API key fields
    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Faker('catch_phrase')
    user_id = factory.Faker('random_int', min=1, max=9999)
    tenant_id = factory.Faker('uuid4')

    # Key details generated together
    prefix = "blp0"
    last_four = factory.LazyFunction(lambda: fake.lexify('????').lower())

    # Generate a realistic API key and hash it (using fast bcrypt for testing)
    key_hash = factory.LazyFunction(lambda:
        bcrypt.hashpw(
            f"blp0_{secrets.token_urlsafe(32)}".encode(),
            bcrypt.gensalt(rounds=4)
        ).decode()
    )

    # Scopes and permissions
    scopes = factory.Iterator([
        "monitor:read monitor:write",
        "monitor:read trigger:read",
        "monitor:read trigger:read network:read",
        "*",  # Full access
        "monitor:read",  # Read-only
        None  # No specific scopes
    ])

    # Status and usage
    is_active = True
    usage_count = factory.Faker('random_int', min=0, max=1000)

    # Expiration (optional)
    expires_at = None
    last_used_at = None

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @classmethod
    def create_with_key(cls, raw_key: str | None = None, **kwargs: Any) -> tuple[APIKey, str]:
        """
        Create an API key and return both the model and the raw key.

        Args:
            raw_key: Optional raw key to use, otherwise generates one
            **kwargs: Additional API key attributes

        Returns:
            Tuple of (APIKey instance, raw key string)
        """
        if raw_key is None:
            raw_key = f"blp0_{secrets.token_urlsafe(32)}"

        # Extract prefix and last four characters
        prefix = raw_key.split('_')[0] if '_' in raw_key else raw_key[:4]
        last_four = raw_key[-4:]

        # Hash the key using fast bcrypt for testing
        key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt(rounds=4)).decode()

        # Create the API key
        defaults = {
            'prefix': prefix,
            'last_four': last_four,
            'key_hash': key_hash,
        }
        defaults.update(kwargs)

        api_key = cls.create(**defaults)
        return api_key, raw_key

    @classmethod
    def create_full_access_key(cls, **kwargs: Any) -> APIKey:
        """
        Create an API key with full access permissions.

        Args:
            **kwargs: Additional API key attributes

        Returns:
            APIKey instance with full access
        """
        defaults = {
            'name': 'Full Access API Key',
            'scopes': '*',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_read_only_key(cls, **kwargs: Any) -> APIKey:
        """
        Create a read-only API key.

        Args:
            **kwargs: Additional API key attributes

        Returns:
            APIKey instance with read-only access
        """
        defaults = {
            'name': 'Read-Only API Key',
            'scopes': 'monitor:read trigger:read network:read',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_monitor_only_key(cls, **kwargs: Any) -> APIKey:
        """
        Create an API key for monitor operations only.

        Args:
            **kwargs: Additional API key attributes

        Returns:
            APIKey instance for monitor operations
        """
        defaults = {
            'name': 'Monitor API Key',
            'scopes': 'monitor:read monitor:write',
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_expired_key(cls, **kwargs: Any) -> APIKey:
        """
        Create an expired API key.

        Args:
            **kwargs: Additional API key attributes

        Returns:
            Expired APIKey instance
        """
        defaults = {
            'name': 'Expired API Key',
            'expires_at': datetime.now(UTC) - timedelta(days=1),
            'is_active': True,  # Still active but expired
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_temporary_key(cls, hours: int = 24, **kwargs: Any) -> APIKey:
        """
        Create a temporary API key that expires in the specified hours.

        Args:
            hours: Number of hours until expiration
            **kwargs: Additional API key attributes

        Returns:
            Temporary APIKey instance
        """
        defaults = {
            'name': f'Temporary API Key ({hours}h)',
            'expires_at': datetime.now(UTC) + timedelta(hours=hours),
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_inactive_key(cls, **kwargs: Any) -> APIKey:
        """
        Create an inactive API key.

        Args:
            **kwargs: Additional API key attributes

        Returns:
            Inactive APIKey instance
        """
        defaults = {
            'name': 'Inactive API Key',
            'is_active': False,
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_heavily_used_key(cls, **kwargs: Any) -> APIKey:
        """
        Create an API key with high usage.

        Args:
            **kwargs: Additional API key attributes

        Returns:
            APIKey instance with high usage
        """
        defaults = {
            'name': 'High Usage API Key',
            'usage_count': fake.random_int(min=5000, max=50000),
            'last_used_at': datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=60)),
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_for_testing(cls, **kwargs: Any) -> tuple[APIKey, str]:
        """
        Create an API key specifically for testing with a known key.

        Args:
            **kwargs: Additional API key attributes

        Returns:
            Tuple of (APIKey instance, raw key string)
        """
        raw_key = f"blp0_test_{secrets.token_urlsafe(16)}"

        defaults = {
            'name': 'Test API Key',
            'scopes': 'monitor:read monitor:write trigger:read trigger:write',
        }
        defaults.update(kwargs)

        return cls.create_with_key(raw_key, **defaults)

    # Factory traits for different API key types
    class Params:
        """Parameters for factory traits."""
        full_access = factory.Trait(
            name="Full Access API Key",
            scopes="*"
        )

        read_only = factory.Trait(
            name="Read-Only API Key",
            scopes="monitor:read trigger:read network:read"
        )

        monitor_only = factory.Trait(
            name="Monitor API Key",
            scopes="monitor:read monitor:write"
        )

        trigger_only = factory.Trait(
            name="Trigger API Key",
            scopes="trigger:read trigger:write"
        )

        expired = factory.Trait(
            expires_at=factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(days=1))
        )

        expiring_soon = factory.Trait(
            expires_at=factory.LazyFunction(lambda: datetime.now(UTC) + timedelta(days=7))
        )

        is_inactive = factory.Trait(is_active=False)

        never_used = factory.Trait(
            usage_count=0,
            last_used_at=None
        )

        recently_used = factory.Trait(
            usage_count=factory.LazyFunction(lambda: fake.random_int(min=1, max=100)),
            last_used_at=factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(hours=fake.random_int(min=1, max=24)))
        )

        heavily_used = factory.Trait(
            usage_count=factory.LazyFunction(lambda: fake.random_int(min=1000, max=10000)),
            last_used_at=factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=60)))
        )

        temporary = factory.Trait(
            name=factory.LazyFunction(lambda: f"Temporary Key - {fake.catch_phrase()}"),
            expires_at=factory.LazyFunction(lambda: datetime.now(UTC) + timedelta(hours=24))
        )

        no_scopes = factory.Trait(scopes=None)
