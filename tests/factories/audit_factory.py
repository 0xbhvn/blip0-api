"""Factories for audit models (UserAuditLog, BlockState, MissedBlock, MonitorMatch, TriggerExecution)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import factory
from faker import Faker
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.audit import (
    BlockState,
    MissedBlock,
    MonitorMatch,
    TriggerExecution,
    UserAuditLog,
)

from .base import BaseFactory

fake = Faker()


class UserAuditLogFactory(BaseFactory):
    """Factory for creating UserAuditLog instances."""

    class Meta:
        model = UserAuditLog

    # Core audit fields
    id = factory.LazyFunction(uuid.uuid4)
    user_id = factory.Faker('random_int', min=1, max=9999)
    action = factory.Iterator([
        "tenant_switch", "api_key_create", "api_key_delete", "api_key_revoke",
        "permission_grant", "permission_revoke", "password_change", "login",
        "logout", "monitor_create", "monitor_delete", "trigger_create",
        "trigger_delete", "network_create", "network_delete", "admin_access"
    ])
    resource_type = factory.Iterator([
        "tenant", "api_key", "user", "monitor", "trigger", "network", "session"
    ])

    # Optional fields
    resource_id = factory.Faker('uuid4')
    target_tenant_id = factory.Faker('uuid4')
    details = factory.LazyFunction(lambda: {
        "ip_address": fake.ipv4(),
        "user_agent": fake.user_agent(),
        "additional_info": fake.text(max_nb_chars=100)
    })
    ip_address = factory.Faker('ipv4')
    user_agent = factory.Faker('user_agent')

    # Timestamp (immutable)
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @classmethod
    def create_tenant_switch_log(cls, **kwargs: Any) -> UserAuditLog:
        """
        Create an audit log for tenant switching.

        Args:
            **kwargs: Additional audit log attributes

        Returns:
            UserAuditLog instance for tenant switch
        """
        defaults = {
            'action': 'tenant_switch',
            'resource_type': 'tenant',
            'details': factory.LazyFunction(lambda: {
                "from_tenant_id": str(uuid.uuid4()),
                "to_tenant_id": str(uuid.uuid4()),
                "reason": "admin_access"
            })
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_api_key_log(cls, action: str = "api_key_create", **kwargs: Any) -> UserAuditLog:
        """
        Create an audit log for API key operations.

        Args:
            action: The API key action (create, delete, revoke)
            **kwargs: Additional audit log attributes

        Returns:
            UserAuditLog instance for API key operation
        """
        defaults = {
            'action': action,
            'resource_type': 'api_key',
            'details': factory.LazyFunction(lambda: {
                "api_key_name": fake.catch_phrase(),
                "scopes": ["monitor:read", "trigger:read"],
                "expires_at": (datetime.now(UTC) + timedelta(days=90)).isoformat()
            })
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_login_log(cls, **kwargs: Any) -> UserAuditLog:
        """
        Create an audit log for user login.

        Args:
            **kwargs: Additional audit log attributes

        Returns:
            UserAuditLog instance for login
        """
        defaults = {
            'action': 'login',
            'resource_type': 'session',
            'details': factory.LazyFunction(lambda: {
                "login_method": fake.random_element(["password", "api_key", "oauth"]),
                "success": True,
                "session_duration": 1800  # 30 minutes
            })
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different audit types
    class Params:
        """Parameters for factory traits."""
        tenant_switch = factory.Trait(
            action="tenant_switch",
            resource_type="tenant"
        )

        api_key_create = factory.Trait(
            action="api_key_create",
            resource_type="api_key"
        )

        login = factory.Trait(
            action="login",
            resource_type="session"
        )

        admin_access = factory.Trait(
            action="admin_access",
            resource_type="admin",
            details=factory.LazyFunction(lambda: {
                "admin_panel": True,
                "elevated_permissions": ["monitor:admin", "tenant:admin"]
            })
        )


class BlockStateFactory(BaseFactory):
    """Factory for creating BlockState instances."""

    class Meta:
        model = BlockState

    # Core fields
    id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.Faker('uuid4')
    network_id = factory.Faker('uuid4')

    # Block processing state
    last_processed_block = factory.Faker('random_int', min=1000000, max=20000000)
    last_processed_at = factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(seconds=fake.random_int(min=10, max=300)))
    processing_status = factory.Iterator(["idle", "processing", "error", "paused"])
    error_count = 0

    # Performance metrics
    blocks_per_minute = factory.LazyFunction(lambda: Decimal(str(fake.random_int(min=1, max=30))))
    average_processing_time_ms = factory.Faker('random_int', min=100, max=2000)

    # Error tracking
    last_error = None
    last_error_at = None

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @classmethod
    def create_processing_state(cls, **kwargs: Any) -> BlockState:
        """
        Create a block state currently processing.

        Args:
            **kwargs: Additional block state attributes

        Returns:
            BlockState instance in processing state
        """
        defaults = {
            'processing_status': 'processing',
            'last_processed_at': factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(seconds=5)),
            'blocks_per_minute': Decimal('15.5'),
            'average_processing_time_ms': 850
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_error_state(cls, **kwargs: Any) -> BlockState:
        """
        Create a block state with errors.

        Args:
            **kwargs: Additional block state attributes

        Returns:
            BlockState instance with error state
        """
        defaults = {
            'processing_status': 'error',
            'error_count': fake.random_int(min=1, max=10),
            'last_error': 'RPC connection timeout',
            'last_error_at': factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(minutes=5)),
            'blocks_per_minute': Decimal('0.0')
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    async def create_processing_state_async(cls, async_db: AsyncSession, **kwargs: Any) -> BlockState:
        """Create a block state currently processing (async version)."""
        defaults = {
            'processing_status': 'processing',
            'last_processed_at': datetime.now(UTC) - timedelta(seconds=5),
            'blocks_per_minute': Decimal('15.5'),
            'average_processing_time_ms': 850
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_error_state_async(cls, async_db: AsyncSession, **kwargs: Any) -> BlockState:
        """Create a block state with errors (async version)."""
        defaults = {
            'processing_status': 'error',
            'error_count': fake.random_int(min=1, max=10),
            'last_error': 'RPC connection timeout',
            'last_error_at': datetime.now(UTC) - timedelta(minutes=5),
            'blocks_per_minute': Decimal('0.0')
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    # Factory traits for different states
    class Params:
        """Parameters for factory traits."""
        idle = factory.Trait(processing_status="idle")
        processing = factory.Trait(processing_status="processing")
        error = factory.Trait(processing_status="error")
        paused = factory.Trait(processing_status="paused")

        high_performance = factory.Trait(
            blocks_per_minute=factory.LazyFunction(lambda: Decimal(str(fake.random_int(min=20, max=50)))),
            average_processing_time_ms=factory.LazyFunction(lambda: fake.random_int(min=50, max=200))
        )

        with_errors = factory.Trait(
            processing_status="error",
            error_count=factory.LazyFunction(lambda: fake.random_int(min=1, max=20)),
            last_error=factory.Faker('sentence'),
            last_error_at=factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=60)))
        )


class MissedBlockFactory(BaseFactory):
    """Factory for creating MissedBlock instances."""

    class Meta:
        model = MissedBlock

    # Core fields
    id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.Faker('uuid4')
    network_id = factory.Faker('uuid4')
    block_number = factory.Faker('random_int', min=1000000, max=20000000)

    # Processing state
    retry_count = 0
    processed = False
    processed_at = None
    reason = factory.Iterator([
        "RPC timeout", "Network error", "Rate limit exceeded",
        "Invalid block data", "Service unavailable"
    ])

    # Timestamp for when block was identified as missed
    created_at = factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=60)))

    @classmethod
    def create_processed_block(cls, **kwargs: Any) -> MissedBlock:
        """
        Create a missed block that has been processed.

        Args:
            **kwargs: Additional missed block attributes

        Returns:
            MissedBlock instance that has been processed
        """
        defaults = {
            'processed': True,
            'processed_at': factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(minutes=5)),
            'retry_count': fake.random_int(min=1, max=3)
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_retry_block(cls, **kwargs: Any) -> MissedBlock:
        """
        Create a missed block with multiple retry attempts.

        Args:
            **kwargs: Additional missed block attributes

        Returns:
            MissedBlock instance with retries
        """
        defaults = {
            'retry_count': fake.random_int(min=2, max=5),
            'reason': 'Network timeout - retrying'
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    async def create_processed_block_async(cls, async_db: AsyncSession, **kwargs: Any) -> MissedBlock:
        """Create a missed block that has been processed (async version)."""
        defaults = {
            'processed': True,
            'processed_at': datetime.now(UTC) - timedelta(minutes=5),
            'retry_count': fake.random_int(min=1, max=3)
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_retry_block_async(cls, async_db: AsyncSession, **kwargs: Any) -> MissedBlock:
        """Create a missed block with multiple retry attempts (async version)."""
        defaults = {
            'retry_count': fake.random_int(min=2, max=5),
            'reason': 'Network timeout - retrying'
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    # Factory traits for different states
    class Params:
        """Parameters for factory traits."""
        is_processed = factory.Trait(
            processed=True,
            processed_at=factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=60)))
        )

        with_retries = factory.Trait(
            retry_count=factory.LazyFunction(lambda: fake.random_int(min=1, max=10))
        )

        recent = factory.Trait(
            created_at=factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=10)))
        )


class MonitorMatchFactory(BaseFactory):
    """Factory for creating MonitorMatch instances."""

    class Meta:
        model = MonitorMatch

    # Core fields
    id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.Faker('uuid4')
    monitor_id = factory.Faker('uuid4')
    network_id = factory.Faker('uuid4')
    block_number = factory.Faker('random_int', min=1000000, max=20000000)
    transaction_hash = factory.LazyFunction(lambda: f"0x{fake.hex(length=64)}")

    # Match data as JSON
    match_data = factory.LazyFunction(lambda: {
        "event": {
            "name": "Transfer",
            "args": {
                "from": fake.ethereum_address(),
                "to": fake.ethereum_address(),
                "value": str(fake.random_int(min=1000000000000000000, max=100000000000000000000))
            }
        },
        "transaction": {
            "hash": f"0x{fake.hex(length=64)}",
            "from": fake.ethereum_address(),
            "to": fake.ethereum_address(),
            "gas_used": fake.random_int(min=21000, max=500000)
        },
        "block": {
            "number": fake.random_int(min=1000000, max=20000000),
            "timestamp": int(datetime.now(UTC).timestamp())
        }
    })

    # Trigger execution tracking
    triggers_executed = factory.Faker('random_int', min=0, max=5)
    triggers_failed = factory.Faker('random_int', min=0, max=2)

    # Timestamp for when match was detected
    created_at = factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=60)))

    @classmethod
    def create_erc20_transfer_match(cls, **kwargs: Any) -> MonitorMatch:
        """
        Create a monitor match for ERC20 transfer.

        Args:
            **kwargs: Additional monitor match attributes

        Returns:
            MonitorMatch instance for ERC20 transfer
        """
        defaults = {
            'match_data': {
                "event": {
                    "name": "Transfer",
                    "signature": "Transfer(address,address,uint256)",
                    "args": {
                        "from": fake.ethereum_address(),
                        "to": fake.ethereum_address(),
                        "value": str(fake.random_int(min=1000000000000000000, max=100000000000000000000))
                    }
                },
                "token": {
                    "symbol": fake.random_element(["USDC", "USDT", "DAI", "WETH"]),
                    "decimals": 18
                },
                "value_usd": fake.random_int(min=100, max=10000)
            }
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_defi_swap_match(cls, **kwargs: Any) -> MonitorMatch:
        """
        Create a monitor match for DeFi swap.

        Args:
            **kwargs: Additional monitor match attributes

        Returns:
            MonitorMatch instance for DeFi swap
        """
        defaults = {
            'match_data': {
                "event": {
                    "name": "Swap",
                    "signature": "Swap(address,uint256,uint256,uint256,uint256,address)",
                    "args": {
                        "sender": fake.ethereum_address(),
                        "amount0In": str(fake.random_int(min=0, max=1000000000000000000)),
                        "amount1In": str(fake.random_int(min=1000000000000000000, max=10000000000000000000)),
                        "to": fake.ethereum_address()
                    }
                },
                "protocol": "uniswap_v2",
                "pair": f"{fake.random_element(['USDC', 'WETH'])}/{fake.random_element(['DAI', 'USDT'])}",
                "value_usd": fake.random_int(min=500, max=50000)
            }
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    async def create_erc20_transfer_match_async(cls, async_db: AsyncSession, **kwargs: Any) -> MonitorMatch:
        """Create a monitor match for ERC20 transfer (async version)."""
        defaults = {
            'match_data': {
                "event": {
                    "name": "Transfer",
                    "signature": "Transfer(address,address,uint256)",
                    "args": {
                        "from": fake.ethereum_address(),
                        "to": fake.ethereum_address(),
                        "value": str(fake.random_int(min=1000000000000000000, max=100000000000000000000))
                    }
                },
                "token": {
                    "symbol": fake.random_element(["USDC", "USDT", "DAI", "WETH"]),
                    "decimals": 18
                },
                "value_usd": fake.random_int(min=100, max=10000)
            }
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_defi_swap_match_async(cls, async_db: AsyncSession, **kwargs: Any) -> MonitorMatch:
        """Create a monitor match for DeFi swap (async version)."""
        defaults = {
            'match_data': {
                "event": {
                    "name": "Swap",
                    "signature": "Swap(address,uint256,uint256,uint256,uint256,address)",
                    "args": {
                        "sender": fake.ethereum_address(),
                        "amount0In": str(fake.random_int(min=0, max=1000000000000000000)),
                        "amount1In": str(fake.random_int(min=1000000000000000000, max=10000000000000000000)),
                        "to": fake.ethereum_address()
                    }
                },
                "protocol": "uniswap_v2",
                "pair": f"{fake.random_element(['USDC', 'WETH'])}/{fake.random_element(['DAI', 'USDT'])}",
                "value_usd": fake.random_int(min=500, max=50000)
            }
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    # Factory traits for different match types
    class Params:
        """Parameters for factory traits."""
        erc20_transfer = factory.Trait(
            match_data=factory.LazyFunction(lambda: {
                "event": {
                    "name": "Transfer",
                    "args": {
                        "from": fake.ethereum_address(),
                        "to": fake.ethereum_address(),
                        "value": str(fake.random_int(min=1000000000000000000, max=100000000000000000000))
                    }
                }
            })
        )

        with_triggers = factory.Trait(
            triggers_executed=factory.LazyFunction(lambda: fake.random_int(min=1, max=3)),
            triggers_failed=0
        )

        with_failed_triggers = factory.Trait(
            triggers_executed=factory.LazyFunction(lambda: fake.random_int(min=1, max=3)),
            triggers_failed=factory.LazyFunction(lambda: fake.random_int(min=1, max=2))
        )


class TriggerExecutionFactory(BaseFactory):
    """Factory for creating TriggerExecution instances."""

    class Meta:
        model = TriggerExecution

    # Core fields
    id = factory.LazyFunction(uuid.uuid4)
    tenant_id = factory.Faker('uuid4')
    trigger_id = factory.Faker('uuid4')
    monitor_match_id = factory.Faker('uuid4')
    execution_type = factory.Iterator(["email", "webhook"])
    status = factory.Iterator(["pending", "running", "success", "failed", "timeout"])
    retry_count = 0

    # Execution data as JSON
    execution_data = factory.LazyFunction(lambda: {
        "recipient": fake.email(),
        "subject": f"Monitor Alert: {fake.catch_phrase()}",
        "template_vars": {
            "monitor_name": fake.catch_phrase(),
            "network": "ethereum",
            "block_number": fake.random_int(min=1000000, max=20000000)
        }
    })

    # Timing information
    started_at = factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(seconds=fake.random_int(min=5, max=300)))
    completed_at = factory.LazyAttribute(lambda obj:
        obj.started_at + timedelta(seconds=fake.random_int(min=1, max=30))
        if obj.status in ["success", "failed", "timeout"] else None
    )
    duration_ms = factory.LazyAttribute(lambda obj:
        int((obj.completed_at - obj.started_at).total_seconds() * 1000)
        if obj.completed_at and obj.started_at else None
    )

    # Error information
    error_message = factory.LazyAttribute(lambda obj:
        fake.sentence() if obj.status == "failed" else None
    )

    # Timestamp for when execution was created
    created_at = factory.LazyFunction(lambda: datetime.now(UTC) - timedelta(minutes=fake.random_int(min=1, max=60)))

    @classmethod
    def create_email_execution(cls, **kwargs: Any) -> TriggerExecution:
        """
        Create a trigger execution for email.

        Args:
            **kwargs: Additional trigger execution attributes

        Returns:
            TriggerExecution instance for email
        """
        defaults = {
            'execution_type': 'email',
            'execution_data': {
                "smtp_host": "smtp.gmail.com",
                "recipient": fake.email(),
                "subject": f"Alert: {fake.catch_phrase()}",
                "body": fake.text(max_nb_chars=500),
                "sent_at": datetime.now(UTC).isoformat()
            }
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_webhook_execution(cls, **kwargs: Any) -> TriggerExecution:
        """
        Create a trigger execution for webhook.

        Args:
            **kwargs: Additional trigger execution attributes

        Returns:
            TriggerExecution instance for webhook
        """
        defaults = {
            'execution_type': 'webhook',
            'execution_data': {
                "url": fake.url(),
                "method": "POST",
                "headers": {
                    "Content-Type": "application/json",
                    "User-Agent": "Blip0-Monitor"
                },
                "payload": {
                    "alert": {
                        "monitor": fake.catch_phrase(),
                        "network": "ethereum",
                        "block_number": fake.random_int(min=1000000, max=20000000)
                    }
                },
                "response_code": fake.random_element([200, 201, 202])
            }
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_failed_execution(cls, **kwargs: Any) -> TriggerExecution:
        """
        Create a failed trigger execution.

        Args:
            **kwargs: Additional trigger execution attributes

        Returns:
            TriggerExecution instance with failed status
        """
        defaults = {
            'status': 'failed',
            'error_message': fake.random_element([
                "SMTP authentication failed",
                "Webhook endpoint returned 404",
                "Connection timeout",
                "Rate limit exceeded",
                "Invalid credentials"
            ]),
            'retry_count': fake.random_int(min=1, max=3)
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    async def create_email_execution_async(cls, async_db: AsyncSession, **kwargs: Any) -> TriggerExecution:
        """Create a trigger execution for email (async version)."""
        defaults = {
            'execution_type': 'email',
            'execution_data': {
                "smtp_host": "smtp.gmail.com",
                "recipient": fake.email(),
                "subject": f"Alert: {fake.catch_phrase()}",
                "body": fake.text(max_nb_chars=500),
                "sent_at": datetime.now(UTC).isoformat()
            }
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_webhook_execution_async(cls, async_db: AsyncSession, **kwargs: Any) -> TriggerExecution:
        """Create a trigger execution for webhook (async version)."""
        defaults = {
            'execution_type': 'webhook',
            'execution_data': {
                "url": fake.url(),
                "method": "POST",
                "headers": {
                    "Content-Type": "application/json",
                    "User-Agent": "Blip0-Monitor"
                },
                "payload": {
                    "alert": {
                        "monitor": fake.catch_phrase(),
                        "network": "ethereum",
                        "block_number": fake.random_int(min=1000000, max=20000000)
                    }
                },
                "response_code": fake.random_element([200, 201, 202])
            }
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    @classmethod
    async def create_failed_execution_async(cls, async_db: AsyncSession, **kwargs: Any) -> TriggerExecution:
        """Create a failed trigger execution (async version)."""
        defaults = {
            'status': 'failed',
            'error_message': fake.random_element([
                "SMTP authentication failed",
                "Webhook endpoint returned 404",
                "Connection timeout",
                "Rate limit exceeded",
                "Invalid credentials"
            ]),
            'retry_count': fake.random_int(min=1, max=3)
        }
        defaults.update(kwargs)
        return await cls.create_async(async_db, **defaults)

    # Factory traits for different execution states
    class Params:
        """Parameters for factory traits."""
        email = factory.Trait(execution_type="email")
        webhook = factory.Trait(execution_type="webhook")

        pending = factory.Trait(status="pending")
        running = factory.Trait(status="running")
        success = factory.Trait(status="success")
        failed = factory.Trait(status="failed")
        timeout = factory.Trait(status="timeout")

        with_retries = factory.Trait(
            retry_count=factory.LazyFunction(lambda: fake.random_int(min=1, max=5))
        )

        fast_execution = factory.Trait(
            duration_ms=factory.LazyFunction(lambda: fake.random_int(min=100, max=1000))
        )

        slow_execution = factory.Trait(
            duration_ms=factory.LazyFunction(lambda: fake.random_int(min=10000, max=30000))
        )
