"""Factory classes for all models in the Blip0 API project.

This module provides comprehensive factory classes using factory-boy for creating
realistic test data for all models. The factories handle relationships, JSON fields,
and provide various traits for different states and configurations.

Usage:
    from tests.factories import UserFactory, TenantFactory
    from tests.factories.base import use_session

    # Configure factories to use your test session
    use_session(test_session)

    # Create test data
    user = UserFactory.create()
    tenant = TenantFactory.create_with_plan("pro")
    monitor = MonitorFactory.create_erc20_monitor(tenant_id=tenant.id)

Available Factories:
    - UserFactory: User accounts with authentication
    - TenantFactory: Multi-tenant organizations
    - TenantLimitsFactory: Resource limits per tenant
    - TierFactory: Legacy user tiers
    - MonitorFactory: Blockchain monitoring configurations
    - NetworkFactory: Blockchain network configurations
    - TriggerFactory: Base trigger configurations
    - EmailTriggerFactory: Email notification triggers
    - WebhookTriggerFactory: Webhook notification triggers
    - FilterScriptFactory: Custom filter scripts
    - UserAuditLogFactory: User action audit logs
    - BlockStateFactory: Block processing state
    - MissedBlockFactory: Missed block tracking
    - MonitorMatchFactory: Monitor execution results
    - TriggerExecutionFactory: Trigger execution history
    - ApiKeyFactory: API key authentication
    - PostFactory: User posts (legacy)
    - RateLimitFactory: API rate limiting rules

Each factory includes:
    - Realistic fake data using Faker
    - Multiple create methods for common scenarios
    - Factory traits for different states and configurations
    - Proper handling of relationships and JSON fields
    - UUID generation and hashing where appropriate
"""

# Import base configuration
# Import individual factories
from .api_key_factory import ApiKeyFactory
from .audit_factory import (
    BlockStateFactory,
    MissedBlockFactory,
    MonitorMatchFactory,
    TriggerExecutionFactory,
    UserAuditLogFactory,
)
from .base import BaseFactory, use_session
from .filter_script_factory import FilterScriptFactory
from .monitor_factory import MonitorFactory
from .network_factory import NetworkFactory
from .post_factory import PostFactory
from .rate_limit_factory import RateLimitFactory
from .tenant_factory import TenantFactory, TenantLimitsFactory
from .tier_factory import TierFactory
from .trigger_factory import EmailTriggerFactory, TriggerFactory, WebhookTriggerFactory
from .user_factory import UserFactory

# Export all factories
__all__ = [
    # Base
    "BaseFactory",
    "use_session",

    # Core models
    "UserFactory",
    "TenantFactory",
    "TenantLimitsFactory",
    "TierFactory",

    # Monitoring models
    "MonitorFactory",
    "NetworkFactory",
    "TriggerFactory",
    "EmailTriggerFactory",
    "WebhookTriggerFactory",
    "FilterScriptFactory",

    # Audit models
    "UserAuditLogFactory",
    "BlockStateFactory",
    "MissedBlockFactory",
    "MonitorMatchFactory",
    "TriggerExecutionFactory",

    # Additional models
    "ApiKeyFactory",
    "PostFactory",
    "RateLimitFactory",
]

# Factory registry for easy access
FACTORIES = {
    "user": UserFactory,
    "tenant": TenantFactory,
    "tenant_limits": TenantLimitsFactory,
    "tier": TierFactory,
    "monitor": MonitorFactory,
    "network": NetworkFactory,
    "trigger": TriggerFactory,
    "email_trigger": EmailTriggerFactory,
    "webhook_trigger": WebhookTriggerFactory,
    "filter_script": FilterScriptFactory,
    "user_audit_log": UserAuditLogFactory,
    "block_state": BlockStateFactory,
    "missed_block": MissedBlockFactory,
    "monitor_match": MonitorMatchFactory,
    "trigger_execution": TriggerExecutionFactory,
    "api_key": ApiKeyFactory,
    "post": PostFactory,
    "rate_limit": RateLimitFactory,
}


def get_factory(model_name: str) -> type[BaseFactory]:
    """
    Get a factory class by model name.

    Args:
        model_name: The name of the model (e.g., 'user', 'tenant', 'monitor')

    Returns:
        The factory class for the model

    Raises:
        KeyError: If the model name is not found

    Example:
        >>> factory_class = get_factory('user')
        >>> user = factory_class.create()
    """
    if model_name not in FACTORIES:
        available = ", ".join(sorted(FACTORIES.keys()))
        raise KeyError(f"Factory '{model_name}' not found. Available: {available}")

    return FACTORIES[model_name]


def create_sample_data(session) -> dict:
    """
    Create a complete set of sample data for testing.

    This creates a realistic dataset with proper relationships between models,
    useful for integration tests or populating test databases.

    Args:
        session: SQLAlchemy session to use for creating data

    Returns:
        Dictionary containing all created instances organized by type

    Example:
        >>> from tests.conftest import db
        >>> data = create_sample_data(db)
        >>> user = data['users'][0]
        >>> tenant = data['tenants'][0]
    """
    # Configure factories to use the session
    use_session(session)

    # Create sample data with proper relationships
    data = {}

    # 1. Create tiers first (for legacy support)
    data['tiers'] = [
        TierFactory.create_free_tier(),
        TierFactory.create_starter_tier(),
        TierFactory.create_pro_tier(),
        TierFactory.create_enterprise_tier(),
    ]

    # 2. Create tenants with different plans
    data['tenants'] = [
        TenantFactory.create_with_plan("free"),
        TenantFactory.create_with_plan("starter"),
        TenantFactory.create_with_plan("pro"),
        TenantFactory.create_enterprise(),
    ]

    # 3. Create users associated with tenants
    data['users'] = [
        UserFactory.create_with_tenant(data['tenants'][0]),
        UserFactory.create_with_tenant(data['tenants'][1]),
        UserFactory.create_superuser(),
        UserFactory.create_with_tenant(data['tenants'][2]),
    ]

    # 4. Create networks for different chains
    data['networks'] = [
        NetworkFactory.create_ethereum_mainnet(tenant_id=data['tenants'][0].id),
        NetworkFactory.create_polygon_mainnet(tenant_id=data['tenants'][0].id),
        NetworkFactory.create_arbitrum_one(tenant_id=data['tenants'][1].id),
        NetworkFactory.create_stellar_mainnet(tenant_id=data['tenants'][2].id),
    ]

    # 5. Create filter scripts
    data['filter_scripts'] = [
        FilterScriptFactory.create_large_transfer_filter(),
        FilterScriptFactory.create_defi_interaction_filter(),
        FilterScriptFactory.create_nft_activity_filter(),
    ]

    # 6. Create monitors
    data['monitors'] = [
        MonitorFactory.create_erc20_monitor(tenant_id=data['tenants'][0].id),
        MonitorFactory.create_defi_monitor(tenant_id=data['tenants'][1].id),
        MonitorFactory.create_nft_monitor(tenant_id=data['tenants'][2].id),
    ]

    # 7. Create triggers
    data['triggers'] = [
        TriggerFactory.create_email_trigger(tenant_id=data['tenants'][0].id),
        TriggerFactory.create_webhook_trigger(tenant_id=data['tenants'][1].id),
        TriggerFactory.create_email_trigger(tenant_id=data['tenants'][2].id),
    ]

    # 8. Create API keys
    data['api_keys'] = [
        ApiKeyFactory.create_full_access_key(
            user_id=data['users'][0].id,
            tenant_id=data['tenants'][0].id
        ),
        ApiKeyFactory.create_read_only_key(
            user_id=data['users'][1].id,
            tenant_id=data['tenants'][1].id
        ),
    ]

    # 9. Create rate limits
    data['rate_limits'] = [
        *RateLimitFactory.create_free_tier_limits(tier_id=data['tiers'][0].id),
        *RateLimitFactory.create_pro_tier_limits(tier_id=data['tiers'][2].id),
    ]

    # 10. Create audit data
    data['audit_logs'] = [
        UserAuditLogFactory.create_login_log(user_id=data['users'][0].id),
        UserAuditLogFactory.create_api_key_log(user_id=data['users'][1].id),
    ]

    # 11. Create monitoring state data
    data['block_states'] = [
        BlockStateFactory.create_processing_state(
            tenant_id=data['tenants'][0].id,
            network_id=data['networks'][0].id
        ),
    ]

    return data
