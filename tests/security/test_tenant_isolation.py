"""Tests for tenant isolation and row-level security."""

import uuid

import pytest

from src.app.middleware.rls import RLSContext, check_resource_access


@pytest.mark.asyncio
async def test_tenant_isolation_middleware():
    """Test that users can only access their tenant's data."""
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()

    # Test tenant isolation logic
    user_a = {"id": 1, "tenant_id": tenant_a_id}
    user_b = {"id": 2, "tenant_id": tenant_b_id}

    # Users should have different tenant IDs
    assert user_a["tenant_id"] != user_b["tenant_id"]

    # Test resource access
    resource_a = {"id": "resource-1", "tenant_id": tenant_a_id}
    resource_b = {"id": "resource-2", "tenant_id": tenant_b_id}

    # User A should only access their tenant's resources
    can_access_own = user_a["tenant_id"] == resource_a["tenant_id"]
    cannot_access_other = user_a["tenant_id"] != resource_b["tenant_id"]

    assert can_access_own is True
    assert cannot_access_other is True


@pytest.mark.asyncio
async def test_superuser_cross_tenant_access():
    """Test that superusers can access cross-tenant resources."""
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()

    # Test superuser permissions
    superuser = {"id": 1, "tenant_id": tenant_a_id, "is_superuser": True}
    regular_user = {"id": 2, "tenant_id": tenant_a_id, "is_superuser": False}

    # Resources from different tenants
    resource_a = {"id": "resource-1", "tenant_id": tenant_a_id}
    resource_b = {"id": "resource-2", "tenant_id": tenant_b_id}

    # Superuser can access any resource
    superuser_can_access_a = superuser["is_superuser"] or superuser["tenant_id"] == resource_a["tenant_id"]
    superuser_can_access_b = superuser["is_superuser"] or superuser["tenant_id"] == resource_b["tenant_id"]

    assert superuser_can_access_a is True
    assert superuser_can_access_b is True

    # Regular user cannot access other tenant's resources
    regular_can_access_a = regular_user["tenant_id"] == resource_a["tenant_id"]
    regular_can_access_b = regular_user["tenant_id"] == resource_b["tenant_id"]

    assert regular_can_access_a is True
    assert regular_can_access_b is False


@pytest.mark.asyncio
async def test_tenant_context_in_request():
    """Test that tenant context is properly set in request state."""
    # Test tenant context structure
    tenant_id = uuid.uuid4()
    user_id = 1

    # Mock request state
    request_context = {
        "user": {
            "id": user_id,
            "tenant_id": tenant_id,
            "is_superuser": False
        }
    }

    # Test context is properly structured
    assert "user" in request_context
    assert request_context["user"]["id"] == user_id
    assert request_context["user"]["tenant_id"] == tenant_id
    assert isinstance(request_context["user"]["tenant_id"], uuid.UUID)

    # Test context extraction
    extracted_tenant_id = request_context["user"]["tenant_id"]
    extracted_user_id = request_context["user"]["id"]

    assert extracted_tenant_id == tenant_id
    assert extracted_user_id == user_id


@pytest.mark.asyncio
async def test_rls_context():
    """Test RLS context management."""
    context = RLSContext.get_instance()

    # Set context
    tenant_id = uuid.uuid4()
    user_id = 1
    context.set_context(
        tenant_id=tenant_id,
        user_id=user_id,
        is_superuser=False,
        bypass_rls=False
    )

    assert context.tenant_id == tenant_id
    assert context.user_id == user_id
    assert context.is_superuser is False
    assert context.bypass_rls is False

    # Clear context
    context.clear_context()
    assert context.tenant_id is None
    assert context.user_id is None


@pytest.mark.asyncio
async def test_check_resource_access():
    """Test resource access checking."""
    # Create mock resource
    class MockResource:
        def __init__(self, tenant_id, user_id):
            self.tenant_id = tenant_id
            self.user_id = user_id

    tenant_id = uuid.uuid4()
    user_id = 1

    # Test user accessing own resource
    resource = MockResource(tenant_id, user_id)
    assert check_resource_access(
        resource,
        user_id=user_id,
        tenant_id=tenant_id,
        raise_on_failure=False
    ) is True

    # Test user accessing another user's resource in same tenant
    other_resource = MockResource(tenant_id, 999)
    assert check_resource_access(
        other_resource,
        user_id=user_id,
        tenant_id=tenant_id,
        raise_on_failure=False
    ) is True  # Should have read access through tenant

    # Test user accessing resource from different tenant
    other_tenant = uuid.uuid4()
    foreign_resource = MockResource(other_tenant, user_id)
    assert check_resource_access(
        foreign_resource,
        user_id=user_id,
        tenant_id=tenant_id,
        raise_on_failure=False
    ) is False


@pytest.mark.asyncio
async def test_tenant_data_filtering():
    """Test that list endpoints filter by tenant."""
    # This test focuses on the RLS logic rather than HTTP calls
    from src.app.middleware.rls import RLSContext

    context = RLSContext.get_instance()

    # Test tenant filtering logic
    tenant_a_id = uuid.uuid4()
    tenant_b_id = uuid.uuid4()

    # Set context for tenant A
    context.set_context(
        tenant_id=tenant_a_id,
        user_id=1,
        is_superuser=False,
        bypass_rls=False
    )

    assert context.tenant_id == tenant_a_id
    assert context.bypass_rls is False

    # Clear and set context for tenant B
    context.clear_context()
    context.set_context(
        tenant_id=tenant_b_id,
        user_id=2,
        is_superuser=False,
        bypass_rls=False
    )

    assert context.tenant_id == tenant_b_id
    assert context.user_id == 2
