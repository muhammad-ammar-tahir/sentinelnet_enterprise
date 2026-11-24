"""Database Connection and Session Management.

Provides async and sync SQLAlchemy engines, session factories, and base declarative models.
Verifies all required schema tables on startup and raises DatabaseInitError on failure.
"""

import logging
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base, DeclarativeBase
from backend.config import settings

logger = logging.getLogger(__name__)


class DatabaseInitError(Exception):
    """Raised when database schema initialization or required table verification fails."""
    pass


# Base class for SQLAlchemy declarative models
class Base(DeclarativeBase):
    """Base declarative model for SentinelNet."""
    pass


# Asynchronous database engine & sessionmaker
engine_kwargs = {
    "echo": settings.DEBUG,
    "pool_pre_ping": True,
}
if "sqlite" not in settings.DATABASE_URL.lower():
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
    })

engine = create_async_engine(
    settings.DATABASE_URL,
    **engine_kwargs
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency generator that yields an asynchronous database session.

    Yields:
        AsyncSession: Active database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error("Database session rollback due to exception: %s", str(e), exc_info=True)
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables during application startup and verify table presence."""
    logger.info("Initializing database tables...")
    # Import models so Base.metadata is fully populated before create_all
    import backend.database.models  # noqa: F401

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified successfully via SQLAlchemy metadata")

        # Verify tables exist in active database (Postgres or SQLite)
        async with engine.connect() as conn:
            if "sqlite" in settings.DATABASE_URL.lower():
                result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            else:
                result = await conn.execute(text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                ))
            tables = [r[0] for r in result]
            required = ["devices", "links", "metrics", "incidents", "recovery_actions", "policies", "users", "audit_logs"]
            missing = [t for t in required if t not in tables]
            if missing:
                raise DatabaseInitError(f"Missing required database tables: {missing}")

        logger.info("Database verification confirmed: %s", tables)
    except Exception as exc:
        logger.critical("Database initialization failed: %s", exc, exc_info=True)
        raise DatabaseInitError(f"Failed to initialize database: {exc}") from exc
