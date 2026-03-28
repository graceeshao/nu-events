"""Pydantic schemas for organization data validation and serialization."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationBase(BaseModel):
    """Shared fields for organization creation and reading."""

    name: str = Field(..., min_length=1, max_length=500, description="Organization name")
    category: str = Field(..., max_length=200, description="Category (RSO, TGS, FSL, etc.)")
    tags: list[str] | None = Field(None, description="List of tag strings")
    club_id: int | None = Field(None, description="WildcatConnection club ID")
    instagram_handle: str | None = Field(None, max_length=200, description="Instagram handle")
    website: str | None = Field(None, max_length=2000, description="Website URL")
    email: str | None = Field(None, max_length=500, description="Contact email")
    listserv_name: str | None = Field(None, max_length=200, description="LISTSERV list name")


class OrganizationCreate(OrganizationBase):
    """Schema for creating a new organization."""

    pass


class OrganizationRead(OrganizationBase):
    """Schema for reading an organization, includes DB-generated fields."""

    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationUpdate(BaseModel):
    """Schema for partially updating an organization. All fields optional."""

    name: str | None = Field(None, min_length=1, max_length=500, description="Organization name")
    category: str | None = Field(None, max_length=200, description="Category")
    tags: list[str] | None = Field(None, description="List of tag strings")
    club_id: int | None = Field(None, description="WildcatConnection club ID")
    instagram_handle: str | None = Field(None, max_length=200, description="Instagram handle")
    website: str | None = Field(None, max_length=2000, description="Website URL")
    email: str | None = Field(None, max_length=500, description="Contact email")
    listserv_name: str | None = Field(None, max_length=200, description="LISTSERV list name")


class OrganizationList(BaseModel):
    """Paginated list of organizations with metadata."""

    items: list[OrganizationRead]
    total: int = Field(..., description="Total number of matching organizations")
    page: int = Field(..., description="Current page number (1-indexed)")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")
