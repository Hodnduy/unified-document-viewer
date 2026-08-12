"""FastAPI Main Application Entrypoint."""
from fastapi import FastAPI
from src.api.routes import documents, health

app = FastAPI(
    title="Unified Document Viewer API",
    description="Unified REST API for dealership vehicle documents",
    version="0.1.0",
)

app.include_router(documents.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to Unified Document Viewer API"}
