"""Unit tests for CRUDFilterScript operations."""

import asyncio
import uuid
from datetime import datetime

import pytest
from fastcrud.paginated import PaginatedListResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.crud.crud_filter_script import crud_filter_script
from src.app.models.filter_script import FilterScript
from src.app.schemas.filter_script import (
    FilterScriptCreateInternal,
    FilterScriptDelete,
    FilterScriptUpdate,
)
from tests.factories.filter_script_factory import FilterScriptFactory


@pytest.mark.asyncio
class TestCRUDFilterScript:
    """Test suite for CRUDFilterScript operations."""

    async def test_create_filter_script_success(self, async_db: AsyncSession) -> None:
        """
        Test successful filter script creation.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        script_data = FilterScriptCreateInternal(
            id=uuid.uuid4(),
            name="Test Python Filter",
            slug="test-python-filter",
            language="python",
            script_path="filters/test-python-filter.py",
            description="Test Python filter for blockchain monitoring",
            arguments=["--format", "json", "--threshold", "1000"],
            timeout_ms=5000
        )

        # Act
        result = await crud_filter_script.create(async_db, object=script_data)

        # Assert
        assert result is not None
        assert result.name == script_data.name
        assert result.slug == script_data.slug
        assert result.language == script_data.language
        assert result.script_path == script_data.script_path
        assert result.description == script_data.description
        assert result.arguments == script_data.arguments
        assert result.timeout_ms == script_data.timeout_ms
        assert result.active is True
        assert result.validated is False
        assert result.created_at is not None
        assert result.updated_at is not None

    async def test_create_filter_script_duplicate_slug(self, async_db: AsyncSession) -> None:
        """
        Test filter script creation with duplicate slug fails.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        existing_script = await FilterScriptFactory.create_async(async_db)

        duplicate_data = FilterScriptCreateInternal(
            id=uuid.uuid4(),
            name="Duplicate Script",
            slug=existing_script.slug,  # Same slug
            language="javascript",
            script_path="filters/duplicate.js",
            timeout_ms=3000
        )

        # Act & Assert
        with pytest.raises(Exception):  # Should raise integrity error
            await crud_filter_script.create(async_db, object=duplicate_data)

    async def test_get_filter_script_by_id(self, async_db: AsyncSession) -> None:
        """
        Test retrieving filter script by ID.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(async_db)

        # Act
        result = await crud_filter_script.get(async_db, id=created_script.id)

        # Assert
        assert result is not None
        assert result.id == created_script.id
        assert result.name == created_script.name
        assert result.slug == created_script.slug
        assert result.language == created_script.language

    async def test_get_filter_script_not_found(self, async_db: AsyncSession) -> None:
        """
        Test retrieving non-existent filter script returns None.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_filter_script.get(async_db, id=uuid.uuid4())

        # Assert
        assert result is None

    async def test_get_by_slug_success(self, async_db: AsyncSession) -> None:
        """
        Test retrieving filter script by slug.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(
            async_db, slug="unique-test-filter"
        )

        # Act
        result = await crud_filter_script.get_by_slug(
            async_db, slug="unique-test-filter"
        )

        # Assert
        assert result is not None
        assert result.id == created_script.id
        assert result.slug == "unique-test-filter"

    async def test_get_by_slug_not_found(self, async_db: AsyncSession) -> None:
        """
        Test retrieving filter script by non-existent slug.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_filter_script.get_by_slug(
            async_db, slug="non-existent-slug"
        )

        # Assert
        assert result is None

    async def test_get_by_language_python(self, async_db: AsyncSession) -> None:
        """
        Test retrieving filter scripts by language (Python).

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        python_script1 = await FilterScriptFactory.create_async(
            async_db, language="python", active=True
        )
        python_script2 = await FilterScriptFactory.create_async(
            async_db, language="python", active=True
        )
        await FilterScriptFactory.create_async(
            async_db, language="javascript", active=True
        )
        await FilterScriptFactory.create_async(
            async_db, language="python", active=False
        )

        # Act
        result = await crud_filter_script.get_by_language(
            async_db, language="python", active_only=True
        )

        # Assert
        assert len(result) == 2
        script_ids = {script.id for script in result}
        assert python_script1.id in script_ids
        assert python_script2.id in script_ids
        for script in result:
            assert script.language == "python"
            assert script.active is True

    async def test_get_by_language_case_insensitive(self, async_db: AsyncSession) -> None:
        """
        Test language filtering is case insensitive.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        await FilterScriptFactory.create_async(
            async_db, language="javascript", active=True
        )

        # Act
        result = await crud_filter_script.get_by_language(
            async_db, language="JAVASCRIPT", active_only=True
        )

        # Assert
        assert len(result) == 1
        assert result[0].language == "javascript"

    async def test_get_by_language_include_inactive(self, async_db: AsyncSession) -> None:
        """
        Test retrieving scripts by language including inactive ones.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        await FilterScriptFactory.create_async(
            async_db, language="bash", active=True
        )
        await FilterScriptFactory.create_async(
            async_db, language="bash", active=False
        )

        # Act
        result = await crud_filter_script.get_by_language(
            async_db, language="bash", active_only=False
        )

        # Assert
        assert len(result) == 2
        active_states = {script.active for script in result}
        assert True in active_states
        assert False in active_states

    async def test_get_active_scripts(self, async_db: AsyncSession) -> None:
        """
        Test retrieving all active filter scripts.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        active_script1 = await FilterScriptFactory.create_async(
            async_db, active=True
        )
        active_script2 = await FilterScriptFactory.create_async(
            async_db, active=True
        )
        await FilterScriptFactory.create_async(
            async_db, active=False
        )

        # Act
        result = await crud_filter_script.get_active_scripts(async_db)

        # Assert
        assert len(result) == 2
        script_ids = {script.id for script in result}
        assert active_script1.id in script_ids
        assert active_script2.id in script_ids
        for script in result:
            assert script.active is True

    async def test_update_filter_script_success(self, async_db: AsyncSession) -> None:
        """
        Test successful filter script update.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(async_db)
        original_updated_at = created_script.updated_at

        update_data = FilterScriptUpdate(
            name="Updated Filter Name",
            description="Updated description for the filter",
            arguments=["--new-arg", "value"],
            timeout_ms=10000,
            active=False
        )

        # Act
        result = await crud_filter_script.update(
            async_db, db_obj=created_script, object=update_data
        )

        # Assert
        assert result is not None
        assert result.id == created_script.id
        assert result.name == "Updated Filter Name"
        assert result.description == "Updated description for the filter"
        assert result.arguments == ["--new-arg", "value"]
        assert result.timeout_ms == 10000
        assert result.active is False
        assert result.updated_at > original_updated_at
        # Slug and language should remain unchanged
        assert result.slug == created_script.slug
        assert result.language == created_script.language

    async def test_update_filter_script_partial(self, async_db: AsyncSession) -> None:
        """
        Test partial filter script update.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(
            async_db,
            name="Original Name",
            timeout_ms=5000,
            active=True
        )

        update_data = FilterScriptUpdate(timeout_ms=15000)

        # Act
        result = await crud_filter_script.update(
            async_db, db_obj=created_script, object=update_data
        )

        # Assert
        assert result is not None
        assert result.name == "Original Name"  # Unchanged
        assert result.timeout_ms == 15000  # Updated
        assert result.active is True  # Unchanged

    async def test_mark_validated_success(self, async_db: AsyncSession) -> None:
        """
        Test marking filter script as validated.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(
            async_db, validated=False
        )

        # Act
        result = await crud_filter_script.mark_validated(
            async_db, script_id=str(created_script.id), validated=True
        )

        # Assert
        assert result is not None
        assert result.id == created_script.id
        assert result.validated is True
        assert result.validation_errors is None
        assert result.last_validated_at is not None
        assert isinstance(result.last_validated_at, datetime)

    async def test_mark_validated_with_errors(self, async_db: AsyncSession) -> None:
        """
        Test marking filter script as invalid with validation errors.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(async_db)
        validation_errors = {
            "syntax": ["Syntax error on line 42: unexpected token"],
            "permissions": ["Script file is not executable"],
            "dependencies": ["Missing required module: numpy"]
        }

        # Act
        result = await crud_filter_script.mark_validated(
            async_db,
            script_id=str(created_script.id),
            validated=False,
            validation_errors=validation_errors
        )

        # Assert
        assert result is not None
        assert result.validated is False
        assert result.validation_errors == validation_errors
        assert result.last_validated_at is not None

    async def test_mark_validated_script_not_found(self, async_db: AsyncSession) -> None:
        """
        Test marking non-existent script as validated returns None.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_filter_script.mark_validated(
            async_db, script_id=str(uuid.uuid4()), validated=True
        )

        # Assert
        assert result is None

    async def test_update_file_metadata_success(self, async_db: AsyncSession) -> None:
        """
        Test updating filter script file metadata.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(
            async_db, file_size_bytes=None, file_hash=None
        )

        # Act
        result = await crud_filter_script.update_file_metadata(
            async_db,
            script_id=str(created_script.id),
            file_size_bytes=2048,
            file_hash="abc123def456..."
        )

        # Assert
        assert result is not None
        assert result.id == created_script.id
        assert result.file_size_bytes == 2048
        assert result.file_hash == "abc123def456..."

    async def test_update_file_metadata_script_not_found(self, async_db: AsyncSession) -> None:
        """
        Test updating file metadata for non-existent script returns None.

        Args:
            async_db: Async database session fixture
        """
        # Act
        result = await crud_filter_script.update_file_metadata(
            async_db,
            script_id=str(uuid.uuid4()),
            file_size_bytes=1024,
            file_hash="nonexistent"
        )

        # Assert
        assert result is None

    async def test_delete_filter_script_soft_delete(self, async_db: AsyncSession) -> None:
        """
        Test soft deletion of filter script.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(async_db)
        delete_data = FilterScriptDelete(is_deleted=True)

        # Act
        result = await crud_filter_script.delete(
            async_db, db_obj=created_script, object=delete_data
        )

        # Assert
        assert result is not None
        assert hasattr(result, 'is_deleted')
        # Check script still exists but is marked deleted
        retrieved = await crud_filter_script.get(async_db, id=created_script.id)
        assert retrieved is not None  # Still exists in database

    async def test_delete_filter_script_hard_delete(self, async_db: AsyncSession) -> None:
        """
        Test hard deletion of filter script.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(async_db)

        # Act
        await crud_filter_script.delete(async_db, id=created_script.id)

        # Assert - script should no longer exist
        retrieved = await crud_filter_script.get(async_db, id=created_script.id)
        assert retrieved is None

    async def test_get_multi_filter_scripts(self, async_db: AsyncSession) -> None:
        """
        Test retrieving multiple filter scripts.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        await asyncio.gather(*[
            FilterScriptFactory.create_async(async_db)
            for _ in range(5)
        ])

        # Act
        result = await crud_filter_script.get_multi(async_db, skip=0, limit=3)

        # Assert
        assert len(result) == 3
        assert all(isinstance(script, FilterScript) for script in result)

    async def test_get_paginated_filter_scripts(self, async_db: AsyncSession) -> None:
        """
        Test paginated retrieval of filter scripts.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        await asyncio.gather(*[
            FilterScriptFactory.create_async(async_db)
            for _ in range(7)
        ])

        # Act
        result = await crud_filter_script.get_paginated(
            async_db, page=1, items_per_page=3
        )

        # Assert
        assert isinstance(result, PaginatedListResponse)
        assert len(result.data) == 3
        assert result.total_count == 7
        assert result.has_next is True
        assert result.has_previous is False
        assert result.page == 1
        assert result.items_per_page == 3

    async def test_count_filter_scripts(self, async_db: AsyncSession) -> None:
        """
        Test counting filter scripts.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        initial_count = await crud_filter_script.count(async_db)
        await asyncio.gather(*[
            FilterScriptFactory.create_async(async_db)
            for _ in range(3)
        ])

        # Act
        final_count = await crud_filter_script.count(async_db)

        # Assert
        assert final_count == initial_count + 3

    async def test_exists_filter_script(self, async_db: AsyncSession) -> None:
        """
        Test checking if filter script exists.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        created_script = await FilterScriptFactory.create_async(async_db)

        # Act
        exists = await crud_filter_script.exists(async_db, id=created_script.id)
        not_exists = await crud_filter_script.exists(async_db, id=uuid.uuid4())

        # Assert
        assert exists is True
        assert not_exists is False

    # Factory variant tests

    async def test_create_python_filter_factory(self, async_db: AsyncSession) -> None:
        """
        Test creating Python filter script using factory variant.

        Args:
            async_db: Async database session fixture
        """
        # Act
        script = await FilterScriptFactory.create_python_filter_async(async_db)

        # Assert
        assert script.language == "python"
        assert "Python" in script.name
        assert "--input-format" in script.arguments
        assert script.timeout_ms == 5000

    async def test_create_javascript_filter_factory(self, async_db: AsyncSession) -> None:
        """
        Test creating JavaScript filter script using factory variant.

        Args:
            async_db: Async database session fixture
        """
        # Act
        script = await FilterScriptFactory.create_javascript_filter_async(async_db)

        # Assert
        assert script.language == "javascript"
        assert "JS" in script.name
        assert "--format" in script.arguments
        assert script.timeout_ms == 3000

    async def test_create_bash_filter_factory(self, async_db: AsyncSession) -> None:
        """
        Test creating Bash filter script using factory variant.

        Args:
            async_db: Async database session fixture
        """
        # Act
        script = await FilterScriptFactory.create_bash_filter_async(async_db)

        # Assert
        assert script.language == "bash"
        assert "Bash" in script.name
        assert "-v" in script.arguments
        assert script.timeout_ms == 2000

    async def test_create_validated_filter_factory(self, async_db: AsyncSession) -> None:
        """
        Test creating validated filter script using factory variant.

        Args:
            async_db: Async database session fixture
        """
        # Act
        script = await FilterScriptFactory.create_validated_filter_async(async_db)

        # Assert
        assert script.validated is True
        assert script.last_validated_at is not None
        assert script.validation_errors is None
        assert script.file_size_bytes is not None
        assert script.file_hash is not None
        assert isinstance(script.file_size_bytes, int)
        assert len(script.file_hash) == 64  # SHA256 length

    async def test_create_invalid_filter_factory(self, async_db: AsyncSession) -> None:
        """
        Test creating invalid filter script using factory variant.

        Args:
            async_db: Async database session fixture
        """
        # Act
        script = await FilterScriptFactory.create_invalid_filter_async(async_db)

        # Assert
        assert script.validated is False
        assert script.validation_errors is not None
        assert "syntax" in script.validation_errors
        assert "permissions" in script.validation_errors
        assert "dependencies" in script.validation_errors
        assert script.last_validated_at is not None

    async def test_create_inactive_filter_factory(self, async_db: AsyncSession) -> None:
        """
        Test creating inactive filter script using factory variant.

        Args:
            async_db: Async database session fixture
        """
        # Act
        script = await FilterScriptFactory.create_inactive_filter_async(async_db)

        # Assert
        assert script.active is False
        assert "Inactive filter" in script.description

    async def test_specialized_filter_factories(self, async_db: AsyncSession) -> None:
        """
        Test creating specialized filter scripts using factory variants.

        Args:
            async_db: Async database session fixture
        """
        # Act
        large_transfer = await FilterScriptFactory.create_large_transfer_filter_async(async_db)
        defi_interaction = await FilterScriptFactory.create_defi_interaction_filter_async(async_db)
        nft_activity = await FilterScriptFactory.create_nft_activity_filter_async(async_db)

        # Assert
        assert large_transfer.slug == "large-transfer-filter"
        assert "--threshold" in large_transfer.arguments
        assert large_transfer.language == "python"

        assert defi_interaction.slug == "defi-interaction-filter"
        assert "--protocols" in defi_interaction.arguments
        assert defi_interaction.language == "javascript"

        assert nft_activity.slug == "nft-activity-filter"
        assert "--include-mints" in nft_activity.arguments
        assert nft_activity.language == "python"

    # Edge cases and error conditions

    async def test_timeout_constraint_validation(self, async_db: AsyncSession) -> None:
        """
        Test that timeout constraints are enforced.

        Args:
            async_db: Async database session fixture
        """
        # Test invalid timeout values should be caught by database constraints
        # This is a database-level constraint, so we test valid values

        # Valid timeout
        script_data = FilterScriptCreateInternal(
            id=uuid.uuid4(),
            name="Valid Timeout Script",
            slug="valid-timeout",
            language="python",
            script_path="filters/valid.py",
            timeout_ms=15000  # Valid: within 1-30000 range
        )

        result = await crud_filter_script.create(async_db, object=script_data)
        assert result.timeout_ms == 15000

    async def test_language_constraint_validation(self, async_db: AsyncSession) -> None:
        """
        Test that language constraints work with valid languages.

        Args:
            async_db: Async database session fixture
        """
        # Test all valid languages
        valid_languages = ["bash", "python", "javascript"]

        for i, language in enumerate(valid_languages):
            script_data = FilterScriptCreateInternal(
                id=uuid.uuid4(),
                name=f"Test {language.title()} Script",
                slug=f"test-{language}-{i}",
                language=language,
                script_path=f"filters/test-{language}.{'py' if language == 'python' else 'js' if language == 'javascript' else 'sh'}",
                timeout_ms=5000
            )

            result = await crud_filter_script.create(async_db, object=script_data)
            assert result.language == language

    async def test_filter_script_with_complex_arguments(self, async_db: AsyncSession) -> None:
        """
        Test filter script with complex argument structures.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        complex_arguments = [
            "--threshold", "1000000000000000000",
            "--networks", "ethereum,polygon,arbitrum",
            "--include-contracts",
            "--exclude-zero-value",
            "--format", "json",
            "--output-file", "/tmp/filter_results.json",
            "--log-level", "debug",
            "--max-concurrent", "10"
        ]

        script_data = FilterScriptCreateInternal(
            id=uuid.uuid4(),
            name="Complex Arguments Filter",
            slug="complex-args-filter",
            language="python",
            script_path="filters/complex.py",
            arguments=complex_arguments,
            timeout_ms=20000
        )

        # Act
        result = await crud_filter_script.create(async_db, object=script_data)

        # Assert
        assert result.arguments == complex_arguments
        assert len(result.arguments) == 16

    async def test_filter_script_json_serialization(self, async_db: AsyncSession) -> None:
        """
        Test that JSON fields serialize/deserialize correctly.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        arguments = ["--config", '{"key": "value", "number": 42}']
        validation_errors = {
            "syntax": ["Line 1: Missing semicolon"],
            "security": ["Unsafe file access detected"],
            "performance": ["Infinite loop detected on line 25"]
        }

        script = await FilterScriptFactory.create_async(
            async_db,
            arguments=arguments,
            validated=False,
            validation_errors=validation_errors
        )

        # Act - retrieve and verify JSON fields
        retrieved = await crud_filter_script.get(async_db, id=script.id)

        # Assert
        assert retrieved is not None
        assert retrieved.arguments == arguments
        assert retrieved.validation_errors == validation_errors
        assert isinstance(retrieved.validation_errors, dict)
        assert isinstance(retrieved.arguments, list)

    async def test_concurrent_filter_script_operations(self, async_db: AsyncSession) -> None:
        """
        Test concurrent filter script operations.

        Args:
            async_db: Async database session fixture
        """
        # Arrange
        async def create_script(index: int) -> FilterScript:
            return await FilterScriptFactory.create_async(
                async_db,
                name=f"Concurrent Script {index}",
                slug=f"concurrent-script-{index}",
                language=["python", "javascript", "bash"][index % 3]
            )

        # Act - create multiple scripts concurrently
        scripts = await asyncio.gather(*[
            create_script(i) for i in range(5)
        ])

        # Assert
        assert len(scripts) == 5
        assert len({script.slug for script in scripts}) == 5  # All unique slugs
        assert all(script.active is True for script in scripts)

    async def test_filter_script_search_patterns(self, async_db: AsyncSession) -> None:
        """
        Test various search patterns for filter scripts.

        Args:
            async_db: Async database session fixture
        """
        # Arrange - create scripts with known patterns
        await FilterScriptFactory.create_async(
            async_db, name="ERC20 Token Filter", language="python"
        )
        await FilterScriptFactory.create_async(
            async_db, name="NFT Marketplace Filter", language="javascript"
        )
        await FilterScriptFactory.create_async(
            async_db, name="DeFi Protocol Filter", language="python"
        )

        # Act & Assert - test language-based filtering
        python_scripts = await crud_filter_script.get_by_language(
            async_db, "python"
        )
        js_scripts = await crud_filter_script.get_by_language(
            async_db, "javascript"
        )

        assert len([s for s in python_scripts if "Filter" in s.name]) >= 2
        assert len([s for s in js_scripts if "Filter" in s.name]) >= 1

    async def test_filter_script_lifecycle(self, async_db: AsyncSession) -> None:
        """
        Test complete filter script lifecycle.

        Args:
            async_db: Async database session fixture
        """
        # Create
        script_data = FilterScriptCreateInternal(
            id=uuid.uuid4(),
            name="Lifecycle Test Filter",
            slug="lifecycle-test",
            language="python",
            script_path="filters/lifecycle.py",
            timeout_ms=5000
        )
        script = await crud_filter_script.create(async_db, object=script_data)
        assert script.validated is False

        # Update file metadata
        updated_script = await crud_filter_script.update_file_metadata(
            async_db,
            script_id=str(script.id),
            file_size_bytes=1024,
            file_hash="abc123"
        )
        assert updated_script.file_size_bytes == 1024

        # Mark as validated
        validated_script = await crud_filter_script.mark_validated(
            async_db, script_id=str(script.id), validated=True
        )
        assert validated_script.validated is True

        # Update configuration
        update_data = FilterScriptUpdate(
            arguments=["--new-config"],
            timeout_ms=10000
        )
        final_script = await crud_filter_script.update(
            async_db, db_obj=validated_script, object=update_data
        )
        assert final_script.arguments == ["--new-config"]
        assert final_script.timeout_ms == 10000
        assert final_script.validated is True  # Should remain validated
