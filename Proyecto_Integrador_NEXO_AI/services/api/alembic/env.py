"""Configuracion Alembic; pg8000 con TLS validado."""
import ssl

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_database_url
from app.db.base import Base
from app.modules.organizations import model  # noqa: F401 registra tabla
from app.modules.auth import model as auth_model  # noqa: F401 registra tablas RF-002
from app.modules.products import model as product_model  # noqa: F401 registra tabla RF-005
from app.modules.materials import model as materials_model  # noqa: F401 registra RF-006
from app.modules.capacity import model as capacity_model  # noqa: F401 registra RF-007
from app.modules.voice_notes import model as voice_note_model  # noqa: F401 registra RF-009
from app.modules.orders import model as orders_model  # noqa: F401 registra RF-008

from app.modules.order_status import model as order_status_model  # noqa: F401 registra RF-011

from app.modules.quotes import model as quotes_model  # noqa: F401 registra RF-013
from app.modules.quote_documents import model as documents_model  # noqa: F401 RF-014

from app.modules.decisions import model as decisions_model  # noqa: F401 RF-018-022

from app.modules.collaborators import model as collaborators_model  # noqa: F401
from app.modules.purchasing import model as purchasing_model  # noqa: F401
from app.modules.scheduling import model as scheduling_model  # noqa: F401
from app.modules.notifications import model as notifications_model  # noqa: F401

from app.modules.extensions import model as extensions_model  # noqa: F401 RF-028..RF-032

from app.modules.ai import model as ai_model  # noqa: F401 RIA-001..RIA-005

from app.modules.ai_ops import model as ai_ops_model  # noqa: F401 RIA-006..RIA-018

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        get_database_url(),
        poolclass=pool.NullPool,
        connect_args={"ssl_context": ssl.create_default_context()},
    )
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
