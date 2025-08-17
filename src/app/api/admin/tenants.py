"""
Admin tenant API endpoints for platform administration.
Implements CRUD operations with enhanced admin capabilities.
"""

import uuid as uuid_pkg
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_admin, rate_limiter_dependency
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
)
from ...core.logger import logging
from ...schemas.tenant import (
    TenantActivateRequest,
    TenantAdminPagination,
    TenantAdminRead,
    TenantCreate,
    TenantFilter,
    TenantRead,
    TenantSort,
    TenantSuspendRequest,
    TenantUpdate,
    TenantWithLimits,
)
from ...services.tenant_service import tenant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tenants", tags=["admin-tenants"])

# Constants for tenant state updates
SUSPEND_TENANT_UPDATE = TenantUpdate(status="suspended", name=None, slug=None)
ACTIVATE_TENANT_UPDATE = TenantUpdate(status="active", name=None, slug=None)


@router.get("", response_model=TenantAdminPagination)
async def list_tenants(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Page size"),
    # Filter parameters
    name: Optional[str] = Query(None, description="Filter by name (partial match)"),
    slug: Optional[str] = Query(None, description="Filter by slug (exact match)"),
    plan: Optional[str] = Query(None, description="Filter by plan (free/starter/pro/enterprise)"),
    status: Optional[str] = Query(None, description="Filter by status (active/suspended/deleted)"),
    # Sort parameters
    sort_field: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
) -> dict[str, Any]:
    """
    List all tenants with pagination, filtering, and sorting.
    Admin only endpoint with enhanced tenant information.

    Returns paginated list of tenants with admin details.
    """
    logger.info(f"Admin {admin_user['id']} listing tenants (page={page}, size={size})")

    # Build filter object
    filters = TenantFilter(
        name=name,
        slug=slug,
        plan=plan,
        status=status,
        created_after=None,
        created_before=None,
    )

    # Build sort object
    sort = TenantSort(field=sort_field, order=sort_order)

    # Get paginated tenants with admin details
    result = await tenant_service.list_all_tenants(
        db=db,
        page=page,
        size=size,
        filters=filters,
        sort=sort,
    )

    logger.info(f"Returned {len(result.items)} tenants (total={result.total})")
    return result.model_dump()


@router.post("", response_model=TenantWithLimits, status_code=201)
async def create_tenant(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    tenant_in: TenantCreate,
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> TenantWithLimits:
    """
    Create a new tenant with default limits based on plan.
    Admin only endpoint.

    Returns created tenant with associated limits.
    """
    logger.info(f"Admin {admin_user['id']} creating tenant: {tenant_in.name}")

    try:
        # Create tenant with limits
        from ...crud.crud_tenant import crud_tenant

        created_tenant = await crud_tenant.create_with_limits(
            db=db,
            obj_in=tenant_in,
        )

        await db.commit()

        logger.info(f"Created tenant {created_tenant.id} ({created_tenant.name})")
        return created_tenant

    except IntegrityError as e:
        await db.rollback()
        if "duplicate key" in str(e).lower():
            raise DuplicateValueException(
                f"Tenant with name '{tenant_in.name}' or slug '{tenant_in.slug}' already exists"
            )
        raise BadRequestException(f"Failed to create tenant: {str(e)}")
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating tenant: {e}")
        raise BadRequestException(f"Failed to create tenant: {str(e)}")


@router.get("/{tenant_id}", response_model=TenantAdminRead)
async def get_tenant(
    _request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> TenantAdminRead:
    """
    Get detailed tenant information including usage statistics.
    Admin only endpoint.

    Returns tenant with enhanced admin information.
    """
    logger.info(f"Admin {admin_user['id']} getting tenant {tenant_id}")

    # Try to parse as UUID
    try:
        tenant_uuid = uuid_pkg.UUID(tenant_id)
    except ValueError:
        raise BadRequestException(f"Invalid tenant ID format: {tenant_id}")

    # Get tenant with enhanced info
    from sqlalchemy import func, select

    from ...models.monitor import Monitor
    from ...models.trigger import Trigger
    from ...models.user import User

    tenant = await tenant_service.get_tenant(db, tenant_uuid)
    if not tenant:
        raise NotFoundException(f"Tenant {tenant_id} not found")

    # Get additional counts
    user_count_query = select(func.count(User.id)).where(
        User.tenant_id == tenant_uuid,
        ~User.is_deleted
    )
    monitor_count_query = select(func.count(Monitor.id)).where(
        Monitor.tenant_id == tenant_uuid,
        Monitor.active == True  # noqa: E712
    )
    trigger_count_query = select(func.count(Trigger.id)).where(
        Trigger.tenant_id == tenant_uuid,
        Trigger.active == True  # noqa: E712
    )

    user_count_result = await db.execute(user_count_query)
    user_count = user_count_result.scalar() or 0

    monitor_count_result = await db.execute(monitor_count_query)
    monitor_count = monitor_count_result.scalar() or 0

    trigger_count_result = await db.execute(trigger_count_query)
    trigger_count = trigger_count_result.scalar() or 0

    # Get limits
    limits = await tenant_service.get_tenant_limits(db, tenant_uuid)

    # Create admin read response
    admin_tenant = TenantAdminRead(
        **tenant.model_dump(),
        limits=limits,
        user_count=user_count,
        monitor_count=monitor_count,
        trigger_count=trigger_count,
        last_activity=None,  # TODO: Track last activity
        suspended_at=tenant.settings.get("suspended_at") if tenant.settings else None,
        suspension_reason=tenant.settings.get("suspension_reason") if tenant.settings else None,
    )

    return admin_tenant


@router.put("/{tenant_id}", response_model=TenantRead)
async def update_tenant(
    _request: Request,
    tenant_id: str,
    tenant_update: TenantUpdate,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> TenantRead:
    """
    Update tenant information.
    Admin only endpoint with full update capabilities.

    Returns updated tenant.
    """
    logger.info(f"Admin {admin_user['id']} updating tenant {tenant_id}")

    # Try to parse as UUID
    try:
        tenant_uuid = uuid_pkg.UUID(tenant_id)
    except ValueError:
        raise BadRequestException(f"Invalid tenant ID format: {tenant_id}")

    # Update tenant
    try:
        updated_tenant = await tenant_service.update_tenant(
            db=db,
            tenant_id=tenant_uuid,
            tenant_update=tenant_update,
        )

        if not updated_tenant:
            raise NotFoundException(f"Tenant {tenant_id} not found")

        await db.commit()

        logger.info(f"Updated tenant {tenant_id}")
        return updated_tenant

    except IntegrityError as e:
        await db.rollback()
        if "duplicate key" in str(e).lower():
            raise DuplicateValueException("Tenant with this name or slug already exists")
        raise BadRequestException(f"Failed to update tenant: {str(e)}")
    except NotFoundException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating tenant {tenant_id}: {e}")
        raise BadRequestException(f"Failed to update tenant: {str(e)}")


@router.delete("/{tenant_id}", status_code=204)
async def delete_tenant(
    _request: Request,
    tenant_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
    is_hard_delete: bool = Query(False, description="If true, permanently delete the tenant"),
) -> None:
    """
    Delete a tenant (soft delete by default).
    Admin only endpoint.

    WARNING: Hard delete will permanently remove all tenant data including
    users, monitors, triggers, and all associated records.
    """
    logger.info(f"Admin {admin_user['id']} deleting tenant {tenant_id} (hard={is_hard_delete})")

    # Try to parse as UUID
    try:
        tenant_uuid = uuid_pkg.UUID(tenant_id)
    except ValueError:
        raise BadRequestException(f"Invalid tenant ID format: {tenant_id}")

    # Check if tenant exists
    tenant = await tenant_service.get_tenant(db, tenant_uuid)
    if not tenant:
        raise NotFoundException(f"Tenant {tenant_id} not found")

    # Prevent deleting own tenant
    if str(admin_user.get("tenant_id")) == str(tenant_uuid):
        raise ForbiddenException("Cannot delete your own tenant")

    # Delete tenant
    deleted = await tenant_service.delete_tenant(
        db=db,
        tenant_id=tenant_uuid,
        is_hard_delete=is_hard_delete,
    )

    if not deleted:
        raise BadRequestException(f"Failed to delete tenant {tenant_id}")

    await db.commit()

    logger.info(f"Deleted tenant {tenant_id} (hard={is_hard_delete})")


@router.post("/{tenant_id}/suspend", response_model=TenantRead)
async def suspend_tenant(
    _request: Request,
    tenant_id: str,
    suspend_request: TenantSuspendRequest,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> TenantRead:
    """
    Suspend a tenant, preventing all operations.
    Admin only endpoint.

    Returns updated tenant with suspended status.
    """
    logger.info(f"Admin {admin_user['id']} suspending tenant {tenant_id}")

    # Try to parse as UUID
    try:
        tenant_uuid = uuid_pkg.UUID(tenant_id)
    except ValueError:
        raise BadRequestException(f"Invalid tenant ID format: {tenant_id}")

    # Check if tenant exists and is not already suspended
    tenant = await tenant_service.get_tenant(db, tenant_uuid)
    if not tenant:
        raise NotFoundException(f"Tenant {tenant_id} not found")

    if tenant.status == "suspended":
        raise BadRequestException(f"Tenant {tenant_id} is already suspended")

    # Prevent suspending own tenant
    if str(admin_user.get("tenant_id")) == str(tenant_uuid):
        raise ForbiddenException("Cannot suspend your own tenant")

    # Suspend tenant
    suspended_tenant = await tenant_service.suspend_tenant(
        db=db,
        tenant_id=tenant_uuid,
        request=suspend_request,
    )

    if not suspended_tenant:
        raise BadRequestException(f"Failed to suspend tenant {tenant_id}")

    await db.commit()

    logger.info(f"Suspended tenant {tenant_id} (reason: {suspend_request.reason})")
    return suspended_tenant


@router.post("/{tenant_id}/activate", response_model=TenantRead)
async def activate_tenant(
    _request: Request,
    tenant_id: str,
    activate_request: TenantActivateRequest,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> TenantRead:
    """
    Activate a suspended tenant, restoring all operations.
    Admin only endpoint.

    Returns updated tenant with active status.
    """
    logger.info(f"Admin {admin_user['id']} activating tenant {tenant_id}")

    # Try to parse as UUID
    try:
        tenant_uuid = uuid_pkg.UUID(tenant_id)
    except ValueError:
        raise BadRequestException(f"Invalid tenant ID format: {tenant_id}")

    # Check if tenant exists and is suspended
    tenant = await tenant_service.get_tenant(db, tenant_uuid)
    if not tenant:
        raise NotFoundException(f"Tenant {tenant_id} not found")

    if tenant.status == "active":
        raise BadRequestException(f"Tenant {tenant_id} is already active")

    # Activate tenant
    activated_tenant = await tenant_service.activate_tenant(
        db=db,
        tenant_id=tenant_uuid,
        request=activate_request,
    )

    if not activated_tenant:
        raise BadRequestException(f"Failed to activate tenant {tenant_id}")

    await db.commit()

    logger.info(f"Activated tenant {tenant_id} (reason: {activate_request.reason})")
    return activated_tenant
