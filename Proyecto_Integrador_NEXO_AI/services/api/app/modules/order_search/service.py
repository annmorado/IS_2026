"""RF-012: filtro tenant-scoped, fechas de la empresa y paginacion consistente."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.order_search.schemas import OrderSearchPage
from app.modules.orders.model import Order
from app.modules.organizations.model import Organization
from app.modules.tenancy.scope import TenantScope


def _escape_like(value: str) -> str:
    # No permitir que porcentajes o guiones bajos del cliente se transformen
    # en patrones LIKE; los parametros siempre via SQLAlchemy.
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_orders(db: Session, scope: TenantScope, *, status: str | None,
                  date_from: date | None, date_to: date | None,
                  q: str | None, only_mine: bool, limit: int, offset: int) -> OrderSearchPage:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from no puede ser posterior a date_to")
    if q is not None:
        q = q.strip()
        if not q:
            raise HTTPException(status_code=422, detail="q no puede estar vacio")

    filters = [Order.organization_id == scope.organization_id]
    if status is not None:
        filters.append(Order.status == status)
    if only_mine:
        filters.append(Order.created_by_user_id == scope.actor_id)
    if q is not None:
        filters.append(Order.raw_text.ilike("%" + _escape_like(q) + "%", escape="\\"))

    if date_from is not None or date_to is not None:
        zone_name = db.scalar(select(Organization.timezone).where(Organization.id == scope.organization_id))
        if zone_name is None:
            raise HTTPException(status_code=404, detail="Organizacion no encontrada")
        zone = ZoneInfo(zone_name)
        if date_from is not None:
            start_utc = datetime.combine(date_from, time.min, tzinfo=zone).astimezone(timezone.utc)
            filters.append(Order.created_at >= start_utc)
        if date_to is not None and date_to != date.max:
            # El ultimo dia representable no admite sumar un dia.
            next_day_utc = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
            filters.append(Order.created_at < next_day_utc)

    total = db.scalar(select(func.count()).select_from(Order).where(*filters)) or 0
    rows = list(db.scalars(select(Order).where(*filters).order_by(
        Order.created_at.desc(), Order.id.desc()).limit(limit).offset(offset)).all())
    has_more = offset + len(rows) < total
    return OrderSearchPage(items=rows, total=total, limit=limit, offset=offset,
                           has_more=has_more, next_offset=offset + len(rows) if has_more else None)
