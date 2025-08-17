"""
Comprehensive tests for trigger API endpoints.
Tests all CRUD operations, type-specific endpoints, and test/validation endpoints.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.app.api.v1.triggers import (
    create_email_trigger,
    create_webhook_trigger,
    delete_trigger,
    disable_trigger,
    enable_trigger,
    get_trigger,
    list_triggers,
    send_test_email_trigger,
    send_test_webhook_trigger,
    update_email_trigger,
    update_webhook_trigger,
    validate_trigger,
)
from src.app.core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
)
from src.app.schemas.trigger import (
    EmailTriggerBase,
    EmailTriggerRead,
    TriggerRead,
    TriggerTestResult,
    TriggerValidationResult,
    WebhookTriggerBase,
    WebhookTriggerRead,
)


@pytest.fixture
def sample_tenant_id():
    """Generate a sample tenant ID."""
    return uuid.uuid4()


@pytest.fixture
def sample_trigger_id():
    """Generate a sample trigger ID."""
    return str(uuid.uuid4())


@pytest.fixture
def current_user_with_tenant(sample_tenant_id):
    """Mock current user with tenant association."""
    return {
        "id": 1,
        "username": "test_user",
        "email": "test@example.com",
        "tenant_id": sample_tenant_id,
        "is_superuser": False,
    }


@pytest.fixture
def current_user_without_tenant():
    """Mock current user without tenant association."""
    return {
        "id": 2,
        "username": "no_tenant_user",
        "email": "no_tenant@example.com",
        "tenant_id": None,
        "is_superuser": False,
    }


@pytest.fixture
def sample_email_config():
    """Generate sample email trigger configuration."""
    return EmailTriggerBase(
        host="smtp.gmail.com",
        port=587,
        username_type="Plain",
        username_value="test@example.com",
        password_type="Environment",
        password_value="SMTP_PASSWORD",
        sender="noreply@example.com",
        recipients=["user1@example.com", "user2@example.com"],
        message_title="Test Alert: {{event_name}}",
        message_body="Alert triggered at {{timestamp}}",
    )


@pytest.fixture
def sample_webhook_config():
    """Generate sample webhook trigger configuration."""
    return WebhookTriggerBase(
        url_type="Plain",
        url_value="https://webhook.site/test",
        method="POST",
        headers={"Content-Type": "application/json"},
        secret_type="Environment",
        secret_value="WEBHOOK_SECRET",
        message_title="Test Alert",
        message_body="{{event_data}}",
    )


@pytest.fixture
def sample_email_trigger_read(sample_trigger_id, sample_tenant_id):
    """Generate sample email trigger read data."""
    return TriggerRead(
        id=uuid.UUID(sample_trigger_id),
        tenant_id=sample_tenant_id,
        name="Test Email Trigger",
        slug="test-email-trigger",
        trigger_type="email",
        description="Test email trigger description",
        active=True,
        validated=True,
        validation_errors=None,
        last_validated_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        email_config=EmailTriggerRead(
            trigger_id=uuid.UUID(sample_trigger_id),
            host="smtp.gmail.com",
            port=587,
            username_type="Plain",
            username_value="test@example.com",
            password_type="Environment",
            password_value="SMTP_PASSWORD",
            sender="noreply@example.com",
            recipients=["user1@example.com"],
            message_title="Alert",
            message_body="Alert body",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
        webhook_config=None,
    )


@pytest.fixture
def sample_webhook_trigger_read(sample_trigger_id, sample_tenant_id):
    """Generate sample webhook trigger read data."""
    return TriggerRead(
        id=uuid.UUID(sample_trigger_id),
        tenant_id=sample_tenant_id,
        name="Test Webhook Trigger",
        slug="test-webhook-trigger",
        trigger_type="webhook",
        description="Test webhook trigger description",
        active=True,
        validated=True,
        validation_errors=None,
        last_validated_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        email_config=None,
        webhook_config=WebhookTriggerRead(
            trigger_id=uuid.UUID(sample_trigger_id),
            url_type="Plain",
            url_value="https://webhook.site/test",
            method="POST",
            headers={"Content-Type": "application/json"},
            secret_type=None,
            secret_value=None,
            message_title="Alert",
            message_body="Alert body",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
    )


@pytest.fixture
def mock_trigger_service():
    """Mock trigger service."""
    with patch("src.app.api.v1.triggers.trigger_service") as mock_service:
        yield mock_service


class TestListTriggers:
    """Test GET /triggers endpoint."""

    @pytest.mark.asyncio
    async def test_list_triggers_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_email_trigger_read,
        sample_webhook_trigger_read,
        mock_trigger_service,
    ):
        """Test successful trigger listing with pagination."""
        # Mock service response
        mock_trigger_service.get_multi = AsyncMock(
            return_value={
                "items": [sample_email_trigger_read, sample_webhook_trigger_read],
                "total": 2,
                "page": 1,
                "size": 50,
                "pages": 1,
            }
        )

        result = await list_triggers(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            page=1,
            size=50,
            name=None,
            slug=None,
            trigger_type=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["total"] == 2
        assert len(result["items"]) == 2
        assert result["items"][0] == sample_email_trigger_read
        assert result["items"][1] == sample_webhook_trigger_read
        mock_trigger_service.get_multi.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_triggers_with_type_filter(
        self,
        mock_db,
        current_user_with_tenant,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test trigger listing filtered by type."""
        mock_trigger_service.get_multi = AsyncMock(
            return_value={
                "items": [sample_email_trigger_read],
                "total": 1,
                "page": 1,
                "size": 50,
                "pages": 1,
            }
        )

        result = await list_triggers(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            page=1,
            size=50,
            name=None,
            slug=None,
            trigger_type="email",
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["total"] == 1
        assert result["items"][0].trigger_type == "email"

        # Verify filter was constructed correctly
        call_args = mock_trigger_service.get_multi.call_args
        filters = call_args.kwargs["filters"]
        assert filters.trigger_type == "email"

    @pytest.mark.asyncio
    async def test_list_triggers_no_tenant(
        self,
        mock_db,
        current_user_without_tenant,
    ):
        """Test trigger listing without tenant association."""
        with pytest.raises(ForbiddenException, match="User is not associated with any tenant"):
            await list_triggers(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_without_tenant,
                page=1,
                size=50,
                name=None,
                slug=None,
                trigger_type=None,
                active=None,
                validated=None,
                sort_field="created_at",
                sort_order="desc",
            )


class TestGetTrigger:
    """Test GET /triggers/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test successful single trigger retrieval."""
        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_email_trigger_read)

        result = await get_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
        )

        assert result == sample_email_trigger_read
        mock_trigger_service.get_trigger_by_id.assert_called_once_with(
            db=mock_db,
            trigger_id=sample_trigger_id,
            tenant_id=str(current_user_with_tenant["tenant_id"]),
        )

    @pytest.mark.asyncio
    async def test_get_trigger_invalid_id(
        self,
        mock_db,
        current_user_with_tenant,
    ):
        """Test trigger retrieval with invalid UUID."""
        with pytest.raises(BadRequestException, match="Invalid trigger ID format"):
            await get_trigger(
                _request=Mock(),
                trigger_id="invalid-uuid",
                db=mock_db,
                current_user=current_user_with_tenant,
            )

    @pytest.mark.asyncio
    async def test_get_trigger_not_found(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        mock_trigger_service,
    ):
        """Test trigger retrieval when trigger doesn't exist."""
        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match=f"Trigger {sample_trigger_id} not found"):
            await get_trigger(
                _request=Mock(),
                trigger_id=sample_trigger_id,
                db=mock_db,
                current_user=current_user_with_tenant,
            )


class TestCreateEmailTrigger:
    """Test POST /triggers/email endpoint."""

    @pytest.mark.asyncio
    async def test_create_email_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_email_config,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test successful email trigger creation."""
        mock_trigger_service.get_trigger_by_slug = AsyncMock(return_value=None)
        mock_trigger_service.create_trigger = AsyncMock(return_value=sample_email_trigger_read)

        result = await create_email_trigger(
            _request=Mock(),
            email_config=sample_email_config,
            db=mock_db,
            current_user=current_user_with_tenant,
            name="Test Email Trigger",
            slug="test-email-trigger",
            description="Test description",
        )

        assert result == sample_email_trigger_read
        mock_trigger_service.create_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_email_trigger_duplicate_slug(
        self,
        mock_db,
        current_user_with_tenant,
        sample_email_config,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test email trigger creation with duplicate slug."""
        mock_trigger_service.get_trigger_by_slug = AsyncMock(return_value=sample_email_trigger_read)

        with pytest.raises(
            DuplicateValueException,
            match="Trigger with slug 'test-email-trigger' already exists",
        ):
            await create_email_trigger(
                _request=Mock(),
                email_config=sample_email_config,
                db=mock_db,
                current_user=current_user_with_tenant,
                name="Test Email Trigger",
                slug="test-email-trigger",
                description="Test description",
            )

    @pytest.mark.asyncio
    async def test_create_email_trigger_invalid_email(
        self,
        mock_db,
        current_user_with_tenant,
        mock_trigger_service,
    ):
        """Test email trigger creation with invalid email addresses."""
        invalid_email_config = EmailTriggerBase(
            host="smtp.gmail.com",
            port=587,
            username_type="Plain",
            username_value="test@example.com",
            password_type="Environment",
            password_value="SMTP_PASSWORD",
            sender="invalid-email",  # Invalid email
            recipients=["user1@example.com"],
            message_title="Test",
            message_body="Test",
        )

        mock_trigger_service.get_trigger_by_slug = AsyncMock(return_value=None)
        mock_trigger_service.create_trigger = AsyncMock(
            side_effect=ValueError("Invalid email address")
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_email_trigger(
                _request=Mock(),
                email_config=invalid_email_config,
                db=mock_db,
                current_user=current_user_with_tenant,
                name="Test",
                slug="test",
                description="Test",
            )

        assert exc_info.value.status_code == 500


class TestCreateWebhookTrigger:
    """Test POST /triggers/webhook endpoint."""

    @pytest.mark.asyncio
    async def test_create_webhook_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_webhook_config,
        sample_webhook_trigger_read,
        mock_trigger_service,
    ):
        """Test successful webhook trigger creation."""
        mock_trigger_service.get_trigger_by_slug = AsyncMock(return_value=None)
        mock_trigger_service.create_trigger = AsyncMock(return_value=sample_webhook_trigger_read)

        result = await create_webhook_trigger(
            _request=Mock(),
            webhook_config=sample_webhook_config,
            db=mock_db,
            current_user=current_user_with_tenant,
            name="Test Webhook Trigger",
            slug="test-webhook-trigger",
            description="Test description",
        )

        assert result == sample_webhook_trigger_read
        mock_trigger_service.create_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_webhook_trigger_invalid_method(
        self,
        mock_db,
        current_user_with_tenant,
        mock_trigger_service,
    ):
        """Test webhook trigger creation with invalid HTTP method."""
        # This should raise validation error from pydantic
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):  # Will be pydantic validation error
            invalid_webhook_config = WebhookTriggerBase(
                url_type="Plain",
                url_value="https://webhook.site/test",
                method="INVALID",  # Invalid method
                headers={},
                secret_type=None,
                secret_value=None,
                message_title="Test",
                message_body="Test",
            )


class TestUpdateEmailTrigger:
    """Test PUT /triggers/email/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_email_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        sample_email_config,
        mock_trigger_service,
    ):
        """Test successful email trigger update."""
        updated_trigger = sample_email_trigger_read.model_copy()
        updated_trigger.name = "Updated Email Trigger"

        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_email_trigger_read)
        mock_trigger_service.get_trigger_by_slug = AsyncMock(return_value=None)
        mock_trigger_service.update_trigger = AsyncMock(return_value=updated_trigger)

        result = await update_email_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            name="Updated Email Trigger",
            slug=None,
            description=None,
            active=None,
            email_config=sample_email_config,
        )

        assert result.name == "Updated Email Trigger"
        mock_trigger_service.update_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_email_trigger_wrong_type(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_webhook_trigger_read,
        mock_trigger_service,
    ):
        """Test updating a non-email trigger through email endpoint."""
        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_webhook_trigger_read)

        with pytest.raises(
            BadRequestException,
            match=f"Trigger {sample_trigger_id} is not an email trigger",
        ):
            await update_email_trigger(
                _request=Mock(),
                trigger_id=sample_trigger_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                name="Updated",
                slug=None,
                description=None,
                active=None,
                email_config=None,
            )


class TestUpdateWebhookTrigger:
    """Test PUT /triggers/webhook/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_webhook_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_webhook_trigger_read,
        sample_webhook_config,
        mock_trigger_service,
    ):
        """Test successful webhook trigger update."""
        updated_trigger = sample_webhook_trigger_read.model_copy()
        updated_trigger.name = "Updated Webhook Trigger"

        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_webhook_trigger_read)
        mock_trigger_service.get_trigger_by_slug = AsyncMock(return_value=None)
        mock_trigger_service.update_trigger = AsyncMock(return_value=updated_trigger)

        result = await update_webhook_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            name="Updated Webhook Trigger",
            slug=None,
            description=None,
            active=None,
            webhook_config=sample_webhook_config,
        )

        assert result.name == "Updated Webhook Trigger"
        mock_trigger_service.update_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_webhook_trigger_wrong_type(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test updating a non-webhook trigger through webhook endpoint."""
        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_email_trigger_read)

        with pytest.raises(
            BadRequestException,
            match=f"Trigger {sample_trigger_id} is not a webhook trigger",
        ):
            await update_webhook_trigger(
                _request=Mock(),
                trigger_id=sample_trigger_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                name="Updated",
                slug=None,
                description=None,
                active=None,
                webhook_config=None,
            )


class TestDeleteTrigger:
    """Test DELETE /triggers/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_trigger_soft_delete(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        mock_trigger_service,
    ):
        """Test soft delete of trigger."""
        mock_trigger_service.delete_trigger = AsyncMock(return_value=True)

        await delete_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            hard_delete=False,
        )

        mock_trigger_service.delete_trigger.assert_called_once_with(
            db=mock_db,
            trigger_id=sample_trigger_id,
            tenant_id=str(current_user_with_tenant["tenant_id"]),
            is_hard_delete=False,
        )

    @pytest.mark.asyncio
    async def test_delete_trigger_hard_delete(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        mock_trigger_service,
    ):
        """Test hard delete of trigger."""
        mock_trigger_service.delete_trigger = AsyncMock(return_value=True)

        await delete_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            hard_delete=True,
        )

        mock_trigger_service.delete_trigger.assert_called_once_with(
            db=mock_db,
            trigger_id=sample_trigger_id,
            tenant_id=str(current_user_with_tenant["tenant_id"]),
            is_hard_delete=True,
        )

    @pytest.mark.asyncio
    async def test_delete_trigger_not_found(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        mock_trigger_service,
    ):
        """Test delete when trigger doesn't exist."""
        mock_trigger_service.delete_trigger = AsyncMock(return_value=False)

        with pytest.raises(NotFoundException, match=f"Trigger {sample_trigger_id} not found"):
            await delete_trigger(
                _request=Mock(),
                trigger_id=sample_trigger_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                hard_delete=False,
            )


class TestEnableDisableTrigger:
    """Test PUT /triggers/{id}/enable and /disable endpoints."""

    @pytest.mark.asyncio
    async def test_enable_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test successful trigger enable."""
        enabled_trigger = sample_email_trigger_read.model_copy()
        enabled_trigger.active = True

        mock_trigger_service.update_trigger = AsyncMock(return_value=enabled_trigger)

        result = await enable_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
        )

        assert result.active is True

        # Verify correct update was called
        call_args = mock_trigger_service.update_trigger.call_args
        assert call_args.kwargs["trigger_in"].active is True

    @pytest.mark.asyncio
    async def test_disable_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test successful trigger disable."""
        disabled_trigger = sample_email_trigger_read.model_copy()
        disabled_trigger.active = False

        mock_trigger_service.update_trigger = AsyncMock(return_value=disabled_trigger)

        result = await disable_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
        )

        assert result.active is False

        # Verify correct update was called
        call_args = mock_trigger_service.update_trigger.call_args
        assert call_args.kwargs["trigger_in"].active is False


class TestEmailTriggerTest:
    """Test POST /triggers/email/{id}/test endpoint."""

    @pytest.mark.asyncio
    async def test_test_email_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test successful email trigger test."""
        test_result = TriggerTestResult(
            trigger_id=uuid.UUID(sample_trigger_id),
            success=True,
            response={"message": "Email sent successfully"},
            error=None,
            duration_ms=150,
        )

        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_email_trigger_read)
        mock_trigger_service.test_trigger = AsyncMock(return_value=test_result)

        result = await send_test_email_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            test_data={"event": "test"},
        )

        assert result.success is True
        assert result.trigger_id == uuid.UUID(sample_trigger_id)
        mock_trigger_service.test_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_email_trigger_wrong_type(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_webhook_trigger_read,
        mock_trigger_service,
    ):
        """Test testing a non-email trigger through email test endpoint."""
        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_webhook_trigger_read)

        with pytest.raises(
            BadRequestException,
            match=f"Trigger {sample_trigger_id} is not an email trigger",
        ):
            await send_test_email_trigger(
                _request=Mock(),
                trigger_id=sample_trigger_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                test_data={},
            )

    @pytest.mark.asyncio
    async def test_test_email_trigger_failure(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test email trigger test failure."""
        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_email_trigger_read)
        mock_trigger_service.test_trigger = AsyncMock(side_effect=Exception("SMTP connection failed"))

        result = await send_test_email_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            test_data={},
        )

        assert result.success is False
        assert "SMTP connection failed" in result.error


class TestWebhookTriggerTest:
    """Test POST /triggers/webhook/{id}/test endpoint."""

    @pytest.mark.asyncio
    async def test_test_webhook_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_webhook_trigger_read,
        mock_trigger_service,
    ):
        """Test successful webhook trigger test."""
        test_result = TriggerTestResult(
            trigger_id=uuid.UUID(sample_trigger_id),
            success=True,
            response={"status_code": 200, "body": "OK"},
            error=None,
            duration_ms=75,
        )

        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_webhook_trigger_read)
        mock_trigger_service.test_trigger = AsyncMock(return_value=test_result)

        result = await send_test_webhook_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            test_data={"event": "test"},
        )

        assert result.success is True
        assert result.trigger_id == uuid.UUID(sample_trigger_id)
        mock_trigger_service.test_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_webhook_trigger_wrong_type(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test testing a non-webhook trigger through webhook test endpoint."""
        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_email_trigger_read)

        with pytest.raises(
            BadRequestException,
            match=f"Trigger {sample_trigger_id} is not a webhook trigger",
        ):
            await send_test_webhook_trigger(
                _request=Mock(),
                trigger_id=sample_trigger_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                test_data={},
            )


class TestValidateTrigger:
    """Test POST /triggers/{id}/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_trigger_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test successful trigger validation."""
        validation_result = TriggerValidationResult(
            trigger_id=uuid.UUID(sample_trigger_id),
            is_valid=True,
            errors=[],
            warnings=[],
        )

        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_email_trigger_read)
        mock_trigger_service.validate_trigger = AsyncMock(return_value=validation_result)

        result = await validate_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            test_connection=True,
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        mock_trigger_service.validate_trigger.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_trigger_with_errors(
        self,
        mock_db,
        current_user_with_tenant,
        sample_trigger_id,
        sample_email_trigger_read,
        mock_trigger_service,
    ):
        """Test trigger validation with errors."""
        validation_result = TriggerValidationResult(
            trigger_id=uuid.UUID(sample_trigger_id),
            is_valid=False,
            errors=["Invalid SMTP credentials", "Cannot connect to server"],
            warnings=["Recipients list is empty"],
        )

        mock_trigger_service.get_trigger_by_id = AsyncMock(return_value=sample_email_trigger_read)
        mock_trigger_service.validate_trigger = AsyncMock(return_value=validation_result)

        result = await validate_trigger(
            _request=Mock(),
            trigger_id=sample_trigger_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            test_connection=True,
        )

        assert result.is_valid is False
        assert len(result.errors) == 2
        assert len(result.warnings) == 1


class TestTriggerEndpointEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_invalid_uuid_format(
        self,
        mock_db,
        current_user_with_tenant,
    ):
        """Test various endpoints with invalid UUID format."""
        invalid_id = "not-a-uuid"

        # Test get
        with pytest.raises(BadRequestException, match="Invalid trigger ID format"):
            await get_trigger(
                _request=Mock(),
                trigger_id=invalid_id,
                db=mock_db,
                current_user=current_user_with_tenant,
            )

        # Test delete
        with pytest.raises(BadRequestException, match="Invalid trigger ID format"):
            await delete_trigger(
                _request=Mock(),
                trigger_id=invalid_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                hard_delete=False,
            )

        # Test enable
        with pytest.raises(BadRequestException, match="Invalid trigger ID format"):
            await enable_trigger(
                _request=Mock(),
                trigger_id=invalid_id,
                db=mock_db,
                current_user=current_user_with_tenant,
            )

    @pytest.mark.asyncio
    async def test_pagination_boundaries(
        self,
        mock_db,
        current_user_with_tenant,
        mock_trigger_service,
    ):
        """Test pagination with edge cases."""
        # Test with very large page number
        mock_trigger_service.get_multi = AsyncMock(
            return_value={"items": [], "total": 10, "page": 1000, "size": 50, "pages": 1}
        )

        result = await list_triggers(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            page=1000,
            size=50,
            name=None,
            slug=None,
            trigger_type=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["items"] == []
        assert result["page"] == 1000
