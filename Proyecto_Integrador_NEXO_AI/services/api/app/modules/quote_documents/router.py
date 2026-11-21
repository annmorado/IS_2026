"""RF-014: API autenticada de emision y descarga de cotizacion aprobada."""
from uuid import UUID
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.tenancy.scope import scope_from_context
from app.modules.quote_documents.schemas import DocumentCreate, DocumentRead
from app.modules.quote_documents.service import create_document, read_document, read_pdf

router = APIRouter(prefix='/quotes', tags=['RF-014 PDF de cotizacion'])

@router.post('/{quote_id}/document', response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def generate_document(quote_id: UUID, payload: DocumentCreate,
    context: AuthContext = Depends(require_staff), db: Session = Depends(get_db)):
    return create_document(db,scope_from_context(context),quote_id,payload.valid_until)

@router.get('/{quote_id}/document', response_model=DocumentRead)
def document_metadata(quote_id: UUID, context: AuthContext = Depends(require_staff),
    db: Session = Depends(get_db)):
    return read_document(db,scope_from_context(context),quote_id)

@router.get('/{quote_id}/pdf')
def download_document(quote_id: UUID, context: AuthContext = Depends(require_staff),
    db: Session = Depends(get_db)):
    folio, data = read_pdf(db,scope_from_context(context),quote_id)
    return Response(content=data,media_type='application/pdf',headers={
        'Content-Disposition': f'attachment; filename="{folio}.pdf"',
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options':'nosniff',
    })
