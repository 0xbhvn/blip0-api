"""
Comprehensive tests for tenant self-service API endpoints.
Tests tenant management operations available to authenticated users for their own tenant.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from src.app.api.v1.tenant import (
    get_current_tenant,
    get_tenant_limits,
    get_tenant_usage,
    update_current_tenant,
)
from src.app.core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
)
from src.app.schemas.tenant import (
    TenantLimitsRead,
    TenantRead,
    TenantSelfServiceUpdate,
    TenantUsageStats,
    TenantWithLimits,
)


@pytest.fixture
def sample_tenant_id():
    """Generate a sample tenant ID."""
    return uuid.uuid4()


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
def sample_tenant_read(sample_tenant_id):
    """Generate sample tenant read data."""
    return TenantRead(
        id=sample_tenant_id,
        name="Test Company",
        slug="test-company",
        plan="starter",
        status="active",
        settings={"timezone": "UTC", "notifications": True},
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_tenant_suspended(sample_tenant_id):
    """Generate sample suspended tenant."""
    return TenantRead(
        id=sample_tenant_id,
        name="Suspended Company",
        slug="suspended-company",
        plan="starter",
        status="suspended",
        settings={"timezone": "UTC", "suspended_at": "2024-01-01T00:00:00Z"},
        is_active=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_tenant_limits(sample_tenant_id):
    """Generate sample tenant limits."""
    return TenantLimitsRead(
        tenant_id=sample_tenant_id,
        max_monitors=50,
        max_networks=10,
        max_triggers=100,
        max_api_calls_per_hour=10000,
        max_storage_gb=10.0,
        max_concurrent_operations=10,
        current_monitors=5,
        current_networks=2,
        current_triggers=10,
        current_storage_gb=1.0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_tenant_with_limits(sample_tenant_read, sample_tenant_limits):
    """Generate sample tenant with limits data."""
    return TenantWithLimits(
        **sample_tenant_read.model_dump(),
        limits=sample_tenant_limits,
    )


@pytest.fixture
def sample_tenant_usage_stats(sample_tenant_id):
    """Generate sample tenant usage statistics."""
    return TenantUsageStats(
        tenant_id=sample_tenant_id,
        # Current usage
        monitors_count=5,
        networks_count=2,
        triggers_count=10,
        storage_gb_used=1.0,
        api_calls_last_hour=500,
        # Limits
        monitors_limit=50,
        networks_limit=10,
        triggers_limit=100,
        storage_gb_limit=10.0,
        api_calls_per_hour_limit=10000,
        # Remaining
        monitors_remaining=45,
        networks_remaining=8,
        triggers_remaining=90,
        storage_gb_remaining=9.0,
        api_calls_remaining=9500,
        # Percentages
        monitors_usage_percent=10.0,
        networks_usage_percent=20.0,
        triggers_usage_percent=10.0,
        storage_usage_percent=10.0,
        api_calls_usage_percent=5.0,
        calculated_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_tenant_service():
    """Mock tenant service."""
    with patch("src.app.api.v1.tenant.tenant_service") as mock_service:
        yield mock_service


@pytest.fixture
def mock_crud_tenant():
    """Mock crud_tenant."""
    with patch("src.app.crud.crud_tenant.crud_tenant") as mock_crud:
        yield mock_crud


class TestGetCurrentTenant:
    """Test GET /tenant endpoint."""

    @pytest.mark.asyncio
    async def test_get_current_tenant_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_with_limits,
        mock_crud_tenant,
    ):
        """Test successful retrieval of current tenant with limits."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        mock_crud_tenant.get_with_limits = AsyncMock(
            return_value=sample_tenant_with_limits
        )

        result = await get_current_tenant(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            tenant_id=tenant_id,
            _rate_limit=Mock(),
        )

        assert result == sample_tenant_with_limits
        mock_crud_tenant.get_with_limits.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_tenant_not_found(
        self,
        mock_db,
        current_user_with_tenant,
        mock_crud_tenant,
    ):
        """Test get current tenant when tenant doesn't exist."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        mock_crud_tenant.get_with_limits = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant .* not found"):
            await get_current_tenant(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_get_current_tenant_suspended(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_with_limits,
        mock_crud_tenant,
    ):
        """Test get current tenant when tenant is suspended."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        suspended_tenant = TenantWithLimits(
            **{**sample_tenant_with_limits.model_dump(), "status": "suspended"}
        )
        mock_crud_tenant.get_with_limits = AsyncMock(return_value=suspended_tenant)

        with pytest.raises(ForbiddenException, match="Tenant is suspended"):
            await get_current_tenant(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                _rate_limit=Mock(),
            )


class TestUpdateCurrentTenant:
    """Test PUT /tenant endpoint."""

    @pytest.mark.asyncio
    async def test_update_current_tenant_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test successful update of current tenant settings."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        update_data = TenantSelfServiceUpdate(
            name="Updated Company",
            settings={"timezone": "America/New_York"},
        )

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        updated_tenant = TenantRead(
            **{**sample_tenant_read.model_dump(), "name": "Updated Company"}
        )
        mock_tenant_service.update_tenant_self_service = AsyncMock(
            return_value=updated_tenant
        )

        result = await update_current_tenant(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            tenant_id=tenant_id,
            update_data=update_data,
            _rate_limit=Mock(),
        )

        assert result.name == "Updated Company"
        mock_tenant_service.update_tenant_self_service.assert_called_once_with(
            db=mock_db,
            tenant_id=tenant_id,
            update_data=update_data,
        )
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_current_tenant_not_found(
        self,
        mock_db,
        current_user_with_tenant,
        mock_tenant_service,
    ):
        """Test update current tenant when tenant doesn't exist."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        update_data = TenantSelfServiceUpdate(name="Updated", settings={})

        mock_tenant_service.get_tenant = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant .* not found"):
            await update_current_tenant(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                update_data=update_data,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_update_current_tenant_suspended(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_suspended,
        mock_tenant_service,
    ):
        """Test update current tenant when tenant is suspended."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        update_data = TenantSelfServiceUpdate(name="Updated", settings={})

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_suspended)

        with pytest.raises(ForbiddenException, match="Cannot update suspended tenant"):
            await update_current_tenant(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                update_data=update_data,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_update_current_tenant_duplicate_name(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test update current tenant with duplicate name."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        update_data = TenantSelfServiceUpdate(name="Existing Company", settings={})

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.update_tenant_self_service = AsyncMock(
            side_effect=IntegrityError("duplicate key", None, Exception("duplicate key error"))
        )

        with pytest.raises(DuplicateValueException, match="already exists"):
            await update_current_tenant(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                update_data=update_data,
                _rate_limit=Mock(),
            )

        mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_current_tenant_validation_error(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test update current tenant with validation error."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        update_data = TenantSelfServiceUpdate(name="Valid", settings={"invalid": True})

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        # Raise a generic exception that will be caught and converted to BadRequestException
        mock_tenant_service.update_tenant_self_service = AsyncMock(
            side_effect=Exception("Invalid settings: validation error")
        )

        with pytest.raises(BadRequestException, match="Failed to update tenant"):
            await update_current_tenant(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                update_data=update_data,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_update_current_tenant_general_error(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test update current tenant with general error."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        update_data = TenantSelfServiceUpdate(name="Valid", settings={})

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.update_tenant_self_service = AsyncMock(
            side_effect=Exception("Database error")
        )

        with pytest.raises(BadRequestException, match="Failed to update tenant"):
            await update_current_tenant(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                update_data=update_data,
                _rate_limit=Mock(),
            )

        mock_db.rollback.assert_called_once()


class TestGetTenantUsage:
    """Test GET /tenant/usage endpoint."""

    @pytest.mark.asyncio
    async def test_get_tenant_usage_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        sample_tenant_usage_stats,
        mock_tenant_service,
    ):
        """Test successful retrieval of tenant usage statistics."""
        tenant_id = str(current_user_with_tenant["tenant_id"])

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.get_tenant_usage = AsyncMock(
            return_value=sample_tenant_usage_stats
        )

        result = await get_tenant_usage(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            tenant_id=tenant_id,
            _rate_limit=Mock(),
        )

        assert result == sample_tenant_usage_stats
        assert result.monitors_count == 5
        assert result.monitors_remaining == 45
        assert result.monitors_usage_percent == 10.0
        mock_tenant_service.get_tenant_usage.assert_called_once_with(mock_db, tenant_id)

    @pytest.mark.asyncio
    async def test_get_tenant_usage_not_found(
        self,
        mock_db,
        current_user_with_tenant,
        mock_tenant_service,
    ):
        """Test get tenant usage when tenant doesn't exist."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        mock_tenant_service.get_tenant = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant .* not found"):
            await get_tenant_usage(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_get_tenant_usage_suspended(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_suspended,
        mock_tenant_service,
    ):
        """Test get tenant usage when tenant is suspended."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_suspended)

        with pytest.raises(ForbiddenException, match="Tenant is suspended"):
            await get_tenant_usage(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_get_tenant_usage_not_available(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test get tenant usage when statistics not available."""
        tenant_id = str(current_user_with_tenant["tenant_id"])

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.get_tenant_usage = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Usage statistics not available"):
            await get_tenant_usage(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_get_tenant_usage_at_limit(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test get tenant usage when at usage limits."""
        tenant_id = str(current_user_with_tenant["tenant_id"])

        usage_at_limit = TenantUsageStats(
            tenant_id=uuid.UUID(tenant_id),
            monitors_count=50,
            networks_count=10,
            triggers_count=100,
            storage_gb_used=10.0,
            api_calls_last_hour=10000,
            monitors_limit=50,
            networks_limit=10,
            triggers_limit=100,
            storage_gb_limit=10.0,
            api_calls_per_hour_limit=10000,
            monitors_remaining=0,
            networks_remaining=0,
            triggers_remaining=0,
            storage_gb_remaining=0.0,
            api_calls_remaining=0,
            monitors_usage_percent=100.0,
            networks_usage_percent=100.0,
            triggers_usage_percent=100.0,
            storage_usage_percent=100.0,
            api_calls_usage_percent=100.0,
            calculated_at=datetime.now(UTC),
        )

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.get_tenant_usage = AsyncMock(return_value=usage_at_limit)

        result = await get_tenant_usage(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            tenant_id=tenant_id,
            _rate_limit=Mock(),
        )

        assert result.monitors_remaining == 0
        assert result.monitors_usage_percent == 100.0
        assert result.api_calls_remaining == 0

    @pytest.mark.asyncio
    async def test_get_tenant_usage_zero_usage(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test get tenant usage with zero usage."""
        tenant_id = str(current_user_with_tenant["tenant_id"])

        zero_usage = TenantUsageStats(
            tenant_id=uuid.UUID(tenant_id),
            monitors_count=0,
            networks_count=0,
            triggers_count=0,
            storage_gb_used=0.0,
            api_calls_last_hour=0,
            monitors_limit=50,
            networks_limit=10,
            triggers_limit=100,
            storage_gb_limit=10.0,
            api_calls_per_hour_limit=10000,
            monitors_remaining=50,
            networks_remaining=10,
            triggers_remaining=100,
            storage_gb_remaining=10.0,
            api_calls_remaining=10000,
            monitors_usage_percent=0.0,
            networks_usage_percent=0.0,
            triggers_usage_percent=0.0,
            storage_usage_percent=0.0,
            api_calls_usage_percent=0.0,
            calculated_at=datetime.now(UTC),
        )

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.get_tenant_usage = AsyncMock(return_value=zero_usage)

        result = await get_tenant_usage(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            tenant_id=tenant_id,
            _rate_limit=Mock(),
        )

        assert result.monitors_count == 0
        assert result.monitors_usage_percent == 0.0


class TestGetTenantLimits:
    """Test GET /tenant/limits endpoint."""

    @pytest.mark.asyncio
    async def test_get_tenant_limits_success(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        sample_tenant_limits,
        mock_tenant_service,
    ):
        """Test successful retrieval of tenant limits."""
        tenant_id = str(current_user_with_tenant["tenant_id"])

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.get_tenant_limits = AsyncMock(
            return_value=sample_tenant_limits
        )

        result = await get_tenant_limits(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            tenant_id=tenant_id,
            _rate_limit=Mock(),
        )

        assert result == sample_tenant_limits
        assert result.max_monitors == 50
        assert result.max_api_calls_per_hour == 10000
        mock_tenant_service.get_tenant_limits.assert_called_once_with(mock_db, tenant_id)

    @pytest.mark.asyncio
    async def test_get_tenant_limits_not_found(
        self,
        mock_db,
        current_user_with_tenant,
        mock_tenant_service,
    ):
        """Test get tenant limits when tenant doesn't exist."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        mock_tenant_service.get_tenant = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant .* not found"):
            await get_tenant_limits(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_get_tenant_limits_suspended(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_suspended,
        mock_tenant_service,
    ):
        """Test get tenant limits when tenant is suspended."""
        tenant_id = str(current_user_with_tenant["tenant_id"])
        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_suspended)

        with pytest.raises(ForbiddenException, match="Tenant is suspended"):
            await get_tenant_limits(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_get_tenant_limits_not_configured(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test get tenant limits when limits not configured."""
        tenant_id = str(current_user_with_tenant["tenant_id"])

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.get_tenant_limits = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant limits not configured"):
            await get_tenant_limits(
                _request=Mock(),
                db=mock_db,
                current_user=current_user_with_tenant,
                tenant_id=tenant_id,
                _rate_limit=Mock(),
            )

    @pytest.mark.asyncio
    async def test_get_tenant_limits_custom_limits(
        self,
        mock_db,
        current_user_with_tenant,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test get tenant limits with custom limits."""
        tenant_id = str(current_user_with_tenant["tenant_id"])

        custom_limits = TenantLimitsRead(
            tenant_id=uuid.UUID(tenant_id),
            max_monitors=1000,  # Custom high limit
            max_networks=100,
            max_triggers=2000,
            max_api_calls_per_hour=1000000,
            max_storage_gb=1000.0,
            max_concurrent_operations=50,
            current_monitors=100,
            current_networks=20,
            current_triggers=200,
            current_storage_gb=50.0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.get_tenant_limits = AsyncMock(return_value=custom_limits)

        result = await get_tenant_limits(
            _request=Mock(),
            db=mock_db,
            current_user=current_user_with_tenant,
            tenant_id=tenant_id,
            _rate_limit=Mock(),
        )

        assert result.max_monitors == 1000
        assert result.max_api_calls_per_hour == 1000000
