"""Factory for Post model."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import factory
from faker import Faker

from src.app.models.post import Post

from .base import BaseFactory

fake = Faker()


class PostFactory(BaseFactory):
    """Factory for creating Post instances with realistic test data."""

    class Meta:
        model = Post

    # Core post fields
    uuid = factory.LazyFunction(uuid.uuid4)
    created_by_user_id = factory.Faker('random_int', min=1, max=9999)
    title = factory.Faker('catch_phrase')
    text = factory.Faker('text', max_nb_chars=1000)

    # Optional media
    media_url = factory.Iterator([
        None,  # No media
        factory.Faker('image_url'),  # Image
        factory.Faker('image_url'),  # Another image
    ])

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = None
    deleted_at = None
    is_deleted = False

    @classmethod
    def create_with_media(cls, **kwargs: Any) -> Post:
        """
        Create a post with media attached.

        Args:
            **kwargs: Additional post attributes

        Returns:
            Post instance with media
        """
        defaults = {
            'media_url': fake.image_url(),
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_long_post(cls, **kwargs: Any) -> Post:
        """
        Create a post with long content.

        Args:
            **kwargs: Additional post attributes

        Returns:
            Post instance with long content
        """
        defaults = {
            'text': fake.text(max_nb_chars=5000),
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_deleted_post(cls, **kwargs: Any) -> Post:
        """
        Create a soft-deleted post.

        Args:
            **kwargs: Additional post attributes

        Returns:
            Soft-deleted Post instance
        """
        defaults = {
            'is_deleted': True,
            'deleted_at': factory.LazyFunction(lambda: datetime.now(UTC)),
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_updated_post(cls, **kwargs: Any) -> Post:
        """
        Create a post that has been updated.

        Args:
            **kwargs: Additional post attributes

        Returns:
            Updated Post instance
        """
        defaults = {
            'updated_at': factory.LazyFunction(lambda: datetime.now(UTC)),
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different post states
    class Params:
        """Parameters for factory traits."""
        with_media = factory.Trait(
            media_url=factory.Faker('image_url')
        )

        long_content = factory.Trait(
            text=factory.LazyFunction(lambda: fake.text(max_nb_chars=5000))
        )

        short_content = factory.Trait(
            text=factory.LazyFunction(lambda: fake.text(max_nb_chars=100))
        )

        deleted = factory.Trait(
            is_deleted=True,
            deleted_at=factory.LazyFunction(lambda: datetime.now(UTC))
        )

        updated = factory.Trait(
            updated_at=factory.LazyFunction(lambda: datetime.now(UTC))
        )

        recent = factory.Trait(
            created_at=factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(hours=fake.random_int(min=1, max=24)))
        )

        old = factory.Trait(
            created_at=factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(days=fake.random_int(min=30, max=365)))
        )
