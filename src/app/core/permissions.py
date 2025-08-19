"""Permission system for role-based access control (RBAC)."""

from collections.abc import Callable
from enum import Enum
from functools import wraps
from typing import Any, Optional

from fastapi import HTTPException, status

from ..core.logger import logging

logger = logging.getLogger(__name__)


class Permission(str, Enum):
    """System permissions enumeration."""

    # Monitor permissions
    MONITOR_READ = "monitor:read"
    MONITOR_WRITE = "monitor:write"
    MONITOR_DELETE = "monitor:delete"
    MONITOR_EXECUTE = "monitor:execute"

    # Trigger permissions
    TRIGGER_READ = "trigger:read"
    TRIGGER_WRITE = "trigger:write"
    TRIGGER_DELETE = "trigger:delete"
    TRIGGER_TEST = "trigger:test"

    # Network permissions
    NETWORK_READ = "network:read"
    NETWORK_WRITE = "network:write"
    NETWORK_DELETE = "network:delete"

    # Filter script permissions
    FILTER_READ = "filter:read"
    FILTER_WRITE = "filter:write"
    FILTER_DELETE = "filter:delete"

    # Tenant permissions
    TENANT_READ = "tenant:read"
    TENANT_WRITE = "tenant:write"
    TENANT_DELETE = "tenant:delete"
    TENANT_MANAGE_USERS = "tenant:manage_users"
    TENANT_MANAGE_BILLING = "tenant:manage_billing"

    # User permissions
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"
    USER_MANAGE_KEYS = "user:manage_keys"

    # Admin permissions
    ADMIN_ACCESS = "admin:access"
    ADMIN_SUPER = "admin:super"

    # API key permissions
    API_KEY_READ = "api_key:read"
    API_KEY_WRITE = "api_key:write"
    API_KEY_DELETE = "api_key:delete"

    # System permissions
    SYSTEM_CONFIG = "system:config"
    SYSTEM_METRICS = "system:metrics"
    SYSTEM_LOGS = "system:logs"


class Role(str, Enum):
    """Predefined roles with permission sets."""

    VIEWER = "viewer"
    USER = "user"
    DEVELOPER = "developer"
    ADMIN = "admin"
    OWNER = "owner"
    SUPERUSER = "superuser"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {
        Permission.MONITOR_READ,
        Permission.TRIGGER_READ,
        Permission.NETWORK_READ,
        Permission.FILTER_READ,
        Permission.USER_READ,
    },
    Role.USER: {
        Permission.MONITOR_READ,
        Permission.MONITOR_WRITE,
        Permission.TRIGGER_READ,
        Permission.TRIGGER_WRITE,
        Permission.TRIGGER_TEST,
        Permission.NETWORK_READ,
        Permission.FILTER_READ,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_MANAGE_KEYS,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
    },
    Role.DEVELOPER: {
        Permission.MONITOR_READ,
        Permission.MONITOR_WRITE,
        Permission.MONITOR_DELETE,
        Permission.MONITOR_EXECUTE,
        Permission.TRIGGER_READ,
        Permission.TRIGGER_WRITE,
        Permission.TRIGGER_DELETE,
        Permission.TRIGGER_TEST,
        Permission.NETWORK_READ,
        Permission.FILTER_READ,
        Permission.FILTER_WRITE,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_MANAGE_KEYS,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
        Permission.API_KEY_DELETE,
    },
    Role.ADMIN: {
        Permission.MONITOR_READ,
        Permission.MONITOR_WRITE,
        Permission.MONITOR_DELETE,
        Permission.MONITOR_EXECUTE,
        Permission.TRIGGER_READ,
        Permission.TRIGGER_WRITE,
        Permission.TRIGGER_DELETE,
        Permission.TRIGGER_TEST,
        Permission.NETWORK_READ,
        Permission.NETWORK_WRITE,
        Permission.FILTER_READ,
        Permission.FILTER_WRITE,
        Permission.FILTER_DELETE,
        Permission.TENANT_READ,
        Permission.TENANT_WRITE,
        Permission.TENANT_MANAGE_USERS,
        Permission.USER_READ,
        Permission.USER_WRITE,
        Permission.USER_DELETE,
        Permission.USER_MANAGE_KEYS,
        Permission.API_KEY_READ,
        Permission.API_KEY_WRITE,
        Permission.API_KEY_DELETE,
        Permission.ADMIN_ACCESS,
    },
    Role.OWNER: {
        # Owners have all permissions except system-level
        *[p for p in Permission if not p.value.startswith("system:")],
        Permission.TENANT_MANAGE_BILLING,
    },
    Role.SUPERUSER: {
        # Superusers have all permissions
        *Permission,
    },
}


def has_permission(
    user: dict[str, Any],
    permission: Permission,
    resource: Optional[Any] = None
) -> bool:
    """Check if a user has a specific permission.

    Parameters
    ----------
    user : dict[str, Any]
        The user dictionary with role and permissions.
    permission : Permission
        The permission to check.
    resource : Optional[Any]
        Optional resource for context-aware permission checks.

    Returns
    -------
    bool
        True if the user has the permission, False otherwise.
    """
    # Superusers always have all permissions
    if user.get("is_superuser"):
        return True

    # Check if user has explicit permission
    user_permissions = user.get("permissions", [])
    if isinstance(user_permissions, str):
        user_permissions = user_permissions.split()

    if permission.value in user_permissions or "*" in user_permissions:
        return True

    # Check role-based permissions
    user_role = user.get("role")
    if user_role:
        try:
            role = Role(user_role)
            role_perms = ROLE_PERMISSIONS.get(role, set())
            if permission in role_perms:
                return True
        except ValueError:
            logger.warning(f"Unknown role: {user_role}")

    # Check resource-level permissions if resource is provided
    if resource:
        # Check if user owns the resource
        if hasattr(resource, "user_id") and resource.user_id == user.get("id"):
            # Owners can read and write their own resources
            if permission.value.endswith(":read") or permission.value.endswith(":write"):
                return True

        # Check if resource belongs to user's tenant
        if hasattr(resource, "tenant_id"):
            user_tenant = user.get("tenant_id")
            if user_tenant and resource.tenant_id == user_tenant:
                # Tenant members can read tenant resources
                if permission.value.endswith(":read"):
                    return True

    return False


def has_any_permission(
    user: dict[str, Any],
    permissions: list[Permission]
) -> bool:
    """Check if a user has any of the specified permissions.

    Parameters
    ----------
    user : dict[str, Any]
        The user dictionary.
    permissions : list[Permission]
        List of permissions to check.

    Returns
    -------
    bool
        True if the user has any of the permissions.
    """
    return any(has_permission(user, perm) for perm in permissions)


def has_all_permissions(
    user: dict[str, Any],
    permissions: list[Permission]
) -> bool:
    """Check if a user has all of the specified permissions.

    Parameters
    ----------
    user : dict[str, Any]
        The user dictionary.
    permissions : list[Permission]
        List of permissions to check.

    Returns
    -------
    bool
        True if the user has all of the permissions.
    """
    return all(has_permission(user, perm) for perm in permissions)


def require_permission(permission: Permission):
    """Decorator to require a specific permission for a route.

    Parameters
    ----------
    permission : Permission
        The required permission.

    Returns
    -------
    Callable
        The decorator function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            if not has_permission(current_user, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission.value} required"
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_any_permission(*permissions: Permission):
    """Decorator to require any of the specified permissions.

    Parameters
    ----------
    *permissions : Permission
        The permissions (user needs at least one).

    Returns
    -------
    Callable
        The decorator function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            if not has_any_permission(current_user, list(permissions)):
                perm_list = ", ".join(p.value for p in permissions)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: one of [{perm_list}] required"
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_all_permissions(*permissions: Permission):
    """Decorator to require all of the specified permissions.

    Parameters
    ----------
    *permissions : Permission
        The permissions (user needs all).

    Returns
    -------
    Callable
        The decorator function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            if not has_all_permissions(current_user, list(permissions)):
                perm_list = ", ".join(p.value for p in permissions)
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: all of [{perm_list}] required"
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


# Note: Use the decorators @require_permission, @require_any_permission,
# or @require_all_permissions for route-level permission checking.
# These decorators can be applied to FastAPI route handlers to enforce
# permission requirements.
