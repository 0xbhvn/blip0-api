"""
Example schemas for demonstrating advanced patterns.

This module contains example schemas that extend base schemas
to demonstrate features like caching integration. These are not
part of the production code but serve as reference implementations.
"""

from .monitor_cached_example import MonitorDelete, MonitorUpdateInternal

__all__ = ["MonitorDelete", "MonitorUpdateInternal"]
