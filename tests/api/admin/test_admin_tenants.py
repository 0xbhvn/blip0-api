"""
Comprehensive tests for admin tenant API endpoints.
Tests all CRUD operations, tenant management, and admin-specific features.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.api.admin.tenants import (
    activate_tenant,
    create_tenant,
    delete_tenant,
    get_tenant,
    list_tenants,
    suspend_tenant,
    update_tenant,
)
from src.app.core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
)
from src.app.schemas.tenant import (
    TenantActivateRequest,
    TenantAdminPagination,
    TenantAdminRead,
    TenantCreate,
    TenantLimitsRead,
    TenantRead,
    TenantSuspendRequest,
    TenantUpdate,
    TenantWithLimits,
)


@pytest.fixture
def sample_tenant_id():
    """Generate a sample tenant ID."""
    return uuid.uuid4()


@pytest.fixture
def sample_admin_user(sample_tenant_id):
    """Mock admin user."""
    return {
        "id": 1,
        "username": "admin_user",
        "email": "admin@example.com",
        "tenant_id": sample_tenant_id,
        "is_superuser": True,
    }


@pytest.fixture
def sample_non_admin_user(sample_tenant_id):
    """Mock non-admin user."""
    return {
        "id": 2,
        "username": "regular_user",
        "email": "user@example.com",
        "tenant_id": sample_tenant_id,
        "is_superuser": False,
    }


@pytest.fixture
def sample_tenant_create():
    """Generate sample tenant creation data."""
    return TenantCreate(
        name="Test Company",
        slug="test-company",
        plan="starter",
        settings={"timezone": "UTC"},
    )


@pytest.fixture
def sample_tenant_read(sample_tenant_id):
    """Generate sample tenant read data."""
    return TenantRead(
        id=sample_tenant_id,
        name="Test Company",
        slug="test-company",
        plan="starter",
        status="active",
        settings={"timezone": "UTC"},
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def sample_tenant_with_limits(sample_tenant_id):
    """Generate sample tenant with limits data."""
    return TenantWithLimits(
        id=sample_tenant_id,
        name="Test Company",
        slug="test-company",
        plan="starter",
        status="active",
        settings={"timezone": "UTC"},
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        limits=TenantLimitsRead(
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
        ),
    )


@pytest.fixture
def sample_tenant_admin_read(sample_tenant_id):
    """Generate sample tenant admin read data."""
    return TenantAdminRead(
        id=sample_tenant_id,
        name="Test Company",
        slug="test-company",
        plan="starter",
        status="active",
        settings={"timezone": "UTC"},
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        limits=TenantLimitsRead(
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
        ),
        user_count=10,
        monitor_count=5,
        trigger_count=10,
        last_activity=None,
        suspended_at=None,
        suspension_reason=None,
    )


@pytest.fixture
def mock_tenant_service():
    """Mock tenant service."""
    with patch("src.app.api.admin.tenants.tenant_service") as mock_service:
        yield mock_service


@pytest.fixture
def mock_crud_tenant():
    """Mock crud_tenant."""
    with patch("src.app.crud.crud_tenant.crud_tenant") as mock_crud:
        yield mock_crud


class TestListTenants:
    """Test GET /admin/tenants endpoint."""

    @pytest.mark.asyncio
    async def test_list_tenants_success(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_admin_read,
        mock_tenant_service,
    ):
        """Test successful tenant listing with default pagination."""
        # Mock service response
        mock_tenant_service.list_all_tenants = AsyncMock(
            return_value=TenantAdminPagination(
                items=[sample_tenant_admin_read],
                total=1,
                page=1,
                size=50,
                pages=1,
            )
        )

        result = await list_tenants(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name=None,
            slug=None,
            plan=None,
            status=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["total"] == 1
        assert len(result["items"]) == 1
        mock_tenant_service.list_all_tenants.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tenants_with_filters(
        self,
        mock_db,
        sample_admin_user,
        mock_tenant_service,
    ):
        """Test tenant listing with all filters applied."""
        mock_tenant_service.list_all_tenants = AsyncMock(
            return_value=TenantAdminPagination(
                items=[], total=0, page=1, size=50, pages=0
            )
        )

        result = await list_tenants(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name="test",
            slug="test-slug",
            plan="starter",
            status="active",
            sort_field="name",
            sort_order="asc",
        )

        assert result["total"] == 0
        assert len(result["items"]) == 0

        # Verify filter was constructed correctly
        call_args = mock_tenant_service.list_all_tenants.call_args
        filters = call_args.kwargs["filters"]
        assert filters.name == "test"
        assert filters.slug == "test-slug"
        assert filters.plan == "starter"
        assert filters.status == "active"

    @pytest.mark.asyncio
    async def test_list_tenants_pagination(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_admin_read,
        mock_tenant_service,
    ):
        """Test tenant listing with custom pagination."""
        mock_tenant_service.list_all_tenants = AsyncMock(
            return_value=TenantAdminPagination(
                items=[sample_tenant_admin_read] * 10,
                total=100,
                page=2,
                size=10,
                pages=10,
            )
        )

        result = await list_tenants(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=2,
            size=10,
            name=None,
            slug=None,
            plan=None,
            status=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["total"] == 100
        assert result["page"] == 2
        assert result["size"] == 10
        assert result["pages"] == 10

    @pytest.mark.asyncio
    async def test_list_tenants_empty_result(
        self,
        mock_db,
        sample_admin_user,
        mock_tenant_service,
    ):
        """Test tenant listing with empty result."""
        mock_tenant_service.list_all_tenants = AsyncMock(
            return_value=TenantAdminPagination(
                items=[], total=0, page=1, size=50, pages=0
            )
        )

        result = await list_tenants(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name="nonexistent",
            slug=None,
            plan=None,
            status=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["total"] == 0
        assert len(result["items"]) == 0
        assert result["pages"] == 0


class TestCreateTenant:
    """Test POST /admin/tenants endpoint."""

    @pytest.mark.asyncio
    async def test_create_tenant_success(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_create,
        sample_tenant_with_limits,
        mock_crud_tenant,
    ):
        """Test successful tenant creation with default limits."""
        mock_crud_tenant.create_with_limits = AsyncMock(
            return_value=sample_tenant_with_limits
        )

        result = await create_tenant(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            tenant_in=sample_tenant_create,
        )

        assert result == sample_tenant_with_limits
        mock_crud_tenant.create_with_limits.assert_called_once_with(
            db=mock_db, obj_in=sample_tenant_create
        )
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_tenant_duplicate_name(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_create,
        mock_crud_tenant,
    ):
        """Test tenant creation with duplicate name."""
        from sqlalchemy.exc import IntegrityError

        mock_crud_tenant.create_with_limits = AsyncMock(
            side_effect=IntegrityError("duplicate key", None, Exception("duplicate key error"))
        )

        with pytest.raises(DuplicateValueException) as exc_info:
            await create_tenant(
                _request=Mock(),
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
                tenant_in=sample_tenant_create,
            )

        assert "already exists" in str(exc_info.value)
        mock_db.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_tenant_all_plans(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_with_limits,
        mock_crud_tenant,
    ):
        """Test tenant creation with different plan types."""
        plans = ["free", "starter", "pro", "enterprise"]

        for plan in plans:
            tenant_create = TenantCreate(
                name=f"Test {plan}",
                slug=f"test-{plan}",
                plan=plan,
            )

            mock_crud_tenant.create_with_limits = AsyncMock(
                return_value=sample_tenant_with_limits
            )

            result = await create_tenant(
                _request=Mock(),
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
                tenant_in=tenant_create,
            )

            assert result == sample_tenant_with_limits

    @pytest.mark.asyncio
    async def test_create_tenant_database_error(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_create,
        mock_crud_tenant,
    ):
        """Test tenant creation with general database error."""
        mock_crud_tenant.create_with_limits = AsyncMock(
            side_effect=Exception("Database connection error")
        )

        with pytest.raises(BadRequestException) as exc_info:
            await create_tenant(
                _request=Mock(),
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
                tenant_in=sample_tenant_create,
            )

        assert "Failed to create tenant" in str(exc_info.value)
        mock_db.rollback.assert_called_once()


class TestGetTenant:
    """Test GET /admin/tenants/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_tenant_success(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        sample_tenant_read,
        sample_tenant_admin_read,
        mock_tenant_service,
    ):
        """Test successful single tenant retrieval with admin details."""
        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.get_tenant_limits = AsyncMock(
            return_value=sample_tenant_admin_read.limits
        )

        # Mock database queries for counts
        mock_execute = AsyncMock()
        mock_execute.scalar = Mock(return_value=10)
        mock_db.execute = AsyncMock(return_value=mock_execute)

        result = await get_tenant(
            _request=Mock(),
            tenant_id=str(sample_tenant_id),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.id == sample_tenant_id
        assert result.user_count == 10
        assert result.monitor_count == 10
        assert result.trigger_count == 10
        mock_tenant_service.get_tenant.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_tenant_invalid_id(
        self,
        mock_db,
        sample_admin_user,
    ):
        """Test get tenant with invalid UUID format."""
        with pytest.raises(BadRequestException, match="Invalid tenant ID format"):
            await get_tenant(
                _request=Mock(),
                tenant_id="invalid-uuid",
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )

    @pytest.mark.asyncio
    async def test_get_tenant_not_found(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        mock_tenant_service,
    ):
        """Test get tenant when tenant doesn't exist."""
        mock_tenant_service.get_tenant = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant .* not found"):
            await get_tenant(
                _request=Mock(),
                tenant_id=str(sample_tenant_id),
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )


class TestUpdateTenant:
    """Test PUT /admin/tenants/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_tenant_success(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test successful tenant update."""
        tenant_update = TenantUpdate(
            slug="test-company",
            name="Updated Company",
        )

        updated_tenant = TenantRead(
            **{**sample_tenant_read.model_dump(), "name": "Updated Company"}
        )
        mock_tenant_service.update_tenant = AsyncMock(return_value=updated_tenant)

        result = await update_tenant(
            _request=Mock(),
            tenant_id=str(sample_tenant_id),
            tenant_update=tenant_update,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.name == "Updated Company"
        mock_tenant_service.update_tenant.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_tenant_invalid_id(
        self,
        mock_db,
        sample_admin_user,
    ):
        """Test update tenant with invalid UUID."""
        tenant_update = TenantUpdate(slug="test-company", name="Updated")

        with pytest.raises(BadRequestException, match="Invalid tenant ID format"):
            await update_tenant(
                _request=Mock(),
                tenant_id="invalid-uuid",
                tenant_update=tenant_update,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )

    @pytest.mark.asyncio
    async def test_update_tenant_not_found(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        mock_tenant_service,
    ):
        """Test update tenant when tenant doesn't exist."""
        tenant_update = TenantUpdate(slug="test-company", name="Updated")
        mock_tenant_service.update_tenant = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant .* not found"):
            await update_tenant(
                _request=Mock(),
                tenant_id=str(sample_tenant_id),
                tenant_update=tenant_update,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )

    @pytest.mark.asyncio
    async def test_update_tenant_duplicate_name(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        mock_tenant_service,
    ):
        """Test update tenant with duplicate name."""
        from sqlalchemy.exc import IntegrityError

        tenant_update = TenantUpdate(slug="test-company", name="Existing Company")
        mock_tenant_service.update_tenant = AsyncMock(
            side_effect=IntegrityError("duplicate key", None, Exception("duplicate key error"))
        )

        with pytest.raises(DuplicateValueException):
            await update_tenant(
                _request=Mock(),
                tenant_id=str(sample_tenant_id),
                tenant_update=tenant_update,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )

        mock_db.rollback.assert_called_once()


class TestDeleteTenant:
    """Test DELETE /admin/tenants/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_tenant_soft_delete(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test successful soft delete of tenant."""
        # Use a different tenant ID for the target
        target_tenant_id = uuid.uuid4()
        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.delete_tenant = AsyncMock(return_value=True)

        await delete_tenant(
            _request=Mock(),
            tenant_id=str(target_tenant_id),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            is_hard_delete=False,
        )

        mock_tenant_service.delete_tenant.assert_called_once_with(
            db=mock_db, tenant_id=target_tenant_id, is_hard_delete=False
        )
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_tenant_hard_delete(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test hard delete of tenant."""
        target_tenant_id = uuid.uuid4()
        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.delete_tenant = AsyncMock(return_value=True)

        await delete_tenant(
            _request=Mock(),
            tenant_id=str(target_tenant_id),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            is_hard_delete=True,
        )

        mock_tenant_service.delete_tenant.assert_called_once_with(
            db=mock_db, tenant_id=target_tenant_id, is_hard_delete=True
        )

    @pytest.mark.asyncio
    async def test_delete_own_tenant_forbidden(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test admin cannot delete their own tenant."""
        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)

        with pytest.raises(ForbiddenException, match="Cannot delete your own tenant"):
            await delete_tenant(
                _request=Mock(),
                tenant_id=str(sample_tenant_id),  # Same as admin's tenant
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
                is_hard_delete=False,
            )

    @pytest.mark.asyncio
    async def test_delete_tenant_not_found(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        mock_tenant_service,
    ):
        """Test delete tenant when tenant doesn't exist."""
        mock_tenant_service.get_tenant = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant .* not found"):
            await delete_tenant(
                _request=Mock(),
                tenant_id=str(uuid.uuid4()),
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
                is_hard_delete=False,
            )

    @pytest.mark.asyncio
    async def test_delete_tenant_failed(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test delete tenant when deletion fails."""
        target_tenant_id = uuid.uuid4()
        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        mock_tenant_service.delete_tenant = AsyncMock(return_value=False)

        with pytest.raises(BadRequestException, match="Failed to delete tenant"):
            await delete_tenant(
                _request=Mock(),
                tenant_id=str(target_tenant_id),
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
                is_hard_delete=False,
            )


class TestSuspendTenant:
    """Test POST /admin/tenants/{id}/suspend endpoint."""

    @pytest.mark.asyncio
    async def test_suspend_tenant_success(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test successful tenant suspension."""
        target_tenant_id = uuid.uuid4()
        suspend_request = TenantSuspendRequest(
            reason="Policy violation", notify_users=True
        )

        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)
        suspended_tenant = TenantRead(
            **{**sample_tenant_read.model_dump(), "status": "suspended"}
        )
        mock_tenant_service.suspend_tenant = AsyncMock(return_value=suspended_tenant)

        result = await suspend_tenant(
            _request=Mock(),
            tenant_id=str(target_tenant_id),
            suspend_request=suspend_request,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.status == "suspended"
        mock_tenant_service.suspend_tenant.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_suspend_already_suspended(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test suspending an already suspended tenant."""
        suspend_request = TenantSuspendRequest(reason="Test")
        suspended_tenant = TenantRead(
            **{**sample_tenant_read.model_dump(), "status": "suspended"}
        )
        mock_tenant_service.get_tenant = AsyncMock(return_value=suspended_tenant)

        with pytest.raises(BadRequestException, match="already suspended"):
            await suspend_tenant(
                _request=Mock(),
                tenant_id=str(uuid.uuid4()),
                suspend_request=suspend_request,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )

    @pytest.mark.asyncio
    async def test_suspend_own_tenant_forbidden(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_id,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test admin cannot suspend their own tenant."""
        suspend_request = TenantSuspendRequest(reason="Test")
        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)

        with pytest.raises(ForbiddenException, match="Cannot suspend your own tenant"):
            await suspend_tenant(
                _request=Mock(),
                tenant_id=str(sample_tenant_id),  # Same as admin's tenant
                suspend_request=suspend_request,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )

    @pytest.mark.asyncio
    async def test_suspend_tenant_not_found(
        self,
        mock_db,
        sample_admin_user,
        mock_tenant_service,
    ):
        """Test suspend tenant when tenant doesn't exist."""
        suspend_request = TenantSuspendRequest(reason="Test")
        mock_tenant_service.get_tenant = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant .* not found"):
            await suspend_tenant(
                _request=Mock(),
                tenant_id=str(uuid.uuid4()),
                suspend_request=suspend_request,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )


class TestActivateTenant:
    """Test POST /admin/tenants/{id}/activate endpoint."""

    @pytest.mark.asyncio
    async def test_activate_tenant_success(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test successful tenant activation."""
        activate_request = TenantActivateRequest(
            reason="Issue resolved", notify_users=True
        )

        suspended_tenant = TenantRead(
            **{**sample_tenant_read.model_dump(), "status": "suspended"}
        )
        mock_tenant_service.get_tenant = AsyncMock(return_value=suspended_tenant)

        activated_tenant = TenantRead(
            **{**sample_tenant_read.model_dump(), "status": "active"}
        )
        mock_tenant_service.activate_tenant = AsyncMock(return_value=activated_tenant)

        result = await activate_tenant(
            _request=Mock(),
            tenant_id=str(uuid.uuid4()),
            activate_request=activate_request,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.status == "active"
        mock_tenant_service.activate_tenant.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_activate_already_active(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test activating an already active tenant."""
        activate_request = TenantActivateRequest(reason="Test")
        mock_tenant_service.get_tenant = AsyncMock(return_value=sample_tenant_read)

        with pytest.raises(BadRequestException, match="already active"):
            await activate_tenant(
                _request=Mock(),
                tenant_id=str(uuid.uuid4()),
                activate_request=activate_request,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )

    @pytest.mark.asyncio
    async def test_activate_tenant_not_found(
        self,
        mock_db,
        sample_admin_user,
        mock_tenant_service,
    ):
        """Test activate tenant when tenant doesn't exist."""
        activate_request = TenantActivateRequest(reason="Test")
        mock_tenant_service.get_tenant = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Tenant .* not found"):
            await activate_tenant(
                _request=Mock(),
                tenant_id=str(uuid.uuid4()),
                activate_request=activate_request,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )

    @pytest.mark.asyncio
    async def test_activate_tenant_failed(
        self,
        mock_db,
        sample_admin_user,
        sample_tenant_read,
        mock_tenant_service,
    ):
        """Test activate tenant when activation fails."""
        activate_request = TenantActivateRequest(reason="Test")
        suspended_tenant = TenantRead(
            **{**sample_tenant_read.model_dump(), "status": "suspended"}
        )
        mock_tenant_service.get_tenant = AsyncMock(return_value=suspended_tenant)
        mock_tenant_service.activate_tenant = AsyncMock(return_value=None)

        with pytest.raises(BadRequestException, match="Failed to activate tenant"):
            await activate_tenant(
                _request=Mock(),
                tenant_id=str(uuid.uuid4()),
                activate_request=activate_request,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )
