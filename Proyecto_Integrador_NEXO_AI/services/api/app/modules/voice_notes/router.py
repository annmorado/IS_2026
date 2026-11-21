"""RF-009: carga y consulta de audios privados con JWT y alcance tenant."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_staff
from app.modules.tenancy.scope import scope_from_context
from app.modules.voice_notes.schemas import VoiceNoteRead
from app.modules.voice_notes.service import (
    get_voice_note, list_voice_notes, resolve_voice_note_file, save_voice_note,
)

router = APIRouter(prefix="/voice-notes", tags=["RF-009 Captura de audio"])


@router.post("", response_model=VoiceNoteRead, status_code=status.HTTP_201_CREATED)
def upload_voice_note(
    file: UploadFile = File(...),
    duration_ms: int | None = Form(default=None, ge=0, le=3600000),
    context: AuthContext = Depends(require_staff),
    db: Session = Depends(get_db),
):
    return save_voice_note(db, scope_from_context(context), file, duration_ms=duration_ms)


@router.get("", response_model=list[VoiceNoteRead])
def list_all(only_mine: bool = False, limit: int = Query(50, ge=1, le=100),
             offset: int = Query(0, ge=0), context: AuthContext = Depends(require_staff),
             db: Session = Depends(get_db)):
    return list_voice_notes(db, scope_from_context(context), only_mine=only_mine,
                            limit=limit, offset=offset)


@router.get("/{note_id}", response_model=VoiceNoteRead)
def read_one(note_id: UUID, context: AuthContext = Depends(require_staff),
             db: Session = Depends(get_db)):
    return get_voice_note(db, scope_from_context(context), note_id)


@router.get("/{note_id}/file")
def download_audio(note_id: UUID, context: AuthContext = Depends(require_staff),
                   db: Session = Depends(get_db)):
    note = get_voice_note(db, scope_from_context(context), note_id)
    path = resolve_voice_note_file(note)
    return FileResponse(
        path, media_type="audio/mp4", filename=f"voice-note-{note.id}.m4a",
        content_disposition_type="attachment",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
