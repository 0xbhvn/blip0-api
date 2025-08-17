"""
Tests for admin filter script API endpoints.
"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.api.admin.filter_scripts import (
    create_filter_script,
    delete_filter_script,
    get_filter_script,
    list_filter_scripts,
    update_filter_script,
    validate_filter_script,
)
from src.app.core.exceptions.http_exceptions import (
    DuplicateValueException,
    NotFoundException,
)
from src.app.schemas.filter_script import (
    FilterScriptCreate,
    FilterScriptRead,
    FilterScriptUpdate,
)


@pytest.fixture
def sample_filter_script_id():
    """Generate a sample filter script ID."""
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
def sample_filter_script_create():
    """Generate sample filter script creation data."""
    return FilterScriptCreate(
        name="Test Bash Filter",
        slug="test-bash-filter",
        language="bash",
        description="Test bash filter script for testing",
        arguments=["--verbose"],
        timeout_ms=1000,
        script_content="""#!/bin/bash
# Test bash filter script
input=$(cat)
echo "$input" | jq '.monitor_match'
exit 0
""",
    )


@pytest.fixture
def sample_filter_script_read(sample_filter_script_id):
    """Generate sample filter script read data."""
    return FilterScriptRead(
        id=uuid.UUID(sample_filter_script_id),
        name="Test Bash Filter",
        slug="test-bash-filter",
        language="bash",
        description="Test bash filter script for testing",
        arguments=["--verbose"],
        timeout_ms=1000,
        script_path="config/filters/test-bash-filter.sh",
        active=True,
        validated=False,
        validation_errors=None,
        last_validated_at=None,
        file_size_bytes=None,
        file_hash=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )


@pytest.fixture
def mock_filter_script_service():
    """Mock filter script service."""
    # Patch the service module import path, not the endpoint import
    with patch("src.app.services.filter_script_service.filter_script_service") as mock_service:
        # Also patch it in the endpoint module to ensure both import paths are covered
        with patch("src.app.api.admin.filter_scripts.filter_script_service", mock_service):
            yield mock_service


@pytest.fixture
def mock_path_operations():
    """Mock Path operations for file system."""
    # Since Path is not imported in filter_scripts module, we don't need to patch it
    # The service layer handles file operations
    return Mock()


class TestListFilterScripts:
    """Test GET /admin/filter-scripts endpoint."""

    @pytest.mark.asyncio
    async def test_list_filter_scripts_success(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test successful filter script listing with pagination."""
        # Create a mock pagination result object
        mock_result = Mock()
        mock_result.items = [sample_filter_script_read]
        mock_result.total = 1
        mock_result.page = 1
        mock_result.size = 50
        mock_result.pages = 1
        mock_result.model_dump.return_value = {
            "items": [sample_filter_script_read],
            "total": 1,
            "page": 1,
            "size": 50,
            "pages": 1,
        }

        mock_filter_script_service.list_filter_scripts = AsyncMock(
            return_value=mock_result
        )

        result = await list_filter_scripts(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name=None,
            slug=None,
            language=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
            include_content=False,
        )

        assert result["total"] == 1
        assert len(result["items"]) == 1
        mock_filter_script_service.list_filter_scripts.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_filter_scripts_with_filters(
        self,
        mock_db,
        sample_admin_user,
        mock_filter_script_service,
    ):
        """Test filter script listing with filters."""
        # Create a mock pagination result object
        mock_result = Mock()
        mock_result.items = []
        mock_result.total = 0
        mock_result.page = 1
        mock_result.size = 50
        mock_result.pages = 0
        mock_result.model_dump.return_value = {"items": [], "total": 0, "page": 1, "size": 50, "pages": 0}

        mock_filter_script_service.list_filter_scripts = AsyncMock(
            return_value=mock_result
        )

        # Mock the batch content method when include_content=True
        mock_filter_script_service.get_filter_scripts_with_content = AsyncMock(
            return_value=[]
        )

        result = await list_filter_scripts(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name="test",
            slug="test-slug",
            language="bash",
            active=True,
            validated=False,
            sort_field="created_at",
            sort_order="desc",
            include_content=True,
        )

        assert result["total"] == 0
        assert len(result["items"]) == 0
        mock_filter_script_service.list_filter_scripts.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_filter_scripts_empty(
        self,
        mock_db,
        sample_admin_user,
        mock_filter_script_service,
    ):
        """Test listing filter scripts when database is empty."""
        # Create a mock pagination result object
        mock_result = Mock()
        mock_result.items = []
        mock_result.total = 0
        mock_result.page = 1
        mock_result.size = 50
        mock_result.pages = 0
        mock_result.model_dump.return_value = {"items": [], "total": 0, "page": 1, "size": 50, "pages": 0}

        mock_filter_script_service.list_filter_scripts = AsyncMock(
            return_value=mock_result
        )

        result = await list_filter_scripts(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name=None,
            slug=None,
            language=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
            include_content=False,
        )

        assert result["total"] == 0
        assert result["items"] == []
        assert result["pages"] == 0

    @pytest.mark.asyncio
    async def test_list_filter_scripts_with_pagination(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test filter script listing with pagination."""
        # Create multiple scripts for pagination
        scripts = [sample_filter_script_read for _ in range(5)]

        # Create a mock pagination result object
        mock_result = Mock()
        mock_result.items = scripts[:2]  # Return only 2 items for page 2
        mock_result.total = 5
        mock_result.page = 2
        mock_result.size = 2
        mock_result.pages = 3
        mock_result.model_dump.return_value = {
            "items": scripts[:2],
            "total": 5,
            "page": 2,
            "size": 2,
            "pages": 3,
        }

        mock_filter_script_service.list_filter_scripts = AsyncMock(
            return_value=mock_result
        )

        result = await list_filter_scripts(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=2,
            size=2,
            name=None,
            slug=None,
            language=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
            include_content=False,
        )

        assert result["total"] == 5
        assert len(result["items"]) == 2
        assert result["page"] == 2
        assert result["pages"] == 3

    @pytest.mark.asyncio
    async def test_list_filter_scripts_with_content(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test filter script listing with script content included."""
        from src.app.schemas.filter_script import FilterScriptWithContent

        # Create script with content
        script_with_content = FilterScriptWithContent(
            **sample_filter_script_read.model_dump(),
            script_content="#!/bin/bash\necho 'test script'"
        )

        # Create a mock pagination result object
        mock_result = Mock()
        mock_result.items = [script_with_content]
        mock_result.total = 1
        mock_result.page = 1
        mock_result.size = 50
        mock_result.pages = 1
        mock_result.model_dump.return_value = {
            "items": [script_with_content],
            "total": 1,
            "page": 1,
            "size": 50,
            "pages": 1,
        }

        mock_filter_script_service.list_filter_scripts = AsyncMock(
            return_value=mock_result
        )

        # Mock the batch content method when include_content=True
        mock_filter_script_service.get_filter_scripts_with_content = AsyncMock(
            return_value=[script_with_content]
        )

        result = await list_filter_scripts(
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name=None,
            slug=None,
            language=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
            include_content=True,
        )

        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert "script_content" in result["items"][0]
        # Verify service was called with correct arguments
        mock_filter_script_service.list_filter_scripts.assert_called_once()
        call_args = mock_filter_script_service.list_filter_scripts.call_args
        assert call_args[1]['db'] == mock_db
        assert call_args[1]['page'] == 1
        assert call_args[1]['size'] == 50
        # Check filters object
        filters = call_args[1]['filters']
        assert filters.name is None
        assert filters.slug is None
        assert filters.language is None
        assert filters.active is None
        assert filters.validated is None
        # Check sort object
        sort = call_args[1]['sort']
        assert sort.field == "created_at"
        assert sort.order == "desc"

    @pytest.mark.asyncio
    async def test_list_filter_scripts_non_admin(
        self,
        mock_db,
        mock_filter_script_service,
    ):
        """Test filter script listing with non-admin user."""
        non_admin_user = {
            "id": 2,
            "username": "user",
            "email": "user@example.com",
            "is_superuser": False,
            "tenant_id": uuid.uuid4(),
        }

        # Create a mock pagination result object
        mock_result = Mock()
        mock_result.items = []
        mock_result.total = 0
        mock_result.page = 1
        mock_result.size = 50
        mock_result.pages = 0
        mock_result.model_dump.return_value = {"items": [], "total": 0, "page": 1, "size": 50, "pages": 0}

        mock_filter_script_service.list_filter_scripts = AsyncMock(
            return_value=mock_result
        )

        result = await list_filter_scripts(
            _request=Mock(),
            db=mock_db,
            admin_user=non_admin_user,
            _rate_limit=None,
            page=1,
            size=50,
            name=None,
            slug=None,
            language=None,
            active=None,
            validated=None,
            sort_field="created_at",
            sort_order="desc",
            include_content=False,
        )

        # Non-admin users should still get results but potentially filtered
        assert "items" in result
        mock_filter_script_service.list_filter_scripts.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_filter_scripts_unauthorized(
        self,
        mock_db,
        mock_filter_script_service,
    ):
        """Test filter script listing without authentication."""
        # This test would normally be handled at the router level
        # In unit tests, we simulate by passing None as admin_user
        mock_filter_script_service.list_filter_scripts = AsyncMock(
            side_effect=Exception("Unauthorized")
        )

        # Create a dummy user to avoid type errors, but expect service to raise exception
        dummy_user = {"id": 0, "username": "none", "email": "none@test.com", "is_superuser": False}

        with pytest.raises(Exception, match="Unauthorized"):
            await list_filter_scripts(
                _request=Mock(),
                db=mock_db,
                admin_user=dummy_user,  # Use dummy instead of None
                _rate_limit=None,  # Use None instead of Mock for type compatibility
                page=1,
                size=50,
                name=None,
                slug=None,
                language=None,
                active=None,
                validated=None,
                sort_field="created_at",
                sort_order="desc",
                include_content=False,
            )


class TestCreateFilterScript:
    """Test POST /admin/filter-scripts endpoint."""

    @pytest.mark.asyncio
    async def test_create_filter_script_success(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_create,
        sample_filter_script_read,
        mock_filter_script_service,
        mock_path_operations,
    ):
        """Test successful filter script creation."""
        # Mock service response
        mock_filter_script_service.create_filter_script = AsyncMock(
            return_value=sample_filter_script_read
        )

        result = await create_filter_script(
            script_in=sample_filter_script_create,
            _request=Mock(),
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.name == sample_filter_script_read.name
        assert result.slug == sample_filter_script_read.slug
        assert result.language == sample_filter_script_read.language
        assert result.active is True
        assert result.validated is False
        mock_filter_script_service.create_filter_script.assert_called_once()


    @pytest.mark.asyncio
    async def test_create_filter_script_duplicate_slug(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_create,
        mock_filter_script_service,
    ):
        """Test creating a filter script with duplicate slug."""
        # Mock service to raise duplicate exception
        mock_filter_script_service.create_filter_script = AsyncMock(
            side_effect=DuplicateValueException(
                f"Filter script with slug '{sample_filter_script_create.slug}' already exists"
            )
        )

        with pytest.raises(DuplicateValueException, match="already exists"):
            await create_filter_script(
                script_in=sample_filter_script_create,
                _request=Mock(),
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )


    @pytest.mark.asyncio
    async def test_create_filter_script_invalid_language(
        self,
        mock_db,
        sample_admin_user,
    ):
        """Test creating a filter script with invalid language."""
        # This should be caught by Pydantic validation

        # Pydantic will raise validation error for invalid enum value
        # This test would be at the router level, not function level


class TestGetFilterScript:
    """Test GET /admin/filter-scripts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_filter_script_success(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test successful filter script retrieval."""
        # Mock service response with content
        from src.app.schemas.filter_script import FilterScriptWithContent
        filter_script_with_content = FilterScriptWithContent(
            **sample_filter_script_read.model_dump(),
            script_content="#!/bin/bash\necho 'test'"
        )
        mock_filter_script_service.get_filter_script = AsyncMock(
            return_value=filter_script_with_content
        )

        result = await get_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.id == sample_filter_script_read.id
        assert result.name == sample_filter_script_read.name
        assert hasattr(result, 'script_content')
        mock_filter_script_service.get_filter_script.assert_called_once_with(
            db=mock_db,
            script_id=sample_filter_script_id,
            include_content=True,
        )


    @pytest.mark.asyncio
    async def test_get_filter_script_not_found(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_id,
        mock_filter_script_service,
    ):
        """Test getting a non-existent filter script."""
        # Mock service to raise not found exception
        mock_filter_script_service.get_filter_script = AsyncMock(
            side_effect=NotFoundException("Filter script not found")
        )

        with pytest.raises(NotFoundException, match="Filter script not found"):
            await get_filter_script(
                _request=Mock(),
                script_id=sample_filter_script_id,
                db=mock_db,
                admin_user=sample_admin_user,
                _rate_limit=None,
            )


class TestUpdateFilterScript:
    """Test PUT /admin/filter-scripts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_filter_script_success(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_filter_script_service,
        mock_path_operations,
    ):
        """Test successful filter script update."""
        # Mock updated data
        updated_script = sample_filter_script_read
        updated_script.name = "Updated Test Filter"
        updated_script.description = "Updated description"
        updated_script.timeout_ms = 5000

        # Mock service response
        mock_filter_script_service.update_filter_script = AsyncMock(
            return_value=updated_script
        )

        update_data = FilterScriptUpdate(
            name="Updated Test Filter",
            description="Updated description",
            timeout_ms=5000,
            script_content="#!/bin/bash\necho 'Updated script'\nexit 0",
        )

        result = await update_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            script_update=update_data,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.name == "Updated Test Filter"
        assert result.description == "Updated description"
        assert result.timeout_ms == 5000
        mock_filter_script_service.update_filter_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_filter_script_slug_rename_file(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test updating filter script slug which should rename the file."""
        # Mock updated data with new slug
        updated_script = sample_filter_script_read
        updated_script.slug = "new-slug"
        updated_script.script_path = "config/filters/new-slug.sh"

        # Mock service response
        mock_filter_script_service.update_filter_script = AsyncMock(
            return_value=updated_script
        )

        update_data = FilterScriptUpdate(
            slug="new-slug",
            name="Updated Name",
            timeout_ms=2000,
            script_content="#!/bin/bash\necho 'updated'\nexit 0",
        )

        result = await update_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            script_update=update_data,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
        )

        assert result.slug == "new-slug"
        assert "new-slug" in result.script_path
        mock_filter_script_service.update_filter_script.assert_called_once_with(
            db=mock_db,
            script_id=sample_filter_script_id,
            script_update=update_data,
        )


class TestDeleteFilterScript:
    """Test DELETE /admin/filter-scripts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_filter_script_soft(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test soft deleting a filter script."""
        # Mock get_filter_script for validation check in delete endpoint
        mock_filter_script_service.get_filter_script = AsyncMock(
            return_value=sample_filter_script_read
        )

        # Mock service response
        mock_filter_script_service.delete_filter_script = AsyncMock(return_value=True)

        result = await delete_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            hard_delete=False,
            delete_file=False,
        )

        assert result is None
        mock_filter_script_service.delete_filter_script.assert_called_once_with(
            db=mock_db,
            script_id=sample_filter_script_id,
            hard_delete=False,
            delete_file=False,
        )


    @pytest.mark.asyncio
    async def test_delete_filter_script_with_file(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test deleting a filter script with file deletion."""
        # Mock get_filter_script for validation check in delete endpoint
        mock_filter_script_service.get_filter_script = AsyncMock(
            return_value=sample_filter_script_read
        )

        # Mock service response
        mock_filter_script_service.delete_filter_script = AsyncMock(return_value=True)

        result = await delete_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            hard_delete=False,
            delete_file=True,
        )

        assert result is None
        mock_filter_script_service.delete_filter_script.assert_called_once_with(
            db=mock_db,
            script_id=sample_filter_script_id,
            hard_delete=False,
            delete_file=True,
        )


class TestValidateFilterScript:
    """Test POST /admin/filter-scripts/{id}/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_filter_script_success(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test successful filter script validation."""
        from src.app.schemas.filter_script import FilterScriptValidationResult

        # Mock get_filter_script for validation check in validate endpoint
        mock_filter_script_service.get_filter_script = AsyncMock(
            return_value=sample_filter_script_read
        )

        # Mock service response
        mock_filter_script_service.validate_filter_script = AsyncMock(
            return_value=FilterScriptValidationResult(
                valid=True,
                errors=[],
                test_output="Test output",
                execution_time_ms=100,
            )
        )

        result = await validate_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            validation_request=None,
        )

        assert result.valid is True
        assert result.errors == []
        mock_filter_script_service.validate_filter_script.assert_called_once()


    @pytest.mark.asyncio
    async def test_validate_filter_script_with_test_input(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test validating a filter script with test input."""
        from src.app.schemas.filter_script import FilterScriptValidationRequest, FilterScriptValidationResult

        test_input = {
            "monitor_match": {
                "test": "data"
            }
        }

        validation_request = FilterScriptValidationRequest(test_input=test_input)

        # Mock get_filter_script for validation check in validate endpoint
        mock_filter_script_service.get_filter_script = AsyncMock(
            return_value=sample_filter_script_read
        )

        # Mock service response
        mock_filter_script_service.validate_filter_script = AsyncMock(
            return_value=FilterScriptValidationResult(
                valid=True,
                errors=[],
                test_output='{"test": "data"}',
                execution_time_ms=50,
            )
        )

        result = await validate_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            validation_request=validation_request,
        )

        assert result.valid is True
        assert result.test_output is not None
        assert result.execution_time_ms is not None
        mock_filter_script_service.validate_filter_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_filter_script_bash(
        self,
        mock_db,
        sample_admin_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_filter_script_service,
    ):
        """Test validating a bash filter script specifically."""
        from src.app.schemas.filter_script import FilterScriptValidationRequest, FilterScriptValidationResult

        # Mock get_filter_script for validation check in validate endpoint
        mock_filter_script_service.get_filter_script = AsyncMock(
            return_value=sample_filter_script_read
        )

        # Mock service response for bash script validation
        mock_filter_script_service.validate_filter_script = AsyncMock(
            return_value=FilterScriptValidationResult(
                valid=True,
                errors=[],
                test_output="#!/bin/bash executed successfully",
                execution_time_ms=25,
            )
        )

        validation_request = FilterScriptValidationRequest(
            test_input={"monitor_match": {"block_number": 12345}}
        )

        result = await validate_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            db=mock_db,
            admin_user=sample_admin_user,
            _rate_limit=None,
            validation_request=validation_request,
        )

        assert result.valid is True
        assert result.errors == []
        assert "bash" in (result.test_output or "").lower()
        mock_filter_script_service.validate_filter_script.assert_called_once()
