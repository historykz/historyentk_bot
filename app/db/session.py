from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,   # detect and discard dead connections before using them
    pool_size=10,
    max_overflow=20,
    pool_recycle=1800,    # recycle connections every 30 min to avoid stale/half-open sockets
    pool_timeout=30,      # don't hang forever waiting for a free connection from the pool
    connect_args={"timeout": 10},  # asyncpg connect timeout in seconds
)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
