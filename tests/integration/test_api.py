"""Integration tests for GET /api/v1/documents.

Uses an in-memory SQLite database (via ``sqlite+aiosqlite:///:memory:``) to
replace the production DB dependency, and ``respx`` to mock the upstream
Sales API and Service API responses.

Each test exercises the *full* request path through FastAPI → aggregator →
(mocked) external APIs → database persistence, asserting on:

1. HTTP status 200
2. Correct document list in the JSON response
3. ``SearchHistory`` records persisted to the in-memory SQLite store
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from src.db.base import Base
from src.db.session import get_db_session
from src.main import app
from src.models.search_history import SearchHistory

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VIN = "1HGCM82633A004352"  # 17 chars – valid VIN format

_SALES_BASE_URL = "http://localhost:8001"
_SERVICE_BASE_URL = "http://localhost:8002"

# ---------------------------------------------------------------------------
# Sample payloads from upstream APIs
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
            "date": "2024-02-20",
            "metadata": {"mileage": 60_000, "service_center": "Honda Care Plus"},
        },
    ]
}


# ---------------------------------------------------------------------------
# Fixtures – in-memory SQLite DB
# ---------------------------------------------------------------------------

@pytest.fixture()
async def test_engine():
    """Create an in-memory async SQLite engine scoped to a single test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    # Create all tables that inherit from Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    # Teardown – drop tables & dispose the engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture()
async def test_session_factory(test_engine):
    """Return an ``async_sessionmaker`` bound to the test engine."""
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture()
async def override_db(test_session_factory):
    """Override FastAPI's ``get_db_session`` dependency with a test session.

    The override mimics the production dependency's commit/rollback
    behaviour so that the route's ``db.add()`` / ``db.commit()`` calls
    work correctly.
    """

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_get_db_session
    yield
    app.dependency_overrides.clear()


@pytest.fixture()
async def async_client(override_db) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provide an ``httpx.AsyncClient`` wired to the FastAPI test app."""
    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Helper – query SearchHistory from the test DB
# ---------------------------------------------------------------------------

async def _get_search_history_records(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[SearchHistory]:
    """Return all ``SearchHistory`` rows from the test database."""
    async with session_factory() as session:
        result = await session.execute(select(SearchHistory))
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGetDocumentsEndpoint:
    """Integration tests for ``GET /api/v1/documents``."""

    @respx.mock
    async def test_returns_200_with_documents_from_both_sources(
        self,
        async_client: httpx.AsyncClient,
        test_session_factory,
    ):
        """Both upstream APIs return 200 – response should contain all
        documents merged, ``degraded`` should be ``false``, and a
        ``SearchHistory`` record should be persisted.
        """
        # Arrange – mock Sales API
        respx.get(
            f"{_SALES_BASE_URL}/sales/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json=_SALES_RESPONSE)

        # Arrange – mock Service API
        respx.get(
            f"{_SERVICE_BASE_URL}/service/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json=_SERVICE_RESPONSE)

        # Act
        response = await async_client.get(
            "/api/v1/documents",
            params={"vin": _VIN},
        )

        # Assert – HTTP 200
        assert response.status_code == 200

        body = response.json()

        # Assert – VIN echoed back
        assert body["vin"] == _VIN

        # Assert – documents list is present and has correct count
        documents = body["documents"]
        assert isinstance(documents, list)
        expected_total = len(_SALES_RESPONSE["documents"]) + len(
            _SERVICE_RESPONSE["documents"]
        )
        assert len(documents) == expected_total

        # Assert – source systems are represented
        source_systems = {doc["source_system"] for doc in documents}
        assert source_systems == {"sales", "service"}

        # Assert – not degraded
        assert body["degraded"] is False

        # Assert – sources metadata
        assert body["sources"]["sales"]["status"] == "success"
        assert body["sources"]["service"]["status"] == "success"

        # Assert – record persisted in SQLite
        records = await _get_search_history_records(test_session_factory)
        assert len(records) == 1
        record = records[0]
        assert record.vin == _VIN
        assert record.total_documents == expected_total
        assert record.is_degraded is False

    @respx.mock
    async def test_documents_contain_expected_fields(
        self,
        async_client: httpx.AsyncClient,
        test_session_factory,
    ):
        """Each document in the response should carry all required fields
        defined by the ``UnifiedDocument`` schema.
        """
        respx.get(
            f"{_SALES_BASE_URL}/sales/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json=_SALES_RESPONSE)

        respx.get(
            f"{_SERVICE_BASE_URL}/service/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json=_SERVICE_RESPONSE)

        response = await async_client.get(
            "/api/v1/documents",
            params={"vin": _VIN},
        )

        assert response.status_code == 200
        body = response.json()

        required_fields = {
            "id",
            "external_id",
            "vin",
            "title",
            "document_type",
            "source_system",
            "date",
            "metadata",
        }
        for doc in body["documents"]:
            assert required_fields.issubset(doc.keys()), (
                f"Missing fields: {required_fields - doc.keys()}"
            )

    @respx.mock
    async def test_degraded_when_sales_api_fails(
        self,
        async_client: httpx.AsyncClient,
        test_session_factory,
    ):
        """When the Sales API returns a server error, the response should
        still be 200 but ``degraded`` should be ``true`` and only Service
        documents should appear.
        """
        # Sales API fails
        respx.get(
            f"{_SALES_BASE_URL}/sales/documents",
            params={"vin": _VIN},
        ).respond(status_code=500)

        # Service API succeeds
        respx.get(
            f"{_SERVICE_BASE_URL}/service/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json=_SERVICE_RESPONSE)

        response = await async_client.get(
            "/api/v1/documents",
            params={"vin": _VIN},
        )

        assert response.status_code == 200
        body = response.json()

        assert body["degraded"] is True
        assert body["sources"]["sales"]["status"] == "error"
        assert body["sources"]["service"]["status"] == "success"

        # Only service documents should be present
        assert len(body["documents"]) == len(_SERVICE_RESPONSE["documents"])
        assert all(
            doc["source_system"] == "service" for doc in body["documents"]
        )

        # SearchHistory should still be persisted
        records = await _get_search_history_records(test_session_factory)
        assert len(records) == 1
        assert records[0].is_degraded is True

    @respx.mock
    async def test_degraded_when_service_api_fails(
        self,
        async_client: httpx.AsyncClient,
        test_session_factory,
    ):
        """When the Service API returns a server error, the response should
        still be 200 but ``degraded`` should be ``true`` and only Sales
        documents should appear.
        """
        # Sales API succeeds
        respx.get(
            f"{_SALES_BASE_URL}/sales/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json=_SALES_RESPONSE)

        # Service API fails
        respx.get(
            f"{_SERVICE_BASE_URL}/service/documents",
            params={"vin": _VIN},
        ).respond(status_code=500)

        response = await async_client.get(
            "/api/v1/documents",
            params={"vin": _VIN},
        )

        assert response.status_code == 200
        body = response.json()

        assert body["degraded"] is True
        assert body["sources"]["sales"]["status"] == "success"
        assert body["sources"]["service"]["status"] == "error"

        assert len(body["documents"]) == len(_SALES_RESPONSE["documents"])
        assert all(
            doc["source_system"] == "sales" for doc in body["documents"]
        )

        records = await _get_search_history_records(test_session_factory)
        assert len(records) == 1
        assert records[0].is_degraded is True

    @respx.mock
    async def test_multiple_requests_create_multiple_search_records(
        self,
        async_client: httpx.AsyncClient,
        test_session_factory,
    ):
        """Each request to the endpoint should create a new
        ``SearchHistory`` row in the database.
        """
        respx.get(
            f"{_SALES_BASE_URL}/sales/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json=_SALES_RESPONSE)

        respx.get(
            f"{_SERVICE_BASE_URL}/service/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json=_SERVICE_RESPONSE)

        # Fire two requests
        resp1 = await async_client.get(
            "/api/v1/documents", params={"vin": _VIN}
        )
        resp2 = await async_client.get(
            "/api/v1/documents", params={"vin": _VIN}
        )

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        records = await _get_search_history_records(test_session_factory)
        assert len(records) == 2
        assert all(r.vin == _VIN for r in records)

    @respx.mock
    async def test_empty_documents_when_both_apis_return_empty(
        self,
        async_client: httpx.AsyncClient,
        test_session_factory,
    ):
        """When both APIs return empty document lists, the response should
        have an empty ``documents`` array and ``total_documents`` should be 0.
        """
        respx.get(
            f"{_SALES_BASE_URL}/sales/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json={"documents": []})

        respx.get(
            f"{_SERVICE_BASE_URL}/service/documents",
            params={"vin": _VIN},
        ).respond(status_code=200, json={"documents": []})

        response = await async_client.get(
            "/api/v1/documents", params={"vin": _VIN}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["documents"] == []
        assert body["degraded"] is False

        records = await _get_search_history_records(test_session_factory)
        assert len(records) == 1
        assert records[0].total_documents == 0
