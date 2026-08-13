"""Document Aggregation Service.

Fetches documents from external Sales and Service APIs, normalises each
response into the ``UnifiedDocument`` schema, and surfaces errors gracefully
without crashing the application.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Union

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

    @staticmethod
    def _is_error(result: Any) -> bool:
        """Return ``True`` if *result* is an exception or an error dict."""
        if isinstance(result, Exception):
            return True
        if isinstance(result, dict) and result.get("status") == "error":
            return True
        return False

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

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

    async def get_aggregated_documents(
        self,
        vin: str,
    ) -> Dict[str, Any]:
        """Fetch documents from **all** sources concurrently and merge them.

        Creates its own ``httpx.AsyncClient`` for connection pooling,
        fires ``fetch_sales_docs`` and ``fetch_service_docs`` in parallel
        via ``asyncio.gather(return_exceptions=True)``, then merges the
        successful results into a single list.

        Parameters
        ----------
        vin:
            Vehicle Identification Number to query across all sources.

        Returns
        -------
        dict
            ``{"vin": str, "documents": list[UnifiedDocument],
              "degraded": bool}``

            * **documents** – unified list from every source that responded
              successfully.
            * **degraded** – ``True`` when at least one source returned an
              error or raised an exception; ``False`` when all sources
              responded successfully.
        """
        async with httpx.AsyncClient() as client:
            sales_result, service_result = await asyncio.gather(
                self.fetch_sales_docs(client, vin),
                self.fetch_service_docs(client, vin),
                return_exceptions=True,
            )

        all_documents: List[UnifiedDocument] = []
        degraded = False
        sources: Dict[str, Any] = {"sales": {}, "service": {}}

        # -- Sales source ------------------------------------------------
        if self._is_error(sales_result):
            degraded = True
            error_msg = (
                str(sales_result)
                if isinstance(sales_result, Exception)
                else sales_result.get("message", "Unknown error")
            )
            sources["sales"] = {"status": "error", "error": error_msg}
        else:
            all_documents.extend(sales_result)
            sources["sales"] = {"status": "success", "count": len(sales_result)}

        # -- Service source ----------------------------------------------
        if self._is_error(service_result):
            degraded = True
            error_msg = (
                str(service_result)
                if isinstance(service_result, Exception)
                else service_result.get("message", "Unknown error")
            )
            sources["service"] = {"status": "error", "error": error_msg}
        else:
            all_documents.extend(service_result)
            sources["service"] = {"status": "success", "count": len(service_result)}

        return {
            "vin": vin,
            "documents": all_documents,
            "sources": sources,
            "degraded": degraded,
        }
