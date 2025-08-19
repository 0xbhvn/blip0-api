"""Request/Response logging middleware for audit and debugging."""

import json
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from ..core.logger import logging

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all incoming requests and outgoing responses.

    This middleware:
    1. Logs request details (method, path, headers, body)
    2. Logs response details (status, headers, timing)
    3. Includes user and tenant context
    4. Supports configurable log levels and filtering
    """

    def __init__(
        self,
        app: ASGIApp,
        log_level: str = "INFO",
        log_request_body: bool = False,
        log_response_body: bool = False,
        exclude_paths: Optional[set[str]] = None,
        exclude_headers: Optional[set[str]] = None,
        max_body_length: int = 1000
    ) -> None:
        """Initialize the request logging middleware.

        Parameters
        ----------
        app : ASGIApp
            The ASGI application instance.
        log_level : str
            Logging level (DEBUG, INFO, WARNING, ERROR).
        log_request_body : bool
            Whether to log request bodies.
        log_response_body : bool
            Whether to log response bodies.
        exclude_paths : Optional[set[str]]
            Paths to exclude from logging.
        exclude_headers : Optional[set[str]]
            Headers to exclude from logging (for security).
        max_body_length : int
            Maximum body length to log.
        """
        super().__init__(app)
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.exclude_paths = exclude_paths or {
            "/health",
            "/metrics",
            "/favicon.ico"
        }
        self.exclude_headers = exclude_headers or {
            "authorization",
            "cookie",
            "x-api-key",
            "x-auth-token"
        }
        self.max_body_length = max_body_length

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process and log the request/response cycle.

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
        # Skip logging for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Start timing
        start_time = time.time()

        # Get or generate request ID
        request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())

        # Build request log entry
        request_log = await self._build_request_log(request, request_id)

        # Log the incoming request
        logger.log(self.log_level, f"Request: {json.dumps(request_log)}")

        # Process the request
        try:
            response = await call_next(request)

            # Calculate request duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Build response log entry
            response_log = self._build_response_log(
                request, response, request_id, duration_ms
            )

            # Log the outgoing response
            logger.log(self.log_level, f"Response: {json.dumps(response_log)}")

            # Add timing header
            response.headers["X-Response-Time"] = f"{duration_ms}ms"

            return response

        except Exception as e:
            # Calculate request duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Log the error
            error_log = {
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_ms": duration_ms,
                "timestamp": datetime.now(UTC).isoformat()
            }
            logger.error(f"Request failed: {json.dumps(error_log)}")

            # Re-raise the exception
            raise

    async def _build_request_log(self, request: Request, request_id: str) -> dict[str, Any]:
        """Build a log entry for the incoming request.

        Parameters
        ----------
        request : Request
            The incoming request.
        request_id : str
            The request ID.

        Returns
        -------
        dict[str, Any]
            The request log entry.
        """
        # Get user and tenant context
        user = getattr(request.state, "user", None)
        tenant_id = getattr(request.state, "tenant_id", None)

        # Build base log entry
        log_entry: dict[str, Any] = {
            "request_id": request_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_host": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }

        # Add user context
        if user and isinstance(user, dict):
            log_entry["user"] = {
                "id": user.get("id"),
                "username": user.get("username"),
                "email": user.get("email"),
                "is_superuser": user.get("is_superuser", False)
            }

        # Add tenant context
        if tenant_id:
            log_entry["tenant_id"] = str(tenant_id)

        # Add filtered headers
        headers = {}
        for header_name, header_value in request.headers.items():
            if header_name.lower() not in self.exclude_headers:
                headers[header_name] = header_value
            else:
                headers[header_name] = "***REDACTED***"
        log_entry["headers"] = headers

        # Add request body if configured
        if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                # Note: This consumes the request body, so we need to be careful
                # In production, you might want to use a different approach
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type:
                    # For JSON bodies, we'd need special handling to not consume the stream
                    log_entry["body"] = "JSON body logging requires special handling"
                else:
                    log_entry["body"] = f"Non-JSON body (type: {content_type})"
            except Exception as e:
                log_entry["body"] = f"Error reading body: {e}"

        return log_entry

    def _build_response_log(
        self,
        request: Request,
        response: Response,
        request_id: str,
        duration_ms: int
    ) -> dict[str, Any]:
        """Build a log entry for the outgoing response.

        Parameters
        ----------
        request : Request
            The original request.
        response : Response
            The response object.
        request_id : str
            The request ID.
        duration_ms : int
            Request duration in milliseconds.

        Returns
        -------
        dict[str, Any]
            The response log entry.
        """
        log_entry = {
            "request_id": request_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "method": request.method,
            "path": request.url.path,
        }

        # Add response headers (filtered)
        headers = {}
        for header_name, header_value in response.headers.items():
            if header_name.lower() not in self.exclude_headers:
                headers[header_name] = header_value
        log_entry["response_headers"] = headers

        # Add response size if available
        if "content-length" in response.headers:
            log_entry["response_size"] = response.headers["content-length"]

        return log_entry


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for detailed audit logging of sensitive operations.

    This middleware focuses on logging security-relevant events
    for compliance and forensic purposes.
    """

    def __init__(
        self,
        app: ASGIApp,
        audit_paths: Optional[set[str]] = None,
        log_all_mutations: bool = True
    ) -> None:
        """Initialize the audit logging middleware.

        Parameters
        ----------
        app : ASGIApp
            The ASGI application instance.
        audit_paths : Optional[set[str]]
            Specific paths to audit.
        log_all_mutations : bool
            Whether to log all POST/PUT/PATCH/DELETE requests.
        """
        super().__init__(app)
        self.audit_paths = audit_paths or {
            "/api/v1/auth",
            "/api/v1/users",
            "/api/v1/tenants",
            "/api/v1/monitors",
            "/api/v1/triggers"
        }
        self.log_all_mutations = log_all_mutations

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process and audit log the request.

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
        # Determine if this request should be audited
        should_audit = False

        # Check if path matches audit paths
        for audit_path in self.audit_paths:
            if request.url.path.startswith(audit_path):
                should_audit = True
                break

        # Check if it's a mutation operation
        if self.log_all_mutations and request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            should_audit = True

        if not should_audit:
            return await call_next(request)

        # Get context
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        user = getattr(request.state, "user", None)
        tenant_id = getattr(request.state, "tenant_id", None)

        # Build audit log entry
        audit_log = {
            "event_type": "API_REQUEST",
            "request_id": request_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }

        # Add authentication context
        if user and isinstance(user, dict):
            audit_log["user"] = {
                "id": user.get("id"),
                "username": user.get("username"),
                "email": user.get("email"),
                "is_superuser": user.get("is_superuser", False)
            }
            audit_log["authenticated"] = True
        else:
            audit_log["authenticated"] = False

        if tenant_id:
            audit_log["tenant_id"] = str(tenant_id)

        # Process request
        try:
            response = await call_next(request)

            # Add response info to audit log
            audit_log["status_code"] = response.status_code
            audit_log["success"] = 200 <= response.status_code < 400

            # Log the audit entry
            logger.info(f"AUDIT: {json.dumps(audit_log)}")

            return response

        except Exception as e:
            # Log failed request
            audit_log["status_code"] = 500
            audit_log["success"] = False
            audit_log["error"] = str(e)
            audit_log["error_type"] = type(e).__name__

            logger.error(f"AUDIT_ERROR: {json.dumps(audit_log)}")

            # Re-raise the exception
            raise
