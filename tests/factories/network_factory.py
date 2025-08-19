"""Factory for Network model."""

import uuid
from datetime import UTC, datetime
from typing import Any

import factory
from faker import Faker

from src.app.models.network import Network

from .base import BaseFactory

fake = Faker()


class NetworkFactory(BaseFactory):
    """Factory for creating Network instances with realistic test data and RPC URLs."""

    class Meta:
        model = Network

    # Core network fields
    id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.Faker('uuid4')
    name = factory.Sequence(lambda n: f"{fake.word().title()} Network {n}")
    slug = factory.Sequence(lambda n: f"network-{n:04d}")
    network_type = factory.Iterator(["EVM", "Stellar"])
    description = factory.Faker('text', max_nb_chars=200)

    # Network-specific fields
    chain_id = factory.LazyAttribute(lambda obj:
        fake.random_int(min=1, max=999999) if obj.network_type == "EVM" else None
    )
    network_passphrase = factory.LazyAttribute(lambda obj:
        f"Stellar {fake.word().title()} Network ; {fake.date().strftime('%B %Y')}"
        if obj.network_type == "Stellar" else None
    )
    block_time_ms = factory.LazyAttribute(lambda obj:
        fake.random_int(min=12000, max=15000) if obj.network_type == "EVM"
        else fake.random_int(min=5000, max=7000)  # Stellar is faster
    )

    # RPC URLs as JSONB array
    rpc_urls = factory.LazyFunction(lambda: [
        {
            "url": f"https://rpc-{fake.word()}.{fake.domain_name()}",
            "type_": "primary",
            "weight": 100
        },
        {
            "url": f"https://rpc-backup-{fake.word()}.{fake.domain_name()}",
            "type_": "backup",
            "weight": 50
        }
    ])

    # Configuration with defaults
    confirmation_blocks = factory.LazyAttribute(lambda obj:
        fake.random_int(min=1, max=3) if obj.network_type == "EVM"
        else fake.random_int(min=1, max=2)  # Stellar needs fewer confirmations
    )
    cron_schedule = "*/10 * * * * *"
    max_past_blocks = factory.LazyAttribute(lambda obj:
        fake.random_int(min=50, max=200) if obj.network_type == "EVM"
        else fake.random_int(min=100, max=500)  # Stellar blocks are faster
    )
    store_blocks = False

    # Status fields
    active = True
    validated = False
    validation_errors = None
    last_validated_at = None

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @classmethod
    def create_ethereum_mainnet(cls, **kwargs: Any) -> Network:
        """
        Create an Ethereum mainnet network configuration.

        Args:
            **kwargs: Additional network attributes

        Returns:
            Network instance configured for Ethereum mainnet
        """
        defaults = {
            'name': 'Ethereum Mainnet',
            'slug': 'ethereum-mainnet',
            'network_type': 'EVM',
            'chain_id': 1,
            'block_time_ms': 12000,
            'rpc_urls': [
                {
                    "url": "https://eth-mainnet.g.alchemy.com/v2/demo",
                    "type_": "primary",
                    "weight": 100
                },
                {
                    "url": "https://mainnet.infura.io/v3/demo",
                    "type_": "backup",
                    "weight": 80
                },
                {
                    "url": "https://rpc.ankr.com/eth",
                    "type_": "fallback",
                    "weight": 60
                }
            ],
            'confirmation_blocks': 2,
            'max_past_blocks': 100
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_polygon_mainnet(cls, **kwargs: Any) -> Network:
        """
        Create a Polygon mainnet network configuration.

        Args:
            **kwargs: Additional network attributes

        Returns:
            Network instance configured for Polygon mainnet
        """
        defaults = {
            'name': 'Polygon Mainnet',
            'slug': 'polygon-mainnet',
            'network_type': 'EVM',
            'chain_id': 137,
            'block_time_ms': 2000,
            'rpc_urls': [
                {
                    "url": "https://polygon-rpc.com",
                    "type_": "primary",
                    "weight": 100
                },
                {
                    "url": "https://matic-mainnet.chainstacklabs.com",
                    "type_": "backup",
                    "weight": 80
                }
            ],
            'confirmation_blocks': 1,
            'max_past_blocks': 200
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_arbitrum_one(cls, **kwargs: Any) -> Network:
        """
        Create an Arbitrum One network configuration.

        Args:
            **kwargs: Additional network attributes

        Returns:
            Network instance configured for Arbitrum One
        """
        defaults = {
            'name': 'Arbitrum One',
            'slug': 'arbitrum-one',
            'network_type': 'EVM',
            'chain_id': 42161,
            'block_time_ms': 250,  # Very fast blocks
            'rpc_urls': [
                {
                    "url": "https://arb1.arbitrum.io/rpc",
                    "type_": "primary",
                    "weight": 100
                },
                {
                    "url": "https://arbitrum-mainnet.infura.io/v3/demo",
                    "type_": "backup",
                    "weight": 80
                }
            ],
            'confirmation_blocks': 1,
            'max_past_blocks': 500
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_stellar_mainnet(cls, **kwargs: Any) -> Network:
        """
        Create a Stellar mainnet network configuration.

        Args:
            **kwargs: Additional network attributes

        Returns:
            Network instance configured for Stellar mainnet
        """
        defaults = {
            'name': 'Stellar Mainnet',
            'slug': 'stellar-mainnet',
            'network_type': 'Stellar',
            'chain_id': None,
            'network_passphrase': 'Public Global Stellar Network ; September 2015',
            'block_time_ms': 5000,
            'rpc_urls': [
                {
                    "url": "https://horizon.stellar.org",
                    "type_": "primary",
                    "weight": 100
                },
                {
                    "url": "https://horizon-backup.stellar.org",
                    "type_": "backup",
                    "weight": 80
                }
            ],
            'confirmation_blocks': 1,
            'max_past_blocks': 300
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_stellar_testnet(cls, **kwargs: Any) -> Network:
        """
        Create a Stellar testnet network configuration.

        Args:
            **kwargs: Additional network attributes

        Returns:
            Network instance configured for Stellar testnet
        """
        defaults = {
            'name': 'Stellar Testnet',
            'slug': 'stellar-testnet',
            'network_type': 'Stellar',
            'chain_id': None,
            'network_passphrase': 'Test SDF Network ; September 2015',
            'block_time_ms': 5000,
            'rpc_urls': [
                {
                    "url": "https://horizon-testnet.stellar.org",
                    "type_": "primary",
                    "weight": 100
                }
            ],
            'confirmation_blocks': 1,
            'max_past_blocks': 300
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_validated_network(cls, **kwargs: Any) -> Network:
        """
        Create a validated network.

        Args:
            **kwargs: Additional network attributes

        Returns:
            Validated Network instance
        """
        defaults = {
            'validated': True,
            'last_validated_at': factory.LazyFunction(lambda: datetime.now(UTC)),
            'validation_errors': None
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_invalid_network(cls, **kwargs: Any) -> Network:
        """
        Create a network with validation errors.

        Args:
            **kwargs: Additional network attributes

        Returns:
            Invalid Network instance
        """
        defaults = {
            'validated': False,
            'validation_errors': {
                "rpc_urls": ["Connection timeout to primary RPC"],
                "chain_id": ["Chain ID mismatch"],
                "configuration": ["Invalid block time configuration"]
            },
            'last_validated_at': factory.LazyFunction(lambda: datetime.now(UTC))
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_inactive_network(cls, **kwargs: Any) -> Network:
        """
        Create an inactive network.

        Args:
            **kwargs: Additional network attributes

        Returns:
            Inactive Network instance
        """
        defaults = {
            'active': False,
            'description': f"Inactive network - {fake.text(max_nb_chars=100)}"
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different network states
    class Params:
        """Parameters for factory traits."""
        evm_network = factory.Trait(
            network_type="EVM",
            chain_id=factory.LazyFunction(lambda: fake.random_int(min=1, max=999999)),
            network_passphrase=None,
            block_time_ms=factory.LazyFunction(lambda: fake.random_int(min=1000, max=15000))
        )

        stellar_network = factory.Trait(
            network_type="Stellar",
            chain_id=None,
            network_passphrase=factory.LazyFunction(
                lambda: f"Stellar {fake.word().title()} Network ; {fake.date().strftime('%B %Y')}"
            ),
            block_time_ms=factory.LazyFunction(lambda: fake.random_int(min=4000, max=6000))
        )

        mainnet = factory.Trait(
            name=factory.LazyAttribute(lambda obj: f"{fake.word().title()} Mainnet"),
            slug=factory.LazyAttribute(lambda obj: f"{obj.name.lower().replace(' ', '-')}")
        )

        testnet = factory.Trait(
            name=factory.LazyAttribute(lambda obj: f"{fake.word().title()} Testnet"),
            slug=factory.LazyAttribute(lambda obj: f"{obj.name.lower().replace(' ', '-')}")
        )

        is_validated = factory.Trait(
            validated=True,
            last_validated_at=factory.LazyFunction(lambda: datetime.now(UTC))
        )

        with_validation_errors = factory.Trait(
            validated=False,
            validation_errors=factory.LazyFunction(lambda: {
                "rpc_urls": [fake.sentence()],
                "configuration": [fake.sentence()]
            })
        )

        is_inactive = factory.Trait(active=False)

        high_throughput = factory.Trait(
            block_time_ms=factory.LazyFunction(lambda: fake.random_int(min=250, max=1000)),
            max_past_blocks=factory.LazyFunction(lambda: fake.random_int(min=500, max=1000))
        )

        with_multiple_rpcs = factory.Trait(
            rpc_urls=factory.LazyFunction(lambda: [
                {
                    "url": f"https://rpc-primary-{fake.word()}.{fake.domain_name()}",
                    "type_": "primary",
                    "weight": 100
                },
                {
                    "url": f"https://rpc-backup1-{fake.word()}.{fake.domain_name()}",
                    "type_": "backup",
                    "weight": 80
                },
                {
                    "url": f"https://rpc-backup2-{fake.word()}.{fake.domain_name()}",
                    "type_": "backup",
                    "weight": 70
                },
                {
                    "url": f"https://rpc-fallback-{fake.word()}.{fake.domain_name()}",
                    "type_": "fallback",
                    "weight": 50
                }
            ])
        )
