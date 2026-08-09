# System Design Document – Unified Document Viewer

> **Scenario D** | Backend Implementation (Python)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Component Description](#3-component-description)
4. [Data Flow](#4-data-flow)
5. [API Design](#5-api-design)
6. [External API Contracts](#6-external-api-contracts)
7. [Data Model](#7-data-model)
8. [Technology Stack & Justifications](#8-technology-stack--justifications)
9. [Scalability, Performance & Reliability](#9-scalability-performance--reliability)
10. [Observability Strategy](#10-observability-strategy)
11. [Assumptions](#11-assumptions)
12. [Scenario D Requirements Coverage](#12-scenario-d-requirements-coverage)
13. [Google Antigravity Collaboration in Design Phase](#13-genai-collaboration-in-design-phase)

---

## 1. Overview

### 1.1 Problem Statement

Dealerships use multiple disconnected systems to manage vehicle-related documents — a **Sales System** for purchase contracts, invoices, and financing agreements, and a **Service System** for repair orders, inspection reports, and maintenance records. Users currently must search each system individually, creating a fragmented and time-consuming experience.

### 1.2 Proposed Solution

Build a **Unified Document Viewer** backend service that provides a single REST API endpoint. Given a Vehicle Identification Number (VIN), the service queries both dealership systems **in parallel**, aggregates the results, and returns a consolidated list of documents — each clearly tagged with its source system.

### 1.3 Scope

- **In scope:** Backend REST API, data aggregation, persistent storage, caching, mock external APIs, testing, observability.
- **Out of scope:** Frontend UI (mocked/stubbed via cURL examples and OpenAPI spec), authentication/authorization (documented as future work), real dealership system integrations.

---

## 2. Architecture Diagram

### 2.1 High-Level Architecture

```mermaid
graph TB
    Client["🖥️ Client<br/>(cURL / Postman / Frontend)"]

    subgraph Backend["Backend Service (FastAPI)"]
        API["API Layer<br/>REST Endpoints"]
        AGG["Aggregation Service<br/>Parallel Fetching & Merging"]
        CACHE["Cache Layer<br/>In-memory LRU (MVP)<br/>Redis-ready (Production)"]
        DB["Persistence Layer<br/>SQLAlchemy ORM"]
    end

    subgraph External["External Systems (Mocked)"]
        SALES["Sales System API<br/>Contracts, Invoices,<br/>Financing Docs"]
        SERVICE["Service System API<br/>Repair Orders,<br/>Inspection Reports"]
    end

    subgraph Storage["Persistent Storage"]
        PG["PostgreSQL<br/>Document Metadata<br/>& Search Audit"]
    end

    subgraph Observability["Observability"]
        LOG["Structured Logging<br/>(structlog)"]
        METRICS["Metrics<br/>(basic counters/histograms)"]
        TRACE["Tracing<br/>(OpenTelemetry – optional MVP)"]
    end

    Client -->|"HTTP Request<br/>GET /api/v1/documents?vin=..."| API
    API --> CACHE
    CACHE -->|"cache miss"| AGG
    AGG -->|"async parallel"| SALES
    AGG -->|"async parallel"| SERVICE
    AGG --> DB
    DB --> PG
    API -->|"JSON Response"| Client

    Backend -.-> LOG
    Backend -.-> METRICS
    Backend -.-> TRACE

    style Backend fill:#1a1a2e,stroke:#16213e,color:#e0e0e0
    style External fill:#0f3460,stroke:#16213e,color:#e0e0e0
    style Storage fill:#533483,stroke:#16213e,color:#e0e0e0
    style Observability fill:#1b4332,stroke:#16213e,color:#e0e0e0
```

> **Key principle:** Cache is an optimization layer (in-memory LRU for MVP, Redis-ready for production). PostgreSQL is the persistent storage for document metadata and search audit history. They serve different purposes and are not interchangeable.

### 2.2 Sequence Diagram – Document Search Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as API Layer
    participant CACHE as Cache Layer
    participant AGG as Aggregation Service
    participant DB as PostgreSQL
    participant SALES as Sales System API
    participant SVC as Service System API

    C->>API: GET /api/v1/documents?vin=1HGCM82633A004352
    API->>API: Validate VIN format

    API->>CACHE: Check cache for VIN
    alt Cache Hit (not expired)
        CACHE->>API: Return cached documents
        API->>C: 200 OK (cached results)
    else Cache Miss
        API->>AGG: Fetch documents for VIN

        par Parallel Requests
            AGG->>SALES: GET /sales/documents?vin=...
            AGG->>SVC: GET /service/documents?vin=...
        end

        SALES-->>AGG: Sales documents[]
        SVC-->>AGG: Service documents[]

        AGG->>AGG: Normalize & tag with source_system
        AGG->>AGG: Merge into unified document list

        AGG->>CACHE: Store aggregated result (TTL)
        AGG->>DB: Persist document metadata & search record

        AGG->>API: Return unified document list
        API->>C: 200 OK (aggregated results)
    end
```

### 2.3 Error Handling Flow (Partial Failure)

```mermaid
sequenceDiagram
    participant C as Client
    participant API as API Layer
    participant AGG as Aggregation Service
    participant SALES as Sales System API
    participant SVC as Service System API

    C->>API: GET /api/v1/documents?vin=...
    API->>AGG: Fetch documents

    par Parallel Requests
        AGG->>SALES: GET /sales/documents?vin=...
        AGG->>SVC: GET /service/documents?vin=...
    end

    SALES-->>AGG: ⚠️ Timeout / 500 Error
    SVC-->>AGG: ✅ Service documents[]

    Note over AGG: Graceful degradation:<br/>Return available data +<br/>error metadata for failed source<br/>Set degraded = true

    AGG->>API: Partial result + source status
    API->>C: 200 OK (degraded: true)
```

> **Why HTTP 200 (not 206)?** The client requested a unified document view and the server successfully processed that request. One upstream dependency being unavailable is reflected in the response body via `"degraded": true` and per-source status metadata. HTTP 206 Partial Content is semantically intended for range requests (RFC 7233) and should not be repurposed for upstream partial failures.

---

## 3. Component Description

### 3.1 API Layer

| Aspect           | Detail                                                                 |
|------------------|------------------------------------------------------------------------|
| Role             | Entry point for all client requests                                    |
| Responsibilities | Request validation, routing, response serialization, error handling    |
| Technology       | FastAPI with Pydantic models                                           |

### 3.2 Aggregation Service

| Aspect           | Detail                                                                              |
|------------------|-------------------------------------------------------------------------------------|
| Role             | Core business logic – orchestrates parallel data fetching and merging               |
| Responsibilities | Parallel HTTP calls, response normalization, source tagging, timeout management     |
| Technology       | Python asyncio + httpx (async HTTP client)                                          |

### 3.3 Cache Layer

| Aspect           | Detail                                                                                  |
|------------------|-----------------------------------------------------------------------------------------|
| Role             | Performance optimization – reduces redundant calls to external APIs                     |
| Responsibilities | TTL-based caching of aggregated query results, cache-aside pattern                      |
| MVP              | In-memory LRU cache (e.g., `functools.lru_cache` or `cachetools.TTLCache`)              |
| Production       | Redis-backed cache behind the same interface (swap without code changes)                |
| Not responsible for | Persistent storage – that is PostgreSQL's role                                      |

### 3.4 Persistence Layer (Database)

| Aspect           | Detail                                                                              |
|------------------|-------------------------------------------------------------------------------------|
| Role             | Persistent storage for document metadata and search audit history                   |
| Responsibilities | CRUD operations, query optimization, migration management                           |
| Technology       | PostgreSQL + SQLAlchemy 2.0 (async) + Alembic                                       |
| Not responsible for | Query result caching – that is the Cache Layer's role                            |

### 3.5 Mock External APIs

| Aspect           | Detail                                                                 |
|------------------|------------------------------------------------------------------------|
| Role             | Simulate real dealership systems for development and testing           |
| Responsibilities | Serve realistic mock data, simulate latency and errors                 |
| Technology       | Separate FastAPI app or in-process fixtures                            |

---

## 4. Data Flow

### 4.1 Happy Path

```
1. Client sends GET /api/v1/documents?vin=<VIN>
2. API Layer validates VIN format (17 alphanumeric chars, ISO 3779)
3. Cache Layer checks for existing, non-expired results
4. On cache miss → Aggregation Service triggers parallel requests:
   a. Sales System API → returns sales documents
   b. Service System API → returns service documents
5. Aggregation Service normalizes both responses into a unified schema
6. Each document is tagged with source_system ("sales" | "service")
7. Result is stored in cache (TTL-based, in-memory)
8. Document metadata and search record are persisted to PostgreSQL
9. Unified document list returned to client (HTTP 200)
```

### 4.2 Partial Failure Path

```
1. Steps 1-4 same as above
2. One external API fails (timeout, 5xx, network error)
3. Aggregation Service collects available results from the successful source
4. Response includes:
   - Documents from the successful source
   - Per-source status metadata (success/error details)
   - "degraded": true flag
5. HTTP 200 returned to client with degraded status
   (the request itself was processed successfully; upstream
    unavailability is conveyed via response body metadata)
```

---

## 5. API Design

### 5.1 Endpoints

| Method | Endpoint                     | Description                       |
|--------|------------------------------|-----------------------------------|
| GET    | `/api/v1/documents`          | Search documents by VIN           |
| GET    | `/api/v1/documents/{doc_id}` | Get a specific document by ID     |
| GET    | `/api/v1/health`             | Health check                      |
| GET    | `/api/v1/health/ready`       | Readiness check (DB + externals)  |

### 5.2 Search Endpoint – Request/Response

**Request:**
```
GET /api/v1/documents?vin=1HGCM82633A004352&page=1&page_size=20
```

**Response (200 OK – all sources successful):**
```json
{
  "vin": "1HGCM82633A004352",
  "total_count": 5,
  "documents": [
    {
      "id": "doc_a1b2c3",
      "title": "Vehicle Purchase Agreement",
      "document_type": "contract",
      "source_system": "sales",
      "date": "2024-03-15",
      "metadata": {
        "dealer_name": "AutoNation Honda",
        "amount": 32500.00
      }
    },
    {
      "id": "doc_d4e5f6",
      "title": "60,000 Mile Service Report",
      "document_type": "service_report",
      "source_system": "service",
      "date": "2025-01-20",
      "metadata": {
        "mileage": 60234,
        "technician": "John Smith"
      }
    }
  ],
  "sources": {
    "sales": {"status": "success", "count": 2, "response_time_ms": 120},
    "service": {"status": "success", "count": 3, "response_time_ms": 85}
  },
  "degraded": false,
  "cached": false,
  "timestamp": "2026-08-08T15:21:00Z"
}
```

**Response (200 OK – partial failure, degraded):**
```json
{
  "vin": "1HGCM82633A004352",
  "total_count": 3,
  "documents": ["..."],
  "sources": {
    "sales": {"status": "error", "error": "Connection timeout after 5000ms"},
    "service": {"status": "success", "count": 3, "response_time_ms": 85}
  },
  "degraded": true,
  "cached": false,
  "timestamp": "2026-08-08T15:21:00Z"
}
```

---

## 6. External API Contracts

The Aggregation Service communicates with two mocked external APIs. Each returns documents for a given VIN.

### 6.1 Sales System API

```
GET /sales/documents?vin={vin}
```

**Response:**
```json
{
  "documents": [
    {
      "id": "SALE-001",
      "title": "Vehicle Purchase Agreement",
      "type": "contract",
      "date": "2024-03-15",
      "metadata": {
        "dealer_name": "AutoNation Honda",
        "amount": 32500.00
      }
    }
  ]
}
```

### 6.2 Service System API

```
GET /service/documents?vin={vin}
```

**Response:**
```json
{
  "documents": [
    {
      "id": "SVC-001",
      "title": "60,000 Mile Service Report",
      "type": "service_report",
      "date": "2025-01-20",
      "metadata": {
        "mileage": 60234,
        "technician": "John Smith"
      }
    }
  ]
}
```

### 6.3 Aggregation Process

The Aggregation Service handles these responses as follows:

1. Calls both APIs concurrently via `asyncio.gather()`
2. Validates and normalizes each response into a common `UnifiedDocument` schema
3. Maps `type` → `document_type` and adds `source_system = "sales"` or `"service"`
4. Assigns an internal `id` (UUID) while preserving the original `id` as `external_id`
5. Merges both lists into a single sorted result

---

## 7. Data Model

### 7.1 Entity Relationship Diagram

```mermaid
erDiagram
    SEARCH_QUERY {
        uuid id PK
        string vin
        timestamp searched_at
        int total_results
        boolean is_cached
        boolean is_degraded
        int response_time_ms
    }

    DOCUMENT {
        uuid id PK
        string external_id
        string vin
        string title
        string document_type
        string source_system
        date document_date
        json metadata
        timestamp fetched_at
    }

    SEARCH_RESULT {
        uuid id PK
        uuid search_query_id FK
        uuid document_id FK
    }

    SOURCE_STATUS {
        uuid id PK
        uuid search_query_id FK
        string source_name
        string status
        string error_message
        int response_time_ms
    }

    SEARCH_QUERY ||--o{ SEARCH_RESULT : "produces"
    DOCUMENT ||--o{ SEARCH_RESULT : "appears in"
    SEARCH_QUERY ||--o{ SOURCE_STATUS : "has"
```

### 7.2 Document Uniqueness

Documents are uniquely identified by the combination of their source system and external ID:

```
UNIQUE(source_system, external_id)
```

Different upstream systems may independently use the same external document ID (e.g., both Sales and Service could have a document with `id = "DOC-001"`). Therefore, `external_id` alone is **not** globally unique — the `source_system` qualifier is required to disambiguate.

### 7.3 Relationship: Search ↔ Document

A `SEARCH_RESULT` association table links searches to documents. This reflects the reality that:

- A single document may appear in **multiple** search queries (e.g., the same VIN searched at different times)
- A single search query returns **multiple** documents

This avoids implying that a document is "owned" by a single search.

### 7.4 Document Types

| Source System | Document Types                                             |
|---------------|-----------------------------------------------------------|
| Sales         | `contract`, `invoice`, `financing_agreement`, `warranty`   |
| Service       | `repair_order`, `inspection_report`, `maintenance_record`  |

---

## 8. Technology Stack & Justifications

| Layer            | Technology              | Justification                                                                                   |
|------------------|-------------------------|-------------------------------------------------------------------------------------------------|
| Language         | Python 3.12+            | Strong async ecosystem, rich library support, team familiarity                                  |
| Web Framework    | FastAPI                 | Native async, auto OpenAPI docs, Pydantic validation, high performance (ASGI)                   |
| Async HTTP       | httpx                   | Async-native HTTP client, connection pooling, timeout management, `asyncio.gather` compatible   |
| ORM              | SQLAlchemy 2.0 (async)  | Industry standard, async support, declarative models, Alembic migrations                        |
| Database         | PostgreSQL              | ACID compliance, JSON support, production-ready, scalable                                       |
| Migrations       | Alembic                 | De-facto standard for SQLAlchemy, version-controlled schema changes                             |
| Validation       | Pydantic v2             | Fast validation, serialization, auto-generated JSON Schema                                      |
| Caching (MVP)    | In-memory LRU           | Zero-dependency, sufficient for single-instance MVP                                             |
| Caching (Prod)   | Redis                   | Distributed cache for multi-instance deployments (same interface, swap at config level)         |
| Testing          | pytest + pytest-asyncio | Async test support, fixtures, rich plugin ecosystem                                             |
| Logging          | structlog               | Structured JSON logging, context binding, processor pipeline                                    |
| Tracing          | OpenTelemetry           | Vendor-neutral distributed tracing, W3C Trace Context standard                                  |
| Containerization | Docker + docker-compose | Reproducible environments, easy local development, CI/CD ready                                  |

---

## 9. Scalability, Performance & Reliability

### 9.1 Scalability

- **Horizontal scaling:** Stateless API design allows multiple instances behind a load balancer
- **Database connection pooling:** SQLAlchemy async pool with configurable pool size
- **Cache evolution:** In-memory LRU for MVP → Redis for distributed caching when scaling to multiple instances

### 9.2 Performance

- **Parallel requests:** `asyncio.gather()` for concurrent calls to Sales & Service APIs
- **Connection reuse:** httpx connection pooling to reduce TCP handshake overhead
- **Response caching:** TTL-based in-memory cache reduces repeated external API calls
- **Pagination:** Limit response payload size for large document sets

### 9.3 Reliability

**MVP (implemented):**

- **Timeouts:** Configurable per-source timeouts (default: 5s)
- **Retry with backoff:** Limited retries for **transient failures only** — connection errors, timeouts, HTTP 502/503/504. Client errors (400, 401, 403, 404) are **not retried**. Policy: max 2 retries, exponential backoff with jitter.
- **Graceful degradation:** Return available data when one source fails, with `degraded: true` and per-source error metadata (HTTP 200)
- **Connection pooling:** httpx connection pool for efficient resource usage
- **Health checks:** `/health` and `/health/ready` endpoints for orchestration

**Future production improvements:**

- **Circuit breaker:** Prevent cascading failures when a source is consistently down (e.g., via `tenacity` or a lightweight state machine)
- **Bulkhead isolation:** Separate connection pools per external source

---

## 10. Observability Strategy

### 10.1 Overview Diagram

```mermaid
graph LR
    subgraph Application["Application (MVP)"]
        SL["structlog<br/>Structured JSON Logs"]
        PM["Basic Metrics<br/>Counters & Histograms"]
        OT["OpenTelemetry<br/>Instrumentation (optional)"]
    end

    subgraph MVP_Outputs["MVP Outputs"]
        STDOUT["stdout / stderr<br/>(JSON logs)"]
        METRICS_LOG["Metrics via logs<br/>or /metrics endpoint"]
    end

    subgraph Prod_Outputs["Production Evolution"]
        PROM["Prometheus<br/>Scrape Endpoint"]
        JAEGER["Jaeger / OTLP<br/>Collector"]
    end

    SL --> STDOUT
    PM --> METRICS_LOG
    PM -.->|"production"| PROM
    OT -.->|"production"| JAEGER

    style Application fill:#1a1a2e,stroke:#16213e,color:#e0e0e0
    style MVP_Outputs fill:#0f3460,stroke:#16213e,color:#e0e0e0
    style Prod_Outputs fill:#533483,stroke:#16213e,color:#e0e0e0
```

### 10.2 MVP vs Production

| Capability         | MVP                                          | Production Evolution                  |
|--------------------|----------------------------------------------|---------------------------------------|
| Logging            | Structured JSON logs to stdout (structlog)   | Log aggregation (ELK/Loki)           |
| Metrics            | Basic counters/histograms in application     | Prometheus scrape endpoint            |
| Tracing            | Optional OpenTelemetry instrumentation       | OTLP Collector → Jaeger              |

### 10.3 Logging

- **Format:** Structured JSON logs via `structlog`
- **Context:** Every log entry includes `request_id`, `vin`, `source_system`, `duration_ms`
- **Levels:** DEBUG (dev), INFO (prod requests), WARNING (degraded), ERROR (failures)

### 10.4 Metrics

| Metric                              | Type      | Description                             |
|--------------------------------------|-----------|-----------------------------------------|
| `http_requests_total`               | Counter   | Total API requests by endpoint & status |
| `http_request_duration_seconds`     | Histogram | Request latency distribution            |
| `external_api_requests_total`       | Counter   | Calls to each external source           |
| `external_api_duration_seconds`     | Histogram | External API latency by source          |
| `cache_hits_total` / `cache_misses` | Counter   | Cache effectiveness                     |
| `documents_returned_total`          | Counter   | Documents aggregated per request        |

### 10.5 Tracing

- **Trace propagation:** W3C Trace Context headers
- **Spans:** API request → Aggregation → Sales API call / Service API call → DB write
- **Attributes:** `vin`, `source_system`, `document_count`, `cache_hit`

---

## 11. Assumptions

| # | Assumption                                                                                           |
|---|------------------------------------------------------------------------------------------------------|
| 1 | VIN follows the ISO 3779 standard (17 alphanumeric characters, excluding I, O, Q)                   |
| 2 | External APIs are RESTful and return JSON                                                            |
| 3 | Document metadata is sufficient (no binary file content is transferred)                               |
| 4 | Cache TTL of 5 minutes is acceptable for document freshness                                          |
| 5 | The system should return partial results rather than failing entirely when one source is unavailable  |
| 6 | Authentication/authorization is out of scope but designed as a pluggable middleware                   |
| 7 | The number of documents per VIN is manageable in memory (< 1000 docs per vehicle)                    |
| 8 | Mock APIs simulate realistic latency (50-500ms) and occasional failures                              |
| 9 | Different upstream systems may reuse the same external document ID independently                     |

---

## 12. Scenario D Requirements Coverage

| Requirement                                      | Status | Implementation                                                     |
|--------------------------------------------------|--------|---------------------------------------------------------------------|
| Unified VIN Search                               | ✅     | `GET /api/v1/documents?vin=<VIN>` with VIN validation              |
| Parallel Sales + Service API requests            | ✅     | `asyncio.gather()` with httpx async client                         |
| Aggregated unified document response             | ✅     | Aggregation Service normalizes and merges both sources              |
| Source system identification                     | ✅     | Each document tagged with `source_system` field                    |
| RESTful backend API                              | ✅     | FastAPI with versioned endpoints (`/api/v1/`)                      |
| Persistent database                              | ✅     | PostgreSQL for document metadata and search audit                  |
| Mock external APIs                               | ✅     | Mocked Sales System API and Service System API                     |
| Scalability / Performance / Reliability          | ✅     | Async, caching, parallel requests, graceful degradation, retries   |
| Observability                                    | ✅     | Structured logging, metrics, optional tracing                      |
| GenAI collaboration                              | ✅     | Documented in Section 13                                           |

---

## 13. Google Antigravity Collaboration in Design Phase

### 13.1 How Antigravity Was Used

| Phase                 | AI Usage                                                                                  |
|-----------------------|-------------------------------------------------------------------------------------------|
| Requirements Analysis | Used AI to clarify ambiguous requirements and identify edge cases (partial failures, VIN validation) |
| Architecture Design   | Directed AI to propose architecture patterns for multi-source data aggregation             |
| API Design            | Collaborated with AI to define REST API contracts and response schemas                     |
| Technology Selection  | Asked AI to compare framework options (FastAPI vs Flask vs Django) with trade-off analysis |
| Diagram Creation      | Used AI to generate Mermaid.js diagrams, then refined for accuracy                         |

### 13.2 Verification Process

- **Cross-referenced** AI suggestions with official documentation (FastAPI, SQLAlchemy, httpx)
- **Challenged** AI-proposed patterns by asking for trade-offs and alternatives
- **Validated** data model design against the specific requirements of Scenario D
- **Iterated** on API response format to ensure it clearly indicates source systems and handles partial failures

### 13.3 Key Design Decisions Influenced by AI Collaboration

1. **Graceful degradation with `degraded` flag** — AI initially suggested HTTP 206; after review, refined to HTTP 200 with explicit `degraded: true` metadata, which is semantically correct (206 is for range requests per RFC 7233)
2. **Cache-aside pattern with clear separation** — AI proposed caching with TTL; refined to clearly separate in-memory cache (optimization) from PostgreSQL (persistent storage)
3. **Structured logging with request context** — AI recommended `structlog` over standard `logging` for better observability in production
4. **Document uniqueness via composite key** — AI helped identify the need for `UNIQUE(source_system, external_id)` to handle cross-system ID collisions

---

## Appendix

### A. Project Structure (Planned)

```
unified-document-viewer/
├── docs/
│   └── SYSTEM_DESIGN.md
├── src/
│   ├── api/                  # API routes & dependencies
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── documents.py
│   │   │   └── health.py
│   │   └── dependencies.py
│   ├── core/                 # Configuration & settings
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── logging.py
│   ├── models/               # SQLAlchemy models
│   │   ├── __init__.py
│   │   └── document.py
│   ├── schemas/              # Pydantic schemas
│   │   ├── __init__.py
│   │   └── document.py
│   ├── services/             # Business logic
│   │   ├── __init__.py
│   │   ├── aggregator.py
│   │   └── external/
│   │       ├── __init__.py
│   │       ├── sales_client.py
│   │       └── service_client.py
│   ├── db/                   # Database setup & migrations
│   │   ├── __init__.py
│   │   ├── session.py
│   │   └── migrations/
│   ├── mock_servers/         # Mock external APIs
│   │   ├── __init__.py
│   │   ├── sales_api.py
│   │   └── service_api.py
│   └── main.py               # Application entry point
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── docker-compose.yml
├── .gitignore
├── Dockerfile
├── pyproject.toml
├── README.md
└── .env.example
```
