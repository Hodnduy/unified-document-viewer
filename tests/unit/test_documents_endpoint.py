"""Unit tests for the ``GET /api/v1/documents`` endpoint.

The ``DocumentAggregator.get_aggregated_documents`` method is mocked so these
tests exercise **only** the API layer: routing, VIN validation, response
formatting, HTTP status codes, and the ``AggregatedDocumentsResponse`` schema
contract defined in SYSTEM_DESIGN.md §5.2.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.schemas.document import UnifiedDocument

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_VIN = "1HGCM82633A004352"
_ENDPOINT = "/api/v1/documents"

# ISO-8601 UTC timestamp pattern  (e.g. "2026-08-13T02:49:08Z")
_ISO8601_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# §5.2 top-level keys that MUST appear in every successful response
_REQUIRED_KEYS = {"vin", "documents", "sources", "degraded", "timestamp"}


# ---------------------------------------------------------------------------
# Sample aggregator results (what get_aggregated_documents would return)
# ---------------------------------------------------------------------------

def _make_docs(source: str, count: int) -> list[UnifiedDocument]:
    """Create *count* minimal ``UnifiedDocument`` instances for *source*."""
    return [
        UnifiedDocument(
            id=f"doc_{source}_{i}",
            external_id=f"{source.upper()}-{i:03d}",
            vin=_TEST_VIN,
            title=f"Test Document {i}",
            document_type="contract" if source == "sales" else "service_report",
            source_system=source,
            date=date(2024, 3, 15),
            metadata={"key": "value"},
        )
        for i in range(1, count + 1)
    ]


def _aggregator_all_ok() -> dict[str, Any]:
    """Simulates a fully-successful aggregation (both sources OK)."""
    sales_docs = _make_docs("sales", 2)
    service_docs = _make_docs("service", 3)
    return {
        "vin": _TEST_VIN,
        "documents": sales_docs + service_docs,
        "sources": {
            "sales": {"status": "success", "count": 2},
            "service": {"status": "success", "count": 3},
        },
        "degraded": False,
    }


def _aggregator_sales_error() -> dict[str, Any]:
    """Simulates a partial failure: Sales API down, Service API OK."""
    service_docs = _make_docs("service", 3)
    return {
        "vin": _TEST_VIN,
        "documents": service_docs,
        "sources": {
            "sales": {"status": "error", "error": "Connection timeout after 3000ms"},
            "service": {"status": "success", "count": 3},
        },
        "degraded": True,
    }


def _aggregator_both_error() -> dict[str, Any]:
    """Simulates a total failure: both upstream sources down."""
    return {
        "vin": _TEST_VIN,
        "documents": [],
        "sources": {
            "sales": {"status": "error", "error": "Connection refused"},
            "service": {"status": "error", "error": "Read timed out"},
        },
        "degraded": True,
    }


def _aggregator_empty() -> dict[str, Any]:
    """Simulates a success where both sources return zero documents."""
    return {
        "vin": _TEST_VIN,
        "documents": [],
        "sources": {
            "sales": {"status": "success", "count": 0},
            "service": {"status": "success", "count": 0},
        },
        "degraded": False,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client() -> TestClient:
    """Synchronous test client for the FastAPI app."""
    return TestClient(app)


# ===================================================================
# VIN Validation (422 cases)
# ===================================================================

class TestVinValidation:
    """Verify that VIN query-param validation rejects bad input."""

    def test_missing_vin_returns_422(self, client: TestClient):
        """VIN is a required query parameter."""
        r = client.get(_ENDPOINT)
        assert r.status_code == 422

    def test_vin_too_short_returns_422(self, client: TestClient):
        """VIN shorter than 17 characters must be rejected."""
        r = client.get(_ENDPOINT, params={"vin": "A" * 16})
        assert r.status_code == 422

    def test_vin_too_long_returns_422(self, client: TestClient):
        """VIN longer than 17 characters must be rejected."""
        r = client.get(_ENDPOINT, params={"vin": "A" * 18})
        assert r.status_code == 422

    def test_empty_vin_returns_422(self, client: TestClient):
        """An empty string must be rejected."""
        r = client.get(_ENDPOINT, params={"vin": ""})
        assert r.status_code == 422

    def test_vin_exactly_17_passes_validation(self, client: TestClient):
        """Exactly 17 characters should pass validation (not 422)."""
        with patch(
            "src.api.routes.documents.DocumentAggregator"
        ) as MockAgg:
            MockAgg.return_value.get_aggregated_documents = AsyncMock(
                return_value=_aggregator_all_ok()
            )
            r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200


# ===================================================================
# Response Structure – §5.2 Contract
# ===================================================================

class TestResponseStructure:
    """Verify the response body matches SYSTEM_DESIGN.md §5.2."""

    @pytest.fixture(autouse=True)
    def _mock_aggregator(self):
        with patch(
            "src.api.routes.documents.DocumentAggregator"
        ) as MockAgg:
            self._mock_agg = MockAgg.return_value
            yield

    # ---- Top-level keys -------------------------------------------

    def test_response_contains_all_required_keys(self, client: TestClient):
        """Response must include vin, documents, sources, degraded, timestamp."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200
        assert _REQUIRED_KEYS == set(r.json().keys())

    def test_response_has_no_extra_keys(self, client: TestClient):
        """No unexpected keys should leak into the response."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert set(r.json().keys()) == _REQUIRED_KEYS

    # ---- VIN echo -------------------------------------------------

    def test_vin_is_echoed_back(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["vin"] == _TEST_VIN

    # ---- Timestamp ------------------------------------------------

    def test_timestamp_is_iso8601_utc(self, client: TestClient):
        """Timestamp must match YYYY-MM-DDTHH:MM:SSZ format."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert _ISO8601_UTC_RE.match(r.json()["timestamp"])

    # ---- Documents list -------------------------------------------

    def test_documents_is_a_list(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert isinstance(r.json()["documents"], list)

    def test_document_objects_have_required_fields(self, client: TestClient):
        """Each document object must have the fields from UnifiedDocument."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        doc_keys = {"id", "vin", "title", "document_type", "source_system",
                     "date", "metadata"}
        for doc in r.json()["documents"]:
            assert doc_keys.issubset(set(doc.keys()))

    # ---- Sources --------------------------------------------------

    def test_sources_contains_sales_and_service(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        sources = r.json()["sources"]
        assert "sales" in sources
        assert "service" in sources

    def test_success_source_has_status_and_count(self, client: TestClient):
        """A successful source must include status='success' and count."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        sales = r.json()["sources"]["sales"]
        assert sales["status"] == "success"
        assert isinstance(sales["count"], int)

    def test_success_source_has_no_error_field(self, client: TestClient):
        """Successful sources should not contain the 'error' key (exclude_none)."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert "error" not in r.json()["sources"]["sales"]

    def test_error_source_has_status_and_error(self, client: TestClient):
        """A failed source must include status='error' and error message."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_sales_error()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        sales = r.json()["sources"]["sales"]
        assert sales["status"] == "error"
        assert isinstance(sales["error"], str)
        assert len(sales["error"]) > 0

    def test_error_source_has_no_count_field(self, client: TestClient):
        """Failed sources should not contain the 'count' key (exclude_none)."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_sales_error()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert "count" not in r.json()["sources"]["sales"]


# ===================================================================
# HTTP Status Code – Always 200
# ===================================================================

class TestHttpStatusCode:
    """Endpoint must always return HTTP 200, regardless of upstream failures."""

    @pytest.fixture(autouse=True)
    def _mock_aggregator(self):
        with patch(
            "src.api.routes.documents.DocumentAggregator"
        ) as MockAgg:
            self._mock_agg = MockAgg.return_value
            yield

    def test_200_when_all_sources_ok(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200

    def test_200_when_one_source_fails(self, client: TestClient):
        """Partial failure → still HTTP 200 with degraded=true."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_sales_error()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200

    def test_200_when_both_sources_fail(self, client: TestClient):
        """Total upstream failure → still HTTP 200 with degraded=true."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_both_error()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200


# ===================================================================
# Degraded Flag
# ===================================================================

class TestDegradedFlag:
    """Verify the ``degraded`` flag correctly reflects upstream health."""

    @pytest.fixture(autouse=True)
    def _mock_aggregator(self):
        with patch(
            "src.api.routes.documents.DocumentAggregator"
        ) as MockAgg:
            self._mock_agg = MockAgg.return_value
            yield

    def test_degraded_false_when_all_ok(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["degraded"] is False

    def test_degraded_true_when_one_source_fails(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_sales_error()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["degraded"] is True

    def test_degraded_true_when_both_sources_fail(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_both_error()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["degraded"] is True


# ===================================================================
# Document Content
# ===================================================================

class TestDocumentContent:
    """Verify the documents list content matches what the aggregator returns."""

    @pytest.fixture(autouse=True)
    def _mock_aggregator(self):
        with patch(
            "src.api.routes.documents.DocumentAggregator"
        ) as MockAgg:
            self._mock_agg = MockAgg.return_value
            yield

    def test_returns_all_documents_from_both_sources(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        docs = r.json()["documents"]
        assert len(docs) == 5  # 2 sales + 3 service

    def test_returns_only_successful_source_docs_on_partial_failure(
        self, client: TestClient
    ):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_sales_error()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        docs = r.json()["documents"]
        assert len(docs) == 3  # only service docs
        assert all(d["source_system"] == "service" for d in docs)

    def test_returns_empty_list_when_both_sources_fail(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_both_error()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["documents"] == []

    def test_returns_empty_list_when_no_documents_found(self, client: TestClient):
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_empty()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        docs = r.json()["documents"]
        assert docs == []
        assert r.json()["degraded"] is False

    def test_document_source_system_preserved(self, client: TestClient):
        """Each document must retain its source_system tag."""
        self._mock_agg.get_aggregated_documents = AsyncMock(
            return_value=_aggregator_all_ok()
        )
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        systems = {d["source_system"] for d in r.json()["documents"]}
        assert systems == {"sales", "service"}


# ===================================================================
# Aggregator Invocation
# ===================================================================

class TestAggregatorInvocation:
    """Verify the endpoint calls the aggregator correctly."""

    def test_aggregator_called_with_vin(self, client: TestClient):
        """The endpoint must pass the validated VIN to the aggregator."""
        with patch(
            "src.api.routes.documents.DocumentAggregator"
        ) as MockAgg:
            mock_method = AsyncMock(return_value=_aggregator_all_ok())
            MockAgg.return_value.get_aggregated_documents = mock_method

            client.get(_ENDPOINT, params={"vin": _TEST_VIN})

            mock_method.assert_called_once_with(_TEST_VIN)

    def test_aggregator_called_with_different_vin(self, client: TestClient):
        """Confirm VIN is forwarded, not hard-coded."""
        other_vin = "5YJSA1E26MF123456"
        with patch(
            "src.api.routes.documents.DocumentAggregator"
        ) as MockAgg:
            result = _aggregator_all_ok()
            result["vin"] = other_vin
            mock_method = AsyncMock(return_value=result)
            MockAgg.return_value.get_aggregated_documents = mock_method

            r = client.get(_ENDPOINT, params={"vin": other_vin})

            mock_method.assert_called_once_with(other_vin)
            assert r.json()["vin"] == other_vin
