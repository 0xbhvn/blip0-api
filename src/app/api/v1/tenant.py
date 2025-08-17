"""
Tenant self-service API endpoints for tenant users.
Allows tenants to view and manage their own settings and usage.
"""

import uuid as uuid_pkg
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_user, get_tenant_context, rate_limiter_dependency
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
)
from ...core.logger import logging
from ...schemas.tenant import (
    TenantLimitsRead,
    TenantRead,
    TenantSelfServiceUpdate,
    TenantUsageStats,
    TenantWithLimits,
)
from ...services.tenant_service import tenant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tenant", tags=["tenant"])


@router.get("", response_model=TenantWithLimits)
async def get_current_tenant(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str, Depends(get_tenant_context)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> TenantWithLimits:
    """
    Get current tenant information including limits.

    Returns the tenant associated with the current user.
    """
    logger.info(f"User {current_user['id']} getting tenant info for {tenant_id}")

    # Get tenant with limits
    from ...crud.crud_tenant import crud_tenant

    tenant_uuid = uuid_pkg.UUID(tenant_id)
    tenant_with_limits = await crud_tenant.get_with_limits(db, tenant_uuid)

    if not tenant_with_limits:
        raise NotFoundException(f"Tenant {tenant_id} not found")

    # Check if tenant is active
    if tenant_with_limits.status == "suspended":
        raise ForbiddenException("Tenant is suspended. Please contact support.")

    return tenant_with_limits


@router.put("", response_model=TenantRead)
async def update_current_tenant(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str, Depends(get_tenant_context)],
    update_data: TenantSelfServiceUpdate,
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> TenantRead:
    """
    Update current tenant settings (limited fields).

    Allows tenants to update their name and non-restricted settings.
    """
    logger.info(f"User {current_user['id']} updating tenant {tenant_id}")

    # Check tenant status
    tenant = await tenant_service.get_tenant(db, tenant_id)
    if not tenant:
        raise NotFoundException(f"Tenant {tenant_id} not found")

    if tenant.status == "suspended":
        raise ForbiddenException("Cannot update suspended tenant. Please contact support.")

    # Update tenant with limited fields
    try:
        updated_tenant = await tenant_service.update_tenant_self_service(
            db=db,
            tenant_id=tenant_id,
            update_data=update_data,
        )

        if not updated_tenant:
            raise NotFoundException(f"Tenant {tenant_id} not found")

        await db.commit()

        logger.info(f"Updated tenant {tenant_id} settings")
        return updated_tenant

    except IntegrityError as e:
        await db.rollback()
        if "duplicate key" in str(e).lower():
            raise DuplicateValueException("Tenant with this name already exists")
        raise BadRequestException(f"Failed to update tenant: {str(e)}")
    except ValidationError as e:
        raise BadRequestException(f"Invalid settings: {str(e)}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating tenant {tenant_id}: {e}")
        raise BadRequestException(f"Failed to update tenant: {str(e)}")


@router.get("/usage", response_model=TenantUsageStats)
async def get_tenant_usage(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str, Depends(get_tenant_context)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> TenantUsageStats:
    """
    Get current tenant usage statistics.

    Returns detailed usage information including:
    - Current resource usage (monitors, triggers, storage, API calls)
    - Resource limits based on plan
    - Remaining quotas
    - Usage percentages
    """
    logger.info(f"User {current_user['id']} getting usage stats for tenant {tenant_id}")

    # Check tenant status
    tenant = await tenant_service.get_tenant(db, tenant_id)
    if not tenant:
        raise NotFoundException(f"Tenant {tenant_id} not found")

    if tenant.status == "suspended":
        raise ForbiddenException("Tenant is suspended. Please contact support.")

    # Get usage statistics
    usage_stats = await tenant_service.get_tenant_usage(db, tenant_id)

    if not usage_stats:
        raise NotFoundException("Usage statistics not available")

    return usage_stats


@router.get("/limits", response_model=TenantLimitsRead)
async def get_tenant_limits(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    tenant_id: Annotated[str, Depends(get_tenant_context)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> TenantLimitsRead:
    """
    Get current tenant rate limits and quotas.

    Returns:
    - Maximum allowed resources (monitors, networks, triggers)
    - API rate limits
    - Storage quotas
    - Current usage for each resource
    """
    logger.info(f"User {current_user['id']} getting limits for tenant {tenant_id}")

    # Check tenant status
    tenant = await tenant_service.get_tenant(db, tenant_id)
    if not tenant:
        raise NotFoundException(f"Tenant {tenant_id} not found")

    if tenant.status == "suspended":
        raise ForbiddenException("Tenant is suspended. Please contact support.")

    # Get tenant limits
    limits = await tenant_service.get_tenant_limits(db, tenant_id)

    if not limits:
        raise NotFoundException("Tenant limits not configured")

    return limits
