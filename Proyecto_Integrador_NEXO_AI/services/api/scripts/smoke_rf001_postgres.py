"""Integracion real PostgreSQL: crea, recupera desde nueva sesion y limpia."""
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.modules.organizations.schemas import OrganizationCreate
from app.modules.organizations.service import create_organization, get_organization


def main() -> None:
    engine = get_engine()
    ids = []
    try:
        with Session(engine) as session:
            for name in ("RF001 A", "RF001 B"):
                org = create_organization(
                    session,
                    OrganizationCreate(name=f"{name} {uuid4().hex[:6]}", sector="Imprenta"),
                )
                ids.append(org.id)
        with Session(engine) as session:
            a = get_organization(session, ids[0])
            b = get_organization(session, ids[1])
            assert a is not None and b is not None
            assert a.id != b.id
            assert a.name.startswith("RF001 A")
            assert b.name.startswith("RF001 B")
            assert a.currency == "MXN"
            print("RF-001 PostgreSQL OK: 2 organizaciones con UUID distintos, persistencia y consulta verificadas.")
    finally:
        with Session(engine) as session:
            from app.modules.organizations.model import Organization
            for org_id in ids:
                row = session.get(Organization, org_id)
                if row is not None:
                    session.delete(row)
            session.commit()
        engine.dispose()


if __name__ == "__main__":
    main()
