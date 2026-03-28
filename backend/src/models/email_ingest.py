"""SQLAlchemy model for ingested email records.

Tracks every email submitted to the ingest endpoint, along with its
processing status and how many events were extracted from it.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models.event import Base


class IngestedEmail(Base):
    """Record of an email submitted for event extraction."""

    __tablename__ = "ingested_emails"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sender: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    events_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<IngestedEmail(id={self.id}, status='{self.status}')>"
