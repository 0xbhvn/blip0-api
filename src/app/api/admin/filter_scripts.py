"""
Admin filter script API endpoints for platform administration.
Implements CRUD operations for managing custom filter scripts.
"""

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_admin, rate_limiter_dependency
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    NotFoundException,
)
from ...core.logger import logging
from ...schemas.filter_script import (
    FilterScriptAdminPagination,
    FilterScriptCreate,
    FilterScriptFilter,
    FilterScriptPagination,
    FilterScriptSort,
    FilterScriptUpdate,
    FilterScriptValidationRequest,
    FilterScriptValidationResult,
    FilterScriptWithContent,
)
from ...services.filter_script_service import filter_script_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/filter-scripts", tags=["admin-filter-scripts"])


@router.get("", response_model=FilterScriptPagination)
async def list_filter_scripts(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
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
    List all filter scripts with pagination, filtering, and sorting.
    Admin only endpoint for managing platform filter scripts.

    Returns paginated list of filter scripts with metadata.
    """
    logger.info(f"Admin {admin_user['id']} listing filter scripts (page={page}, size={size})")

    # Build filter object
    filters = FilterScriptFilter(
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
    result = await filter_script_service.list_filter_scripts(
        db=db,
        page=page,
        size=size,
        filters=filters,
        sort=sort,
    )

    # If include_content is requested, fetch content for each script
    if include_content:
        items_with_content: list[FilterScriptWithContent] = []
        for script in result.items:
            script_with_content = await filter_script_service.get_filter_script(
                db=db,
                script_id=str(script.id),
                include_content=True,
            )
            # Only append if it's actually a FilterScriptWithContent
            if script_with_content and isinstance(script_with_content, FilterScriptWithContent):
                items_with_content.append(script_with_content)

        # Return admin pagination with content
        admin_result = FilterScriptAdminPagination(
            items=items_with_content,
            total=result.total if hasattr(result, 'total') else 0,
            page=result.page if hasattr(result, 'page') else page,
            size=result.size if hasattr(result, 'size') else size,
            pages=result.pages if hasattr(result, 'pages') else 0,
        )
        logger.info(f"Returned {len(admin_result.items)} filter scripts with content")
        return admin_result.model_dump()

    if hasattr(result, 'items') and hasattr(result, 'total'):
        logger.info(f"Returned {len(result.items)} filter scripts (total={result.total})")
        return result.model_dump()
    elif isinstance(result, dict):
        # Handle dict return type
        logger.info(f"Returned {len(result.get('items', []))} filter scripts (total={result.get('total', 0)})")
        return result
    else:
        # Fallback
        return {"items": [], "total": 0, "page": page, "size": size, "pages": 0}


@router.post("", response_model=FilterScriptWithContent, status_code=201)
async def create_filter_script(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
    script_in: FilterScriptCreate,
) -> FilterScriptWithContent:
    """
    Create a new filter script.
    Admin only endpoint for adding new filter scripts.

    Args:
        script_in: Filter script data including script content

    Returns:
        Created filter script with content

    Raises:
        409: If script with same slug already exists
        400: If validation fails or file operations fail
    """
    logger.info(f"Admin {admin_user['id']} creating filter script {script_in.slug}")

    try:
        script = await filter_script_service.create_filter_script(
            db=db,
            script_in=script_in,
        )

        logger.info(f"Created filter script {script.id} ({script.slug})")
        return script

    except IntegrityError as e:
        if "unique_filter_script_slug" in str(e):
            raise DuplicateValueException(f"Filter script with slug '{script_in.slug}' already exists")
        raise BadRequestException(str(e))
    except ValueError as e:
        # File operation errors
        raise BadRequestException(str(e))
    except Exception as e:
        logger.error(f"Failed to create filter script: {e}")
        raise BadRequestException(f"Failed to create filter script: {str(e)}")


@router.get("/{script_id}", response_model=FilterScriptWithContent)
async def get_filter_script(
    _request: Request,
    script_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
) -> FilterScriptWithContent:
    """
    Get a specific filter script by ID with content.
    Admin only endpoint for viewing filter script details.

    Args:
        script_id: Filter script UUID

    Returns:
        Filter script details with content

    Raises:
        404: If filter script not found
    """
    logger.info(f"Admin {admin_user['id']} getting filter script {script_id}")

    script = await filter_script_service.get_filter_script(
        db=db,
        script_id=script_id,
        include_content=True,
    )

    if not script:
        raise NotFoundException(f"Filter script {script_id} not found")

    # Ensure we return FilterScriptWithContent type
    if not isinstance(script, FilterScriptWithContent):
        # If it's a FilterScriptRead, convert it
        if hasattr(script, 'id'):
            # Re-fetch with content
            script_with_content = await filter_script_service.get_filter_script(
                db=db,
                script_id=script_id,
                include_content=True,
            )
            if script_with_content and isinstance(script_with_content, FilterScriptWithContent):
                return script_with_content

    if script and isinstance(script, FilterScriptWithContent):
        return script
    else:
        raise NotFoundException(f"Filter script {script_id} not found")


@router.put("/{script_id}", response_model=FilterScriptWithContent)
async def update_filter_script(
    _request: Request,
    script_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
    script_update: FilterScriptUpdate,
) -> FilterScriptWithContent:
    """
    Update a filter script.
    Admin only endpoint for modifying filter scripts.

    Args:
        script_id: Filter script UUID
        script_update: Updated filter script data

    Returns:
        Updated filter script with content

    Raises:
        404: If filter script not found
        409: If update would create duplicate
        400: If file operations fail
    """
    logger.info(f"Admin {admin_user['id']} updating filter script {script_id}")

    try:
        script = await filter_script_service.update_filter_script(
            db=db,
            script_id=script_id,
            script_update=script_update,
        )

        if not script:
            raise NotFoundException(f"Filter script {script_id} not found")

        logger.info(f"Updated filter script {script.id}")
        return script

    except IntegrityError as e:
        if "unique_filter_script_slug" in str(e):
            raise DuplicateValueException(f"Filter script with slug '{script_update.slug}' already exists")
        raise BadRequestException(str(e))
    except ValueError as e:
        # File operation errors
        raise BadRequestException(str(e))
    except Exception as e:
        if isinstance(e, NotFoundException):
            raise
        logger.error(f"Failed to update filter script: {e}")
        raise BadRequestException(f"Failed to update filter script: {str(e)}")


@router.delete("/{script_id}", status_code=204)
async def delete_filter_script(
    _request: Request,
    script_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
    hard_delete: bool = Query(False, description="Perform hard delete from database"),
    delete_file: bool = Query(False, description="Also delete the script file from filesystem"),
) -> None:
    """
    Delete a filter script.
    Admin only endpoint for removing filter scripts.

    Args:
        script_id: Filter script UUID
        hard_delete: If true, permanently delete from database. Otherwise, soft delete.
        delete_file: If true, also delete the script file from filesystem.

    Raises:
        404: If filter script not found
        400: If filter script is in use by monitors
    """
    logger.info(
        f"Admin {admin_user['id']} deleting filter script {script_id} "
        f"(hard={hard_delete}, file={delete_file})"
    )

    # Check if script exists
    script = await filter_script_service.get_filter_script(db=db, script_id=script_id)
    if not script:
        raise NotFoundException(f"Filter script {script_id} not found")

    # TODO: Check if script is in use by any monitors
    # For now, we'll allow deletion but log a warning

    try:
        success = await filter_script_service.delete_filter_script(
            db=db,
            script_id=script_id,
            hard_delete=hard_delete,
            delete_file=delete_file,
        )

        if not success:
            raise BadRequestException(f"Failed to delete filter script {script_id}")

        logger.info(f"Deleted filter script {script_id} (hard={hard_delete}, file={delete_file})")

    except Exception as e:
        logger.error(f"Failed to delete filter script: {e}")
        raise BadRequestException(f"Failed to delete filter script: {str(e)}")


@router.post("/{script_id}/validate", response_model=FilterScriptValidationResult)
async def validate_filter_script(
    _request: Request,
    script_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    admin_user: Annotated[dict, Depends(get_current_admin)],
    _rate_limit: Annotated[None, Depends(rate_limiter_dependency)],
    validation_request: Optional[FilterScriptValidationRequest] = None,
) -> FilterScriptValidationResult:
    """
    Validate a filter script by checking syntax and optionally running a test.
    Admin only endpoint for verifying filter script correctness.

    Args:
        script_id: Filter script UUID
        validation_request: Optional test input for validation

    Returns:
        Validation result with errors/warnings

    Raises:
        404: If filter script not found
    """
    logger.info(f"Admin {admin_user['id']} validating filter script {script_id}")

    # Check if script exists
    script = await filter_script_service.get_filter_script(db=db, script_id=script_id)
    if not script:
        raise NotFoundException(f"Filter script {script_id} not found")

    try:
        # Validate filter script
        result = await filter_script_service.validate_filter_script(
            db=db,
            script_id=script_id,
            validation_request=validation_request or FilterScriptValidationRequest(),
        )

        logger.info(f"Validated filter script {script_id}: valid={result.valid}")
        return result

    except Exception as e:
        logger.error(f"Failed to validate filter script: {e}")
        # Return validation failure instead of raising exception
        return FilterScriptValidationResult(
            valid=False,
            errors=[f"Validation failed: {str(e)}"],
            warnings=None,
            test_output=None,
            execution_time_ms=None,
        )
