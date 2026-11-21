"""RF-014: PDF comercial inmutable, folio unico, vigencia, RBAC y aislamiento."""
from datetime import datetime,timedelta
from hashlib import sha256
from io import BytesIO
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from pypdf import PdfReader
from sqlalchemy import select,func

# Reutiliza la misma fixture PostgreSQL-compatible RF-013, sin redefinir usuarios.
from test_quotes import ctx,prepared,create,payload,request,product,order,tax
from app.modules.quotes.model import Quote
from app.modules.quote_documents.model import QuoteDocument
from app.modules.organizations.model import Organization

BASE='/api/v1/quotes'
TODAY=lambda: datetime.now(ZoneInfo('America/Mexico_City')).date()
def future(n=10):return (TODAY()+timedelta(days=n)).isoformat()

def approved(ctx):
    o,p=prepared(ctx)
    q=create(ctx,payload(o,p,discount='10.00')).json()
    resp=request(ctx,'/'+q['id']+'/approve',method='POST')
    assert resp.status_code==200,resp.text
    return o,p,resp.json()

def issue(ctx,q,until=None,who='owner'):
    return request(ctx,f"/{q['id']}/document",who,'POST',{'valid_until':until or future()})

def pdf(ctx,q,who='owner'):
    return request(ctx,f"/{q['id']}/pdf",who)


def test_document_requires_approved_quote(ctx):
    o,p=prepared(ctx)
    q=create(ctx,payload(o,p)).json()
    assert issue(ctx,q).status_code==409
    assert request(ctx,f"/{q['id']}/document").status_code==404
    assert pdf(ctx,q).status_code==404


def test_document_contains_all_required_fields(ctx):
    o,p,q=approved(ctx)
    response=issue(ctx,q)
    assert response.status_code==201,response.text
    d=response.json()
    assert d['quote_id']==q['id'] and d['order_id']==o['id']
    assert d['quote_version']==1 and d['valid_until']==future()
    assert d['folio'].startswith('NEXO-') and d['size_bytes']>1000
    assert d['sha256'] and d['download_path']==f"/quotes/{q['id']}/pdf"
    content=pdf(ctx,q)
    assert content.status_code==200 and content.content.startswith(b'%PDF-')
    assert content.headers['content-type']=='application/pdf'
    assert 'attachment' in content.headers['content-disposition']
    assert 'no-store' in content.headers['cache-control']
    assert content.headers['x-content-type-options']=='nosniff'
    assert sha256(content.content).hexdigest()==d['sha256']
    assert len(content.content)==d['size_bytes']
    reader=PdfReader(BytesIO(content.content))
    text=' '.join(page.extract_text() or '' for page in reader.pages)
    for expected in [d['folio'],'RF013 A',o['id'],q['id'],'25.50','76.50',
                     '7.65','68.85','11.02','79.87',future(),'Articulo de prueba','MXN','CFDI']:
        assert expected in text,expected
    assert '9.25' not in text  # El costo interno nunca se expone al cliente.


def test_document_idempotent_same_validity(ctx):
    _,_,q=approved(ctx)
    first=issue(ctx,q); second=issue(ctx,q)
    assert first.status_code==201 and second.status_code==201
    assert first.json()==second.json()
    assert request(ctx,f"/{q['id']}/document").json()==first.json()
    assert pdf(ctx,q).content==pdf(ctx,q).content
    with ctx['factory']() as db:
        assert db.scalar(select(func.count()).select_from(QuoteDocument))==1


def test_document_cannot_change_validity_after_issue(ctx):
    _,_,q=approved(ctx)
    assert issue(ctx,q).status_code==201
    assert issue(ctx,q,until=future(11)).status_code==409


@pytest.mark.parametrize('days',[-20,-1,366,1000])
def test_invalid_business_validity(ctx,days):
    _,_,q=approved(ctx)
    assert issue(ctx,q,until=future(days)).status_code==422


def test_today_and_one_year_allowed(ctx):
    _,_,q=approved(ctx)
    assert issue(ctx,q,until=future(0)).status_code==201
    _,_,p=approved(ctx)
    assert issue(ctx,p,until=future(365)).status_code==201


@pytest.mark.parametrize('body',[{'valid_until':'mal'}, {'valid_until':None},
    {'valid_until':'2026-02-30'}, {'valid_until':future(),'folio':'fake'}, {}])
def test_invalid_contract(ctx,body):
    _,_,q=approved(ctx)
    resp=request(ctx,f"/{q['id']}/document",method='POST',json=body)
    assert resp.status_code==422


def test_cross_tenant_cannot_generate_read_or_download(ctx):
    _,_,q=approved(ctx)
    assert issue(ctx,q,who='foreign').status_code==404
    assert request(ctx,f"/{q['id']}/document",'foreign').status_code==404
    assert pdf(ctx,q,'foreign').status_code==404
    assert issue(ctx,q).status_code==201
    assert pdf(ctx,q,'foreign').status_code==404
    assert request(ctx,f"/{q['id']}/document",'foreign').status_code==404


def test_operator_may_create_and_download_approved_doc(ctx):
    _,_,q=approved(ctx)
    assert issue(ctx,q,who='operator').status_code==201
    assert pdf(ctx,q,'operator').status_code==200


def test_unauthenticated_rejected(ctx):
    _,_,q=approved(ctx)
    assert ctx['client'].post(BASE+f"/{q['id']}/document",json={'valid_until':future()}).status_code==401
    assert ctx['client'].get(BASE+f"/{q['id']}/pdf").status_code==401
    assert ctx['client'].get(BASE+f"/{q['id']}/document").status_code==401


def test_revoked_token_rejected(ctx):
    _,_,q=approved(ctx)
    assert issue(ctx,q).status_code==201
    assert ctx['client'].post('/api/v1/auth/logout',headers=ctx['auth']['operator']).status_code==200
    assert pdf(ctx,q,'operator').status_code==401


def test_persisted_pdf_immutable_after_catalog_and_org_changes(ctx):
    o,p,q=approved(ctx)
    d=issue(ctx,q).json()
    before=pdf(ctx,q).content
    changed=ctx['client'].patch('/api/v1/products/'+p['id'],headers=ctx['auth']['owner'],
        json={'price_mxn':'999.99'})
    assert changed.status_code==200
    with ctx['factory']() as db:
        org=db.get(Organization,ctx['ids']['a']);org.name='Nuevo nombre';db.commit()
    after=pdf(ctx,q).content
    assert before==after and sha256(after).hexdigest()==d['sha256']


def test_two_quotes_get_distinct_incremental_folios(ctx):
    o,p,q=approved(ctx)
    second_order=order(ctx)
    second=create(ctx,payload(second_order,p)).json()
    approved2=request(ctx,'/'+second['id']+'/approve',method='POST').json()
    first=issue(ctx,q).json(); second=issue(ctx,approved2).json()
    assert first['folio']!=second['folio']
    assert first['folio'].endswith('000001')
    assert second['folio'].endswith('000002')


def test_independent_tenant_folio_and_document(ctx):
    _,_,q=approved(ctx)
    doc=issue(ctx,q).json()
    assert tax(ctx,who='foreign').status_code==200
    foreign_order=order(ctx,'foreign');foreign_product=product(ctx,'foreign')
    another=create(ctx,payload(foreign_order,foreign_product),who='foreign').json()
    approved_foreign=request(ctx,'/'+another['id']+'/approve','foreign','POST').json()
    b=issue(ctx,approved_foreign,who='foreign').json()
    assert doc['folio']!=b['folio']
    assert b['folio'].endswith('000001')
    assert pdf(ctx,approved_foreign,'foreign').status_code==200
    assert pdf(ctx,approved_foreign).status_code==404


def test_multiline_pdf_breaks_into_multiple_pages(ctx):
    # 30 partidas => PDF multipagina y repeticion de encabezados.
    o,p=prepared(ctx)
    products=[p]+[product(ctx,sku=f'LONG-{i:03}',price='1.00') for i in range(29)]
    q=create(ctx,{'order_id':o['id'],'discount_percent':'0.00',
        'items':[{'product_id':x['id'],'quantity':'1.000'} for x in products]}).json()
    q=request(ctx,'/'+q['id']+'/approve',method='POST').json()
    assert issue(ctx,q).status_code==201
    reader=PdfReader(BytesIO(pdf(ctx,q).content))
    assert len(reader.pages)>=2
    text=' '.join(page.extract_text() or '' for page in reader.pages)
    assert 'LONG-028' in text and 'TOTAL MXN' in text


def test_pdf_metadata_is_not_binary_leak(ctx):
    _,_,q=approved(ctx)
    d=issue(ctx,q).json()
    assert 'pdf_bytes' not in d and 'authorization' not in str(d).lower()
    assert request(ctx,f"/{q['id']}/document").headers['content-type'].startswith('application/json')
