"""Pydantic schemas for Search History responses."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SearchHistoryItem(BaseModel):
    """A single search history record."""

    id: UUID = Field(..., description="Unique identifier of the search record.")
    vin: str = Field(..., description="The VIN that was searched.")
    searched_at: datetime = Field(
        ..., description="UTC timestamp of when the search was performed."
    )
    total_documents: int = Field(
        ..., description="Number of documents returned in the search."
    )
    is_degraded: bool = Field(
        ...,
        description="Whether the search result was degraded (at least one source failed).",
    )

    model_config = {"from_attributes": True}


class SearchHistoryResponse(BaseModel):
    """Response for the search history endpoint."""

    total: int = Field(..., description="Total number of matching history records.")
    records: list[SearchHistoryItem] = Field(
        ..., description="List of search history records."
    )
