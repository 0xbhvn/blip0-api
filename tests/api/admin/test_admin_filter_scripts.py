"""
Tests for admin filter script API endpoints.
"""

import uuid
from pathlib import Path

from starlette.testclient import TestClient

# Import admin fixtures
from tests.conftest_admin import admin_user, admin_user_token, db_session, normal_user, normal_user_token  # noqa: F401

# Test script content
BASH_SCRIPT_CONTENT = """#!/bin/bash
# Test bash filter script
input=$(cat)
echo "$input" | jq '.monitor_match'
exit 0
"""

PYTHON_SCRIPT_CONTENT = """#!/usr/bin/env python3
# Test python filter script
import sys
import json

data = json.loads(sys.stdin.read())
print(json.dumps(data['monitor_match']))
sys.exit(0)
"""

JAVASCRIPT_SCRIPT_CONTENT = """#!/usr/bin/env node
// Test JavaScript filter script
let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', () => {
    const data = JSON.parse(input);
    console.log(JSON.stringify(data.monitor_match));
    process.exit(0);
});
"""

# Test data
TEST_BASH_SCRIPT = {
    "name": "Test Bash Filter",
    "slug": "test-bash-filter",
    "language": "bash",
    "description": "Test bash filter script for testing",
    "arguments": ["--verbose"],
    "timeout_ms": 1000,
    "script_content": BASH_SCRIPT_CONTENT,
}

TEST_PYTHON_SCRIPT = {
    "name": "Test Python Filter",
    "slug": "test-python-filter",
    "language": "python",
    "description": "Test Python filter script",
    "arguments": [],
    "timeout_ms": 2000,
    "script_content": PYTHON_SCRIPT_CONTENT,
}


def test_list_filter_scripts_unauthorized(client: TestClient):
    """Test listing filter scripts without authentication."""
    response = client.get("/api/admin/filter-scripts")
    assert response.status_code == 401


def test_list_filter_scripts_non_admin(client: TestClient, normal_user_token: dict):
    """Test listing filter scripts as non-admin user."""
    headers = {"Authorization": f"Bearer {normal_user_token['access_token']}"}
    response = client.get("/api/admin/filter-scripts", headers=headers)
    assert response.status_code == 403
    assert "Admin privileges required" in response.json()["detail"]


def test_list_filter_scripts_empty(client: TestClient, admin_user_token: dict):
    """Test listing filter scripts when none exist."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}
    response = client.get("/api/admin/filter-scripts", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["size"] == 50


def test_create_filter_script(client: TestClient, admin_user_token: dict):
    """Test creating a new filter script."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}
    response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == TEST_BASH_SCRIPT["name"]
    assert data["slug"] == TEST_BASH_SCRIPT["slug"]
    assert data["language"] == TEST_BASH_SCRIPT["language"]
    assert data["script_content"] == TEST_BASH_SCRIPT["script_content"]
    assert data["active"] is True
    assert data["validated"] is False
    assert "id" in data
    assert "created_at" in data
    assert "script_path" in data

    # Verify file was created
    script_path = Path("config/filters/test-bash-filter.sh")
    assert script_path.exists()
    # Clean up
    script_path.unlink(missing_ok=True)


def test_create_filter_script_duplicate_slug(
    client: TestClient,
    admin_user_token: dict
):
    """Test creating a filter script with duplicate slug."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create first script
    response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert response.status_code == 201

    # Try to create duplicate
    response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]

    # Clean up
    Path("config/filters/test-bash-filter.sh").unlink(missing_ok=True)


def test_create_filter_script_invalid_language(
    client: TestClient,
    admin_user_token: dict
):
    """Test creating a filter script with invalid language."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}
    script_data = {**TEST_BASH_SCRIPT, "language": "invalid"}
    response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=script_data
    )
    assert response.status_code == 422


def test_get_filter_script(client: TestClient, admin_user_token: dict):
    """Test getting a specific filter script."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create script
    create_response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert create_response.status_code == 201
    script_id = create_response.json()["id"]

    # Get script
    response = client.get(
        f"/api/admin/filter-scripts/{script_id}",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == script_id
    assert data["name"] == TEST_BASH_SCRIPT["name"]
    assert data["script_content"] == TEST_BASH_SCRIPT["script_content"]

    # Clean up
    Path("config/filters/test-bash-filter.sh").unlink(missing_ok=True)


def test_get_filter_script_not_found(client: TestClient, admin_user_token: dict):
    """Test getting a non-existent filter script."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}
    fake_id = str(uuid.uuid4())
    response = client.get(
        f"/api/admin/filter-scripts/{fake_id}",
        headers=headers
    )
    assert response.status_code == 404


def test_update_filter_script(client: TestClient, admin_user_token: dict):
    """Test updating a filter script."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create script
    create_response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert create_response.status_code == 201
    script_id = create_response.json()["id"]

    # Update script
    update_data = {
        "name": "Updated Test Filter",
        "description": "Updated description",
        "timeout_ms": 5000,
        "script_content": "#!/bin/bash\necho 'Updated script'\nexit 0",
    }
    response = client.put(
        f"/api/admin/filter-scripts/{script_id}",
        headers=headers,
        json=update_data
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Test Filter"
    assert data["description"] == "Updated description"
    assert data["timeout_ms"] == 5000
    assert "Updated script" in data["script_content"]
    assert data["slug"] == TEST_BASH_SCRIPT["slug"]  # Unchanged

    # Verify file was updated
    script_path = Path("config/filters/test-bash-filter.sh")
    assert script_path.exists()
    content = script_path.read_text()
    assert "Updated script" in content

    # Clean up
    script_path.unlink(missing_ok=True)


def test_update_filter_script_slug_rename_file(
    client: TestClient,
    admin_user_token: dict
):
    """Test updating filter script slug renames the file."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create script
    create_response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert create_response.status_code == 201
    script_id = create_response.json()["id"]

    # Update slug
    update_data = {"slug": "renamed-filter"}
    response = client.put(
        f"/api/admin/filter-scripts/{script_id}",
        headers=headers,
        json=update_data
    )
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "renamed-filter"

    # Verify old file doesn't exist and new file does
    old_path = Path("config/filters/test-bash-filter.sh")
    new_path = Path("config/filters/renamed-filter.sh")
    assert not old_path.exists()
    assert new_path.exists()

    # Clean up
    new_path.unlink(missing_ok=True)


def test_delete_filter_script_soft(client: TestClient, admin_user_token: dict):
    """Test soft deleting a filter script."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create script
    create_response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert create_response.status_code == 201
    script_id = create_response.json()["id"]

    # Soft delete script
    response = client.delete(
        f"/api/admin/filter-scripts/{script_id}",
        headers=headers
    )
    assert response.status_code == 204

    # Verify script is soft deleted (inactive)
    get_response = client.get(
        f"/api/admin/filter-scripts/{script_id}",
        headers=headers
    )
    assert get_response.status_code == 200
    assert get_response.json()["active"] is False

    # Verify file still exists
    script_path = Path("config/filters/test-bash-filter.sh")
    assert script_path.exists()

    # Clean up
    script_path.unlink(missing_ok=True)


def test_delete_filter_script_with_file(
    client: TestClient,
    admin_user_token: dict
):
    """Test deleting a filter script with file deletion."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create script
    create_response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert create_response.status_code == 201
    script_id = create_response.json()["id"]

    # Delete script and file
    response = client.delete(
        f"/api/admin/filter-scripts/{script_id}?delete_file=true",
        headers=headers
    )
    assert response.status_code == 204

    # Verify file was deleted
    script_path = Path("config/filters/test-bash-filter.sh")
    assert not script_path.exists()


def test_validate_filter_script_bash(client: TestClient, admin_user_token: dict):
    """Test validating a bash filter script."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create script
    create_response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert create_response.status_code == 201
    script_id = create_response.json()["id"]

    # Validate script
    response = client.post(
        f"/api/admin/filter-scripts/{script_id}/validate",
        headers=headers,
        json={}
    )
    assert response.status_code == 200
    data = response.json()
    assert "valid" in data
    assert data["valid"] is True  # Simple bash script should be valid

    # Clean up
    Path("config/filters/test-bash-filter.sh").unlink(missing_ok=True)


def test_validate_filter_script_with_test_input(
    client: TestClient,
    admin_user_token: dict
):
    """Test validating a filter script with test input."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create script
    create_response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_PYTHON_SCRIPT
    )
    assert create_response.status_code == 201
    script_id = create_response.json()["id"]

    # Validate with test input
    test_input = {
        "monitor_match": {
            "test": "data"
        }
    }
    response = client.post(
        f"/api/admin/filter-scripts/{script_id}/validate",
        headers=headers,
        json={"test_input": test_input}
    )
    assert response.status_code == 200
    data = response.json()
    assert "valid" in data
    assert "test_output" in data
    assert "execution_time_ms" in data

    # Clean up
    Path("config/filters/test-python-filter.py").unlink(missing_ok=True)


def test_list_filter_scripts_with_pagination(
    client: TestClient,
    admin_user_token: dict
):
    """Test listing filter scripts with pagination."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create multiple scripts
    created_ids = []
    for i in range(5):
        script_data = {
            **TEST_BASH_SCRIPT,
            "name": f"Test Script {i}",
            "slug": f"test-script-{i}",
        }
        response = client.post(
            "/api/admin/filter-scripts",
            headers=headers,
            json=script_data
        )
        assert response.status_code == 201
        created_ids.append(response.json()["id"])

    # Test pagination
    response = client.get(
        "/api/admin/filter-scripts?page=1&size=2",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["pages"] == 3

    # Clean up
    for i in range(5):
        Path(f"config/filters/test-script-{i}.sh").unlink(missing_ok=True)


def test_list_filter_scripts_with_filters(
    client: TestClient,
    admin_user_token: dict
):
    """Test listing filter scripts with filters."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create bash script
    response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert response.status_code == 201

    # Create python script
    response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_PYTHON_SCRIPT
    )
    assert response.status_code == 201

    # Filter by language
    response = client.get(
        "/api/admin/filter-scripts?language=bash",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["language"] == "bash"

    # Filter by name partial match
    response = client.get(
        "/api/admin/filter-scripts?name=Python",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "Python" in data["items"][0]["name"]

    # Clean up
    Path("config/filters/test-bash-filter.sh").unlink(missing_ok=True)
    Path("config/filters/test-python-filter.py").unlink(missing_ok=True)


def test_list_filter_scripts_with_content(
    client: TestClient,
    admin_user_token: dict
):
    """Test listing filter scripts with content included."""
    headers = {"Authorization": f"Bearer {admin_user_token['access_token']}"}

    # Create script
    response = client.post(
        "/api/admin/filter-scripts",
        headers=headers,
        json=TEST_BASH_SCRIPT
    )
    assert response.status_code == 201

    # List with content
    response = client.get(
        "/api/admin/filter-scripts?include_content=true",
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert "script_content" in data["items"][0]
    assert data["items"][0]["script_content"] == TEST_BASH_SCRIPT["script_content"]

    # Clean up
    Path("config/filters/test-bash-filter.sh").unlink(missing_ok=True)
