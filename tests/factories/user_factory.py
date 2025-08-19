"""Factory for User model."""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import factory
from faker import Faker

from src.app.models.user import User

from .base import BaseFactory

fake = Faker()


class UserFactory(BaseFactory):
    """Factory for creating User instances with realistic test data."""

    class Meta:
        model = User

    # Core user fields with realistic data
    name = factory.Faker('name')
    username = factory.Sequence(lambda n: f"user{n:04d}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")

    # Use fast bcrypt for testing (4 rounds)
    hashed_password = factory.LazyFunction(
        lambda: bcrypt.hashpw(
            b"TestPassword123!",
            bcrypt.gensalt(rounds=4)
        ).decode()
    )

    # Profile and metadata
    profile_image_url = factory.Faker('image_url')
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = None
    deleted_at = None
    is_deleted = False
    is_superuser = False

    # Tenant relationship (optional)
    tenant_id = None

    # Legacy tier relationship (optional)
    tier_id = None

    @classmethod
    def create_with_password(cls, password: str = "TestPassword123!", **kwargs: Any) -> User:
        """
        Create a user with a specific password.

        Args:
            password: The password to hash and set
            **kwargs: Additional user attributes

        Returns:
            User instance with the specified password
        """
        hashed_password = bcrypt.hashpw(
            password.encode(),
            bcrypt.gensalt(rounds=4)
        ).decode()

        return cls.create(hashed_password=hashed_password, **kwargs)

    @classmethod
    def create_superuser(cls, **kwargs: Any) -> User:
        """
        Create a superuser instance.

        Args:
            **kwargs: Additional user attributes

        Returns:
            User instance with superuser privileges
        """
        defaults = {
            'is_superuser': True,
            'username': factory.Sequence(lambda n: f"admin{n:04d}"),
            'name': fake.name() + " (Admin)",
            'email': factory.LazyAttribute(lambda obj: f"{obj.username}@admin.example.com"),
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_with_tenant(cls, tenant: Any = None, **kwargs: Any) -> User:
        """
        Create a user associated with a specific tenant.

        Args:
            tenant: Tenant instance or tenant_id UUID
            **kwargs: Additional user attributes

        Returns:
            User instance associated with the tenant
        """
        if tenant is not None:
            if hasattr(tenant, 'id'):
                kwargs['tenant_id'] = tenant.id
            else:
                kwargs['tenant_id'] = tenant

        return cls.create(**kwargs)

    @classmethod
    def create_deleted(cls, **kwargs: Any) -> User:
        """
        Create a soft-deleted user instance.

        Args:
            **kwargs: Additional user attributes

        Returns:
            Soft-deleted User instance
        """
        defaults = {
            'is_deleted': True,
            'deleted_at': factory.LazyFunction(lambda: datetime.now(UTC)),
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_recently_updated(cls, **kwargs: Any) -> User:
        """
        Create a user with recent update timestamp.

        Args:
            **kwargs: Additional user attributes

        Returns:
            User instance with recent update
        """
        defaults = {
            'updated_at': factory.LazyFunction(
                lambda: datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=60))
            ),
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different user states
    class Params:
        """Parameters for factory traits."""
        is_admin = factory.Trait(
            is_superuser=True,
            username=factory.Sequence(lambda n: f"admin{n:04d}"),
            name=factory.LazyAttribute(lambda obj: f"{fake.name()} (Admin)"),
        )

        deleted = factory.Trait(
            is_deleted=True,
            deleted_at=factory.LazyFunction(lambda: datetime.now(UTC)),
        )

        with_tenant = factory.Trait(
            tenant_id=factory.Faker('uuid4'),
        )

        recently_updated = factory.Trait(
            updated_at=factory.LazyFunction(
                lambda: datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=60))
            ),
        )
