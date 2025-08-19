"""Example test file demonstrating comprehensive factory usage.

This file serves as both documentation and validation for all factory classes.
It demonstrates proper factory usage patterns, session configuration,
and relationships between different models.
"""

import pytest
from sqlalchemy.orm import Session

from tests.factories import (
    ApiKeyFactory,
    FilterScriptFactory,
    MonitorFactory,
    NetworkFactory,
    TenantFactory,
    TriggerFactory,
    UserFactory,
    create_sample_data,
    use_session,
)


class TestFactoryBasics:
    """Test basic factory functionality."""

    def test_user_factory_basic(self, db: Session):
        """Test basic user creation."""
        use_session(db)

        # Create a basic user
        user = UserFactory.create()

        assert user.name
        assert user.username
        assert user.email
        assert user.hashed_password
        assert not user.is_superuser
        assert not user.is_deleted

        # Verify it's in the database
        db.flush()
        assert user.id is not None

    def test_user_factory_with_traits(self, db: Session):
        """Test user factory traits."""
        use_session(db)

        # Create superuser
        admin = UserFactory.create(is_admin=True)
        assert admin.is_superuser

        # Create deleted user
        deleted_user = UserFactory.create(is_deleted=True)
        assert deleted_user.is_deleted
        assert deleted_user.deleted_at is not None

    def test_tenant_factory_with_limits(self, db: Session):
        """Test tenant creation with limits."""
        use_session(db)

        # Create tenant with default limits
        tenant = TenantFactory.create()

        assert tenant.name
        assert tenant.slug
        assert tenant.plan == "free"
        assert tenant.status == "active"

        # Should have created associated limits
        db.flush()
        assert tenant.limits is not None
        assert tenant.limits.max_monitors == 5  # Free tier default

    def test_tenant_factory_different_plans(self, db: Session):
        """Test different tenant plans."""
        use_session(db)

        plans = ["free", "starter", "pro", "enterprise"]

        for plan in plans:
            tenant = TenantFactory.create_with_plan(plan)
            assert tenant.plan == plan

            db.flush()
            # Verify limits match the plan
            if plan == "pro":
                assert tenant.limits.max_monitors == 100
            elif plan == "enterprise":
                assert tenant.limits.max_monitors == 500


class TestFactoryRelationships:
    """Test relationships between factories."""

    def test_user_tenant_relationship(self, db: Session):
        """Test user-tenant relationships."""
        use_session(db)

        # Create tenant first
        tenant = TenantFactory.create()
        db.flush()

        # Create user associated with tenant
        user = UserFactory.create_with_tenant(tenant)

        assert user.tenant_id == tenant.id
        assert user in tenant.users

    def test_monitor_tenant_relationship(self, db: Session):
        """Test monitor-tenant relationships."""
        use_session(db)

        tenant = TenantFactory.create()
        db.flush()

        # Create monitor for tenant
        monitor = MonitorFactory.create(tenant_id=tenant.id)

        assert monitor.tenant_id == tenant.id
        assert monitor.name
        assert monitor.networks  # Should have networks list
        assert isinstance(monitor.addresses, list)

    def test_api_key_relationships(self, db: Session):
        """Test API key relationships."""
        use_session(db)

        tenant = TenantFactory.create()
        db.flush()

        user = UserFactory.create_with_tenant(tenant)
        db.flush()

        # Create API key for user
        api_key, raw_key = ApiKeyFactory.create_with_key(
            user_id=user.id,
            tenant_id=tenant.id
        )

        assert api_key.user_id == user.id
        assert api_key.tenant_id == tenant.id
        assert raw_key.startswith("blp0_")
        assert api_key.prefix == "blp0"

        # Verify key is hashed
        assert api_key.key_hash != raw_key
        assert len(api_key.key_hash) > 50  # bcrypt hash


class TestFactorySpecializedCreation:
    """Test specialized factory creation methods."""

    def test_monitor_specialized_types(self, db: Session):
        """Test specialized monitor types."""
        use_session(db)

        tenant = TenantFactory.create()
        db.flush()

        # Create ERC20 monitor
        erc20_monitor = MonitorFactory.create_erc20_monitor(tenant_id=tenant.id)
        assert "ERC20" in erc20_monitor.name
        assert any("transfer" in func.get("signature", "")
                  for func in erc20_monitor.match_functions)

        # Create DeFi monitor
        defi_monitor = MonitorFactory.create_defi_monitor(tenant_id=tenant.id)
        assert "DeFi" in defi_monitor.name
        assert any("swap" in func.get("signature", "")
                  for func in defi_monitor.match_functions)

        # Create NFT monitor
        nft_monitor = MonitorFactory.create_nft_monitor(tenant_id=tenant.id)
        assert "NFT" in nft_monitor.name
        assert any("Transfer" in event.get("signature", "")
                  for event in nft_monitor.match_events)

    def test_network_specialized_types(self, db: Session):
        """Test specialized network types."""
        use_session(db)

        tenant = TenantFactory.create()
        db.flush()

        # Create Ethereum mainnet
        eth_network = NetworkFactory.create_ethereum_mainnet(tenant_id=tenant.id)
        assert eth_network.name == "Ethereum Mainnet"
        assert eth_network.chain_id == 1
        assert eth_network.network_type == "EVM"

        # Create Stellar mainnet
        stellar_network = NetworkFactory.create_stellar_mainnet(tenant_id=tenant.id)
        assert stellar_network.name == "Stellar Mainnet"
        assert stellar_network.network_type == "Stellar"
        assert stellar_network.chain_id is None
        assert stellar_network.network_passphrase is not None

    def test_trigger_specialized_types(self, db: Session):
        """Test specialized trigger types."""
        use_session(db)

        tenant = TenantFactory.create()
        db.flush()

        # Create email trigger
        email_trigger = TriggerFactory.create_email_trigger(tenant_id=tenant.id)
        assert email_trigger.trigger_type == "email"

        db.flush()
        assert email_trigger.email_config is not None
        assert email_trigger.email_config.host
        assert email_trigger.email_config.sender

        # Create webhook trigger
        webhook_trigger = TriggerFactory.create_webhook_trigger(tenant_id=tenant.id)
        assert webhook_trigger.trigger_type == "webhook"

        db.flush()
        assert webhook_trigger.webhook_config is not None
        assert webhook_trigger.webhook_config.url_value
        assert webhook_trigger.webhook_config.method == "POST"


class TestFactoryComplexData:
    """Test factories with complex JSON data."""

    def test_monitor_json_fields(self, db: Session):
        """Test monitor JSON field generation."""
        use_session(db)

        monitor = MonitorFactory.create()

        # Verify JSON fields are properly structured
        assert isinstance(monitor.networks, list)
        assert len(monitor.networks) > 0

        assert isinstance(monitor.addresses, list)
        for address in monitor.addresses:
            assert "address" in address
            assert "contract_specs" in address

        assert isinstance(monitor.match_functions, list)
        for func in monitor.match_functions:
            assert "signature" in func
            assert "expression" in func

    def test_network_rpc_urls(self, db: Session):
        """Test network RPC URL generation."""
        use_session(db)

        network = NetworkFactory.create()

        assert isinstance(network.rpc_urls, list)
        assert len(network.rpc_urls) > 0

        for rpc in network.rpc_urls:
            assert "url" in rpc
            assert "type_" in rpc
            assert "weight" in rpc
            assert isinstance(rpc["weight"], int)

    def test_filter_script_validation(self, db: Session):
        """Test filter script with validation data."""
        use_session(db)

        # Create validated filter
        validated_filter = FilterScriptFactory.create_validated_filter()
        assert validated_filter.validated
        assert validated_filter.validation_errors is None
        assert validated_filter.file_hash is not None
        assert validated_filter.file_size_bytes > 0

        # Create invalid filter
        invalid_filter = FilterScriptFactory.create_invalid_filter()
        assert not invalid_filter.validated
        assert invalid_filter.validation_errors is not None
        assert "syntax" in invalid_filter.validation_errors


class TestFactoryStateVariations:
    """Test different factory states and traits."""

    def test_factory_traits(self, db: Session):
        """Test various factory traits."""
        use_session(db)

        tenant = TenantFactory.create()
        db.flush()

        # Test paused monitor
        paused_monitor = MonitorFactory.create(paused=True, tenant_id=tenant.id)
        assert paused_monitor.paused

        # Test inactive network
        inactive_network = NetworkFactory.create(inactive=True, tenant_id=tenant.id)
        assert not inactive_network.active

        # Test expired API key
        expired_key = ApiKeyFactory.create(expired=True)
        assert expired_key.expires_at is not None
        assert expired_key.is_expired()


class TestSampleDataCreation:
    """Test the sample data creation utility."""

    def test_create_sample_data(self, db: Session):
        """Test creating a complete sample dataset."""
        data = create_sample_data(db)

        # Verify all expected data types are present
        expected_keys = [
            'tiers', 'tenants', 'users', 'networks',
            'filter_scripts', 'monitors', 'triggers',
            'api_keys', 'rate_limits', 'audit_logs', 'block_states'
        ]

        for key in expected_keys:
            assert key in data
            assert len(data[key]) > 0

        # Verify relationships
        data['users'][0]
        data['tenants'][0]

        # Some users should be associated with tenants
        tenant_users = [u for u in data['users'] if u.tenant_id is not None]
        assert len(tenant_users) > 0

        # Networks should be associated with tenants
        for network in data['networks']:
            assert network.tenant_id in [t.id for t in data['tenants']]

        # API keys should be associated with users and tenants
        for api_key in data['api_keys']:
            assert api_key.user_id in [u.id for u in data['users']]
            assert api_key.tenant_id in [t.id for t in data['tenants']]


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_factories_example.py -v
    pytest.main([__file__, "-v"])
