"""
Example schemas for demonstrating cached monitor CRUD operations.
These schemas extend the base monitor schemas to show write-through caching patterns.
"""

from pydantic import BaseModel

from ..monitor import MonitorUpdate


class MonitorDelete(BaseModel):
    """Schema for deleting a Monitor.

    Required by FastCRUD but can be empty for this example.
    """
    pass


class MonitorUpdateInternal(MonitorUpdate):
    """Schema for internal Monitor updates.

    Used by FastCRUD for internal update operations.
    """
    pass
