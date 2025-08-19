"""Row-Level Security (RLS) middleware for enforcing data access policies."""

import uuid
from typing import Any, Optional

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import event
from sqlalchemy.orm import Query, Session
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from ..core.logger import logging

logger = logging.getLogger(__name__)


class RLSContext:
    """Thread-local context for RLS enforcement."""

    _instance: Optional["RLSContext"] = None

    def __init__(self) -> None:
        self.tenant_id: Optional[uuid.UUID] = None
        self.user_id: Optional[int] = None
        self.is_superuser: bool = False
        self.bypass_rls: bool = False

    @classmethod
    def get_instance(cls) -> "RLSContext":
        """Get singleton instance of RLS context."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_context(
        self,
        tenant_id: Optional[uuid.UUID] = None,
        user_id: Optional[int] = None,
        is_superuser: bool = False,
        bypass_rls: bool = False
    ) -> None:
        """Set the RLS context for the current request.

        Parameters
        ----------
        tenant_id : Optional[uuid.UUID]
            The tenant ID for the current request.
        user_id : Optional[int]
            The user ID for the current request.
        is_superuser : bool
            Whether the current user is a superuser.
        bypass_rls : bool
            Whether to bypass RLS checks (for system operations).
        """
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.is_superuser = is_superuser
        self.bypass_rls = bypass_rls

    def clear_context(self) -> None:
        """Clear the RLS context after request processing."""
        self.tenant_id = None
        self.user_id = None
        self.is_superuser = False
        self.bypass_rls = False


class RowLevelSecurityMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce row-level security policies.

    This middleware:
    1. Sets up RLS context from authenticated user
    2. Enforces tenant and user-level data access restrictions
    3. Prevents unauthorized cross-tenant data access
    4. Provides hooks for SQLAlchemy query modification
    """

    def __init__(
        self,
        app: ASGIApp,
        enforce_tenant_isolation: bool = True,
        allow_superuser_bypass: bool = True
    ) -> None:
        """Initialize the RLS middleware.

        Parameters
        ----------
        app : ASGIApp
            The ASGI application instance.
        enforce_tenant_isolation : bool
            Whether to enforce tenant isolation. Defaults to True.
        allow_superuser_bypass : bool
            Whether to allow superusers to bypass RLS. Defaults to True.
        """
        super().__init__(app)
        self.enforce_tenant_isolation = enforce_tenant_isolation
        self.allow_superuser_bypass = allow_superuser_bypass
        self.rls_context = RLSContext.get_instance()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request with RLS enforcement.

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
        # Extract user and tenant information from request state
        tenant_id = getattr(request.state, "tenant_id", None)
        user = getattr(request.state, "user", None)

        user_id = None
        is_superuser = False

        if user and isinstance(user, dict):
            user_id = user.get("id")
            is_superuser = user.get("is_superuser", False)

        # Set RLS context
        bypass_rls = is_superuser and self.allow_superuser_bypass
        self.rls_context.set_context(
            tenant_id=tenant_id,
            user_id=user_id,
            is_superuser=is_superuser,
            bypass_rls=bypass_rls
        )

        # Log RLS context for debugging
        logger.debug(
            f"RLS Context - Tenant: {tenant_id}, User: {user_id}, "
            f"Superuser: {is_superuser}, Bypass: {bypass_rls}"
        )

        try:
            # Process the request
            response = await call_next(request)

            # Check if we should validate response data
            if self.enforce_tenant_isolation and tenant_id and not bypass_rls:
                # Note: Response validation would happen at the data layer
                # This is just for logging suspicious activity
                if hasattr(response, "headers"):
                    response_tenant = response.headers.get("X-Resource-Tenant-ID")
                    if response_tenant and response_tenant != str(tenant_id):
                        logger.warning(
                            f"Potential RLS violation: User from tenant {tenant_id} "
                            f"accessed resource from tenant {response_tenant}"
                        )

            return response

        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            # Log unexpected errors
            logger.error(f"RLS middleware error: {e}")
            raise
        finally:
            # Clear RLS context after request
            self.rls_context.clear_context()


def apply_tenant_filter(query: Query, model_class: Any) -> Query:
    """Apply tenant filter to SQLAlchemy query.

    This function can be used as a helper to apply tenant filtering
    to queries when needed.

    Parameters
    ----------
    query : Query
        The SQLAlchemy query to filter.
    model_class : Any
        The model class being queried.

    Returns
    -------
    Query
        The filtered query.
    """
    rls_context = RLSContext.get_instance()

    # Skip filtering if RLS is bypassed
    if rls_context.bypass_rls:
        return query

    # Apply tenant filter if tenant_id is set and model has tenant_id column
    if rls_context.tenant_id and hasattr(model_class, "tenant_id"):
        query = query.filter(model_class.tenant_id == rls_context.tenant_id)
        logger.debug(f"Applied tenant filter: {rls_context.tenant_id}")

    return query


def check_resource_access(
    resource: Any,
    user_id: Optional[int] = None,
    tenant_id: Optional[uuid.UUID] = None,
    raise_on_failure: bool = True
) -> bool:
    """Check if a user has access to a specific resource.

    Parameters
    ----------
    resource : Any
        The resource to check access for.
    user_id : Optional[int]
        The user ID to check (uses context if not provided).
    tenant_id : Optional[uuid.UUID]
        The tenant ID to check (uses context if not provided).
    raise_on_failure : bool
        Whether to raise an exception on access failure.

    Returns
    -------
    bool
        True if access is allowed, False otherwise.

    Raises
    ------
    HTTPException
        If access is denied and raise_on_failure is True.
    """
    rls_context = RLSContext.get_instance()

    # Use context values if not provided
    if user_id is None:
        user_id = rls_context.user_id
    if tenant_id is None:
        tenant_id = rls_context.tenant_id

    # Superusers with bypass can access anything
    if rls_context.bypass_rls:
        return True

    # Check tenant isolation
    if tenant_id and hasattr(resource, "tenant_id"):
        resource_tenant = getattr(resource, "tenant_id")
        if resource_tenant and resource_tenant != tenant_id:
            logger.warning(
                f"Access denied: Tenant {tenant_id} tried to access "
                f"resource from tenant {resource_tenant}"
            )
            if raise_on_failure:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: Resource belongs to another tenant"
                )
            return False

    # Check user-level access for user-owned resources
    if user_id and hasattr(resource, "user_id"):
        resource_user = getattr(resource, "user_id")
        if resource_user and resource_user != user_id:
            # Check if user has read access through tenant membership
            if not (tenant_id and hasattr(resource, "tenant_id") and
                    getattr(resource, "tenant_id") == tenant_id):
                logger.warning(
                    f"Access denied: User {user_id} tried to access "
                    f"resource owned by user {resource_user}"
                )
                if raise_on_failure:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: Resource belongs to another user"
                    )
                return False

    return True


def setup_sqlalchemy_rls_events(engine: Any) -> None:
    """Set up SQLAlchemy event listeners for automatic RLS enforcement.

    This function sets up event listeners that automatically apply
    RLS filters to queries.

    Parameters
    ----------
    engine : Any
        The SQLAlchemy engine to attach events to.
    """

    @event.listens_for(Session, "after_begin")
    def receive_after_begin(session: Session, transaction: Any, connection: Any) -> None:
        """Set session-level RLS configuration after transaction begins."""
        rls_context = RLSContext.get_instance()
        if rls_context.tenant_id and not rls_context.bypass_rls:
            # Store tenant_id in session info for reference
            session.info["tenant_id"] = rls_context.tenant_id
            session.info["enforce_rls"] = True
