"""Crea un negocio y su propietario inicial, sin endpoints publicos."""
import getpass
import os

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import API_ROOT  # noqa: F401, carga .env
from app.db.session import get_session_factory
from app.modules.auth.model import User  # noqa: F401
from app.modules.auth.service import create_first_owner
from app.modules.organizations.model import Organization
from app.modules.organizations.schemas import OrganizationCreate


def main() -> None:
    if os.getenv("NEXO_ENVIRONMENT") != "local":
        raise SystemExit("Bootstrap solo permitido con NEXO_ENVIRONMENT=local")
    name = input("Nombre comercial: ").strip()
    sector = input("Sector (por ejemplo, imprenta): ").strip()
    email_input = input("Correo del propietario: ").strip().lower()
    try:
        payload = OrganizationCreate(name=name, sector=sector)
        email = str(TypeAdapter(EmailStr).validate_python(email_input))
    except ValidationError as exc:
        raise SystemExit("Datos invalidos: revisa nombre, sector y correo") from exc
    password = getpass.getpass("Contrasena (12-128 caracteres): ")
    repeated = getpass.getpass("Confirmar contrasena: ")
    if password != repeated:
        raise SystemExit("Las contrasenas no coinciden")
    with get_session_factory()() as db:
        try:
            organization = Organization(**payload.model_dump())
            db.add(organization)
            db.flush()
            user = create_first_owner(db, organization_id=organization.id, email=email, password=password)
            db.commit()
            print("Organizacion:", organization.id)
            print("Usuario propietario:", user.id)
            print("Registro inicial completado; utiliza /api/v1/auth/login")
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
