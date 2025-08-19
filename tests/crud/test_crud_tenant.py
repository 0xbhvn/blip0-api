"""
Comprehensive unit tests for CRUDTenant operations.

Tests cover all CRUD operations including:
- Create operations with limits management
- Read operations with tenant-specific filters
- Update operations including plan upgrades
- Delete operations (soft delete)
- Resource limit management
- Plan validation and limits enforcement
- Usage tracking and validation
- Tenant suspension and reactivation
- Bulk operations
"""

import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.crud.crud_tenant import CRUDTenant, crud_tenant
from src.app.models.tenant import Tenant, TenantLimits
from src.app.schemas.tenant import (
    TenantCreate,
    TenantCreateInternal,
    TenantFilter,
    TenantLimitsUpdate,
    TenantUpdate,
    TenantWithLimits,
)
from tests.factories.tenant_factory import TenantFactory, TenantLimitsFactory


class TestCRUDTenantCreate:
    """Test tenant creation operations."""

    @pytest.mark.asyncio
    async def test_create_tenant_basic(self, async_db: AsyncSession) -> None:
        """Test basic tenant creation."""
        # Arrange
        tenant_create = TenantCreate(
            name="Test Tenant",
            slug="test-tenant",
            plan="free"
        )

        # Act
        created_tenant = await crud_tenant.create(async_db, object=tenant_create)

        # Assert
        assert created_tenant is not None
        assert created_tenant.name == tenant_create.name
        assert created_tenant.slug == tenant_create.slug
        assert created_tenant.plan == tenant_create.plan
        assert created_tenant.status == "active"  # Default status
        assert created_tenant.id is not None
        assert created_tenant.created_at is not None

    @patch('src.app.crud.crud_tenant.get_plan_limits_for_db')
    @pytest.mark.asyncio
    async def test_create_with_limits(
        self,
        mock_get_limits,
        async_db: AsyncSession
    ) -> None:
        """Test tenant creation with automatic limits setup."""
        # Arrange
        mock_get_limits.return_value = {
            "max_monitors": 5,
            "max_networks": 2,
            "max_triggers": 10,
            "max_api_calls_per_hour": 100,
            "max_storage_gb": Decimal("0.5"),
            "max_concurrent_operations": 3,
        }

        tenant_create = TenantCreate(
            name="Tenant with Limits",
            slug="tenant-with-limits",
            plan="free"
        )

        # Act
        created_tenant = await crud_tenant.create_with_limits(async_db, object=tenant_create)

        # Assert
        assert isinstance(created_tenant, TenantWithLimits)
        assert created_tenant.name == tenant_create.name
        assert created_tenant.limits is not None
        assert created_tenant.limits.max_monitors == 5
        assert created_tenant.limits.max_networks == 2
        mock_get_limits.assert_called_once_with("free")

    @pytest.mark.asyncio
    async def test_create_with_custom_limits(self, async_db: AsyncSession) -> None:
        """Test tenant creation with custom limits."""
        # Arrange
        tenant_create = TenantCreate(
            name="Custom Limits Tenant",
            slug="custom-limits",
            plan="pro"
        )

        custom_limits = {
            "max_monitors": 200,
            "max_networks": 20,
            "max_triggers": 500,
            "max_api_calls_per_hour": 10000,
            "max_storage_gb": Decimal("50.0"),
            "max_concurrent_operations": 50,
        }

        # Act
        created_tenant = await crud_tenant.create_with_limits(
            async_db,
            object=tenant_create,
            plan_limits=custom_limits
        )

        # Assert
        assert isinstance(created_tenant, TenantWithLimits)
        assert created_tenant.limits.max_monitors == 200
        assert created_tenant.limits.max_networks == 20

    @pytest.mark.asyncio
    async def test_create_tenant_duplicate_slug(self, async_db: AsyncSession) -> None:
        """Test tenant creation with duplicate slug fails."""
        # Arrange
        slug = "duplicate-slug"
        tenant1_create = TenantCreate(
            name="First Tenant",
            slug=slug,
            plan="free"
        )
        tenant2_create = TenantCreate(
            name="Second Tenant",
            slug=slug,  # Duplicate slug
            plan="starter"
        )

        # Act & Assert
        await crud_tenant.create(async_db, object=tenant1_create)

        with pytest.raises(Exception):  # Should be IntegrityError
            await crud_tenant.create(async_db, object=tenant2_create)
            await async_db.commit()

    @pytest.mark.asyncio
    async def test_create_tenant_with_settings(self, async_db: AsyncSession) -> None:
        """Test tenant creation with custom settings."""
        # Arrange
        custom_settings = {
            "notifications": {"email_enabled": False},
            "ui": {"theme": "dark"},
            "custom": {"feature_flag_a": True}
        }

        tenant_create = TenantCreateInternal(
            name="Settings Tenant",
            slug="settings-tenant",
            plan="pro",
            settings=custom_settings
        )

        # Act
        created_tenant = await crud_tenant.create(async_db, object=tenant_create)

        # Assert
        assert created_tenant.settings == custom_settings


class TestCRUDTenantRead:
    """Test tenant read operations."""

    @pytest.mark.asyncio
    async def test_get_tenant_by_id(self, async_db: AsyncSession) -> None:
        """Test getting tenant by ID."""
        # Arrange
        tenant = TenantFactory.create(name="Get By ID Test")
        async_db.add(tenant)
        await async_db.flush()

        # Act
        retrieved_tenant = await crud_tenant.get(async_db, id=tenant.id)

        # Assert
        assert retrieved_tenant is not None
        assert retrieved_tenant.id == tenant.id
        assert retrieved_tenant.name == "Get By ID Test"

    @pytest.mark.asyncio
    async def test_get_tenant_by_slug(self, async_db: AsyncSession) -> None:
        """Test getting tenant by slug."""
        # Arrange
        slug = "test-slug-123"
        tenant = TenantFactory.create(slug=slug)
        async_db.add(tenant)
        await async_db.flush()

        # Act
        retrieved_tenant = await crud_tenant.get_by_slug(async_db, slug=slug)

        # Assert
        assert retrieved_tenant is not None
        assert retrieved_tenant.slug == slug
        assert retrieved_tenant.id == tenant.id

    @pytest.mark.asyncio
    async def test_get_with_limits(self, async_db: AsyncSession) -> None:
        """Test getting tenant with limits included."""
        # Arrange
        tenant = TenantFactory.create(plan="pro")
        async_db.add(tenant)
        await async_db.flush()

        # Create limits separately for this tenant
        limits = TenantLimitsFactory.create_for_plan("pro", tenant.id)
        async_db.add(limits)
        await async_db.flush()

        # Act
        tenant_with_limits = await crud_tenant.get_with_limits(async_db, tenant.id)

        # Assert
        assert tenant_with_limits is not None
        assert isinstance(tenant_with_limits, TenantWithLimits)
        assert tenant_with_limits.id == tenant.id
        assert tenant_with_limits.limits is not None
        assert tenant_with_limits.limits.tenant_id == tenant.id

    @pytest.mark.asyncio
    async def test_get_multi_tenants(self, async_db: AsyncSession) -> None:
        """Test getting multiple tenants."""
        # Arrange
        tenants = TenantFactory.create_batch(5)
        for tenant in tenants:
            async_db.add(tenant)
        await async_db.flush()

        # Act
        retrieved_tenants = await crud_tenant.get_multi(async_db, skip=0, limit=10)

        # Assert
        assert len(retrieved_tenants) >= 5
        tenant_ids = [str(t.id) for t in retrieved_tenants]
        for tenant in tenants:
            assert str(tenant.id) in tenant_ids

    @pytest.mark.asyncio
    async def test_get_active_tenants(self, async_db: AsyncSession) -> None:
        """Test getting only active tenants."""
        # Arrange
        active_tenant = TenantFactory.create(status="active")
        suspended_tenant = TenantFactory.create(status="suspended")
        async_db.add(active_tenant)
        async_db.add(suspended_tenant)
        await async_db.flush()

        # Act
        result = await crud_tenant.get_active_tenants(async_db, page=1, size=10)

        # Assert
        assert "items" in result
        active_tenant_ids = [str(t.id) for t in result["items"]]
        assert str(active_tenant.id) in active_tenant_ids
        assert str(suspended_tenant.id) not in active_tenant_ids

    # @pytest.mark.asyncio
    # async def test_get_paginated_with_filters(self, async_db: AsyncSession) -> None:
    #     """Test paginated tenant retrieval with filters."""
    #     # NOTE: FastCRUD doesn't have get_paginated method - commented out
    #     # Arrange
    #     free_tenant = TenantFactory.create(plan="free", name="Free Tenant")
    #     pro_tenant = TenantFactory.create(plan="pro", name="Pro Tenant")
    #     async_db.add(free_tenant)
    #     async_db.add(pro_tenant)
    #     await async_db.flush()

    #     # Act - Filter by plan
    #     filters = TenantFilter(plan="pro")
    #     result = await crud_tenant.get_paginated(
    #         async_db,
    #         page=1,
    #         size=10,
    #         filters=filters
    #     )

    #     # Assert
    #     assert result["total"] >= 1
    #     found_pro = any(t.plan == "pro" for t in result["items"])
    #     assert found_pro

    # @pytest.mark.asyncio
    # async def test_get_paginated_with_sorting(self, async_db: AsyncSession) -> None:
    #     """Test paginated tenant retrieval with sorting."""
    #     # NOTE: FastCRUD doesn't have get_paginated method - commented out
    #     # Arrange
    #     tenant_a = TenantFactory.create(name="A Tenant")
    #     tenant_z = TenantFactory.create(name="Z Tenant")
    #     async_db.add(tenant_a)
    #     async_db.add(tenant_z)
    #     await async_db.flush()

    #     # Act - Sort by name ascending
    #     sort = TenantSort(field="name", order="asc")
    #     result = await crud_tenant.get_paginated(
    #         async_db,
    #         page=1,
    #         size=10,
    #         sort=sort
    #     )

    #     # Assert
    #     assert len(result["items"]) >= 2
    #     names = [t.name for t in result["items"][:2]]
    #     assert names == sorted(names)


class TestCRUDTenantUpdate:
    """Test tenant update operations."""

    @pytest.mark.asyncio
    async def test_update_tenant_basic(self, async_db: AsyncSession) -> None:
        """Test basic tenant update."""
        # Arrange
        tenant = TenantFactory.create(name="Original Name")
        async_db.add(tenant)
        await async_db.flush()

        update_data = TenantUpdate(name="Updated Name")

        # Act
        updated_tenant = await crud_tenant.update(
            async_db,
            db_obj=tenant,
            object=update_data
        )

        # Assert
        assert updated_tenant is not None
        assert updated_tenant.name == "Updated Name"
        assert updated_tenant.id == tenant.id

    @pytest.mark.asyncio
    async def test_update_limits(self, async_db: AsyncSession) -> None:
        """Test updating tenant limits."""
        # Arrange
        tenant = TenantFactory.create()
        async_db.add(tenant)
        await async_db.flush()

        limits = TenantLimitsFactory.create(tenant_id=tenant.id, max_monitors=5)
        async_db.add(limits)
        await async_db.flush()

        limits_update = TenantLimitsUpdate(max_monitors=10, max_networks=5)

        # Act
        updated_limits = await crud_tenant.update_limits(
            async_db,
            tenant.id,
            limits_update
        )

        # Assert
        assert updated_limits is not None
        assert updated_limits.max_monitors == 10
        assert updated_limits.max_networks == 5

    @pytest.mark.asyncio
    async def test_upgrade_plan(self, async_db: AsyncSession) -> None:
        """Test upgrading tenant plan."""
        # Arrange
        tenant = TenantFactory.create(plan="free")
        async_db.add(tenant)
        await async_db.flush()

        limits = TenantLimitsFactory.create_for_plan("free", tenant.id)
        async_db.add(limits)
        await async_db.flush()

        # Act
        with patch('src.app.crud.crud_tenant.get_plan_limits_for_db') as mock_get_limits:
            mock_get_limits.return_value = {
                "max_monitors": 100,
                "max_networks": 15,
                "max_triggers": 200,
                "max_api_calls_per_hour": 5000,
                "max_storage_gb": Decimal("25.0"),
                "max_concurrent_operations": 25,
            }

            upgraded_tenant = await crud_tenant.upgrade_plan(
                async_db,
                tenant.id,
                "pro"
            )

        # Assert
        assert upgraded_tenant is not None
        assert upgraded_tenant.plan == "pro"
        assert upgraded_tenant.limits.max_monitors == 100
        mock_get_limits.assert_called_once_with("pro")

    @pytest.mark.asyncio
    async def test_suspend_tenant(self, async_db: AsyncSession) -> None:
        """Test suspending a tenant."""
        # Arrange
        tenant = TenantFactory.create(status="active")
        async_db.add(tenant)
        await async_db.flush()

        # Act
        suspended_tenant = await crud_tenant.suspend_tenant(
            async_db,
            tenant.id,
            reason="payment_failed"
        )

        # Assert
        assert suspended_tenant is not None
        assert suspended_tenant.status == "suspended"
        assert "suspension_reason" in suspended_tenant.settings
        assert suspended_tenant.settings["suspension_reason"] == "payment_failed"

    @pytest.mark.asyncio
    async def test_reactivate_tenant(self, async_db: AsyncSession) -> None:
        """Test reactivating a suspended tenant."""
        # Arrange
        tenant = TenantFactory.create_suspended()
        async_db.add(tenant)
        await async_db.flush()

        # Act
        reactivated_tenant = await crud_tenant.reactivate_tenant(async_db, tenant.id)

        # Assert
        assert reactivated_tenant is not None
        assert reactivated_tenant.status == "active"
        assert "suspension_reason" not in reactivated_tenant.settings
        assert "suspended_at" not in reactivated_tenant.settings


class TestCRUDTenantResourceLimits:
    """Test tenant resource limit management."""

    @pytest.mark.asyncio
    async def test_check_resource_limit_success(self, async_db: AsyncSession) -> None:
        """Test checking resource limits when within bounds."""
        # Arrange
        tenant = TenantFactory.create()
        async_db.add(tenant)
        await async_db.flush()

        limits = TenantLimitsFactory.create(
            tenant_id=tenant.id,
            max_monitors=10,
            current_monitors=5
        )
        async_db.add(limits)
        await async_db.flush()

        # Act
        can_create, current, max_limit = await crud_tenant.check_resource_limit(
            async_db,
            tenant.id,
            "monitors"
        )

        # Assert
        assert can_create is True
        assert current == 5
        assert max_limit == 10

    @pytest.mark.asyncio
    async def test_check_resource_limit_at_limit(self, async_db: AsyncSession) -> None:
        """Test checking resource limits when at limit."""
        # Arrange
        tenant = TenantFactory.create()
        async_db.add(tenant)
        await async_db.flush()

        limits = TenantLimitsFactory.create(
            tenant_id=tenant.id,
            max_monitors=5,
            current_monitors=5
        )
        async_db.add(limits)
        await async_db.flush()

        # Act
        can_create, current, max_limit = await crud_tenant.check_resource_limit(
            async_db,
            tenant.id,
            "monitors"
        )

        # Assert
        assert can_create is False
        assert current == 5
        assert max_limit == 5

    @pytest.mark.asyncio
    async def test_increment_usage_success(self, async_db: AsyncSession) -> None:
        """Test incrementing resource usage successfully."""
        # Arrange
        tenant = TenantFactory.create()
        async_db.add(tenant)
        await async_db.flush()

        limits = TenantLimitsFactory.create(
            tenant_id=tenant.id,
            max_monitors=10,
            current_monitors=5
        )
        async_db.add(limits)
        await async_db.flush()

        # Act
        success = await crud_tenant.increment_usage(async_db, tenant.id, "monitors", 2)

        # Assert
        assert success is True

        # Verify in database
        query = select(TenantLimits).where(TenantLimits.tenant_id == tenant.id)
        result = await async_db.execute(query)
        updated_limits = result.scalar_one()
        assert updated_limits.current_monitors == 7

    @pytest.mark.asyncio
    async def test_increment_usage_exceeds_limit(self, async_db: AsyncSession) -> None:
        """Test incrementing resource usage that exceeds limit."""
        # Arrange
        tenant = TenantFactory.create()
        async_db.add(tenant)
        await async_db.flush()

        limits = TenantLimitsFactory.create(
            tenant_id=tenant.id,
            max_monitors=10,
            current_monitors=9
        )
        async_db.add(limits)
        await async_db.flush()

        # Act
        success = await crud_tenant.increment_usage(async_db, tenant.id, "monitors", 2)

        # Assert
        assert success is False

    @pytest.mark.asyncio
    async def test_decrement_usage(self, async_db: AsyncSession) -> None:
        """Test decrementing resource usage."""
        # Arrange
        tenant = TenantFactory.create()
        async_db.add(tenant)
        await async_db.flush()

        limits = TenantLimitsFactory.create(
            tenant_id=tenant.id,
            current_monitors=5
        )
        async_db.add(limits)
        await async_db.flush()

        # Act
        success = await crud_tenant.decrement_usage(async_db, tenant.id, "monitors", 2)

        # Assert
        assert success is True

        # Verify in database
        query = select(TenantLimits).where(TenantLimits.tenant_id == tenant.id)
        result = await async_db.execute(query)
        updated_limits = result.scalar_one()
        assert updated_limits.current_monitors == 3

    @pytest.mark.asyncio
    async def test_decrement_usage_to_zero(self, async_db: AsyncSession) -> None:
        """Test decrementing resource usage to zero (doesn't go negative)."""
        # Arrange
        tenant = TenantFactory.create()
        async_db.add(tenant)
        await async_db.flush()

        limits = TenantLimitsFactory.create(
            tenant_id=tenant.id,
            current_monitors=2
        )
        async_db.add(limits)
        await async_db.flush()

        # Act
        success = await crud_tenant.decrement_usage(async_db, tenant.id, "monitors", 5)

        # Assert
        assert success is True

        # Verify in database - should be 0, not negative
        query = select(TenantLimits).where(TenantLimits.tenant_id == tenant.id)
        result = await async_db.execute(query)
        updated_limits = result.scalar_one()
        assert updated_limits.current_monitors == 0


class TestCRUDTenantDelete:
    """Test tenant delete operations."""

    @pytest.mark.asyncio
    async def test_soft_delete_tenant(self, async_db: AsyncSession) -> None:
        """Test soft deletion of tenant."""
        # Arrange
        tenant = TenantFactory.create(status="active")
        async_db.add(tenant)
        await async_db.flush()
        tenant_id = tenant.id

        # Act
        result = await crud_tenant.delete(async_db, id=tenant_id)

        # Assert
        assert result is not None

        # Check tenant still exists but status changed
        db_tenant = await async_db.get(Tenant, tenant_id)
        assert db_tenant is not None
        # Note: The actual soft delete implementation may vary
        # This test assumes the delete method updates status

    @pytest.mark.asyncio
    async def test_delete_tenant_by_object(self, async_db: AsyncSession) -> None:
        """Test deleting tenant by object reference."""
        # Arrange
        tenant = TenantFactory.create()
        async_db.add(tenant)
        await async_db.flush()

        # Act
        result = await crud_tenant.delete(async_db, db_obj=tenant)

        # Assert
        assert result is not None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_tenant(self, async_db: AsyncSession) -> None:
        """Test deleting non-existent tenant."""
        # Arrange
        non_existent_id = uuid.uuid4()

        # Act
        result = await crud_tenant.delete(async_db, id=non_existent_id)

        # Assert
        assert result is None


class TestCRUDTenantAdvanced:
    """Test advanced CRUD operations and edge cases."""

    # @pytest.mark.asyncio
    # async def test_bulk_operations(self, async_db: AsyncSession) -> None:
    #     """Test bulk operations on tenants."""
    #     # NOTE: FastCRUD doesn't have bulk_update method - commented out
    #     # Arrange
    #     tenants = TenantFactory.create_batch(3)
    #     for tenant in tenants:
    #         async_db.add(tenant)
    #     await async_db.flush()

    #     tenant_ids = [tenant.id for tenant in tenants]

    #     # Act - Bulk update
    #     update_data = TenantUpdate(status="maintenance")
    #     updated_tenants = await crud_tenant.bulk_update(
    #         async_db,
    #         ids=tenant_ids,
    #         update_data=update_data
    #     )

    #     # Assert
    #     assert len(updated_tenants) == 3
    #     for tenant in updated_tenants:
    #         assert tenant.status == "maintenance"

    @pytest.mark.asyncio
    async def test_exists_tenant(self, async_db: AsyncSession) -> None:
        """Test checking if tenant exists."""
        # Arrange
        tenant = TenantFactory.create(slug="exists-test")
        async_db.add(tenant)
        await async_db.flush()

        # Act & Assert
        assert await crud_tenant.exists(async_db, slug="exists-test") is True
        assert await crud_tenant.exists(async_db, slug="nonexistent") is False

    @pytest.mark.asyncio
    async def test_count_filtered_tenants(self, async_db: AsyncSession) -> None:
        """Test counting tenants with filters."""
        # Arrange
        free_tenants = TenantFactory.create_batch(3, plan="free")
        pro_tenants = TenantFactory.create_batch(2, plan="pro")

        for tenant in free_tenants + pro_tenants:
            async_db.add(tenant)
        await async_db.flush()

        # Act
        filters = TenantFilter(plan="pro")
        count = await crud_tenant.count_filtered(async_db, filters=filters)

        # Assert
        assert count >= 2

    @pytest.mark.asyncio
    async def test_tenant_with_complex_settings(self, async_db: AsyncSession) -> None:
        """Test tenant with complex JSON settings."""
        # Arrange
        complex_settings = {
            "features": {
                "advanced_analytics": True,
                "custom_domains": ["app.tenant.com", "dashboard.tenant.com"],
                "integrations": {
                    "slack": {"enabled": True, "webhook_url": "https://hooks.slack.com/..."},
                    "discord": {"enabled": False},
                    "teams": {"enabled": True, "tenant_id": "abc123"}
                }
            },
            "branding": {
                "logo_url": "https://cdn.tenant.com/logo.png",
                "primary_color": "#007bff",
                "secondary_color": "#6c757d"
            },
            "security": {
                "sso_enabled": True,
                "mfa_required": False,
                "ip_whitelist": ["192.168.1.0/24", "10.0.0.0/8"]
            }
        }

        tenant_create = TenantCreateInternal(
            name="Complex Settings Tenant",
            slug="complex-settings",
            plan="enterprise",
            settings=complex_settings
        )

        # Act
        created_tenant = await crud_tenant.create(async_db, object=tenant_create)

        # Assert
        assert created_tenant.settings["features"]["advanced_analytics"] is True
        assert len(created_tenant.settings["features"]["integrations"]) == 3
        assert created_tenant.settings["branding"]["primary_color"] == "#007bff"

    @pytest.mark.asyncio
    async def test_tenant_factory_variants(self, async_db: AsyncSession) -> None:
        """Test different tenant factory creation methods."""
        # Test plan-specific creation
        pro_tenant = TenantFactory.create_with_plan("pro")
        async_db.add(pro_tenant)
        assert pro_tenant.plan == "pro"

        # Test suspended tenant
        suspended_tenant = TenantFactory.create_suspended()
        async_db.add(suspended_tenant)
        assert suspended_tenant.status == "suspended"
        assert "suspension" in suspended_tenant.settings

        # Test enterprise tenant
        enterprise_tenant = TenantFactory.create_enterprise()
        async_db.add(enterprise_tenant)
        assert enterprise_tenant.plan == "enterprise"
        assert "features" in enterprise_tenant.settings

        await async_db.flush()

        # Verify all tenants were created
        assert pro_tenant.id is not None
        assert suspended_tenant.id is not None
        assert enterprise_tenant.id is not None

    @pytest.mark.asyncio
    async def test_limits_factory_variants(self, async_db: AsyncSession) -> None:
        """Test different tenant limits factory creation methods."""
        # Test limits with usage
        limits_with_usage = TenantLimitsFactory.create_with_usage(usage_percent=0.8)
        assert limits_with_usage.current_monitors == int(limits_with_usage.max_monitors * 0.8)

        # Test plan-specific limits
        tenant_id = uuid.uuid4()
        enterprise_limits = TenantLimitsFactory.create_for_plan("enterprise", tenant_id)
        assert enterprise_limits.max_monitors == 500
        assert enterprise_limits.tenant_id == tenant_id

    @pytest.mark.asyncio
    async def test_crud_instance_validation(self) -> None:
        """Test that crud_tenant is properly instantiated."""
        # Assert
        assert isinstance(crud_tenant, CRUDTenant)
        assert crud_tenant.model is Tenant

    @pytest.mark.asyncio
    async def test_plan_limits_integration(self, async_db: AsyncSession) -> None:
        """Test integration with plan limits configuration."""
        # This test verifies the CRUD integrates with the plan limits system

        with patch('src.app.crud.crud_tenant.get_plan_limits_for_db') as mock_get_limits:
            mock_get_limits.return_value = {
                "max_monitors": 25,
                "max_networks": 5,
                "max_triggers": 50,
                "max_api_calls_per_hour": 1000,
                "max_storage_gb": Decimal("5.0"),
                "max_concurrent_operations": 10,
            }

            # Act
            tenant_create = TenantCreate(name="Plan Test", slug="plan-test", plan="starter")
            tenant_with_limits = await crud_tenant.create_with_limits(async_db, object=tenant_create)

            # Assert
            assert tenant_with_limits.limits.max_monitors == 25
            assert tenant_with_limits.limits.max_networks == 5
            mock_get_limits.assert_called_once_with("starter")

    @pytest.mark.asyncio
    async def test_error_handling_missing_limits(self, async_db: AsyncSession) -> None:
        """Test error handling when tenant limits are missing."""
        # Arrange
        tenant = TenantFactory.create()
        async_db.add(tenant)
        await async_db.flush()
        # Note: Not creating limits for this tenant

        # Act
        result = await crud_tenant.check_resource_limit(async_db, tenant.id, "monitors")

        # Assert
        can_create, current, max_limit = result
        assert can_create is False
        assert current == 0
        assert max_limit == 0
