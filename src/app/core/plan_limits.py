"""
Centralized plan limits configuration for multi-tenant architecture.
Single source of truth for resource limits across different subscription plans.
"""

from typing import Any

# Default resource limits for each subscription plan
DEFAULT_PLAN_LIMITS: dict[str, dict[str, Any]] = {
    "free": {
        "monitors": 10,
        "networks": 3,
        "triggers": 20,
        "api_calls": 1000,  # per hour
        "storage": 1.0,  # GB
        "concurrent_operations": 10,
    },
    "starter": {
        "monitors": 50,
        "networks": 10,
        "triggers": 100,
        "api_calls": 10000,  # per hour
        "storage": 10.0,  # GB
        "concurrent_operations": 25,
    },
    "pro": {
        "monitors": 200,
        "networks": 50,
        "triggers": 500,
        "api_calls": 100000,  # per hour
        "storage": 100.0,  # GB
        "concurrent_operations": 100,
    },
    "enterprise": {
        "monitors": 1000,
        "networks": 200,
        "triggers": 2000,
        "api_calls": 1000000,  # per hour
        "storage": 1000.0,  # GB
        "concurrent_operations": 500,
    },
}


def get_plan_limits(plan: str) -> dict[str, Any]:
    """
    Get resource limits for a specific plan.

    Args:
        plan: Plan name (free, starter, pro, enterprise)

    Returns:
        Dictionary of resource limits for the plan
    """
    return DEFAULT_PLAN_LIMITS.get(plan, DEFAULT_PLAN_LIMITS["free"])


def get_plan_limits_for_db(plan: str) -> dict[str, Any]:
    """
    Get resource limits formatted for database storage.
    Uses max_ prefix for database field compatibility.

    Args:
        plan: Plan name (free, starter, pro, enterprise)

    Returns:
        Dictionary of resource limits with max_ prefix
    """
    base_limits = get_plan_limits(plan)
    return {
        "max_monitors": base_limits["monitors"],
        "max_networks": base_limits["networks"],
        "max_triggers": base_limits["triggers"],
        "max_api_calls_per_hour": base_limits["api_calls"],
        "max_storage_gb": base_limits["storage"],
        "max_concurrent_operations": base_limits.get("concurrent_operations", 10),
    }
