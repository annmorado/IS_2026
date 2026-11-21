"""RF-023..027: security, tenant scoping, current state and full exports."""
from datetime import date,timedelta
from decimal import Decimal
from uuid import UUID,uuid4
import csv,io
from sqlalchemy import select,func
from test_quotes import ctx,order,product,prepared,payload,create,request
from app.modules.auth.model import User
from app.modules.auth.security import hash_password
from app.modules.collaborators.model import CollaboratorInvite
from app.modules.purchasing.model import Supplier,PurchaseRequest
from app.modules.notifications.model import NotificationPreference,BusinessNotification
from app.modules.scheduling.model import ResourceAllocation

API='/api/v1'
TODAY=date.today()
FUTURE=(TODAY+timedelta(days=3)).isoformat()


def post(ctx,path,body,who='owner'):
    return ctx['client'].post(API+path,json=body,headers=ctx['auth'][who])

def get(ctx,path,who='owner'):
    return ctx['client'].get(API+path,headers=ctx['auth'][who])


def setup_material(ctx):
    m=post(ctx,'/materials',{'sku':'material-'+uuid4().hex[:6],'name':'Tela','unit':'kg'})
    assert m.status_code==201,m.text
    return m.json()


def setup_resource(ctx):
    r=post(ctx,'/capacity/resources',{'code':'resource-'+uuid4().hex[:6], 'name':'Maquina','unit':'pieza',
                       'daily_capacity':'5.000','workdays':[0,1,2,3,4,5,6]})
    assert r.status_code==201,r.text
    return r.json()


def confirm_order(ctx,o,quantity='4.000',due=FUTURE):
    c=ctx['client'];h=ctx['auth']['owner']
    a=c.put(API+'/orders/'+o['id']+'/review',headers=h,json={'quantity':quantity,'due_date':due,'expected_revision':0})
    assert a.status_code==200,a.text
    b=c.post(API+'/orders/'+o['id']+'/confirm',headers=h,json={'expected_revision':1})
    assert b.status_code==200,b.text


def test_rf023_one_time_invitation_and_suspension(ctx):
    p=['orders.read','notifications.read']
    invite=post(ctx,'/collaborators/invitations',{'email':'helper@example.com','permissions':p,'expires_hours':4})
    assert invite.status_code==201,invite.text
    token=invite.json()['token'];assert len(token)>32
    assert 'token' not in str(get(ctx,'/collaborators/users').json())
    accepted=ctx['client'].post(API+'/collaborators/invitations/accept',json={'token':token,'password':'StrongPass#2026Accepted'})
    assert accepted.status_code==201,accepted.text
    person=accepted.json();assert sorted(person['permissions'])==sorted(p)
    assert ctx['client'].post(API+'/collaborators/invitations/accept',json={'token':token,'password':'StrongPass#2026Accepted'}).status_code==410
    login=ctx['client'].post(API+'/auth/login',json={'organization_id':str(ctx['ids']['a']),'email':'helper@example.com','password':'StrongPass#2026Accepted'})
    assert login.status_code==200,login.text
    h={'Authorization':'Bearer '+login.json()['access_token']}
    assert ctx['client'].get(API+'/orders/search',headers=h).status_code==200
    assert ctx['client'].post(API+'/orders',headers=h,json={'raw_text':'No permission'}).status_code==403
    update=ctx['client'].patch(API+'/collaborators/users/'+person['id']+'/permissions',headers=ctx['auth']['owner'],json={'permissions':['orders.read','orders.write']})
    assert update.status_code==200,update.text
    assert ctx['client'].post(API+'/orders',headers=h,json={'raw_text':'Now permitted'}).status_code==201
    suspend=ctx['client'].patch(API+'/collaborators/users/'+person['id']+'/suspension',headers=ctx['auth']['owner'],json={'is_active':False})
    assert suspend.status_code==200,suspend.text
    assert ctx['client'].get(API+'/orders/search',headers=h).status_code==401
    assert ctx['client'].post(API+'/auth/login',json={'organization_id':str(ctx['ids']['a']),'email':'helper@example.com','password':'StrongPass#2026Accepted'}).status_code==401
    assert ctx['client'].get(API+'/collaborators/users',headers=ctx['auth']['operator']).status_code==403
    assert ctx['client'].get(API+'/collaborators/users',headers=ctx['auth']['foreign']).json()==[
      {'id':str(ctx['ids']['foreign']),'email':'foreign@rf013.example','role':'owner','is_active':True,
       'permissions':get(ctx,'/collaborators/permissions',who='foreign').json()}]


def test_rf023_invite_expiry_and_no_owner_suspension(ctx):
    r=post(ctx,'/collaborators/invitations',{'email':'expired@example.com','permissions':[]})
    assert r.status_code==201
    with ctx['factory']() as db:
        obj=db.get(CollaboratorInvite,UUID(r.json()['invitation_id']))
        from datetime import datetime,timezone
        obj.expires_at=datetime.now(timezone.utc)-timedelta(minutes=1);db.commit()
    assert ctx['client'].post(API+'/collaborators/invitations/accept',json={'token':r.json()['token'],'password':'StrongPass#2026Accepted'}).status_code==410
    assert ctx['client'].patch(API+'/collaborators/users/'+str(ctx['ids']['owner'])+'/suspension',
       headers=ctx['auth']['owner'],json={'is_active':False}).status_code==409
    assert post(ctx,'/collaborators/invitations',{'email':'bad@example.com','permissions':['owner']}).status_code==422


def test_rf024_supplier_purchase_approval_no_stock_write(ctx):
    m=setup_material(ctx)
    s=post(ctx,'/purchasing/suppliers',{'code':'S-'+uuid4().hex[:8],'name':'Proveedor','contact_email':'contact@example.com'})
    assert s.status_code==201,s.text
    assert post(ctx,'/purchasing/suppliers',{'code':s.json()['code'],'name':'Repetido'}).status_code==409
    assert post(ctx,'/purchasing/suppliers',{'code':'OUT','name':'OUT'},who='operator').status_code==403
    r=post(ctx,'/purchasing/requests',{'supplier_id':s.json()['id'],'material_id':m['id'],
          'quantity':'2.500','unit_cost_mxn':'3.75'},who='operator')
    assert r.status_code==201,r.text
    a=r.json();assert a['status']=='pending' and a['total_mxn']=='9.38'
    assert post(ctx,'/purchasing/requests/'+a['id']+'/decision',{'decision':'approve','note':'Autorizado'},who='operator').status_code==403
    approval=post(ctx,'/purchasing/requests/'+a['id']+'/decision',{'decision':'approve','note':'Compra autorizada'})
    assert approval.status_code==200 and approval.json()['status']=='approved'
    assert post(ctx,'/purchasing/requests/'+a['id']+'/decision',{'decision':'reject','note':'Rechazo tardio'}).status_code==409
    assert get(ctx,'/materials/'+m['id']).json()['quantity_available']=='0.000'
    assert get(ctx,'/purchasing/requests',who='foreign').json()==[]
    assert post(ctx,'/purchasing/requests',{'supplier_id':s.json()['id'],'material_id':m['id'],'quantity':'1','unit_cost_mxn':'1'},who='foreign').status_code==404


def test_rf025_calendar_capacity_and_tenant(ctx):
    o=order(ctx);confirm_order(ctx,o)
    r=setup_resource(ctx)
    allocation=post(ctx,'/scheduling/allocations',{'resource_id':r['id'],'order_id':o['id'],'day':FUTURE,'quantity':'3.000'})
    assert allocation.status_code==201,allocation.text
    assert post(ctx,'/scheduling/allocations',{'resource_id':r['id'],'order_id':o['id'],'day':FUTURE,'quantity':'1'}).status_code==409
    panel=get(ctx,'/scheduling/calendar?day='+FUTURE)
    assert panel.status_code==200,panel.text
    item=panel.json()['resources'][0]
    assert item['occupied']=='3.000' and item['remaining']=='2.000' and item['unit']=='pieza'
    other=order(ctx);confirm_order(ctx,other)
    assert post(ctx,'/scheduling/allocations',{'resource_id':r['id'],'order_id':other['id'],'day':FUTURE,'quantity':'3.000'}).status_code==409
    assert get(ctx,'/scheduling/calendar?day='+FUTURE,who='foreign').json()['resources']==[]
    assert post(ctx,'/scheduling/allocations',{'resource_id':r['id'],'order_id':o['id'],'day':FUTURE,'quantity':'1'},who='foreign').status_code==404
    rem=ctx['client'].delete(API+'/scheduling/allocations/'+allocation.json()['id'],headers=ctx['auth']['owner'])
    assert rem.status_code==200
    assert get(ctx,'/scheduling/calendar?day='+FUTURE).json()['resources'][0]['remaining']=='5.000'


def test_rf026_disabled_then_enabled_alerts(ctx):
    o=order(ctx);confirm_order(ctx,o)
    m=setup_material(ctx)
    p=product(ctx)
    from test_quotes import tax
    assert tax(ctx).status_code==200
    assert ctx['client'].put(API+'/products/'+p['id']+'/recipe/'+m['id'],headers=ctx['auth']['owner'],json={'quantity_per_unit':'2.000'}).status_code==200
    q=create(ctx,payload(o,p,q='4.000',discount='0.00'))
    assert q.status_code==201,q.text
    assert request(ctx,'/'+q.json()['id']+'/approve',method='POST').status_code==200
    disabled=post(ctx,'/notifications/scan',{})
    assert disabled.status_code==200 and disabled.json()['created']==0
    upd=ctx['client'].put(API+'/notifications/preferences',headers=ctx['auth']['owner'],json={'due_soon':True,'risk':True,'material_shortage':True})
    assert upd.status_code==200
    scanned=post(ctx,'/notifications/scan',{})
    assert scanned.status_code==200,scanned.text
    assert scanned.json()['created']==2 # upcoming date and material shortage
    assert post(ctx,'/notifications/scan',{}).json()['created']==0
    notes=get(ctx,'/notifications/entries').json()
    assert {n['kind'] for n in notes}=={'due_soon','material_shortage'}
    assert get(ctx,'/notifications/entries',who='foreign').json()==[]
    assert get(ctx,'/notifications/preferences',who='foreign').json()=={'due_soon':False,'risk':False,'material_shortage':False}


def test_rf027_filtered_totals_and_download(ctx):
    from test_quotes import tax
    o,p=prepared(ctx)
    assert tax(ctx,'0.00').status_code==200
    confirm_order(ctx,o)
    quote=create(ctx,payload(o,p,q='2.000',discount='0.00'))
    assert quote.status_code==201,quote.text
    assert request(ctx,'/'+quote.json()['id']+'/approve',method='POST').status_code==200
    result=get(ctx,'/reports/summary')
    assert result.status_code==200,result.text
    data=result.json();assert data['totals']['orders']==1
    assert data['totals']['revenue_mxn']=='51.00'
    c=get(ctx,'/reports/export?format=csv')
    assert c.status_code==200 and c.content.startswith(b'\xef\xbb\xbf')
    assert 'text/csv' in c.headers['content-type']
    assert '51.00' in c.text
    pdf=get(ctx,'/reports/export?format=pdf')
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    filtered=get(ctx,'/reports/summary?status=cancelled').json()
    assert filtered['totals']['orders']==0 and filtered['totals']['revenue_mxn']=='0.00'
    assert get(ctx,'/reports/summary?status=not-a-status').status_code==422
    assert get(ctx,'/reports/summary',who='foreign').json()['totals']['orders']==0
    assert ctx['client'].get(API+'/reports/summary').status_code==401
    assert get(ctx,'/reports/export?format=html').status_code==422


def test_restricted_operator_calendar_and_business_permissions(ctx):
    o=order(ctx);confirm_order(ctx,o)
    r=setup_resource(ctx)
    invite=post(ctx,'/collaborators/invitations',{'email':'calendar'+uuid4().hex[:6]+'@example.com',
              'permissions':['orders.read','calendar.read','calendar.write']})
    assert invite.status_code==201
    accepted=ctx['client'].post(API+'/collaborators/invitations/accept',json={
        'token':invite.json()['token'],'password':'StrongPassword2026!'}).json()
    login=ctx['client'].post(API+'/auth/login',json={
        'organization_id':str(ctx['ids']['a']),'email':accepted['email'],'password':'StrongPassword2026!'})
    assert login.status_code==200,login.text
    h={'Authorization':'Bearer '+login.json()['access_token']}
    assert ctx['client'].get(API+'/orders/search',headers=h).status_code==200
    assert ctx['client'].get(API+'/reports/summary',headers=h).status_code==403
    assert ctx['client'].get(API+'/materials',headers=h).status_code==403
    allocation=ctx['client'].post(API+'/scheduling/allocations',headers=h,json={
       'resource_id':r['id'],'order_id':o['id'],'day':FUTURE,'quantity':'1.000'})
    assert allocation.status_code==201,allocation.text
    assert ctx['client'].delete(API+'/scheduling/allocations/'+allocation.json()['id'],headers=h).status_code==200
    # Modified permissions apply to the current session; no stale claim bypass.
    changed=ctx['client'].patch(API+'/collaborators/users/'+accepted['id']+'/permissions',
        headers=ctx['auth']['owner'],json={'permissions':['orders.read']})
    assert changed.status_code==200
    assert ctx['client'].get(API+'/scheduling/calendar?day='+FUTURE,headers=h).status_code==403


def test_rf024_rejected_purchase_keeps_inventory(ctx):
    m=setup_material(ctx)
    s=post(ctx,'/purchasing/suppliers',{'code':'S-'+uuid4().hex[:8],'name':'Proveedor alternativo'}).json()
    request=post(ctx,'/purchasing/requests',{'supplier_id':s['id'],'material_id':m['id'],
         'quantity':'100','unit_cost_mxn':'19.90'}).json()
    result=post(ctx,'/purchasing/requests/'+request['id']+'/decision',{'decision':'reject','note':'Cotización demasiado costosa'})
    assert result.status_code==200 and result.json()['status']=='rejected'
    assert get(ctx,'/materials/'+m['id']).json()['quantity_available']=='0.000'
    assert post(ctx,'/purchasing/requests/'+request['id']+'/decision',{'decision':'approve','note':'Cambio de opinión'}).status_code==409


def test_rf025_blackout_and_unconfirmed_order_rejected(ctx):
    o=order(ctx);r=setup_resource(ctx)
    body={'resource_id':r['id'],'order_id':o['id'],'day':FUTURE,'quantity':'1.000'}
    assert post(ctx,'/scheduling/allocations',body).status_code==409
    confirm_order(ctx,o)
    blackout=ctx['client'].put(API+'/capacity/resources/'+r['id']+'/blackouts/'+FUTURE,headers=ctx['auth']['owner'])
    assert blackout.status_code==200,blackout.text
    assert post(ctx,'/scheduling/allocations',body).status_code==409
    rget=get(ctx,'/scheduling/calendar?day='+FUTURE)
    assert rget.status_code==200 and rget.json()['resources'][0]['capacity']=='0'


def test_rf026_overdue_only_emitted_when_enabled(ctx):
    o=order(ctx);confirm_order(ctx,o)
    from app.modules.orders.model import Order
    with ctx['factory']() as db:
        row=db.get(Order,UUID(o['id']))
        row.reviewed_due_date=TODAY-timedelta(days=5)
        db.commit()
    assert post(ctx,'/notifications/scan',{}).json()['created']==0
    changed=ctx['client'].put(API+'/notifications/preferences',headers=ctx['auth']['owner'],json={
      'due_soon':False,'risk':True,'material_shortage':False})
    assert changed.status_code==200
    result=post(ctx,'/notifications/scan',{}).json()
    assert result['created']==1
    assert [n['kind'] for n in get(ctx,'/notifications/entries').json()]==['risk']
    assert post(ctx,'/notifications/scan',{}).json()['created']==0


def test_rf027_date_ranges_exclude_and_match(ctx):
    o=order(ctx)
    future=(TODAY+timedelta(days=7)).isoformat()
    past=(TODAY-timedelta(days=7)).isoformat()
    assert get(ctx,'/reports/summary?date_from='+future).json()['totals']['orders']==0
    assert get(ctx,'/reports/summary?date_to='+past).json()['totals']['orders']==0
    assert get(ctx,'/reports/export?format=csv&date_from='+future).status_code==200
    assert get(ctx,'/reports/summary?date_from='+future+'&date_to='+past).status_code==422
