"""Sesiones SQLAlchemy; conexiones TLS certificadas para Neon."""
from functools import lru_cache
from collections.abc import Generator
import ssl

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_database_url


@lru_cache
def get_engine():
    # Conexion diferida: /health sigue funcionando sin PostgreSQL.
    return create_engine(
        get_database_url(),
        pool_pre_ping=True,
        connect_args={"ssl_context": ssl.create_default_context()},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    with get_session_factory()() as session:
        yield session
