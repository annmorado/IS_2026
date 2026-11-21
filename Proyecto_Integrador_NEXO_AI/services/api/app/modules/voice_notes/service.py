"""RF-009: guardar M4A privado en disco, limitado a 10 MiB y segregado por tenant.

La cabecera ISO BMFF ftyp es una comprobacion basica y no sustituye
validacion multimedia, antivirus, escaneo ni almacenamiento privado en nube.
"""
import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.tenancy.scope import TenantScope
from app.modules.voice_notes.model import VoiceNote
from app.modules.decisions.audit import audit

MAX_AUDIO_BYTES = 10 * 1024 * 1024
CHUNK_SIZE = 64 * 1024
ALLOWED_TYPES = frozenset({"audio/mp4", "audio/x-m4a", "audio/m4a"})


def storage_root() -> Path:
    default = Path(__file__).resolve().parents[3] / "storage" / "private" / "voice_notes"
    return Path(os.environ.get("NEXO_VOICE_STORAGE_DIR", str(default))).resolve()


def private_path(organization_id: UUID, note_id: UUID) -> Path:
    return storage_root() / str(organization_id) / f"{note_id}.m4a"


def _valid_m4a_signature(header: bytes) -> bool:
    return (len(header) >= 12 and header[4:8] == b"ftyp"
            and header[8:12] in {b"M4A ", b"isom", b"iso2", b"mp41", b"mp42"})


def save_voice_note(db: Session, scope: TenantScope, uploaded: UploadFile,
                    *, duration_ms: int | None) -> VoiceNote:
    if uploaded.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="Solo se admite audio M4A (audio/mp4)")

    note_id = uuid4()
    final_path = private_path(scope.organization_id, note_id)
    directory = final_path.parent
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp_path = directory / f".{note_id}.{uuid4().hex}.part"
    digest = hashlib.sha256()
    total = 0
    finalized = False
    try:
        with tmp_path.open("xb") as output:
            os.chmod(tmp_path, 0o600)
            first_chunk = True
            while chunk := uploaded.file.read(CHUNK_SIZE):
                if first_chunk:
                    first_chunk = False
                    if not _valid_m4a_signature(chunk):
                        raise HTTPException(status_code=415, detail="Contenido de audio M4A invalido")
                total += len(chunk)
                if total > MAX_AUDIO_BYTES:
                    raise HTTPException(status_code=413, detail="El audio supera 10 MiB")
                digest.update(chunk)
                output.write(chunk)
        if total == 0:
            raise HTTPException(status_code=422, detail="No se recibio audio")

        tmp_path.replace(final_path)
        finalized = True
        note = VoiceNote(
            id=note_id, organization_id=scope.organization_id,
            created_by_user_id=scope.actor_id,
            byte_size=total, duration_ms=duration_ms, sha256_hex=digest.hexdigest(),
        )
        db.add(note)
        audit(db, scope, entity_type='voice_note', entity_id=note.id,
              action='voice_note.created',after={'sha256':note.sha256_hex,
               'byte_size':total})
        db.commit()
        db.refresh(note)
        return note
    except Exception:
        db.rollback()
        if finalized:
            final_path.unlink(missing_ok=True)
        raise
    finally:
        tmp_path.unlink(missing_ok=True)
        uploaded.file.close()


def get_voice_note(db: Session, scope: TenantScope, note_id: UUID) -> VoiceNote:
    note = db.scalar(select(VoiceNote).where(
        VoiceNote.id == note_id, VoiceNote.organization_id == scope.organization_id,
    ))
    if note is None:
        raise HTTPException(status_code=404, detail="Nota de voz no encontrada")
    return note


def list_voice_notes(db: Session, scope: TenantScope, *, only_mine: bool,
                     limit: int, offset: int) -> list[VoiceNote]:
    query = select(VoiceNote).where(VoiceNote.organization_id == scope.organization_id)
    if only_mine:
        query = query.where(VoiceNote.created_by_user_id == scope.actor_id)
    return list(db.scalars(query.order_by(VoiceNote.created_at.desc(), VoiceNote.id.desc())
                           .limit(limit).offset(offset)).all())


def resolve_voice_note_file(note: VoiceNote) -> Path:
    path = private_path(note.organization_id, note.id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Archivo de audio no disponible")
    return path
