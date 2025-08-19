"""Factories for Tenant and TenantLimits models."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import factory
from faker import Faker

from src.app.models.tenant import Tenant, TenantLimits

from .base import BaseFactory

fake = Faker()


class TenantFactory(BaseFactory):
    """Factory for creating Tenant instances with realistic test data."""

    class Meta:
        model = Tenant

    # Core tenant fields
    id = factory.LazyFunction(uuid.uuid4)
    name = factory.Faker('company')
    slug = factory.Sequence(lambda n: f"tenant-{n:04d}")

    # Plan and status
    plan = "free"
    status = "active"

    # Settings as JSONB
    settings = factory.LazyFunction(lambda: {
        "notifications": {
            "email_enabled": True,
            "webhook_enabled": False,
            "slack_enabled": False
        },
        "ui": {
            "theme": fake.random_element(["light", "dark", "auto"]),
            "timezone": fake.timezone()
        },
        "api": {
            "rate_limit_enabled": True,
            "cors_origins": [f"https://{fake.domain_name()}"]
        }
    })

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @factory.post_generation
    def create_limits(self, create: bool, extracted: Any, **kwargs: Any) -> None:
        """Create associated TenantLimits after tenant creation."""
        if not create:
            return

        # Create limits based on the plan
        plan_configs = {
            "free": {
                "max_monitors": 5,
                "max_networks": 2,
                "max_triggers": 10,
                "max_api_calls_per_hour": 100,
                "max_storage_gb": Decimal("0.5"),
                "max_concurrent_operations": 3,
            },
            "starter": {
                "max_monitors": 25,
                "max_networks": 5,
                "max_triggers": 50,
                "max_api_calls_per_hour": 1000,
                "max_storage_gb": Decimal("5.0"),
                "max_concurrent_operations": 10,
            },
            "pro": {
                "max_monitors": 100,
                "max_networks": 15,
                "max_triggers": 200,
                "max_api_calls_per_hour": 5000,
                "max_storage_gb": Decimal("25.0"),
                "max_concurrent_operations": 25,
            },
            "enterprise": {
                "max_monitors": 500,
                "max_networks": 50,
                "max_triggers": 1000,
                "max_api_calls_per_hour": 25000,
                "max_storage_gb": Decimal("100.0"),
                "max_concurrent_operations": 100,
            }
        }

        config = plan_configs.get(self.plan, plan_configs["free"])

        if extracted is True or (extracted is None and kwargs.get('with_limits', True)):
            TenantLimitsFactory.create(tenant_id=self.id, **config)

    @classmethod
    def create_with_plan(cls, plan: str = "free", **kwargs: Any) -> Tenant:
        """
        Create a tenant with a specific plan.

        Args:
            plan: The subscription plan (free, starter, pro, enterprise)
            **kwargs: Additional tenant attributes

        Returns:
            Tenant instance with the specified plan
        """
        if plan not in ["free", "starter", "pro", "enterprise"]:
            raise ValueError(f"Invalid plan: {plan}")

        return cls.create(plan=plan, **kwargs)

    @classmethod
    def create_suspended(cls, **kwargs: Any) -> Tenant:
        """
        Create a suspended tenant.

        Args:
            **kwargs: Additional tenant attributes

        Returns:
            Suspended Tenant instance
        """
        defaults = {
            'status': 'suspended',
            'settings': factory.LazyFunction(lambda: {
                "suspension": {
                    "reason": "payment_failed",
                    "suspended_at": datetime.now(UTC).isoformat(),
                    "auto_reactivate": False
                }
            })
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    @classmethod
    def create_enterprise(cls, **kwargs: Any) -> Tenant:
        """
        Create an enterprise tenant with full features.

        Args:
            **kwargs: Additional tenant attributes

        Returns:
            Enterprise Tenant instance
        """
        defaults = {
            'plan': 'enterprise',
            'settings': factory.LazyFunction(lambda: {
                "features": {
                    "custom_domains": True,
                    "sso_enabled": True,
                    "advanced_analytics": True,
                    "priority_support": True
                },
                "billing": {
                    "custom_contract": True,
                    "dedicated_support": True
                }
            })
        }
        defaults.update(kwargs)
        return cls.create(**defaults)

    # Factory traits for different tenant states
    class Params:
        """Parameters for factory traits."""
        free_plan = factory.Trait(plan="free")
        starter_plan = factory.Trait(plan="starter")
        pro_plan = factory.Trait(plan="pro")
        enterprise_plan = factory.Trait(plan="enterprise")

        suspended = factory.Trait(
            status="suspended",
            settings=factory.LazyFunction(lambda: {
                "suspension": {
                    "reason": "payment_failed",
                    "suspended_at": datetime.now(UTC).isoformat()
                }
            })
        )

        deleted = factory.Trait(status="deleted")

        with_custom_settings = factory.Trait(
            settings=factory.LazyFunction(lambda: {
                "custom": {
                    "logo_url": fake.image_url(),
                    "brand_color": fake.hex_color(),
                    "support_email": fake.company_email()
                }
            })
        )


class TenantLimitsFactory(BaseFactory):
    """Factory for creating TenantLimits instances."""

    class Meta:
        model = TenantLimits

    # Foreign key to tenant
    tenant_id = factory.Faker('uuid4')

    # Resource limits (default to free tier)
    max_monitors = 5
    max_networks = 2
    max_triggers = 10
    max_api_calls_per_hour = 100
    max_storage_gb = Decimal("0.5")
    max_concurrent_operations = 3

    # Current usage (start at zero)
    current_monitors = 0
    current_networks = 0
    current_triggers = 0
    current_storage_gb = Decimal("0.0")

    # Timestamps
    created_at = factory.LazyFunction(lambda: datetime.now(UTC))
    updated_at = factory.LazyFunction(lambda: datetime.now(UTC))

    @classmethod
    def create_for_plan(cls, plan: str, tenant_id: uuid.UUID, **kwargs: Any) -> TenantLimits:
        """
        Create limits for a specific plan.

        Args:
            plan: The subscription plan
            tenant_id: The tenant UUID
            **kwargs: Additional limit attributes

        Returns:
            TenantLimits instance for the plan
        """
        plan_configs = {
            "free": {
                "max_monitors": 5,
                "max_networks": 2,
                "max_triggers": 10,
                "max_api_calls_per_hour": 100,
                "max_storage_gb": Decimal("0.5"),
                "max_concurrent_operations": 3,
            },
            "starter": {
                "max_monitors": 25,
                "max_networks": 5,
                "max_triggers": 50,
                "max_api_calls_per_hour": 1000,
                "max_storage_gb": Decimal("5.0"),
                "max_concurrent_operations": 10,
            },
            "pro": {
                "max_monitors": 100,
                "max_networks": 15,
                "max_triggers": 200,
                "max_api_calls_per_hour": 5000,
                "max_storage_gb": Decimal("25.0"),
                "max_concurrent_operations": 25,
            },
            "enterprise": {
                "max_monitors": 500,
                "max_networks": 50,
                "max_triggers": 1000,
                "max_api_calls_per_hour": 25000,
                "max_storage_gb": Decimal("100.0"),
                "max_concurrent_operations": 100,
            }
        }

        config = plan_configs.get(plan, plan_configs["free"])
        config.update(kwargs)

        return cls.create(tenant_id=tenant_id, **config)

    @classmethod
    def create_with_usage(cls, usage_percent: float = 0.5, **kwargs: Any) -> TenantLimits:
        """
        Create limits with simulated usage.

        Args:
            usage_percent: Percentage of limits to simulate as used (0.0 to 1.0)
            **kwargs: Additional limit attributes

        Returns:
            TenantLimits instance with usage
        """
        limits = cls.create(**kwargs)

        # Set current usage based on percentage
        limits.current_monitors = int(limits.max_monitors * usage_percent)
        limits.current_networks = int(limits.max_networks * usage_percent)
        limits.current_triggers = int(limits.max_triggers * usage_percent)
        limits.current_storage_gb = Decimal(str(float(limits.max_storage_gb) * usage_percent))

        return limits

    # Factory traits for different limit states
    class Params:
        """Parameters for factory traits."""
        free_tier = factory.Trait(
            max_monitors=5,
            max_networks=2,
            max_triggers=10,
            max_api_calls_per_hour=100,
            max_storage_gb=Decimal("0.5"),
            max_concurrent_operations=3,
        )

        starter_tier = factory.Trait(
            max_monitors=25,
            max_networks=5,
            max_triggers=50,
            max_api_calls_per_hour=1000,
            max_storage_gb=Decimal("5.0"),
            max_concurrent_operations=10,
        )

        pro_tier = factory.Trait(
            max_monitors=100,
            max_networks=15,
            max_triggers=200,
            max_api_calls_per_hour=5000,
            max_storage_gb=Decimal("25.0"),
            max_concurrent_operations=25,
        )

        enterprise_tier = factory.Trait(
            max_monitors=500,
            max_networks=50,
            max_triggers=1000,
            max_api_calls_per_hour=25000,
            max_storage_gb=Decimal("100.0"),
            max_concurrent_operations=100,
        )

        near_limit = factory.Trait(
            current_monitors=factory.LazyAttribute(lambda obj: max(1, obj.max_monitors - 1)),
            current_networks=factory.LazyAttribute(lambda obj: max(1, obj.max_networks - 1)),
            current_triggers=factory.LazyAttribute(lambda obj: max(1, obj.max_triggers - 1)),
        )

        over_limit = factory.Trait(
            current_monitors=factory.LazyAttribute(lambda obj: obj.max_monitors + 1),
            current_networks=factory.LazyAttribute(lambda obj: obj.max_networks + 1),
            current_triggers=factory.LazyAttribute(lambda obj: obj.max_triggers + 1),
        )
