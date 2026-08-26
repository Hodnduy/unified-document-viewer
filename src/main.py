"""FastAPI Main Application Entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes import documents, history
from src.cache import close_redis, init_redis
from src.db import Base, engine

# Import all models so Base.metadata knows about them
from src.models import SearchHistory  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: create tables on startup, dispose engine on shutdown."""
    # -- Startup ----------------------------------------------------------
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await init_redis()
    logger.info("Application startup complete")

    yield

    # -- Shutdown ---------------------------------------------------------
    await close_redis()
    await engine.dispose()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="Unified Document Viewer API",
    description="Unified REST API for dealership vehicle documents",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(documents.router, prefix="/api/v1")
app.include_router(history.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Welcome to Unified Document Viewer API"}
