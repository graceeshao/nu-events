"""API routes for campus organizations.

Provides CRUD endpoints for managing organizations with filtering
and pagination support.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.session import get_db
from src.schemas.organization import (
    OrganizationCreate,
    OrganizationList,
    OrganizationRead,
    OrganizationUpdate,
)
from src.services.organization_service import (
    create_organization,
    delete_organization,
    get_organization,
    list_organizations,
    update_organization,
)

router = APIRouter()


@router.get("", response_model=OrganizationList)
async def list_orgs(
    category: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> OrganizationList:
    """List organizations with optional category filter, search, and pagination."""
    return await list_organizations(
        db, category=category, search=search, page=page, page_size=page_size
    )


@router.get("/{org_id}", response_model=OrganizationRead)
async def get_org(
    org_id: int,
    db: AsyncSession = Depends(get_db),
) -> OrganizationRead:
    """Get a single organization by ID."""
    org = await get_organization(db, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationRead.model_validate(org)


@router.post("", response_model=OrganizationRead, status_code=201)
async def create_org(
    org_in: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
) -> OrganizationRead:
    """Create a new organization."""
    org = await create_organization(db, org_in)
    return OrganizationRead.model_validate(org)


@router.patch("/{org_id}", response_model=OrganizationRead)
async def update_org(
    org_id: int,
    org_in: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
) -> OrganizationRead:
    """Partially update an organization by ID."""
    org = await update_organization(db, org_id, org_in)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrganizationRead.model_validate(org)


@router.delete("/{org_id}", status_code=204)
async def delete_org(
    org_id: int,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an organization by ID."""
    deleted = await delete_organization(db, org_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Organization not found")
