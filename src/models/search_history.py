"""SearchHistory ORM model for persistent search logging."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class SearchHistory(Base):
    """Stores each VIN search performed through the API."""

    __tablename__ = "search_history"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )
    vin: Mapped[str] = mapped_column(String(17), index=True, nullable=False)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    total_documents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_degraded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<SearchHistory(id={self.id!r}, vin={self.vin!r}, "
            f"searched_at={self.searched_at!r})>"
        )
