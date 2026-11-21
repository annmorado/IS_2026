"""Presentacion PDF de la version aprobada (sin escribir archivos temporales)."""
from datetime import datetime
from decimal import Decimal
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

INK = colors.HexColor('#102138')
BLUE = colors.HexColor('#155E75')
TEAL = colors.HexColor('#0F766E')
PALE = colors.HexColor('#EDF7F7')
GRAY = colors.HexColor('#64748B')


def _txt(value: object) -> str:
    """Evitar markup inyectado y caracteres no dibujables por Helvetica WinAnsi."""
    clean = ''.join(' ' if ord(char) < 32 else char for char in str(value))
    return escape(clean.encode('cp1252', 'replace').decode('cp1252'))


def _money(value: Decimal) -> str:
    return f'${Decimal(value):,.2f}'


def render_quote_pdf(*, organization_name: str, quote, lines, folio: str,
                     valid_until, generated_at: datetime) -> bytes:
    """PDF multipagina de partidas inmutables; no incluye costos internos."""
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4,
        rightMargin=17*mm, leftMargin=17*mm, topMargin=27*mm, bottomMargin=22*mm,
        title=f'Cotizacion {folio}', author=_txt(organization_name))
    ss = getSampleStyleSheet()
    normal = ParagraphStyle('CustomNormal', parent=ss['Normal'], fontName='Helvetica',
        fontSize=9.2, leading=13, textColor=INK, spaceAfter=5)
    tiny = ParagraphStyle('Small', parent=normal, fontSize=8, leading=10)
    title = ParagraphStyle('CustomTitle', parent=normal, fontName='Helvetica-Bold',
        fontSize=20, leading=24, textColor=INK, spaceAfter=7)
    cell = ParagraphStyle('Cell', parent=normal, fontSize=8, leading=11)
    headcell = ParagraphStyle('HeadCell', parent=cell, fontName='Helvetica-Bold', textColor=colors.white)
    amount = ParagraphStyle('Amount', parent=cell, alignment=TA_RIGHT)
    amountbold = ParagraphStyle('AmountBold', parent=amount, fontName='Helvetica-Bold')

    story = [Paragraph('COTIZACION COMERCIAL', title),
        Paragraph(f'<b>Emisor:</b> {_txt(organization_name)}', normal),
        Paragraph(f'<b>Folio:</b> {_txt(folio)}', normal),
        Paragraph(f'<b>Pedido:</b> {_txt(quote.order_id)}', tiny),
        Paragraph(f'<b>Cotizacion:</b> {_txt(quote.id)} · <b>Version:</b> {quote.version}', tiny),
        Paragraph(f'<b>Aprobada:</b> {_txt(quote.approved_at.date().isoformat() if quote.approved_at else "-")} '
                  f' · <b>Emitida:</b> {_txt(generated_at.date().isoformat())} '
                  f' · <b>Vigente hasta:</b> {_txt(valid_until.isoformat())}', normal),
        Spacer(1, 6*mm), HRFlowable(width='100%', thickness=1.2, color=TEAL),
        Spacer(1, 5*mm), Paragraph('PARTIDAS', ParagraphStyle('Section',parent=title,fontSize=12,leading=15)),
    ]

    rows = [[Paragraph(x,headcell) for x in ['SKU / Producto', 'Cantidad', 'Precio unit.', 'Importe']]]
    for line in lines:
        rows.append([
            Paragraph(f'<b>{_txt(line.product_sku)}</b><br/>{_txt(line.product_name)}<br/>'
                      f'<font color="#64748B">{_txt(line.unit)}</font>',cell),
            Paragraph(f'{line.quantity:.3f}', amount),
            Paragraph(_money(line.unit_price), amount),
            Paragraph(_money(line.line_subtotal), amount),
        ])
    widths=[83*mm,25*mm,31*mm,37*mm]
    tbl = Table(rows, colWidths=widths, repeatRows=1, hAlign='LEFT')
    tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),BLUE),
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
        ('LINEBELOW',(0,-1),(-1,-1),0.6,colors.HexColor('#CBD5E1')),
        ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
        ('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9),
    ]))
    story.extend([tbl,Spacer(1,8*mm)])
    totals = [
        ('Subtotal',_money(quote.subtotal)),
        (f'Descuento ({quote.discount_percent}%)',f'-{_money(quote.discount_amount)}'),
        ('Base gravable',_money(quote.taxable_base)),
        (f'Impuesto configurado ({quote.tax_percent}%)',_money(quote.tax_amount)),
        ('TOTAL MXN',_money(quote.total)),
    ]
    total_rows = [[Paragraph(_txt(label), amountbold if i==len(totals)-1 else amount),
                   Paragraph(value,amountbold if i==len(totals)-1 else amount)]
                  for i,(label,value) in enumerate(totals)]
    summary = Table(total_rows,colWidths=[115*mm,61*mm],hAlign='LEFT')
    summary.setStyle(TableStyle([
        ('BACKGROUND',(0,-1),(-1,-1),PALE),
        ('LINEABOVE',(0,-1),(-1,-1),1.1,TEAL),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('RIGHTPADDING',(0,0),(-1,-1),8),
    ]))
    story.append(KeepTogether([summary,Spacer(1,4*mm),
        Paragraph('Cotizacion comercial informativa. No es CFDI ni comprobante fiscal.',tiny)]))

    def page_background(canvas, document):
        canvas.saveState()
        w,h=A4
        canvas.setFillColor(INK)
        canvas.rect(0,h-13*mm,w,13*mm,fill=1,stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold',10)
        canvas.drawString(17*mm,h-9*mm,'NEXO AI  /  COTIZACIONES')
        canvas.setStrokeColor(colors.HexColor('#CBD5E1'))
        canvas.line(17*mm,17*mm,w-17*mm,17*mm)
        canvas.setFillColor(GRAY)
        canvas.setFont('Helvetica',8)
        canvas.drawString(17*mm,12*mm,_txt(folio).replace('&amp;','&'))
        canvas.drawRightString(w-17*mm,12*mm,f'Pagina {document.page}')
        canvas.restoreState()

    pdf.build(story,onFirstPage=page_background,onLaterPages=page_background)
    return buffer.getvalue()
