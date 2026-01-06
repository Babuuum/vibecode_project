from __future__ import annotations

from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.autocontent.config import Settings


class Base(DeclarativeBase):
    """Shared declarative base for ORM models."""


def create_engine_from_settings(settings: Settings | None = None) -> AsyncEngine:
    settings = settings or Settings()
    return create_async_engine(str(settings.postgres_dsn), echo=settings.sqlalchemy_echo)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
