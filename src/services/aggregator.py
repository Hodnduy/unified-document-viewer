"""Document Aggregation Service.

Fetches documents from external Sales and Service APIs, normalises each
response into the ``UnifiedDocument`` schema, and surfaces errors gracefully
without crashing the application.
"""

from __future__ import annotations

import uuid
from typing import Dict, List, Union

import httpx

from src.core.config import settings
from src.schemas.document import UnifiedDocument

# Hard timeout applied to every outbound request (seconds).
_REQUEST_TIMEOUT = 3.0


class DocumentAggregator:
    """Fetches and normalises documents from Sales and Service APIs.

    Each ``fetch_*`` method accepts an ``httpx.AsyncClient`` and a ``vin``
    string.  On success it returns a list of ``UnifiedDocument`` instances;
    on failure it returns a dict ``{'status': 'error', 'message': ...}``
    so that one failing source never crashes the whole aggregation.
    """

    def __init__(self) -> None:
        self.sales_base_url: str = settings.SALES_SERVICE_URL
        self.service_base_url: str = settings.SERVICE_SERVICE_URL

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_to_unified(
        raw_doc: dict,
        vin: str,
        source_system: str,
    ) -> UnifiedDocument:
        """Convert a single raw API document into a ``UnifiedDocument``."""
        return UnifiedDocument(
            id=f"doc_{uuid.uuid4().hex[:8]}",
            external_id=raw_doc["id"],
            vin=vin,
            title=raw_doc["title"],
            document_type=raw_doc["type"],
            source_system=source_system,
            date=raw_doc["date"],
            metadata=raw_doc.get("metadata", {}),
        )

    # ------------------------------------------------------------------
    # Public async fetchers
    # ------------------------------------------------------------------

    async def fetch_sales_docs(
        self,
        client: httpx.AsyncClient,
        vin: str,
    ) -> Union[List[UnifiedDocument], Dict[str, str]]:
        """Fetch documents from the Sales System API.

        Parameters
        ----------
        client:
            A reusable ``httpx.AsyncClient`` instance.
        vin:
            Vehicle Identification Number to query.

        Returns
        -------
        list[UnifiedDocument]
            Normalised documents on success.
        dict
            ``{'status': 'error', 'message': '<detail>'}`` on failure.
        """
        try:
            response = await client.get(
                f"{self.sales_base_url}/sales/documents",
                params={"vin": vin},
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()
            return [
                self._map_to_unified(doc, vin=vin, source_system="sales")
                for doc in data.get("documents", [])
            ]
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"status": "error", "message": str(e)}

    async def fetch_service_docs(
        self,
        client: httpx.AsyncClient,
        vin: str,
    ) -> Union[List[UnifiedDocument], Dict[str, str]]:
        """Fetch documents from the Service System API.

        Parameters
        ----------
        client:
            A reusable ``httpx.AsyncClient`` instance.
        vin:
            Vehicle Identification Number to query.

        Returns
        -------
        list[UnifiedDocument]
            Normalised documents on success.
        dict
            ``{'status': 'error', 'message': '<detail>'}`` on failure.
        """
        try:
            response = await client.get(
                f"{self.service_base_url}/service/documents",
                params={"vin": vin},
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()
            return [
                self._map_to_unified(doc, vin=vin, source_system="service")
                for doc in data.get("documents", [])
            ]
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            return {"status": "error", "message": str(e)}
