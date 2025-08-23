"""
Filter script API endpoints for tenant-managed custom filtering logic.
Implements CRUD operations with tenant isolation.
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
from ...crud.crud_filter_script import crud_filter_script
from ...schemas.filter_script import (
    FilterScriptCreate,
    FilterScriptFilter,
    FilterScriptPagination,
    FilterScriptRead,
    FilterScriptSort,
    FilterScriptUpdate,
    FilterScriptValidationRequest,
    FilterScriptValidationResult,
    FilterScriptWithContent,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/filter-scripts", tags=["filter-scripts"])


@router.get("", response_model=FilterScriptPagination)
async def list_filter_scripts(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Page size"),
    # Filter parameters
    name: Optional[str] = Query(None, description="Filter by name (partial match)"),
    slug: Optional[str] = Query(None, description="Filter by slug (exact match)"),
    language: Optional[str] = Query(None, description="Filter by language (bash/python/javascript)"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    validated: Optional[bool] = Query(None, description="Filter by validation status"),
    # Sort parameters
    sort_field: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
    # Include content
    include_content: bool = Query(False, description="Include script content in response"),
) -> dict[str, Any]:
    """
    List filter scripts for the current tenant with pagination, filtering, and sorting.

    Returns paginated list of filter scripts with metadata.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Build filter object
    filters = FilterScriptFilter(
        tenant_id=uuid_pkg.UUID(tenant_id),
        name=name,
        slug=slug,
        language=language,
        active=active,
        validated=validated,
        created_after=None,
        created_before=None,
    )

    # Build sort object
    sort = FilterScriptSort(field=sort_field, order=sort_order)

    # Get paginated filter scripts
    result = await crud_filter_script.get_paginated(
        db=db,
        page=page,
        size=size,
        filters=filters,
        sort=sort,
        tenant_id=tenant_id
    )

    # Convert models to schemas
    items = []
    for item in result["items"]:
        if include_content:
            # Get with content
            script_with_content = await crud_filter_script.get_with_cache(
                db=db,
                script_id=str(item.id),
                tenant_id=tenant_id,
                include_content=True
            )
            if script_with_content:
                items.append(script_with_content)
        else:
            items.append(FilterScriptRead.model_validate(item))

    result["items"] = items

    logger.info(f"Listed {len(result['items'])} filter scripts for tenant {tenant_id}")
    return result


@router.get("/{script_id}", response_model=FilterScriptWithContent)
async def get_filter_script(
    _request: Request,
    script_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> FilterScriptWithContent | dict[str, Any]:
    """
    Get a single filter script by ID with content.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate script_id is a valid UUID
    try:
        uuid_pkg.UUID(script_id)
    except ValueError:
        raise BadRequestException("Invalid filter script ID format")

    # Get filter script with content
    script = await crud_filter_script.get_with_cache(
        db=db,
        script_id=script_id,
        tenant_id=tenant_id,
        include_content=True,
    )

    if not script:
        raise NotFoundException(f"Filter script {script_id} not found")

    # Ensure it returns FilterScriptWithContent
    if isinstance(script, dict):
        return FilterScriptWithContent(**script)
    elif isinstance(script, FilterScriptWithContent):
        return script
    else:
        # Convert FilterScriptRead to FilterScriptWithContent if needed
        return FilterScriptWithContent(**script.model_dump(), script_content=None)


@router.post("", response_model=FilterScriptWithContent, status_code=201)
async def create_filter_script(
    _request: Request,
    script_in: FilterScriptCreate,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> FilterScriptWithContent:
    """
    Create a new filter script for the current tenant.

    The script will be stored in the filesystem and cached in Redis for fast access.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = current_user["tenant_id"]

    # Ensure the tenant_id in the request matches the user's tenant
    if script_in.tenant_id != tenant_id:
        raise ForbiddenException("Cannot create filter scripts for other tenants")

    # Check if slug already exists for this tenant
    existing_script = await crud_filter_script.get_by_slug(
        db=db,
        slug=script_in.slug,
        tenant_id=str(tenant_id)
    )

    if existing_script:
        raise DuplicateValueException(f"Filter script with slug '{script_in.slug}' already exists")

    # Create the filter script
    try:
        script = await crud_filter_script.create_with_tenant(
            db=db,
            obj_in=script_in,
            tenant_id=str(tenant_id),
        )
        return script
    except ValidationError as e:
        logger.warning(f"Filter script validation failed: {e}")
        raise BadRequestException(f"Validation failed: {str(e)}")
    except IntegrityError as e:
        logger.warning(f"Filter script integrity constraint violated: {e}")
        raise DuplicateValueException("Filter script with this configuration already exists")
    except Exception as e:
        logger.error(f"Failed to create filter script: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{script_id}", response_model=FilterScriptWithContent)
async def update_filter_script(
    _request: Request,
    script_id: str,
    script_update: FilterScriptUpdate,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> FilterScriptWithContent:
    """
    Update an existing filter script.

    Updates both filesystem and Redis cache to ensure consistency.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate script_id is a valid UUID
    try:
        uuid_pkg.UUID(script_id)
    except ValueError:
        raise BadRequestException("Invalid filter script ID format")

    # Check if updating slug to an existing one
    if script_update.slug:
        existing_script = await crud_filter_script.get_by_slug(
            db=db,
            slug=script_update.slug,
            tenant_id=tenant_id
        )

        if existing_script and str(existing_script.id) != script_id:
            raise DuplicateValueException(f"Filter script with slug '{script_update.slug}' already exists")

    # Update the filter script
    script = await crud_filter_script.update_with_tenant(
        db=db,
        script_id=script_id,
        obj_in=script_update,
        tenant_id=tenant_id,
    )

    if not script:
        raise NotFoundException(f"Filter script {script_id} not found")

    logger.info(f"Updated filter script {script_id} for tenant {tenant_id}")
    return script


@router.delete("/{script_id}", status_code=204)
async def delete_filter_script(
    _request: Request,
    script_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    hard_delete: bool = Query(False, description="Permanently delete the filter script"),
    delete_file: bool = Query(False, description="Also delete the script file from filesystem"),
) -> None:
    """
    Delete a filter script.

    By default performs a soft delete. Set hard_delete=true for permanent deletion.
    Set delete_file=true to also remove the script file from the filesystem.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate script_id is a valid UUID
    try:
        uuid_pkg.UUID(script_id)
    except ValueError:
        raise BadRequestException("Invalid filter script ID format")

    # Delete the filter script
    deleted = await crud_filter_script.delete_with_tenant(
        db=db,
        script_id=script_id,
        tenant_id=tenant_id,
        is_hard_delete=hard_delete,
        delete_file=delete_file,
    )

    if not deleted:
        raise NotFoundException(f"Filter script {script_id} not found")

    logger.info(
        f"Deleted filter script {script_id} for tenant {tenant_id} "
        f"(hard={hard_delete}, delete_file={delete_file})"
    )


@router.post("/{script_id}/validate", response_model=FilterScriptValidationResult)
async def validate_filter_script(
    _request: Request,
    script_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    test_execution: bool = Query(False, description="Test script execution"),
    check_syntax: bool = Query(True, description="Check script syntax"),
) -> FilterScriptValidationResult:
    """
    Validate a filter script configuration.

    Tests that the script syntax is valid and optionally executes it.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate script_id is a valid UUID
    try:
        script_uuid = uuid_pkg.UUID(script_id)
    except ValueError:
        raise BadRequestException("Invalid filter script ID format")

    # Check that script belongs to tenant
    script = await crud_filter_script.get(db=db, id=script_id)
    if not script:
        raise NotFoundException(f"Filter script {script_id} not found")

    # Check tenant ownership
    script_tenant_id = script.get('tenant_id') if isinstance(script, dict) else script.tenant_id
    if str(script_tenant_id) != tenant_id:
        raise NotFoundException(f"Filter script {script_id} not found")

    # Create validation request
    validation_request = FilterScriptValidationRequest(
        script_id=script_uuid,
        test_execution=test_execution,
        check_syntax=check_syntax,
    )

    # Perform validation
    result = await crud_filter_script.validate_filter_script(
        db=db,
        validation_request=validation_request
    )

    logger.info(f"Validated filter script {script_id}: valid={result.is_valid}")
    return result
