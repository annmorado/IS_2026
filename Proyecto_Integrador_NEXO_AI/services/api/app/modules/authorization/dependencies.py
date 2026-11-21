"""Guardias de roles del servidor; nunca confiar en roles enviados por el cliente."""
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from app.modules.auth.dependencies import AuthContext, get_auth_context

VALID_ROLES = frozenset({"owner", "operator"})


def require_roles(*roles: str) -> Callable:
    allowed = frozenset(roles)
    if not allowed or not allowed.issubset(VALID_ROLES):
        raise ValueError("Configuracion de permisos invalida")

    def check_role(request: Request, context: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if context.user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para realizar esta operacion",
            )
        if context.user.role=='operator' and context.user.permissions_json is not None:
            from app.modules.collaborators.permissions import required_for_path, ensure_permission
            required=required_for_path(request.url.path,request.method)
            if required is None:
                raise HTTPException(status_code=403,detail='La operación no está habilitada para este colaborador')
            ensure_permission(context.user,required)
        return context

    return check_role


require_owner = require_roles("owner")
require_staff = require_roles("owner", "operator")
