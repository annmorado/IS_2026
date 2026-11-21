"""Asistente para guardar URL de Neon y token local sin mostrarlos."""
from getpass import getpass
from pathlib import Path
from secrets import token_urlsafe
import sys

api_root = Path(__file__).resolve().parents[1]
env_file = api_root / ".env"

if env_file.exists():
    sys.exit("Ya existe services/api/.env. No se sobrescribio.")

print("Copia la conexion DIRECTA de Neon. El texto que pegues no se mostrara.")
url = getpass("DATABASE_URL: ").strip()
if not url.startswith(("postgresql://", "postgresql+psycopg://")):
    sys.exit("URL no valida. No se creo .env.")
if chr(10) in url or chr(13) in url or '"' in url:
    sys.exit("URL contiene caracteres no admitidos.")
if "-pooler." in url:
    sys.exit("Selecciona conexion DIRECTA (sin -pooler) para migraciones.")

content = (
    f'DATABASE_URL="{url}"' + chr(10)
    + "NEXO_ENVIRONMENT=local" + chr(10)
    + f"NEXO_BOOTSTRAP_TOKEN={token_urlsafe(32)}" + chr(10)
)
env_file.write_text(content, encoding="utf-8")
print("services/api/.env creado. Claves ocultas y excluidas de Git.")
