"""Tenant isolation middleware for multi-tenant support."""

import uuid
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from ..core.logger import logging
from ..models.audit import UserAuditLog

logger = logging.getLogger(__name__)


class TenantIsolationMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce tenant isolation in a multi-tenant environment.

    This middleware:
    1. Extracts tenant_id from authenticated users
    2. Stores tenant context in request.state for downstream use
    3. Ensures all operations are properly scoped to the tenant
    4. Adds tenant_id to response headers for debugging (in non-production)
    """

    def __init__(self, app: ASGIApp, allow_cross_tenant_superuser: bool = True) -> None:
        """Initialize the tenant isolation middleware.

        Parameters
        ----------
        app : ASGIApp
            The ASGI application instance.
        allow_cross_tenant_superuser : bool
            Whether to allow superusers to access resources across tenants.
            Defaults to True for admin operations.
        """
        super().__init__(app)
        self.allow_cross_tenant_superuser = allow_cross_tenant_superuser

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request and enforce tenant isolation.

        Parameters
        ----------
        request : Request
            The incoming request.
        call_next : RequestResponseEndpoint
            The next middleware or route handler in the processing chain.

        Returns
        -------
        Response
            The response with tenant context applied.
        """
        # Initialize tenant_id as None
        tenant_id: Optional[uuid.UUID] = None
        tenant_slug: Optional[str] = None

        # Try to extract tenant from various sources
        # 1. Check if user is authenticated and has tenant_id
        if hasattr(request.state, "user") and request.state.user:
            user = request.state.user
            if isinstance(user, dict):
                tenant_id = user.get("tenant_id")
                # For superusers, they might operate across tenants
                if user.get("is_superuser") and self.allow_cross_tenant_superuser:
                    # Check if a specific tenant is requested via header or query param
                    requested_tenant = request.headers.get("X-Tenant-ID") or \
                                     request.query_params.get("tenant_id")
                    if requested_tenant:
                        try:
                            requested_tenant_id = uuid.UUID(requested_tenant)
                            user_id = user.get("id")
                            # Only audit if we have a valid user_id
                            if user_id is not None:
                                await self._audit_tenant_switch(
                                    request=request,
                                    user_id=user_id,
                                    original_tenant_id=tenant_id,
                                    target_tenant_id=requested_tenant_id
                                )
                            tenant_id = requested_tenant_id
                            logger.info(f"Superuser {user_id} switched to tenant: {tenant_id}")
                        except ValueError:
                            logger.warning(f"Invalid tenant ID format: {requested_tenant}")

        # 2. For API key authentication (future implementation)
        # This will be populated by API key authentication when implemented
        if not tenant_id and hasattr(request.state, "api_key_tenant_id"):
            tenant_id = request.state.api_key_tenant_id

        # 3. Store tenant context in request state
        if tenant_id:
            request.state.tenant_id = tenant_id
            logger.debug(f"Request tenant context set: {tenant_id}")
        else:
            # For public endpoints or pre-auth requests
            request.state.tenant_id = None

        # Store tenant slug if available (useful for logging and debugging)
        if hasattr(request.state, "tenant_slug"):
            tenant_slug = request.state.tenant_slug

        # Process the request
        response = await call_next(request)

        # Add tenant context to response headers (for debugging, not in production)
        # This helps with debugging multi-tenant issues
        from ..core.config import settings
        if hasattr(settings, "ENVIRONMENT") and settings.ENVIRONMENT != "production":
            if tenant_id:
                response.headers["X-Tenant-ID"] = str(tenant_id)
            if tenant_slug:
                response.headers["X-Tenant-Slug"] = tenant_slug

        return response

    async def _audit_tenant_switch(
        self,
        request: Request,
        user_id: uuid.UUID,
        original_tenant_id: Optional[uuid.UUID],
        target_tenant_id: uuid.UUID
    ) -> None:
        """Create audit log entry for superuser tenant switch.

        Parameters
        ----------
        request : Request
            The incoming request.
        user_id : uuid.UUID
            The superuser's ID.
        original_tenant_id : Optional[uuid.UUID]
            The user's original tenant ID.
        target_tenant_id : uuid.UUID
            The tenant ID being switched to.
        """
        try:
            # Get database session
            from ..core.db.database import async_get_db
            async for db in async_get_db():
                # Extract request metadata
                ip_address = request.client.host if request.client else None
                user_agent = request.headers.get("User-Agent", "")[:500]  # Limit to 500 chars

                # Create audit log entry
                audit_log = UserAuditLog(
                    user_id=user_id,
                    action="tenant_switch",
                    resource_type="tenant",
                    resource_id=str(target_tenant_id),
                    target_tenant_id=target_tenant_id,
                    details={
                        "original_tenant_id": str(original_tenant_id) if original_tenant_id else None,
                        "method": request.method,
                        "path": str(request.url.path),
                        "query_params": dict(request.query_params),
                        "switch_source": "header" if "X-Tenant-ID" in request.headers else "query_param"
                    },
                    ip_address=ip_address,
                    user_agent=user_agent
                )

                db.add(audit_log)
                await db.commit()

                logger.info(
                    f"Audit log created for superuser tenant switch: "
                    f"user={user_id}, from={original_tenant_id}, to={target_tenant_id}"
                )
                break  # Exit after first iteration

        except Exception as e:
            # Log error but don't fail the request
            logger.error(f"Failed to create audit log for tenant switch: {e}")


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Middleware to set tenant context from authenticated user.

    This is a lighter version that just sets the context without enforcement.
    Useful when you want to make tenant_id available but not enforce isolation.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Set tenant context from authenticated user.

        Parameters
        ----------
        request : Request
            The incoming request.
        call_next : RequestResponseEndpoint
            The next middleware or route handler.

        Returns
        -------
        Response
            The response object.
        """
        # This will be populated by the authentication dependency
        # The actual user object comes from get_current_user dependency
        # We just ensure the tenant context is available in request.state

        # Check if we have an authenticated user with tenant_id
        user = getattr(request.state, "user", None)
        if user and isinstance(user, dict) and "tenant_id" in user:
            request.state.tenant_id = user["tenant_id"]

            # Also get tenant details if available
            if "tenant" in user:
                request.state.tenant = user["tenant"]

        return await call_next(request)
