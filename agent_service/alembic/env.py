import asyncio
import os
import re
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from alembic import context
from src.config import settings

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
if config.config_file_name:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url, literal_binds=True, dialect_opts={"paramstyle": "named"}
    )
    with context.begin_transaction():
        context.run_migrations()


# Keep alembic's bookkeeping out of `public` when sharing the database with core: Flyway refuses to
# migrate a non-empty `public` schema without its own history table. Existing databases that already
# track alembic in `public` simply leave this unset.
VERSION_SCHEMA = os.getenv("ALEMBIC_VERSION_SCHEMA") or None
if VERSION_SCHEMA and not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", VERSION_SCHEMA):
    raise ValueError("ALEMBIC_VERSION_SCHEMA must be a simple lower-case identifier")


def do_run_migrations(connection) -> None:
    if VERSION_SCHEMA:
        connection.exec_driver_sql(f'CREATE SCHEMA IF NOT EXISTS "{VERSION_SCHEMA}"')
        # Commit now: if a transaction is still open, alembic treats it as caller-owned and never
        # commits its own work, so every migration would silently roll back.
        connection.commit()
    context.configure(connection=connection, version_table_schema=VERSION_SCHEMA)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
