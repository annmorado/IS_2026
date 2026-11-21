"""RF-015: la web consulta cotizaciones aprobadas por móvil, sin recaptura."""
from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select, func

from test_quotes import ctx, product, order, tax, payload, create, request, PASSWORD
from app.modules.orders.model import Order
from app.modules.quotes.model import Quote
from app.modules.quote_documents.model import QuoteDocument

BASE='/api/v1'

def another_web_session(ctx, role='owner'):
    ids=ctx['ids']
    org=ids['b'] if role=='foreign' else ids['a']
    r=ctx['client'].post(BASE+'/auth/login',json={
        'organization_id':str(org),'email':role+'@rf013.example','password':PASSWORD})
    assert r.status_code==200,r.text
    assert r.json()['access_token']!=ctx['auth'][role]['Authorization'].split(' ',1)[1]
    return {'Authorization':'Bearer '+r.json()['access_token']}

def search(ctx,headers,**params):
    return ctx['client'].get(BASE+'/orders/search',headers=headers,params=params)

def test_mobile_create_visible_in_web_without_duplicate_record(ctx):
    web=another_web_session(ctx)
    mobile=ctx['auth']['owner']
    assert search(ctx,web,q='RF015 unique').json()['total']==0
    r=ctx['client'].post(BASE+'/orders',headers=mobile,json={'raw_text':'RF015 unique mobile order'})
    assert r.status_code==201,r.text
    oid=r.json()['id']
    found=search(ctx,web,q='RF015 unique')
    assert found.status_code==200,found.text
    assert found.json()['total']==1 and found.json()['items'][0]['id']==oid
    assert ctx['client'].get(BASE+'/orders/'+oid,headers=web).json()['id']==oid
    with ctx['factory']() as db:
        assert db.scalar(select(func.count()).select_from(Order).where(Order.organization_id==ctx['ids']['a']))==1


def test_mobile_change_reflected_in_web_on_next_request(ctx):
    web=another_web_session(ctx)
    o=order(ctx)
    oid=o['id']
    assert ctx['client'].get(BASE+'/orders/'+oid,headers=web).json()['raw_text']=='Pedido RF-013'
    r=ctx['client'].patch(BASE+'/orders/'+oid,headers=ctx['auth']['owner'],json={'raw_text':'Pedido actualizado desde iPhone'})
    assert r.status_code==200,r.text
    assert ctx['client'].get(BASE+'/orders/'+oid,headers=web).json()['raw_text']=='Pedido actualizado desde iPhone'
    assert search(ctx,web,q='actualizado desde iPhone').json()['items'][0]['id']==oid


def test_mobile_status_transition_reflected_in_web_history(ctx):
    web=another_web_session(ctx)
    o=order(ctx)
    r=ctx['client'].post(BASE+'/orders/'+o['id']+'/status',headers=ctx['auth']['owner'],
          json={'expected_status':'draft','to_status':'pending'})
    assert r.status_code==200,r.text
    found=search(ctx,web,status='pending')
    assert found.json()['total']==1 and found.json()['items'][0]['id']==o['id']
    events=ctx['client'].get(BASE+'/orders/'+o['id']+'/history',headers=web)
    assert events.status_code==200,events.text
    assert len(events.json())==1 and events.json()[0]['to_status']=='pending'


def test_mobile_quote_approved_pdf_visible_to_web_no_recapture(ctx):
    web=another_web_session(ctx)
    o=order(ctx);p=product(ctx)
    assert tax(ctx,'16.00').status_code==200
    body=payload(o,p,discount='0.00')
    q=create(ctx,body).json()
    assert request(ctx,'/'+q['id']+'/approve',method='POST').status_code==200
    expiry=(datetime.now(ZoneInfo('America/Mexico_City')).date()+timedelta(days=20)).isoformat()
    document=request(ctx,'/'+q['id']+'/document',method='POST',json={'valid_until':expiry})
    assert document.status_code==201,document.text
    response=ctx['client'].get(BASE+'/quotes',headers=web,params={'order_id':o['id']})
    assert response.status_code==200,response.text
    assert len(response.json())==1
    assert response.json()[0]['id']==q['id'] and response.json()[0]['status']=='approved'
    assert response.json()[0]['total']=='88.74'
    assert ctx['client'].get(BASE+'/quotes/'+q['id']+'/document',headers=web).json()['folio']==document.json()['folio']
    pdf=ctx['client'].get(BASE+'/quotes/'+q['id']+'/pdf',headers=web)
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    with ctx['factory']() as db:
        assert db.scalar(select(func.count()).select_from(Quote).where(Quote.organization_id==ctx['ids']['a']))==1
        assert db.scalar(select(func.count()).select_from(QuoteDocument).where(QuoteDocument.organization_id==ctx['ids']['a']))==1


def test_web_refresh_sees_new_quote_version_not_overwriting_first(ctx):
    web=another_web_session(ctx)
    o=order(ctx);p=product(ctx);assert tax(ctx,'0.00').status_code==200
    first=create(ctx,payload(o,p,discount='0.00')).json()
    assert ctx['client'].get(BASE+'/quotes',headers=web,params={'order_id':o['id']}).json()[0]['version']==1
    second=create(ctx,payload(o,p,discount='0.00')).json()
    refreshed=ctx['client'].get(BASE+'/quotes',headers=web,params={'order_id':o['id']}).json()
    assert len(refreshed)==2 and [x['version'] for x in refreshed]==[2,1]
    assert refreshed[0]['id']==second['id'] and refreshed[1]['id']==first['id']


def test_web_isolated_from_other_organization(ctx):
    foreign=another_web_session(ctx,'foreign')
    a=order(ctx);p=product(ctx);assert tax(ctx,'0.00').status_code==200
    q=create(ctx,payload(a,p,discount='0.00')).json()
    assert search(ctx,foreign,q='Pedido RF-013').json()['total']==0
    assert ctx['client'].get(BASE+'/orders/'+a['id'],headers=foreign).status_code==404
    assert ctx['client'].get(BASE+'/quotes',headers=foreign,params={'order_id':a['id']}).status_code==404
    assert ctx['client'].get(BASE+'/quotes/'+q['id'],headers=foreign).status_code==404
    assert ctx['client'].get(BASE+'/quotes/'+q['id']+'/pdf',headers=foreign).status_code==404


def test_revoked_web_session_rejected_mobile_unchanged(ctx):
    web=another_web_session(ctx)
    o=order(ctx)
    assert ctx['client'].post(BASE+'/auth/logout',headers=web).status_code==200
    assert ctx['client'].get(BASE+'/orders/search',headers=web).status_code==401
    assert ctx['client'].get(BASE+'/orders/'+o['id'],headers=ctx['auth']['owner']).status_code==200


def test_web_requires_authentication(ctx):
    assert ctx['client'].get(BASE+'/orders/search').status_code==401
    assert ctx['client'].get(BASE+'/quotes',params={'order_id':str(uuid4())}).status_code==401
