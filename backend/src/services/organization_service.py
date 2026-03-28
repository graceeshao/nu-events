"""Organization business logic: CRUD operations with filtering and pagination.

All database operations go through this service layer so that routes
remain thin and logic is testable independently.
"""

import math

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.organization import Organization
from src.schemas.organization import (
    OrganizationCreate,
    OrganizationList,
    OrganizationRead,
    OrganizationUpdate,
)


async def create_organization(
    db: AsyncSession, org_in: OrganizationCreate
) -> Organization:
    """Create a new organization.

    Args:
        db: Async database session.
        org_in: Validated organization data.

    Returns:
        The created Organization ORM instance.
    """
    org = Organization(**org_in.model_dump())
    db.add(org)
    await db.flush()
    await db.refresh(org)
    return org


async def list_organizations(
    db: AsyncSession,
    *,
    category: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> OrganizationList:
    """List organizations with optional filters and pagination.

    Args:
        db: Async database session.
        category: Filter by organization category.
        search: Free-text search across name.
        page: Page number (1-indexed).
        page_size: Number of results per page.

    Returns:
        OrganizationList with items, total count, and pagination metadata.
    """
    query = select(Organization)

    if category is not None:
        query = query.where(Organization.category == category)
    if search:
        pattern = f"%{search}%"
        query = query.where(Organization.name.ilike(pattern))

    # Total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Paginate
    query = query.order_by(Organization.name.asc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    orgs = result.scalars().all()

    return OrganizationList(
        items=[OrganizationRead.model_validate(o) for o in orgs],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


async def get_organization(db: AsyncSession, org_id: int) -> Organization | None:
    """Get a single organization by ID.

    Args:
        db: Async database session.
        org_id: Primary key of the organization.

    Returns:
        The Organization if found, else None.
    """
    result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    return result.scalar_one_or_none()


async def update_organization(
    db: AsyncSession, org_id: int, org_in: OrganizationUpdate
) -> Organization | None:
    """Partially update an organization by ID.

    Only fields explicitly set (not None) in org_in are updated.

    Args:
        db: Async database session.
        org_id: Primary key of the organization to update.
        org_in: Partial update data.

    Returns:
        The updated Organization if found, else None.
    """
    org = await get_organization(db, org_id)
    if org is None:
        return None

    update_data = org_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(org, field, value)

    await db.flush()
    await db.refresh(org)
    return org


async def delete_organization(db: AsyncSession, org_id: int) -> bool:
    """Delete an organization by ID.

    Args:
        db: Async database session.
        org_id: Primary key of the organization to delete.

    Returns:
        True if the organization was deleted, False if not found.
    """
    org = await get_organization(db, org_id)
    if org is None:
        return False
    await db.delete(org)
    await db.flush()
    return True
