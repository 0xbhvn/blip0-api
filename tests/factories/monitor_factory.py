"""Factory for Monitor model."""

import uuid
from datetime import UTC, datetime
from typing import Any

import factory
from faker import Faker

from src.app.models.monitor import Monitor

from .base import BaseFactory

fake = Faker()


class MonitorFactory(BaseFactory):
    """Factory for creating Monitor instances with realistic test data and complex JSON fields."""

    class Meta:
        model = Monitor

    # Core monitor fields
    id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.Faker('uuid4')
    name = factory.Faker('catch_phrase')
    slug = factory.Sequence(lambda n: f"monitor-{n:04d}")
    description = factory.Faker('text', max_nb_chars=200)

    # Status and control
    paused = False
    active = True
    validated = False
    validation_errors = None
    last_validated_at = None

    # Network and addresses (JSONB arrays)
    networks = factory.LazyFunction(lambda: [
        fake.random_element(["ethereum", "polygon", "bsc", "arbitrum", "optimism"]),
        fake.random_element(["avalanche", "fantom", "moonbeam", "gnosis"])
    ][:fake.random_int(min=1, max=3)])

    addresses = factory.LazyFunction(lambda: [
        {
            "address": fake.ethereum_address(),
            "contract_specs": {
                "abi": [
                    {
                        "type": "function",
                        "name": "transfer",
                        "inputs": [
                            {"name": "to", "type": "address"},
                            {"name": "value", "type": "uint256"}
                        ]
                    }
                ],
                "name": f"{fake.word().title()} Token"
            }
        }
        for _ in range(fake.random_int(min=1, max=3))
    ])

    # Match conditions (JSONB arrays)
    match_functions = factory.LazyFunction(lambda: [
        {
            "signature": "transfer(address,uint256)",
            "expression": f"args.value > {fake.random_int(min=1000, max=1000000)}",
            "description": "Large transfers"
        },
        {
            "signature": "approve(address,uint256)",
            "expression": "args.value > 0",
            "description": "Token approvals"
        }
    ][:fake.random_int(min=0, max=2)])

    match_events = factory.LazyFunction(lambda: [
        {
            "signature": "Transfer(address,address,uint256)",
            "expression": f"args.value > {fake.random_int(min=1000, max=1000000)}",
            "description": "Large transfer events"
        },
        {
            "signature": "Approval(address,address,uint256)",
            "expression": "args.spender != args.owner",
            "description": "Token approval events"
        }
    ][:fake.random_int(min=0, max=2)])

    match_transactions = factory.LazyFunction(lambda: [
        {
            "status": "success",
            "expression": f"transaction.value > {fake.random_int(min=1, max=100)}",
            "description": "High-value successful transactions"
        }
    ][:fake.random_int(min=0, max=1)])

    # Trigger configuration (JSONB arrays)
    trigger_conditions = factory.LazyFunction(lambda: [
        {
            "type": "filter",
            "script": "large_transfer_filter",
            "params": {
                "threshold": fake.random_int(min=1000, max=1000000),
                "currency": "USD"
            }
        }
    ][:fake.random_int(min=0, max=2)])

    triggers = factory.LazyFunction(lambda: [
        f"email-{fake.random_int(min=1, max=100)}",
        f"webhook-{fake.random_int(min=1, max=100)}"
    ][:fake.random_int(min=0, max=2)])

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @classmethod
    def create_erc20_monitor(cls, **kwargs: Any) -> Monitor:
        """
        Create a monitor specifically for ERC20 token monitoring.

        Args:
            **kwargs: Additional monitor attributes

        Returns:
            Monitor instance configured for ERC20 tokens
        """
        defaults = {
            'name': f"ERC20 {fake.word().title()} Monitor",
            'description': "Monitor for ERC20 token transfers and approvals",
            'networks': ["ethereum", "polygon"],
            'match_functions': [
                {
                    "signature": "transfer(address,uint256)",
                    "expression": "args.value > 1000000000000000000",  # > 1 token
                    "description": "Large token transfers"
                }
            ],
            'match_events': [
                {
                    "signature": "Transfer(address,address,uint256)",
                    "expression": "args.value > 1000000000000000000",
                    "description": "Large transfer events"
                }
            ]
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_defi_monitor(cls, **kwargs: Any) -> Monitor:
        """
        Create a monitor for DeFi protocol interactions.

        Args:
            **kwargs: Additional monitor attributes

        Returns:
            Monitor instance configured for DeFi monitoring
        """
        defaults = {
            'name': f"DeFi {fake.word().title()} Monitor",
            'description': "Monitor for DeFi protocol interactions",
            'networks': ["ethereum", "arbitrum", "optimism"],
            'match_functions': [
                {
                    "signature": "swap(uint256,uint256,address[],address,uint256)",
                    "expression": "args.amountIn > 1000000000000000000",
                    "description": "Large swaps"
                },
                {
                    "signature": "addLiquidity(address,address,uint256,uint256,uint256,uint256,address,uint256)",
                    "expression": "args.amountADesired > 1000000000000000000",
                    "description": "Large liquidity additions"
                }
            ],
            'match_events': [
                {
                    "signature": "Swap(address,uint256,uint256,uint256,uint256,address)",
                    "expression": "args.amount0In > 0 OR args.amount1In > 0",
                    "description": "DEX swaps"
                }
            ]
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_nft_monitor(cls, **kwargs: Any) -> Monitor:
        """
        Create a monitor for NFT transfers and mints.

        Args:
            **kwargs: Additional monitor attributes

        Returns:
            Monitor instance configured for NFT monitoring
        """
        defaults = {
            'name': f"NFT {fake.word().title()} Monitor",
            'description': "Monitor for NFT transfers and mints",
            'networks': ["ethereum"],
            'match_events': [
                {
                    "signature": "Transfer(address,address,uint256)",
                    "expression": "args.from == '0x0000000000000000000000000000000000000000'",
                    "description": "NFT mints (from zero address)"
                },
                {
                    "signature": "Transfer(address,address,uint256)",
                    "expression": "args.from != '0x0000000000000000000000000000000000000000' AND args.to != '0x0000000000000000000000000000000000000000'",
                    "description": "NFT transfers"
                }
            ]
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_paused_monitor(cls, **kwargs: Any) -> Monitor:
        """
        Create a paused monitor.

        Args:
            **kwargs: Additional monitor attributes

        Returns:
            Paused Monitor instance
        """
        defaults = {
            'paused': True,
            'description': f"Paused monitor - {fake.text(max_nb_chars=100)}"
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_validated_monitor(cls, **kwargs: Any) -> Monitor:
        """
        Create a validated monitor.

        Args:
            **kwargs: Additional monitor attributes

        Returns:
            Validated Monitor instance
        """
        defaults = {
            'validated': True,
            'last_validated_at': factory.LazyFunction(lambda: datetime.now(UTC)),
            'validation_errors': None
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_invalid_monitor(cls, **kwargs: Any) -> Monitor:
        """
        Create a monitor with validation errors.

        Args:
            **kwargs: Additional monitor attributes

        Returns:
            Invalid Monitor instance
        """
        defaults = {
            'validated': False,
            'validation_errors': {
                "networks": ["Invalid network: nonexistent"],
                "addresses": ["Invalid address format: 0xinvalid"],
                "match_functions": ["Invalid function signature: malformed()"]
            },
            'last_validated_at': factory.LazyFunction(lambda: datetime.now(UTC))
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different monitor states
    class Params:
        """Parameters for factory traits."""
        is_paused = factory.Trait(paused=True)
        is_inactive = factory.Trait(active=False)
        is_validated = factory.Trait(
            validated=True,
            last_validated_at=factory.LazyFunction(lambda: datetime.now(UTC))
        )

        with_validation_errors = factory.Trait(
            validated=False,
            validation_errors=factory.LazyFunction(lambda: {
                "general": [fake.sentence()]
            })
        )

        erc20_token = factory.Trait(
            name=factory.LazyAttribute(lambda obj: f"ERC20 {fake.word().title()} Monitor"),
            networks=["ethereum", "polygon"],
            match_functions=factory.LazyFunction(lambda: [
                {
                    "signature": "transfer(address,uint256)",
                    "expression": "args.value > 1000000000000000000"
                }
            ])
        )

        defi_protocol = factory.Trait(
            name=factory.LazyAttribute(lambda obj: f"DeFi {fake.word().title()} Monitor"),
            networks=["ethereum", "arbitrum"],
            match_functions=factory.LazyFunction(lambda: [
                {
                    "signature": "swap(uint256,uint256,address[],address,uint256)",
                    "expression": "args.amountIn > 1000000000000000000"
                }
            ])
        )

        nft_collection = factory.Trait(
            name=factory.LazyAttribute(lambda obj: f"NFT {fake.word().title()} Monitor"),
            networks=["ethereum"],
            match_events=factory.LazyFunction(lambda: [
                {
                    "signature": "Transfer(address,address,uint256)",
                    "expression": "args.from == '0x0000000000000000000000000000000000000000'"
                }
            ])
        )
