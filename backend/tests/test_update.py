"""Tests for the PATCH /events/{id} endpoint.

Verifies partial updates, nonexistent event handling, and field preservation.
"""

from datetime import datetime, timedelta

import pytest


@pytest.mark.asyncio
async def test_patch_partial_update(client, sample_event_data: dict) -> None:
    """PATCH updates only the provided fields."""
    # Create an event first
    resp = await client.post("/events", json=sample_event_data)
    assert resp.status_code == 201
    event = resp.json()
    event_id = event["id"]

    # Patch only the title
    patch_resp = await client.patch(f"/events/{event_id}", json={"title": "Updated Title"})
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["title"] == "Updated Title"
    # Other fields should remain unchanged
    assert updated["description"] == sample_event_data["description"]
    assert updated["location"] == sample_event_data["location"]
    assert updated["category"] == sample_event_data["category"]


@pytest.mark.asyncio
async def test_patch_nonexistent_event(client) -> None:
    """PATCH returns 404 for a nonexistent event."""
    resp = await client.patch("/events/99999", json={"title": "Ghost Event"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_multiple_fields(client, sample_event_data: dict) -> None:
    """PATCH can update multiple fields at once."""
    resp = await client.post("/events", json=sample_event_data)
    assert resp.status_code == 201
    event_id = resp.json()["id"]

    new_data = {
        "title": "New Title",
        "location": "New Location",
        "category": "sports",
    }
    patch_resp = await client.patch(f"/events/{event_id}", json=new_data)
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["title"] == "New Title"
    assert updated["location"] == "New Location"
    assert updated["category"] == "sports"
    # Description should remain unchanged
    assert updated["description"] == sample_event_data["description"]


@pytest.mark.asyncio
async def test_patch_empty_body(client, sample_event_data: dict) -> None:
    """PATCH with empty body returns the event unchanged."""
    resp = await client.post("/events", json=sample_event_data)
    assert resp.status_code == 201
    event = resp.json()
    event_id = event["id"]

    patch_resp = await client.patch(f"/events/{event_id}", json={})
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["title"] == sample_event_data["title"]
    assert updated["description"] == sample_event_data["description"]
