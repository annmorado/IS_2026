"""Proteccion temporal del bootstrap. NO reemplaza RF-002/003/004."""
import os
import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status


def require_local_bootstrap(
    request: Request,
    x_nexo_bootstrap_token: Annotated[str | None, Header(alias="X-NEXO-Bootstrap-Token")] = None,
) -> None:
    """Permite operar el prototipo solo desde loopback y con clave local."""
    client_host = request.client.host if request.client is not None else None
    if os.getenv("NEXO_ENVIRONMENT") != "local" or client_host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bootstrap no disponible")

    secret = os.getenv("NEXO_BOOTSTRAP_TOKEN", "")
    if not secret or not x_nexo_bootstrap_token or not secrets.compare_digest(secret, x_nexo_bootstrap_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado")
