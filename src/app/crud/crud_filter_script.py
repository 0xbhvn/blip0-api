"""
Enhanced CRUD operations for filter script management.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.filter_script import FilterScript
from ..schemas.filter_script import (
    FilterScriptCreateInternal,
    FilterScriptDelete,
    FilterScriptFilter,
    FilterScriptRead,
    FilterScriptSort,
    FilterScriptUpdate,
    FilterScriptUpdateInternal,
)
from .base import EnhancedCRUD


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

    async def get_by_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Optional[FilterScript]:
        """
        Get a filter script by slug.

        Args:
            db: Database session
            slug: Filter script slug

        Returns:
            FilterScript if found, None otherwise
        """
        stmt = select(self.model).where(self.model.slug == slug)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_language(
        self,
        db: AsyncSession,
        language: str,
        active_only: bool = True,
    ) -> list[FilterScript]:
        """
        Get all filter scripts for a specific language.

        Args:
            db: Database session
            language: Script language (bash, python, javascript)
            active_only: Only return active scripts

        Returns:
            List of filter scripts
        """
        stmt = select(self.model).where(self.model.language == language.lower())

        if active_only:
            stmt = stmt.where(self.model.active.is_(True))

        stmt = stmt.order_by(self.model.name)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_active_scripts(
        self,
        db: AsyncSession,
    ) -> list[FilterScript]:
        """
        Get all active filter scripts.

        Args:
            db: Database session

        Returns:
            List of active filter scripts
        """
        stmt = (
            select(self.model)
            .where(self.model.active.is_(True))
            .order_by(self.model.name)
        )

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


# Create instance
crud_filter_script = CRUDFilterScript(FilterScript)
