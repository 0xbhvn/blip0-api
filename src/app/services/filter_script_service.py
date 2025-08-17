"""
Service layer for FilterScript operations with filesystem management.
Filter scripts are platform-managed resources for custom filtering logic.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import logging
from ..core.redis_client import redis_client
from ..crud.crud_filter_script import CRUDFilterScript, crud_filter_script
from ..schemas.filter_script import (
    FilterScriptCreate,
    FilterScriptCreateInternal,
    FilterScriptFilter,
    FilterScriptPagination,
    FilterScriptRead,
    FilterScriptSort,
    FilterScriptUpdate,
    FilterScriptUpdateInternal,
    FilterScriptValidationRequest,
    FilterScriptValidationResult,
    FilterScriptWithContent,
)
from .base_service import BaseService

logger = logging.getLogger(__name__)


class FilterScriptService(BaseService):
    """
    Service layer for FilterScript operations.
    Handles platform-managed filter scripts with filesystem storage and Redis caching.
    """

    def __init__(self, crud_filter_script: CRUDFilterScript):
        """Initialize filter script service with CRUD dependency."""
        super().__init__(crud_filter_script)
        self.crud_filter_script = crud_filter_script
        # Base directory for filter scripts (relative to project root)
        self.scripts_base_dir = Path("config/filters")
        self.scripts_base_dir.mkdir(parents=True, exist_ok=True)

    # Abstract method implementations from BaseService
    def get_cache_key(self, entity_id: str, **kwargs) -> str:
        """Get Redis cache key for filter script."""
        return f"platform:filter_scripts:{entity_id}"

    def get_cache_ttl(self) -> int:
        """Get cache TTL in seconds (1 hour)."""
        return 3600

    @property
    def read_schema(self) -> type[FilterScriptRead]:
        """Get the read schema class for validation."""
        return FilterScriptRead

    async def create_filter_script(
        self,
        db: AsyncSession,
        script_in: FilterScriptCreate,
    ) -> FilterScriptWithContent:
        """
        Create a new filter script with filesystem storage.

        Args:
            db: Database session
            script_in: Filter script creation data

        Returns:
            Created filter script with content
        """
        # Calculate file metadata first
        file_size_bytes = len(script_in.script_content.encode())
        file_hash = hashlib.sha256(script_in.script_content.encode()).hexdigest()

        # Generate script filename based on slug and language
        script_filename = f"{script_in.slug}.{self._get_file_extension(script_in.language)}"
        script_path = f"./config/filters/{script_filename}"

        # Create database record FIRST to check constraints
        script_internal = FilterScriptCreateInternal(
            **script_in.model_dump(exclude={"script_content"}),
            script_path=script_path,
            file_size_bytes=file_size_bytes,
            file_hash=file_hash,
        )

        db_script = await self.crud_filter_script.create(
            db=db,
            object=script_internal
        )

        # Only write file after database success
        full_path = self.scripts_base_dir / script_filename
        try:
            full_path.write_text(script_in.script_content)
            # Set proper permissions (644 - read for all, write for owner only)
            os.chmod(full_path, 0o644)
        except Exception as e:
            # Rollback database record if file write fails
            try:
                await self.crud_filter_script.db_delete(db=db, id=str(db_script.id))
            except Exception:
                pass  # Best effort cleanup
            logger.error(f"Failed to write script file {full_path}: {e}")
            raise ValueError(f"Failed to save script file: {str(e)}")

        # Write-through to Redis for fast access
        await self._cache_filter_script(db_script)

        logger.info(f"Created filter script {db_script.slug} at {script_path}")

        # Return with content
        return FilterScriptWithContent(
            **FilterScriptRead.model_validate(db_script).model_dump(),
            script_content=script_in.script_content
        )

    async def get_filter_script(
        self,
        db: AsyncSession,
        script_id: str,
        include_content: bool = False,
    ) -> Optional[Union[FilterScriptRead, FilterScriptWithContent]]:
        """
        Get a filter script by ID.

        Args:
            db: Database session
            script_id: Filter script ID
            include_content: Whether to include actual script content

        Returns:
            Filter script if found
        """
        # Try cache first
        cached = await self._get_cached_filter_script(script_id)
        if cached:
            logger.debug(f"Cache hit for filter script {script_id}")
            if include_content:
                script_path = cached.get("script_path", "")
                if script_path:
                    content = await self._read_script_file(script_path)
                    return FilterScriptWithContent(**cached, script_content=content)
            return FilterScriptRead(**cached)

        # Fallback to database
        db_script = await self.crud_filter_script.get(db=db, id=script_id)
        if not db_script:
            return None

        # Refresh cache on cache miss
        await self._cache_filter_script(db_script)

        if include_content and hasattr(db_script, 'script_path'):
            content = await self._read_script_file(db_script.script_path)
            return FilterScriptWithContent(
                **FilterScriptRead.model_validate(db_script).model_dump(),
                script_content=content
            )

        return FilterScriptRead.model_validate(db_script)

    async def update_filter_script(
        self,
        db: AsyncSession,
        script_id: str,
        script_update: FilterScriptUpdate,
    ) -> Optional[FilterScriptWithContent]:
        """
        Update a filter script with cache invalidation.

        Args:
            db: Database session
            script_id: Filter script ID
            script_update: Update data

        Returns:
            Updated filter script if found
        """
        # Get existing script
        existing = await self.crud_filter_script.get(db=db, id=script_id)
        if not existing:
            return None
        if not hasattr(existing, 'script_path'):
            return None

        # Calculate file metadata if content is updated
        if script_update.script_content is not None:
            file_size_bytes = len(script_update.script_content.encode())
            file_hash = hashlib.sha256(script_update.script_content.encode()).hexdigest()
        else:
            file_size_bytes = None
            file_hash = None

        # Handle slug update (requires path update)
        new_script_path = None
        if script_update.slug and hasattr(existing, 'slug') and script_update.slug != existing.slug:
            language = (
                script_update.language if script_update.language
                else (existing.language if hasattr(existing, 'language') else 'bash')
            )
            new_filename = f"{script_update.slug}.{self._get_file_extension(language)}"
            new_script_path = f"./config/filters/{new_filename}"

        # Create internal update with file metadata and new path
        update_data = script_update.model_dump(exclude={"script_content"}, exclude_unset=True)
        if new_script_path:
            update_data["script_path"] = new_script_path

        update_internal = FilterScriptUpdateInternal(
            **update_data,
            file_size_bytes=file_size_bytes,
            file_hash=file_hash,
            validated=False,  # Reset validation on update
        )

        # Update database record FIRST to check constraints
        db_script = await self.crud_filter_script.update(
            db=db,
            id=script_id,
            object=update_internal
        )

        if not db_script:
            return None

        # Now handle file operations after database success
        try:
            # Handle script content update if provided
            if script_update.script_content is not None:
                existing_script_path = existing.script_path if hasattr(existing, 'script_path') else ""
                full_path = Path(existing_script_path.replace("./", ""))
                if not full_path.exists():
                    full_path = self.scripts_base_dir / Path(existing_script_path).name

                full_path.write_text(script_update.script_content)
                os.chmod(full_path, 0o644)

            # Handle slug/file rename if needed
            if new_script_path and hasattr(existing, 'script_path'):
                old_path = Path(existing.script_path.replace("./", ""))
                if not old_path.exists():
                    old_path = self.scripts_base_dir / Path(existing.script_path).name

                new_path = self.scripts_base_dir / Path(new_script_path).name

                if old_path.exists():
                    old_path.rename(new_path)

        except Exception as e:
            logger.error(f"Failed to update script file: {e}")
            # Don't raise ValueError, just log the error - DB update already succeeded
            # The file operation is secondary to the database record

        # Invalidate cache
        await self._invalidate_cache(script_id)

        # Get updated content
        content = script_update.script_content
        if content is None and hasattr(db_script, 'script_path'):
            content = await self._read_script_file(db_script.script_path)

        return FilterScriptWithContent(
            **FilterScriptRead.model_validate(db_script).model_dump(),
            script_content=content
        )

    async def delete_filter_script(
        self,
        db: AsyncSession,
        script_id: str,
        hard_delete: bool = False,
        delete_file: bool = False,
    ) -> bool:
        """
        Delete a filter script.

        Args:
            db: Database session
            script_id: Filter script ID
            hard_delete: Whether to hard delete from database
            delete_file: Whether to delete the script file

        Returns:
            True if deleted successfully
        """
        # Get existing script
        existing = await self.crud_filter_script.get(db=db, id=script_id)
        if not existing:
            return False
        if not hasattr(existing, 'script_path'):
            return False

        # Delete file if requested
        if delete_file and hasattr(existing, 'script_path'):
            existing_script_path = existing.script_path
            full_path = Path(existing_script_path.replace("./", ""))
            if not full_path.exists():
                full_path = self.scripts_base_dir / Path(existing_script_path).name

            try:
                if full_path.exists():
                    full_path.unlink()
                    logger.info(f"Deleted script file {full_path}")
            except Exception as e:
                logger.error(f"Failed to delete script file {full_path}: {e}")
                # Continue with database deletion even if file deletion fails

        # Delete from database
        if hard_delete:
            await self.crud_filter_script.db_delete(db=db, id=script_id)
        else:
            # Soft delete by marking as inactive
            from datetime import UTC, datetime
            # MyPy has issues with optional-only Pydantic models
            # All fields in FilterScriptUpdateInternal are optional except updated_at
            update_data = FilterScriptUpdateInternal(  # type: ignore[call-arg]
                active=False,
                updated_at=datetime.now(UTC)
            )
            await self.crud_filter_script.update(
                db=db,
                id=script_id,
                object=update_data
            )

        # Invalidate cache
        await self._invalidate_cache(script_id)

        logger.info(f"Deleted filter script {script_id} (hard={hard_delete}, file={delete_file})")
        return True

    async def validate_filter_script(
        self,
        db: AsyncSession,
        script_id: str,
        validation_request: FilterScriptValidationRequest,
    ) -> FilterScriptValidationResult:
        """
        Validate a filter script by checking syntax and optionally running a test.

        Args:
            db: Database session
            script_id: Filter script ID
            validation_request: Validation parameters

        Returns:
            Validation result
        """
        # Get script
        existing = await self.crud_filter_script.get(db=db, id=script_id)
        if not existing:
            return FilterScriptValidationResult(
                valid=False,
                errors=["Filter script not found"]
            )
        if not hasattr(existing, 'script_path'):
            return FilterScriptValidationResult(
                valid=False,
                errors=["Filter script has no script_path"]
            )

        # Read script content
        existing_script_path = existing.script_path if hasattr(existing, 'script_path') else ""
        content = await self._read_script_file(existing_script_path)
        if content is None:
            return FilterScriptValidationResult(
                valid=False,
                errors=["Script file not found"]
            )

        errors = []
        warnings = []
        test_output = None
        execution_time_ms = None

        # Validate based on language
        language = existing.language if hasattr(existing, 'language') else 'bash'
        if language == "bash":
            # Check bash syntax
            result = subprocess.run(
                ["bash", "-n", "-"],
                input=content,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                errors.append(f"Bash syntax error: {result.stderr}")

        elif language == "python":
            # Check Python syntax
            try:
                script_path = existing.script_path if hasattr(existing, 'script_path') else 'script.py'
                compile(content, script_path, 'exec')
            except SyntaxError as e:
                errors.append(f"Python syntax error: {str(e)}")

        elif language == "javascript":
            # Basic JavaScript validation (could use node --check if available)
            try:
                # Very basic check - just ensure it's not completely invalid
                if not content.strip():
                    errors.append("Empty JavaScript file")
            except Exception as e:
                errors.append(f"JavaScript validation error: {str(e)}")

        # Run test if input provided
        if validation_request.test_input and not errors:
            try:
                import time
                start_time = time.time()

                # Prepare test input as JSON
                test_input_json = json.dumps(validation_request.test_input)

                # Run script with test input
                if language == "bash":
                    cmd = ["bash", "-"]
                elif language == "python":
                    cmd = ["python3", "-"]
                elif language == "javascript":
                    cmd = ["node", "-"]
                else:
                    warnings.append(f"Unknown language for test execution: {language}")
                    cmd = None

                if cmd:
                    timeout_ms = existing.timeout_ms if hasattr(existing, 'timeout_ms') else 1000
                    result = subprocess.run(
                        cmd,
                        input=content,
                        capture_output=True,
                        text=True,
                        timeout=timeout_ms / 1000,
                        env={**os.environ, "FILTER_INPUT": test_input_json}
                    )
                    test_output = result.stdout
                    if result.returncode != 0:
                        warnings.append(f"Test execution failed: {result.stderr}")

                    execution_time_ms = int((time.time() - start_time) * 1000)

            except subprocess.TimeoutExpired:
                timeout_ms = existing.timeout_ms if hasattr(existing, 'timeout_ms') else 1000
                warnings.append(f"Test execution timed out after {timeout_ms}ms")
            except Exception as e:
                warnings.append(f"Test execution error: {str(e)}")

        # Update validation status in database
        valid = len(errors) == 0
        await self.crud_filter_script.mark_validated(
            db=db,
            script_id=script_id,
            validated=valid,
            validation_errors={"errors": errors, "warnings": warnings} if errors or warnings else None
        )

        return FilterScriptValidationResult(
            valid=valid,
            errors=errors if errors else None,
            warnings=warnings if warnings else None,
            test_output=test_output,
            execution_time_ms=execution_time_ms
        )

    async def list_filter_scripts(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 50,
        filters: Optional[FilterScriptFilter] = None,
        sort: Optional[FilterScriptSort] = None,
    ) -> FilterScriptPagination:
        """
        List filter scripts with pagination.

        Args:
            db: Database session
            page: Page number
            size: Page size
            filters: Filter criteria
            sort: Sort criteria

        Returns:
            Paginated filter scripts
        """
        # Get paginated results from CRUD
        result = await self.crud_filter_script.get_paginated(
            db=db,
            page=page,
            size=size,
            filters=filters,
            sort=sort
        )

        # Convert to read schemas
        items: list[FilterScriptRead] = []
        total: int = 0
        pages: int = 0
        if isinstance(result, dict):
            result_items = result.get("items", [])
            if isinstance(result_items, list):
                items = [
                    FilterScriptRead.model_validate(script)
                    for script in result_items
                ]
            total_val = result.get("total", 0)
            pages_val = result.get("pages", 0)
            if isinstance(total_val, int):
                total = total_val
            if isinstance(pages_val, int):
                pages = pages_val

        return FilterScriptPagination(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=pages
        )

    # Helper methods

    def _get_file_extension(self, language: str) -> str:
        """Get file extension for a language."""
        extensions = {
            "bash": "sh",
            "python": "py",
            "javascript": "js"
        }
        return extensions.get(language.lower(), "txt")

    async def _read_script_file(self, script_path: str) -> Optional[str]:
        """Read script content from filesystem."""
        try:
            # Handle relative path
            full_path = Path(script_path.replace("./", ""))
            if not full_path.exists():
                full_path = self.scripts_base_dir / Path(script_path).name

            if full_path.exists():
                return full_path.read_text()
            else:
                logger.warning(f"Script file not found: {full_path}")
                return None
        except Exception as e:
            logger.error(f"Failed to read script file {script_path}: {e}")
            return None

    async def _cache_filter_script(self, script: Any) -> None:
        """Cache filter script metadata in Redis."""
        if not hasattr(redis_client, '_redis') or not redis_client._redis:
            return

        try:
            # Prepare cache data
            if hasattr(script, 'model_dump'):
                cache_data = script.model_dump(mode='json')
            elif hasattr(script, '__dict__'):
                cache_data = FilterScriptRead.model_validate(script).model_dump(mode='json')
            else:
                cache_data = dict(script)

            # Cache with 1 hour TTL
            cache_key = f"platform:filter_scripts:{script.id}"
            await redis_client.set(
                cache_key,
                json.dumps(cache_data, default=str),
                expiration=3600
            )

            # Also cache by slug for quick lookup
            slug_key = f"platform:filter_scripts:slug:{script.slug}"
            await redis_client.set(slug_key, str(script.id), expiration=3600)

            logger.debug(f"Cached filter script {script.id}")
        except Exception as e:
            logger.error(f"Failed to cache filter script: {e}")

    async def _get_cached_filter_script(self, script_id: str) -> Optional[dict]:
        """Get cached filter script from Redis."""
        if not hasattr(redis_client, '_redis') or not redis_client._redis:
            return None

        try:
            cache_key = f"platform:filter_scripts:{script_id}"
            cached = await redis_client.get(cache_key)
            if cached:
                if isinstance(cached, str):
                    data = json.loads(cached)
                    return dict(data) if data else None
                elif isinstance(cached, dict):
                    return dict(cached)
        except Exception as e:
            logger.error(f"Failed to get cached filter script: {e}")

        return None

    async def _invalidate_cache(self, script_id: str) -> None:
        """Invalidate filter script cache."""
        if not hasattr(redis_client, '_redis') or not redis_client._redis:
            return

        try:
            # Get script to find slug
            cached = await self._get_cached_filter_script(script_id)

            # Delete main cache entry
            cache_key = f"platform:filter_scripts:{script_id}"
            await redis_client.delete(cache_key)

            # Delete slug cache if we have it
            if cached and cached.get("slug"):
                slug_key = f"platform:filter_scripts:slug:{cached['slug']}"
                await redis_client.delete(slug_key)

            logger.debug(f"Invalidated cache for filter script {script_id}")
        except Exception as e:
            logger.error(f"Failed to invalidate filter script cache: {e}")


# Create instance
filter_script_service = FilterScriptService(crud_filter_script)
