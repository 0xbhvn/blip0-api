"""
Trigger API endpoints for action configurations.
Implements CRUD operations with type-specific handling for email and webhook triggers.
"""

import uuid as uuid_pkg
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...api.dependencies import get_current_user, rate_limiter_dependency
from ...core.db.database import async_get_db
from ...core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
)
from ...core.logger import logging
from ...crud.crud_trigger import crud_trigger
from ...schemas.trigger import (
    EmailTriggerBase,
    TriggerCreate,
    TriggerFilter,
    TriggerPagination,
    TriggerRead,
    TriggerSort,
    TriggerTestRequest,
    TriggerTestResult,
    TriggerUpdate,
    TriggerValidationRequest,
    TriggerValidationResult,
    WebhookTriggerBase,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/triggers", tags=["triggers"])

# Constants for trigger state updates - only update specific fields
ENABLE_TRIGGER_UPDATE = TriggerUpdate(active=True, name=None, slug=None)
DISABLE_TRIGGER_UPDATE = TriggerUpdate(active=False, name=None, slug=None)


@router.get("", response_model=TriggerPagination)
async def list_triggers(
    _request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(50, ge=1, le=100, description="Page size"),
    # Filter parameters
    name: Optional[str] = Query(None, description="Filter by name (partial match)"),
    slug: Optional[str] = Query(None, description="Filter by slug (exact match)"),
    trigger_type: Optional[str] = Query(None, description="Filter by trigger type (email/webhook)"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
    validated: Optional[bool] = Query(None, description="Filter by validation status"),
    # Sort parameters
    sort_field: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order"),
) -> dict[str, Any]:
    """
    List triggers for the current tenant with pagination, filtering, and sorting.

    Returns paginated list of triggers with metadata.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Build filter object
    filters = TriggerFilter(
        tenant_id=uuid_pkg.UUID(tenant_id),
        name=name,
        slug=slug,
        trigger_type=trigger_type,
        active=active,
        validated=validated,
        created_after=None,
        created_before=None,
    )

    # Build sort object
    sort = TriggerSort(field=sort_field, order=sort_order)

    # Get paginated triggers
    result = await crud_trigger.get_paginated(
        db=db,
        page=page,
        size=size,
        filters=filters,
        sort=sort,
        tenant_id=tenant_id,
    )

    # Convert models to schemas
    result["items"] = [
        TriggerRead.model_validate(item) for item in result["items"]
    ]

    logger.info(f"Listed {len(result['items'])} triggers for tenant {tenant_id}")
    return result


@router.get("/{trigger_id}", response_model=TriggerRead)
async def get_trigger(
    _request: Request,
    trigger_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> TriggerRead:
    """
    Get a single trigger by ID.

    Returns trigger with its type-specific configuration.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate trigger_id is a valid UUID
    try:
        uuid_pkg.UUID(trigger_id)
    except ValueError:
        raise BadRequestException("Invalid trigger ID format")

    # Get trigger
    db_trigger = await crud_trigger.get(
        db=db,
        id=trigger_id,
        tenant_id=tenant_id,
    )

    if not db_trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    return TriggerRead.model_validate(db_trigger)


@router.delete("/{trigger_id}", status_code=204)
async def delete_trigger(
    _request: Request,
    trigger_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    hard_delete: bool = Query(False, description="Permanently delete the trigger"),
) -> None:
    """
    Delete a trigger.

    By default performs a soft delete. Set hard_delete=true for permanent deletion.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate trigger_id is a valid UUID
    try:
        uuid_pkg.UUID(trigger_id)
    except ValueError:
        raise BadRequestException("Invalid trigger ID format")

    # Delete the trigger
    deleted = await crud_trigger.delete_with_tenant(
        db=db,
        trigger_id=trigger_id,
        tenant_id=tenant_id,
        is_hard_delete=hard_delete,
    )

    if not deleted:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    logger.info(f"Deleted trigger {trigger_id} for tenant {tenant_id} (hard={hard_delete})")


@router.put("/{trigger_id}/enable", response_model=TriggerRead)
async def enable_trigger(
    _request: Request,
    trigger_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> TriggerRead:
    """
    Enable a trigger to start processing.

    Sets the trigger's active status to true.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate trigger_id is a valid UUID
    try:
        uuid_pkg.UUID(trigger_id)
    except ValueError:
        raise BadRequestException("Invalid trigger ID format")

    # Enable the trigger
    trigger = await crud_trigger.enable_trigger(
        db=db,
        trigger_id=trigger_id,
        tenant_id=tenant_id,
    )

    if not trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    logger.info(f"Enabled trigger {trigger_id} for tenant {tenant_id}")
    return trigger


@router.put("/{trigger_id}/disable", response_model=TriggerRead)
async def disable_trigger(
    _request: Request,
    trigger_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> TriggerRead:
    """
    Disable a trigger to stop processing.

    Sets the trigger's active status to false.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate trigger_id is a valid UUID
    try:
        uuid_pkg.UUID(trigger_id)
    except ValueError:
        raise BadRequestException("Invalid trigger ID format")

    # Disable the trigger
    trigger = await crud_trigger.disable_trigger(
        db=db,
        trigger_id=trigger_id,
        tenant_id=tenant_id,
    )

    if not trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    logger.info(f"Disabled trigger {trigger_id} for tenant {tenant_id}")
    return trigger


@router.post("/email", response_model=TriggerRead, status_code=201)
async def create_email_trigger(
    _request: Request,
    email_config: EmailTriggerBase,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    name: str = Query(..., description="Trigger name"),
    slug: str = Query(..., description="Trigger slug"),
    description: Optional[str] = Query(None, description="Trigger description"),
) -> TriggerRead:
    """
    Create a new email trigger.

    Validates email addresses and SMTP configuration.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = current_user["tenant_id"]

    # Check if slug already exists for this tenant
    existing = await crud_trigger.get_by_slug(
        db=db,
        slug=slug,
        tenant_id=tenant_id,
    )

    if existing:
        raise DuplicateValueException(f"Trigger with slug '{slug}' already exists")

    # Create the trigger
    trigger_in = TriggerCreate(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        description=description,
        trigger_type="email",
        email_config=email_config,
        webhook_config=None,
    )

    try:
        trigger = await crud_trigger.create_with_config(
            db=db,
            obj_in=trigger_in,
        )
        logger.info(f"Created email trigger {trigger.id} for tenant {tenant_id}")
        return trigger
    except ValidationError as e:
        logger.warning(f"Email trigger validation failed: {e}")
        raise BadRequestException(f"Validation failed: {str(e)}")
    except IntegrityError as e:
        logger.warning(f"Email trigger integrity constraint violated: {e}")
        raise DuplicateValueException("Trigger with this configuration already exists")
    except Exception as e:
        logger.error(f"Failed to create email trigger: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/email/{trigger_id}", response_model=TriggerRead)
async def update_email_trigger(
    _request: Request,
    trigger_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    name: Optional[str] = Query(None, description="Trigger name"),
    slug: Optional[str] = Query(None, description="Trigger slug"),
    description: Optional[str] = Query(None, description="Trigger description"),
    active: Optional[bool] = Query(None, description="Active status"),
    email_config: Optional[EmailTriggerBase] = None,
) -> TriggerRead:
    """
    Update an existing email trigger.

    Only email triggers can be updated through this endpoint.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate trigger_id is a valid UUID
    try:
        uuid_pkg.UUID(trigger_id)
    except ValueError:
        raise BadRequestException("Invalid trigger ID format")

    # Get existing trigger to verify it's an email trigger
    existing_db_trigger = await crud_trigger.get(
        db=db,
        id=trigger_id,
        tenant_id=tenant_id,
    )
    existing_trigger = TriggerRead.model_validate(existing_db_trigger) if existing_db_trigger else None

    if not existing_trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    if existing_trigger.trigger_type != "email":
        raise BadRequestException(f"Trigger {trigger_id} is not an email trigger")

    # Check if updating slug to an existing one
    if slug and slug != existing_trigger.slug:
        existing_slug = await crud_trigger.get_by_slug(
            db=db,
            slug=slug,
            tenant_id=tenant_id,
        )
        if existing_slug:
            raise DuplicateValueException(f"Trigger with slug '{slug}' already exists")

    # Update the trigger
    trigger_update = TriggerUpdate(
        name=name,
        slug=slug,
        description=description,
        active=active,
        email_config=email_config,
        webhook_config=None,
    )

    trigger = await crud_trigger.update_with_config(
        db=db,
        trigger_id=trigger_id,
        obj_in=trigger_update,
        tenant_id=tenant_id,
    )

    if not trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    logger.info(f"Updated email trigger {trigger_id} for tenant {tenant_id}")
    return trigger


@router.post(
    "/email/{trigger_id}/test",
    response_model=TriggerTestResult,
    dependencies=[Depends(rate_limiter_dependency)],
)
async def send_test_email_trigger(
    _request: Request,
    trigger_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    test_data: dict[str, Any] = Body(default_factory=dict, description="Sample data for test"),
) -> TriggerTestResult:
    """
    Send a test email using the trigger configuration.

    Rate limited to prevent abuse.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate trigger_id is a valid UUID
    try:
        uuid_pkg.UUID(trigger_id)
    except ValueError:
        raise BadRequestException("Invalid trigger ID format")

    # Get trigger to verify it exists and is an email trigger
    db_trigger = await crud_trigger.get(
        db=db,
        id=trigger_id,
        tenant_id=tenant_id,
    )
    trigger = TriggerRead.model_validate(db_trigger) if db_trigger else None

    if not trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    if trigger.trigger_type != "email":
        raise BadRequestException(f"Trigger {trigger_id} is not an email trigger")

    # Test the trigger
    test_request = TriggerTestRequest(
        trigger_id=uuid_pkg.UUID(trigger_id),
        test_data=test_data,
    )

    try:
        result = await crud_trigger.test_trigger(
            db=db,
            test_request=test_request,
        )
        logger.info(f"Tested email trigger {trigger_id} for tenant {tenant_id}: success={result.success}")
        return result
    except Exception as e:
        logger.error(f"Failed to test email trigger {trigger_id}: {e}")
        return TriggerTestResult(
            trigger_id=uuid_pkg.UUID(trigger_id),
            success=False,
            error=str(e),
        )


@router.post("/webhook", response_model=TriggerRead, status_code=201)
async def create_webhook_trigger(
    _request: Request,
    webhook_config: WebhookTriggerBase,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    name: str = Query(..., description="Trigger name"),
    slug: str = Query(..., description="Trigger slug"),
    description: Optional[str] = Query(None, description="Trigger description"),
) -> TriggerRead:
    """
    Create a new webhook trigger.

    Validates URL format and HTTP configuration.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = current_user["tenant_id"]

    # Check if slug already exists for this tenant
    existing = await crud_trigger.get_by_slug(
        db=db,
        slug=slug,
        tenant_id=tenant_id,
    )

    if existing:
        raise DuplicateValueException(f"Trigger with slug '{slug}' already exists")

    # Create the trigger
    trigger_in = TriggerCreate(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        description=description,
        trigger_type="webhook",
        email_config=None,
        webhook_config=webhook_config,
    )

    try:
        trigger = await crud_trigger.create_with_config(
            db=db,
            obj_in=trigger_in,
        )
        logger.info(f"Created webhook trigger {trigger.id} for tenant {tenant_id}")
        return trigger
    except ValidationError as e:
        logger.warning(f"Webhook trigger validation failed: {e}")
        raise BadRequestException(f"Validation failed: {str(e)}")
    except IntegrityError as e:
        logger.warning(f"Webhook trigger integrity constraint violated: {e}")
        raise DuplicateValueException("Trigger with this configuration already exists")
    except Exception as e:
        logger.error(f"Failed to create webhook trigger: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/webhook/{trigger_id}", response_model=TriggerRead)
async def update_webhook_trigger(
    _request: Request,
    trigger_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    name: Optional[str] = Query(None, description="Trigger name"),
    slug: Optional[str] = Query(None, description="Trigger slug"),
    description: Optional[str] = Query(None, description="Trigger description"),
    active: Optional[bool] = Query(None, description="Active status"),
    webhook_config: Optional[WebhookTriggerBase] = None,
) -> TriggerRead:
    """
    Update an existing webhook trigger.

    Only webhook triggers can be updated through this endpoint.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate trigger_id is a valid UUID
    try:
        uuid_pkg.UUID(trigger_id)
    except ValueError:
        raise BadRequestException("Invalid trigger ID format")

    # Get existing trigger to verify it's a webhook trigger
    existing_db_trigger = await crud_trigger.get(
        db=db,
        id=trigger_id,
        tenant_id=tenant_id,
    )
    existing_trigger = TriggerRead.model_validate(existing_db_trigger) if existing_db_trigger else None

    if not existing_trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    if existing_trigger.trigger_type != "webhook":
        raise BadRequestException(f"Trigger {trigger_id} is not a webhook trigger")

    # Check if updating slug to an existing one
    if slug and slug != existing_trigger.slug:
        existing_slug = await crud_trigger.get_by_slug(
            db=db,
            slug=slug,
            tenant_id=tenant_id,
        )
        if existing_slug:
            raise DuplicateValueException(f"Trigger with slug '{slug}' already exists")

    # Update the trigger
    trigger_update = TriggerUpdate(
        name=name,
        slug=slug,
        description=description,
        active=active,
        email_config=None,
        webhook_config=webhook_config,
    )

    trigger = await crud_trigger.update_with_config(
        db=db,
        trigger_id=trigger_id,
        obj_in=trigger_update,
        tenant_id=tenant_id,
    )

    if not trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    logger.info(f"Updated webhook trigger {trigger_id} for tenant {tenant_id}")
    return trigger


@router.post(
    "/webhook/{trigger_id}/test",
    response_model=TriggerTestResult,
    dependencies=[Depends(rate_limiter_dependency)],
)
async def send_test_webhook_trigger(
    _request: Request,
    trigger_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    test_data: dict[str, Any] = Body(default_factory=dict, description="Sample data for test"),
) -> TriggerTestResult:
    """
    Send a test webhook using the trigger configuration.

    Rate limited to prevent abuse.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate trigger_id is a valid UUID
    try:
        uuid_pkg.UUID(trigger_id)
    except ValueError:
        raise BadRequestException("Invalid trigger ID format")

    # Get trigger to verify it exists and is a webhook trigger
    db_trigger = await crud_trigger.get(
        db=db,
        id=trigger_id,
        tenant_id=tenant_id,
    )
    trigger = TriggerRead.model_validate(db_trigger) if db_trigger else None

    if not trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    if trigger.trigger_type != "webhook":
        raise BadRequestException(f"Trigger {trigger_id} is not a webhook trigger")

    # Test the trigger
    test_request = TriggerTestRequest(
        trigger_id=uuid_pkg.UUID(trigger_id),
        test_data=test_data,
    )

    try:
        result = await crud_trigger.test_trigger(
            db=db,
            test_request=test_request,
        )
        logger.info(f"Tested webhook trigger {trigger_id} for tenant {tenant_id}: success={result.success}")
        return result
    except Exception as e:
        logger.error(f"Failed to test webhook trigger {trigger_id}: {e}")
        return TriggerTestResult(
            trigger_id=uuid_pkg.UUID(trigger_id),
            success=False,
            error=str(e),
        )


@router.post("/{trigger_id}/validate", response_model=TriggerValidationResult)
async def validate_trigger(
    _request: Request,
    trigger_id: str,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
    test_connection: bool = Query(True, description="Test the trigger connection/credentials"),
) -> TriggerValidationResult:
    """
    Validate a trigger configuration.

    Checks that the trigger configuration is valid and can be executed.
    """
    # Check if user has a tenant
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    tenant_id = str(current_user["tenant_id"])

    # Validate trigger_id is a valid UUID
    try:
        trigger_uuid = uuid_pkg.UUID(trigger_id)
    except ValueError:
        raise BadRequestException("Invalid trigger ID format")

    # Get trigger to verify it exists
    db_trigger = await crud_trigger.get(
        db=db,
        id=trigger_id,
        tenant_id=tenant_id,
    )
    trigger = TriggerRead.model_validate(db_trigger) if db_trigger else None

    if not trigger:
        raise NotFoundException(f"Trigger {trigger_id} not found")

    # Validate the trigger
    validation_request = TriggerValidationRequest(
        trigger_id=trigger_uuid,
        test_connection=test_connection,
    )

    result = await crud_trigger.validate_trigger(
        db=db,
        validation_request=validation_request,
    )

    logger.info(f"Validated trigger {trigger_id}: valid={result.is_valid}, errors={len(result.errors)}")
    return result
