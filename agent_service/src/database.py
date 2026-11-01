from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"timeout": 5, "command_timeout": 120},
)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


async def check_database() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("SELECT embedding FROM ai.knowledge_chunk LIMIT 0")
            await connection.exec_driver_sql("SELECT '[1,0,0]'::vector")
        return True
    except Exception:
        return False
