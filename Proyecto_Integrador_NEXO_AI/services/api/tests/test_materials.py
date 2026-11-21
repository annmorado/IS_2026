"""RF-006: CRUD inventario, receta, calculo y seguridad entre tenants."""
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.modules.auth.model import User  # noqa: F401
from app.modules.auth.security import hash_password
from app.modules.materials.model import Material, ProductMaterial  # noqa: F401
from app.modules.organizations.model import Organization
from app.modules.products.model import Product

P = "Materiales-RF006-Fuerte-2026!"
SECRET = "clave-rf006-pruebas-" + "z" * 70
BASE = "/api/v1/materials"


def material_payload(**kwargs):
    payload = {"sku": "TEL-100", "name": "Tela algodon", "unit": "metro", "quantity_available": "10.000"}
    payload.update(kwargs)
    return payload


def product_payload(**kwargs):
    payload = {"sku": "PLAYERA-1", "name": "Playera", "unit": "pieza", "cost_mxn": "40.00",
               "price_mxn": "80.00", "base_production_minutes": "25.00"}
    payload.update(kwargs)
    return payload


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setenv("NEXO_JWT_SECRET", SECRET)
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(conn, record):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    passwd = hash_password(P)
    with factory() as db:
        a = Organization(name="Negocio A", sector="Textil", timezone="America/Mexico_City", currency="MXN")
        b = Organization(name="Negocio B", sector="Textil", timezone="America/Mexico_City", currency="MXN")
        db.add_all((a,b)); db.flush()
        db.add_all([
            User(organization_id=a.id, email="owner.a@example.com", password_hash=passwd, role="owner"),
            User(organization_id=b.id, email="owner.b@example.com", password_hash=passwd, role="owner"),
            User(organization_id=a.id, email="operator.a@example.com", password_hash=passwd, role="operator"),
        ])
        a_id,b_id=a.id,b.id
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            def login(org, email):
                r = client.post("/api/v1/auth/login", json={"organization_id":str(org), "email":email, "password":P})
                assert r.status_code == 200, r.text
                return {"Authorization": "Bearer " + r.json()["access_token"]}
            yield {"client":client,"factory":factory,"a":a_id,"b":b_id,
                "owner_a":login(a_id,"owner.a@example.com"),
                "owner_b":login(b_id,"owner.b@example.com"),
                "operator_a":login(a_id,"operator.a@example.com")}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def new_material(ctx, headers="owner_a", **kwargs):
    return ctx["client"].post(BASE, headers=ctx[headers], json=material_payload(**kwargs))


def new_product(ctx, headers="owner_a", **kwargs):
    return ctx["client"].post("/api/v1/products", headers=ctx[headers], json=product_payload(**kwargs))


def api(ctx, method, suffix, headers="owner_a", payload=None):
    return ctx["client"].request(method, suffix, headers=ctx[headers], json=payload)


def test_create_material_and_retrieve_and_persist(ctx):
    r = new_material(ctx)
    assert r.status_code == 201, r.text
    item=r.json()
    assert item["organization_id"]==str(ctx["a"])
    assert item["quantity_available"]=="10.000"
    assert api(ctx,"GET",BASE+"/"+item["id"]).status_code==200
    with ctx["factory"]() as db:
        assert db.get(Material, UUID(item["id"])).name=="Tela algodon"


def test_operator_can_list_and_read(ctx):
    item=new_material(ctx).json()
    response=api(ctx,"GET",BASE,headers="operator_a")
    assert response.status_code==200 and len(response.json())==1
    assert api(ctx,"GET",BASE+"/"+item["id"],headers="operator_a").status_code==200


def test_owner_patch_name_and_sku(ctx):
    id=new_material(ctx).json()["id"]
    r=api(ctx,"PATCH",BASE+"/"+id,payload={"sku":"  TEL-200  ","name":"  Tela nueva "})
    assert r.status_code==200 and r.json()["sku"]=="TEL-200" and r.json()["name"]=="Tela nueva"


def test_duplicate_sku_within_org_conflicts(ctx):
    assert new_material(ctx).status_code==201
    assert new_material(ctx).status_code==409


def test_same_sku_allowed_in_different_org(ctx):
    assert new_material(ctx,"owner_a").status_code==201
    assert new_material(ctx,"owner_b").status_code==201


def test_patch_conflicting_sku_409(ctx):
    new_material(ctx)
    two=new_material(ctx,sku="TEL-200").json()["id"]
    assert api(ctx,"PATCH",BASE+"/"+two,payload={"sku":"TEL-100"}).status_code==409


def test_set_absolute_stock_and_read(ctx):
    id=new_material(ctx).json()["id"]
    r=api(ctx,"PUT",BASE+"/"+id+"/stock",payload={"quantity_available":"12.500"})
    assert r.status_code==200 and r.json()["quantity_available"]=="12.500"
    with ctx["factory"]() as db:
        assert db.get(Material,UUID(id)).quantity_available==Decimal("12.500")


def test_zero_stock_allowed(ctx):
    id=new_material(ctx).json()["id"]
    assert api(ctx,"PUT",BASE+"/"+id+"/stock",payload={"quantity_available":"0"}).status_code==200


@pytest.mark.parametrize("quantity", ["-0.001", "invalid", "1.0009", "9999999999999999", None])
def test_invalid_stock_is_422(ctx, quantity):
    id=new_material(ctx).json()["id"]
    assert api(ctx,"PUT",BASE+"/"+id+"/stock",payload={"quantity_available":quantity}).status_code==422


@pytest.mark.parametrize("bad", ["0", "-1", "0.0001", "not-number", None])
def test_invalid_recipe_consumption_422(ctx,bad):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    assert api(ctx,"PUT",f"/api/v1/products/{p}/recipe/{m}",payload={"quantity_per_unit":bad}).status_code==422


def test_recipe_create_and_read(ctx):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    r=api(ctx,"PUT",f"/api/v1/products/{p}/recipe/{m}",payload={"quantity_per_unit":"0.250"})
    assert r.status_code==200,r.text
    assert r.json()["quantity_per_unit"]=="0.250"
    rec=api(ctx,"GET",f"/api/v1/products/{p}/recipe",headers="operator_a")
    assert rec.status_code==200 and len(rec.json()["items"])==1
    assert rec.json()["items"][0]["material_id"]==m


def test_recipe_upsert_replaces_not_duplicates(ctx):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    url=f"/api/v1/products/{p}/recipe/{m}"
    assert api(ctx,"PUT",url,payload={"quantity_per_unit":"0.250"}).status_code==200
    assert api(ctx,"PUT",url,payload={"quantity_per_unit":"0.500"}).status_code==200
    response=api(ctx,"GET",f"/api/v1/products/{p}/recipe")
    assert len(response.json()["items"])==1
    assert response.json()["items"][0]["quantity_per_unit"]=="0.500"


def test_recipe_delete_and_redelete_404(ctx):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    url=f"/api/v1/products/{p}/recipe/{m}"
    api(ctx,"PUT",url,payload={"quantity_per_unit":"0.250"})
    assert api(ctx,"DELETE",url).status_code==204
    assert api(ctx,"DELETE",url).status_code==404
    assert api(ctx,"GET",f"/api/v1/products/{p}/recipe").json()["items"]==[]


def test_quantity_30_times_quarter_meter_yields_7_5(ctx):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    api(ctx,"PUT",f"/api/v1/products/{p}/recipe/{m}",payload={"quantity_per_unit":"0.250"})
    r=api(ctx,"GET",f"/api/v1/products/{p}/material-requirements?quantity=30",headers="operator_a")
    assert r.status_code==200,r.text
    j=r.json();assert j["feasible"] is True and j["recipe_configured"] is True
    assert j["materials"][0]["required"]=="7.500" and j["materials"][0]["shortage"]=="0.000"


def test_insufficient_stock_and_then_update_recalculates(ctx):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    api(ctx,"PUT",f"/api/v1/products/{p}/recipe/{m}",payload={"quantity_per_unit":"0.500"})
    url=f"/api/v1/products/{p}/material-requirements?quantity=30"
    first=api(ctx,"GET",url).json()
    assert first["feasible"] is False and first["materials"][0]["shortage"]=="5.000"
    api(ctx,"PUT",BASE+"/"+m+"/stock",payload={"quantity_available":"20.000"})
    second=api(ctx,"GET",url).json()
    assert second["feasible"] is True and second["materials"][0]["shortage"]=="0.000"


def test_quantity_rounds_up_to_three_decimals(ctx):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    api(ctx,"PUT",f"/api/v1/products/{p}/recipe/{m}",payload={"quantity_per_unit":"0.333"})
    r=api(ctx,"GET",f"/api/v1/products/{p}/material-requirements?quantity=0.333")
    assert r.status_code==200 and r.json()["materials"][0]["required"]=="0.111"


def test_empty_recipe_does_not_look_feasible(ctx):
    p=new_product(ctx).json()["id"]
    r=api(ctx,"GET",f"/api/v1/products/{p}/material-requirements?quantity=30")
    assert r.status_code==200
    assert r.json()["recipe_configured"] is False and r.json()["feasible"] is False


def test_deactivate_material_makes_recipe_infeasible(ctx):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    api(ctx,"PUT",f"/api/v1/products/{p}/recipe/{m}",payload={"quantity_per_unit":"0.200"})
    assert api(ctx,"POST",BASE+"/"+m+"/deactivate").status_code==200
    resp=api(ctx,"GET",f"/api/v1/products/{p}/material-requirements?quantity=2").json()
    assert resp["feasible"] is False and resp["materials"][0]["sufficient"] is False
    assert api(ctx,"GET",BASE).json()==[]
    assert len(api(ctx,"GET",BASE+"?include_inactive=true").json())==1


def test_cannot_add_inactive_material_to_new_recipe(ctx):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    api(ctx,"POST",BASE+"/"+m+"/deactivate")
    assert api(ctx,"PUT",f"/api/v1/products/{p}/recipe/{m}",payload={"quantity_per_unit":"1"}).status_code==409


def test_cross_tenant_material_read_and_stock_404(ctx):
    foreign=new_material(ctx,headers="owner_b").json()["id"]
    assert api(ctx,"GET",BASE+"/"+foreign).status_code==404
    assert api(ctx,"PUT",BASE+"/"+foreign+"/stock",payload={"quantity_available":"999"}).status_code==404
    assert api(ctx,"POST",BASE+"/"+foreign+"/deactivate").status_code==404
    with ctx["factory"]() as db:
        assert db.get(Material,UUID(foreign)).quantity_available==Decimal("10.000")


def test_cross_tenant_product_rejected_for_recipe_and_calculator(ctx):
    other_product=new_product(ctx,headers="owner_b").json()["id"]
    own_material=new_material(ctx).json()["id"]
    assert api(ctx,"PUT",f"/api/v1/products/{other_product}/recipe/{own_material}",payload={"quantity_per_unit":"1"}).status_code==404
    assert api(ctx,"GET",f"/api/v1/products/{other_product}/material-requirements?quantity=1").status_code==404


def test_cross_tenant_material_rejected_for_recipe(ctx):
    product=new_product(ctx).json()["id"]
    foreign=new_material(ctx,headers="owner_b").json()["id"]
    assert api(ctx,"PUT",f"/api/v1/products/{product}/recipe/{foreign}",payload={"quantity_per_unit":"1"}).status_code==404
    assert api(ctx,"GET",f"/api/v1/products/{product}/recipe").json()["items"]==[]


def test_product_materials_db_fk_rejects_cross_tenant(ctx):
    p=new_product(ctx).json()["id"]
    foreign=new_material(ctx,headers="owner_b").json()["id"]
    with ctx["factory"]() as db:
        db.add(ProductMaterial(product_id=UUID(p),material_id=UUID(foreign),organization_id=ctx["a"], quantity_per_unit=Decimal("1.000")))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


@pytest.mark.parametrize("path,body",[
    (BASE,material_payload()),
    (BASE+"/"+str(uuid4())+"/stock",{"quantity_available":"12"}),
])
def test_operator_cannot_write_materials(ctx,path,body):
    method="POST" if path==BASE else "PUT"
    assert api(ctx,method,path,headers="operator_a",payload=body).status_code==403


def test_operator_cannot_edit_recipe(ctx):
    p=new_product(ctx).json()["id"]
    m=new_material(ctx).json()["id"]
    assert api(ctx,"PUT",f"/api/v1/products/{p}/recipe/{m}",headers="operator_a",payload={"quantity_per_unit":"1"}).status_code==403


def test_missing_token_returns_401(ctx):
    assert ctx["client"].get(BASE).status_code==401
    assert ctx["client"].get("/api/v1/products/"+str(uuid4())+"/recipe").status_code==401


def test_malicious_org_field_rejected_and_header_ignored(ctx):
    bad=new_material(ctx,organization_id=str(ctx["b"]))
    assert bad.status_code==422
    response=ctx["client"].get(BASE,headers={**ctx["owner_a"],"X-Organization-ID":str(ctx["b"])})
    assert response.status_code==200 and response.json()==[]


@pytest.mark.parametrize("quantity",["0","-1","oops","1.00001"])
def test_bad_product_quantity_422(ctx,quantity):
    p=new_product(ctx).json()["id"]
    assert api(ctx,"GET",f"/api/v1/products/{p}/material-requirements?quantity={quantity}").status_code==422


def test_missing_and_illformed_product_404_422(ctx):
    assert api(ctx,"GET",f"/api/v1/products/{uuid4()}/recipe").status_code==404
    assert api(ctx,"GET",f"/api/v1/products/not-a-uuid/recipe").status_code==422


def test_material_listing_pagination(ctx):
    new_material(ctx)
    new_material(ctx,sku="OTRO-01",name="Otro material")
    assert len(api(ctx,"GET",BASE+"?limit=1").json())==1
    assert len(api(ctx,"GET",BASE+"?limit=1&offset=1").json())==1
    assert api(ctx,"GET",BASE+"?limit=101").status_code==422


def test_openapi_documents_rf006(ctx):
    paths=ctx["client"].get("/openapi.json").json()["paths"]
    for path in (BASE,BASE+"/{material_id}/stock","/api/v1/products/{product_id}/recipe", "/api/v1/products/{product_id}/material-requirements"):
        assert path in paths


def test_recipe_edit_recalculates_requirements(ctx):
    p = new_product(ctx).json()["id"]
    m = new_material(ctx).json()["id"]
    recipe_url = f"/api/v1/products/{p}/recipe/{m}"
    needs_url = f"/api/v1/products/{p}/material-requirements?quantity=30"
    assert api(ctx, "PUT", recipe_url, payload={"quantity_per_unit": "0.250"}).status_code == 200
    before = api(ctx, "GET", needs_url).json()
    assert before["feasible"] is True
    assert before["materials"][0]["required"] == "7.500"
    assert api(ctx, "PUT", recipe_url, payload={"quantity_per_unit": "0.500"}).status_code == 200
    after = api(ctx, "GET", needs_url).json()
    assert after["feasible"] is False
    assert after["materials"][0]["required"] == "15.000"
    assert after["materials"][0]["shortage"] == "5.000"


def test_multiple_materials_all_required(ctx):
    p = new_product(ctx).json()["id"]
    tela = new_material(ctx).json()["id"]
    tinta = new_material(ctx, sku="TINTA-01",name="Tinta negra",unit="litro",quantity_available="2.000").json()["id"]
    assert api(ctx, "PUT", f"/api/v1/products/{p}/recipe/{tela}", payload={"quantity_per_unit":"0.200"}).status_code == 200
    assert api(ctx, "PUT", f"/api/v1/products/{p}/recipe/{tinta}", payload={"quantity_per_unit":"0.150"}).status_code == 200
    r=api(ctx,"GET",f"/api/v1/products/{p}/material-requirements?quantity=20").json()
    assert len(r["materials"]) == 2
    assert r["feasible"] is False
    by_sku = {m["sku"]:m for m in r["materials"]}
    assert by_sku["TEL-100"]["required"] == "4.000"
    assert by_sku["TINTA-01"]["required"] == "3.000"
    assert by_sku["TINTA-01"]["shortage"] == "1.000"
