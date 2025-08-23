"""
Enhanced CRUD operations for filter script management.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import logging
from ..core.redis_client import redis_client
from ..models.filter_script import FilterScript
from ..schemas.filter_script import (
    FilterScriptCreate,
    FilterScriptCreateInternal,
    FilterScriptDelete,
    FilterScriptFilter,
    FilterScriptRead,
    FilterScriptSort,
    FilterScriptUpdate,
    FilterScriptUpdateInternal,
    FilterScriptValidationRequest,
    FilterScriptValidationResult,
    FilterScriptWithContent,
)
from .base import EnhancedCRUD

logger = logging.getLogger(__name__)


class CRUDFilterScript(
    EnhancedCRUD[
        FilterScript,
        FilterScriptCreateInternal,
        FilterScriptUpdate,
        FilterScriptUpdateInternal,
        FilterScriptDelete,
        FilterScriptRead,
        FilterScriptFilter,
        FilterScriptSort
    ]
):
    """
    Enhanced CRUD operations for FilterScript model.
    Manages filter script metadata in database while actual scripts are in filesystem.
    """

    def __init__(self, model: type[FilterScript]):
        """Initialize filter script CRUD with filesystem management."""
        super().__init__(model)
        # Base directory for filter scripts (relative to project root)
        self.scripts_base_dir = Path("config/filters")
        self.scripts_base_dir.mkdir(parents=True, exist_ok=True)

    async def get_by_slug(
        self,
        db: AsyncSession,
        slug: str,
        tenant_id: Optional[str] = None,
    ) -> Optional[FilterScript]:
        """
        Get a filter script by slug.

        Args:
            db: Database session
            slug: Filter script slug
            tenant_id: Optional tenant ID for filtering

        Returns:
            FilterScript if found, None otherwise
        """
        stmt = select(self.model).where(self.model.slug == slug)
        if tenant_id:
            stmt = stmt.where(self.model.tenant_id == tenant_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_language(
        self,
        db: AsyncSession,
        language: str,
        tenant_id: Optional[str] = None,
        active_only: bool = True,
    ) -> list[FilterScript]:
        """
        Get all filter scripts for a specific language.

        Args:
            db: Database session
            language: Script language (bash, python, javascript)
            tenant_id: Optional tenant ID for filtering
            active_only: Only return active scripts

        Returns:
            List of filter scripts
        """
        stmt = select(self.model).where(self.model.language == language.lower())

        if tenant_id:
            stmt = stmt.where(self.model.tenant_id == tenant_id)

        if active_only:
            stmt = stmt.where(self.model.active.is_(True))

        stmt = stmt.order_by(self.model.name)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_active_scripts(
        self,
        db: AsyncSession,
        tenant_id: Optional[str] = None,
    ) -> list[FilterScript]:
        """
        Get all active filter scripts.

        Args:
            db: Database session
            tenant_id: Optional tenant ID for filtering

        Returns:
            List of active filter scripts
        """
        stmt = (
            select(self.model)
            .where(self.model.active.is_(True))
            .order_by(self.model.name)
        )

        if tenant_id:
            stmt = stmt.where(self.model.tenant_id == tenant_id)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def mark_validated(
        self,
        db: AsyncSession,
        script_id: str,
        validated: bool = True,
        validation_errors: Optional[dict] = None,
    ) -> Optional[FilterScript]:
        """
        Mark a filter script as validated or invalid.

        Args:
            db: Database session
            script_id: Filter script ID
            validated: Whether the script is valid
            validation_errors: Validation errors if invalid

        Returns:
            Updated filter script if found
        """
        from datetime import UTC, datetime

        script = await self.get(db=db, id=script_id)
        if not script or not isinstance(script, FilterScript):
            return None

        script.validated = validated
        script.validation_errors = validation_errors
        script.last_validated_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(script)

        return script

    async def update_file_metadata(
        self,
        db: AsyncSession,
        script_id: str,
        file_size_bytes: int,
        file_hash: str,
    ) -> Optional[FilterScript]:
        """
        Update file metadata for a filter script.

        Args:
            db: Database session
            script_id: Filter script ID
            file_size_bytes: Size of the script file
            file_hash: SHA256 hash of the file content

        Returns:
            Updated filter script if found
        """
        script = await self.get(db=db, id=script_id)
        if not script or not isinstance(script, FilterScript):
            return None

        script.file_size_bytes = file_size_bytes
        script.file_hash = file_hash

        await db.commit()
        await db.refresh(script)

        return script

    # File system operations
    def _get_file_extension(self, language: str) -> str:
        """Get file extension based on script language."""
        extensions = {
            "bash": "sh",
            "python": "py",
            "javascript": "js",
        }
        return extensions.get(language.lower(), "txt")

    async def _read_script_file(self, script_path: str) -> Optional[str]:
        """Read script content from filesystem."""
        try:
            full_path = self.scripts_base_dir / Path(script_path).name
            if full_path.exists():
                return full_path.read_text()
            else:
                # Try legacy path without base_dir
                legacy_path = Path(script_path)
                if legacy_path.exists():
                    return legacy_path.read_text()
                logger.warning(f"Script file not found: {script_path}")
                return None
        except Exception as e:
            logger.error(f"Failed to read script file {script_path}: {e}")
            return None

    # Redis caching operations
    async def _cache_filter_script(self, script: Any, tenant_id: str) -> None:
        """Cache filter script in Redis for fast access."""
        cache_key = f"tenant:{tenant_id}:filter_script:{script.id}"
        script_data = FilterScriptRead.model_validate(script).model_dump_json()

        try:
            await redis_client.set(
                cache_key,
                script_data,
                expiration=3600  # 1 hour TTL
            )
            logger.debug(f"Cached filter script {script.id} for tenant {tenant_id}")
        except Exception as e:
            logger.warning(f"Failed to cache filter script: {e}")

    async def _get_cached_filter_script(self, script_id: str, tenant_id: str) -> Optional[dict[str, Any]]:
        """Get cached filter script from Redis."""
        cache_key = f"tenant:{tenant_id}:filter_script:{script_id}"
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)  # type: ignore[no-any-return]
        except Exception as e:
            logger.warning(f"Failed to get cached filter script: {e}")
        return None

    async def _invalidate_cache(self, script_id: str, tenant_id: str) -> None:
        """Invalidate cached filter script."""
        cache_key = f"tenant:{tenant_id}:filter_script:{script_id}"
        try:
            await redis_client.delete(cache_key)
            logger.debug(f"Invalidated cache for filter script {script_id}")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")

    # Enhanced CRUD operations with filesystem and caching
    async def create_with_tenant(
        self,
        db: AsyncSession,
        obj_in: FilterScriptCreate,
        tenant_id: str,
    ) -> FilterScriptWithContent:
        """
        Create a new filter script with filesystem storage and caching.

        Args:
            db: Database session
            obj_in: Filter script creation data
            tenant_id: Tenant ID

        Returns:
            Created filter script with content
        """
        # Calculate file metadata first
        file_size_bytes = len(obj_in.script_content.encode())
        file_hash = hashlib.sha256(obj_in.script_content.encode()).hexdigest()

        # Generate script filename based on tenant, slug and language
        script_filename = f"{tenant_id}_{obj_in.slug}.{self._get_file_extension(obj_in.language)}"
        script_path = f"./config/filters/{script_filename}"

        # Create database record FIRST to check constraints
        script_internal = FilterScriptCreateInternal(
            **obj_in.model_dump(exclude={"script_content"}),
            script_path=script_path,
            file_size_bytes=file_size_bytes,
            file_hash=file_hash,
        )

        db_script = await self.create(
            db=db,
            object=script_internal
        )

        # Only write file after database success
        full_path = self.scripts_base_dir / script_filename
        try:
            full_path.write_text(obj_in.script_content)
            # Set proper permissions (644 - read for all, write for owner only)
            os.chmod(full_path, 0o644)
        except Exception as e:
            # Rollback database record if file write fails
            try:
                await self.db_delete(db=db, id=str(db_script.id))
            except Exception:
                pass  # Best effort cleanup
            logger.error(f"Failed to write script file {full_path}: {e}")
            raise ValueError(f"Failed to save script file: {str(e)}")

        # Write-through to Redis for fast access
        await self._cache_filter_script(db_script, tenant_id)

        logger.info(f"Created filter script {db_script.slug} for tenant {tenant_id}")

        # Return with content
        return FilterScriptWithContent(
            **FilterScriptRead.model_validate(db_script).model_dump(),
            script_content=obj_in.script_content
        )

    async def get_with_cache(
        self,
        db: AsyncSession,
        script_id: str,
        tenant_id: str,
        include_content: bool = False,
    ) -> Optional[Union[FilterScriptRead, FilterScriptWithContent]]:
        """
        Get a filter script by ID with caching.

        Args:
            db: Database session
            script_id: Filter script ID
            tenant_id: Tenant ID
            include_content: Whether to include actual script content

        Returns:
            Filter script if found
        """
        # Try cache first
        cached = await self._get_cached_filter_script(script_id, tenant_id)
        if cached:
            logger.debug(f"Cache hit for filter script {script_id}")
            if include_content:
                script_path = cached.get("script_path", "")
                if script_path:
                    content = await self._read_script_file(script_path)
                    return FilterScriptWithContent(**cached, script_content=content)
            return FilterScriptRead(**cached)

        # Fallback to database
        db_script = await self.get(db=db, id=script_id)
        if not db_script or not isinstance(db_script, FilterScript):
            return None
        if str(db_script.tenant_id) != tenant_id:
            return None

        # Refresh cache on cache miss
        await self._cache_filter_script(db_script, tenant_id)

        if include_content and hasattr(db_script, 'script_path'):
            content = await self._read_script_file(str(db_script.script_path))
            return FilterScriptWithContent(
                **FilterScriptRead.model_validate(db_script).model_dump(),
                script_content=content
            )

        return FilterScriptRead.model_validate(db_script)

    async def update_with_tenant(
        self,
        db: AsyncSession,
        script_id: str,
        obj_in: FilterScriptUpdate,
        tenant_id: str,
    ) -> Optional[FilterScriptWithContent]:
        """
        Update a filter script with cache invalidation.

        Args:
            db: Database session
            script_id: Filter script ID
            obj_in: Update data
            tenant_id: Tenant ID

        Returns:
            Updated filter script if found
        """
        # Get existing script
        existing = await self.get(db=db, id=script_id)
        if not existing or not isinstance(existing, FilterScript):
            return None
        if str(existing.tenant_id) != tenant_id:
            return None
        if not hasattr(existing, 'script_path'):
            return None

        # Calculate file metadata if content is updated
        update_internal_data = obj_in.model_dump(exclude={"script_content"}, exclude_unset=True)

        if obj_in.script_content is not None:
            file_size_bytes = len(obj_in.script_content.encode())
            file_hash = hashlib.sha256(obj_in.script_content.encode()).hexdigest()
            update_internal_data["file_size_bytes"] = file_size_bytes
            update_internal_data["file_hash"] = file_hash

        # Handle slug change - need to rename file
        if obj_in.slug and obj_in.slug != existing.slug:
            old_path = Path(existing.script_path)
            new_filename = f"{tenant_id}_{obj_in.slug}{old_path.suffix}"
            new_path = f"./config/filters/{new_filename}"
            update_internal_data["script_path"] = new_path

        # Update database
        update_internal = FilterScriptUpdateInternal(**update_internal_data)
        updated = await self.update(db=db, object=update_internal, id=script_id)

        if not updated:
            return None

        # Update file if content changed
        if obj_in.script_content is not None:
            script_path = updated.get('script_path') if isinstance(updated, dict) else updated.script_path
            if not script_path:
                raise ValueError("Script path not found in updated record")
            full_path = self.scripts_base_dir / Path(script_path).name
            try:
                full_path.write_text(obj_in.script_content)
                os.chmod(full_path, 0o644)
            except Exception as e:
                logger.error(f"Failed to update script file: {e}")
                raise ValueError(f"Failed to update script file: {str(e)}")

        # Handle file rename if slug changed
        if obj_in.slug and obj_in.slug != existing.slug:
            old_script_path = existing.get('script_path') if isinstance(existing, dict) else existing.script_path
            new_script_path = updated.get('script_path') if isinstance(updated, dict) else updated.script_path
            if old_script_path and new_script_path:
                old_full_path = self.scripts_base_dir / Path(old_script_path).name
                new_full_path = self.scripts_base_dir / Path(new_script_path).name
                try:
                    if old_full_path.exists():
                        old_full_path.rename(new_full_path)
                except Exception as e:
                    logger.error(f"Failed to rename script file: {e}")

        # Invalidate cache
        await self._invalidate_cache(script_id, tenant_id)

        # Return with content
        updated_script_path = updated.get('script_path') if isinstance(updated, dict) else updated.script_path
        if not updated_script_path:
            raise ValueError("Script path not found in updated record")
        if obj_in.script_content is None:
            content = await self._read_script_file(updated_script_path)
        else:
            content = obj_in.script_content
        return FilterScriptWithContent(
            **FilterScriptRead.model_validate(updated).model_dump(),
            script_content=content
        )

    async def delete_with_tenant(
        self,
        db: AsyncSession,
        script_id: str,
        tenant_id: str,
        is_hard_delete: bool = False,
        delete_file: bool = False,
    ) -> bool:
        """
        Delete a filter script with cache invalidation.

        Args:
            db: Database session
            script_id: Filter script ID
            tenant_id: Tenant ID
            is_hard_delete: If True, permanently delete
            delete_file: If True, also delete the script file

        Returns:
            True if deleted, False if not found
        """
        # Get existing script
        existing = await self.get(db=db, id=script_id)
        if not existing or not isinstance(existing, FilterScript):
            return False
        if str(existing.tenant_id) != tenant_id:
            return False

        # Delete from database
        await self.delete(db=db, id=script_id, is_hard_delete=is_hard_delete)

        # Delete file if requested
        if delete_file and hasattr(existing, 'script_path'):
            full_path = self.scripts_base_dir / Path(existing.script_path).name
            try:
                if full_path.exists():
                    full_path.unlink()
                    logger.info(f"Deleted script file: {full_path}")
            except Exception as e:
                logger.error(f"Failed to delete script file: {e}")

        # Invalidate cache
        await self._invalidate_cache(script_id, tenant_id)

        logger.info(f"Deleted filter script {script_id} for tenant {tenant_id}")
        return True

    async def validate_filter_script(
        self,
        db: AsyncSession,
        validation_request: FilterScriptValidationRequest,
    ) -> FilterScriptValidationResult:
        """
        Validate a filter script by testing execution.

        Args:
            db: Database session
            validation_request: Validation request with script ID and options

        Returns:
            Validation result with status and any errors
        """
        from datetime import UTC, datetime

        script_id = str(validation_request.script_id)
        script = await self.get(db=db, id=script_id)

        if not script:
            return FilterScriptValidationResult(
                script_id=validation_request.script_id,
                is_valid=False,
                errors=["Script not found"],
                warnings=[],
                execution_time_ms=0,
                validated_at=datetime.now(UTC),
            )

        errors = []
        warnings = []
        execution_time_ms = 0

        # Read script content
        script_path = script.get('script_path') if isinstance(script, dict) else script.script_path
        if not script_path:
            errors.append("Script path not found")
            return FilterScriptValidationResult(
                script_id=validation_request.script_id,
                is_valid=False,
                errors=errors,
                warnings=[],
                execution_time_ms=0,
                validated_at=datetime.now(UTC),
            )

        content = await self._read_script_file(script_path)
        if not content:
            errors.append("Script file not found or empty")
        elif validation_request.test_execution:
            # Test script execution
            try:
                import time
                start_time = time.time()

                # Prepare command based on language
                language = script.get('language') if isinstance(script, dict) else script.language
                if language == "bash":
                    cmd = ["bash", "-c", content]
                elif language == "python":
                    cmd = ["python3", "-c", content]
                elif language == "javascript":
                    cmd = ["node", "-e", content]
                else:
                    errors.append(f"Unsupported language: {language}")
                    cmd = None

                if cmd:
                    # Run with timeout
                    timeout_ms = script.get('timeout_ms', 1000) if isinstance(script, dict) else script.timeout_ms
                    timeout_seconds = timeout_ms / 1000.0
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout_seconds,
                        check=False,
                    )

                    execution_time_ms = int((time.time() - start_time) * 1000)

                    if result.returncode != 0:
                        errors.append(f"Script execution failed: {result.stderr}")
                    elif result.stderr:
                        warnings.append(f"Script produced stderr output: {result.stderr}")

                    if execution_time_ms > timeout_ms:
                        warnings.append(
                            f"Script execution time ({execution_time_ms}ms) "
                            f"exceeds timeout ({timeout_ms}ms)"
                        )

            except subprocess.TimeoutExpired:
                errors.append(f"Script execution timeout ({timeout_ms}ms)")
            except Exception as e:
                errors.append(f"Script validation failed: {str(e)}")

        # Check basic syntax based on language
        if validation_request.check_syntax and content:
            language = script.get('language') if isinstance(script, dict) else script.language
            if language == "python":
                try:
                    compile(content, script_path, 'exec')
                except SyntaxError as e:
                    errors.append(f"Python syntax error: {e}")
            elif language == "bash":
                # Basic bash syntax check
                result = subprocess.run(
                    ["bash", "-n"],
                    input=content,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    errors.append(f"Bash syntax error: {result.stderr}")

        is_valid = len(errors) == 0

        # Update validation status in database
        await self.mark_validated(
            db=db,
            script_id=script_id,
            validated=is_valid,
            validation_errors={"errors": errors, "warnings": warnings} if errors else None,
        )

        return FilterScriptValidationResult(
            script_id=validation_request.script_id,
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            execution_time_ms=execution_time_ms,
            validated_at=datetime.now(UTC),
        )


# Create instance
crud_filter_script = CRUDFilterScript(FilterScript)
