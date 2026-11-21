"""RF-029: OCR real con Tesseract opcional; solo crea PROPUESTAS para revisión humana.
Los bytes de la foto no se guardan, y nunca genera facturas/pedidos automáticamente.
"""
import hashlib,io,json,os,re
from datetime import date as Date
from uuid import UUID
from fastapi import APIRouter,Depends,File,HTTPException,UploadFile
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner,require_staff
from app.modules.decisions.audit import audit
from app.modules.extensions.entitlements import consume
from app.modules.extensions.model import OcrProposal
from app.modules.tenancy.scope import scope_from_context
router=APIRouter(prefix='/documents/ocr',tags=['RF-029 OCR asistido'])
MAX_IMAGE=4*1024*1024
ALLOWED={'image/jpeg','image/png','image/webp'}

def recognize(data:bytes)->dict:
    try:
        from PIL import Image,ImageOps,UnidentifiedImageError
        import pytesseract
        from pytesseract import Output
        try:
            image=Image.open(io.BytesIO(data));image.verify()
            image=Image.open(io.BytesIO(data));image=ImageOps.exif_transpose(image)
        except (UnidentifiedImageError,ValueError,OSError) as exc:
            raise HTTPException(status_code=422,detail='El archivo no contiene una imagen reconocible') from exc
        if image.width*image.height>16_000_000 or min(image.size)<60:
            raise HTTPException(status_code=422,detail='Imagen demasiado grande o pequeña')
        image=image.convert('RGB')
        if os.getenv('NEXO_TESSERACT_CMD'):
            pytesseract.pytesseract.tesseract_cmd=os.environ['NEXO_TESSERACT_CMD']
        try:
            info=pytesseract.image_to_data(image,lang='spa',output_type=Output.DICT,config='--psm 6')
        except pytesseract.TesseractError:
            info=pytesseract.image_to_data(image,lang='eng',output_type=Output.DICT,config='--psm 6')
        phrases=[];conf=[]
        for s,n in zip(info['text'],info['conf']):
            if s and s.strip():
                phrases.append(s.strip())
                try:
                    v=float(n)
                    if v>=0:conf.append(v)
                except (TypeError,ValueError):pass
        text=' '.join(phrases)[:2000]
        score=round(sum(conf)/len(conf)/100,3) if conf else 0.0
        amounts=re.findall(r'(?:\$\s*|TOTAL\s*:?\s*)(\d{1,8}[.,]\d{2})',text,re.I)
        date_match=re.search(r'\b(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b',text)
        return {'raw_text':text,'confidence':score,'suggested_fields':{
            'amount_mxn':amounts[-1].replace(',','.') if amounts else None,
            'date':date_match.group(1) if date_match else None,
            'reference':None,'vendor':None},
            'field_confidence':{'amount_mxn':score if amounts else None,'date':score if date_match else None,'reference':None,'vendor':None},
            'confidence_note':'Aproximación basada en confianza media OCR; no es una probabilidad calibrada por campo.',
            'engine':'tesseract-local','review_required':True}
    except HTTPException:raise
    except (ImportError,FileNotFoundError,OSError) as exc:
        raise HTTPException(status_code=503,detail='OCR no disponible: instala Tesseract OCR y los paquetes Pillow/pytesseract') from exc
    except Exception as exc:
        # Failed OCR must not create fake data or consume quota.
        raise HTTPException(status_code=422,detail='No se pudo interpretar la imagen como documento') from exc

class OcrReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm:bool
    vendor:str|None=Field(default=None,max_length=160)
    amount_mxn:str|None=Field(default=None,pattern=r'^\d{1,9}(?:\.\d{1,2})?$')
    date:Date|None=None
    reference:str|None=Field(default=None,max_length=120)
    concept:str|None=Field(default=None,max_length=500)

def out(o):
    return {'id':str(o.id),'document_type':o.document_type,'filename':o.filename,'status':o.status,
            'extracted':json.loads(o.extracted_json),'reviewed':json.loads(o.reviewed_json) if o.reviewed_json else None,
            'created_at':o.created_at}

@router.post('/proposals',status_code=201)
async def propose(file:UploadFile=File(...),document_type:str='invoice',
                  ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    if document_type not in {'invoice','receipt','label'}:
        raise HTTPException(status_code=422,detail='Tipo de documento inválido')
    if file.content_type not in ALLOWED:
        raise HTTPException(status_code=415,detail='Solo JPEG, PNG o WebP')
    payload=await file.read(MAX_IMAGE+1)
    if not payload or len(payload)>MAX_IMAGE:
        raise HTTPException(status_code=413,detail='Imagen vacía o mayor a 4 MB')
    result=recognize(payload)
    if not result['raw_text']:
        raise HTTPException(status_code=422,detail='No se detectó texto legible; no se guardó ningún dato')
    scope=scope_from_context(ctx);consume(db,scope.organization_id,'ocr')
    name=os.path.basename((file.filename or 'documento')[:120]).replace('\\','_')
    proposal=OcrProposal(organization_id=scope.organization_id,created_by_user_id=scope.actor_id,
        document_type=document_type,filename=name,sha256=hashlib.sha256(payload).hexdigest(),
        extracted_json=json.dumps(result,ensure_ascii=False))
    db.add(proposal);db.flush()
    audit(db,scope,entity_type='ocr_proposal',entity_id=proposal.id,action='ocr.proposed',after={'document_type':document_type,'status':'proposed'})
    db.commit();return out(proposal)

@router.get('/proposals')
def list_proposals(ctx:AuthContext=Depends(require_staff),db:Session=Depends(get_db)):
    return [out(o) for o in db.scalars(select(OcrProposal).where(OcrProposal.organization_id==ctx.user.organization_id)
                           .order_by(OcrProposal.created_at.desc()).limit(30)).all()]

@router.post('/proposals/{proposal_id}/review')
def review(proposal_id:UUID,body:OcrReview,ctx:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    o=db.scalar(select(OcrProposal).where(OcrProposal.id==proposal_id,OcrProposal.organization_id==ctx.user.organization_id).with_for_update())
    if not o:raise HTTPException(status_code=404,detail='Documento no encontrado')
    if o.status!='proposed':raise HTTPException(status_code=409,detail='Documento ya revisado')
    if not body.confirm:raise HTTPException(status_code=422,detail='Revisión humana y confirmación explícita obligatorias')
    o.reviewed_json=json.dumps(body.model_dump(mode='json',exclude={'confirm'}),ensure_ascii=False)
    o.status='reviewed'
    audit(db,scope_from_context(ctx),entity_type='ocr_proposal',entity_id=o.id,action='ocr.reviewed',after={'status':'reviewed'})
    db.commit();return out(o)
