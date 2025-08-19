from typing import Annotated, Any, Optional, cast

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader, APIKeyQuery
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.api_key import authenticate_api_key
from ..core.config import settings
from ..core.db.database import async_get_db
from ..core.exceptions.http_exceptions import ForbiddenException, RateLimitException, UnauthorizedException
from ..core.logger import logging
from ..core.security import TokenType, oauth2_scheme, verify_token
from ..core.utils.rate_limit import rate_limiter
from ..crud.crud_rate_limit import crud_rate_limits
from ..crud.crud_tier import crud_tiers
from ..crud.crud_users import crud_users
from ..schemas.rate_limit import RateLimitRead, sanitize_path
from ..schemas.tier import TierRead

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = settings.DEFAULT_RATE_LIMIT_LIMIT
DEFAULT_PERIOD = settings.DEFAULT_RATE_LIMIT_PERIOD

# API Key security schemes
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


async def get_current_user_jwt(
    token: Annotated[str, Depends(oauth2_scheme)], db: Annotated[AsyncSession, Depends(async_get_db)]
) -> dict[str, Any] | None:
    token_data = await verify_token(token, TokenType.ACCESS, db)
    if token_data is None:
        raise UnauthorizedException("User not authenticated.")

    if "@" in token_data.username_or_email:
        user = await crud_users.get(db=db, email=token_data.username_or_email, is_deleted=False)
    else:
        user = await crud_users.get(db=db, username=token_data.username_or_email, is_deleted=False)

    if user:
        return cast(dict[str, Any], user)

    raise UnauthorizedException("User not authenticated.")


async def get_current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(async_get_db)],
    token: Annotated[Optional[str], Depends(oauth2_scheme)] = None,
    api_key_from_header: Annotated[Optional[str], Depends(api_key_header)] = None,
    api_key_from_query: Annotated[Optional[str], Depends(api_key_query)] = None,
) -> dict[str, Any]:
    """Get current user from either JWT token or API key.

    This function tries authentication in the following order:
    1. JWT token from Authorization header
    2. API key from X-API-Key header
    3. API key from query parameter

    Parameters
    ----------
    request : Request
        The FastAPI request object.
    db : AsyncSession
        Database session.
    token : Optional[str]
        JWT token from Authorization header.
    api_key_from_header : Optional[str]
        API key from X-API-Key header.
    api_key_from_query : Optional[str]
        API key from query parameter.

    Returns
    -------
    dict[str, Any]
        The authenticated user dictionary.

    Raises
    ------
    UnauthorizedException
        If no valid authentication is provided.
    """
    # Try JWT token first
    if token:
        token_data = await verify_token(token, TokenType.ACCESS, db)
        if token_data:
            if "@" in token_data.username_or_email:
                user = await crud_users.get(db=db, email=token_data.username_or_email, is_deleted=False)
            else:
                user = await crud_users.get(db=db, username=token_data.username_or_email, is_deleted=False)

            if user:
                user_dict = cast(dict[str, Any], user)
                # Store user in request state for middleware
                request.state.user = user_dict
                return user_dict

    # Try API key authentication
    if api_key_from_header or api_key_from_query:
        user = await authenticate_api_key(
            request, db, api_key_from_header, api_key_from_query
        )
        if user:
            # Store user in request state for middleware
            request.state.user = user
            return user

    # No valid authentication found
    raise UnauthorizedException("User not authenticated. Please provide a valid JWT token or API key.")


async def get_optional_user(request: Request, db: AsyncSession = Depends(async_get_db)) -> dict | None:
    token = request.headers.get("Authorization")
    if not token:
        return None

    try:
        token_type, _, token_value = token.partition(" ")
        if token_type.lower() != "bearer" or not token_value:
            return None

        token_data = await verify_token(token_value, TokenType.ACCESS, db)
        if token_data is None:
            return None

        return await get_current_user(request, db, token=token_value)

    except HTTPException as http_exc:
        if http_exc.status_code != 401:
            logger.error(f"Unexpected HTTPException in get_optional_user: {http_exc.detail}")
        return None

    except Exception as exc:
        logger.error(f"Unexpected error in get_optional_user: {exc}")
        return None


async def get_current_superuser(current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
    if not current_user["is_superuser"]:
        raise ForbiddenException("You do not have enough privileges.")

    return current_user


async def get_current_admin(current_user: Annotated[dict, Depends(get_current_user)]) -> dict:
    """Check if current user is an admin (superuser or has admin role)."""
    # For now, admin is same as superuser. In future, could check for admin role
    if not current_user.get("is_superuser", False):
        # Could also check for admin role in tenant settings
        # Example: tenant_settings = current_user.get("tenant_settings", {})
        # if not tenant_settings.get("is_admin", False):
        raise ForbiddenException("Admin privileges required.")

    return current_user


async def get_tenant_context(
    current_user: Annotated[dict, Depends(get_current_user)]
) -> str:
    """Get tenant context from current user.

    Ensures the user has a tenant association and returns the tenant_id.
    This middleware helps enforce tenant isolation across all endpoints.
    """
    if not current_user.get("tenant_id"):
        raise ForbiddenException("User is not associated with any tenant")

    return str(current_user["tenant_id"])


async def rate_limiter_dependency(
    request: Request, db: Annotated[AsyncSession, Depends(async_get_db)], user: dict | None = Depends(get_optional_user)
) -> None:
    if hasattr(request.app.state, "initialization_complete"):
        await request.app.state.initialization_complete.wait()

    path = sanitize_path(request.url.path)
    if user:
        user_id = user["id"]
        tier = await crud_tiers.get(db, id=user["tier_id"], schema_to_select=TierRead)
        if tier:
            tier = cast(TierRead, tier)
            rate_limit = await crud_rate_limits.get(db=db, tier_id=tier.id, path=path, schema_to_select=RateLimitRead)
            if rate_limit:
                rate_limit = cast(RateLimitRead, rate_limit)
                limit, period = rate_limit.limit, rate_limit.period
            else:
                logger.warning(
                    f"User {user_id} with tier '{tier.name}' has no specific rate limit for path '{path}'. \
                        Applying default rate limit."
                )
                limit, period = DEFAULT_LIMIT, DEFAULT_PERIOD
        else:
            logger.warning(f"User {user_id} has no assigned tier. Applying default rate limit.")
            limit, period = DEFAULT_LIMIT, DEFAULT_PERIOD
    else:
        user_id = request.client.host if request.client else "unknown"
        limit, period = DEFAULT_LIMIT, DEFAULT_PERIOD

    is_limited = await rate_limiter.is_rate_limited(db=db, user_id=user_id, path=path, limit=limit, period=period)
    if is_limited:
        raise RateLimitException("Rate limit exceeded.")
