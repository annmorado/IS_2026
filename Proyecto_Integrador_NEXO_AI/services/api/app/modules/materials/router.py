"""RF-006: acceso seguro al stock y recetas. Org sale solo del JWT validado."""
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner, require_staff
from app.modules.tenancy.scope import scope_from_context
from app.modules.materials.schemas import (
    MaterialCreate, MaterialPatch, MaterialRead, StockSet,
    RecipeItemRead, RecipeItemSet, RecipeRead, RequirementsRead,
)
from app.modules.materials.service import (
    create_material, list_materials, find_material, patch_material,
    set_stock, deactivate_material, recipe_items, upsert_recipe_item,
    delete_recipe_item, calculate_requirements,
)

materials_router = APIRouter(prefix="/materials", tags=["RF-006 Materiales e inventario"])
recipe_router = APIRouter(prefix="/products", tags=["RF-006 Recetas de produccion"])


@materials_router.post("", status_code=status.HTTP_201_CREATED, response_model=MaterialRead)
def create(payload: MaterialCreate, context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return create_material(db, scope_from_context(context), payload)


@materials_router.get("", response_model=list[MaterialRead])
def list_all(
    include_inactive: bool = False, limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    context: AuthContext = Depends(require_staff), db: Session = Depends(get_db),
):
    return list_materials(db, scope_from_context(context), include_inactive=include_inactive, limit=limit, offset=offset)


@materials_router.get("/{material_id}", response_model=MaterialRead)
def read(material_id: UUID, context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return find_material(db, scope_from_context(context), material_id)


@materials_router.patch("/{material_id}", response_model=MaterialRead)
def edit(material_id: UUID, payload: MaterialPatch,
         context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return patch_material(db, scope_from_context(context), material_id, payload)


@materials_router.put("/{material_id}/stock", response_model=MaterialRead)
def update_stock(material_id: UUID, payload: StockSet,
                 context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return set_stock(db, scope_from_context(context), material_id, payload.quantity_available)


@materials_router.post("/{material_id}/deactivate", response_model=MaterialRead)
def deactivate(material_id: UUID, context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return deactivate_material(db, scope_from_context(context), material_id)


@recipe_router.get("/{product_id}/recipe", response_model=RecipeRead)
def read_recipe(product_id: UUID, context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return RecipeRead(product_id=product_id, items=recipe_items(db, scope_from_context(context), product_id))


@recipe_router.put("/{product_id}/recipe/{material_id}", response_model=RecipeItemRead)
def put_recipe_item(product_id: UUID, material_id: UUID, payload: RecipeItemSet,
                    context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    return upsert_recipe_item(db, scope_from_context(context), product_id, material_id, payload)


@recipe_router.delete("/{product_id}/recipe/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_recipe_item(product_id: UUID, material_id: UUID,
                       context: AuthContext = Depends(require_owner), db: Session = Depends(get_db)):
    delete_recipe_item(db, scope_from_context(context), product_id, material_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@recipe_router.get("/{product_id}/material-requirements", response_model=RequirementsRead)
def requirements(
    product_id: UUID,
    quantity: Decimal = Query(..., gt=Decimal("0"), max_digits=11, decimal_places=3),
    context: AuthContext = Depends(require_staff), db: Session = Depends(get_db),
):
    return calculate_requirements(db, scope_from_context(context), product_id, quantity)
