"""AgentForge Lite — SQLite数据库引擎（SQLAlchemy 2.0 async）

要升级PostgreSQL只需改连接串 + pip install asyncpg。
"""

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

DB_PATH = os.getenv("AGENTFORGE_DB", "agentforge.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """自动建表，无需Alembic迁移。"""
    from src.storage.models import Task, Transcript  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """获取数据库会话"""
    async with SessionLocal() as session:
        yield session
