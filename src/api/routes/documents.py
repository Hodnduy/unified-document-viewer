"""Documents API Router.

Provides the ``GET /documents`` endpoint that aggregates vehicle documents
from multiple upstream sources (Sales, Service) using the
:class:`~src.services.aggregator.DocumentAggregator`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query

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
        ),
    ],
) -> AggregatedDocumentsResponse:
    """Fetch and merge documents from Sales and Service systems.

    The ``vin`` query parameter is **required** and must be exactly
    17 characters long, matching the ISO 3779 VIN standard.

    The endpoint **always** returns HTTP 200.  When one upstream source
    fails, the available documents are still returned and the response
    includes ``"degraded": true`` with per-source error metadata.

    Response structure (SYSTEM_DESIGN.md §5.2):
    - **vin** – the queried VIN.
    - **documents** – a unified list of documents from all sources.
    - **sources** – per-source status (``success`` or ``error``).
    - **degraded** – ``true`` when at least one source failed.
    - **timestamp** – ISO-8601 UTC timestamp of the response.
    """
    aggregator = DocumentAggregator()
    result = await aggregator.get_aggregated_documents(vin)

    return AggregatedDocumentsResponse(
        vin=result["vin"],
        documents=result["documents"],
        sources=result["sources"],
        degraded=result["degraded"],
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

