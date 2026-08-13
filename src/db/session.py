"""Database session setup with SQLAlchemy async engine."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings

# ── Async Engine ─────────────────────────────────────────────────────────────
# aiosqlite is the async driver for SQLite; the URL scheme must be
# "sqlite+aiosqlite:///..." so SQLAlchemy dispatches to the async dialect.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    # SQLite does not support pool_size/max_overflow, but connect_args can
    # be used to pass pragmas for WAL mode, foreign keys, etc.
    connect_args={"check_same_thread": False},
)

# ── Session Factory ──────────────────────────────────────────────────────────
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── FastAPI Dependency ───────────────────────────────────────────────────────
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session for use as a FastAPI dependency.

    Usage in a route::

        @router.get("/items")
        async def list_items(session: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
