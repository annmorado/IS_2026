"""Pruebas de configuracion pg8000: no requieren una base de datos."""
import ssl

import pytest
from sqlalchemy.engine import make_url

from app.core.config import get_database_url
from app.db import session as db_session


@pytest.mark.parametrize(
    "scheme", ["postgresql", "postgresql+psycopg", "postgresql+pg8000"]
)
def test_neon_url_uses_pg8000_with_no_libpq_params(monkeypatch, scheme):
    monkeypatch.setenv(
        "DATABASE_URL",
        f"{scheme}://user:secret@ep-example.us-east-1.aws.neon.tech/nexo_ai_dev"
        "?sslmode=require&channel_binding=require",
    )
    get_database_url.cache_clear()
    url = make_url(get_database_url())
    assert url.drivername == "postgresql+pg8000"
    assert url.password == "secret"
    assert url.query == {}
    get_database_url.cache_clear()


def test_unknown_url_scheme_is_rejected(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///mydb")
    get_database_url.cache_clear()
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        get_database_url()
    get_database_url.cache_clear()


def test_engine_requires_verified_tls(monkeypatch):
    captured = {}

    def fake_create_engine(url, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(db_session, "get_database_url", lambda: "dummy")
    monkeypatch.setattr(db_session, "create_engine", fake_create_engine)
    db_session.get_engine.cache_clear()
    db_session.get_engine()
    ctx = captured["connect_args"]["ssl_context"]
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True
    db_session.get_engine.cache_clear()
