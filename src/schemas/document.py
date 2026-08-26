"""Pydantic schemas for Document requests and responses."""

from __future__ import annotations

from datetime import date as Date
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


class UnifiedDocument(BaseModel):
    """A single document returned by the aggregation layer.

    Mirrors the document object described in SYSTEM_DESIGN.md §5.2.
    """

    id: str = Field(
        ...,
        description="Internal unique identifier (e.g. 'doc_a1b2c3').",
        examples=["doc_a1b2c3"],
    )
    external_id: Optional[str] = Field(
        default=None,
        description="Identifier from the originating source system.",
        examples=["SALE-2024-78432"],
    )
    vin: str = Field(
        ...,
        description="Vehicle Identification Number the document belongs to.",
        examples=["1HGCM82633A004352"],
    )
    title: str = Field(
        ...,
        description="Human-readable document title.",
        examples=["Vehicle Purchase Agreement"],
    )
    document_type: str = Field(
        ...,
        description="Category of the document (e.g. 'contract', 'service_report').",
        examples=["contract", "service_report"],
    )
    source_system: Literal["sales", "service"] = Field(
        ...,
        description="The upstream system that produced this document.",
    )
    date: Date = Field(
        ...,
        description="Primary date associated with the document (ISO-8601).",
        examples=["2024-03-15"],
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary key-value pairs specific to the source system.",
        examples=[{"dealer_name": "AutoNation Honda", "amount": 32500.00}],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "doc_a1b2c3",
                    "external_id": "SALE-2024-78432",
                    "vin": "1HGCM82633A004352",
                    "title": "Vehicle Purchase Agreement",
                    "document_type": "contract",
                    "source_system": "sales",
                    "date": "2024-03-15",
                    "metadata": {
                        "dealer_name": "AutoNation Honda",
                        "amount": 32500.00,
                    },
                }
            ]
        }
    }


class SourceStatus(BaseModel):
    """Per-source status included in the aggregated response.

    Mirrors the ``sources`` object described in SYSTEM_DESIGN.md §5.2.
    """

    status: Literal["success", "error"] = Field(
        ...,
        description="Whether the upstream source responded successfully.",
    )
    count: Optional[int] = Field(
        default=None,
        description="Number of documents returned (present on success).",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error detail message (present on failure).",
    )


class AggregatedDocumentsResponse(BaseModel):
    """Top-level response returned by ``GET /api/v1/documents``.

    Matches the JSON structure defined in SYSTEM_DESIGN.md §5.2.
    The endpoint **always** returns HTTP 200; partial upstream failures
    are signalled via ``degraded: true`` and per-source error metadata.
    """

    vin: str = Field(
        ...,
        description="The queried Vehicle Identification Number.",
        examples=["1HGCM82633A004352"],
    )
    documents: list[UnifiedDocument] = Field(
        ...,
        description="Unified list of documents from all responding sources.",
    )
    sources: Dict[str, SourceStatus] = Field(
        ...,
        description="Per-source fetch status (keyed by source name).",
    )
    degraded: bool = Field(
        ...,
        description=(
            "``true`` when at least one upstream source failed; "
            "``false`` when all sources responded successfully."
        ),
    )
    timestamp: str = Field(
        ...,
        description="ISO-8601 UTC timestamp of when the response was generated.",
        examples=["2026-08-08T15:21:00Z"],
    )
    cache_hit: bool = Field(
        ...,
        description="Whether the response was served from the Redis cache.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "vin": "1HGCM82633A004352",
                    "documents": [],
                    "sources": {
                        "sales": {"status": "success", "count": 2},
                        "service": {"status": "error", "error": "Connection timeout"},
                    },
                    "degraded": True,
                    "timestamp": "2026-08-08T15:21:00Z",
                    "cache_hit": False,
                }
            ]
        }
    }
