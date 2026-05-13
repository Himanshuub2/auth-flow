from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context
from alembic.operations.base import Operations
from alembic.operations.ops import DropTableOp

from config import settings
from database import Base
from models.events import Event, EventLike, EventMediaItem
from models.events.user import User
from models.documents import Document, DocumentRevision
from models.documents.bulk_applicability import BulkApplicabilityRequest  # noqa: F401
from models.documents.document_file import DocumentFile
from models.documents.legislation import Legislation, SubLegislation

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_original_operations_invoke = Operations.invoke


def _invoke_block_drop_table(self, operation):
    """Reject ``op.drop_table()`` during ``alembic upgrade`` / offline runs.

    Does not intercept ``op.execute("DROP TABLE ...")`` — avoid raw DDL drops in migrations.
    """
    if isinstance(operation, DropTableOp):
        t = operation.table_name
        s = operation.schema
        qualified = f"{s}.{t}" if s else t
        raise RuntimeError(
            "DROP TABLE is disabled in alembic/env.py "
            f"({qualified!r}). Remove op.drop_table from the revision or run the drop outside Alembic."
        )
    return _original_operations_invoke(self, operation)


Operations.invoke = _invoke_block_drop_table  # type: ignore[method-assign]


def include_object(obj, name: str, type_: str, reflected: bool, compare_to) -> bool:
    """Block autogenerate from emitting DROP TABLE / DROP COLUMN.

    When ``reflected`` is True and ``compare_to`` is None, the object exists in the
    database but not in ``target_metadata`` — Alembic would normally generate a drop.
    Returning False skips that so tables/columns are never auto-dropped.

    Note: Hand-written ``op.drop_table()`` is still blocked at runtime via
    ``Operations.invoke``; ``op.drop_column`` and ``op.execute("DROP ...")`` are not.
    """
    if type_ == "table" and reflected and compare_to is None:
        return False
    if type_ == "column" and reflected and compare_to is None:
        return False
    return True


sync_url = settings.DATABASE_URL
if sync_url.startswith("postgresql+asyncpg://"):
    sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
elif sync_url.startswith("postgresql+psycopg://"):
    sync_url = sync_url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(sync_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
