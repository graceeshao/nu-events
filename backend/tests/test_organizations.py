"""Tests for organization CRUD endpoints."""

import pytest


@pytest.mark.asyncio
async def test_create_organization(client):
    """POST /organizations creates a new org and returns 201."""
    payload = {
        "name": "Test Org",
        "category": "RSO",
        "tags": ["Academic"],
        "club_id": 99999,
    }
    resp = await client.post("/organizations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Org"
    assert data["category"] == "RSO"
    assert data["tags"] == ["Academic"]
    assert data["club_id"] == 99999
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_organizations(client):
    """GET /organizations returns paginated list."""
    # Create two orgs
    await client.post("/organizations", json={"name": "Org A", "category": "RSO"})
    await client.post("/organizations", json={"name": "Org B", "category": "FSL"})

    resp = await client.get("/organizations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.asyncio
async def test_list_organizations_filter_category(client):
    """GET /organizations?category=FSL filters by category."""
    await client.post("/organizations", json={"name": "Org A", "category": "RSO"})
    await client.post("/organizations", json={"name": "Org B", "category": "FSL"})

    resp = await client.get("/organizations", params={"category": "FSL"})
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["category"] == "FSL"


@pytest.mark.asyncio
async def test_list_organizations_search(client):
    """GET /organizations?search=... filters by name."""
    await client.post("/organizations", json={"name": "Alpha Chi Omega", "category": "FSL"})
    await client.post("/organizations", json={"name": "Beta Club", "category": "RSO"})

    resp = await client.get("/organizations", params={"search": "alpha"})
    data = resp.json()
    assert data["total"] == 1
    assert "Alpha" in data["items"][0]["name"]


@pytest.mark.asyncio
async def test_get_organization(client):
    """GET /organizations/{id} returns the org."""
    create_resp = await client.post(
        "/organizations", json={"name": "Get Me", "category": "RSO"}
    )
    org_id = create_resp.json()["id"]

    resp = await client.get(f"/organizations/{org_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Me"


@pytest.mark.asyncio
async def test_get_organization_not_found(client):
    """GET /organizations/{id} returns 404 for missing org."""
    resp = await client.get("/organizations/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_organization(client):
    """PATCH /organizations/{id} partially updates the org."""
    create_resp = await client.post(
        "/organizations", json={"name": "Update Me", "category": "RSO"}
    )
    org_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/organizations/{org_id}",
        json={"category": "TGS", "instagram_handle": "@updateme"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "TGS"
    assert data["instagram_handle"] == "@updateme"
    assert data["name"] == "Update Me"  # unchanged


@pytest.mark.asyncio
async def test_delete_organization(client):
    """DELETE /organizations/{id} removes the org."""
    create_resp = await client.post(
        "/organizations", json={"name": "Delete Me", "category": "RSO"}
    )
    org_id = create_resp.json()["id"]

    resp = await client.delete(f"/organizations/{org_id}")
    assert resp.status_code == 204

    # Confirm gone
    resp = await client.get(f"/organizations/{org_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_organization_not_found(client):
    """DELETE /organizations/{id} returns 404 for missing org."""
    resp = await client.delete("/organizations/9999")
    assert resp.status_code == 404
