"""RF-027: reproducible tenant-isolated filtered reporting CSV/PDF."""
import csv
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from io import BytesIO,StringIO
from zoneinfo import ZoneInfo
from html import escape
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.orders.model import Order
from app.modules.order_status.model import OrderStatusEvent
from app.modules.quotes.model import Quote
from app.modules.organizations.model import Organization

router=APIRouter(prefix='/reports',tags=['RF-027 Reportes exportables'])

HEADERS=['order_id','created_at','status','due_date','reviewed_quantity','compliance','quote_id','quote_version','revenue_mxn','gross_margin_mxn']

def dataset(db,org_id,from_date,to_date,status):
    if from_date and to_date and from_date>to_date:raise HTTPException(422,detail='Intervalo inválido')
    org=db.get(Organization,org_id)
    try:
        zone=ZoneInfo(org.timezone) if org else ZoneInfo('UTC')
    except Exception as exc:raise HTTPException(409,detail='Zona horaria de la empresa inválida') from exc
    stmt=select(Order).where(Order.organization_id==org_id)
    if from_date:
        local_start=datetime.combine(from_date,datetime.min.time(),tzinfo=zone)
        stmt=stmt.where(Order.created_at>=local_start.astimezone(timezone.utc))
    if to_date:
        local_end=datetime.combine(to_date+timedelta(days=1),datetime.min.time(),tzinfo=zone)
        stmt=stmt.where(Order.created_at<local_end.astimezone(timezone.utc))
    if status:stmt=stmt.where(Order.status==status)
    orders=list(db.scalars(stmt.order_by(Order.created_at.desc(),Order.id.desc()).limit(10001)).all())
    if len(orders)>10000:raise HTTPException(422,detail='Demasiados pedidos; aplica filtros para exportar hasta 10,000')
    if not orders:return [],{'orders':0,'completed':0,'on_time':0,'late':0,'unknown_completion':0,'revenue_mxn':'0.00','gross_margin_mxn':'0.00'}
    ids=[o.id for o in orders]
    quotes=db.scalars(select(Quote).where(Quote.organization_id==org_id,Quote.order_id.in_(ids),Quote.status=='approved').order_by(Quote.version.desc())).all()
    latest={}
    for q in quotes:latest.setdefault(q.order_id,q)
    events=db.scalars(select(OrderStatusEvent).where(OrderStatusEvent.organization_id==org_id,
            OrderStatusEvent.order_id.in_(ids),OrderStatusEvent.to_status=='completed').order_by(OrderStatusEvent.changed_at)).all()
    completion={}
    for e in events:completion.setdefault(e.order_id,e.changed_at)
    rows=[];t={'orders':len(orders),'completed':0,'on_time':0,'late':0,'unknown_completion':0,
             'revenue_mxn':Decimal('0'),'gross_margin_mxn':Decimal('0')}
    for o in orders:
        comp='not_completed'
        if o.status=='completed':
            t['completed']+=1
            if o.reviewed_due_date and o.id in completion:
                moment=completion[o.id]
                if moment.tzinfo is None:moment=moment.replace(tzinfo=timezone.utc)
                comp='on_time' if moment.astimezone(zone).date()<=o.reviewed_due_date else 'late'
                t[comp]+=1
            else:
                comp='unknown';t['unknown_completion']+=1
        q=latest.get(o.id)
        revenue=q.total if q else Decimal('0');margin=q.estimated_gross_margin if q else Decimal('0')
        t['revenue_mxn']+=revenue;t['gross_margin_mxn']+=margin
        rows.append({'order_id':str(o.id),'created_at':o.created_at.isoformat(),'status':o.status,
         'due_date':o.reviewed_due_date.isoformat() if o.reviewed_due_date else '',
         'reviewed_quantity':str(o.reviewed_quantity) if o.reviewed_quantity else '',
         'compliance':comp,'quote_id':str(q.id) if q else '', 'quote_version':q.version if q else '',
         'revenue_mxn':str(revenue.quantize(Decimal('0.01'))),
         'gross_margin_mxn':str(margin.quantize(Decimal('0.01')))})
    for key in ('revenue_mxn','gross_margin_mxn'):t[key]=str(t[key].quantize(Decimal('0.01')))
    return rows,t

def data_request(context,db,from_date,to_date,status):
    return dataset(db,context.user.organization_id,from_date,to_date,status)

@router.get('/summary')
def summary(date_from:date|None=None,date_to:date|None=None,
    status:str|None=Query(default=None,pattern=r'^(draft|pending|confirmed|in_progress|completed|cancelled)$'),
    context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    rows,totals=data_request(context,db,date_from,date_to,status)
    return {'rows':rows,'totals':totals,'filters':{'date_from':date_from,'date_to':date_to,'status':status},
      'notice':'Ingresos y márgenes son cotizaciones aprobadas, no pagos cobrados. Cumplimiento usa evento de finalización.'}

@router.get('/export')
def export(format:str=Query(pattern=r'^(csv|pdf)$'),date_from:date|None=None,date_to:date|None=None,
    status:str|None=Query(default=None,pattern=r'^(draft|pending|confirmed|in_progress|completed|cancelled)$'),
    context:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    rows,totals=data_request(context,db,date_from,date_to,status)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%d')
    if format=='csv':
        out=StringIO();writer=csv.DictWriter(out,fieldnames=HEADERS,lineterminator='\r\n');writer.writeheader()
        # CSV formula injection prevention for text fields
        for row in rows:writer.writerow({k:("'"+str(v) if isinstance(v,str) and v[:1] in ('=','+','-','@') else v) for k,v in row.items()})
        writer.writerow({})
        writer.writerow({'order_id':'TOTAL_ORDERS','status':str(totals['orders'])})
        writer.writerow({'order_id':'TOTAL_REVENUE_MXN','revenue_mxn':totals['revenue_mxn']})
        writer.writerow({'order_id':'TOTAL_GROSS_MARGIN_MXN','gross_margin_mxn':totals['gross_margin_mxn']})
        return Response(content=('\ufeff'+out.getvalue()).encode('utf-8'),media_type='text/csv; charset=utf-8',
             headers={'Content-Disposition':f'attachment; filename="nexo-reporte-{stamp}.csv"','Cache-Control':'no-store'})
    out=BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=14*mm,leftMargin=14*mm,topMargin=18*mm,bottomMargin=18*mm)
    ss=getSampleStyleSheet();story=[Paragraph('NEXO AI / INFORME OPERATIVO',ss['Title']),
      Paragraph('Organizacion: '+escape(str(context.user.organization_id)),ss['Normal']),
      Paragraph('Filtros: '+escape(str({'from':date_from,'to':date_to,'status':status})),ss['Normal']),Spacer(1,8*mm),
      Paragraph(f"Pedidos: {totals['orders']} | Completados: {totals['completed']} | Puntuales: {totals['on_time']} | Tardios: {totals['late']}",ss['Normal']),
      Paragraph('Ingresos aprobados MXN: '+totals['revenue_mxn']+' | Margen bruto MXN: '+totals['gross_margin_mxn'],ss['Normal']),Spacer(1,7*mm)]
    tbl=[['Pedido','Estado','Cumplimiento','Ingreso MXN','Margen MXN']]
    for row in rows:tbl.append([row['order_id'][:8],row['status'],row['compliance'],row['revenue_mxn'],row['gross_margin_mxn']])
    if len(tbl)>1:
        table=Table(tbl,repeatRows=1,colWidths=[30*mm,34*mm,46*mm,35*mm,35*mm]);table.setStyle(TableStyle([
           ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#155e75')),('TEXTCOLOR',(0,0),(-1,0),colors.white),
           ('FONTSIZE',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
           ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#eef5f5')])]))
        story.append(table)
    else:story.append(Paragraph('Sin pedidos para el filtro seleccionado.',ss['Normal']))
    story.append(Spacer(1,5*mm));story.append(Paragraph('No equivale a ingreso cobrado ni a reporte fiscal.',ss['Normal']))
    doc.build(story)
    return Response(content=out.getvalue(),media_type='application/pdf',headers={
      'Content-Disposition':f'attachment; filename="nexo-reporte-{stamp}.pdf"','Cache-Control':'no-store'})
