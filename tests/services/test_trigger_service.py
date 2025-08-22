"""
Comprehensive unit tests for TriggerService class.
Tests validation, testing, activation/deactivation, and trigger lifecycle.
"""

import json
import uuid
from datetime import UTC
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.schemas.trigger import (
    EmailTriggerBase,
    TriggerRead,
    TriggerTestRequest,
    TriggerTestResult,
    TriggerUpdate,
    TriggerValidationRequest,
    TriggerValidationResult,
)
from src.app.services.trigger_service import TriggerService


class TestTriggerService:
    """Test suite for TriggerService."""

    @pytest.fixture
    def mock_crud_trigger(self):
        """Mock trigger CRUD operations."""
        mock = Mock()
        mock.create = AsyncMock()
        mock.get = AsyncMock()
        mock.update = AsyncMock()
        mock.delete = AsyncMock()
        mock.get_paginated = AsyncMock()
        mock.get_multi = AsyncMock()
        mock.get_by_slug = AsyncMock()
        mock.create_with_config = AsyncMock()
        mock.update_with_config = AsyncMock()
        mock._get_trigger_with_config = AsyncMock()
        mock.validate_trigger = AsyncMock()
        mock.test_trigger = AsyncMock()
        mock.activate_trigger = AsyncMock()
        mock.deactivate_trigger = AsyncMock()
        mock.get_active_triggers_by_type = AsyncMock()
        return mock

    @pytest.fixture
    def trigger_service(self, mock_crud_trigger):
        """Create trigger service instance."""
        return TriggerService(mock_crud_trigger)

    @pytest.fixture
    def sample_trigger_create(self):
        """Sample trigger creation data."""
        # Note: tenant_id is added by the service, not included here
        class MockTriggerCreate:
            def __init__(self):
                self.name = "Email Alert"
                self.slug = "email-alert"
                self.trigger_type = "email"
                self.description = "Test email trigger"
                self.email_config = EmailTriggerBase(
                    host="smtp.example.com",
                    port=465,
                    username_type="Plain",
                    username_value="user@example.com",
                    password_type="Plain",
                    password_value="password123",
                    sender="alerts@example.com",
                    recipients=["admin@example.com"],
                    message_title="Alert: {{monitor_name}}",
                    message_body="Monitor {{monitor_name}} triggered at {{timestamp}}"
                )
                self.webhook_config = None
                self.tenant_id = None  # Will be set in test

            def model_dump(self):
                result = {
                    "name": self.name,
                    "slug": self.slug,
                    "trigger_type": self.trigger_type,
                    "description": self.description,
                    "email_config": self.email_config,
                    "webhook_config": self.webhook_config
                }
                # Only include tenant_id if it's been set
                if self.tenant_id:
                    result["tenant_id"] = self.tenant_id
                return result

        return MockTriggerCreate()

    @pytest.fixture
    def sample_trigger_db(self):
        """Sample trigger database entity."""
        from datetime import datetime

        # Create a simple object with attributes instead of using TriggerRead directly
        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        return MockDBObject(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name="Email Alert",
            slug="email-alert",
            trigger_type="email",
            description="Test email trigger",
            active=True,
            validated=False,
            validation_errors=None,
            last_validated_at=None,
            created_at=now,
            updated_at=now,
            email_config=MockDBObject(
                trigger_id=uuid.uuid4(),
                host="smtp.example.com",
                port=465,
                username_type="Plain",
                username_value="user@example.com",
                password_type="Plain",
                password_value="password123",
                sender="alerts@example.com",
                recipients=["admin@example.com"],
                message_title="Alert: {{monitor_name}}",
                message_body="Monitor {{monitor_name}} triggered at {{timestamp}}",
                created_at=now,
                updated_at=now
            ),
            webhook_config=None
        )

    @pytest.fixture
    def sample_trigger_update(self):
        """Sample trigger update data."""
        return TriggerUpdate(
            name="Updated Email Alert",
            slug="updated-email-alert",
            description="Updated trigger description",
            active=False,
            email_config=EmailTriggerBase(
                host="smtp.updated.com",
                port=587,
                username_type="Plain",
                username_value="updated@example.com",
                password_type="Plain",
                password_value="newpass123",
                sender="updated-alerts@example.com",
                recipients=["updated@example.com"],
                message_title="Updated Alert: {{monitor_name}}",
                message_body="Updated monitor alert body"
            )
        )

    @pytest.mark.asyncio
    async def test_create_trigger_success(
        self,
        trigger_service,
        sample_trigger_create,
        sample_trigger_db,
        mock_db
    ):
        """Test successful trigger creation with caching."""
        tenant_id = uuid.uuid4()

        # Don't set tenant_id on sample_trigger_create since service adds it

        # Mock CRUD create_with_config
        trigger_service.crud_trigger.create_with_config.return_value = sample_trigger_db

        with patch.object(trigger_service, "_cache_trigger") as mock_cache:
            result = await trigger_service.create_trigger(
                mock_db,
                sample_trigger_create,
                tenant_id
            )

            # Verify CRUD create_with_config was called
            trigger_service.crud_trigger.create_with_config.assert_called_once_with(
                db=mock_db,
                obj_in=sample_trigger_create
            )

            # Verify caching
            mock_cache.assert_called_once_with(sample_trigger_db, str(tenant_id))

            # Verify result
            assert isinstance(result, TriggerRead)
            assert result.name == sample_trigger_create.name

    @pytest.mark.asyncio
    async def test_create_trigger_with_string_tenant_id(
        self,
        trigger_service,
        sample_trigger_create,
        sample_trigger_db,
        mock_db
    ):
        """Test trigger creation with string tenant_id conversion."""
        tenant_id = "550e8400-e29b-41d4-a716-446655440000"

        # Don't set tenant_id on sample_trigger_create since service adds it

        trigger_service.crud_trigger.create_with_config.return_value = sample_trigger_db

        with patch.object(trigger_service, "_cache_trigger"):
            await trigger_service.create_trigger(
                mock_db,
                sample_trigger_create,
                tenant_id
            )

            # Should complete without error (UUID conversion happens internally)
            trigger_service.crud_trigger.create_with_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_trigger_success(
        self,
        trigger_service,
        sample_trigger_update,
        sample_trigger_db,
        mock_db
    ):
        """Test successful trigger update with cache refresh."""
        trigger_id = sample_trigger_db.id
        tenant_id = sample_trigger_db.tenant_id

        # Mock CRUD update_with_config
        # Create an updated mock object
        from datetime import datetime

        class MockDBObject:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        now = datetime.now(UTC)

        updated_trigger = MockDBObject(
            id=sample_trigger_db.id,
            tenant_id=sample_trigger_db.tenant_id,
            name=sample_trigger_update.name or sample_trigger_db.name,
            slug=sample_trigger_db.slug,
            trigger_type=sample_trigger_db.trigger_type,
            description=(
                sample_trigger_update.description
                if hasattr(sample_trigger_update, 'description')
                else sample_trigger_db.description
            ),
            active=(
                sample_trigger_update.active
                if hasattr(sample_trigger_update, 'active')
                else sample_trigger_db.active
            ),
            validated=sample_trigger_db.validated,
            validation_errors=sample_trigger_db.validation_errors,
            last_validated_at=sample_trigger_db.last_validated_at,
            created_at=sample_trigger_db.created_at,
            updated_at=now,
            email_config=sample_trigger_db.email_config,
            webhook_config=sample_trigger_db.webhook_config
        )
        trigger_service.crud_trigger.update_with_config.return_value = updated_trigger

        with patch.object(trigger_service, "_cache_trigger") as mock_cache:
            result = await trigger_service.update_trigger(
                mock_db,
                trigger_id,
                sample_trigger_update,
                tenant_id
            )

            # Verify CRUD update_with_config was called
            trigger_service.crud_trigger.update_with_config.assert_called_once_with(
                db=mock_db,
                trigger_id=trigger_id,
                obj_in=sample_trigger_update,
                tenant_id=tenant_id
            )

            # Verify cache refresh
            mock_cache.assert_called_once_with(updated_trigger, str(tenant_id))

            # Verify result
            assert isinstance(result, TriggerRead)
            assert result.name == sample_trigger_update.name

    @pytest.mark.asyncio
    async def test_update_trigger_with_string_ids(
        self,
        trigger_service,
        sample_trigger_update,
        sample_trigger_db,
        mock_db
    ):
        """Test trigger update with string UUID conversion."""
        trigger_id = "550e8400-e29b-41d4-a716-446655440001"
        tenant_id = "550e8400-e29b-41d4-a716-446655440002"

        trigger_service.crud_trigger.update_with_config.return_value = sample_trigger_db

        with patch.object(trigger_service, "_cache_trigger"):
            result = await trigger_service.update_trigger(
                mock_db,
                trigger_id,
                sample_trigger_update,
                tenant_id
            )

            # Verify UUID conversion was handled
            call_args = trigger_service.crud_trigger.update_with_config.call_args
            assert isinstance(call_args[1]["trigger_id"], uuid.UUID)
            assert isinstance(call_args[1]["tenant_id"], uuid.UUID)

            assert isinstance(result, TriggerRead)

    @pytest.mark.asyncio
    async def test_update_trigger_not_found(
        self,
        trigger_service,
        sample_trigger_update,
        mock_db
    ):
        """Test update_trigger when trigger not found."""
        trigger_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        trigger_service.crud_trigger.update_with_config.return_value = None

        result = await trigger_service.update_trigger(
            mock_db,
            trigger_id,
            sample_trigger_update,
            tenant_id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_trigger_success(
        self,
        trigger_service,
        sample_trigger_db,
        mock_db
    ):
        """Test successful trigger deletion with cache cleanup."""
        trigger_id = sample_trigger_db.id
        tenant_id = sample_trigger_db.tenant_id

        with patch.object(trigger_service, "_remove_from_cache") as mock_remove_cache:
            result = await trigger_service.delete_trigger(
                mock_db,
                trigger_id,
                tenant_id
            )

            # Verify CRUD delete was called
            trigger_service.crud_trigger.delete.assert_called_once_with(
                db=mock_db,
                id=trigger_id,
                is_hard_delete=False
            )

            # Verify cache cleanup
            mock_remove_cache.assert_called_once_with(str(trigger_id), str(tenant_id))

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_trigger_hard_delete(
        self,
        trigger_service,
        sample_trigger_db,
        mock_db
    ):
        """Test trigger hard deletion."""
        trigger_id = sample_trigger_db.id
        tenant_id = sample_trigger_db.tenant_id

        with patch.object(trigger_service, "_remove_from_cache"):
            result = await trigger_service.delete_trigger(
                mock_db,
                trigger_id,
                tenant_id,
                is_hard_delete=True
            )

            # Verify hard delete was passed through
            trigger_service.crud_trigger.delete.assert_called_once_with(
                db=mock_db,
                id=trigger_id,
                is_hard_delete=True
            )

            assert result is True

    @pytest.mark.asyncio
    async def test_delete_trigger_failure(
        self,
        trigger_service,
        sample_trigger_db,
        mock_db
    ):
        """Test trigger deletion failure."""
        trigger_id = sample_trigger_db.id
        tenant_id = sample_trigger_db.tenant_id

        # Mock deletion failure
        trigger_service.crud_trigger.delete.side_effect = Exception("Database error")

        with patch.object(trigger_service, "_remove_from_cache") as mock_remove_cache:
            result = await trigger_service.delete_trigger(
                mock_db,
                trigger_id,
                tenant_id
            )

            # Verify cache was NOT cleaned up on failure
            mock_remove_cache.assert_not_called()

            assert result is False

    @pytest.mark.asyncio
    async def test_get_trigger_by_id_cache_hit(
        self,
        trigger_service,
        sample_trigger_db,
        mock_db
    ):
        """Test get_trigger_by_id with cache hit."""
        trigger_id = sample_trigger_db.id
        tenant_id = sample_trigger_db.tenant_id

        with patch("src.app.services.trigger_service.redis_client.get") as mock_get:
            # Create JSON data that can be parsed as TriggerRead
            trigger_data = {
                "id": str(sample_trigger_db.id),
                "tenant_id": str(sample_trigger_db.tenant_id),
                "name": sample_trigger_db.name,
                "slug": sample_trigger_db.slug,
                "trigger_type": sample_trigger_db.trigger_type,
                "description": sample_trigger_db.description,
                "active": sample_trigger_db.active,
                "validated": sample_trigger_db.validated,
                "validation_errors": sample_trigger_db.validation_errors,
                "last_validated_at": (
                    sample_trigger_db.last_validated_at.isoformat()
                    if sample_trigger_db.last_validated_at else None
                ),
                "created_at": sample_trigger_db.created_at.isoformat(),
                "updated_at": sample_trigger_db.updated_at.isoformat() if sample_trigger_db.updated_at else None,
                "email_config": None,
                "webhook_config": None
            }
            mock_get.return_value = json.dumps(trigger_data)

            result = await trigger_service.get_trigger_by_id(
                mock_db,
                trigger_id,
                tenant_id
            )

            # Verify cache was checked
            expected_key = f"tenant:{tenant_id}:trigger:{trigger_id}"
            mock_get.assert_called_once_with(expected_key)

            # Verify CRUD was NOT called (cache hit)
            trigger_service.crud_trigger._get_trigger_with_config.assert_not_called()

            # Verify result
            assert isinstance(result, TriggerRead)
            assert result.id == trigger_id

    @pytest.mark.asyncio
    async def test_get_trigger_by_id_cache_miss(
        self,
        trigger_service,
        sample_trigger_db,
        mock_db
    ):
        """Test get_trigger_by_id with cache miss."""
        trigger_id = sample_trigger_db.id
        tenant_id = sample_trigger_db.tenant_id

        # Mock cache miss and database hit
        trigger_service.crud_trigger._get_trigger_with_config.return_value = sample_trigger_db

        with patch("src.app.services.trigger_service.redis_client.get") as mock_get, \
             patch.object(trigger_service, "_cache_trigger") as mock_cache:
            mock_get.return_value = None

            result = await trigger_service.get_trigger_by_id(
                mock_db,
                trigger_id,
                tenant_id
            )

            # Verify CRUD was called
            trigger_service.crud_trigger._get_trigger_with_config.assert_called_once_with(
                db=mock_db,
                trigger_id=trigger_id
            )

            # Verify cache was refreshed
            mock_cache.assert_called_once_with(sample_trigger_db, str(tenant_id))

            # Verify result
            assert isinstance(result, TriggerRead)

    @pytest.mark.asyncio
    async def test_get_trigger_by_id_not_found(
        self,
        trigger_service,
        mock_db
    ):
        """Test get_trigger_by_id when trigger not found."""
        trigger_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        # Mock cache miss and database miss
        trigger_service.crud_trigger._get_trigger_with_config.return_value = None

        with patch("src.app.services.trigger_service.redis_client.get") as mock_get:
            mock_get.return_value = None

            result = await trigger_service.get_trigger_by_id(
                mock_db,
                trigger_id,
                tenant_id
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_get_trigger_by_slug_success(
        self,
        trigger_service,
        sample_trigger_db,
        mock_db
    ):
        """Test getting trigger by slug."""
        slug = "email-alert"
        tenant_id = sample_trigger_db.tenant_id

        # Mock successful slug lookup
        slug_result = Mock(id=sample_trigger_db.id)
        trigger_service.crud_trigger.get_by_slug.return_value = slug_result

        # Mock full trigger retrieval
        trigger_service.crud_trigger._get_trigger_with_config.return_value = sample_trigger_db

        with patch.object(trigger_service, "_cache_trigger") as mock_cache:
            result = await trigger_service.get_trigger_by_slug(
                mock_db,
                slug,
                tenant_id
            )

            # Verify slug lookup
            trigger_service.crud_trigger.get_by_slug.assert_called_once_with(
                db=mock_db,
                slug=slug,
                tenant_id=tenant_id
            )

            # Verify full trigger retrieval
            trigger_service.crud_trigger._get_trigger_with_config.assert_called_once_with(
                db=mock_db,
                trigger_id=sample_trigger_db.id
            )

            # Verify caching
            mock_cache.assert_called_once_with(sample_trigger_db, str(tenant_id))

            # Verify result
            assert isinstance(result, TriggerRead)

    @pytest.mark.asyncio
    async def test_get_trigger_by_slug_not_found(
        self,
        trigger_service,
        mock_db
    ):
        """Test get_trigger_by_slug when trigger not found."""
        slug = "nonexistent-trigger"
        tenant_id = uuid.uuid4()

        trigger_service.crud_trigger.get_by_slug.return_value = None

        result = await trigger_service.get_trigger_by_slug(
            mock_db,
            slug,
            tenant_id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_trigger_by_slug_config_not_found(
        self,
        trigger_service,
        sample_trigger_db,
        mock_db
    ):
        """Test get_trigger_by_slug when config retrieval fails."""
        slug = "email-alert"
        tenant_id = sample_trigger_db.tenant_id

        # Mock successful slug lookup but failed config retrieval
        slug_result = Mock(id=sample_trigger_db.id)
        trigger_service.crud_trigger.get_by_slug.return_value = slug_result
        trigger_service.crud_trigger._get_trigger_with_config.return_value = None

        result = await trigger_service.get_trigger_by_slug(
            mock_db,
            slug,
            tenant_id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_trigger_success(
        self,
        trigger_service,
        mock_db
    ):
        """Test trigger validation."""
        validation_request = TriggerValidationRequest(
            trigger_id=uuid.uuid4(),
            test_connection=True
        )

        validation_result = TriggerValidationResult(
            trigger_id=validation_request.trigger_id,
            is_valid=True,
            errors=[],
            warnings=[]
        )

        # Mock CRUD validation
        trigger_service.crud_trigger.validate_trigger.return_value = validation_result

        # Mock trigger retrieval for cache update
        from datetime import datetime
        now = datetime.now(UTC)

        mock_trigger = TriggerRead(
            id=validation_request.trigger_id,
            tenant_id=uuid.uuid4(),
            name="Test Trigger",
            slug="test-trigger",
            trigger_type="email",
            description="Test email trigger",
            active=True,
            validated=False,
            validation_errors=None,
            last_validated_at=None,
            created_at=now,
            updated_at=now,
            email_config=None,
            webhook_config=None
        )
        trigger_service.crud_trigger._get_trigger_with_config.return_value = mock_trigger

        with patch.object(trigger_service, "_cache_trigger") as mock_cache:
            result = await trigger_service.validate_trigger(mock_db, validation_request)

            # Verify CRUD validation was called
            trigger_service.crud_trigger.validate_trigger.assert_called_once_with(
                db=mock_db,
                validation_request=validation_request
            )

            # Verify cache update (if trigger_id provided)
            trigger_service.crud_trigger._get_trigger_with_config.assert_called_once_with(
                db=mock_db,
                trigger_id=validation_request.trigger_id
            )
            mock_cache.assert_called_once_with(mock_trigger, str(mock_trigger.tenant_id))

            # Verify result
            assert isinstance(result, TriggerValidationResult)
            assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_validate_trigger_cache_update_failure(
        self,
        trigger_service,
        mock_db
    ):
        """Test trigger validation when cache update fails."""
        trigger_id = uuid.uuid4()
        validation_request = TriggerValidationRequest(
            trigger_id=trigger_id
        )

        validation_result = TriggerValidationResult(
            trigger_id=trigger_id,
            is_valid=True,
            errors=[],
            warnings=[]
        )

        trigger_service.crud_trigger.validate_trigger.return_value = validation_result
        # Simulate cache update failure by returning None from get config
        trigger_service.crud_trigger._get_trigger_with_config.return_value = None

        result = await trigger_service.validate_trigger(mock_db, validation_request)

        # Verify cache update was attempted but failed gracefully
        trigger_service.crud_trigger._get_trigger_with_config.assert_called_once_with(
            db=mock_db,
            trigger_id=trigger_id
        )

        assert isinstance(result, TriggerValidationResult)
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_test_trigger_success(
        self,
        trigger_service,
        mock_db
    ):
        """Test trigger testing."""
        test_request = TriggerTestRequest(
            trigger_id=uuid.uuid4(),
            test_data={"transaction_hash": "0x123"}
        )

        test_result = TriggerTestResult(
            trigger_id=test_request.trigger_id,
            success=True,
            response={"message": "Test successful"},
            error=None,
            duration_ms=500
        )

        trigger_service.crud_trigger.test_trigger.return_value = test_result

        result = await trigger_service.test_trigger(mock_db, test_request)

        # Verify CRUD test was called
        trigger_service.crud_trigger.test_trigger.assert_called_once_with(
            db=mock_db,
            test_request=test_request
        )

        # Verify result
        assert isinstance(result, TriggerTestResult)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_activate_trigger_success(
        self,
        trigger_service,
        sample_trigger_db,
        mock_db
    ):
        """Test trigger activation."""
        trigger_id = sample_trigger_db.id
        tenant_id = sample_trigger_db.tenant_id

        # Mock activated trigger
        from datetime import datetime
        now = datetime.now(UTC)

        activated_trigger = TriggerRead(
            id=sample_trigger_db.id,
            tenant_id=sample_trigger_db.tenant_id,
            name=sample_trigger_db.name,
            slug=sample_trigger_db.slug,
            trigger_type=sample_trigger_db.trigger_type,
            description=sample_trigger_db.description,
            active=True,  # This is the key change
            validated=sample_trigger_db.validated,
            validation_errors=sample_trigger_db.validation_errors,
            last_validated_at=sample_trigger_db.last_validated_at,
            created_at=sample_trigger_db.created_at,
            updated_at=now,
            email_config=None,
            webhook_config=None
        )
        trigger_service.crud_trigger.activate_trigger.return_value = activated_trigger

        with patch.object(trigger_service, "_cache_trigger") as mock_cache:
            result = await trigger_service.activate_trigger(
                mock_db,
                trigger_id,
                tenant_id
            )

            # Verify CRUD activate was called
            trigger_service.crud_trigger.activate_trigger.assert_called_once_with(
                db=mock_db,
                trigger_id=trigger_id,
                tenant_id=tenant_id
            )

            # Verify cache update
            mock_cache.assert_called_once_with(activated_trigger, str(tenant_id))

            # Verify result
            assert isinstance(result, TriggerRead)
            assert result.active is True

    @pytest.mark.asyncio
    async def test_activate_trigger_not_found(
        self,
        trigger_service,
        mock_db
    ):
        """Test activate_trigger when trigger not found."""
        trigger_id = uuid.uuid4()
        tenant_id = uuid.uuid4()

        trigger_service.crud_trigger.activate_trigger.return_value = None

        result = await trigger_service.activate_trigger(
            mock_db,
            trigger_id,
            tenant_id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_deactivate_trigger_success(
        self,
        trigger_service,
        sample_trigger_db,
        mock_db
    ):
        """Test trigger deactivation."""
        trigger_id = sample_trigger_db.id
        tenant_id = sample_trigger_db.tenant_id

        # Mock deactivated trigger
        from datetime import datetime
        now = datetime.now(UTC)

        deactivated_trigger = TriggerRead(
            id=sample_trigger_db.id,
            tenant_id=sample_trigger_db.tenant_id,
            name=sample_trigger_db.name,
            slug=sample_trigger_db.slug,
            trigger_type=sample_trigger_db.trigger_type,
            description=sample_trigger_db.description,
            active=False,  # This is the key change
            validated=sample_trigger_db.validated,
            validation_errors=sample_trigger_db.validation_errors,
            last_validated_at=sample_trigger_db.last_validated_at,
            created_at=sample_trigger_db.created_at,
            updated_at=now,
            email_config=None,
            webhook_config=None
        )
        trigger_service.crud_trigger.deactivate_trigger.return_value = deactivated_trigger

        with patch.object(trigger_service, "_cache_trigger") as mock_cache:
            result = await trigger_service.deactivate_trigger(
                mock_db,
                trigger_id,
                tenant_id
            )

            # Verify CRUD deactivate was called
            trigger_service.crud_trigger.deactivate_trigger.assert_called_once_with(
                db=mock_db,
                trigger_id=trigger_id,
                tenant_id=tenant_id
            )

            # Verify cache update
            mock_cache.assert_called_once_with(deactivated_trigger, str(tenant_id))

            # Verify result
            assert isinstance(result, TriggerRead)
            assert result.active is False

    @pytest.mark.asyncio
    async def test_get_active_triggers_by_type_success(
        self,
        trigger_service,
        mock_db
    ):
        """Test getting active triggers by type."""
        trigger_type = "email"
        tenant_id = uuid.uuid4()

        # Mock active triggers
        from datetime import datetime
        now = datetime.now(UTC)

        active_triggers = [
            TriggerRead(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name=f"Email Trigger {i}",
                slug=f"email-trigger-{i}",
                trigger_type="email",
                description=f"Test email trigger {i}",
                active=True,
                validated=True,
                validation_errors=None,
                last_validated_at=now,
                created_at=now,
                updated_at=now,
                email_config=None,
                webhook_config=None
            ) for i in range(3)
        ]

        trigger_service.crud_trigger.get_active_triggers_by_type.return_value = active_triggers

        result = await trigger_service.get_active_triggers_by_type(
            mock_db,
            trigger_type,
            tenant_id
        )

        # Verify CRUD was called
        trigger_service.crud_trigger.get_active_triggers_by_type.assert_called_once_with(
            db=mock_db,
            trigger_type=trigger_type,
            tenant_id=tenant_id
        )

        # Verify result
        assert len(result) == 3
        assert all(isinstance(trigger, TriggerRead) for trigger in result)
        assert all(trigger.trigger_type == "email" for trigger in result)

    @pytest.mark.asyncio
    async def test_get_active_triggers_by_type_without_tenant(
        self,
        trigger_service,
        mock_db
    ):
        """Test getting active triggers by type without tenant filter."""
        trigger_type = "webhook"

        # Mock active triggers
        from datetime import datetime
        now = datetime.now(UTC)

        active_triggers = [
            TriggerRead(
                id=uuid.uuid4(),
                tenant_id=uuid.uuid4(),
                name="Webhook Trigger",
                slug="webhook-trigger",
                trigger_type="webhook",
                description="Test webhook trigger",
                active=True,
                validated=True,
                validation_errors=None,
                last_validated_at=now,
                created_at=now,
                updated_at=now,
                email_config=None,
                webhook_config=None
            )
        ]

        trigger_service.crud_trigger.get_active_triggers_by_type.return_value = active_triggers

        result = await trigger_service.get_active_triggers_by_type(
            mock_db,
            trigger_type
        )

        # Verify CRUD was called without tenant filter
        trigger_service.crud_trigger.get_active_triggers_by_type.assert_called_once_with(
            db=mock_db,
            trigger_type=trigger_type,
            tenant_id=None
        )

        # Verify result
        assert len(result) == 1
        assert result[0].trigger_type == "webhook"

    @pytest.mark.asyncio
    async def test_bulk_cache_triggers_success(
        self,
        trigger_service,
        mock_db
    ):
        """Test bulk caching triggers for a tenant."""
        tenant_id = uuid.uuid4()

        # Mock triggers result
        from typing import NamedTuple

        class MockTrigger(NamedTuple):
            id: uuid.UUID
            name: str

        mock_triggers = [
            MockTrigger(id=uuid.uuid4(), name=f"Trigger {i}") for i in range(3)
        ]
        triggers_result = {"data": mock_triggers}
        trigger_service.crud_trigger.get_multi.return_value = triggers_result

        # Mock trigger retrieval with config
        from datetime import datetime
        now = datetime.now(UTC)

        mock_trigger_reads = [
            TriggerRead(
                id=trigger.id,
                tenant_id=tenant_id,
                name=trigger.name,
                slug=f"trigger-{i}",
                trigger_type="email",
                description=f"Test email trigger {i}",
                active=True,
                validated=True,
                validation_errors=None,
                last_validated_at=now,
                created_at=now,
                updated_at=now,
                email_config=None,
                webhook_config=None
            ) for i, trigger in enumerate(mock_triggers)
        ]

        trigger_service.crud_trigger._get_trigger_with_config.side_effect = mock_trigger_reads

        with patch.object(trigger_service, "_cache_trigger") as mock_cache:
            count = await trigger_service.bulk_cache_triggers(mock_db, tenant_id)

            # Verify CRUD get_multi was called
            trigger_service.crud_trigger.get_multi.assert_called_once_with(
                db=mock_db,
                filters={"tenant_id": tenant_id}
            )

            # Verify each trigger was retrieved with config
            assert trigger_service.crud_trigger._get_trigger_with_config.call_count == 3

            # Verify each trigger was cached
            assert mock_cache.call_count == 3

            # Verify return count
            assert count == 3

    @pytest.mark.asyncio
    async def test_bulk_cache_triggers_with_list_result(
        self,
        trigger_service,
        mock_db
    ):
        """Test bulk_cache_triggers when get_multi returns a list."""
        tenant_id = uuid.uuid4()

        # Mock get_multi result as list (not dict)
        mock_triggers = [Mock(id=uuid.uuid4(), name="Trigger 1")]
        trigger_service.crud_trigger.get_multi.return_value = mock_triggers

        count = await trigger_service.bulk_cache_triggers(mock_db, tenant_id)

        # Should handle list result gracefully
        assert count == 0

    @pytest.mark.asyncio
    async def test_bulk_cache_triggers_config_retrieval_fails(
        self,
        trigger_service,
        mock_db
    ):
        """Test bulk_cache_triggers when config retrieval fails for some triggers."""
        tenant_id = uuid.uuid4()

        # Mock triggers result
        from typing import NamedTuple

        class MockTrigger(NamedTuple):
            id: uuid.UUID
            name: str

        mock_triggers = [
            MockTrigger(id=uuid.uuid4(), name=f"Trigger {i}") for i in range(3)
        ]
        triggers_result = {"data": mock_triggers}
        trigger_service.crud_trigger.get_multi.return_value = triggers_result

        # Mock config retrieval - some succeed, some fail
        from datetime import datetime
        now = datetime.now(UTC)

        trigger_service.crud_trigger._get_trigger_with_config.side_effect = [
            TriggerRead(
                id=mock_triggers[0].id,
                tenant_id=tenant_id,
                name="Trigger 0",
                slug="trigger-0",
                trigger_type="email",
                description="Test email trigger 0",
                active=True,
                validated=True,
                validation_errors=None,
                last_validated_at=now,
                created_at=now,
                updated_at=now,
                email_config=None,
                webhook_config=None
            ),
            None,  # Failed retrieval
            TriggerRead(
                id=mock_triggers[2].id,
                tenant_id=tenant_id,
                name="Trigger 2",
                slug="trigger-2",
                trigger_type="email",
                description="Test email trigger 2",
                active=True,
                validated=True,
                validation_errors=None,
                last_validated_at=now,
                created_at=now,
                updated_at=now,
                email_config=None,
                webhook_config=None
            )
        ]

        with patch.object(trigger_service, "_cache_trigger") as mock_cache:
            count = await trigger_service.bulk_cache_triggers(mock_db, tenant_id)

            # Should only cache successful retrievals
            assert mock_cache.call_count == 2
            assert count == 2


class TestTriggerServiceCachingMethods:
    """Test Redis caching helper methods."""

    @pytest.fixture
    def trigger_service(self):
        """Create trigger service for testing cache methods."""
        return TriggerService(Mock())

    @pytest.fixture
    def sample_trigger(self):
        """Sample trigger for caching tests."""
        from datetime import datetime
        now = datetime.now(UTC)
        return TriggerRead(
            id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            name="Test Trigger",
            slug="test-trigger",
            trigger_type="email",
            description="Test email trigger",
            active=True,
            validated=True,
            validation_errors=None,
            last_validated_at=now,
            created_at=now,
            updated_at=now,
            email_config=None,
            webhook_config=None
        )

    @pytest.mark.asyncio
    async def test_cache_trigger_success(self, trigger_service, sample_trigger):
        """Test successful trigger caching."""
        tenant_id = str(sample_trigger.tenant_id)

        with patch("src.app.services.trigger_service.redis_client.set") as mock_set:
            await trigger_service._cache_trigger(sample_trigger, tenant_id)

            # Verify Redis set was called
            mock_set.assert_called_once()
            call_args = mock_set.call_args

            # Check cache key
            expected_key = f"tenant:{tenant_id}:trigger:{sample_trigger.id}"
            assert call_args[0][0] == expected_key

            # Check data is JSON serialized
            cached_data = call_args[0][1]
            parsed_data = json.loads(cached_data)
            assert parsed_data["name"] == sample_trigger.name

            # Check TTL
            assert call_args[1]["expiration"] == 3600

    @pytest.mark.asyncio
    async def test_remove_from_cache_success(self, trigger_service):
        """Test successful cache removal."""
        trigger_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        with patch("src.app.services.trigger_service.redis_client.delete") as mock_delete:
            await trigger_service._remove_from_cache(trigger_id, tenant_id)

            expected_key = f"tenant:{tenant_id}:trigger:{trigger_id}"
            mock_delete.assert_called_once_with(expected_key)

    def test_get_cache_key_success(self, trigger_service):
        """Test cache key generation."""
        entity_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        key = trigger_service.get_cache_key(entity_id, tenant_id=tenant_id)

        expected_key = f"tenant:{tenant_id}:trigger:{entity_id}"
        assert key == expected_key

    def test_get_cache_key_missing_tenant_id(self, trigger_service):
        """Test cache key generation without tenant_id."""
        entity_id = str(uuid.uuid4())

        with pytest.raises(ValueError, match="tenant_id is required for trigger cache key"):
            trigger_service.get_cache_key(entity_id)

    def test_get_cache_ttl(self, trigger_service):
        """Test cache TTL value."""
        ttl = trigger_service.get_cache_ttl()
        assert ttl == 3600

    def test_read_schema_property(self, trigger_service):
        """Test read_schema property."""
        assert trigger_service.read_schema == TriggerRead


class TestTriggerServiceInitialization:
    """Test TriggerService initialization and dependency injection."""

    def test_trigger_service_initialization(self):
        """Test service initialization with dependencies."""
        mock_crud_trigger = Mock()

        service = TriggerService(mock_crud_trigger)

        assert service.crud == mock_crud_trigger
        assert service.crud_trigger == mock_crud_trigger


class TestTriggerServiceBaseServiceIntegration:
    """Test TriggerService integration with BaseService."""

    @pytest.fixture
    def trigger_service(self):
        """Create trigger service for base service integration testing."""
        return TriggerService(Mock())

    def test_inheritance_from_base_service(self, trigger_service):
        """Test that TriggerService properly inherits from BaseService."""
        from src.app.services.base_service import BaseService

        assert isinstance(trigger_service, BaseService)

    def test_abstract_methods_implemented(self, trigger_service):
        """Test that all required abstract methods are implemented."""
        # Test get_cache_key
        key = trigger_service.get_cache_key("123", tenant_id="tenant1")
        assert key == "tenant:tenant1:trigger:123"

        # Test get_cache_ttl
        ttl = trigger_service.get_cache_ttl()
        assert ttl == 3600

        # Test read_schema property
        assert trigger_service.read_schema == TriggerRead
