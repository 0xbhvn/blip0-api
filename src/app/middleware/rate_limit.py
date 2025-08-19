"""Rate limiting middleware for API protection."""

import time
from datetime import UTC, datetime
from typing import Optional

from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from ..core.logger import logging
from ..core.utils.rate_limit import rate_limiter
from ..schemas.rate_limit import sanitize_path

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limiting on API endpoints.

    This middleware:
    1. Tracks request rates per user/IP
    2. Applies tier-based limits for authenticated users
    3. Adds rate limit headers to responses
    4. Supports endpoint-specific rate limits
    """

    def __init__(
        self,
        app: ASGIApp,
        default_limit: int = 100,
        default_period: int = 3600,
        enable_headers: bool = True,
        exclude_paths: Optional[list[str]] = None
    ) -> None:
        """Initialize the rate limit middleware.

        Parameters
        ----------
        app : ASGIApp
            The ASGI application instance.
        default_limit : int
            Default number of requests allowed per period.
        default_period : int
            Default time period in seconds.
        enable_headers : bool
            Whether to add rate limit headers to responses.
        exclude_paths : Optional[list[str]]
            List of paths to exclude from rate limiting.
        """
        super().__init__(app)
        self.default_limit = default_limit
        self.default_period = default_period
        self.enable_headers = enable_headers
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico"
        ]

        # Cache for user limits to avoid repeated DB lookups
        self._limit_cache: dict[str, tuple[int, int, float]] = {}
        self._cache_ttl = 60  # Cache limits for 60 seconds

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request with rate limiting.

        Parameters
        ----------
        request : Request
            The incoming request.
        call_next : RequestResponseEndpoint
            The next middleware or route handler.

        Returns
        -------
        Response
            The response with rate limit headers.
        """
        # Skip rate limiting for excluded paths
        path = sanitize_path(request.url.path)
        if any(request.url.path.startswith(excluded) for excluded in self.exclude_paths):
            return await call_next(request)

        # Determine rate limit key and limits
        rate_limit_key, limit, period = await self._get_rate_limit_info(request, path)

        # Check rate limit
        current_timestamp = int(datetime.now(UTC).timestamp())
        window_start = current_timestamp - (current_timestamp % period)

        redis_key = f"ratelimit:{rate_limit_key}:{path}:{window_start}"

        try:
            client = rate_limiter.get_client()

            # Get current count
            current_count = await client.get(redis_key)
            current_count = int(current_count) if current_count else 0

            # Check if limit exceeded
            if current_count >= limit:
                remaining = 0
                reset_time = window_start + period

                # Add rate limit headers even on error response
                headers = self._create_rate_limit_headers(
                    limit, remaining, reset_time, period
                )

                logger.warning(
                    f"Rate limit exceeded for {rate_limit_key} on {path}: "
                    f"{current_count}/{limit}"
                )

                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later.",
                    headers=headers if self.enable_headers else None
                )

            # Increment counter
            new_count = await client.incr(redis_key)
            if new_count == 1:
                # Set expiry on first request in window
                await client.expire(redis_key, period)

            # Calculate remaining requests
            remaining = max(0, limit - new_count)
            reset_time = window_start + period

            # Process request
            response = await call_next(request)

            # Add rate limit headers to response
            if self.enable_headers:
                headers = self._create_rate_limit_headers(
                    limit, remaining, reset_time, period
                )
                for header, value in headers.items():
                    response.headers[header] = value

            return response

        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            # Log error but don't block request on rate limit failure
            logger.error(f"Rate limit middleware error: {e}")
            # Continue without rate limiting on error
            return await call_next(request)

    async def _get_rate_limit_info(
        self, request: Request, path: str
    ) -> tuple[str, int, int]:
        """Get rate limit information for the request.

        Parameters
        ----------
        request : Request
            The incoming request.
        path : str
            The sanitized request path.

        Returns
        -------
        tuple[str, int, int]
            Rate limit key, limit, and period.
        """
        user = getattr(request.state, "user", None)

        if user and isinstance(user, dict):
            # Authenticated user - use user ID as key
            user_id = user.get("id")
            rate_limit_key = str(user_id)

            # Check cache first
            cache_key = f"{user_id}:{path}"
            if cache_key in self._limit_cache:
                cached_limit, cached_period, cache_time = self._limit_cache[cache_key]
                if time.time() - cache_time < self._cache_ttl:
                    return rate_limit_key, cached_limit, cached_period

            # Get tier-based limits (would normally query DB)
            # For now, use defaults or tier-specific limits
            tier_id = user.get("tier_id")
            if tier_id:
                # These would come from database based on tier and path
                # For now, use tier-based defaults
                if user.get("is_superuser"):
                    limit, period = 10000, 3600  # Superuser gets higher limits
                elif tier_id == 1:  # Free tier
                    limit, period = 100, 3600
                elif tier_id == 2:  # Pro tier
                    limit, period = 1000, 3600
                else:  # Enterprise
                    limit, period = 10000, 3600
            else:
                limit, period = self.default_limit, self.default_period

            # Cache the limits
            self._limit_cache[cache_key] = (limit, period, time.time())

        else:
            # Anonymous user - use IP address as key
            client_host = request.client.host if request.client else "unknown"
            rate_limit_key = f"anon:{client_host}"

            # Anonymous users get lower limits
            limit = self.default_limit // 2
            period = self.default_period

        return rate_limit_key, limit, period

    def _create_rate_limit_headers(
        self, limit: int, remaining: int, reset_time: int, period: int
    ) -> dict[str, str]:
        """Create rate limit headers for the response.

        Parameters
        ----------
        limit : int
            The rate limit.
        remaining : int
            Remaining requests in current window.
        reset_time : int
            Unix timestamp when the rate limit resets.
        period : int
            The rate limit period in seconds.

        Returns
        -------
        dict[str, str]
            Rate limit headers.
        """
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
            "X-RateLimit-Period": str(period),
        }

        # Add Retry-After header if rate limited
        if remaining == 0:
            retry_after = reset_time - int(datetime.now(UTC).timestamp())
            headers["Retry-After"] = str(max(0, retry_after))

        return headers


class EndpointRateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for endpoint-specific rate limiting.

    This allows different rate limits for specific endpoints,
    useful for resource-intensive operations.
    """

    def __init__(
        self,
        app: ASGIApp,
        endpoint_limits: Optional[dict[str, tuple[int, int]]] = None
    ) -> None:
        """Initialize endpoint-specific rate limit middleware.

        Parameters
        ----------
        app : ASGIApp
            The ASGI application instance.
        endpoint_limits : Optional[dict[str, tuple[int, int]]]
            Dictionary mapping endpoint paths to (limit, period) tuples.
        """
        super().__init__(app)
        self.endpoint_limits = endpoint_limits or {
            # Example endpoint-specific limits
            "/api/v1/monitors/sync": (10, 3600),  # 10 per hour
            "/api/v1/triggers/test": (5, 300),    # 5 per 5 minutes
            "/api/v1/auth/password-reset": (3, 3600),  # 3 per hour
        }

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Apply endpoint-specific rate limits.

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
        path = request.url.path

        # Check if this endpoint has specific limits
        for endpoint_path, (limit, period) in self.endpoint_limits.items():
            if path.startswith(endpoint_path):
                # Store endpoint limits in request state for main rate limiter
                request.state.endpoint_rate_limit = limit
                request.state.endpoint_rate_period = period
                break

        return await call_next(request)
