# Unified Document Viewer

> A personal backend project for unified vehicle document aggregation.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture & Design](#-architecture--design)
- [Features & Requirements Coverage](#-features--requirements-coverage)
- [Project Structure](#-project-structure)
- [Quick Start Guide](#-quick-start-guide)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Installation](#2-installation)
  - [3. Running All Servers (One Command)](#3-running-all-servers-one-command)
  - [4. Testing the API](#4-testing-the-api)
- [Running Automated Tests](#-running-automated-tests)

---

## 🔍 Overview

Dealerships typically operate with fragmented systems: a **Sales System** (handling purchase contracts, invoices, financing) and a **Service System** (handling repair orders, inspection reports, maintenance). 

The **Unified Document Viewer** backend service resolves this fragmentation by exposing a single, high-performance RESTful endpoint (`GET /api/v1/documents`). Given a Vehicle Identification Number (VIN), the backend issues **async parallel requests** to all upstream dealership APIs, normalises heterogeneous data into a unified schema, and surfaces results gracefully even during partial upstream outages.

---

## 🏗️ Architecture & Design

The complete architectural plan, data flow diagrams, and technology selection rationale are documented in detail in:

📄 **[docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)**

```
+-----------------------------------------------------------------------+
|                             Client Layer                              |
|                   (cURL / Postman / Swagger UI)                       |
+-----------------------------------------------------------------------+
                                    |
                    GET /api/v1/documents?vin=...
                                    v
+-----------------------------------------------------------------------+
|                    Unified Document Viewer API                        |
|                            (FastAPI)                                  |
|  - Route & Query Parameter Validation (VIN 17-char format)            |
|  - Aggregation Service (httpx AsyncClient, asyncio.gather)            |
|  - Resilient Error Handling (Graceful Degradation Mode)               |
+-----------------------------------------------------------------------+
                       /                         \
           Parallel Async Call               Parallel Async Call
                     /                             \
                    v                               v
+-----------------------+               +-----------------------+
| Mock Sales System API |               |Mock Service System API|
|     (Port 8001)       |               |     (Port 8002)       |
+-----------------------+               +-----------------------+
```

---

## ✨ Features & Requirements Coverage

- **Unified Search:** `GET /api/v1/documents?vin=<VIN>` endpoint with strict 17-character ISO 3779 VIN validation.
- **Parallel Data Aggregation:** Uses Python `asyncio.gather` and non-blocking `httpx.AsyncClient` to fetch from Sales and Service APIs concurrently.
- **Graceful Degradation:** When an upstream source fails or times out (3.0s limit), the API returns available documents, sets `"degraded": true`, and provides detailed per-source error metadata without returning HTTP 500.
- **Unified Document Schema:** Standardised Pydantic model (`UnifiedDocument`) tag each document with its `source_system` (`sales` or `service`).
- **Persistent Database:** SQLite (async via aiosqlite) stores every search in a `search_history` table, with a dedicated `GET /api/v1/history` endpoint to query past searches.
- **Comprehensive Test Suite:** 151 unit tests covering routes, schemas, aggregator resilience, and mock servers.

---

## 📁 Project Structure

```
unified-document-viewer/
├── docs/
│   └── SYSTEM_DESIGN.md          # Comprehensive System Design Document
├── scripts/
│   ├── run_all.sh                # 🚀 One-command launcher for all 3 servers
│   └── test_api.sh               # 🧪 cURL-based API smoke tests
├── src/
│   ├── api/
│   │   └── routes/
│   │       ├── documents.py      # GET /api/v1/documents endpoint
│   │       └── history.py        # GET /api/v1/history endpoint
│   ├── core/
│   │   └── config.py             # Application settings & environment variables
│   ├── db/
│   │   ├── base.py               # SQLAlchemy DeclarativeBase
│   │   └── session.py            # Async engine, session factory & dependency
│   ├── mock_servers/
│   │   ├── sales_api.py          # Standalone Mock Sales API (Port 8001)
│   │   └── service_api.py        # Standalone Mock Service API (Port 8002)
│   ├── models/
│   │   └── search_history.py     # SearchHistory ORM model
│   ├── schemas/
│   │   ├── document.py           # UnifiedDocument & response Pydantic models
│   │   └── history.py            # SearchHistory response Pydantic models
│   ├── services/
│   │   └── aggregator.py         # Parallel document fetching & merging service
│   └── main.py                   # FastAPI main entrypoint
├── tests/
│   └── unit/
│       ├── test_aggregator.py    # Unit tests for aggregation & fault tolerance
│       ├── test_documents_endpoint.py  # Unit tests for REST API layer
│       ├── test_mock_servers.py  # Tests for mock server functionality
│       └── test_schemas_document.py    # Schema validation tests
├── examples.http                 # VS Code REST Client request examples
├── Makefile                      # Command shortcuts for cleanup and management
├── pyproject.toml                # Project metadata & dependencies
└── README.md                     # Project documentation
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites

- **Python 3.12+**
- **uv** (recommended fast package manager) or standard `pip` / `venv`

### 2. Installation

Clone the repository and install dependencies:

```bash
# Using Make (Recommended)
make install

# Or using uv directly
uv sync
```

*(Alternatively using standard venv: `python -m venv .venv && source .venv/bin/activate && pip install -e .[dev]`)*

---

### 3. Running All Servers (One Command)

The easiest way to start the entire stack (Mock Sales API, Mock Service API, and Main API) is with the provided script:

```bash
make run
```
*(Alternatively: `./scripts/run_all.sh`)*

This starts all three servers in the background. Press **Ctrl+C** to stop them all, or run:
```bash
make run-stop
```

<details>
<summary><strong>Manual startup (3 separate terminals)</strong></summary>

**Terminal 1 — Mock Sales API (Port 8001):**
```bash
uv run uvicorn src.mock_servers.sales_api:app --port 8001
```

**Terminal 2 — Mock Service API (Port 8002):**
```bash
uv run uvicorn src.mock_servers.service_api:app --port 8002
```

**Terminal 3 — Main Application (Port 8000):**
```bash
uv run uvicorn src.main:app --port 8000 --reload
```

</details>

---

### 4. Testing the API

#### Option A: Automated Smoke Tests (Recommended)

Run all API scenarios automatically with one command:
```bash
make test-api
```
*(Alternatively: `./scripts/test_api.sh`)*

This tests: root health check, valid VIN, empty VIN results, invalid VIN (422), missing VIN (422), and search history.

#### Option B: Interactive Swagger UI
Open your browser and navigate to:
👉 **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**

#### Option C: VS Code REST Client
Open [`examples.http`](examples.http) in VS Code with the [REST Client extension](https://marketplace.visualstudio.com/items?itemName=humao.rest-client) and click **"Send Request"** above each block.

#### Option D: Using `curl` (Terminal)

**Search documents for a VIN:**
```bash
curl -s "http://127.0.0.1:8000/api/v1/documents?vin=1HGCM82633A004352" | python3 -m json.tool
```

**View search history (proves database persistence):**
```bash
curl -s "http://127.0.0.1:8000/api/v1/history" | python3 -m json.tool
```

**Filter history by VIN:**
```bash
curl -s "http://127.0.0.1:8000/api/v1/history?vin=1HGCM82633A004352" | python3 -m json.tool
```

**Invalid VIN (expect 422):**
```bash
curl -s "http://127.0.0.1:8000/api/v1/documents?vin=ABC" | python3 -m json.tool
```

#### Option E: Simulating Upstream Failure (Graceful Degradation)

To see the system's fault tolerance in action, you can manually stop one of the mock servers (e.g., the Sales API) while the Main API is still running:

```bash
# 1. Kill the Mock Sales API
kill $(cat .pids/mock-sales-api.pid)

# 2. Make the same search request again
curl -s "http://127.0.0.1:8000/api/v1/documents?vin=1HGCM82633A004352" | python3 -m json.tool
```

*Notice that the API still returns HTTP 200 and the Service System documents, but now includes `"degraded": true` and lists the Sales System connection error in the metadata.*

---

## 🧪 Running Automated Tests

Run the full pytest suite (151 unit tests):

```bash
# Run unit tests using Make
make test

# Run unit tests with code coverage report
make test-cov
```

*(Alternatively: `uv run pytest` and `uv run pytest --cov=src --cov-report=term-missing`)*