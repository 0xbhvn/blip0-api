"""
Base CRUD operations with enhanced pagination, filtering, and sorting capabilities.
"""

from typing import Any, Generic, Optional, TypeVar

from fastcrud import FastCRUD
from pydantic import BaseModel
from sqlalchemy import Select, and_, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

ModelType = TypeVar("ModelType", bound=DeclarativeBase)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)
UpdateSchemaType = TypeVar("UpdateSchemaType", bound=BaseModel)
UpdateInternalSchemaType = TypeVar("UpdateInternalSchemaType", bound=BaseModel)
DeleteSchemaType = TypeVar("DeleteSchemaType", bound=BaseModel)
ReadSchemaType = TypeVar("ReadSchemaType", bound=BaseModel)
FilterSchemaType = TypeVar("FilterSchemaType", bound=BaseModel)
SortSchemaType = TypeVar("SortSchemaType", bound=BaseModel)


class EnhancedCRUD(
    FastCRUD[
        ModelType,
        CreateSchemaType,
        UpdateSchemaType,
        UpdateInternalSchemaType,
        DeleteSchemaType,
        ReadSchemaType
    ],
    Generic[
        ModelType,
        CreateSchemaType,
        UpdateSchemaType,
        UpdateInternalSchemaType,
        DeleteSchemaType,
        ReadSchemaType,
        FilterSchemaType,
        SortSchemaType
    ]
):
    """
    Enhanced CRUD operations with advanced filtering, sorting, and pagination.
    Extends FastCRUD with additional capabilities for complex queries.
    """

    def __init__(self, model: type[ModelType]) -> None:
        """Initialize the enhanced CRUD with a model."""
        super().__init__(model)
        self.model = model

    def apply_filters(
        self,
        query: Select,
        filters: Optional[FilterSchemaType]
    ) -> Select:
        """
        Apply filters to a query based on filter schema.

        Args:
            query: SQLAlchemy select query
            filters: Filter schema with filter criteria

        Returns:
            Modified query with filters applied
        """
        if not filters:
            return query

        conditions = []

        # Iterate through filter fields
        for field_name, field_value in filters.model_dump(exclude_unset=True).items():
            if field_value is None:
                continue

            # Handle different filter types
            if field_name.endswith("_after"):
                # Date/time after filter
                actual_field = field_name[:-6]  # Remove "_after"
                if hasattr(self.model, actual_field):
                    conditions.append(
                        getattr(self.model, actual_field) >= field_value)

            elif field_name.endswith("_before"):
                # Date/time before filter
                actual_field = field_name[:-7]  # Remove "_before"
                if hasattr(self.model, actual_field):
                    conditions.append(
                        getattr(self.model, actual_field) <= field_value)

            elif field_name.endswith("_gte"):
                # Greater than or equal filter
                actual_field = field_name[:-4]  # Remove "_gte"
                if hasattr(self.model, actual_field):
                    conditions.append(
                        getattr(self.model, actual_field) >= field_value)

            elif field_name.endswith("_lte"):
                # Less than or equal filter
                actual_field = field_name[:-4]  # Remove "_lte"
                if hasattr(self.model, actual_field):
                    conditions.append(
                        getattr(self.model, actual_field) <= field_value)

            elif field_name.endswith("_in"):
                # In list filter
                actual_field = field_name[:-3]  # Remove "_in"
                if hasattr(self.model, actual_field) and isinstance(field_value, list):
                    conditions.append(
                        getattr(self.model, actual_field).in_(field_value))

            elif field_name.startswith("has_"):
                # Boolean existence check (e.g., has_error checks if error field is not null)
                actual_field = field_name[4:]  # Remove "has_"
                if field_value:
                    conditions.append(
                        getattr(self.model, f"last_{actual_field}").isnot(None))
                else:
                    conditions.append(
                        getattr(self.model, f"last_{actual_field}").is_(None))

            elif hasattr(self.model, field_name):
                # Direct field match
                model_field = getattr(self.model, field_name)

                # Check if it's a string field for partial matching
                if isinstance(field_value, str) and hasattr(model_field.property.columns[0].type, "python_type"):
                    if model_field.property.columns[0].type.python_type is str:
                        # Use LIKE for string fields (partial match)
                        # Exact match for these fields
                        if field_name in ["slug", "email", "url"]:
                            conditions.append(model_field == field_value)
                        else:
                            conditions.append(
                                model_field.ilike(f"%{field_value}%"))
                    else:
                        conditions.append(model_field == field_value)
                else:
                    conditions.append(model_field == field_value)

        if conditions:
            query = query.where(and_(*conditions))

        return query

    def apply_sorting(
        self,
        query: Select,
        sort: Optional[SortSchemaType]
    ) -> Select:
        """
        Apply sorting to a query based on sort schema.

        Args:
            query: SQLAlchemy select query
            sort: Sort schema with field and order

        Returns:
            Modified query with sorting applied
        """
        if not sort:
            # Default sorting by created_at desc
            if hasattr(self.model, "created_at"):
                # type: ignore[arg-type]
                return query.order_by(desc(getattr(self.model, "created_at")))
            return query

        # type: ignore[attr-defined]
        field_name = getattr(sort, "field", "created_at")
        order = getattr(sort, "order", "desc")  # type: ignore[attr-defined]

        if hasattr(self.model, field_name):
            model_field = getattr(self.model, field_name)
            if order == "asc":
                query = query.order_by(asc(model_field))
            else:
                query = query.order_by(desc(model_field))

        return query

    async def get_paginated(
        self,
        db: AsyncSession,
        page: int = 1,
        size: int = 50,
        filters: Optional[FilterSchemaType] = None,
        sort: Optional[SortSchemaType] = None,
        tenant_id: Optional[Any] = None
    ) -> dict[str, Any]:
        """
        Get paginated results with filtering and sorting.

        Args:
            db: Database session
            page: Page number (1-indexed)
            size: Page size
            filters: Filter criteria
            sort: Sort criteria
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            Dictionary with items, total, page, size, and pages
        """
        # Build base query
        query = select(self.model)

        # Apply tenant filter if provided
        if tenant_id and hasattr(self.model, "tenant_id"):
            # type: ignore[arg-type]
            query = query.where(getattr(self.model, "tenant_id") == tenant_id)

        # Apply filters
        query = self.apply_filters(query, filters)

        # Get total count
        count_query = select(func.count()).select_from(self.model)
        if tenant_id and hasattr(self.model, "tenant_id"):
            count_query = count_query.where(
                # type: ignore[arg-type]
                getattr(self.model, "tenant_id") == tenant_id)
        count_query = self.apply_filters(count_query, filters)

        result = await db.execute(count_query)
        total = result.scalar() or 0

        # Apply sorting
        query = self.apply_sorting(query, sort)

        # Apply pagination
        offset = (page - 1) * size
        query = query.limit(size).offset(offset)

        # Execute query
        result = await db.execute(query)
        items = result.scalars().all()

        # Calculate pages
        pages = (total + size - 1) // size if size > 0 else 0

        return {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "pages": pages
        }

    async def bulk_create(
        self,
        db: AsyncSession,
        objects: list[CreateSchemaType]
    ) -> list[ModelType]:
        """
        Create multiple objects in a single transaction.

        Args:
            db: Database session
            objects: List of objects to create

        Returns:
            List of created model instances
        """
        instances = []
        for obj_data in objects:
            instance = self.model(**obj_data.model_dump())
            db.add(instance)
            instances.append(instance)

        await db.flush()
        return instances

    async def bulk_update(
        self,
        db: AsyncSession,
        ids: list[Any],
        update_data: UpdateSchemaType,
        tenant_id: Optional[Any] = None
    ) -> list[ModelType]:
        """
        Update multiple objects by their IDs.

        Args:
            db: Database session
            ids: List of object IDs to update
            update_data: Update data
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            List of updated model instances
        """
        query = select(self.model).where(
            getattr(self.model, "id").in_(ids))  # type: ignore[arg-type]

        # Apply tenant filter if provided
        if tenant_id and hasattr(self.model, "tenant_id"):
            # type: ignore[arg-type]
            query = query.where(getattr(self.model, "tenant_id") == tenant_id)

        result = await db.execute(query)
        instances = list(result.scalars().all())

        update_dict = update_data.model_dump(exclude_unset=True)
        for instance in instances:
            for key, value in update_dict.items():
                setattr(instance, key, value)

        await db.flush()
        return instances

    async def bulk_delete(
        self,
        db: AsyncSession,
        ids: list[Any],
        is_hard_delete: bool = False,
        tenant_id: Optional[Any] = None
    ) -> int:
        """
        Delete multiple objects by their IDs.

        Args:
            db: Database session
            ids: List of object IDs to delete
            is_hard_delete: If True, permanently delete; if False, soft delete
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            Number of deleted objects
        """
        query = select(self.model).where(
            getattr(self.model, "id").in_(ids))  # type: ignore[arg-type]

        # Apply tenant filter if provided
        if tenant_id and hasattr(self.model, "tenant_id"):
            # type: ignore[arg-type]
            query = query.where(getattr(self.model, "tenant_id") == tenant_id)

        result = await db.execute(query)
        instances = list(result.scalars().all())

        if is_hard_delete:
            for instance in instances:
                await db.delete(instance)
        else:
            # Soft delete if the model supports it
            if hasattr(self.model, "is_deleted"):
                for instance in instances:
                    # type: ignore[attr-defined]
                    setattr(instance, "is_deleted", True)
                    if hasattr(instance, "deleted_at"):
                        from datetime import UTC, datetime
                        # type: ignore[attr-defined]
                        setattr(instance, "deleted_at", datetime.now(UTC))
            else:
                # If no soft delete support, do hard delete
                for instance in instances:
                    await db.delete(instance)

        await db.flush()
        return len(instances)

    async def exists(
        self,
        db: AsyncSession,
        **kwargs: Any
    ) -> bool:
        """
        Check if an object exists with the given criteria.

        Args:
            db: Database session
            **kwargs: Field criteria to check

        Returns:
            True if object exists, False otherwise
        """
        query = select(func.count()).select_from(self.model)

        for key, value in kwargs.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)

        result = await db.execute(query)
        count = result.scalar() or 0
        return count > 0

    async def count_filtered(
        self,
        db: AsyncSession,
        filters: Optional[FilterSchemaType] = None,
        tenant_id: Optional[Any] = None
    ) -> int:
        """
        Count objects matching the given criteria.

        Args:
            db: Database session
            filters: Filter criteria
            tenant_id: Optional tenant ID for multi-tenant filtering

        Returns:
            Count of matching objects
        """
        query = select(func.count()).select_from(self.model)

        # Apply tenant filter if provided
        if tenant_id and hasattr(self.model, "tenant_id"):
            # type: ignore[arg-type]
            query = query.where(getattr(self.model, "tenant_id") == tenant_id)

        # Apply filters
        query = self.apply_filters(query, filters)

        result = await db.execute(query)
        return result.scalar() or 0
