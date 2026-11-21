"""RF-006: inventario + recetas con consultas siempre restringidas al tenant."""
from decimal import Decimal, ROUND_UP
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.modules.decisions.audit import audit

from app.modules.materials.model import Material, ProductMaterial
from app.modules.materials.schemas import (
    MaterialCreate, MaterialPatch, RecipeItemRead, RecipeItemSet,
    MaterialNeedRead, RequirementsRead,
)
from app.modules.products.model import Product
from app.modules.tenancy.scope import TenantScope

PRECISION = Decimal("0.001")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Registro no encontrado")


def _duplicate() -> HTTPException:
    return HTTPException(status_code=409, detail="SKU duplicado en la organizacion")


def find_material(db: Session, scope: TenantScope, material_id: UUID, *, lock: bool = False) -> Material:
    stmt = select(Material).where(Material.id == material_id, Material.organization_id == scope.organization_id)
    if lock:
        stmt = stmt.with_for_update()
    material = db.scalar(stmt)
    if material is None:
        raise _not_found()
    return material


def find_product(db: Session, scope: TenantScope, product_id: UUID, *, lock: bool = False) -> Product:
    stmt = select(Product).where(Product.id == product_id, Product.organization_id == scope.organization_id)
    if lock:
        stmt = stmt.with_for_update()
    product = db.scalar(stmt)
    if product is None:
        raise _not_found()
    return product


def create_material(db: Session, scope: TenantScope, payload: MaterialCreate) -> Material:
    item = Material(organization_id=scope.organization_id, **payload.model_dump())
    db.add(item)
    try:
        db.flush()
        audit(db, scope, entity_type='material', entity_id=item.id, action='material.created',
              after={'sku':item.sku,'name':item.name})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate() from exc
    db.refresh(item)
    return item


def list_materials(db: Session, scope: TenantScope, *, include_inactive: bool, limit: int, offset: int) -> list[Material]:
    stmt = select(Material).where(Material.organization_id == scope.organization_id)
    if not include_inactive:
        stmt = stmt.where(Material.is_active.is_(True))
    return list(db.scalars(stmt.order_by(Material.name, Material.id).limit(limit).offset(offset)).all())


def patch_material(db: Session, scope: TenantScope, material_id: UUID, payload: MaterialPatch) -> Material:
    item = find_material(db, scope, material_id, lock=True)
    fields=payload.model_dump(exclude_unset=True)
    before={k:str(getattr(item,k)) for k in fields}
    for key, value in fields.items():
        setattr(item, key, value)
    audit(db, scope, entity_type='material', entity_id=item.id, action='material.updated',
          before=before,after={k:str(getattr(item,k)) for k in fields})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _duplicate() from exc
    db.refresh(item)
    return item


def set_stock(db: Session, scope: TenantScope, material_id: UUID, quantity: Decimal) -> Material:
    """Ajuste de stock absoluto, no una reserva ni un consumo por pedido."""
    item = find_material(db, scope, material_id, lock=True)
    previous=item.quantity_available
    item.quantity_available = quantity
    audit(db, scope, entity_type='material', entity_id=item.id, action='material.stock_set',
          before={'quantity_available':str(previous)},after={'quantity_available':str(quantity)})
    db.commit()
    db.refresh(item)
    return item


def deactivate_material(db: Session, scope: TenantScope, material_id: UUID) -> Material:
    item = find_material(db, scope, material_id, lock=True)
    item.is_active = False
    audit(db, scope, entity_type='material', entity_id=item.id, action='material.deactivated',
          before={'is_active':True},after={'is_active':False})
    db.commit()
    db.refresh(item)
    return item


def _recipe_rows(db: Session, scope: TenantScope, product_id: UUID):
    return db.execute(
        select(ProductMaterial, Material)
        .join(Material, (ProductMaterial.material_id == Material.id) &
              (ProductMaterial.organization_id == Material.organization_id))
        .where(ProductMaterial.organization_id == scope.organization_id,
               ProductMaterial.product_id == product_id)
        .order_by(Material.sku, Material.id)
    ).all()


def recipe_items(db: Session, scope: TenantScope, product_id: UUID) -> list[RecipeItemRead]:
    find_product(db, scope, product_id)
    return [
        RecipeItemRead(
            material_id=m.id, sku=m.sku, name=m.name, unit=m.unit,
            quantity_per_unit=link.quantity_per_unit,
            quantity_available=m.quantity_available, is_active=m.is_active,
        ) for link, m in _recipe_rows(db, scope, product_id)
    ]


def upsert_recipe_item(db: Session, scope: TenantScope, product_id: UUID, material_id: UUID,
                       payload: RecipeItemSet) -> RecipeItemRead:
    find_product(db, scope, product_id, lock=True)
    material = find_material(db, scope, material_id)
    if not material.is_active:
        raise HTTPException(status_code=409, detail="No puede agregarse un material inactivo")
    link = db.scalar(select(ProductMaterial).where(
        ProductMaterial.organization_id == scope.organization_id,
        ProductMaterial.product_id == product_id,
        ProductMaterial.material_id == material_id,
    ))
    before_value=str(link.quantity_per_unit) if link is not None else None
    if link is None:
        link = ProductMaterial(organization_id=scope.organization_id, product_id=product_id,
                               material_id=material_id, quantity_per_unit=payload.quantity_per_unit)
        db.add(link)
    else:
        link.quantity_per_unit = payload.quantity_per_unit
    audit(db, scope, entity_type='product', entity_id=product_id, action='product.recipe_set',
          before={'material_id':str(material_id),'quantity_per_unit':before_value},
          after={'material_id':str(material_id),'quantity_per_unit':str(payload.quantity_per_unit)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflicto de receta") from exc
    return RecipeItemRead(material_id=material.id, sku=material.sku, name=material.name,
                          unit=material.unit, quantity_per_unit=payload.quantity_per_unit,
                          quantity_available=material.quantity_available, is_active=material.is_active)


def delete_recipe_item(db: Session, scope: TenantScope, product_id: UUID, material_id: UUID) -> None:
    find_product(db, scope, product_id, lock=True)
    link = db.scalar(select(ProductMaterial).where(
        ProductMaterial.organization_id == scope.organization_id,
        ProductMaterial.product_id == product_id,
        ProductMaterial.material_id == material_id,
    ))
    if link is None:
        raise _not_found()
    audit(db, scope, entity_type='product', entity_id=product_id, action='product.recipe_removed',
          before={'material_id':str(material_id),'quantity_per_unit':str(link.quantity_per_unit)})
    db.delete(link)
    db.commit()


def calculate_requirements(db: Session, scope: TenantScope, product_id: UUID, quantity: Decimal) -> RequirementsRead:
    items = recipe_items(db, scope, product_id)
    needs: list[MaterialNeedRead] = []
    for item in items:
        # ROUND_UP evita subestimar material necesario cuando la unidad tiene 3 decimales.
        required = (item.quantity_per_unit * quantity).quantize(PRECISION, rounding=ROUND_UP)
        shortage = max(required - item.quantity_available, Decimal("0.000"))
        needs.append(MaterialNeedRead(**item.model_dump(), required=required,
                                      shortage=shortage,
                                      sufficient=item.is_active and shortage == 0))
    return RequirementsRead(product_id=product_id, quantity=quantity, recipe_configured=bool(items),
                            feasible=bool(items) and all(x.sufficient for x in needs), materials=needs)
