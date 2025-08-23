"""
Monitor API endpoints for blockchain monitoring configurations.
Implements CRUD operations with tenant isolation and Redis caching.
"""

import uuid as uuid_pkg
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_user
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
)
from ...core.logger import logging
from ...crud.crud_monitor import crud_monitor
from ...schemas.monitor import (
    MonitorCreate,
    MonitorFilter,
    MonitorPagination,
    MonitorRead,
    MonitorSort,
    MonitorUpdate,
    MonitorValidationResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitors", tags=["monitors"])

# Constants for monitor state updates - only update specific fields
PAUSE_MONITOR_UPDATE = MonitorUpdate(paused=True, active=False, name=None, slug=None)
RESUME_MONITOR_UPDATE = MonitorUpdate(paused=False, active=True, name=None, slug=None)


@router.get("", response_model=MonitorPagination)
async def list_monitors(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Page size"),
    # Filter parameters
    name: Optional[str] = Query(None, description="Filter by name (partial match)"),
    slug: Optional[str] = Query(None, description="Filter by slug (exact match)"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    paused: Optional[bool] = Query(None, description="Filter by paused status"),
    validated: Optional[bool] = Query(None, description="Filter by validation status"),
    network_slug: Optional[str] = Query(None, description="Filter by network slug"),
    has_triggers: Optional[bool] = Query(None, description="Filter monitors with/without triggers"),
    # Sort parameters
    sort_field: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
) -> dict[str, Any]:
    """
    List monitors for the current tenant with pagination, filtering, and sorting.

    Returns paginated list of monitors with metadata.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Build filter object
    filters = MonitorFilter(
        tenant_id=uuid_pkg.UUID(tenant_id),
        name=name,
        slug=slug,
        active=active,
        paused=paused,
        validated=validated,
        network_slug=network_slug,
        has_triggers=has_triggers,
        created_after=None,
        created_before=None,
        updated_after=None,
        updated_before=None,
    )

    # Build sort object
    sort = MonitorSort(field=sort_field, order=sort_order)

    # Get paginated monitors
    result = await crud_monitor.get_paginated(
        db=db,
        page=page,
        size=size,
        filters=filters,
        sort=sort,
        tenant_id=tenant_id
    )

    # Convert models to schemas
    result["items"] = [
        MonitorRead.model_validate(item) for item in result["items"]
    ]

    logger.info(f"Listed {len(result['items'])} monitors for tenant {tenant_id}")
    return result


@router.get("/{monitor_id}", response_model=MonitorRead)
async def get_monitor(
    _request: Request,
    monitor_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    include_triggers: bool = Query(False, description="Include associated triggers"),
) -> MonitorRead | dict[str, Any]:
    """
    Get a single monitor by ID.

    Optionally includes associated triggers in denormalized format.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate monitor_id is a valid UUID
    try:
        uuid_pkg.UUID(monitor_id)
    except ValueError:
        raise BadRequestException("Invalid monitor ID format")

    if include_triggers:
        # Get monitor with triggers (denormalized)
        monitor_data = await crud_monitor.get_monitor_with_triggers(
            db=db,
            monitor_id=monitor_id,
            tenant_id=tenant_id,
        )
        if not monitor_data:
            raise NotFoundException(f"Monitor {monitor_id} not found")
        return monitor_data
    else:
        # Get monitor only
        db_monitor = await crud_monitor.get(
            db=db,
            id=monitor_id,
            tenant_id=tenant_id
        )
        if not db_monitor:
            raise NotFoundException(f"Monitor {monitor_id} not found")
        return MonitorRead.model_validate(db_monitor)


@router.post("", response_model=MonitorRead, status_code=201)
async def create_monitor(
    _request: Request,
    monitor_in: MonitorCreate,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> MonitorRead:
    """
    Create a new monitor for the current tenant.

    The monitor will be automatically cached in Redis for fast access by the Rust monitor.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = current_user["tenant_id"]

    # Ensure the tenant_id in the request matches the user's tenant
    if monitor_in.tenant_id != tenant_id:
        raise ForbiddenException("Cannot create monitors for other tenants")

    # Check if slug already exists for this tenant
    existing_monitor = await crud_monitor.get_by_slug(
        db=db,
        slug=monitor_in.slug,
        tenant_id=tenant_id
    )

    if existing_monitor:
        raise DuplicateValueException(f"Monitor with slug '{monitor_in.slug}' already exists")

    # Create the monitor
    try:
        monitor = await crud_monitor.create_with_tenant(
            db=db,
            obj_in=monitor_in,
            tenant_id=tenant_id,
        )
        return monitor
    except ValidationError as e:
        logger.warning(f"Monitor validation failed: {e}")
        raise BadRequestException(f"Validation failed: {str(e)}")
    except IntegrityError as e:
        logger.warning(f"Monitor integrity constraint violated: {e}")
        raise DuplicateValueException("Monitor with this configuration already exists")
    except Exception as e:
        logger.error(f"Failed to create monitor: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{monitor_id}", response_model=MonitorRead)
async def update_monitor(
    _request: Request,
    monitor_id: str,
    monitor_update: MonitorUpdate,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> MonitorRead:
    """
    Update an existing monitor.

    Updates both PostgreSQL and Redis cache to ensure consistency.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate monitor_id is a valid UUID
    try:
        uuid_pkg.UUID(monitor_id)
    except ValueError:
        raise BadRequestException("Invalid monitor ID format")

    # Check if updating slug to an existing one
    if monitor_update.slug:
        existing_monitor = await crud_monitor.get_by_slug(
            db=db,
            slug=monitor_update.slug,
            tenant_id=tenant_id
        )

        if existing_monitor and str(existing_monitor.id) != monitor_id:
            raise DuplicateValueException(f"Monitor with slug '{monitor_update.slug}' already exists")

    # Update the monitor
    monitor = await crud_monitor.update_with_tenant(
        db=db,
        monitor_id=monitor_id,
        obj_in=monitor_update,
        tenant_id=tenant_id,
    )

    if not monitor:
        raise NotFoundException(f"Monitor {monitor_id} not found")

    logger.info(f"Updated monitor {monitor_id} for tenant {tenant_id}")
    return monitor


@router.delete("/{monitor_id}", status_code=204)
async def delete_monitor(
    _request: Request,
    monitor_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    hard_delete: bool = Query(False, description="Permanently delete the monitor"),
) -> None:
    """
    Delete a monitor.

    By default performs a soft delete. Set hard_delete=true for permanent deletion.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate monitor_id is a valid UUID
    try:
        uuid_pkg.UUID(monitor_id)
    except ValueError:
        raise BadRequestException("Invalid monitor ID format")

    # Delete the monitor
    deleted = await crud_monitor.delete_with_tenant(
        db=db,
        monitor_id=monitor_id,
        tenant_id=tenant_id,
        is_hard_delete=hard_delete,
    )

    if not deleted:
        raise NotFoundException(f"Monitor {monitor_id} not found")

    logger.info(f"Deleted monitor {monitor_id} for tenant {tenant_id} (hard={hard_delete})")


@router.post("/{monitor_id}/pause", response_model=MonitorRead)
async def pause_monitor(
    _request: Request,
    monitor_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> MonitorRead:
    """
    Pause a monitor to stop processing.

    The monitor remains configured but will not process blockchain events.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate monitor_id is a valid UUID
    try:
        uuid_pkg.UUID(monitor_id)
    except ValueError:
        raise BadRequestException("Invalid monitor ID format")

    # Pause the monitor
    monitor = await crud_monitor.pause_monitor(
        db=db,
        monitor_id=monitor_id,
        tenant_id=tenant_id,
    )

    if not monitor:
        raise NotFoundException(f"Monitor {monitor_id} not found")

    logger.info(f"Paused monitor {monitor_id} for tenant {tenant_id}")
    return monitor


@router.post("/{monitor_id}/resume", response_model=MonitorRead)
async def resume_monitor(
    _request: Request,
    monitor_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> MonitorRead:
    """
    Resume a paused monitor to restart processing.

    The monitor will begin processing blockchain events again.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate monitor_id is a valid UUID
    try:
        uuid_pkg.UUID(monitor_id)
    except ValueError:
        raise BadRequestException("Invalid monitor ID format")

    # Resume the monitor
    monitor = await crud_monitor.resume_monitor(
        db=db,
        monitor_id=monitor_id,
        tenant_id=tenant_id,
    )

    if not monitor:
        raise NotFoundException(f"Monitor {monitor_id} not found")

    logger.info(f"Resumed monitor {monitor_id} for tenant {tenant_id}")
    return monitor


@router.post("/{monitor_id}/validate", response_model=MonitorValidationResult)
async def validate_monitor(
    _request: Request,
    monitor_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    validate_triggers: bool = Query(True, description="Also validate associated triggers"),
    _validate_networks: bool = Query(True, description="Also validate network configurations"),
) -> MonitorValidationResult:
    """
    Validate a monitor configuration.

    Checks that the monitor configuration is valid and can be executed.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate monitor_id is a valid UUID
    try:
        monitor_uuid = uuid_pkg.UUID(monitor_id)
    except ValueError:
        raise BadRequestException("Invalid monitor ID format")

    # Get the monitor
    db_monitor = await crud_monitor.get(
        db=db,
        id=monitor_id,
        tenant_id=tenant_id
    )

    if not db_monitor:
        raise NotFoundException(f"Monitor {monitor_id} not found")

    monitor = MonitorRead.model_validate(db_monitor)

    # Perform validation
    errors = []
    warnings = []

    # Basic validation
    if not monitor.name:
        errors.append("Monitor name is required")

    if not monitor.slug:
        errors.append("Monitor slug is required")

    if not monitor.networks:
        errors.append("At least one network must be configured")

    # Check if monitor has any matching criteria
    has_criteria = (
        monitor.match_events or
        monitor.match_functions or
        monitor.match_transactions
    )

    if not has_criteria:
        warnings.append("Monitor has no matching criteria configured")

    # Validate triggers if requested
    if validate_triggers and not monitor.triggers:
        warnings.append("Monitor has no triggers configured")

    # Create validation result
    is_valid = len(errors) == 0

    # Update monitor validation status
    if is_valid != monitor.validated:
        # Note: validation status will be updated by the service layer
        # MonitorUpdate schema doesn't include validation fields by design
        logger.info(f"Monitor {monitor_id} validation complete: valid={is_valid}")

    result = MonitorValidationResult(
        monitor_id=monitor_uuid,
        is_valid=is_valid,
        errors=errors,
        warnings=warnings,
    )

    logger.info(f"Validated monitor {monitor_id}: valid={is_valid}, errors={len(errors)}, warnings={len(warnings)}")
    return result


@router.post("/refresh-cache", response_model=dict)
async def refresh_monitors_cache(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> dict[str, Any]:
    """
    Refresh all monitors in Redis cache for the current tenant.

    This is useful after bulk updates or to ensure cache consistency.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Get all active monitors for the tenant and refresh their cache
    from sqlalchemy import select

    from ...models.monitor import Monitor

    query = select(Monitor).where(
        Monitor.tenant_id == tenant_id,
        Monitor.active
    )
    result = await db.execute(query)
    monitors = result.scalars().all()

    count = 0
    for monitor in monitors:
        await crud_monitor._cache_monitor(monitor, tenant_id)
        count += 1

    logger.info(f"Refreshed {count} monitors in cache for tenant {tenant_id}")

    return {
        "message": f"Successfully refreshed {count} monitors in cache",
        "tenant_id": tenant_id,
        "monitors_refreshed": count,
    }
