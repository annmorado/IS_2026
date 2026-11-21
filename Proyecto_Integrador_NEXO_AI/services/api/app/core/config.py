"""Configuracion segura de PostgreSQL para NEXO AI."""
from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(API_ROOT / ".env")


@lru_cache
def get_database_url() -> str:
    """Adapta la URL de Neon a pg8000 sin divulgar la contrasena.

    pg8000 no entiende parametros libpq como sslmode/channel_binding;
    exigimos TLS con validacion de certificado al crear cada engine.
    """
    raw_url = os.getenv("DATABASE_URL", "").strip()
    if not raw_url:
        raise RuntimeError("Falta DATABASE_URL. Configura services/api/.env")

    url = make_url(raw_url)
    if url.drivername not in {
        "postgresql", "postgresql+psycopg", "postgresql+pg8000"
    }:
        raise RuntimeError("DATABASE_URL debe apuntar a PostgreSQL.")

    url = url.set(drivername="postgresql+pg8000")
    url = url.difference_update_query(["sslmode", "channel_binding"])

    # No pasar parametros no soportados por pg8000 inadvertidamente.
    if url.query:
        raise RuntimeError(
            "La URL de PostgreSQL tiene parametros adicionales no compatibles "
            "con pg8000. Consulta los parametros de Neon sin mostrar secretos."
        )
    return url.render_as_string(hide_password=False)
