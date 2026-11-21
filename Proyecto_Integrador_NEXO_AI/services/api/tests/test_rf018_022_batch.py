"""RF-018 a RF-022: aceptación y auditoría sobre API real de pruebas."""
from datetime import date, timedelta
from uuid import UUID, uuid4
from sqlalchemy import func, select
from test_quotes import ctx, order, product, prepared, payload, create, tax, request
from app.modules.orders.model import Order
from app.modules.decisions.model import DecisionRecommendation, AuditEvent

ROOT='/api/v1'
TOMORROW=(date.today()+timedelta(days=10)).isoformat()
START=(date.today()+timedelta(days=1)).isoformat()


def propose(ctx,o,p,*,key=None,who='owner',**scenario):
    data={'order_id':o['id'],'product_id':p['id'],'quantity':'3.000',
          'delivery_date':TOMORROW,'start_date':START}
    data.update(scenario)
    return ctx['client'].post(ROOT+'/decisions/recommend',headers={**ctx['auth'][who],
       'Idempotency-Key':key or ('rec-'+uuid4().hex)},json={'scenario':data})


def confirm(ctx, rec, *, key=None, expected=0, reason=None,who='owner',ack=True,word='CONFIRMAR'):
    return ctx['client'].post(ROOT+'/decisions/'+rec['id']+'/confirm',headers={**ctx['auth'][who],
        'Idempotency-Key':key or ('conf-'+uuid4().hex)},json={
        'confirmation':word,'expected_review_revision':expected,
        'acknowledge_estimates':ack,'exception_reason':reason})


def test_proposal_no_order_write(ctx):
    o,p=order(ctx),product(ctx)
    rec=propose(ctx,o,p)
    assert rec.status_code==201,rec.text
    r=rec.json()
    assert r['status']=='proposed' and r['result']['changes_applied'] is False
    assert r['result']['explanation']['status']=='not_evaluable'
    assert ctx['client'].get(ROOT+'/orders/'+o['id'],headers=ctx['auth']['owner']).json()['status']=='draft'
    listed=ctx['client'].get(ROOT+'/decisions',headers=ctx['auth']['owner'],params={'order_id':o['id']}).json()
    assert listed[0]['id']==r['id']
    assert listed[0]['engine_version']=='rf017-v1'


def test_confirmation_requires_explicit_owner_and_reason(ctx):
    o,p=order(ctx),product(ctx)
    rec=propose(ctx,o,p).json()
    assert confirm(ctx,rec,who='operator').status_code==403
    assert confirm(ctx,rec,word='CONFIRMO').status_code==422
    assert confirm(ctx,rec,ack=False).status_code==422
    assert confirm(ctx,rec).status_code==409
    assert ctx['client'].get(ROOT+'/orders/'+o['id'],headers=ctx['auth']['owner']).json()['status']=='draft'
    ok=confirm(ctx,rec,reason='Sin recurso ni receta, autorizo excepción informada')
    assert ok.status_code==200,ok.text
    assert ok.json()['status']=='applied' and ok.json()['applied_order_status']=='confirmed'
    changed=ctx['client'].get(ROOT+'/orders/'+o['id'],headers=ctx['auth']['owner']).json()
    assert changed['status']=='confirmed' and changed['reviewed_quantity']=='3.000'
    assert changed['reviewed_due_date']==TOMORROW
    assert len(ctx['client'].get(ROOT+'/orders/'+o['id']+'/history',headers=ctx['auth']['owner']).json())==1


def test_idempotent_retries_and_payload_conflicts(ctx):
    o,p=order(ctx),product(ctx)
    key='rec-'+uuid4().hex
    a=propose(ctx,o,p,key=key)
    b=propose(ctx,o,p,key=key)
    assert a.status_code==201 and b.status_code==201, (a.text,b.text)
    assert a.json()['id']==b.json()['id']
    assert propose(ctx,o,p,key=key,quantity='4.000').status_code==409
    id=a.json()['id']
    ck='confirm-'+uuid4().hex
    r=confirm(ctx,{'id':id},key=ck,reason='Acepto incertidumbre y posible inventario insuficiente')
    assert r.status_code==200,r.text
    same=confirm(ctx,{'id':id},key=ck,reason='Acepto incertidumbre y posible inventario insuficiente')
    assert same.status_code==200 and same.json()['id']==id
    changed=confirm(ctx,{'id':id},key=ck,reason='Texto excepcional distinto')
    assert changed.status_code==409
    with ctx['factory']() as db:
        assert db.scalar(select(func.count()).select_from(DecisionRecommendation))==1
        assert db.get(Order,UUID(o['id'])).review_revision==1


def test_idempotency_header_required_and_safe(ctx):
    o,p=order(ctx),product(ctx)
    scenario={'scenario':{'order_id':o['id'],'product_id':p['id'],
             'quantity':'3.000','delivery_date':TOMORROW,'start_date':START}}
    c=ctx['client']
    assert c.post(ROOT+'/decisions/recommend',headers=ctx['auth']['owner'],json=scenario).status_code==422
    assert c.post(ROOT+'/decisions/recommend',headers={**ctx['auth']['owner'],'Idempotency-Key':'a'},json=scenario).status_code==422
    assert c.post(ROOT+'/decisions/recommend',headers={**ctx['auth']['owner'],'Idempotency-Key':'../unsafe'},json=scenario).status_code==422


def test_changed_order_does_not_apply_stale_recommendation(ctx):
    o,p=order(ctx),product(ctx)
    rec=propose(ctx,o,p).json()
    updated=ctx['client'].patch(ROOT+'/orders/'+o['id'],headers=ctx['auth']['owner'],json={'raw_text':'Reemplazo'});assert updated.status_code==200
    res=confirm(ctx,rec,reason='Justificación de prueba sobre datos insuficientes')
    assert res.status_code==409
    assert ctx['client'].get(ROOT+'/orders/'+o['id'],headers=ctx['auth']['owner']).json()['status']=='draft'


def test_hypothetical_price_override_cannot_change_real_price(ctx):
    o,p=order(ctx),product(ctx)
    rec=propose(ctx,o,p,unit_price_mxn='0.01').json()
    assert confirm(ctx,rec,reason='Excepción de datos incompletos').status_code==409
    real=ctx['client'].get(ROOT+'/products/'+p['id'],headers=ctx['auth']['owner']).json()
    assert real['price_mxn']=='25.50'


def test_cross_tenant_and_operator_blocked(ctx):
    o,p=order(ctx),product(ctx)
    rec=propose(ctx,o,p).json()
    assert propose(ctx,o,p,who='operator').status_code==403
    assert ctx['client'].get(ROOT+'/decisions/'+rec['id'],headers=ctx['auth']['foreign']).status_code==404
    assert ctx['client'].post(ROOT+'/decisions/'+rec['id']+'/confirm',headers={**ctx['auth']['foreign'],'Idempotency-Key':'foreign-01234567'},json={
      'confirmation':'CONFIRMAR','expected_review_revision':0,'acknowledge_estimates':True}).status_code==404
    assert ctx['client'].get(ROOT+'/audit/events',headers=ctx['auth']['operator']).status_code==403


def test_audit_creation_update_review_confirm_quote(ctx):
    o,p=prepared(ctx)
    assert ctx['client'].patch(ROOT+'/orders/'+o['id'],headers=ctx['auth']['owner'],json={'raw_text':'Pedido modificado'}).status_code==200
    rev=ctx['client'].put(ROOT+'/orders/'+o['id']+'/review',headers=ctx['auth']['owner'],json={
       'quantity':'3.000','due_date':TOMORROW,'expected_revision':1})
    assert rev.status_code==200,rev.text
    assert ctx['client'].post(ROOT+'/orders/'+o['id']+'/confirm',headers=ctx['auth']['owner'],json={
       'expected_revision':2}).status_code==200
    q=create(ctx,payload(o,p,discount='0.00')).json()
    assert request(ctx,'/'+q['id']+'/approve',method='POST').status_code==200
    a=ctx['client'].get(ROOT+'/audit/events',headers=ctx['auth']['owner'],params={'limit':100})
    assert a.status_code==200,a.text
    data=a.json(); actions={e['action'] for e in data['items']}
    assert {'order.created','order.updated','order.reviewed','order.confirmed',
            'quote.created','quote.approved'}.issubset(actions)
    for e in data['items']:
        assert e['actor_user_id']==str(ctx['ids']['owner'])
        assert e['organization_id']==str(ctx['ids']['a'])
    assert ctx['client'].patch(ROOT+'/audit/events',headers=ctx['auth']['owner']).status_code==405
    assert ctx['client'].delete(ROOT+'/audit/events',headers=ctx['auth']['owner']).status_code==405


def test_operating_panel_matches_backend(ctx):
    o,p=order(ctx),product(ctx)
    c=ctx['client']; h=ctx['auth']['owner']
    summ=c.get(ROOT+'/operations/summary',headers=h).json()
    assert summ['open_orders']==1 and summ['due_soon']==0 and summ['overdue']==0
    assert summ['counts_by_status']['draft']==1
    assert 'capacity_caveat' in summ and 'No hay recursos' in summ['alerts'][0]['message']
    r=c.get(ROOT+'/operations/summary',headers=h,params={'days':7})
    assert r.status_code==200 and r.json()['open_orders']==1
    assert c.get(ROOT+'/operations/summary',headers=h,params={'days':0}).status_code==422
    assert c.get(ROOT+'/operations/summary').status_code==401
    assert c.get(ROOT+'/operations/summary',headers=ctx['auth']['foreign']).json()['open_orders']==0


def test_pdf_repeated_issue_same_doc(ctx):
    from datetime import timedelta
    o,p=prepared(ctx)
    q=create(ctx,payload(o,p,discount='0.00')).json()
    assert request(ctx,'/'+q['id']+'/approve',method='POST').status_code==200
    expires=(date.today()+timedelta(days=40)).isoformat()
    a=request(ctx,'/'+q['id']+'/document',method='POST',json={'valid_until':expires})
    b=request(ctx,'/'+q['id']+'/document',method='POST',json={'valid_until':expires})
    assert a.status_code==201 and b.status_code==201,(a.text,b.text)
    assert a.json()['folio']==b.json()['folio'] and a.json()['sha256']==b.json()['sha256']


def test_order_creation_idempotent_under_retry(ctx):
    key='order-'+uuid4().hex
    headers={**ctx['auth']['owner'],'Idempotency-Key':key}
    c=ctx['client']
    first=c.post(ROOT+'/orders',headers=headers,json={'raw_text':'Sin duplicados'})
    second=c.post(ROOT+'/orders',headers=headers,json={'raw_text':'Sin duplicados'})
    assert first.status_code==second.status_code==201
    assert first.json()['id']==second.json()['id']
    assert c.post(ROOT+'/orders',headers=headers,json={'raw_text':'Pedido diferente'}).status_code==409
    with ctx['factory']() as db:
        assert db.scalar(select(func.count()).select_from(Order).where(
            Order.organization_id==ctx['ids']['a']))==1


def test_quote_creation_idempotent_under_retry(ctx):
    from app.modules.quotes.model import Quote
    o,p=prepared(ctx)
    key='quote-'+uuid4().hex
    headers={**ctx['auth']['owner'],'Idempotency-Key':key}
    body=payload(o,p,discount='0.00')
    c=ctx['client']
    one=c.post(ROOT+'/quotes',headers=headers,json=body)
    two=c.post(ROOT+'/quotes',headers=headers,json=body)
    assert one.status_code==two.status_code==201
    assert one.json()['id']==two.json()['id'] and one.json()['version']==1
    assert c.post(ROOT+'/quotes',headers=headers,json={**body,'discount_percent':'1.00'}).status_code==409
    with ctx['factory']() as db:
        assert db.scalar(select(func.count()).select_from(Quote).where(
            Quote.organization_id==ctx['ids']['a']))==1
