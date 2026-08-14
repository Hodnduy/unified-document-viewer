"""Search History API Router.

Provides the ``GET /history`` endpoint to query past VIN searches
stored in the persistent database — proving that the DB layer is
fully operational.
"""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db_session
from src.models import SearchHistory
from src.schemas.history import SearchHistoryItem, SearchHistoryResponse

router = APIRouter(prefix="/history", tags=["Search History"])


@router.get(
    "",
    summary="Get search history records",
    response_model=SearchHistoryResponse,
    response_description="Paginated list of past VIN searches",
)
async def get_search_history(
    vin: Annotated[
        Optional[str],
        Query(
            description="Filter history by a specific VIN (optional).",
            min_length=17,
            max_length=17,
            pattern="^[a-zA-Z0-9]{17}$",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(description="Maximum number of records to return.", ge=1, le=100),
    ] = 20,
    offset: Annotated[
        int,
        Query(description="Number of records to skip for pagination.", ge=0),
    ] = 0,
    db: AsyncSession = Depends(get_db_session),
) -> SearchHistoryResponse:
    """Retrieve past VIN search records from the database.

    Supports optional filtering by VIN and simple offset-based pagination.
    Records are returned in reverse chronological order (newest first).
    """
    # Build base query
    base_filter = select(SearchHistory)
    count_filter = select(func.count(SearchHistory.id))

    if vin:
        base_filter = base_filter.where(SearchHistory.vin == vin)
        count_filter = count_filter.where(SearchHistory.vin == vin)

    # Total count
    total_result = await db.execute(count_filter)
    total = total_result.scalar() or 0

    # Fetch paginated records (newest first)
    query = (
        base_filter
        .order_by(SearchHistory.searched_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    rows = result.scalars().all()

    return SearchHistoryResponse(
        total=total,
        records=[SearchHistoryItem.model_validate(row) for row in rows],
    )
