"""
Tests for admin network API endpoints.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.api.admin.networks import (
    create_network,
    delete_network,
    get_network,
    list_networks,
    update_network,
    validate_network,
)
from src.app.core.exceptions.http_exceptions import (
    BadRequestException,
    DuplicateValueException,
    NotFoundException,
)
from src.app.schemas.network import (
    NetworkCreateAdmin,
    NetworkRead,
    NetworkUpdate,
)


@pytest.fixture
def sample_network_id():
    """Generate a sample network ID."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_admin_user():
    """Mock admin user."""
    return {
        "id": 1,
        "username": "admin",
        "email": "admin@example.com",
        "is_superuser": True,
        "tenant_id": uuid.uuid4(),
    }


@pytest.fixture
def sample_network_create():
    """Generate sample network creation data."""
    return NetworkCreateAdmin(
        name="Test Ethereum Network",
        slug="test-ethereum",
        network_type="EVM",
        block_time_ms=12000,
        description="Test EVM network for testing",
        network_passphrase=None,  # EVM networks don't have network passphrase
        chain_id=1337,
        rpc_urls=[
            {"url": "https://test-rpc.example.com", "type_": "primary", "weight": 100}
        ],
        confirmation_blocks=2,
        cron_schedule="*/5 * * * * *",
        max_past_blocks=50,
        store_blocks=False,
    )


@pytest.fixture
def sample_network_read(sample_network_id):
    """Generate sample network read data."""
    return NetworkRead(
        id=uuid.UUID(sample_network_id),
        tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        name="Test Ethereum Network",
        slug="test-ethereum",
        network_type="EVM",
        block_time_ms=12000,
        description="Test EVM network for testing",
        network_passphrase=None,  # EVM networks don't have network passphrase
        chain_id=1337,
        rpc_urls=[
            {"url": "https://test-rpc.example.com", "type_": "primary", "weight": 100}
        ],
        confirmation_blocks=2,
        cron_schedule="*/5 * * * * *",
        max_past_blocks=50,
        store_blocks=False,
        active=True,
        validated=False,
        validation_errors=None,
        last_validated_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def mock_network_service():
    """Mock network service."""
    # Patch the service module import path, not the endpoint import
    with patch("src.app.services.network_service.network_service") as mock_service:
        # Also patch it in the endpoint module to ensure both import paths are covered
        with patch("src.app.api.admin.networks.network_service", mock_service):
            yield mock_service


@pytest.fixture
def mock_crud_tenant():
    """Mock crud_tenant for admin endpoints."""
    with patch("src.app.crud.crud_tenant.crud_tenant") as mock_crud:
        # Mock platform tenant exists
        mock_crud.get = AsyncMock(return_value={"id": "11111111-1111-1111-1111-111111111111"})
        mock_crud.create = AsyncMock()
        yield mock_crud


class TestListNetworks:
    """Test GET /admin/networks endpoint."""

    @pytest.mark.asyncio
    async def test_list_networks_success(
        self,
        mock_db,
        sample_admin_user,
        sample_network_read,
        mock_network_service,
    ):
        """Test successful network listing with pagination."""
        # Mock service response - service returns a dict
        mock_result = {
            "items": [sample_network_read],
            "total": 1,
            "page": 1,
            "size": 50,
            "pages": 1,
        }

        mock_network_service.list_networks = AsyncMock(
            return_value=mock_result
        )

        result = await list_networks(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name=None,
            slug=None,
            network_type=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["total"] == 1
        assert len(result["items"]) == 1
        mock_network_service.list_networks.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_networks_with_filters(
        self,
        mock_db,
        sample_admin_user,
        mock_network_service,
    ):
        """Test network listing with filters."""
        # Mock service response - service returns a dict
        mock_result = {
            "items": [],
            "total": 0,
            "page": 1,
            "size": 50,
            "pages": 0
        }

        mock_network_service.list_networks = AsyncMock(
            return_value=mock_result
        )

        result = await list_networks(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name="test",
            slug="test-slug",
            network_type="EVM",
            active=True,
            validated=False,
            sort_field="name",
            sort_order="asc",
        )

        assert result["total"] == 0
        assert len(result["items"]) == 0
        mock_network_service.list_networks.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_networks_empty(
        self,
        mock_db,
        sample_admin_user,
        mock_network_service,
    ):
        """Test listing networks when database is empty."""
        # Mock service response - service returns a dict
        mock_result = {
            "items": [],
            "total": 0,
            "page": 1,
            "size": 50,
            "pages": 0
        }

        mock_network_service.list_networks = AsyncMock(
            return_value=mock_result
        )

        result = await list_networks(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name=None,
            slug=None,
            network_type=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["total"] == 0
        assert result["items"] == []
        assert result["pages"] == 0

    @pytest.mark.asyncio
    async def test_list_networks_with_pagination(
        self,
        mock_db,
        sample_admin_user,
        sample_network_read,
        mock_network_service,
    ):
        """Test network listing with pagination."""
        # Create multiple networks for pagination
        networks = [sample_network_read for _ in range(5)]

        # Mock service response - service returns a dict
        mock_result = {
            "items": networks[:2],  # Return only 2 items for page 2
            "total": 5,
            "page": 2,
            "size": 2,
            "pages": 3,
        }

        mock_network_service.list_networks = AsyncMock(
            return_value=mock_result
        )

        result = await list_networks(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=2,
            size=2,
            name=None,
            slug=None,
            network_type=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
        )

        assert result["total"] == 5
        assert len(result["items"]) == 2
        assert result["page"] == 2
        assert result["pages"] == 3

    @pytest.mark.asyncio
    async def test_list_networks_with_sorting(
        self,
        mock_db,
        sample_admin_user,
        sample_network_read,
        mock_network_service,
    ):
        """Test network listing with different sorting options."""
        # Mock service response - service returns a dict
        mock_result = {
            "items": [sample_network_read],
            "total": 1,
            "page": 1,
            "size": 50,
            "pages": 1,
        }

        mock_network_service.list_networks = AsyncMock(
            return_value=mock_result
        )

        # Test sorting by name ascending
        result = await list_networks(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name=None,
            slug=None,
            network_type=None,
            active=None,
            validated=None,
            sort_field="name",
            sort_order="asc",
        )

        assert result["total"] == 1
        # Verify service was called with correct arguments
        mock_network_service.list_networks.assert_called_once()
        call_args = mock_network_service.list_networks.call_args
        assert call_args[1]['db'] == mock_db
        assert call_args[1]['page'] == 1
        assert call_args[1]['size'] == 50
        # Check filters object
        filters = call_args[1]['filters']
        assert filters.name is None
        assert filters.slug is None
        assert filters.network_type is None
        assert filters.active is None
        assert filters.validated is None
        # Check sort object
        sort = call_args[1]['sort']
        assert sort.field == "name"
        assert sort.order == "asc"

    @pytest.mark.asyncio
    async def test_list_networks_non_admin(
        self,
        mock_db,
        mock_network_service,
    ):
        """Test network listing with non-admin user."""
        non_admin_user = {
            "id": 2,
            "username": "user",
            "email": "user@example.com",
            "is_superuser": False,
            "tenant_id": uuid.uuid4(),
        }

        # Mock service response - service returns a dict
        mock_result = {
            "items": [],
            "total": 0,
            "page": 1,
            "size": 50,
            "pages": 0
        }

        mock_network_service.list_networks = AsyncMock(
            return_value=mock_result
        )

        result = await list_networks(
            _request=Mock(),
            db=mock_db,
            admin_user=non_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name=None,
            slug=None,
            network_type=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
        )

        # Non-admin users should still get results but potentially filtered
        assert "items" in result
        mock_network_service.list_networks.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_networks_unauthorized(
        self,
        mock_db,
        mock_network_service,
    ):
        """Test network listing without authentication."""
        # This test would normally be handled at the router level
        # In unit tests, we simulate by passing a dummy user but service raises exception
        mock_network_service.list_networks = AsyncMock(
            side_effect=Exception("Unauthorized")
        )

        # Create a dummy user to avoid type errors, but expect service to raise exception
        dummy_user = {"id": 0, "username": "none", "email": "none@test.com", "is_superuser": False}

        with pytest.raises(Exception, match="Unauthorized"):
            await list_networks(
                _request=Mock(),
                db=mock_db,
                admin_user=dummy_user,  # Use dummy instead of None
                _rate_limit=None,
                page=1,
                size=50,
                name=None,
                slug=None,
                network_type=None,
                active=None,
                validated=None,
                sort_field="created_at",
                sort_order="desc",
            )


class TestCreateNetwork:
    """Test POST /admin/networks endpoint."""

    @pytest.mark.asyncio
    async def test_create_network_success(
        self,
        mock_db,
        sample_admin_user,
        sample_network_create,
        sample_network_read,
        mock_network_service,
        mock_crud_tenant,
    ):
        """Test successful network creation."""
        # Mock service response
        mock_network_service.create_network = AsyncMock(
            return_value=sample_network_read
        )

        result = await create_network(
            network_in=sample_network_create,
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.name == sample_network_read.name
        assert result.slug == sample_network_read.slug
        assert result.network_type == sample_network_read.network_type
        assert result.active is True
        assert result.validated is False
        mock_network_service.create_network.assert_called_once()


    @pytest.mark.asyncio
    async def test_create_network_duplicate_slug(
        self,
        mock_db,
        sample_admin_user,
        sample_network_create,
        mock_network_service,
        mock_crud_tenant,
    ):
        """Test creating a network with duplicate slug."""
        # Mock service to raise duplicate exception
        mock_network_service.create_network = AsyncMock(
            side_effect=DuplicateValueException(
                f"Network with slug '{sample_network_create.slug}' already exists"
            )
        )

        with pytest.raises(DuplicateValueException, match="already exists"):
            await create_network(
                network_in=sample_network_create,
                _request=Mock(),
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )

    @pytest.mark.asyncio
    async def test_create_network_invalid_type(
        self,
        mock_db,
        sample_admin_user,
        mock_network_service,
        mock_crud_tenant,
    ):
        """Test creating a network with invalid network type."""

        # Try to create with invalid network type - this would be caught by Pydantic

        # This would normally raise a ValidationError at the schema level
        # In a mock test, we simulate the service rejecting invalid data
        mock_network_service.create_network = AsyncMock(
            side_effect=ValueError("Invalid network type: INVALID_TYPE")
        )

        # Create a network with the valid schema but mock service rejects it
        network_in = NetworkCreateAdmin(
            name="Test Network",
            slug="test-network",
            network_type="EVM",  # Valid for schema
            description="Test network description",
            network_passphrase=None,  # EVM networks don't have network passphrase
            block_time_ms=12000,
            chain_id=1,
            rpc_urls=[{"url": "https://test.com", "type_": "primary", "weight": 100}],
        )

        with pytest.raises(BadRequestException, match="Failed to create network"):
            await create_network(
                network_in=network_in,
                _request=Mock(),
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )


class TestGetNetwork:
    """Test GET /admin/networks/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_network_success(
        self,
        mock_db,
        sample_admin_user,
        sample_network_id,
        sample_network_read,
        mock_network_service,
    ):
        """Test successful network retrieval."""
        # Mock service response
        mock_network_service.get_network = AsyncMock(
            return_value=sample_network_read
        )

        result = await get_network(
            _request=Mock(),
            network_id=sample_network_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.id == sample_network_read.id
        assert result.name == sample_network_read.name
        mock_network_service.get_network.assert_called_once_with(
            db=mock_db,
            network_id=sample_network_id,
        )


    @pytest.mark.asyncio
    async def test_get_network_not_found(
        self,
        mock_db,
        sample_admin_user,
        sample_network_id,
        mock_network_service,
    ):
        """Test getting a non-existent network."""
        # Mock service to raise not found exception
        mock_network_service.get_network = AsyncMock(
            side_effect=NotFoundException("Network not found")
        )

        with pytest.raises(NotFoundException, match="Network not found"):
            await get_network(
                _request=Mock(),
                network_id=sample_network_id,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )


class TestUpdateNetwork:
    """Test PUT /admin/networks/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_network_success(
        self,
        mock_db,
        sample_admin_user,
        sample_network_id,
        sample_network_read,
        mock_network_service,
    ):
        """Test successful network update."""
        # Mock updated data
        updated_network = sample_network_read
        updated_network.name = "Updated Test Network"
        updated_network.description = "Updated description"
        updated_network.confirmation_blocks = 5

        # Mock service response
        mock_network_service.update_network = AsyncMock(
            return_value=updated_network
        )

        update_data = NetworkUpdate(
            name="Updated Test Network",
            slug="updated-test-network",
            description="Updated description",
            network_passphrase=None,  # EVM networks don't have network passphrase
            block_time_ms=15000,
            confirmation_blocks=5,
            max_past_blocks=100,
        )

        result = await update_network(
            _request=Mock(),
            network_id=sample_network_id,
            network_update=update_data,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.name == "Updated Test Network"
        assert result.description == "Updated description"
        assert result.confirmation_blocks == 5
        mock_network_service.update_network.assert_called_once()


    @pytest.mark.asyncio
    async def test_update_network_duplicate_slug(
        self,
        mock_db,
        sample_admin_user,
        sample_network_id,
        mock_network_service,
    ):
        """Test updating network to duplicate slug."""
        # Mock service to raise duplicate exception
        mock_network_service.update_network = AsyncMock(
            side_effect=DuplicateValueException(
                "Network with slug 'existing-slug' already exists"
            )
        )

        update_data = NetworkUpdate(
            name="Updated Network",
            slug="existing-slug",
            description="Updated description",
            network_passphrase=None,  # EVM networks don't have network passphrase
            block_time_ms=12000,
            confirmation_blocks=2,
            max_past_blocks=50,
        )

        with pytest.raises(BadRequestException, match="Failed to update network"):
            await update_network(
                _request=Mock(),
                network_id=sample_network_id,
                network_update=update_data,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )


class TestDeleteNetwork:
    """Test DELETE /admin/networks/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_network_soft(
        self,
        mock_db,
        sample_admin_user,
        sample_network_id,
        sample_network_read,
        mock_network_service,
    ):
        """Test soft deleting a network."""
        # Mock get_network for existence check in delete endpoint
        mock_network_service.get_network = AsyncMock(
            return_value=sample_network_read
        )

        # Mock service response
        mock_network_service.delete_network = AsyncMock(return_value=True)

        result = await delete_network(
            _request=Mock(),
            network_id=sample_network_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            hard_delete=False,
        )

        assert result is None
        mock_network_service.delete_network.assert_called_once_with(
            db=mock_db,
            network_id=sample_network_id,
            is_hard_delete=False,
        )


    @pytest.mark.asyncio
    async def test_delete_network_hard(
        self,
        mock_db,
        sample_admin_user,
        sample_network_id,
        sample_network_read,
        mock_network_service,
    ):
        """Test hard deleting a network."""
        # Mock get_network for existence check in delete endpoint
        mock_network_service.get_network = AsyncMock(
            return_value=sample_network_read
        )

        # Mock service response
        mock_network_service.delete_network = AsyncMock(return_value=True)

        result = await delete_network(
            _request=Mock(),
            network_id=sample_network_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            hard_delete=True,
        )

        assert result is None
        mock_network_service.delete_network.assert_called_once_with(
            db=mock_db,
            network_id=sample_network_id,
            is_hard_delete=True,
        )


    @pytest.mark.asyncio
    async def test_delete_network_not_found(
        self,
        mock_db,
        sample_admin_user,
        sample_network_id,
        mock_network_service,
    ):
        """Test deleting non-existent network."""
        # Mock get_network to return None (network not found)
        mock_network_service.get_network = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Network .* not found"):
            await delete_network(
                _request=Mock(),
                network_id=sample_network_id,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
                hard_delete=False,
            )


class TestValidateNetwork:
    """Test POST /admin/networks/{id}/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_network_success(
        self,
        mock_db,
        sample_admin_user,
        sample_network_id,
        sample_network_read,
        mock_network_service,
    ):
        """Test successful network validation."""
        # Mock get_network for existence check in validate endpoint
        mock_network_service.get_network = AsyncMock(
            return_value=sample_network_read
        )

        # Note: validate_network doesn't actually call network_service.validate_network
        # The endpoint returns a mock validation result directly
        # No need to mock the service method since it doesn't exist

        result = await validate_network(
            _request=Mock(),
            network_id=sample_network_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.is_valid is True
        assert result.errors == []
        # Note: No service call to assert since validate_network doesn't call the service
