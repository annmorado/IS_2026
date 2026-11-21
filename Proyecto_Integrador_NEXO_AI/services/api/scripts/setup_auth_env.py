"""Genera NEXO_JWT_SECRET sin imprimir credenciales ni sobreescribir otras claves."""
import os
import secrets

from dotenv import dotenv_values
from app.core.config import API_ROOT


def main() -> None:
    path = API_ROOT / ".env"
    if not path.is_file():
        raise SystemExit("Falta .env: primero configura RF-001")
    parsed = dotenv_values(path)
    if parsed.get("NEXO_JWT_SECRET"):
        print("NEXO_JWT_SECRET ya existe; no se modifico.")
        return
    with path.open("a", encoding="utf-8") as f:
        f.write("\nNEXO_JWT_SECRET=" + secrets.token_urlsafe(48) + "\n")
    print("NEXO_JWT_SECRET generado y guardado en .env (valor oculto).")
    print("Reinicia Uvicorn si estaba encendido.")


if __name__ == "__main__":
    main()
