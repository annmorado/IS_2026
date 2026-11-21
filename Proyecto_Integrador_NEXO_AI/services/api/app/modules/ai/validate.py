"""RIA-003: validation before human confirmation; this module never writes orders."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from uuid import UUID
from sqlalchemy import select
from app.modules.products.model import Product


def validate_input(db, scope, data: dict) -> dict:
    issues=[]
    product=None
    product_id=data.get("product_id")
    if not product_id:
        issues.append({"field":"product_id","code":"required","message":"Selecciona un producto del catálogo"})
    else:
        try:
            product=db.scalar(select(Product).where(Product.id==UUID(str(product_id)),
                Product.organization_id==scope.organization_id, Product.is_active.is_(True)))
        except (ValueError, TypeError):pass
        if product is None:
            issues.append({"field":"product_id","code":"not_in_catalog","message":"El producto no existe en este catálogo activo"})
    quantity=data.get("quantity")
    qty=None
    if quantity is None or isinstance(quantity,bool):
        issues.append({"field":"quantity","code":"required","message":"Indica una cantidad válida"})
    else:
        try:
            qty=Decimal(str(quantity))
            if not qty.is_finite() or qty<=0 or qty>Decimal("999999999.999") or -qty.as_tuple().exponent>3:
                raise ValueError
        except (ValueError,InvalidOperation,TypeError):
            issues.append({"field":"quantity","code":"invalid","message":"La cantidad debe ser positiva, finita y con hasta tres decimales"})
    price=data.get("unit_price_mxn")
    if price is not None and price!='':
        try:
            value=Decimal(str(price))
            if not value.is_finite() or value<0 or value>Decimal("9999999999.99") or -value.as_tuple().exponent>2:
                raise ValueError
        except (ValueError,InvalidOperation,TypeError):
            issues.append({"field":"unit_price_mxn","code":"invalid","message":"El precio debe ser no negativo, finito y con máximo dos decimales"})
    when=data.get("requested_date")
    if not when:
        issues.append({"field":"requested_date","code":"required","message":"Indica la fecha solicitada"})
    else:
        try:
            if not isinstance(when,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",when):raise ValueError
            date.fromisoformat(when)
        except ValueError:
            issues.append({"field":"requested_date","code":"invalid_date","message":"Fecha inválida; usa AAAA-MM-DD"})
    notes=data.get("notes")
    if notes is not None and (not isinstance(notes,str) or len(notes)>500):
        issues.append({"field":"notes","code":"invalid","message":"Observaciones de máximo 500 caracteres"})
    return {"valid":not issues,"issues":issues,"product_name":product.name if product else None,
            "review_required":True,"order_confirmed":False,"changes_applied":False}
