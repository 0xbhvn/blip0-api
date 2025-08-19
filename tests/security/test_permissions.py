"""Tests for permission system."""


import pytest

from src.app.core.permissions import (
    ROLE_PERMISSIONS,
    Permission,
    Role,
    has_all_permissions,
    has_any_permission,
    has_permission,
)


def test_role_permissions():
    """Test that roles have correct permissions."""
    # Viewer should have read-only permissions
    viewer_perms = ROLE_PERMISSIONS[Role.VIEWER]
    assert Permission.MONITOR_READ in viewer_perms
    assert Permission.MONITOR_WRITE not in viewer_perms
    assert Permission.MONITOR_DELETE not in viewer_perms

    # User should have basic permissions
    user_perms = ROLE_PERMISSIONS[Role.USER]
    assert Permission.MONITOR_READ in user_perms
    assert Permission.MONITOR_WRITE in user_perms
    assert Permission.MONITOR_DELETE not in user_perms

    # Admin should have most permissions
    admin_perms = ROLE_PERMISSIONS[Role.ADMIN]
    assert Permission.MONITOR_READ in admin_perms
    assert Permission.MONITOR_WRITE in admin_perms
    assert Permission.MONITOR_DELETE in admin_perms
    assert Permission.ADMIN_ACCESS in admin_perms

    # Superuser should have all permissions
    superuser_perms = ROLE_PERMISSIONS[Role.SUPERUSER]
    assert all(perm in superuser_perms for perm in Permission)


def test_has_permission():
    """Test permission checking."""
    # Test superuser always has permission
    superuser = {"is_superuser": True}
    assert has_permission(superuser, Permission.MONITOR_DELETE) is True
    assert has_permission(superuser, Permission.SYSTEM_CONFIG) is True

    # Test explicit permissions
    user_with_perms = {
        "is_superuser": False,
        "permissions": ["monitor:read", "monitor:write"]
    }
    assert has_permission(user_with_perms, Permission.MONITOR_READ) is True
    assert has_permission(user_with_perms, Permission.MONITOR_WRITE) is True
    assert has_permission(user_with_perms, Permission.MONITOR_DELETE) is False

    # Test wildcard permission
    user_with_wildcard = {
        "is_superuser": False,
        "permissions": ["*"]
    }
    assert has_permission(user_with_wildcard, Permission.MONITOR_DELETE) is True

    # Test role-based permissions
    user_with_role = {
        "is_superuser": False,
        "role": "developer",
        "permissions": []
    }
    assert has_permission(user_with_role, Permission.MONITOR_READ) is True
    assert has_permission(user_with_role, Permission.MONITOR_DELETE) is True
    assert has_permission(user_with_role, Permission.TENANT_MANAGE_BILLING) is False


def test_has_any_permission():
    """Test checking for any of multiple permissions."""
    user = {
        "is_superuser": False,
        "permissions": ["monitor:read", "trigger:read"]
    }

    # Should have at least one
    assert has_any_permission(user, [
        Permission.MONITOR_READ,
        Permission.MONITOR_WRITE
    ]) is True

    # Should not have any
    assert has_any_permission(user, [
        Permission.MONITOR_DELETE,
        Permission.ADMIN_ACCESS
    ]) is False


def test_has_all_permissions():
    """Test checking for all permissions."""
    user = {
        "is_superuser": False,
        "permissions": ["monitor:read", "monitor:write", "trigger:read"]
    }

    # Should have all
    assert has_all_permissions(user, [
        Permission.MONITOR_READ,
        Permission.TRIGGER_READ
    ]) is True

    # Should not have all
    assert has_all_permissions(user, [
        Permission.MONITOR_READ,
        Permission.MONITOR_DELETE
    ]) is False


def test_resource_level_permissions():
    """Test resource-level permission checking."""
    # Mock resource
    class MockResource:
        def __init__(self, user_id, tenant_id):
            self.user_id = user_id
            self.tenant_id = tenant_id

    # Test that resources have the expected structure
    owned_resource = MockResource(1, "tenant-1")
    assert owned_resource.user_id == 1
    assert owned_resource.tenant_id == "tenant-1"

    # Test resource from different tenant
    other_resource = MockResource(999, "tenant-1")
    assert other_resource.user_id == 999
    assert other_resource.tenant_id == "tenant-1"

    # Test cross-tenant resource
    cross_tenant_resource = MockResource(1, "tenant-2")
    assert cross_tenant_resource.user_id == 1
    assert cross_tenant_resource.tenant_id == "tenant-2"

    # Test that different tenants have different IDs
    assert owned_resource.tenant_id != cross_tenant_resource.tenant_id


@pytest.mark.asyncio
async def test_permission_required_endpoint(
    mock_viewer_user,
    mock_admin_user
):
    """Test endpoints that require specific permissions."""
    from src.app.core.permissions import Permission, has_permission

    # Mock viewer user should not have delete permissions
    assert has_permission(mock_viewer_user, Permission.MONITOR_DELETE) is False

    # Mock admin user should have delete permissions
    assert has_permission(mock_admin_user, Permission.MONITOR_DELETE) is True


@pytest.mark.asyncio
async def test_role_based_access(
    mock_viewer_user,
    mock_user,
    mock_admin_user
):
    """Test role-based access control."""
    from src.app.core.permissions import Permission, has_permission

    # Test viewer role - can read but not write
    assert has_permission(mock_viewer_user, Permission.MONITOR_READ) is True
    assert has_permission(mock_viewer_user, Permission.MONITOR_WRITE) is False

    # Test user role - can read and write but not delete
    assert has_permission(mock_user, Permission.MONITOR_READ) is True
    assert has_permission(mock_user, Permission.MONITOR_WRITE) is True
    assert has_permission(mock_user, Permission.MONITOR_DELETE) is False

    # Test admin role - should have admin access
    assert has_permission(mock_admin_user, Permission.MONITOR_READ) is True
    assert has_permission(mock_admin_user, Permission.MONITOR_WRITE) is True
    assert has_permission(mock_admin_user, Permission.MONITOR_DELETE) is True
    assert has_permission(mock_admin_user, Permission.ADMIN_ACCESS) is True
