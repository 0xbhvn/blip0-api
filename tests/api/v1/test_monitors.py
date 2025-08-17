"""
Comprehensive tests for monitor API endpoints.
Tests all CRUD operations, pagination, filtering, and special endpoints.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.app.api.v1.monitors import (
    create_monitor,
    delete_monitor,
    get_monitor,
    list_monitors,
    pause_monitor,
    refresh_monitors_cache,
    resume_monitor,
    update_monitor,
    validate_monitor,
)
from src.app.core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
)
from src.app.schemas.monitor import (
    MonitorCreate,
    MonitorRead,
    MonitorUpdate,
    MonitorValidationResult,
)


@pytest.fixture
def sample_tenant_id():
    """Generate a sample tenant ID."""
    return uuid.uuid4()


@pytest.fixture
def sample_monitor_id():
    """Generate a sample monitor ID."""
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
def sample_monitor_create(sample_tenant_id):
    """Generate sample monitor creation data."""
    return MonitorCreate(
        tenant_id=sample_tenant_id,
        name="Test Monitor",
        slug="test-monitor",
        description="Test monitor description",
        paused=False,
        networks=["ethereum", "polygon"],
        addresses=[],
        match_events=[{"event": "Transfer"}],
        match_functions=[],
        match_transactions=[],
        trigger_conditions=[],
        triggers=["trigger-1"],
    )


@pytest.fixture
def sample_monitor_read(sample_monitor_id, sample_tenant_id):
    """Generate sample monitor read data."""
    return MonitorRead(
        id=uuid.UUID(sample_monitor_id),
        tenant_id=sample_tenant_id,
        name="Test Monitor",
        slug="test-monitor",
        description="Test monitor description",
        paused=False,
        active=True,
        validated=True,
        validation_errors=None,
        networks=["ethereum", "polygon"],
        addresses=[],
        match_events=[{"event": "Transfer"}],
        match_functions=[],
        match_transactions=[],
        trigger_conditions=[],
        triggers=["trigger-1"],
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        last_validated_at=datetime.utcnow(),
    )


@pytest.fixture
def mock_monitor_service():
    """Mock monitor service."""
    with patch("src.app.api.v1.monitors.monitor_service") as mock_service:
        yield mock_service


class TestListMonitors:
    """Test GET /monitors endpoint."""

    @pytest.mark.asyncio
    async def test_list_monitors_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test successful monitor listing with pagination."""
        # Mock service response
        mock_monitor_service.list_monitors = AsyncMock(
            return_value={
                "items": [sample_monitor_read],
                "total": 1,
                "page": 1,
                "size": 50,
                "pages": 1,
            }
        )

        result = await list_monitors(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            page=1,
            size=50,
            name=None,
            slug=None,
            active=None,
            paused=None,
            validated=None,
            network_slug=None,
            has_triggers=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0] == sample_monitor_read
        mock_monitor_service.list_monitors.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_monitors_with_filters(
        self,
        mock_db,
        current_user_with_tenant,
        mock_monitor_service,
    ):
        """Test monitor listing with filters."""
        mock_monitor_service.list_monitors = AsyncMock(
            return_value={"items": [], "total": 0, "page": 1, "size": 50, "pages": 0}
        )

        result = await list_monitors(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            page=1,
            size=50,
            name="test",
            slug="test-slug",
            active=True,
            paused=False,
            validated=True,
            network_slug="ethereum",
            has_triggers=True,
            sort_field="name",
            sort_order="asc",
        )

        assert result["total"] == 0
        assert len(result["items"]) == 0

        # Verify filter was constructed correctly
        call_args = mock_monitor_service.list_monitors.call_args
        filters = call_args.kwargs["filters"]
        assert filters.name == "test"
        assert filters.slug == "test-slug"
        assert filters.active is True
        assert filters.paused is False

    @pytest.mark.asyncio
    async def test_list_monitors_no_tenant(
        self,
        mock_db,
        current_user_without_tenant,
    ):
        """Test monitor listing without tenant association."""
        with pytest.raises(ForbiddenException, match="User is not associated with any tenant"):
            await list_monitors(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_without_tenant,
                page=1,
                size=50,
                name=None,
                slug=None,
                active=None,
                paused=None,
                validated=None,
                network_slug=None,
                has_triggers=None,
                sort_field="created_at",
                sort_order="desc",
            )


class TestGetMonitor:
    """Test GET /monitors/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_monitor_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test successful single monitor retrieval."""
        mock_monitor_service.get_monitor = AsyncMock(return_value=sample_monitor_read)

        result = await get_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            include_triggers=False,
        )

        assert result == sample_monitor_read
        mock_monitor_service.get_monitor.assert_called_once_with(
            db=mock_db,
            monitor_id=sample_monitor_id,
            tenant_id=str(current_user_with_tenant["tenant_id"]),
        )

    @pytest.mark.asyncio
    async def test_get_monitor_with_triggers(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test monitor retrieval with triggers included."""
        monitor_with_triggers = {
            **sample_monitor_read.model_dump(),
            "triggers": [{"id": "trigger-1", "type": "email"}],
        }
        mock_monitor_service.get_monitor_with_triggers = AsyncMock(
            return_value=monitor_with_triggers
        )

        result = await get_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            include_triggers=True,
        )

        assert result == monitor_with_triggers
        assert "triggers" in result
        mock_monitor_service.get_monitor_with_triggers.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_monitor_invalid_id(
        self,
        mock_db,
        current_user_with_tenant,
    ):
        """Test monitor retrieval with invalid UUID."""
        with pytest.raises(BadRequestException, match="Invalid monitor ID format"):
            await get_monitor(
                _request=Mock(),
                monitor_id="invalid-uuid",
                db=mock_db,
                current_user=current_user_with_tenant,
                include_triggers=False,
            )

    @pytest.mark.asyncio
    async def test_get_monitor_not_found(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        mock_monitor_service,
    ):
        """Test monitor retrieval when monitor doesn't exist."""
        mock_monitor_service.get_monitor = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match=f"Monitor {sample_monitor_id} not found"):
            await get_monitor(
                _request=Mock(),
                monitor_id=sample_monitor_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                include_triggers=False,
            )


class TestCreateMonitor:
    """Test POST /monitors endpoint."""

    @pytest.mark.asyncio
    async def test_create_monitor_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_create,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test successful monitor creation."""
        mock_monitor_service.list_monitors = AsyncMock(
            return_value={"total": 0, "items": []}
        )
        mock_monitor_service.create_monitor = AsyncMock(return_value=sample_monitor_read)

        result = await create_monitor(
            _request=Mock(),
            monitor_in=sample_monitor_create,
            db=mock_db,
            current_user=current_user_with_tenant,
        )

        assert result == sample_monitor_read
        mock_monitor_service.create_monitor.assert_called_once_with(
            db=mock_db,
            monitor_in=sample_monitor_create,
            tenant_id=current_user_with_tenant["tenant_id"],
        )

    @pytest.mark.asyncio
    async def test_create_monitor_wrong_tenant(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_create,
    ):
        """Test monitor creation with mismatched tenant ID."""
        sample_monitor_create.tenant_id = uuid.uuid4()  # Different tenant

        with pytest.raises(ForbiddenException, match="Cannot create monitors for other tenants"):
            await create_monitor(
                _request=Mock(),
                monitor_in=sample_monitor_create,
                db=mock_db,
                current_user=current_user_with_tenant,
            )

    @pytest.mark.asyncio
    async def test_create_monitor_duplicate_slug(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_create,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test monitor creation with duplicate slug."""
        mock_monitor_service.list_monitors = AsyncMock(
            return_value={"total": 1, "items": [sample_monitor_read]}
        )

        with pytest.raises(
            DuplicateValueException,
            match=f"Monitor with slug '{sample_monitor_create.slug}' already exists",
        ):
            await create_monitor(
                _request=Mock(),
                monitor_in=sample_monitor_create,
                db=mock_db,
                current_user=current_user_with_tenant,
            )

    @pytest.mark.asyncio
    async def test_create_monitor_service_error(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_create,
        mock_monitor_service,
    ):
        """Test monitor creation with service error."""
        mock_monitor_service.list_monitors = AsyncMock(
            return_value={"total": 0, "items": []}
        )
        mock_monitor_service.create_monitor = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_monitor(
                _request=Mock(),
                monitor_in=sample_monitor_create,
                db=mock_db,
                current_user=current_user_with_tenant,
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal server error"


class TestUpdateMonitor:
    """Test PUT /monitors/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_monitor_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test successful monitor update."""
        monitor_update = MonitorUpdate(name="Updated Monitor", description="Updated description")
        updated_monitor = sample_monitor_read.model_copy()
        updated_monitor.name = "Updated Monitor"

        mock_monitor_service.update_monitor = AsyncMock(return_value=updated_monitor)

        result = await update_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            monitor_update=monitor_update,
            db=mock_db,
            current_user=current_user_with_tenant,
        )

        assert result.name == "Updated Monitor"
        mock_monitor_service.update_monitor.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_monitor_duplicate_slug(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test monitor update with duplicate slug."""
        monitor_update = MonitorUpdate(slug="existing-slug")

        # Create a different monitor with the same slug (different ID)
        different_monitor = sample_monitor_read.model_copy()
        different_monitor.id = uuid.uuid4()  # Different ID

        # Mock that another monitor with this slug exists
        mock_monitor_service.list_monitors = AsyncMock(
            return_value={"total": 1, "items": [different_monitor]}
        )

        with pytest.raises(
            DuplicateValueException,
            match="Monitor with slug 'existing-slug' already exists",
        ):
            await update_monitor(
                _request=Mock(),
                monitor_id=sample_monitor_id,
                monitor_update=monitor_update,
                db=mock_db,
                current_user=current_user_with_tenant,
            )

    @pytest.mark.asyncio
    async def test_update_monitor_not_found(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        mock_monitor_service,
    ):
        """Test monitor update when monitor doesn't exist."""
        monitor_update = MonitorUpdate(name="Updated Monitor")
        mock_monitor_service.update_monitor = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match=f"Monitor {sample_monitor_id} not found"):
            await update_monitor(
                _request=Mock(),
                monitor_id=sample_monitor_id,
                monitor_update=monitor_update,
                db=mock_db,
                current_user=current_user_with_tenant,
            )


class TestDeleteMonitor:
    """Test DELETE /monitors/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_monitor_soft_delete(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        mock_monitor_service,
    ):
        """Test soft delete of monitor."""
        mock_monitor_service.delete_monitor = AsyncMock(return_value=True)

        await delete_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            hard_delete=False,
        )

        mock_monitor_service.delete_monitor.assert_called_once_with(
            db=mock_db,
            monitor_id=sample_monitor_id,
            tenant_id=str(current_user_with_tenant["tenant_id"]),
            is_hard_delete=False,
        )

    @pytest.mark.asyncio
    async def test_delete_monitor_hard_delete(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        mock_monitor_service,
    ):
        """Test hard delete of monitor."""
        mock_monitor_service.delete_monitor = AsyncMock(return_value=True)

        await delete_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            hard_delete=True,
        )

        mock_monitor_service.delete_monitor.assert_called_once_with(
            db=mock_db,
            monitor_id=sample_monitor_id,
            tenant_id=str(current_user_with_tenant["tenant_id"]),
            is_hard_delete=True,
        )

    @pytest.mark.asyncio
    async def test_delete_monitor_not_found(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        mock_monitor_service,
    ):
        """Test delete when monitor doesn't exist."""
        mock_monitor_service.delete_monitor = AsyncMock(return_value=False)

        with pytest.raises(NotFoundException, match=f"Monitor {sample_monitor_id} not found"):
            await delete_monitor(
                _request=Mock(),
                monitor_id=sample_monitor_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                hard_delete=False,
            )


class TestPauseResumeMonitor:
    """Test POST /monitors/{id}/pause and /resume endpoints."""

    @pytest.mark.asyncio
    async def test_pause_monitor_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test successful monitor pause."""
        paused_monitor = sample_monitor_read.model_copy()
        paused_monitor.paused = True
        paused_monitor.active = False

        mock_monitor_service.update_monitor = AsyncMock(return_value=paused_monitor)

        result = await pause_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            db=mock_db,
            current_user=current_user_with_tenant,
        )

        assert result.paused is True
        assert result.active is False

        # Verify correct update was called
        call_args = mock_monitor_service.update_monitor.call_args
        assert call_args.kwargs["monitor_update"].paused is True
        assert call_args.kwargs["monitor_update"].active is False

    @pytest.mark.asyncio
    async def test_resume_monitor_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test successful monitor resume."""
        resumed_monitor = sample_monitor_read.model_copy()
        resumed_monitor.paused = False
        resumed_monitor.active = True

        mock_monitor_service.update_monitor = AsyncMock(return_value=resumed_monitor)

        result = await resume_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            db=mock_db,
            current_user=current_user_with_tenant,
        )

        assert result.paused is False
        assert result.active is True

        # Verify correct update was called
        call_args = mock_monitor_service.update_monitor.call_args
        assert call_args.kwargs["monitor_update"].paused is False
        assert call_args.kwargs["monitor_update"].active is True


class TestValidateMonitor:
    """Test POST /monitors/{id}/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_monitor_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        sample_monitor_read,
        mock_monitor_service,
    ):
        """Test successful monitor validation."""
        mock_monitor_service.get_monitor = AsyncMock(return_value=sample_monitor_read)
        mock_monitor_service.update_monitor = AsyncMock(return_value=sample_monitor_read)

        result = await validate_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            validate_triggers=True,
            _validate_networks=True,
        )

        assert isinstance(result, MonitorValidationResult)
        assert result.monitor_id == uuid.UUID(sample_monitor_id)
        assert result.is_valid is True
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_validate_monitor_with_errors(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        mock_monitor_service,
    ):
        """Test monitor validation with errors."""
        # Create a monitor with missing required fields
        invalid_monitor = MonitorRead(
            id=uuid.UUID(sample_monitor_id),
            tenant_id=current_user_with_tenant["tenant_id"],
            name="",  # Empty name
            slug="",  # Empty slug
            description=None,
            paused=False,
            active=True,
            validated=False,
            validation_errors=None,
            networks=[],  # No networks
            addresses=[],
            match_events=[],
            match_functions=[],
            match_transactions=[],
            trigger_conditions=[],
            triggers=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_validated_at=None,
        )

        mock_monitor_service.get_monitor = AsyncMock(return_value=invalid_monitor)
        mock_monitor_service.update_monitor = AsyncMock(return_value=invalid_monitor)

        result = await validate_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            validate_triggers=True,
            _validate_networks=True,
        )

        assert result.is_valid is False
        assert len(result.errors) > 0
        assert "Monitor name is required" in result.errors
        assert "Monitor slug is required" in result.errors
        assert "At least one network must be configured" in result.errors

    @pytest.mark.asyncio
    async def test_validate_monitor_with_warnings(
        self,
        mock_db,
        current_user_with_tenant,
        sample_monitor_id,
        mock_monitor_service,
    ):
        """Test monitor validation with warnings."""
        # Monitor with no matching criteria or triggers
        monitor_with_warnings = MonitorRead(
            id=uuid.UUID(sample_monitor_id),
            tenant_id=current_user_with_tenant["tenant_id"],
            name="Test Monitor",
            slug="test-monitor",
            description=None,
            paused=False,
            active=True,
            validated=True,
            validation_errors=None,
            networks=["ethereum"],
            addresses=[],
            match_events=[],  # No matching criteria
            match_functions=[],
            match_transactions=[],
            trigger_conditions=[],
            triggers=[],  # No triggers
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_validated_at=None,
        )

        mock_monitor_service.get_monitor = AsyncMock(return_value=monitor_with_warnings)
        mock_monitor_service.update_monitor = AsyncMock(return_value=monitor_with_warnings)

        result = await validate_monitor(
            _request=Mock(),
            monitor_id=sample_monitor_id,
            db=mock_db,
            current_user=current_user_with_tenant,
            validate_triggers=True,
            _validate_networks=True,
        )

        assert result.is_valid is True  # Warnings don't make it invalid
        assert len(result.warnings) > 0
        assert "Monitor has no matching criteria configured" in result.warnings
        assert "Monitor has no triggers configured" in result.warnings


class TestRefreshMonitorsCache:
    """Test POST /monitors/refresh-cache endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_cache_success(
        self,
        mock_db,
        current_user_with_tenant,
        mock_monitor_service,
    ):
        """Test successful cache refresh."""
        mock_monitor_service.refresh_all_tenant_monitors = AsyncMock(return_value=5)

        result = await refresh_monitors_cache(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
        )

        assert result["monitors_refreshed"] == 5
        assert "Successfully refreshed 5 monitors" in result["message"]
        assert result["tenant_id"] == str(current_user_with_tenant["tenant_id"])

        mock_monitor_service.refresh_all_tenant_monitors.assert_called_once_with(
            db=mock_db,
            tenant_id=str(current_user_with_tenant["tenant_id"]),
        )

    @pytest.mark.asyncio
    async def test_refresh_cache_no_monitors(
        self,
        mock_db,
        current_user_with_tenant,
        mock_monitor_service,
    ):
        """Test cache refresh with no monitors."""
        mock_monitor_service.refresh_all_tenant_monitors = AsyncMock(return_value=0)

        result = await refresh_monitors_cache(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
        )

        assert result["monitors_refreshed"] == 0
        assert "Successfully refreshed 0 monitors" in result["message"]

    @pytest.mark.asyncio
    async def test_refresh_cache_no_tenant(
        self,
        mock_db,
        current_user_without_tenant,
    ):
        """Test cache refresh without tenant association."""
        with pytest.raises(ForbiddenException, match="User is not associated with any tenant"):
            await refresh_monitors_cache(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_without_tenant,
            )


class TestMonitorEndpointEdgeCases:
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
        with pytest.raises(BadRequestException, match="Invalid monitor ID format"):
            await get_monitor(
                _request=Mock(),
                monitor_id=invalid_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                include_triggers=False,
            )

        # Test update
        with pytest.raises(BadRequestException, match="Invalid monitor ID format"):
            await update_monitor(
                _request=Mock(),
                monitor_id=invalid_id,
                monitor_update=MonitorUpdate(name="Test"),
                db=mock_db,
                current_user=current_user_with_tenant,
            )

        # Test delete
        with pytest.raises(BadRequestException, match="Invalid monitor ID format"):
            await delete_monitor(
                _request=Mock(),
                monitor_id=invalid_id,
                db=mock_db,
                current_user=current_user_with_tenant,
                hard_delete=False,
            )

    @pytest.mark.asyncio
    async def test_pagination_boundaries(
        self,
        mock_db,
        current_user_with_tenant,
        mock_monitor_service,
    ):
        """Test pagination with edge cases."""
        # Test with very large page number
        mock_monitor_service.list_monitors = AsyncMock(
            return_value={"items": [], "total": 10, "page": 1000, "size": 50, "pages": 1}
        )

        result = await list_monitors(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            page=1000,
            size=50,
            name=None,
            slug=None,
            active=None,
            paused=None,
            validated=None,
            network_slug=None,
            has_triggers=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["items"] == []
        assert result["page"] == 1000
