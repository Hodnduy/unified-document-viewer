"""Documents API Router.

Provides the ``GET /documents`` endpoint that aggregates vehicle documents
from multiple upstream sources (Sales, Service) using the
:class:`~src.services.aggregator.DocumentAggregator`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_db_session
from src.models import SearchHistory
from src.schemas.document import AggregatedDocumentsResponse
from src.services.aggregator import DocumentAggregator

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get(
    "",
    summary="Get aggregated documents for a VIN",
    response_model=AggregatedDocumentsResponse,
    response_model_exclude_none=True,
    response_description="Aggregated documents from all source systems",
)
async def get_documents(
    vin: Annotated[
        str,
        Query(
            description="Vehicle Identification Number (exactly 17 characters)",
            min_length=17,
            max_length=17,
            pattern="^[a-zA-Z0-9]{17}$",
        ),
    ],
    force_refresh: Annotated[
        bool,
        Query(
            description="Bypass cache and fetch fresh data from upstream APIs.",
        ),
    ] = False,
    db: AsyncSession = Depends(get_db_session),
    aggregator: DocumentAggregator = Depends(DocumentAggregator),
) -> AggregatedDocumentsResponse:
    """Fetch and merge documents from Sales and Service systems.

    The ``vin`` query parameter is **required** and must be exactly
    17 characters long, matching the ISO 3779 VIN standard.

    Set ``force_refresh=true`` to bypass the Redis cache and fetch
    fresh data from the upstream APIs.

    The endpoint **always** returns HTTP 200.  When one upstream source
    fails, the available documents are still returned and the response
    includes ``"degraded": true`` with per-source error metadata.

    Response structure (SYSTEM_DESIGN.md §5.2):
    - **vin** – the queried VIN.
    - **documents** – a unified list of documents from all sources.
    - **sources** – per-source status (``success`` or ``error``).
    - **degraded** – ``true`` when at least one source failed.
    - **timestamp** – ISO-8601 UTC timestamp of the response.
    - **cache_hit** – ``true`` when the response was served from cache.
    """
    result = await aggregator.get_aggregated_documents(vin, force_refresh=force_refresh)

    # Persist search history record
    record = SearchHistory(
        vin=vin,
        total_documents=len(result["documents"]),
        is_degraded=result["degraded"],
    )
    db.add(record)
    await db.commit()

    return AggregatedDocumentsResponse(
        vin=result["vin"],
        documents=result["documents"],
        sources=result["sources"],
        degraded=result["degraded"],
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        cache_hit=result["cache_hit"],
    )
