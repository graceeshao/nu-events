"""Tests for the events and scrapers API endpoints.

Covers CRUD operations, filtering, pagination, and error cases.
"""

from datetime import datetime, timedelta

import pytest


class TestHealthCheck:
    """Test the root health endpoint."""

    @pytest.mark.asyncio
    async def test_root(self, client) -> None:
        """GET / returns health status."""
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestCreateEvent:
    """Test POST /events."""

    @pytest.mark.asyncio
    async def test_create_event(self, client, sample_event_data) -> None:
        """POST /events creates and returns the event."""
        resp = await client.post("/events", json=sample_event_data)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == sample_event_data["title"]
        assert data["category"] == "academic"
        assert "id" in data
        assert "dedup_key" in data

    @pytest.mark.asyncio
    async def test_create_event_minimal(self, client) -> None:
        """POST /events works with only required fields."""
        payload = {
            "title": "Quick Meetup",
            "start_time": datetime.now().isoformat(),
        }
        resp = await client.post("/events", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Quick Meetup"
        assert data["category"] == "other"

    @pytest.mark.asyncio
    async def test_create_event_missing_title(self, client) -> None:
        """POST /events rejects missing title."""
        payload = {"start_time": datetime.now().isoformat()}
        resp = await client.post("/events", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_event_missing_start_time(self, client) -> None:
        """POST /events rejects missing start_time."""
        payload = {"title": "No Time Event"}
        resp = await client.post("/events", json=payload)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_duplicate_returns_existing(self, client, sample_event_data) -> None:
        """POST /events with identical data returns the existing event (dedup)."""
        resp1 = await client.post("/events", json=sample_event_data)
        resp2 = await client.post("/events", json=sample_event_data)
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["id"] == resp2.json()["id"]


class TestGetEvent:
    """Test GET /events/{id}."""

    @pytest.mark.asyncio
    async def test_get_event(self, client, sample_event_data) -> None:
        """GET /events/{id} returns the event."""
        create_resp = await client.post("/events", json=sample_event_data)
        event_id = create_resp.json()["id"]

        resp = await client.get(f"/events/{event_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == event_id

    @pytest.mark.asyncio
    async def test_get_event_not_found(self, client) -> None:
        """GET /events/{id} returns 404 for nonexistent ID."""
        resp = await client.get("/events/9999")
        assert resp.status_code == 404


class TestListEvents:
    """Test GET /events with filters and pagination."""

    @pytest.mark.asyncio
    async def test_list_events_empty(self, client) -> None:
        """GET /events returns empty list when no events exist."""
        resp = await client.get("/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_events_with_data(self, client, sample_event_data) -> None:
        """GET /events returns created events."""
        await client.post("/events", json=sample_event_data)
        resp = await client.get("/events")
        data = resp.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_events_filter_category(self, client) -> None:
        """GET /events?category= filters by category."""
        now = datetime.now()
        await client.post("/events", json={
            "title": "Academic Talk",
            "start_time": (now + timedelta(days=1)).isoformat(),
            "category": "academic",
        })
        await client.post("/events", json={
            "title": "Sports Game",
            "start_time": (now + timedelta(days=2)).isoformat(),
            "category": "sports",
        })

        resp = await client.get("/events", params={"category": "academic"})
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Academic Talk"

    @pytest.mark.asyncio
    async def test_list_events_filter_search(self, client, sample_event_data) -> None:
        """GET /events?search= searches title and description."""
        await client.post("/events", json=sample_event_data)
        resp = await client.get("/events", params={"search": "Machine Learning"})
        assert resp.json()["total"] == 1

        resp = await client.get("/events", params={"search": "nonexistent"})
        assert resp.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_list_events_pagination(self, client) -> None:
        """GET /events respects page and page_size."""
        now = datetime.now()
        for i in range(5):
            await client.post("/events", json={
                "title": f"Event {i}",
                "start_time": (now + timedelta(days=i)).isoformat(),
            })

        resp = await client.get("/events", params={"page": 1, "page_size": 2})
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["pages"] == 3

        resp = await client.get("/events", params={"page": 3, "page_size": 2})
        data = resp.json()
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_events_date_range(self, client) -> None:
        """GET /events?date_from=&date_to= filters by date range."""
        base = datetime(2025, 6, 1, 12, 0)
        for i in range(3):
            await client.post("/events", json={
                "title": f"June Event {i}",
                "start_time": (base + timedelta(days=i)).isoformat(),
            })

        resp = await client.get("/events", params={
            "date_from": base.isoformat(),
            "date_to": (base + timedelta(days=1)).isoformat(),
        })
        data = resp.json()
        assert data["total"] == 2


class TestDeleteEvent:
    """Test DELETE /events/{id}."""

    @pytest.mark.asyncio
    async def test_delete_event(self, client, sample_event_data) -> None:
        """DELETE /events/{id} removes the event."""
        create_resp = await client.post("/events", json=sample_event_data)
        event_id = create_resp.json()["id"]

        resp = await client.delete(f"/events/{event_id}")
        assert resp.status_code == 204

        resp = await client.get(f"/events/{event_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_event_not_found(self, client) -> None:
        """DELETE /events/{id} returns 404 for nonexistent ID."""
        resp = await client.delete("/events/9999")
        assert resp.status_code == 404


class TestScrapersAPI:
    """Test scraper management endpoints."""

    @pytest.mark.asyncio
    async def test_list_scrapers(self, client) -> None:
        """GET /scrapers returns registered scrapers."""
        resp = await client.get("/scrapers")
        assert resp.status_code == 200
        data = resp.json()
        names = [s["name"] for s in data]
        assert "planitpurple" in names
        assert "wildcat_connection" in names

    @pytest.mark.asyncio
    async def test_run_scraper_not_found(self, client) -> None:
        """POST /scrapers/{name}/run returns 404 for unknown scraper."""
        resp = await client.post("/scrapers/nonexistent/run")
        assert resp.status_code == 404
