"""Pydantic schemas for event data validation and serialization.

Defines the request/response shapes for the events API, including
pagination metadata for list responses.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.models.event import EventCategory


class EventBase(BaseModel):
    """Shared fields for event creation and reading."""

    title: str = Field(..., min_length=1, max_length=500, description="Event title")
    description: str | None = Field(None, description="Event description")
    start_time: datetime = Field(..., description="Event start time (ISO 8601)")
    end_time: datetime | None = Field(None, description="Event end time")
    location: str | None = Field(None, max_length=500, description="Venue or address")
    source_url: str | None = Field(None, description="URL of the original event page")
    source_name: str | None = Field(None, description="Name of the source (e.g. 'Northwestern Events')")
    category: EventCategory = Field(EventCategory.OTHER, description="Event category")
    tags: dict | None = Field(None, description="Arbitrary tags as JSON")
    image_url: str | None = Field(None, description="URL of an event image")
    rsvp_url: str | None = Field(None, description="RSVP or registration URL")
    has_free_food: bool = Field(False, description="Whether free food is offered")


class EventCreate(EventBase):
    """Schema for creating a new event. Dedup key is generated server-side."""

    pass


class EventUpdate(BaseModel):
    """Schema for partially updating an event. All fields are optional."""

    title: str | None = Field(None, min_length=1, max_length=500, description="Event title")
    description: str | None = Field(None, description="Event description")
    start_time: datetime | None = Field(None, description="Event start time (ISO 8601)")
    end_time: datetime | None = Field(None, description="Event end time")
    location: str | None = Field(None, max_length=500, description="Venue or address")
    source_url: str | None = Field(None, description="URL of the original event page")
    source_name: str | None = Field(None, description="Name of the source")
    category: EventCategory | None = Field(None, description="Event category")
    tags: dict | None = Field(None, description="Arbitrary tags as JSON")
    image_url: str | None = Field(None, description="URL of an event image")
    rsvp_url: str | None = None
    has_free_food: bool | None = None


class EventRead(EventBase):
    """Schema for reading an event, includes DB-generated fields."""

    id: int
    dedup_key: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventList(BaseModel):
    """Paginated list of events with metadata."""

    items: list[EventRead]
    total: int = Field(..., description="Total number of matching events")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")
