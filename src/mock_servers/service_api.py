"""Mock Service System API Server.

Standalone FastAPI application simulating the dealership Service System.
Returns sample service documents (repair orders, inspection reports,
maintenance records) for a given VIN, following the contract defined in
SYSTEM_DESIGN.md §6.2.

Run standalone:
    uvicorn src.mock_servers.service_api:app --port 8002
"""

import asyncio

from fastapi import FastAPI, HTTPException, Query

app = FastAPI(
    title="Mock Service System API",
    description="Simulated dealership Service System for development and testing.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Sample data keyed by VIN.  Any unknown VIN returns an empty list.
# ---------------------------------------------------------------------------
_SERVICE_DOCUMENTS: dict[str, list[dict]] = {
    "1HGCM82633A004352": [
        {
            "id": "SVC-001",
            "title": "60,000 Mile Service Report",
            "type": "service_report",
            "date": "2025-01-20",
            "metadata": {
                "mileage": 60234,
                "technician": "John Smith",
            },
        },
        {
            "id": "SVC-002",
            "title": "Brake Pad Replacement",
            "type": "repair_order",
            "date": "2025-03-10",
            "metadata": {
                "mileage": 62100,
                "technician": "Maria Garcia",
                "cost": 450.00,
            },
        },
        {
            "id": "SVC-003",
            "title": "Annual Safety Inspection",
            "type": "inspection_report",
            "date": "2025-07-05",
            "metadata": {
                "mileage": 65800,
                "technician": "John Smith",
                "result": "pass",
            },
        },
    ],
    "5YJSA1E26MF123456": [
        {
            "id": "SVC-200",
            "title": "Initial Service Check",
            "type": "maintenance_record",
            "date": "2025-12-15",
            "metadata": {
                "mileage": 5000,
                "technician": "Alex Johnson",
            },
        },
        {
            "id": "SVC-201",
            "title": "Tire Rotation & Alignment",
            "type": "maintenance_record",
            "date": "2026-03-20",
            "metadata": {
                "mileage": 12300,
                "technician": "Alex Johnson",
                "cost": 180.00,
            },
        },
    ],
}


@app.get("/service/documents")
async def get_service_documents(
    vin: str = Query(..., description="Vehicle Identification Number"),
    force_error: bool = Query(False, description="Simulate a slow/failing response"),
) -> dict:
    """Return service documents for the requested VIN.

    Response format follows SYSTEM_DESIGN.md §6.2:
    ```json
    {
      "documents": [ { "id", "title", "type", "date", "metadata" } ]
    }
    ```
    """
    if force_error:
        await asyncio.sleep(5)
        raise HTTPException(status_code=500, detail="Simulated Internal Server Error")

    documents = _SERVICE_DOCUMENTS.get(vin, [])
    return {"documents": documents}
