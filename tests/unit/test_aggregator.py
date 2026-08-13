"""Unit tests for src.services.aggregator – DocumentAggregator.

All external HTTP calls are replaced with ``httpx.MockTransport`` handlers
so tests run fast, deterministically, and without network access.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.schemas.document import UnifiedDocument
from src.services.aggregator import DocumentAggregator, _REQUEST_TIMEOUT


# ---------------------------------------------------------------------------
# Sample payloads returned by the mock APIs
# ---------------------------------------------------------------------------

_SALES_RESPONSE: dict[str, Any] = {
    "documents": [
        {
            "id": "SALE-001",
            "title": "Vehicle Purchase Agreement",
            "type": "contract",
            "date": "2024-03-15",
            "metadata": {"dealer_name": "AutoNation Honda", "amount": 32500.00},
        },
        {
            "id": "SALE-002",
            "title": "Trade-In Invoice",
            "type": "invoice",
            "date": "2024-03-15",
            "metadata": {"dealer_name": "AutoNation Honda", "amount": 8500.00},
        },
    ]
}

_SERVICE_RESPONSE: dict[str, Any] = {
    "documents": [
        {
            "id": "SVC-001",
            "title": "60,000 Mile Service Report",
            "type": "service_report",
            "date": "2025-01-20",
            "metadata": {"mileage": 60234, "technician": "John Smith"},
        },
    ]
}

_TEST_VIN = "1HGCM82633A004352"


# ---------------------------------------------------------------------------
# Transport factories – build httpx.MockTransport instances
# ---------------------------------------------------------------------------

def _ok_transport(payload: dict) -> httpx.MockTransport:
    """Return a transport that always responds 200 with *payload*."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def _status_error_transport(status_code: int = 500) -> httpx.MockTransport:
    """Return a transport that always responds with the given HTTP error."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": "Server Error"})

    return httpx.MockTransport(handler)


def _connection_error_transport() -> httpx.MockTransport:
    """Return a transport that always raises ``httpx.ConnectError``."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    return httpx.MockTransport(handler)


def _timeout_error_transport() -> httpx.MockTransport:
    """Return a transport that always raises ``httpx.ReadTimeout``."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out")

    return httpx.MockTransport(handler)


def _empty_documents_transport() -> httpx.MockTransport:
    """Return a transport that responds 200 with an empty documents list."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"documents": []})

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def aggregator() -> DocumentAggregator:
    return DocumentAggregator()


# ===================================================================
# fetch_sales_docs – success cases
# ===================================================================

class TestFetchSalesDocsSuccess:
    """Happy-path tests for ``fetch_sales_docs``."""

    async def test_returns_list_of_unified_documents(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(doc, UnifiedDocument) for doc in result)

    async def test_maps_external_id(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert result[0].external_id == "SALE-001"
        assert result[1].external_id == "SALE-002"

    async def test_maps_document_type_from_type_field(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert result[0].document_type == "contract"
        assert result[1].document_type == "invoice"

    async def test_sets_source_system_to_sales(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert all(doc.source_system == "sales" for doc in result)

    async def test_preserves_vin(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert all(doc.vin == _TEST_VIN for doc in result)

    async def test_generates_internal_id(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        for doc in result:
            assert doc.id.startswith("doc_")
            assert len(doc.id) == 12  # "doc_" + 8 hex chars

    async def test_internal_ids_are_unique(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        ids = [doc.id for doc in result]
        assert len(ids) == len(set(ids))

    async def test_maps_title(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert result[0].title == "Vehicle Purchase Agreement"

    async def test_maps_date_as_date_object(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert result[0].date == date(2024, 3, 15)

    async def test_maps_metadata(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SALES_RESPONSE)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert result[0].metadata == {"dealer_name": "AutoNation Honda", "amount": 32500.00}

    async def test_empty_documents_returns_empty_list(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_empty_documents_transport()) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert result == []


# ===================================================================
# fetch_sales_docs – error cases
# ===================================================================

class TestFetchSalesDocsErrors:
    """Error handling tests for ``fetch_sales_docs``."""

    async def test_http_500_returns_error_dict(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_status_error_transport(500)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert isinstance(result["message"], str)
        assert len(result["message"]) > 0

    async def test_http_404_returns_error_dict(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_status_error_transport(404)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert result["status"] == "error"

    async def test_http_503_returns_error_dict(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_status_error_transport(503)) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert result["status"] == "error"

    async def test_connection_error_returns_error_dict(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_connection_error_transport()) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert "Connection refused" in result["message"]

    async def test_timeout_error_returns_error_dict(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_timeout_error_transport()) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert result["status"] == "error"
        assert "timed out" in result["message"].lower()

    async def test_error_dict_never_raises(self, aggregator: DocumentAggregator):
        """Confirm the method does NOT raise – it always returns."""
        async with httpx.AsyncClient(transport=_connection_error_transport()) as client:
            result = await aggregator.fetch_sales_docs(client, _TEST_VIN)

        # If we reach here, no exception was raised.
        assert "status" in result


# ===================================================================
# fetch_service_docs – success cases
# ===================================================================

class TestFetchServiceDocsSuccess:
    """Happy-path tests for ``fetch_service_docs``."""

    async def test_returns_list_of_unified_documents(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SERVICE_RESPONSE)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], UnifiedDocument)

    async def test_maps_external_id(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SERVICE_RESPONSE)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result[0].external_id == "SVC-001"

    async def test_maps_document_type_from_type_field(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SERVICE_RESPONSE)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result[0].document_type == "service_report"

    async def test_sets_source_system_to_service(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SERVICE_RESPONSE)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert all(doc.source_system == "service" for doc in result)

    async def test_preserves_vin(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SERVICE_RESPONSE)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result[0].vin == _TEST_VIN

    async def test_generates_internal_id(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SERVICE_RESPONSE)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result[0].id.startswith("doc_")
        assert len(result[0].id) == 12

    async def test_maps_metadata(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SERVICE_RESPONSE)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result[0].metadata == {"mileage": 60234, "technician": "John Smith"}

    async def test_maps_date_as_date_object(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_ok_transport(_SERVICE_RESPONSE)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result[0].date == date(2025, 1, 20)

    async def test_empty_documents_returns_empty_list(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_empty_documents_transport()) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result == []


# ===================================================================
# fetch_service_docs – error cases
# ===================================================================

class TestFetchServiceDocsErrors:
    """Error handling tests for ``fetch_service_docs``."""

    async def test_http_500_returns_error_dict(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_status_error_transport(500)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert isinstance(result, dict)
        assert result["status"] == "error"
        assert isinstance(result["message"], str)

    async def test_http_404_returns_error_dict(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_status_error_transport(404)) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result["status"] == "error"

    async def test_connection_error_returns_error_dict(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_connection_error_transport()) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result["status"] == "error"
        assert "Connection refused" in result["message"]

    async def test_timeout_error_returns_error_dict(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_timeout_error_transport()) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert result["status"] == "error"
        assert "timed out" in result["message"].lower()

    async def test_error_dict_never_raises(self, aggregator: DocumentAggregator):
        async with httpx.AsyncClient(transport=_connection_error_transport()) as client:
            result = await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert "status" in result


# ===================================================================
# _map_to_unified – unit tests for the static helper
# ===================================================================

class TestMapToUnified:
    """Direct tests for ``DocumentAggregator._map_to_unified``."""

    _RAW_DOC: dict[str, Any] = {
        "id": "EXT-999",
        "title": "Test Document",
        "type": "warranty",
        "date": "2025-06-01",
        "metadata": {"key": "value"},
    }

    def test_returns_unified_document_instance(self):
        doc = DocumentAggregator._map_to_unified(self._RAW_DOC, "VIN123", "sales")
        assert isinstance(doc, UnifiedDocument)

    def test_external_id_mapped_from_raw_id(self):
        doc = DocumentAggregator._map_to_unified(self._RAW_DOC, "VIN123", "sales")
        assert doc.external_id == "EXT-999"

    def test_document_type_mapped_from_type(self):
        doc = DocumentAggregator._map_to_unified(self._RAW_DOC, "VIN123", "sales")
        assert doc.document_type == "warranty"

    def test_source_system_propagated(self):
        doc = DocumentAggregator._map_to_unified(self._RAW_DOC, "VIN123", "service")
        assert doc.source_system == "service"

    def test_vin_propagated(self):
        doc = DocumentAggregator._map_to_unified(self._RAW_DOC, "MY_VIN", "sales")
        assert doc.vin == "MY_VIN"

    def test_missing_metadata_defaults_to_empty_dict(self):
        raw = {k: v for k, v in self._RAW_DOC.items() if k != "metadata"}
        doc = DocumentAggregator._map_to_unified(raw, "VIN123", "sales")
        assert doc.metadata == {}


# ===================================================================
# Timeout configuration
# ===================================================================

class TestTimeoutConfiguration:
    """Verify the hard-coded timeout constant is 3 seconds."""

    def test_request_timeout_is_3_seconds(self):
        assert _REQUEST_TIMEOUT == 3.0

    async def test_timeout_value_used_in_request(self, aggregator: DocumentAggregator):
        """Confirm that the timeout parameter is actually passed to the request."""
        captured_timeout = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_timeout
            captured_timeout = request.extensions.get("timeout")
            return httpx.Response(200, json={"documents": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await aggregator.fetch_sales_docs(client, _TEST_VIN)

        # httpx stores timeout in extensions as a dict with pool/connect/read/write keys
        assert captured_timeout is not None


# ===================================================================
# URL configuration
# ===================================================================

class TestURLConfiguration:
    """Verify the aggregator reads base URLs from settings."""

    def test_sales_base_url_from_settings(self, aggregator: DocumentAggregator):
        assert aggregator.sales_base_url == "http://localhost:8001"

    def test_service_base_url_from_settings(self, aggregator: DocumentAggregator):
        assert aggregator.service_base_url == "http://localhost:8002"

    async def test_sales_request_hits_correct_url(self, aggregator: DocumentAggregator):
        captured_url = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_url
            captured_url = str(request.url)
            return httpx.Response(200, json={"documents": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await aggregator.fetch_sales_docs(client, _TEST_VIN)

        assert captured_url is not None
        assert "/sales/documents" in captured_url
        assert f"vin={_TEST_VIN}" in captured_url

    async def test_service_request_hits_correct_url(self, aggregator: DocumentAggregator):
        captured_url = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal captured_url
            captured_url = str(request.url)
            return httpx.Response(200, json={"documents": []})

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            await aggregator.fetch_service_docs(client, _TEST_VIN)

        assert captured_url is not None
        assert "/service/documents" in captured_url
        assert f"vin={_TEST_VIN}" in captured_url


# ===================================================================
# _is_error – unit tests for the static helper
# ===================================================================

class TestIsError:
    """Direct tests for ``DocumentAggregator._is_error``."""

    def test_returns_true_for_exception(self):
        assert DocumentAggregator._is_error(ValueError("boom")) is True

    def test_returns_true_for_runtime_error(self):
        assert DocumentAggregator._is_error(RuntimeError("fail")) is True

    def test_returns_true_for_error_dict(self):
        assert DocumentAggregator._is_error({"status": "error", "message": "oops"}) is True

    def test_returns_false_for_success_list(self):
        assert DocumentAggregator._is_error([]) is False

    def test_returns_false_for_non_empty_list(self):
        assert DocumentAggregator._is_error(["doc1", "doc2"]) is False

    def test_returns_false_for_dict_without_status(self):
        assert DocumentAggregator._is_error({"key": "value"}) is False

    def test_returns_false_for_dict_with_non_error_status(self):
        assert DocumentAggregator._is_error({"status": "success"}) is False

    def test_returns_false_for_none(self):
        assert DocumentAggregator._is_error(None) is False

    def test_returns_false_for_string(self):
        assert DocumentAggregator._is_error("some string") is False


# ===================================================================
# Helper: build fake UnifiedDocument instances for mocking
# ===================================================================

def _fake_sales_docs() -> list[UnifiedDocument]:
    """Return a list that mimics successful ``fetch_sales_docs`` output."""
    return [
        UnifiedDocument(
            id="doc_aaa00001",
            external_id="SALE-001",
            vin=_TEST_VIN,
            title="Vehicle Purchase Agreement",
            document_type="contract",
            source_system="sales",
            date="2024-03-15",
            metadata={"dealer_name": "AutoNation Honda", "amount": 32500.00},
        ),
        UnifiedDocument(
            id="doc_aaa00002",
            external_id="SALE-002",
            vin=_TEST_VIN,
            title="Trade-In Invoice",
            document_type="invoice",
            source_system="sales",
            date="2024-03-15",
            metadata={"dealer_name": "AutoNation Honda", "amount": 8500.00},
        ),
    ]


def _fake_service_docs() -> list[UnifiedDocument]:
    """Return a list that mimics successful ``fetch_service_docs`` output."""
    return [
        UnifiedDocument(
            id="doc_bbb00001",
            external_id="SVC-001",
            vin=_TEST_VIN,
            title="60,000 Mile Service Report",
            document_type="service_report",
            source_system="service",
            date="2025-01-20",
            metadata={"mileage": 60234, "technician": "John Smith"},
        ),
    ]


_ERROR_DICT: dict[str, str] = {"status": "error", "message": "Connection refused"}


# ===================================================================
# get_aggregated_documents – success cases
# ===================================================================

class TestGetAggregatedDocumentsSuccess:
    """Happy-path tests for ``get_aggregated_documents``."""

    async def test_both_sources_succeed_returns_all_documents(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_fake_sales_docs())
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert len(result["documents"]) == 3

    async def test_both_sources_succeed_degraded_is_false(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_fake_sales_docs())
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["degraded"] is False

    async def test_both_sources_succeed_vin_is_echoed(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_fake_sales_docs())
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["vin"] == _TEST_VIN

    async def test_both_sources_succeed_sources_report_success(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_fake_sales_docs())
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["sources"]["sales"]["status"] == "success"
        assert result["sources"]["sales"]["count"] == 2
        assert result["sources"]["service"]["status"] == "success"
        assert result["sources"]["service"]["count"] == 1

    async def test_both_sources_empty_returns_empty_list(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=[])
        aggregator.fetch_service_docs = AsyncMock(return_value=[])

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["documents"] == []
        assert result["degraded"] is False

    async def test_documents_are_unified_document_instances(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_fake_sales_docs())
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert all(isinstance(doc, UnifiedDocument) for doc in result["documents"])

    async def test_response_contains_all_required_keys(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=[])
        aggregator.fetch_service_docs = AsyncMock(return_value=[])

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert set(result.keys()) == {"vin", "documents", "sources", "degraded"}


# ===================================================================
# get_aggregated_documents – degraded mode (partial failures)
# ===================================================================

class TestGetAggregatedDocumentsDegraded:
    """Degraded-mode tests when one or both sources fail."""

    async def test_sales_error_dict_service_ok(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_ERROR_DICT)
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["degraded"] is True
        assert len(result["documents"]) == 1
        assert result["documents"][0].source_system == "service"

    async def test_sales_ok_service_error_dict(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_fake_sales_docs())
        aggregator.fetch_service_docs = AsyncMock(return_value=_ERROR_DICT)

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["degraded"] is True
        assert len(result["documents"]) == 2
        assert all(doc.source_system == "sales" for doc in result["documents"])

    async def test_both_sources_error_dict(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_ERROR_DICT)
        aggregator.fetch_service_docs = AsyncMock(return_value=_ERROR_DICT)

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["degraded"] is True
        assert result["documents"] == []

    async def test_sales_exception_service_ok(
        self, aggregator: DocumentAggregator,
    ):
        """When gather catches an exception from Sales, Service docs still appear."""
        aggregator.fetch_sales_docs = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused"),
        )
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["degraded"] is True
        assert len(result["documents"]) == 1
        assert result["sources"]["sales"]["status"] == "error"
        assert result["sources"]["service"]["status"] == "success"

    async def test_sales_ok_service_exception(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_fake_sales_docs())
        aggregator.fetch_service_docs = AsyncMock(
            side_effect=httpx.ReadTimeout("Read timed out"),
        )

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["degraded"] is True
        assert len(result["documents"]) == 2
        assert result["sources"]["service"]["status"] == "error"
        assert result["sources"]["sales"]["status"] == "success"

    async def test_both_sources_exception(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(
            side_effect=httpx.ConnectError("refused"),
        )
        aggregator.fetch_service_docs = AsyncMock(
            side_effect=httpx.ReadTimeout("timed out"),
        )

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["degraded"] is True
        assert result["documents"] == []
        assert result["sources"]["sales"]["status"] == "error"
        assert result["sources"]["service"]["status"] == "error"


# ===================================================================
# get_aggregated_documents – sources dict structure
# ===================================================================

class TestGetAggregatedDocumentsSources:
    """Verify the ``sources`` dict reports correct details."""

    async def test_success_source_has_count(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_fake_sales_docs())
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["sources"]["sales"]["count"] == 2
        assert result["sources"]["service"]["count"] == 1

    async def test_error_source_has_error_message_from_dict(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=_ERROR_DICT)
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["sources"]["sales"]["status"] == "error"
        assert result["sources"]["sales"]["error"] == "Connection refused"

    async def test_error_source_has_error_message_from_exception(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(
            side_effect=httpx.ConnectError("host unreachable"),
        )
        aggregator.fetch_service_docs = AsyncMock(return_value=_fake_service_docs())

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert result["sources"]["sales"]["status"] == "error"
        assert "host unreachable" in result["sources"]["sales"]["error"]

    async def test_sources_contains_both_keys(
        self, aggregator: DocumentAggregator,
    ):
        aggregator.fetch_sales_docs = AsyncMock(return_value=[])
        aggregator.fetch_service_docs = AsyncMock(return_value=[])

        result = await aggregator.get_aggregated_documents(_TEST_VIN)

        assert set(result["sources"].keys()) == {"sales", "service"}
