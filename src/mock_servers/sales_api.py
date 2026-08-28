"""Mock Sales System API Server.

Standalone FastAPI application simulating the dealership Sales System.
Returns sample sales documents (contracts, invoices, financing agreements)
for a given VIN, following the contract defined in SYSTEM_DESIGN.md §6.1.

Run standalone:
    uvicorn src.mock_servers.sales_api:app --port 8001
"""

import asyncio

from fastapi import FastAPI, HTTPException, Query

app = FastAPI(
    title="Mock Sales System API",
    description="Simulated dealership Sales System for development and testing.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Sample data keyed by VIN.  Any unknown VIN returns an empty list.
# ---------------------------------------------------------------------------
_SALES_DOCUMENTS: dict[str, list[dict]] = {
    "1HGCM82633A004352": [
        {
            "id": "SALE-001",
            "title": "Vehicle Purchase Agreement",
            "type": "contract",
            "date": "2024-03-15",
            "metadata": {
                "dealer_name": "AutoNation Honda",
                "amount": 32500.00,
            },
        },
        {
            "id": "SALE-002",
            "title": "Trade-In Invoice",
            "type": "invoice",
            "date": "2024-03-15",
            "metadata": {
                "dealer_name": "AutoNation Honda",
                "amount": 8500.00,
            },
        },
        {
            "id": "SALE-003",
            "title": "Auto Loan Financing Agreement",
            "type": "financing_agreement",
            "date": "2024-03-16",
            "metadata": {
                "dealer_name": "AutoNation Honda",
                "amount": 24000.00,
                "term_months": 60,
                "apr": 4.9,
            },
        },
    ],
    "5YJSA1E26MF123456": [
        {
            "id": "SALE-100",
            "title": "New Vehicle Purchase Contract",
            "type": "contract",
            "date": "2025-06-01",
            "metadata": {
                "dealer_name": "Tesla Downtown",
                "amount": 52990.00,
            },
        },
    ],
}


@app.get("/sales/documents")
async def get_sales_documents(
    vin: str = Query(..., description="Vehicle Identification Number"),
    force_error: bool = Query(False, description="Simulate a slow/failing response"),
) -> dict:
    """Return sales documents for the requested VIN.

    Response format follows SYSTEM_DESIGN.md §6.1:
    ```json
    {
      "documents": [ { "id", "title", "type", "date", "metadata" } ]
    }
    ```
    """
    if force_error:
        await asyncio.sleep(5)
        raise HTTPException(status_code=500, detail="Simulated Internal Server Error")

    documents = _SALES_DOCUMENTS.get(vin, [])
    return {"documents": documents}
