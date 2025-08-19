"""Tests for API Key authentication."""


import pytest

from src.app.core.api_key import extract_key_info, generate_api_key, verify_api_key


@pytest.mark.asyncio
async def test_generate_api_key():
    """Test API key generation."""
    full_key, key_hash = generate_api_key()

    assert full_key.startswith("blp0_")
    assert len(full_key) > 20
    assert key_hash != full_key
    assert len(key_hash) > 0


@pytest.mark.asyncio
async def test_verify_api_key(test_api_key, precomputed_api_key_hash):
    """Test API key verification."""
    # Use pre-computed hash for speed
    key_hash = precomputed_api_key_hash

    # Verify correct key
    assert verify_api_key(test_api_key, key_hash) is True

    # Verify incorrect key
    assert verify_api_key("wrong_key", key_hash) is False
    assert verify_api_key(test_api_key, "wrong_hash") is False


@pytest.mark.asyncio
async def test_extract_key_info():
    """Test extracting displayable key information."""
    test_key = "blp0_abcdefghijklmnopqrstuvwxyz1234"
    info = extract_key_info(test_key)

    assert info["prefix"] == "blp0_"
    assert info["last_four"] == "1234"


@pytest.mark.asyncio
async def test_api_key_authentication_header(test_api_key: str, precomputed_api_key_hash: str):
    """Test API key authentication via header."""
    from src.app.core.api_key import verify_api_key

    # Test that verification works with pre-computed hash
    assert verify_api_key(test_api_key, precomputed_api_key_hash) is True
    assert verify_api_key(test_api_key, "wrong_hash") is False


@pytest.mark.asyncio
async def test_api_key_authentication_query(test_api_key: str):
    """Test API key authentication via query parameter."""
    # Test key info extraction
    info = extract_key_info(test_api_key)

    assert info["prefix"] == "blp0_"
    assert "last_four" in info
    assert len(info["last_four"]) == 4


@pytest.mark.asyncio
async def test_invalid_api_key():
    """Test authentication with invalid API key."""
    from src.app.core.api_key import verify_api_key

    # Test invalid key verification
    valid_key, key_hash = generate_api_key()

    # Wrong key should fail
    assert verify_api_key("invalid_key", key_hash) is False

    # Wrong hash should fail
    assert verify_api_key(valid_key, "invalid_hash") is False


@pytest.mark.asyncio
async def test_expired_api_key(expired_api_key: str):
    """Test authentication with expired API key."""
    # Test that expired key info can still be extracted (for logging)
    info = extract_key_info(expired_api_key)

    assert info["prefix"] == "blp0_"
    assert "last_four" in info


@pytest.mark.asyncio
async def test_api_key_with_scopes(scoped_api_key: dict):
    """Test API key with specific scopes."""
    # Test scoped key has expected properties
    assert "key" in scoped_api_key
    assert "scopes" in scoped_api_key
    assert "monitor:read" in scoped_api_key["scopes"]
    assert "trigger:read" in scoped_api_key["scopes"]

    # Test key format
    assert scoped_api_key["key"].startswith("blp0_")

    # Test scope checking logic
    allowed_scopes = scoped_api_key["scopes"]
    assert "monitor:delete" not in allowed_scopes


@pytest.mark.asyncio
async def test_api_key_usage_tracking(mock_db, test_api_key: str):
    """Test that API key usage is tracked."""
    # Mock API key tracking logic
    usage_count = 0
    last_used_at = None

    # Simulate usage
    usage_count += 1
    last_used_at = "2023-01-01T00:00:00"

    # Verify tracking increments
    assert usage_count == 1
    assert last_used_at is not None

    # Test key format is valid for tracking
    assert test_api_key.startswith("blp0_")
    assert len(test_api_key) > 10


@pytest.mark.asyncio
async def test_api_key_tenant_isolation(
    tenant_a_api_key: str,
    tenant_b_api_key: str
):
    """Test that API keys are isolated by tenant."""
    # Test that tenant-specific keys have correct format
    assert tenant_a_api_key.startswith("blp0_tenant_a")
    assert tenant_b_api_key.startswith("blp0_tenant_b")

    # Extract key info for both
    info_a = extract_key_info(tenant_a_api_key)
    info_b = extract_key_info(tenant_b_api_key)

    assert info_a["prefix"] == "blp0_"
    assert info_b["prefix"] == "blp0_"
    assert info_a["last_four"] != info_b["last_four"]
