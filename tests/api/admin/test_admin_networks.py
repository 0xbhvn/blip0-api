"""
Tests for admin network API endpoints.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from starlette.testclient import TestClient

# Import admin fixtures
from tests.conftest_admin import admin_user, admin_user_token, db_session, normal_user, normal_user_token  # noqa: F401

# Test data
TEST_NETWORK = {
    "name": "Test Ethereum Network",
    "slug": "test-ethereum",
    "network_type": "EVM",
    "block_time_ms": 12000,
    "description": "Test EVM network for testing",
    "chain_id": 1337,
    "rpc_urls": [
        {"url": "https://test-rpc.example.com", "type_": "primary", "weight": 100}
    ],
    "confirmation_blocks": 2,
    "cron_schedule": "*/5 * * * * *",
    "max_past_blocks": 50,
    "store_blocks": False,
}

TEST_STELLAR_NETWORK = {
    "name": "Test Stellar Network",
    "slug": "test-stellar",
    "network_type": "Stellar",
    "block_time_ms": 5000,
    "description": "Test Stellar network",
    "network_passphrase": "Test SDF Network ; September 2015",
    "rpc_urls": [
        {"url": "https://horizon-test.stellar.org", "type_": "primary", "weight": 100}
    ],
}


def test_list_networks_unauthorized(client: TestClient):
    """Test listing networks without authentication."""
    response = client.get("/api/admin/networks")
    assert response.status_code == 401


def test_list_networks_non_admin(client: TestClient, normal_user_token: dict):
    """Test listing networks as non-admin user."""
    headers = {"Authorization": f"Bearer {normal_user_token['access_token']}"}
    response = client.get("/api/admin/networks", headers=headers)
    assert response.status_code == 403
    assert "Admin privileges required" in response.json()["detail"]


def test_list_networks_empty(client: TestClient, admin_user_token: dict):
    """Test listing networks when none exist."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}
    response = client.get("/api/admin/networks", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["size"] == 50


def test_create_network(client: TestClient, admin_user_token: dict):
    """Test creating a new network."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}
    response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == TEST_NETWORK["name"]
    assert data["slug"] == TEST_NETWORK["slug"]
    assert data["network_type"] == TEST_NETWORK["network_type"]
    assert data["active"] is True
    assert data["validated"] is False
    assert "id" in data
    assert "created_at" in data


def test_create_network_duplicate_slug(
    client: TestClient,
    admin_user_token: dict,
    db_session: AsyncSession
):
    """Test creating a network with duplicate slug."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create first network
    response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert response.status_code == 201

    # Try to create duplicate
    response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_create_network_invalid_type(client: TestClient, admin_user_token: dict):
    """Test creating a network with invalid network type."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}
    network_data = {**TEST_NETWORK, "network_type": "Invalid"}
    response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=network_data
    )
    assert response.status_code == 422


def test_get_network(client: TestClient, admin_user_token: dict):
    """Test getting a specific network."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create network
    create_response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert create_response.status_code == 201
    network_id = create_response.json()["id"]

    # Get network
    response = client.get(
        f"/api/admin/networks/{network_id}",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == network_id
    assert data["name"] == TEST_NETWORK["name"]


def test_get_network_not_found(client: TestClient, admin_user_token: dict):
    """Test getting a non-existent network."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}
    fake_id = str(uuid.uuid4())
    response = client.get(
        f"/api/admin/networks/{fake_id}",
        headers=headers
    )
    assert response.status_code == 404


def test_update_network(client: TestClient, admin_user_token: dict):
    """Test updating a network."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create network
    create_response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert create_response.status_code == 201
    network_id = create_response.json()["id"]

    # Update network
    update_data = {
        "name": "Updated Test Network",
        "description": "Updated description",
        "confirmation_blocks": 5,
    }
    response = client.put(
        f"/api/admin/networks/{network_id}",
        headers=headers,
        json=update_data
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Test Network"
    assert data["description"] == "Updated description"
    assert data["confirmation_blocks"] == 5
    assert data["slug"] == TEST_NETWORK["slug"]  # Unchanged


def test_update_network_slug_duplicate(
    client: TestClient,
    admin_user_token: dict
):
    """Test updating network to duplicate slug."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create first network
    response1 = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert response1.status_code == 201

    # Create second network
    response2 = client.post(
        "/api/admin/networks",
        headers=headers,
        json={**TEST_STELLAR_NETWORK, "slug": "another-network"}
    )
    assert response2.status_code == 201
    network2_id = response2.json()["id"]

    # Try to update second network with first network's slug
    update_data = {"slug": TEST_NETWORK["slug"]}
    response = client.put(
        f"/api/admin/networks/{network2_id}",
        headers=headers,
        json=update_data
    )
    assert response.status_code == 409


def test_delete_network_soft(client: TestClient, admin_user_token: dict):
    """Test soft deleting a network."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create network
    create_response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert create_response.status_code == 201
    network_id = create_response.json()["id"]

    # Soft delete network
    response = client.delete(
        f"/api/admin/networks/{network_id}",
        headers=headers
    )
    assert response.status_code == 204

    # Verify network is soft deleted (inactive)
    get_response = client.get(
        f"/api/admin/networks/{network_id}",
        headers=headers
    )
    assert get_response.status_code == 200
    assert get_response.json()["active"] is False


def test_delete_network_hard(
    client: TestClient,
    admin_user_token: dict,
    db_session: AsyncSession
):
    """Test hard deleting a network."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create network
    create_response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert create_response.status_code == 201
    network_id = create_response.json()["id"]

    # Hard delete network
    response = client.delete(
        f"/api/admin/networks/{network_id}?hard_delete=true",
        headers=headers
    )
    assert response.status_code == 204

    # Verify network is gone
    get_response = client.get(
        f"/api/admin/networks/{network_id}",
        headers=headers
    )
    assert get_response.status_code == 404


def test_delete_network_not_found(client: TestClient, admin_user_token: dict):
    """Test deleting non-existent network."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}
    fake_id = str(uuid.uuid4())
    response = client.delete(
        f"/api/admin/networks/{fake_id}",
        headers=headers
    )
    assert response.status_code == 404


def test_validate_network(client: TestClient, admin_user_token: dict):
    """Test validating a network configuration."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create network
    create_response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert create_response.status_code == 201
    network_id = create_response.json()["id"]

    # Validate network
    response = client.post(
        f"/api/admin/networks/{network_id}/validate",
        headers=headers,
        json={}
    )
    assert response.status_code == 200
    data = response.json()
    assert "valid" in data
    assert "errors" in data
    assert "rpc_results" in data


def test_list_networks_with_pagination(
    client: TestClient,
    admin_user_token: dict
):
    """Test listing networks with pagination."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create multiple networks
    for i in range(5):
        network_data = {
            **TEST_NETWORK,
            "name": f"Test Network {i}",
            "slug": f"test-network-{i}",
        }
        response = client.post(
            "/api/admin/networks",
            headers=headers,
            json=network_data
        )
        assert response.status_code == 201

    # Test pagination
    response = client.get(
        "/api/admin/networks?page=1&size=2",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["pages"] == 3


def test_list_networks_with_filters(
    client: TestClient,
    admin_user_token: dict
):
    """Test listing networks with filters."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create EVM network
    response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_NETWORK
    )
    assert response.status_code == 201

    # Create Stellar network
    response = client.post(
        "/api/admin/networks",
        headers=headers,
        json=TEST_STELLAR_NETWORK
    )
    assert response.status_code == 201

    # Filter by network type
    response = client.get(
        "/api/admin/networks?network_type=EVM",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["network_type"] == "EVM"

    # Filter by name partial match
    response = client.get(
        "/api/admin/networks?name=Stellar",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "Stellar" in data["items"][0]["name"]


def test_list_networks_with_sorting(
    client: TestClient,
    admin_user_token: dict
):
    """Test listing networks with sorting."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create networks with different names
    networks = [
        {**TEST_NETWORK, "name": "Alpha Network", "slug": "alpha-network"},
        {**TEST_NETWORK, "name": "Beta Network", "slug": "beta-network"},
        {**TEST_NETWORK, "name": "Gamma Network", "slug": "gamma-network"},
    ]

    for network in networks:
        response = client.post(
            "/api/admin/networks",
            headers=headers,
            json=network
        )
        assert response.status_code == 201

    # Sort by name ascending
    response = client.get(
        "/api/admin/networks?sort_field=name&sort_order=asc",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["name"] == "Alpha Network"
    assert data["items"][1]["name"] == "Beta Network"
    assert data["items"][2]["name"] == "Gamma Network"

    # Sort by name descending
    response = client.get(
        "/api/admin/networks?sort_field=name&sort_order=desc",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["name"] == "Gamma Network"
    assert data["items"][1]["name"] == "Beta Network"
    assert data["items"][2]["name"] == "Alpha Network"
