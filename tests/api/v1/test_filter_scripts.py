"""
Tests for tenant-scoped filter script API endpoints.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.api.v1.filter_scripts import (
    create_filter_script,
    delete_filter_script,
    get_filter_script,
    list_filter_scripts,
    update_filter_script,
    validate_filter_script,
)
from src.app.core.exceptions.http_exceptions import (
    DuplicateValueException,
    ForbiddenException,
    NotFoundException,
)
from src.app.schemas.filter_script import (
    FilterScriptCreate,
    FilterScriptRead,
    FilterScriptUpdate,
    FilterScriptValidationResult,
    FilterScriptWithContent,
)


@pytest.fixture
def sample_tenant_id():
    """Generate a sample tenant ID."""
    return uuid.uuid4()


@pytest.fixture
def sample_filter_script_id():
    """Generate a sample filter script ID."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_user(sample_tenant_id):
    """Mock user with tenant."""
    return {
        "id": 1,
        "username": "testuser",
        "email": "user@example.com",
        "is_superuser": False,
        "tenant_id": sample_tenant_id,
    }


@pytest.fixture
def sample_filter_script_create(sample_tenant_id):
    """Generate sample filter script creation data."""
    return FilterScriptCreate(
        tenant_id=sample_tenant_id,
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
def sample_filter_script_read(sample_filter_script_id, sample_tenant_id):
    """Generate sample filter script read data."""
    return FilterScriptRead(
        id=uuid.UUID(sample_filter_script_id),
        tenant_id=sample_tenant_id,
        name="Test Bash Filter",
        slug="test-bash-filter",
        language="bash",
        description="Test bash filter script for testing",
        arguments=["--verbose"],
        timeout_ms=1000,
        script_path=f"config/filters/{sample_tenant_id}_test-bash-filter.sh",
        active=True,
        validated=False,
        validation_errors=None,
        last_validated_at=None,
        file_size_bytes=None,
        file_hash=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_crud_filter_script():
    """Mock CRUD filter script operations."""
    with patch("src.app.api.v1.filter_scripts.crud_filter_script") as mock_crud:
        yield mock_crud


class TestListFilterScripts:
    """Test GET /v1/filter-scripts endpoint."""

    @pytest.mark.asyncio
    async def test_list_filter_scripts_success(
        self,
        mock_db,
        sample_user,
        sample_filter_script_read,
        mock_crud_filter_script,
    ):
        """Test successful filter script listing with pagination."""
        # Mock CRUD response
        mock_crud_filter_script.get_paginated = AsyncMock(
            return_value={
                "items": [sample_filter_script_read],
                "total": 1,
                "page": 1,
                "size": 50,
                "pages": 1,
            }
        )

        result = await list_filter_scripts(
            _request=Mock(),
            db=mock_db,
            current_user=sample_user,
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
        mock_crud_filter_script.get_paginated.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_filter_scripts_no_tenant(
        self,
        mock_db,
        mock_crud_filter_script,
    ):
        """Test filter script listing without tenant association."""
        user_without_tenant = {
            "id": 1,
            "username": "testuser",
            "email": "user@example.com",
            "is_superuser": False,
            # No tenant_id
        }

        with pytest.raises(ForbiddenException, match="not associated with any tenant"):
            await list_filter_scripts(
                _request=Mock(),
                db=mock_db,
                current_user=user_without_tenant,
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
    """Test POST /v1/filter-scripts endpoint."""

    @pytest.mark.asyncio
    async def test_create_filter_script_success(
        self,
        mock_db,
        sample_user,
        sample_filter_script_create,
        sample_filter_script_read,
        mock_crud_filter_script,
    ):
        """Test successful filter script creation."""
        # Mock CRUD response
        mock_crud_filter_script.get_by_slug = AsyncMock(return_value=None)

        script_with_content = FilterScriptWithContent(
            **sample_filter_script_read.model_dump(),
            script_content=sample_filter_script_create.script_content
        )
        mock_crud_filter_script.create_with_tenant = AsyncMock(
            return_value=script_with_content
        )

        result = await create_filter_script(
            _request=Mock(),
            script_in=sample_filter_script_create,
            db=mock_db,
            current_user=sample_user,
        )

        assert result.name == sample_filter_script_read.name
        assert result.slug == sample_filter_script_read.slug
        assert result.language == sample_filter_script_read.language
        mock_crud_filter_script.create_with_tenant.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_filter_script_duplicate_slug(
        self,
        mock_db,
        sample_user,
        sample_filter_script_create,
        sample_filter_script_read,
        mock_crud_filter_script,
    ):
        """Test creating a filter script with duplicate slug."""
        # Mock CRUD to return existing script
        mock_crud_filter_script.get_by_slug = AsyncMock(
            return_value=sample_filter_script_read
        )

        with pytest.raises(DuplicateValueException, match="already exists"):
            await create_filter_script(
                _request=Mock(),
                script_in=sample_filter_script_create,
                db=mock_db,
                current_user=sample_user,
            )

    @pytest.mark.asyncio
    async def test_create_filter_script_wrong_tenant(
        self,
        mock_db,
        sample_user,
        sample_filter_script_create,
        mock_crud_filter_script,
    ):
        """Test creating a filter script for a different tenant."""
        # Modify script to have different tenant_id
        sample_filter_script_create.tenant_id = uuid.uuid4()

        with pytest.raises(ForbiddenException, match="Cannot create filter scripts for other tenants"):
            await create_filter_script(
                _request=Mock(),
                script_in=sample_filter_script_create,
                db=mock_db,
                current_user=sample_user,
            )


class TestGetFilterScript:
    """Test GET /v1/filter-scripts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_filter_script_success(
        self,
        mock_db,
        sample_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_crud_filter_script,
    ):
        """Test successful filter script retrieval."""
        # Mock CRUD response with content
        filter_script_with_content = FilterScriptWithContent(
            **sample_filter_script_read.model_dump(),
            script_content="#!/bin/bash\necho 'test'"
        )
        mock_crud_filter_script.get_with_cache = AsyncMock(
            return_value=filter_script_with_content
        )

        result = await get_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            db=mock_db,
            current_user=sample_user,
        )

        assert str(result.id) == sample_filter_script_id
        assert result.name == sample_filter_script_read.name
        assert hasattr(result, 'script_content')
        mock_crud_filter_script.get_with_cache.assert_called_once_with(
            db=mock_db,
            script_id=sample_filter_script_id,
            tenant_id=str(sample_user["tenant_id"]),
            include_content=True,
        )

    @pytest.mark.asyncio
    async def test_get_filter_script_not_found(
        self,
        mock_db,
        sample_user,
        sample_filter_script_id,
        mock_crud_filter_script,
    ):
        """Test getting a non-existent filter script."""
        # Mock CRUD to return None
        mock_crud_filter_script.get_with_cache = AsyncMock(return_value=None)

        with pytest.raises(NotFoundException, match="Filter script"):
            await get_filter_script(
                _request=Mock(),
                script_id=sample_filter_script_id,
                db=mock_db,
                current_user=sample_user,
            )


class TestUpdateFilterScript:
    """Test PUT /v1/filter-scripts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_filter_script_success(
        self,
        mock_db,
        sample_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_crud_filter_script,
    ):
        """Test successful filter script update."""
        # Mock updated data
        updated_data = sample_filter_script_read.model_dump()
        updated_data.update({
            "name": "Updated Test Filter",
            "description": "Updated description",
            "timeout_ms": 5000,
            "script_content": "#!/bin/bash\necho 'Updated'"
        })
        updated_script = FilterScriptWithContent(**updated_data)

        # Mock CRUD responses
        mock_crud_filter_script.get_by_slug = AsyncMock(return_value=None)
        mock_crud_filter_script.update_with_tenant = AsyncMock(
            return_value=updated_script
        )

        update_data = FilterScriptUpdate(
            name="Updated Test Filter",
            description="Updated description",
            timeout_ms=5000,
            script_content="#!/bin/bash\necho 'Updated'",
        )

        result = await update_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            script_update=update_data,
            db=mock_db,
            current_user=sample_user,
        )

        assert result.name == "Updated Test Filter"
        assert result.description == "Updated description"
        assert result.timeout_ms == 5000
        mock_crud_filter_script.update_with_tenant.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_filter_script_duplicate_slug(
        self,
        mock_db,
        sample_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_crud_filter_script,
    ):
        """Test updating filter script with duplicate slug."""
        # Mock CRUD to return existing script with different ID
        existing_data = sample_filter_script_read.model_dump()
        existing_data.update({
            "id": uuid.uuid4(),  # Different ID
            "slug": "existing-slug"
        })
        existing_script = FilterScriptRead(**existing_data)
        mock_crud_filter_script.get_by_slug = AsyncMock(
            return_value=existing_script
        )

        update_data = FilterScriptUpdate(slug="existing-slug")

        with pytest.raises(DuplicateValueException, match="already exists"):
            await update_filter_script(
                _request=Mock(),
                script_id=sample_filter_script_id,
                script_update=update_data,
                db=mock_db,
                current_user=sample_user,
            )


class TestDeleteFilterScript:
    """Test DELETE /v1/filter-scripts/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_filter_script_soft(
        self,
        mock_db,
        sample_user,
        sample_filter_script_id,
        mock_crud_filter_script,
    ):
        """Test soft deleting a filter script."""
        # Mock CRUD response
        mock_crud_filter_script.delete_with_tenant = AsyncMock(return_value=True)

        result = await delete_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            db=mock_db,
            current_user=sample_user,
            hard_delete=False,
            delete_file=False,
        )

        assert result is None
        mock_crud_filter_script.delete_with_tenant.assert_called_once_with(
            db=mock_db,
            script_id=sample_filter_script_id,
            tenant_id=str(sample_user["tenant_id"]),
            is_hard_delete=False,
            delete_file=False,
        )

    @pytest.mark.asyncio
    async def test_delete_filter_script_not_found(
        self,
        mock_db,
        sample_user,
        sample_filter_script_id,
        mock_crud_filter_script,
    ):
        """Test deleting a non-existent filter script."""
        # Mock CRUD to return False
        mock_crud_filter_script.delete_with_tenant = AsyncMock(return_value=False)

        with pytest.raises(NotFoundException, match="Filter script"):
            await delete_filter_script(
                _request=Mock(),
                script_id=sample_filter_script_id,
                db=mock_db,
                current_user=sample_user,
                hard_delete=False,
                delete_file=False,
            )


class TestValidateFilterScript:
    """Test POST /v1/filter-scripts/{id}/validate endpoint."""

    @pytest.mark.asyncio
    async def test_validate_filter_script_success(
        self,
        mock_db,
        sample_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_crud_filter_script,
    ):
        """Test successful filter script validation."""
        # Mock CRUD responses
        mock_crud_filter_script.get = AsyncMock(return_value=sample_filter_script_read)
        mock_crud_filter_script.validate_filter_script = AsyncMock(
            return_value=FilterScriptValidationResult(
                script_id=uuid.UUID(sample_filter_script_id),
                is_valid=True,
                errors=[],
                warnings=[],
                test_output="Test output",
                execution_time_ms=100,
                validated_at=datetime.now(UTC),
            )
        )

        result = await validate_filter_script(
            _request=Mock(),
            script_id=sample_filter_script_id,
            db=mock_db,
            current_user=sample_user,
            test_execution=False,
            check_syntax=True,
        )

        assert result.is_valid is True
        assert result.errors == []
        mock_crud_filter_script.validate_filter_script.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_filter_script_wrong_tenant(
        self,
        mock_db,
        sample_user,
        sample_filter_script_id,
        sample_filter_script_read,
        mock_crud_filter_script,
    ):
        """Test validating a filter script from another tenant."""
        # Mock script with different tenant
        wrong_tenant_data = sample_filter_script_read.model_dump()
        wrong_tenant_data["tenant_id"] = uuid.uuid4()  # Different tenant
        wrong_tenant_script = FilterScriptRead(**wrong_tenant_data)
        mock_crud_filter_script.get = AsyncMock(return_value=wrong_tenant_script)

        with pytest.raises(NotFoundException, match="Filter script"):
            await validate_filter_script(
                _request=Mock(),
                script_id=sample_filter_script_id,
                db=mock_db,
                current_user=sample_user,
                test_execution=False,
                check_syntax=True,
            )
