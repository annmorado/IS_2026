"""Identificador de organizacion confiable derivado de una sesion validada."""
from dataclasses import dataclass
from uuid import UUID

from app.modules.auth.dependencies import AuthContext


@dataclass(frozen=True, slots=True)
class TenantScope:
    organization_id: UUID
    actor_id: UUID


def scope_from_context(context: AuthContext) -> TenantScope:
    # Nunca tomar organization_id de URL, query, cuerpo o X-Organization-ID.
    return TenantScope(
        organization_id=context.user.organization_id,
        actor_id=context.user.id,
    )
