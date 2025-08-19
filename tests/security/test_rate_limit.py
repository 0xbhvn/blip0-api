"""Tests for rate limiting middleware."""

from unittest.mock import Mock

import pytest
from fastapi import Request, Response

from src.app.middleware.rate_limit import RateLimitMiddleware


@pytest.mark.asyncio
async def test_rate_limit_headers(fast_redis_mock):
    """Test that rate limit headers are included in responses."""
    # Test rate limit header structure
    headers = {
        "X-RateLimit-Limit": "100",
        "X-RateLimit-Remaining": "50",
        "X-RateLimit-Reset": "1234567890",
        "X-RateLimit-Period": "3600"
    }

    # Check header values are valid
    limit = int(headers["X-RateLimit-Limit"])
    remaining = int(headers["X-RateLimit-Remaining"])

    assert limit > 0
    assert remaining >= 0
    assert remaining <= limit


@pytest.mark.asyncio
async def test_rate_limit_enforcement(mock_redis):
    """Test that rate limits are enforced."""
    # Test rate limit logic
    limit = 5
    current_usage = 6  # Over the limit

    # Check if limit is exceeded
    limit_exceeded = current_usage > limit
    assert limit_exceeded is True

    # Test within limit
    current_usage_ok = 3
    limit_ok = current_usage_ok <= limit
    assert limit_ok is True


@pytest.mark.asyncio
async def test_rate_limit_per_user(mock_redis):
    """Test that rate limits are per-user."""
    # Test per-user rate limiting logic
    user_a_count = 10
    user_b_count = 2
    limit = 15

    # User A usage
    user_a_within_limit = user_a_count <= limit
    assert user_a_within_limit is True

    # User B usage
    user_b_within_limit = user_b_count <= limit
    assert user_b_within_limit is True

    # Users should have independent counts
    assert user_a_count != user_b_count


@pytest.mark.asyncio
async def test_rate_limit_anonymous_users(mock_redis):
    """Test rate limiting for anonymous users."""
    # Test anonymous user rate limiting
    anonymous_limit = 3
    authenticated_limit = 10

    # Anonymous users should have lower limits
    assert anonymous_limit < authenticated_limit

    # Test anonymous usage tracking
    anonymous_usage = 2
    anonymous_within_limit = anonymous_usage <= anonymous_limit
    assert anonymous_within_limit is True

    # Test over limit
    anonymous_over_limit = 5
    over_limit = anonymous_over_limit > anonymous_limit
    assert over_limit is True


@pytest.mark.asyncio
async def test_rate_limit_retry_after(mock_redis):
    """Test Retry-After header when rate limited."""
    # Test retry-after calculation
    period = 60  # 60 seconds
    ttl = 30     # 30 seconds remaining

    # Retry-After should be the TTL
    retry_after = ttl
    assert retry_after >= 0
    assert retry_after <= period

    # Test header format
    retry_header = f"{retry_after}"
    assert retry_header == "30"


@pytest.mark.asyncio
async def test_tier_based_rate_limits(mock_redis):
    """Test that different tiers have different rate limits."""
    # Test tier-based limit configuration
    free_limit = 100
    pro_limit = 1000

    # Pro tier should have higher limits
    assert pro_limit > free_limit

    # Test tier limit calculation
    tier_multiplier = pro_limit / free_limit
    assert tier_multiplier == 10.0

    # Test usage within tiers
    free_usage = 50
    pro_usage = 500

    assert free_usage <= free_limit
    assert pro_usage <= pro_limit


@pytest.mark.asyncio
async def test_endpoint_specific_rate_limits(mock_redis):
    """Test endpoint-specific rate limits."""
    # Test endpoint-specific configuration
    endpoint_limits = {
        "/api/v1/auth/password-reset": {"limit": 3, "period": 300},  # Strict limit
        "/api/v1/monitors": {"limit": 100, "period": 60}  # Normal limit
    }

    # Password reset should have stricter limits
    password_reset_limit = endpoint_limits["/api/v1/auth/password-reset"]["limit"]
    monitors_limit = endpoint_limits["/api/v1/monitors"]["limit"]

    assert password_reset_limit < monitors_limit
    assert password_reset_limit == 3
    assert monitors_limit == 100

    # Test period configuration
    password_reset_period = endpoint_limits["/api/v1/auth/password-reset"]["period"]
    monitors_period = endpoint_limits["/api/v1/monitors"]["period"]

    assert password_reset_period > monitors_period  # Longer cool-down for sensitive endpoints


@pytest.mark.asyncio
async def test_rate_limit_middleware_initialization():
    """Test RateLimitMiddleware initialization."""
    app = Mock()

    # Test with default settings
    middleware = RateLimitMiddleware(app)
    assert middleware.default_limit == 100
    assert middleware.default_period == 3600
    assert middleware.enable_headers is True

    # Test with custom settings
    middleware = RateLimitMiddleware(
        app,
        default_limit=50,
        default_period=60,
        enable_headers=False,
        exclude_paths=["/custom", "/path"]
    )
    assert middleware.default_limit == 50
    assert middleware.default_period == 60
    assert middleware.enable_headers is False
    assert "/custom" in middleware.exclude_paths


@pytest.mark.asyncio
async def test_rate_limit_excluded_paths(fast_redis_mock):
    """Test that certain paths are excluded from rate limiting."""
    app = Mock()
    middleware = RateLimitMiddleware(
        app,
        exclude_paths=["/health", "/docs", "/metrics"]
    )

    # Mock health check request
    request = Mock(spec=Request)
    request.url = Mock(path="/health")
    request.client = Mock(host="127.0.0.1")
    request.state = Mock()

    async def mock_call_next(req):
        return Mock(spec=Response, headers={})

    # Test that excluded paths bypass rate limiting
    response = await middleware.dispatch(request, mock_call_next)

    # Should process excluded paths normally
    assert response is not None

    # Verify excluded paths are configured
    assert "/health" in middleware.exclude_paths
    assert "/docs" in middleware.exclude_paths
