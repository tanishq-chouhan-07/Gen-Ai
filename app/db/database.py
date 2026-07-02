# app/db/database.py
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
import structlog

from app.config.settings import get_settings

logger = structlog.get_logger()


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def _build_db_url(original_url: str) -> str:
    """
    Convert any postgresql URL to use psycopg driver.
    psycopg3 works correctly on Windows with PostgreSQL 16.
    """
    url = original_url
    # Replace any existing driver prefix with psycopg
    for prefix in [
        "postgresql+asyncpg://",
        "postgresql+psycopg2://",
        "postgresql://",
    ]:
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
            break
    return url


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = _build_db_url(settings.database_url)

        logger.info("Creating database engine", url_prefix=db_url[:40])

        _engine = create_async_engine(
            db_url,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_recycle=1800,
            echo=settings.debug,
        )
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def check_database_connection() -> tuple[bool, str]:
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True, "Connected successfully"
    except Exception as e:
        logger.error("Database connection failed", error=str(e))
        return False, str(e)


async def create_all_tables() -> None:
    # CRITICAL: Models must be imported before create_all
    # SQLAlchemy only creates tables it knows about
    # Importing the module registers the models with Base.metadata
    import app.db.models  # noqa: F401

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified/created")

async def close_database() -> None:
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database connections closed")