"""RF-012: /orders/search debe registrarse ANTES de /orders/{order_id}."""
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.order_search.schemas import OrderSearchPage
from app.modules.order_search.service import search_orders
from app.modules.tenancy.scope import scope_from_context

router = APIRouter(prefix="/orders", tags=["RF-012 Listado y busqueda"])

Status = Literal["draft", "pending", "confirmed", "in_progress", "completed", "cancelled"]

@router.get("/search", response_model=OrderSearchPage)
def find_orders(
    status: Status | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    q: str | None = Query(default=None, min_length=1, max_length=200),
    only_mine: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: AuthContext = Depends(require_staff),
    db: Session = Depends(get_db),
):
    return search_orders(db, scope_from_context(context), status=status, date_from=date_from,
                         date_to=date_to, q=q, only_mine=only_mine, limit=limit, offset=offset)
