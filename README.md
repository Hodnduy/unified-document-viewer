# Unified Document Viewer

[![CI/CD Pipeline](https://github.com/<username>/unified-document-viewer/actions/workflows/ci.yml/badge.svg)](https://github.com/<username>/unified-document-viewer/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://docker.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-Cache-DC382D.svg)](https://redis.io)

> A production-grade backend service for unified vehicle document aggregation, featuring a **Redis Cache-Aside pattern**, **Async PostgreSQL**, **Graceful Degradation**, and a full **CI/CD pipeline**.

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture & Design](#-architecture--design)
- [Key Features](#-key-features)
- [Quick Start Guide (Docker)](#-quick-start-guide-docker)
  - [1. Running the System](#1-running-the-system)
  - [2. Database Migrations](#2-database-migrations)
  - [3. Testing the API](#3-testing-the-api)
- [Local Development & Tests](#-local-development--tests)
- [CI/CD Pipeline](#-cicd-pipeline)

---

## 🔍 Overview

Dealerships typically operate with fragmented systems: a **Sales System** and a **Service System**. 

The **Unified Document Viewer** backend resolves this fragmentation by exposing a high-performance RESTful endpoint (`GET /api/v1/documents`). Given a Vehicle Identification Number (VIN), the backend:
1. **Checks Redis Cache** for instant retrieval.
2. If cache misses, issues **async parallel requests** to all upstream APIs.
3. Normalises heterogeneous data into a unified schema.
4. Saves the search audit trail to **PostgreSQL**.
5. Surfaces results gracefully even during partial upstream outages (Degraded Mode).

---

## 🏗️ Architecture & Design

The complete architectural plan and data flow diagrams are documented in:
📄 **[docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md)**

```text
                     GET /api/v1/documents?vin=...
                                  │
                                  ▼
+-----------------------------------------------------------------------+
|                    Unified Document Viewer API                        |
|                            (FastAPI)                                  |
+-----------------------------------------------------------------------+
     │                      │                              │
 (1) │ Cache Check      (2) │ Parallel Fetch           (3) │ Audit Log
     ▼                      ▼                              ▼
+---------+     +-----------------------+              +------------+
|  Redis  |     |   httpx AsyncClient   |              | PostgreSQL |
| (Cache) |     +-----------------------+              | (History)  |
+---------+         /               \                  +------------+
                   /                 \
                  ▼                   ▼
    +-------------------+      +-------------------+
    |  Mock Sales API   |      | Mock Service API  |
    |    (Port 8001)    |      |    (Port 8002)    |
    +-------------------+      +-------------------+
```

---

## ✨ Key Features

- **Redis Cache-Aside Pattern:** Instant document retrieval (sub-10ms) for repeated queries. Includes a fail-safe mechanism: if Redis is down, the system bypasses the cache and continues functioning normally.
- **Async PostgreSQL Database:** Uses `asyncpg` and SQLAlchemy ORM for high-throughput, non-blocking database operations.
- **Alembic Migrations:** Version-controlled database schema management.
- **Graceful Degradation:** When an upstream source fails or times out, the API returns available documents, sets `"degraded": true`, and provides per-source error metadata without returning an HTTP 500.
- **Dockerized Infrastructure:** A single `docker-compose.yml` orchestrates the API, Mock Servers, PostgreSQL, and Redis with health checks and dependency orders.
- **CI/CD Pipeline:** GitHub Actions automatically run linting (`ruff`), unit tests (`pytest`), measure coverage, and push the verified Docker image to **GitHub Container Registry (GHCR)**.

---

## 🚀 Quick Start Guide (Docker)

The easiest way to run the entire distributed system is using Docker Compose.

### 1. Running the System

```bash
# Build and start all 5 containers (API, Sales, Service, DB, Cache) in the background
docker compose up --build -d
```

### 2. Database Migrations

Once the containers are running, apply the Alembic database migrations to create the tables in PostgreSQL:

```bash
docker compose exec api uv run alembic upgrade head
```

### 3. Testing the API

**Request aggregated documents (Cache Miss - fetching from APIs):**
```bash
curl -s "http://localhost:8000/api/v1/documents?vin=1HGCM82633A004352" | jq
```
*Notice `"cache_hit": false` in the response.*

**Request again (Cache Hit - instant response from Redis):**
```bash
curl -s "http://localhost:8000/api/v1/documents?vin=1HGCM82633A004352" | jq
```
*Notice `"cache_hit": true` in the response.*

**Force refresh the cache:**
```bash
curl -s "http://localhost:8000/api/v1/documents?vin=1HGCM82633A004352&force_refresh=true" | jq
```

---

## 💻 Local Development & Tests

If you want to run the code locally (without Docker):

1. **Install dependencies using `uv`:**
   ```bash
   uv sync --all-extras
   ```

2. **Run the 175+ automated tests:**
   ```bash
   uv run pytest --cov=src -v
   ```
   *(Note: Local tests are configured via `conftest.py` to use in-memory SQLite and mock Redis, so they run blazing fast without requiring local DB installations).*

---

## ⚙️ CI/CD Pipeline

This project includes a robust CI/CD pipeline built with GitHub Actions (`.github/workflows/ci.yml`).

- **Continuous Integration (CI):** On every Pull Request, the pipeline runs `ruff` for code quality and `pytest` for unit testing.
- **Continuous Deployment (CD):** When code is merged into `main`, the pipeline automatically builds the Docker image and pushes it to **GitHub Container Registry (GHCR)** tagged with `latest` and the specific commit SHA.