"""SQLAlchemy model for campus organizations.

Stores registered student organizations, Greek life chapters, residential
colleges, and campus departments sourced from WildcatConnection.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.event import Base


class Organization(Base):
    """A campus organization (RSO, FSL chapter, residential college, etc.)."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(200), nullable=False)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    club_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    instagram_handle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    website: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    email: Mapped[str | None] = mapped_column(String(500), nullable=True)
    listserv_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    instagram_active: Mapped[bool | None] = mapped_column(default=True, nullable=True)
    instagram_last_post_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    instagram_last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name='{self.name}')>"
