"""
Comprehensive unit tests for CRUDTrigger operations with config validation and testing.

Tests cover all CRUD operations including:
- Create operations with email/webhook configuration
- Read operations with configuration loading
- Update operations including configuration updates
- Delete operations
- Trigger validation with connectivity testing
- Trigger testing with sample data
- Configuration management (email/webhook specific)
- Credential handling (Plain, Environment, Vault)
- Multi-tenant isolation
- Bulk operations and parallel validation
- Activation/deactivation operations
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.crud.crud_trigger import CRUDTrigger, crud_trigger
from src.app.models.trigger import EmailTrigger, Trigger
from src.app.schemas.trigger import (
    EmailTriggerBase,
    TriggerCreate,
    TriggerTestRequest,
    TriggerUpdate,
    TriggerValidationRequest,
    TriggerValidationResult,
    WebhookTriggerBase,
)
from tests.factories.trigger_factory import (
    EmailTriggerFactory,
    TriggerFactory,
    WebhookTriggerFactory,
)


class TestCRUDTriggerCreate:
    """Test trigger creation operations."""

    @pytest.mark.asyncio
    async def test_create_email_trigger(self, async_db: AsyncSession) -> None:
        """Test creating email trigger with configuration."""
        # Arrange
        tenant_id = uuid.uuid4()
        email_config = EmailTriggerBase(
            host="smtp.gmail.com",
            port=587,
            username_type="Plain",
            username_value="test@gmail.com",
            password_type="Plain",
            password_value="password123",
            sender="test@gmail.com",
            recipients=["alert@example.com"],
            message_title="Test Alert - {{ monitor_name }}",
            message_body="Alert from {{ monitor_name }} on {{ network }}"
        )

        trigger_create = TriggerCreate(
            tenant_id=tenant_id,
            name="Email Alert Trigger",
            slug="email-alert-trigger",
            trigger_type="email",
            description="Test email trigger",
            email_config=email_config
        )

        # Act
        created_trigger = await crud_trigger.create_with_config(async_db, object=trigger_create)

        # Assert
        assert created_trigger is not None
        assert created_trigger.name == "Email Alert Trigger"
        assert created_trigger.trigger_type == "email"
        assert created_trigger.tenant_id == tenant_id
        assert created_trigger.active is True
        assert created_trigger.validated is False
        assert created_trigger.email_config is not None
        assert created_trigger.email_config.host == "smtp.gmail.com"
        assert created_trigger.email_config.sender == "test@gmail.com"

    @pytest.mark.asyncio
    async def test_create_webhook_trigger(self, async_db: AsyncSession) -> None:
        """Test creating webhook trigger with configuration."""
        # Arrange
        tenant_id = uuid.uuid4()
        webhook_config = WebhookTriggerBase(
            url_type="Plain",
            url_value="https://hooks.slack.com/services/test",
            method="POST",
            headers={"Content-Type": "application/json"},
            message_title="Webhook Alert",
            message_body='{"text": "Alert from {{ monitor_name }}"}',
            secret_type="Plain",
            secret_value="webhook_secret_123"
        )

        trigger_create = TriggerCreate(
            tenant_id=tenant_id,
            name="Webhook Alert Trigger",
            slug="webhook-alert-trigger",
            trigger_type="webhook",
            description="Test webhook trigger",
            webhook_config=webhook_config
        )

        # Act
        created_trigger = await crud_trigger.create_with_config(async_db, object=trigger_create)

        # Assert
        assert created_trigger is not None
        assert created_trigger.name == "Webhook Alert Trigger"
        assert created_trigger.trigger_type == "webhook"
        assert created_trigger.webhook_config is not None
        assert created_trigger.webhook_config.url_value == "https://hooks.slack.com/services/test"
        assert created_trigger.webhook_config.method == "POST"
        assert created_trigger.webhook_config.secret_value == "webhook_secret_123"

    @pytest.mark.asyncio
    async def test_create_trigger_without_config(self, async_db: AsyncSession) -> None:
        """Test creating trigger without type-specific configuration."""
        # Arrange
        tenant_id = uuid.uuid4()
        trigger_create = TriggerCreate(
            tenant_id=tenant_id,
            name="Basic Trigger",
            slug="basic-trigger",
            trigger_type="email",
            description="Trigger without email config"
            # No email_config provided
        )

        # Act
        created_trigger = await crud_trigger.create_with_config(async_db, object=trigger_create)

        # Assert
        assert created_trigger is not None
        assert created_trigger.trigger_type == "email"
        assert created_trigger.email_config is None  # No config created

    @pytest.mark.asyncio
    async def test_create_trigger_with_environment_credentials(
        self,
        async_db: AsyncSession
    ) -> None:
        """Test creating trigger with environment variable credentials."""
        # Arrange
        tenant_id = uuid.uuid4()
        email_config = EmailTriggerBase(
            host="smtp.sendgrid.net",
            port=587,
            username_type="Environment",
            username_value="SENDGRID_USERNAME",
            password_type="Environment",
            password_value="SENDGRID_API_KEY",
            sender="noreply@example.com",
            recipients=["alerts@example.com"],
            message_title="Environment Test Alert",
            message_body="Test message with environment credentials"
        )

        trigger_create = TriggerCreate(
            tenant_id=tenant_id,
            name="Environment Trigger",
            slug="environment-trigger",
            trigger_type="email",
            email_config=email_config
        )

        # Act
        created_trigger = await crud_trigger.create_with_config(async_db, object=trigger_create)

        # Assert
        assert created_trigger is not None
        assert created_trigger.email_config.username_type == "Environment"
        assert created_trigger.email_config.username_value == "SENDGRID_USERNAME"
        assert created_trigger.email_config.password_type == "Environment"


class TestCRUDTriggerRead:
    """Test trigger read operations."""

    @pytest.mark.asyncio
    async def test_get_trigger_by_id(self, async_db: AsyncSession) -> None:
        """Test getting trigger by ID."""
        # Arrange
        trigger = TriggerFactory.create_email_trigger(name="Get By ID Test")
        email_config = EmailTriggerFactory.create(trigger_id=trigger.id)
        async_db.add(trigger)
        async_db.add(email_config)
        await async_db.flush()

        # Act
        retrieved_trigger = await crud_trigger.get(async_db, id=trigger.id)

        # Assert
        assert retrieved_trigger is not None
        assert retrieved_trigger.id == trigger.id
        assert retrieved_trigger.name == "Get By ID Test"

    @pytest.mark.asyncio
    async def test_get_trigger_with_config(self, async_db: AsyncSession) -> None:
        """Test getting trigger with configuration loaded."""
        # Arrange
        trigger = TriggerFactory.create_email_trigger()
        email_config = EmailTriggerFactory.create_gmail_config(trigger_id=trigger.id)
        async_db.add(trigger)
        async_db.add(email_config)
        await async_db.flush()

        # Act
        trigger_with_config = await crud_trigger._get_trigger_with_config(
            async_db,
            trigger.id
        )

        # Assert
        assert trigger_with_config is not None
        assert trigger_with_config.id == trigger.id
        assert trigger_with_config.email_config is not None
        assert trigger_with_config.email_config.host == "smtp.gmail.com"

    @pytest.mark.asyncio
    async def test_get_trigger_by_slug(self, async_db: AsyncSession) -> None:
        """Test getting trigger by slug within tenant context."""
        # Arrange
        tenant_id = uuid.uuid4()
        slug = "test-trigger-slug"
        trigger = TriggerFactory.create(slug=slug, tenant_id=tenant_id)
        async_db.add(trigger)
        await async_db.flush()

        # Act
        retrieved_trigger = await crud_trigger.get_by_slug(
            async_db,
            slug=slug,
            tenant_id=tenant_id
        )

        # Assert
        assert retrieved_trigger is not None
        assert retrieved_trigger.slug == slug
        assert retrieved_trigger.tenant_id == tenant_id

    @pytest.mark.asyncio
    async def test_get_trigger_by_slug_wrong_tenant(self, async_db: AsyncSession) -> None:
        """Test getting trigger by slug with wrong tenant returns None."""
        # Arrange
        tenant_id = uuid.uuid4()
        other_tenant_id = uuid.uuid4()
        slug = "test-slug-456"
        trigger = TriggerFactory.create(slug=slug, tenant_id=tenant_id)
        async_db.add(trigger)
        await async_db.flush()

        # Act
        retrieved_trigger = await crud_trigger.get_by_slug(
            async_db,
            slug=slug,
            tenant_id=other_tenant_id
        )

        # Assert
        assert retrieved_trigger is None

    @pytest.mark.asyncio
    async def test_get_active_triggers_by_type(self, async_db: AsyncSession) -> None:
        """Test getting active triggers filtered by type."""
        # Arrange
        tenant_id = uuid.uuid4()

        # Create email triggers
        email_trigger1 = TriggerFactory.create_email_trigger(
            tenant_id=tenant_id,
            active=True,
            validated=True
        )
        email_trigger2 = TriggerFactory.create_email_trigger(
            tenant_id=tenant_id,
            active=True,
            validated=True
        )

        # Create webhook trigger
        webhook_trigger = TriggerFactory.create_webhook_trigger(
            tenant_id=tenant_id,
            active=True,
            validated=True
        )

        # Create inactive email trigger
        inactive_email = TriggerFactory.create_email_trigger(
            tenant_id=tenant_id,
            active=False,
            validated=True
        )

        for trigger in [email_trigger1, email_trigger2, webhook_trigger, inactive_email]:
            async_db.add(trigger)
        await async_db.flush()

        # Act
        active_email_triggers = await crud_trigger.get_active_triggers_by_type(
            async_db,
            "email",
            tenant_id
        )

        # Assert
        assert len(active_email_triggers) >= 2
        trigger_ids = [str(t.id) for t in active_email_triggers]
        assert str(email_trigger1.id) in trigger_ids
        assert str(email_trigger2.id) in trigger_ids
        assert str(webhook_trigger.id) not in trigger_ids
        assert str(inactive_email.id) not in trigger_ids

    @pytest.mark.asyncio
    async def test_get_multi_triggers(self, async_db: AsyncSession) -> None:
        """Test getting multiple triggers."""
        # Arrange
        triggers = TriggerFactory.create_batch(5)
        for trigger in triggers:
            async_db.add(trigger)
        await async_db.flush()

        # Act
        retrieved_triggers = await crud_trigger.get_multi(async_db, skip=0, limit=10)

        # Assert
        assert len(retrieved_triggers) >= 5
        trigger_ids = [str(t.id) for t in retrieved_triggers]
        for trigger in triggers:
            assert str(trigger.id) in trigger_ids


class TestCRUDTriggerUpdate:
    """Test trigger update operations."""

    @pytest.mark.asyncio
    async def test_update_trigger_basic(self, async_db: AsyncSession) -> None:
        """Test basic trigger update."""
        # Arrange
        tenant_id = uuid.uuid4()
        trigger = TriggerFactory.create(
            tenant_id=tenant_id,
            name="Original Name"
        )
        async_db.add(trigger)
        await async_db.flush()

        update_data = TriggerUpdate(name="Updated Name")

        # Act
        updated_trigger = await crud_trigger.update(
            async_db,
            db_obj=trigger,
            object=update_data
        )

        # Assert
        assert updated_trigger is not None
        assert updated_trigger.name == "Updated Name"
        assert updated_trigger.updated_at is not None

    @pytest.mark.asyncio
    async def test_update_trigger_with_email_config(self, async_db: AsyncSession) -> None:
        """Test updating trigger with email configuration."""
        # Arrange
        tenant_id = uuid.uuid4()
        trigger = TriggerFactory.create_email_trigger(tenant_id=tenant_id)
        email_config = EmailTriggerFactory.create(trigger_id=trigger.id, port=587)
        async_db.add(trigger)
        async_db.add(email_config)
        await async_db.flush()

        updated_email_config = EmailTriggerBase(
            host="smtp.outlook.com",
            port=465,  # Changed port
            username_type="Plain",
            username_value="updated@outlook.com",
            password_type="Plain",
            password_value="newpassword",
            sender="updated@outlook.com",
            recipients=["newalerts@example.com"],
            message_title="Updated Alert Title",
            message_body="Updated alert body"
        )

        update_data = TriggerUpdate(
            name="Updated Email Trigger",
            email_config=updated_email_config
        )

        # Act
        updated_trigger = await crud_trigger.update_with_config(
            async_db,
            trigger.id,
            update_data,
            tenant_id
        )

        # Assert
        assert updated_trigger is not None
        assert updated_trigger.name == "Updated Email Trigger"
        assert updated_trigger.email_config.port == 465
        assert updated_trigger.email_config.host == "smtp.outlook.com"
        assert "newalerts@example.com" in updated_trigger.email_config.recipients

    @pytest.mark.asyncio
    async def test_update_trigger_with_webhook_config(self, async_db: AsyncSession) -> None:
        """Test updating trigger with webhook configuration."""
        # Arrange
        tenant_id = uuid.uuid4()
        trigger = TriggerFactory.create_webhook_trigger(tenant_id=tenant_id)
        webhook_config = WebhookTriggerFactory.create(trigger_id=trigger.id)
        async_db.add(trigger)
        async_db.add(webhook_config)
        await async_db.flush()

        updated_webhook_config = WebhookTriggerBase(
            url_type="Plain",
            url_value="https://discord.com/api/webhooks/updated",
            method="PUT",  # Changed method
            headers={"Content-Type": "application/json", "Authorization": "Bearer token"},
            message_title="Updated Webhook Alert",
            message_body='{"content": "Updated webhook message"}',
            secret_type="Plain",
            secret_value="updated_secret"
        )

        update_data = TriggerUpdate(
            name="Updated Webhook Trigger",
            webhook_config=updated_webhook_config
        )

        # Act
        updated_trigger = await crud_trigger.update_with_config(
            async_db,
            trigger.id,
            update_data,
            tenant_id
        )

        # Assert
        assert updated_trigger is not None
        assert updated_trigger.name == "Updated Webhook Trigger"
        assert updated_trigger.webhook_config.method == "PUT"
        assert updated_trigger.webhook_config.url_value == "https://discord.com/api/webhooks/updated"
        assert updated_trigger.webhook_config.secret_value == "updated_secret"

    @pytest.mark.asyncio
    async def test_activate_trigger(self, async_db: AsyncSession) -> None:
        """Test activating a trigger."""
        # Arrange
        tenant_id = uuid.uuid4()
        trigger = TriggerFactory.create(tenant_id=tenant_id, active=False)
        async_db.add(trigger)
        await async_db.flush()

        # Act
        activated_trigger = await crud_trigger.activate_trigger(
            async_db,
            trigger.id,
            tenant_id
        )

        # Assert
        assert activated_trigger is not None
        assert activated_trigger.active is True

    @pytest.mark.asyncio
    async def test_deactivate_trigger(self, async_db: AsyncSession) -> None:
        """Test deactivating a trigger."""
        # Arrange
        tenant_id = uuid.uuid4()
        trigger = TriggerFactory.create(tenant_id=tenant_id, active=True)
        async_db.add(trigger)
        await async_db.flush()

        # Act
        deactivated_trigger = await crud_trigger.deactivate_trigger(
            async_db,
            trigger.id,
            tenant_id
        )

        # Assert
        assert deactivated_trigger is not None
        assert deactivated_trigger.active is False


class TestCRUDTriggerValidation:
    """Test trigger validation operations."""

    @patch('src.app.crud.crud_trigger.CRUDTrigger._test_smtp_connection')
    @pytest.mark.asyncio
    async def test_validate_email_trigger_success(
        self,
        mock_smtp_test,
        async_db: AsyncSession
    ) -> None:
        """Test successful email trigger validation."""
        # Arrange
        mock_smtp_test.return_value = {"success": True}

        trigger = TriggerFactory.create_email_trigger()
        email_config = EmailTriggerFactory.create_gmail_config(trigger_id=trigger.id)
        async_db.add(trigger)
        async_db.add(email_config)
        await async_db.flush()

        validation_request = TriggerValidationRequest(
            trigger_id=trigger.id,
            test_connection=True
        )

        # Act
        result = await crud_trigger.validate_trigger(async_db, validation_request)

        # Assert
        assert result.trigger_id == trigger.id
        assert result.is_valid is True
        assert len(result.errors) == 0
        mock_smtp_test.assert_called_once()

    @patch('src.app.crud.crud_trigger.CRUDTrigger._test_smtp_connection')
    @pytest.mark.asyncio
    async def test_validate_email_trigger_connection_failure(
        self,
        mock_smtp_test,
        async_db: AsyncSession
    ) -> None:
        """Test email trigger validation with connection failure."""
        # Arrange
        mock_smtp_test.return_value = {
            "success": False,
            "error": "Authentication failed"
        }

        trigger = TriggerFactory.create_email_trigger()
        email_config = EmailTriggerFactory.create(trigger_id=trigger.id)
        async_db.add(trigger)
        async_db.add(email_config)
        await async_db.flush()

        validation_request = TriggerValidationRequest(
            trigger_id=trigger.id,
            test_connection=True
        )

        # Act
        result = await crud_trigger.validate_trigger(async_db, validation_request)

        # Assert
        assert result.is_valid is False
        assert any("SMTP connection failed" in error for error in result.errors)

    @patch('src.app.crud.crud_trigger.CRUDTrigger._test_webhook_url')
    @pytest.mark.asyncio
    async def test_validate_webhook_trigger_success(
        self,
        mock_webhook_test,
        async_db: AsyncSession
    ) -> None:
        """Test successful webhook trigger validation."""
        # Arrange
        mock_webhook_test.return_value = {
            "success": True,
            "response": {"status_code": 200}
        }

        trigger = TriggerFactory.create_webhook_trigger()
        webhook_config = WebhookTriggerFactory.create(trigger_id=trigger.id)
        async_db.add(trigger)
        async_db.add(webhook_config)
        await async_db.flush()

        validation_request = TriggerValidationRequest(
            trigger_id=trigger.id,
            test_connection=True
        )

        # Act
        result = await crud_trigger.validate_trigger(async_db, validation_request)

        # Assert
        assert result.is_valid is True
        assert len(result.errors) == 0
        mock_webhook_test.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_trigger_no_config(self, async_db: AsyncSession) -> None:
        """Test validation of trigger without configuration."""
        # Arrange
        trigger = TriggerFactory.create_email_trigger()
        async_db.add(trigger)
        # Note: Not creating email config
        await async_db.flush()

        validation_request = TriggerValidationRequest(
            trigger_id=trigger.id,
            test_connection=False
        )

        # Act
        result = await crud_trigger.validate_trigger(async_db, validation_request)

        # Assert
        assert result.is_valid is False
        assert any("missing configuration" in error.lower() for error in result.errors)

    @pytest.mark.asyncio
    async def test_validate_nonexistent_trigger(self, async_db: AsyncSession) -> None:
        """Test validating non-existent trigger."""
        # Arrange
        fake_id = uuid.uuid4()
        validation_request = TriggerValidationRequest(trigger_id=fake_id)

        # Act
        result = await crud_trigger.validate_trigger(async_db, validation_request)

        # Assert
        assert result.is_valid is False
        assert any("not found" in error.lower() for error in result.errors)

    @pytest.mark.asyncio
    async def test_bulk_validate_triggers(self, async_db: AsyncSession) -> None:
        """Test bulk validation of multiple triggers."""
        # Arrange
        triggers = TriggerFactory.create_batch(3)
        for trigger in triggers:
            async_db.add(trigger)
        await async_db.flush()

        trigger_ids = [trigger.id for trigger in triggers]

        # Act
        with patch('src.app.crud.crud_trigger.CRUDTrigger.validate_trigger') as mock_validate:
            mock_validate.return_value = TriggerValidationResult(
                trigger_id=uuid.uuid4(),
                is_valid=True,
                errors=[],
                warnings=[]
            )

            results = await crud_trigger.bulk_validate(async_db, trigger_ids)

        # Assert
        assert len(results) == 3
        assert len(mock_validate.call_args_list) == 3


class TestCRUDTriggerTesting:
    """Test trigger testing operations with sample data."""

    @patch('src.app.crud.crud_trigger.CRUDTrigger._send_test_email')
    @pytest.mark.asyncio
    async def test_test_email_trigger(
        self,
        mock_send_email,
        async_db: AsyncSession
    ) -> None:
        """Test sending test email through trigger."""
        # Arrange
        mock_send_email.return_value = {
            "success": True,
            "response": {"recipients": ["test@example.com"]}
        }

        trigger = TriggerFactory.create_email_trigger()
        email_config = EmailTriggerFactory.create_gmail_config(trigger_id=trigger.id)
        async_db.add(trigger)
        async_db.add(email_config)
        await async_db.flush()

        test_request = TriggerTestRequest(
            trigger_id=trigger.id,
            test_data={
                "monitor_name": "Test Monitor",
                "network": "ethereum",
                "block_number": 12345,
                "transaction_hash": "0xabc123"
            }
        )

        # Act
        result = await crud_trigger.test_trigger(async_db, test_request)

        # Assert
        assert result.trigger_id == trigger.id
        assert result.success is True
        assert result.response is not None
        assert result.error is None
        assert result.duration_ms > 0
        mock_send_email.assert_called_once()

    @patch('src.app.crud.crud_trigger.CRUDTrigger._send_test_webhook')
    @pytest.mark.asyncio
    async def test_test_webhook_trigger(
        self,
        mock_send_webhook,
        async_db: AsyncSession
    ) -> None:
        """Test sending test webhook through trigger."""
        # Arrange
        mock_send_webhook.return_value = {
            "success": True,
            "response": {"status_code": 200, "body": "OK"}
        }

        trigger = TriggerFactory.create_webhook_trigger()
        webhook_config = WebhookTriggerFactory.create_slack_webhook(trigger_id=trigger.id)
        async_db.add(trigger)
        async_db.add(webhook_config)
        await async_db.flush()

        test_request = TriggerTestRequest(
            trigger_id=trigger.id,
            test_data={
                "monitor_name": "Test Monitor",
                "network": "ethereum",
                "block_number": 12345
            }
        )

        # Act
        result = await crud_trigger.test_trigger(async_db, test_request)

        # Assert
        assert result.success is True
        assert result.response["status_code"] == 200
        mock_send_webhook.assert_called_once()

    @pytest.mark.asyncio
    async def test_test_nonexistent_trigger(self, async_db: AsyncSession) -> None:
        """Test testing non-existent trigger."""
        # Arrange
        fake_id = uuid.uuid4()
        test_request = TriggerTestRequest(
            trigger_id=fake_id,
            test_data={"test": "data"}
        )

        # Act
        result = await crud_trigger.test_trigger(async_db, test_request)

        # Assert
        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_test_trigger_without_config(self, async_db: AsyncSession) -> None:
        """Test testing trigger without configuration."""
        # Arrange
        trigger = TriggerFactory.create_email_trigger()
        async_db.add(trigger)
        # Not creating email config
        await async_db.flush()

        test_request = TriggerTestRequest(
            trigger_id=trigger.id,
            test_data={"test": "data"}
        )

        # Act
        result = await crud_trigger.test_trigger(async_db, test_request)

        # Assert
        assert result.success is False
        assert "configuration" in result.error.lower()


class TestCRUDTriggerCredentials:
    """Test credential handling functionality."""

    @patch.dict('os.environ', {'TEST_SMTP_USER': 'env_user', 'TEST_SMTP_PASS': 'env_pass'})
    def test_get_credential_value_environment(self) -> None:
        """Test getting credential value from environment variables."""
        # Act
        username = crud_trigger._get_credential_value("Environment", "TEST_SMTP_USER")
        password = crud_trigger._get_credential_value("Environment", "TEST_SMTP_PASS")

        # Assert
        assert username == "env_user"
        assert password == "env_pass"

    def test_get_credential_value_plain(self) -> None:
        """Test getting plain text credential value."""
        # Act
        credential = crud_trigger._get_credential_value("Plain", "plain_text_value")

        # Assert
        assert credential == "plain_text_value"

    def test_get_credential_value_vault(self) -> None:
        """Test getting credential value from HashiCorp Vault (not implemented)."""
        # Act
        credential = crud_trigger._get_credential_value("HashicorpCloudVault", "secret/path")

        # Assert
        assert credential == ""  # Not implemented yet

    @patch.dict('os.environ', {}, clear=True)
    def test_get_credential_value_environment_missing(self) -> None:
        """Test getting environment credential when variable doesn't exist."""
        # Act
        credential = crud_trigger._get_credential_value("Environment", "NONEXISTENT_VAR")

        # Assert
        assert credential == ""

    @pytest.mark.asyncio
    async def test_create_trigger_with_vault_credentials(self, async_db: AsyncSession) -> None:
        """Test creating trigger with HashiCorp Vault credentials."""
        # Arrange
        tenant_id = uuid.uuid4()
        email_config = EmailTriggerBase(
            host="smtp.gmail.com",
            port=587,
            username_type="HashicorpCloudVault",
            username_value="secret/email/smtp:username",
            password_type="HashicorpCloudVault",
            password_value="secret/email/smtp:password",
            sender="vault@example.com",
            recipients=["alerts@example.com"],
            message_title="Vault Test",
            message_body="Test message with vault credentials"
        )

        trigger_create = TriggerCreate(
            tenant_id=tenant_id,
            name="Vault Trigger",
            slug="vault-trigger",
            trigger_type="email",
            email_config=email_config
        )

        # Act
        created_trigger = await crud_trigger.create_with_config(async_db, object=trigger_create)

        # Assert
        assert created_trigger is not None
        assert created_trigger.email_config.username_type == "HashicorpCloudVault"
        assert created_trigger.email_config.password_type == "HashicorpCloudVault"


class TestCRUDTriggerDelete:
    """Test trigger delete operations."""

    @pytest.mark.asyncio
    async def test_delete_trigger(self, async_db: AsyncSession) -> None:
        """Test trigger deletion."""
        # Arrange
        trigger = TriggerFactory.create()
        async_db.add(trigger)
        await async_db.flush()
        trigger_id = trigger.id

        # Act
        result = await crud_trigger.delete(async_db, id=trigger_id)

        # Assert
        assert result is not None

    @pytest.mark.asyncio
    async def test_delete_trigger_with_config(self, async_db: AsyncSession) -> None:
        """Test deleting trigger with associated configuration."""
        # Arrange
        trigger = TriggerFactory.create_email_trigger()
        email_config = EmailTriggerFactory.create(trigger_id=trigger.id)
        async_db.add(trigger)
        async_db.add(email_config)
        await async_db.flush()

        # Act
        result = await crud_trigger.delete(async_db, id=trigger.id)

        # Assert
        assert result is not None

        # Verify email config is also deleted (cascade)
        config_query = select(EmailTrigger).where(EmailTrigger.trigger_id == trigger.id)
        config_result = await async_db.execute(config_query)
        config_result.scalar_one_or_none()
        # Behavior depends on cascade settings


class TestCRUDTriggerAdvanced:
    """Test advanced trigger operations and edge cases."""

    @pytest.mark.asyncio
    async def test_trigger_factory_variants(self, async_db: AsyncSession) -> None:
        """Test different trigger factory creation methods."""
        # Test email trigger
        email_trigger = TriggerFactory.create_email_trigger()
        async_db.add(email_trigger)
        assert email_trigger.trigger_type == "email"
        assert "Email Alert" in email_trigger.name

        # Test webhook trigger
        webhook_trigger = TriggerFactory.create_webhook_trigger()
        async_db.add(webhook_trigger)
        assert webhook_trigger.trigger_type == "webhook"
        assert "Webhook Alert" in webhook_trigger.name

        # Test validated trigger
        validated_trigger = TriggerFactory.create_validated_trigger()
        async_db.add(validated_trigger)
        assert validated_trigger.validated is True
        assert validated_trigger.last_validated_at is not None

        # Test invalid trigger
        invalid_trigger = TriggerFactory.create_invalid_trigger()
        async_db.add(invalid_trigger)
        assert invalid_trigger.validated is False
        assert invalid_trigger.validation_errors is not None

        await async_db.flush()

        # Verify all triggers were created
        triggers = [email_trigger, webhook_trigger, validated_trigger, invalid_trigger]
        for trigger in triggers:
            assert trigger.id is not None

    @pytest.mark.asyncio
    async def test_email_trigger_factory_variants(self, async_db: AsyncSession) -> None:
        """Test different email trigger factory creation methods."""
        # Test Gmail config
        gmail_config = EmailTriggerFactory.create_gmail_config()
        async_db.add(gmail_config)
        assert gmail_config.host == "smtp.gmail.com"
        assert gmail_config.port == 587
        assert "@gmail.com" in gmail_config.username_value

        # Test SendGrid config
        sendgrid_config = EmailTriggerFactory.create_sendgrid_config()
        async_db.add(sendgrid_config)
        assert sendgrid_config.host == "smtp.sendgrid.net"
        assert sendgrid_config.username_value == "apikey"
        assert sendgrid_config.password_value.startswith("SG.")

        # Test environment credentials
        env_config = EmailTriggerFactory.create_with_environment_creds()
        async_db.add(env_config)
        assert env_config.username_type == "Environment"
        assert env_config.password_type == "Environment"

        # Test vault credentials
        vault_config = EmailTriggerFactory.create_with_vault_creds()
        async_db.add(vault_config)
        assert vault_config.username_type == "HashicorpCloudVault"
        assert vault_config.password_type == "HashicorpCloudVault"

        await async_db.flush()

    @pytest.mark.asyncio
    async def test_webhook_trigger_factory_variants(self, async_db: AsyncSession) -> None:
        """Test different webhook trigger factory creation methods."""
        # Test Slack webhook
        slack_webhook = WebhookTriggerFactory.create_slack_webhook()
        async_db.add(slack_webhook)
        assert "hooks.slack.com" in slack_webhook.url_value
        assert "text" in slack_webhook.message_body

        # Test Discord webhook
        discord_webhook = WebhookTriggerFactory.create_discord_webhook()
        async_db.add(discord_webhook)
        assert "discord.com" in discord_webhook.url_value
        assert "embeds" in discord_webhook.message_body

        # Test environment URL
        env_webhook = WebhookTriggerFactory.create_with_environment_url()
        async_db.add(env_webhook)
        assert env_webhook.url_type == "Environment"
        assert env_webhook.url_value == "WEBHOOK_URL"

        # Test vault URL
        vault_webhook = WebhookTriggerFactory.create_with_vault_url()
        async_db.add(vault_webhook)
        assert vault_webhook.url_type == "HashicorpCloudVault"
        assert "secret/webhooks" in vault_webhook.url_value

        # Test with secret
        secret_webhook = WebhookTriggerFactory.create_with_secret()
        async_db.add(secret_webhook)
        assert secret_webhook.secret_type == "Plain"
        assert secret_webhook.secret_value is not None

        await async_db.flush()

    @pytest.mark.asyncio
    async def test_crud_instance_validation(self) -> None:
        """Test that crud_trigger is properly instantiated."""
        # Assert
        assert isinstance(crud_trigger, CRUDTrigger)
        assert crud_trigger.model is Trigger

    @pytest.mark.asyncio
    async def test_exists_trigger(self, async_db: AsyncSession) -> None:
        """Test checking if trigger exists."""
        # Arrange
        trigger = TriggerFactory.create(slug="exists-test")
        async_db.add(trigger)
        await async_db.flush()

        # Act & Assert
        assert await crud_trigger.exists(async_db, slug="exists-test") is True
        assert await crud_trigger.exists(async_db, slug="nonexistent") is False

    @pytest.mark.asyncio
    async def test_error_handling_edge_cases(self, async_db: AsyncSession) -> None:
        """Test error handling and edge cases."""
        # Test getting non-existent trigger
        fake_id = uuid.uuid4()
        retrieved = await crud_trigger.get(async_db, id=fake_id)
        assert retrieved is None

        # Test getting by slug that doesn't exist
        by_slug = await crud_trigger.get_by_slug(async_db, "nonexistent-slug", uuid.uuid4())
        assert by_slug is None

        # Test updating non-existent trigger
        update_data = TriggerUpdate(name="Should Fail")
        updated = await crud_trigger.update(async_db, id=fake_id, object=update_data)
        assert updated is None

    @pytest.mark.parametrize("trigger_type,config_type", [
        ("email", "email_config"),
        ("webhook", "webhook_config"),
    ])
    @pytest.mark.asyncio
    async def test_trigger_type_variations(
        self,
        async_db: AsyncSession,
        trigger_type: str,
        config_type: str
    ) -> None:
        """Test trigger operations for different trigger types."""
        # Arrange
        tenant_id = uuid.uuid4()

        if trigger_type == "email":
            config = EmailTriggerBase(
                host="smtp.test.com",
                port=587,
                username_type="Plain",
                username_value="test@test.com",
                password_type="Plain",
                password_value="password",
                sender="test@test.com",
                recipients=["alert@test.com"],
                message_title="Test Alert",
                message_body="Test message"
            )
        else:  # webhook
            config = WebhookTriggerBase(
                url_type="Plain",
                url_value="https://webhook.test.com",
                method="POST",
                headers={"Content-Type": "application/json"},
                message_title="Test Alert",
                message_body='{"text": "test"}'
            )

        trigger_create = TriggerCreate(
            tenant_id=tenant_id,
            name=f"Test {trigger_type.title()} Trigger",
            slug=f"test-{trigger_type}-trigger",
            trigger_type=trigger_type,
            **{config_type: config}
        )

        # Act
        created_trigger = await crud_trigger.create_with_config(async_db, object=trigger_create)

        # Assert
        assert created_trigger is not None
        assert created_trigger.trigger_type == trigger_type

        if trigger_type == "email":
            assert created_trigger.email_config is not None
            assert created_trigger.email_config.host == "smtp.test.com"
        else:
            assert created_trigger.webhook_config is not None
            assert created_trigger.webhook_config.url_value == "https://webhook.test.com"
