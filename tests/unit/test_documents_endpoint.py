"""Unit tests for the ``GET /api/v1/documents`` endpoint.

The ``DocumentAggregator.get_aggregated_documents`` method is mocked so these
tests exercise **only** the API layer: routing, VIN validation, response
formatting, HTTP status codes, the ``AggregatedDocumentsResponse`` schema
contract defined in SYSTEM_DESIGN.md §5.2, **and** SearchHistory persistence.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.db import get_db_session
from src.db.base import Base
from src.main import app
from src.models import SearchHistory
from src.schemas.document import UnifiedDocument
from src.services.aggregator import DocumentAggregator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_VIN = "1HGCM82633A004352"
_ENDPOINT = "/api/v1/documents"

# ISO-8601 UTC timestamp pattern  (e.g. "2026-08-13T02:49:08Z")
_ISO8601_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# §5.2 top-level keys that MUST appear in every successful response
_REQUIRED_KEYS = {"vin", "documents", "sources", "degraded", "timestamp", "cache_hit"}


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
        "cache_hit": False,
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
        "cache_hit": False,
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
        "cache_hit": False,
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
        "cache_hit": False,
    }


# ---------------------------------------------------------------------------
# In-memory async DB for tests
# ---------------------------------------------------------------------------

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a test DB session backed by an in-memory SQLite database."""
    async with _test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
async def _setup_test_db():
    """Create tables before each test and drop them after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
def mock_aggregator() -> AsyncMock:
    """Return a mock DocumentAggregator whose method can be configured per test."""
    mock = AsyncMock(spec=DocumentAggregator)
    return mock


@pytest.fixture()
def client(mock_aggregator: AsyncMock) -> TestClient:
    """Synchronous test client with both aggregator and DB session overridden."""
    app.dependency_overrides[DocumentAggregator] = lambda: mock_aggregator
    app.dependency_overrides[get_db_session] = _override_get_db_session
    yield TestClient(app)
    app.dependency_overrides.clear()


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

    def test_vin_exactly_17_passes_validation(
        self, client: TestClient, mock_aggregator: AsyncMock
    ):
        """Exactly 17 characters should pass validation (not 422)."""
        mock_aggregator.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200


# ===================================================================
# Response Structure – §5.2 Contract
# ===================================================================

class TestResponseStructure:
    """Verify the response body matches SYSTEM_DESIGN.md §5.2."""

    @pytest.fixture(autouse=True)
    def _configure_aggregator(self, mock_aggregator: AsyncMock):
        self._mock_agg = mock_aggregator

    # ---- Top-level keys -------------------------------------------

    def test_response_contains_all_required_keys(self, client: TestClient):
        """Response must include vin, documents, sources, degraded, timestamp."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200
        assert _REQUIRED_KEYS == set(r.json().keys())

    def test_response_has_no_extra_keys(self, client: TestClient):
        """No unexpected keys should leak into the response."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert set(r.json().keys()) == _REQUIRED_KEYS

    # ---- VIN echo -------------------------------------------------

    def test_vin_is_echoed_back(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["vin"] == _TEST_VIN

    # ---- Timestamp ------------------------------------------------

    def test_timestamp_is_iso8601_utc(self, client: TestClient):
        """Timestamp must match YYYY-MM-DDTHH:MM:SSZ format."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert _ISO8601_UTC_RE.match(r.json()["timestamp"])

    # ---- Documents list -------------------------------------------

    def test_documents_is_a_list(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert isinstance(r.json()["documents"], list)

    def test_document_objects_have_required_fields(self, client: TestClient):
        """Each document object must have the fields from UnifiedDocument."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        doc_keys = {"id", "vin", "title", "document_type", "source_system",
                     "date", "metadata"}
        for doc in r.json()["documents"]:
            assert doc_keys.issubset(set(doc.keys()))

    # ---- Sources --------------------------------------------------

    def test_sources_contains_sales_and_service(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        sources = r.json()["sources"]
        assert "sales" in sources
        assert "service" in sources

    def test_success_source_has_status_and_count(self, client: TestClient):
        """A successful source must include status='success' and count."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        sales = r.json()["sources"]["sales"]
        assert sales["status"] == "success"
        assert isinstance(sales["count"], int)

    def test_success_source_has_no_error_field(self, client: TestClient):
        """Successful sources should not contain the 'error' key (exclude_none)."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert "error" not in r.json()["sources"]["sales"]

    def test_error_source_has_status_and_error(self, client: TestClient):
        """A failed source must include status='error' and error message."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_sales_error()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        sales = r.json()["sources"]["sales"]
        assert sales["status"] == "error"
        assert isinstance(sales["error"], str)
        assert len(sales["error"]) > 0

    def test_error_source_has_no_count_field(self, client: TestClient):
        """Failed sources should not contain the 'count' key (exclude_none)."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_sales_error()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert "count" not in r.json()["sources"]["sales"]


# ===================================================================
# HTTP Status Code – Always 200
# ===================================================================

class TestHttpStatusCode:
    """Endpoint must always return HTTP 200, regardless of upstream failures."""

    @pytest.fixture(autouse=True)
    def _configure_aggregator(self, mock_aggregator: AsyncMock):
        self._mock_agg = mock_aggregator

    def test_200_when_all_sources_ok(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200

    def test_200_when_one_source_fails(self, client: TestClient):
        """Partial failure → still HTTP 200 with degraded=true."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_sales_error()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200

    def test_200_when_both_sources_fail(self, client: TestClient):
        """Total upstream failure → still HTTP 200 with degraded=true."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_both_error()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200


# ===================================================================
# Degraded Flag
# ===================================================================

class TestDegradedFlag:
    """Verify the ``degraded`` flag correctly reflects upstream health."""

    @pytest.fixture(autouse=True)
    def _configure_aggregator(self, mock_aggregator: AsyncMock):
        self._mock_agg = mock_aggregator

    def test_degraded_false_when_all_ok(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["degraded"] is False

    def test_degraded_true_when_one_source_fails(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_sales_error()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["degraded"] is True

    def test_degraded_true_when_both_sources_fail(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_both_error()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["degraded"] is True


# ===================================================================
# Document Content
# ===================================================================

class TestDocumentContent:
    """Verify the documents list content matches what the aggregator returns."""

    @pytest.fixture(autouse=True)
    def _configure_aggregator(self, mock_aggregator: AsyncMock):
        self._mock_agg = mock_aggregator

    def test_returns_all_documents_from_both_sources(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        docs = r.json()["documents"]
        assert len(docs) == 5  # 2 sales + 3 service

    def test_returns_only_successful_source_docs_on_partial_failure(
        self, client: TestClient
    ):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_sales_error()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        docs = r.json()["documents"]
        assert len(docs) == 3  # only service docs
        assert all(d["source_system"] == "service" for d in docs)

    def test_returns_empty_list_when_both_sources_fail(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_both_error()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.json()["documents"] == []

    def test_returns_empty_list_when_no_documents_found(self, client: TestClient):
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_empty()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        docs = r.json()["documents"]
        assert docs == []
        assert r.json()["degraded"] is False

    def test_document_source_system_preserved(self, client: TestClient):
        """Each document must retain its source_system tag."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        systems = {d["source_system"] for d in r.json()["documents"]}
        assert systems == {"sales", "service"}


# ===================================================================
# Aggregator Invocation
# ===================================================================

class TestAggregatorInvocation:
    """Verify the endpoint calls the aggregator correctly."""

    def test_aggregator_called_with_vin(
        self, client: TestClient, mock_aggregator: AsyncMock
    ):
        """The endpoint must pass the validated VIN to the aggregator."""
        mock_aggregator.get_aggregated_documents.return_value = _aggregator_all_ok()
        client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        mock_aggregator.get_aggregated_documents.assert_called_once_with(_TEST_VIN, force_refresh=False)

    def test_aggregator_called_with_different_vin(
        self, client: TestClient, mock_aggregator: AsyncMock
    ):
        """Confirm VIN is forwarded, not hard-coded."""
        other_vin = "5YJSA1E26MF123456"
        result = _aggregator_all_ok()
        result["vin"] = other_vin
        mock_aggregator.get_aggregated_documents.return_value = result

        r = client.get(_ENDPOINT, params={"vin": other_vin})

        mock_aggregator.get_aggregated_documents.assert_called_once_with(other_vin, force_refresh=False)
        assert r.json()["vin"] == other_vin


# ===================================================================
# SearchHistory Persistence
# ===================================================================

class TestSearchHistoryPersistence:
    """Verify that each successful request creates a SearchHistory record."""

    @pytest.fixture(autouse=True)
    def _configure_aggregator(self, mock_aggregator: AsyncMock):
        self._mock_agg = mock_aggregator

    async def _get_all_history(self) -> list[SearchHistory]:
        """Helper to query all SearchHistory rows from the test DB."""
        async with _test_session_factory() as session:
            result = await session.execute(select(SearchHistory))
            return list(result.scalars().all())

    @pytest.mark.asyncio
    async def test_record_created_on_successful_request(self, client: TestClient):
        """A SearchHistory row must be created after a successful request."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        r = client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        assert r.status_code == 200

        rows = await self._get_all_history()
        assert len(rows) == 1
        assert rows[0].vin == _TEST_VIN

    @pytest.mark.asyncio
    async def test_total_documents_matches_document_count(self, client: TestClient):
        """total_documents must equal the number of documents returned."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        client.get(_ENDPOINT, params={"vin": _TEST_VIN})

        rows = await self._get_all_history()
        assert rows[0].total_documents == 5  # 2 sales + 3 service

    @pytest.mark.asyncio
    async def test_total_documents_zero_when_no_docs(self, client: TestClient):
        """total_documents should be 0 when no documents are returned."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_empty()
        client.get(_ENDPOINT, params={"vin": _TEST_VIN})

        rows = await self._get_all_history()
        assert rows[0].total_documents == 0

    @pytest.mark.asyncio
    async def test_is_degraded_false_when_all_ok(self, client: TestClient):
        """is_degraded must be False when both sources succeed."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        client.get(_ENDPOINT, params={"vin": _TEST_VIN})

        rows = await self._get_all_history()
        assert rows[0].is_degraded is False

    @pytest.mark.asyncio
    async def test_is_degraded_true_when_partial_failure(self, client: TestClient):
        """is_degraded must be True when at least one source fails."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_sales_error()
        client.get(_ENDPOINT, params={"vin": _TEST_VIN})

        rows = await self._get_all_history()
        assert rows[0].is_degraded is True

    @pytest.mark.asyncio
    async def test_is_degraded_true_when_both_fail(self, client: TestClient):
        """is_degraded must be True when all sources fail."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_both_error()
        client.get(_ENDPOINT, params={"vin": _TEST_VIN})

        rows = await self._get_all_history()
        assert rows[0].is_degraded is True

    @pytest.mark.asyncio
    async def test_multiple_requests_create_multiple_records(self, client: TestClient):
        """Each request must create its own SearchHistory row."""
        self._mock_agg.get_aggregated_documents.return_value = _aggregator_all_ok()
        client.get(_ENDPOINT, params={"vin": _TEST_VIN})
        client.get(_ENDPOINT, params={"vin": _TEST_VIN})

        rows = await self._get_all_history()
        assert len(rows) == 2

    @pytest.mark.asyncio
    async def test_no_record_created_on_validation_failure(self, client: TestClient):
        """No SearchHistory row should exist when VIN validation fails (422)."""
        client.get(_ENDPOINT, params={"vin": "SHORT"})

        rows = await self._get_all_history()
        assert len(rows) == 0
