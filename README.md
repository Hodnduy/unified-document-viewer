# Unified Document Viewer

> **Technical Coding Challenge — Scenario D (The Unified Document Viewer)**  

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture & Design](#-architecture--design)
- [Features & Requirements Coverage](#-features--requirements-coverage)
- [Project Structure](#-project-structure)
- [Quick Start Guide](#-quick-start-guide)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Installation](#2-installation)
  - [3. Running the Mock Upstream Servers](#3-running-the-mock-upstream-servers)
  - [4. Running the Main API Server](#4-running-the-main-api-server)
  - [5. Testing the API](#5-testing-the-api)
- [Running Automated Tests](#-running-automated-tests)
- [🤖 AI Collaboration Narrative](#-ai-collaboration-narrative)
  - [1. High-Level Strategy for Guiding the AI](#1-high-level-strategy-for-guiding-the-ai)
  - [2. Verification & Refinement Process](#2-verification--refinement-process)
  - [3. Code Quality & Ownership](#3-code-quality--ownership)
- [🎥 Video Presentation Guide (5–10 Minutes)](#-video-presentation-guide-510-minutes)

---

## 🔍 Overview

Dealerships typically operate with fragmented systems: a **Sales System** (handling purchase contracts, invoices, financing) and a **Service System** (handling repair orders, inspection reports, maintenance). 

The **Unified Document Viewer** backend service resolves this fragmentation by exposing a single, high-performance RESTful endpoint (`GET /api/v1/documents`). Given a Vehicle Identification Number (VIN), the backend issues **async parallel requests** to all upstream dealership APIs, normalises heterogeneous data into a unified schema, and surfaces results gracefully even during partial upstream outages.

---

## 🏗️ Architecture & Design

The complete architectural plan, data flow diagrams, technology selection rationale, observability strategy, and GenAI design phase logs are documented in detail in:

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
- **Comprehensive Test Suite:** 159 unit tests covering routes, schemas, aggregator resilience, and mock servers.

---

## 📁 Project Structure

```
unified-document-viewer/
├── docs/
│   └── SYSTEM_DESIGN.md          # Comprehensive System Design Document
├── src/
│   ├── api/
│   │   └── routes/
│   │       ├── documents.py      # GET /api/v1/documents endpoint
│   │       └── health.py         # Health check endpoint
│   ├── core/
│   │   └── config.py             # Application settings & environment variables
│   ├── mock_servers/
│   │   ├── sales_api.py          # Standalone Mock Sales API (Port 8001)
│   │   └── service_api.py        # Standalone Mock Service API (Port 8002)
│   ├── schemas/
│   │   └── document.py           # UnifiedDocument & response Pydantic models
│   ├── services/
│   │   └── aggregator.py         # Parallel document fetching & merging service
│   └── main.py                   # FastAPI main entrypoint
├── tests/
│   └── unit/
│       ├── test_aggregator.py    # Unit tests for aggregation & fault tolerance
│       ├── test_documents_endpoint.py  # Unit tests for REST API layer
│       ├── test_mock_servers.py # Tests for mock server functionality
│       └── test_schemas_document.py    # Schema validation tests
├── Dockerfile                    # Container definition
├── docker-compose.yml            # Multi-container orchestration setup
├── Makefile                      # Command shortcuts for cleanup and management
├── pyproject.toml                # Project metadata & dependencies
└── README.md                     # Documentation & AI Collaboration Narrative
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites

- **Python 3.12+**
- **uv** (recommended fast package manager) or standard `pip` / `venv`

### 2. Installation

Clone the repository and install dependencies:

```bash
# Install dependencies using uv
uv sync
```

*(Alternatively using standard venv: `python -m venv .venv && source .venv/bin/activate && pip install -e .[dev]`)*

---

### 3. Running the Mock Upstream Servers

The aggregator connects to two upstream services. Open two separate terminal windows to launch them:

**Terminal 1 — Mock Sales API (Port 8001):**
```bash
uv run uvicorn src.mock_servers.sales_api:app --port 8001
```

**Terminal 2 — Mock Service API (Port 8002):**
```bash
uv run uvicorn src.mock_servers.service_api:app --port 8002
```

---

### 4. Running the Main API Server

**Terminal 3 — Main Application (Port 8000):**
```bash
uv run uvicorn src.main:app --port 8000 --reload
```

---

### 5. Testing the API

#### Option A: Interactive Swagger UI
Open your browser and navigate to:
👉 **[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)**

#### Option B: Using `curl` (Terminal)

Test with valid VIN containing sample data (`1HGCM82633A004352`):
```bash
curl -X GET "http://127.0.0.1:8000/api/v1/documents?vin=1HGCM82633A004352" -H "accept: application/json"
```

**Example Successful Response:**
```json
{
  "vin": "1HGCM82633A004352",
  "documents": [
    {
      "id": "doc_a1b2c3d4",
      "external_id": "SALE-001",
      "vin": "1HGCM82633A004352",
      "title": "Vehicle Purchase Agreement",
      "document_type": "contract",
      "source_system": "sales",
      "date": "2024-03-15",
      "metadata": {
        "dealer_name": "AutoNation Honda",
        "amount": 32500.0
      }
    },
    {
      "id": "doc_e5f6g7h8",
      "external_id": "SRV-101",
      "vin": "1HGCM82633A004352",
      "title": "10,000 Mile Scheduled Maintenance",
      "document_type": "maintenance",
      "source_system": "service",
      "date": "2024-09-20",
      "metadata": {
        "service_center": "Honda Service Center East",
        "cost": 185.50
      }
    }
  ],
  "sources": {
    "sales": { "status": "success", "count": 2 },
    "service": { "status": "success", "count": 2 }
  },
  "degraded": false,
  "timestamp": "2026-08-13T10:30:00Z"
}
```

---

## 🧪 Running Automated Tests

Run the full pytest suite (159 unit tests):

```bash
# Run unit tests
uv run pytest

# Run unit tests with code coverage report
uv run pytest --cov=src --cov-report=term-missing
```

---

## 🤖 AI Collaboration Narrative

> *This section documents how Artificial Intelligence (Google Antigravity AI agent) was leveraged as an essential engineering partner throughout the lifecycle of this project.*

### 1. High-Level Strategy for Guiding the AI

Rather than treating AI as a simple autocomplete tool, I operated as an **Engineering Manager & Lead Architect**, directing the AI agent via clear architectural constraints, test-driven expectations, and iterative code reviews:

1. **System Design First:** Directing the AI to draft a comprehensive `SYSTEM_DESIGN.md` before writing production code. This established clear boundaries (e.g., ISO 3779 VIN validation, asynchronous parallel requests, resiliency contracts).
2. **Modular Responsibility:** Enforcing separation of concerns — isolating Pydantic schemas, application settings, FastAPI routes, and upstream mock services into decoupled modules.
3. **Test-Driven Verification:** Instructing the AI to generate robust unit tests for edge cases (e.g., invalid VIN length, upstream connection timeouts, partial source failures).

### 2. Verification & Refinement Process

To maintain complete ownership and ensure software quality, every AI-generated component was subjected to rigorous validation:

- **Data Resiliency & Contract Checks:** I verified that upstream timeouts (3.0s limit) or connection failures returned HTTP 200 with `"degraded": true` rather than bubbling up unhandled exceptions or returning HTTP 500.
- **Pydantic V2 Migration & Deprecations:** During testing, deprecation warnings regarding Pydantic V1 class-based configs were identified and refined into clean Pydantic V2 `model_config` patterns.
- **Edge Case Validation:** Tested boundaries such as non-existent VINs (empty list response with `"degraded": false`) and malformed VIN strings (HTTP 422 Unprocessable Entity).

### 3. Code Quality & Ownership

- **Zero Dummy Fallbacks:** Guaranteed that failure modes explicitly report upstream errors in `sources` status metadata rather than masking issues with silent fallbacks.
- **Complete Type Annotations:** All functions and API routes include full Python type annotations (`__future__.annotations`, `Annotated`, `Pydantic models`).
- **100% Passing Test Suite:** Validated 159 unit tests covering all components before finalizing commits.

---

## 🎥 Video Presentation Guide (5–10 Minutes)

When recording your video submission, follow this structured agenda:

| Time | Agenda Item | Key Talking Points |
| :--- | :--- | :--- |
| **0:00 – 1:00** | **Introduction & Scenario** | Introduce yourself, state scenario: **Scenario D — The Unified Document Viewer (Backend Service)**. |
| **1:00 – 3:00** | **System Architecture** | Walk through [`SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md). Explain parallel fetching (`asyncio.gather`), FastAPI, and graceful degradation when upstream sources fail. |
| **3:00 – 5:00** | **Live API Demonstration** | Show terminal running mock servers (ports 8001 & 8002) and main server (port 8000). Execute cURL or Swagger UI calls for valid VIN, invalid VIN, and degraded state (kill one mock server to demonstrate `"degraded": true`). |
| **5:00 – 7:00** | **AI Collaboration Story** | Describe how you guided the AI (System Design first, TDD, Resiliency checks). Highlight how you verified AI output and fixed deprecation/schema issues. |
| **7:00 – 9:00** | **Code & Test Suite Walkthrough** | Show project structure, `DocumentAggregator` code, and run `uv run pytest` demonstrating all 159 passing unit tests. |
| **9:00 – 10:00** | **Conclusion & Lessons Learned** | Summarize key takeaways: building resilient microservices, prompt engineering, and maintaining ownership of AI-assisted code. |
