"""Factory for FilterScript model."""

import uuid
from datetime import UTC, datetime
from typing import Any

import factory
from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.filter_script import FilterScript

from .base import BaseFactory

fake = Faker()


class FilterScriptFactory(BaseFactory):
    """Factory for creating FilterScript instances with realistic test data."""

    class Meta:
        model = FilterScript

    # Core filter script fields
    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Sequence(lambda n: f"{fake.word().title()} Filter {n}")
    slug = factory.Sequence(lambda n: f"filter-{n:04d}")
    language = factory.Iterator(["bash", "python", "javascript"])
    description = factory.Faker('text', max_nb_chars=200)

    # Script path based on language and name
    script_path = factory.LazyAttribute(lambda obj:
        f"filters/{obj.slug}.{_get_extension(obj.language)}"
    )

    # Configuration
    arguments = factory.LazyFunction(lambda: [
        "--threshold", "1000",
        "--format", "json",
        "--verbose"
    ][:fake.random_int(min=0, max=4)])

    timeout_ms = factory.Iterator([1000, 5000, 10000, 15000])

    # Status fields
    active = True
    validated = False
    validation_errors = None
    last_validated_at = None

    # File metadata (initially None, set after validation)
    file_size_bytes = None
    file_hash = None

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @classmethod
    def create_python_filter(cls, **kwargs: Any) -> FilterScript:
        """
        Create a Python filter script.

        Args:
            **kwargs: Additional filter script attributes

        Returns:
            FilterScript instance for Python
        """
        defaults = {
            'language': 'python',
            'name': f"Python {fake.word().title()} Filter",
            'arguments': [
                "--input-format", "json",
                "--output-format", "json",
                "--log-level", "info"
            ],
            'timeout_ms': 5000
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_javascript_filter(cls, **kwargs: Any) -> FilterScript:
        """
        Create a JavaScript filter script.

        Args:
            **kwargs: Additional filter script attributes

        Returns:
            FilterScript instance for JavaScript
        """
        defaults = {
            'language': 'javascript',
            'name': f"JS {fake.word().title()} Filter",
            'arguments': [
                "--format", "json",
                "--strict"
            ],
            'timeout_ms': 3000
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_bash_filter(cls, **kwargs: Any) -> FilterScript:
        """
        Create a Bash filter script.

        Args:
            **kwargs: Additional filter script attributes

        Returns:
            FilterScript instance for Bash
        """
        defaults = {
            'language': 'bash',
            'name': f"Bash {fake.word().title()} Filter",
            'arguments': [
                "-v",  # verbose
                "-j",  # json output
            ],
            'timeout_ms': 2000
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_large_transfer_filter(cls, **kwargs: Any) -> FilterScript:
        """
        Create a filter for detecting large transfers.

        Args:
            **kwargs: Additional filter script attributes

        Returns:
            FilterScript instance for large transfer detection
        """
        defaults = {
            'name': 'Large Transfer Filter',
            'slug': 'large-transfer-filter',
            'language': 'python',
            'description': 'Filters transactions with transfer amounts above threshold',
            'arguments': [
                "--threshold", "1000000000000000000",  # 1 token in wei
                "--currency", "ETH",
                "--format", "json"
            ],
            'timeout_ms': 5000
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_defi_interaction_filter(cls, **kwargs: Any) -> FilterScript:
        """
        Create a filter for DeFi protocol interactions.

        Args:
            **kwargs: Additional filter script attributes

        Returns:
            FilterScript instance for DeFi monitoring
        """
        defaults = {
            'name': 'DeFi Interaction Filter',
            'slug': 'defi-interaction-filter',
            'language': 'javascript',
            'description': 'Filters DeFi protocol interactions and complex transactions',
            'arguments': [
                "--protocols", "uniswap,compound,aave",
                "--min-gas", "200000",
                "--format", "json"
            ],
            'timeout_ms': 10000
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_nft_activity_filter(cls, **kwargs: Any) -> FilterScript:
        """
        Create a filter for NFT activity.

        Args:
            **kwargs: Additional filter script attributes

        Returns:
            FilterScript instance for NFT monitoring
        """
        defaults = {
            'name': 'NFT Activity Filter',
            'slug': 'nft-activity-filter',
            'language': 'python',
            'description': 'Filters NFT mints, transfers, and marketplace activity',
            'arguments': [
                "--include-mints",
                "--include-sales",
                "--min-value", "0.1",
                "--format", "json"
            ],
            'timeout_ms': 7000
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_validated_filter(cls, **kwargs: Any) -> FilterScript:
        """
        Create a validated filter script with file metadata.

        Args:
            **kwargs: Additional filter script attributes

        Returns:
            Validated FilterScript instance
        """
        defaults = {
            'validated': True,
            'last_validated_at': factory.LazyFunction(lambda: datetime.now(UTC)),
            'validation_errors': None,
            'file_size_bytes': fake.random_int(min=512, max=8192),
            'file_hash': fake.sha256()
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_invalid_filter(cls, **kwargs: Any) -> FilterScript:
        """
        Create a filter script with validation errors.

        Args:
            **kwargs: Additional filter script attributes

        Returns:
            Invalid FilterScript instance
        """
        defaults = {
            'validated': False,
            'validation_errors': {
                "syntax": ["Syntax error on line 15: unexpected token"],
                "permissions": ["Script file is not executable"],
                "dependencies": ["Missing required module: requests"]
            },
            'last_validated_at': factory.LazyFunction(lambda: datetime.now(UTC)),
            'file_size_bytes': fake.random_int(min=256, max=2048),
            'file_hash': None
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_inactive_filter(cls, **kwargs: Any) -> FilterScript:
        """
        Create an inactive filter script.

        Args:
            **kwargs: Additional filter script attributes

        Returns:
            Inactive FilterScript instance
        """
        defaults = {
            'active': False,
            'description': f"Inactive filter - {fake.text(max_nb_chars=100)}"
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Async versions of all factory methods
    @classmethod
    async def create_python_filter_async(cls, async_db: AsyncSession, **kwargs: Any) -> FilterScript:
        """Create a Python filter script (async version)."""
        defaults = {
            'language': 'python',
            'name': f"Python {fake.word().title()} Filter",
            'arguments': [
                "--input-format", "json",
                "--output-format", "json",
                "--log-level", "info"
            ],
            'timeout_ms': 5000
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_javascript_filter_async(cls, async_db: AsyncSession, **kwargs: Any) -> FilterScript:
        """Create a JavaScript filter script (async version)."""
        defaults = {
            'language': 'javascript',
            'name': f"JS {fake.word().title()} Filter",
            'arguments': [
                "--format", "json",
                "--strict"
            ],
            'timeout_ms': 3000
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_bash_filter_async(cls, async_db: AsyncSession, **kwargs: Any) -> FilterScript:
        """Create a Bash filter script (async version)."""
        defaults = {
            'language': 'bash',
            'name': f"Bash {fake.word().title()} Filter",
            'arguments': [
                "-v",  # verbose
                "-j",  # json output
            ],
            'timeout_ms': 2000
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_large_transfer_filter_async(cls, async_db: AsyncSession, **kwargs: Any) -> FilterScript:
        """Create a filter for detecting large transfers (async version)."""
        defaults = {
            'name': 'Large Transfer Filter',
            'slug': 'large-transfer-filter',
            'language': 'python',
            'description': 'Filters transactions with transfer amounts above threshold',
            'arguments': [
                "--threshold", "1000000000000000000",  # 1 token in wei
                "--currency", "ETH",
                "--format", "json"
            ],
            'timeout_ms': 5000
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_defi_interaction_filter_async(cls, async_db: AsyncSession, **kwargs: Any) -> FilterScript:
        """Create a filter for DeFi protocol interactions (async version)."""
        defaults = {
            'name': 'DeFi Interaction Filter',
            'slug': 'defi-interaction-filter',
            'language': 'javascript',
            'description': 'Filters DeFi protocol interactions and complex transactions',
            'arguments': [
                "--protocols", "uniswap,compound,aave",
                "--min-gas", "200000",
                "--format", "json"
            ],
            'timeout_ms': 10000
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_nft_activity_filter_async(cls, async_db: AsyncSession, **kwargs: Any) -> FilterScript:
        """Create a filter for NFT activity (async version)."""
        defaults = {
            'name': 'NFT Activity Filter',
            'slug': 'nft-activity-filter',
            'language': 'python',
            'description': 'Filters NFT mints, transfers, and marketplace activity',
            'arguments': [
                "--include-mints",
                "--include-sales",
                "--min-value", "0.1",
                "--format", "json"
            ],
            'timeout_ms': 7000
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_validated_filter_async(cls, async_db: AsyncSession, **kwargs: Any) -> FilterScript:
        """Create a validated filter script with file metadata (async version)."""
        defaults = {
            'validated': True,
            'last_validated_at': datetime.now(UTC),
            'validation_errors': None,
            'file_size_bytes': fake.random_int(min=512, max=8192),
            'file_hash': fake.sha256()
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_invalid_filter_async(cls, async_db: AsyncSession, **kwargs: Any) -> FilterScript:
        """Create a filter script with validation errors (async version)."""
        defaults = {
            'validated': False,
            'validation_errors': {
                "syntax": ["Syntax error on line 15: unexpected token"],
                "permissions": ["Script file is not executable"],
                "dependencies": ["Missing required module: requests"]
            },
            'last_validated_at': datetime.now(UTC),
            'file_size_bytes': fake.random_int(min=256, max=2048),
            'file_hash': None
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_inactive_filter_async(cls, async_db: AsyncSession, **kwargs: Any) -> FilterScript:
        """Create an inactive filter script (async version)."""
        defaults = {
            'active': False,
            'description': f"Inactive filter - {fake.text(max_nb_chars=100)}"
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    # Factory traits for different filter script states
    class Params:
        """Parameters for factory traits."""
        python = factory.Trait(
            language="python",
            script_path=factory.LazyAttribute(lambda obj: f"filters/{obj.slug}.py"),
            timeout_ms=5000
        )

        javascript = factory.Trait(
            language="javascript",
            script_path=factory.LazyAttribute(lambda obj: f"filters/{obj.slug}.js"),
            timeout_ms=3000
        )

        bash = factory.Trait(
            language="bash",
            script_path=factory.LazyAttribute(lambda obj: f"filters/{obj.slug}.sh"),
            timeout_ms=2000
        )

        is_validated = factory.Trait(
            validated=True,
            last_validated_at=factory.LazyFunction(lambda: datetime.now(UTC)),
            file_size_bytes=factory.LazyFunction(lambda: fake.random_int(min=512, max=8192)),
            file_hash=factory.Faker('sha256')
        )

        with_validation_errors = factory.Trait(
            validated=False,
            validation_errors=factory.LazyFunction(lambda: {
                "general": [fake.sentence()]
            })
        )

        is_inactive = factory.Trait(active=False)

        fast_timeout = factory.Trait(timeout_ms=1000)
        long_timeout = factory.Trait(timeout_ms=30000)

        complex_filter = factory.Trait(
            arguments=factory.LazyFunction(lambda: [
                "--threshold", str(fake.random_int(min=1000, max=1000000)),
                "--network", fake.random_element(["ethereum", "polygon", "arbitrum"]),
                "--format", "json",
                "--verbose",
                "--include-metadata"
            ]),
            timeout_ms=15000
        )

        simple_filter = factory.Trait(
            arguments=factory.LazyFunction(lambda: [
                "--format", "json"
            ]),
            timeout_ms=1000
        )


def _get_extension(language: str) -> str:
    """Get file extension for a programming language."""
    extensions = {
        "python": "py",
        "javascript": "js",
        "bash": "sh"
    }
    return extensions.get(language, "txt")
