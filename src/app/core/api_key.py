"""API Key authentication and management."""

import secrets
from datetime import UTC, datetime
from typing import Any, Optional

import bcrypt
from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyHeader, APIKeyQuery
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import logging
from ..crud.crud_users import crud_users
from ..models.api_key import APIKey

logger = logging.getLogger(__name__)

# API Key configuration
API_KEY_PREFIX = "blp0_"
API_KEY_LENGTH = 32  # Length of the random part
API_KEY_HEADER = "X-API-Key"


# Security schemes for API key authentication
api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)


def generate_api_key() -> tuple[str, str]:
    """Generate a new API key.

    Returns
    -------
    tuple[str, str]
        A tuple of (full_key, key_hash).
        The full_key should be shown to the user only once.
        The key_hash should be stored in the database.
    """
    # Generate random key
    random_key = secrets.token_urlsafe(API_KEY_LENGTH)

    # Create full key with prefix
    full_key = f"{API_KEY_PREFIX}{random_key}"

    # Hash the full key for storage
    key_hash = bcrypt.hashpw(full_key.encode(), bcrypt.gensalt()).decode()

    return full_key, key_hash


def hash_api_key(api_key: str) -> str:
    """Hash an API key for storage.

    Parameters
    ----------
    api_key : str
        The API key to hash.

    Returns
    -------
    str
        The hashed API key.
    """
    return bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()


def verify_api_key(api_key: str, hashed_key: str) -> bool:
    """Verify an API key against its hash.

    Parameters
    ----------
    api_key : str
        The API key to verify.
    hashed_key : str
        The hashed key from the database.

    Returns
    -------
    bool
        True if the key is valid, False otherwise.
    """
    try:
        return bcrypt.checkpw(api_key.encode(), hashed_key.encode())
    except Exception:
        return False


async def get_api_key(
    api_key_header: Optional[str] = None,
    api_key_query: Optional[str] = None
) -> Optional[str]:
    """Extract API key from request.

    Parameters
    ----------
    api_key_header : Optional[str]
        API key from header.
    api_key_query : Optional[str]
        API key from query parameter.

    Returns
    -------
    Optional[str]
        The API key if found, None otherwise.
    """
    # Prefer header over query parameter
    if api_key_header:
        return api_key_header
    if api_key_query:
        return api_key_query
    return None


async def validate_api_key(
    db: AsyncSession,
    api_key: str
) -> Optional[dict[str, Any]]:
    """Validate an API key and return associated user information.

    Parameters
    ----------
    db : AsyncSession
        Database session.
    api_key : str
        The API key to validate.

    Returns
    -------
    Optional[dict[str, Any]]
        User information if the key is valid, None otherwise.
    """
    # Check if key has correct prefix
    if not api_key.startswith(API_KEY_PREFIX):
        logger.warning(f"Invalid API key prefix: {api_key[:10]}...")
        return None

    # Extract key parts for quick lookup
    prefix = API_KEY_PREFIX
    last_four = api_key[-4:] if len(api_key) > 4 else ""

    # Query for API keys with matching prefix and last_four
    # This narrows down the search before doing expensive bcrypt verification
    from sqlalchemy import select

    stmt = select(APIKey).where(
        APIKey.prefix == prefix,
        APIKey.last_four == last_four,
        APIKey.is_active
    )

    result = await db.execute(stmt)
    api_keys = result.scalars().all()

    # Try to verify against each potential match
    for api_key_obj in api_keys:
        if verify_api_key(api_key, api_key_obj.key_hash):
            # Check if key is expired
            if api_key_obj.is_expired():
                logger.warning(f"Expired API key used: {api_key_obj.id}")
                return None

            # Update usage statistics
            api_key_obj.last_used_at = datetime.now(UTC)
            api_key_obj.usage_count += 1
            await db.commit()

            # Get associated user
            user = await crud_users.get(db=db, id=api_key_obj.user_id)
            if not user:
                logger.error(f"User not found for API key: {api_key_obj.id}")
                return None

            # Return user info with API key context
            user_dict = dict(user) if not isinstance(user, dict) else user
            user_dict["api_key_id"] = str(api_key_obj.id)
            user_dict["api_key_scopes"] = api_key_obj.scopes
            user_dict["tenant_id"] = api_key_obj.tenant_id

            return user_dict

    logger.warning(f"Invalid API key attempted: {prefix}...{last_four}")
    return None


async def authenticate_api_key(
    request: Request,
    db: AsyncSession,
    api_key_header: Optional[str] = None,
    api_key_query: Optional[str] = None
) -> Optional[dict[str, Any]]:
    """Authenticate a request using API key.

    Parameters
    ----------
    request : Request
        The FastAPI request object.
    db : AsyncSession
        Database session.
    api_key_header : Optional[str]
        API key from header.
    api_key_query : Optional[str]
        API key from query parameter.

    Returns
    -------
    Optional[dict[str, Any]]
        User information if authenticated, None otherwise.

    Raises
    ------
    HTTPException
        If the API key is invalid.
    """
    api_key = await get_api_key(api_key_header, api_key_query)

    if not api_key:
        return None

    user_info = await validate_api_key(db, api_key)

    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": f"ApiKey realm=\"{API_KEY_HEADER}\""},
        )

    # Store API key context in request state
    request.state.api_key_tenant_id = user_info.get("tenant_id")
    request.state.api_key_user = user_info

    return user_info


def extract_key_info(api_key: str) -> dict[str, str]:
    """Extract displayable information from an API key.

    Parameters
    ----------
    api_key : str
        The full API key.

    Returns
    -------
    dict[str, str]
        Dictionary with prefix and last_four.
    """
    prefix = api_key[:len(API_KEY_PREFIX)] if len(api_key) >= len(API_KEY_PREFIX) else ""
    last_four = api_key[-4:] if len(api_key) > 4 else api_key

    return {
        "prefix": prefix,
        "last_four": last_four
    }
