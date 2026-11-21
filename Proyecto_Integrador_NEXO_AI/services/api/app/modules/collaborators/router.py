"""RF-023: owner-controlled scoped invitations, suspension and explicit permissions."""
import hashlib, json, secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.auth.model import AuthSession,User
from app.modules.auth.security import hash_password, utc_now, as_utc
from app.modules.authorization.dependencies import require_owner
from app.modules.collaborators.model import CollaboratorInvite
from app.modules.collaborators.permissions import PERMISSIONS,validate_permissions,readable_permissions
from app.modules.decisions.audit import audit
from app.modules.tenancy.scope import scope_from_context

router=APIRouter(prefix='/collaborators',tags=['RF-023 Colaboradores'])

class InviteCreate(BaseModel):
    email:EmailStr
    permissions:list[str]=Field(default_factory=list,max_length=25)
    expires_hours:int=Field(default=24,ge=1,le=168)
class InviteAccept(BaseModel):
    token:str=Field(min_length=32,max_length=160)
    password:str=Field(min_length=12,max_length=128)
class PermissionPatch(BaseModel):
    permissions:list[str]=Field(max_length=25)
class SuspensionPatch(BaseModel):
    is_active:bool

def summary(user):
    return {'id':str(user.id),'email':user.email,'role':user.role,
            'is_active':user.is_active,'permissions':readable_permissions(user)}

@router.get('/permissions')
def available_permissions(context:AuthContext=Depends(require_owner)):
    return sorted(PERMISSIONS)

@router.get('/users')
def users(context:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    return [summary(x) for x in db.scalars(select(User).where(User.organization_id==context.user.organization_id).order_by(User.email)).all()]

@router.post('/invitations',status_code=201)
def invite(data:InviteCreate,context:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    scope=scope_from_context(context);email=str(data.email).strip().lower();perms=validate_permissions(data.permissions)
    if db.scalar(select(User).where(User.organization_id==scope.organization_id,User.email==email)):
        raise HTTPException(status_code=409,detail='Ya existe un usuario con ese correo')
    token=secrets.token_urlsafe(48)
    obj=CollaboratorInvite(organization_id=scope.organization_id,created_by_user_id=scope.actor_id,
      email=email,permissions_json=json.dumps(perms),token_hash=hashlib.sha256(token.encode()).hexdigest(),
      expires_at=utc_now()+timedelta(hours=data.expires_hours))
    db.add(obj);db.flush();audit(db,scope,entity_type='invitation',entity_id=obj.id,action='invitation.created',after={'email':email,'expires_at':obj.expires_at.isoformat(),'permissions':perms})
    db.commit()
    return {'invitation_id':str(obj.id),'token':token,'email':email,'expires_at':obj.expires_at.isoformat(),
      'notice':'Entrega este token por un canal seguro; solo se muestra una vez. No se envio correo automáticamente.'}

@router.post('/invitations/accept',status_code=201)
def accept(data:InviteAccept,db:Session=Depends(get_db)):
    tokenhash=hashlib.sha256(data.token.encode()).hexdigest()
    obj=db.scalar(select(CollaboratorInvite).where(CollaboratorInvite.token_hash==tokenhash).with_for_update())
    if not obj or obj.consumed_at or obj.revoked_at or as_utc(obj.expires_at)<=utc_now():
        raise HTTPException(status_code=410,detail='Invitación inválida, vencida o utilizada')
    if db.scalar(select(User).where(User.organization_id==obj.organization_id,User.email==obj.email)):
        raise HTTPException(status_code=409,detail='Usuario ya existe')
    user=User(organization_id=obj.organization_id,email=obj.email,password_hash=hash_password(data.password),
              role='operator',is_active=True,permissions_json=obj.permissions_json)
    db.add(user);db.flush();obj.consumed_at=utc_now()
    from app.modules.tenancy.scope import TenantScope
    scope=TenantScope(organization_id=obj.organization_id,actor_id=obj.created_by_user_id)
    audit(db,scope,entity_type='user',entity_id=user.id,action='collaborator.invitation_accepted',after={'email':user.email,'permissions':json.loads(obj.permissions_json)})
    db.commit();return summary(user)

@router.patch('/users/{user_id}/permissions')
def permissions(user_id:UUID,data:PermissionPatch,context:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    perms=validate_permissions(data.permissions)
    user=db.scalar(select(User).where(User.id==user_id,User.organization_id==context.user.organization_id).with_for_update())
    if not user:raise HTTPException(404,detail='Usuario no encontrado')
    if user.role=='owner':raise HTTPException(409,detail='No se modifican los permisos del propietario')
    before=readable_permissions(user)
    user.permissions_json=json.dumps(perms)
    scope=scope_from_context(context)
    audit(db,scope,entity_type='user',entity_id=user.id,action='collaborator.permissions_changed',before={'permissions':before},after={'permissions':perms})
    db.commit();return summary(user)

@router.patch('/users/{user_id}/suspension')
def suspension(user_id:UUID,data:SuspensionPatch,context:AuthContext=Depends(require_owner),db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.id==user_id,User.organization_id==context.user.organization_id).with_for_update())
    if not user:raise HTTPException(404,detail='Usuario no encontrado')
    if user.id==context.user.id or user.role=='owner':raise HTTPException(409,detail='No puedes suspender al propietario')
    before=user.is_active;user.is_active=data.is_active
    if not user.is_active:
        for session in db.scalars(select(AuthSession).where(AuthSession.user_id==user.id,AuthSession.revoked_at.is_(None))).all():
            session.revoked_at=utc_now()
    audit(db,scope_from_context(context),entity_type='user',entity_id=user.id,action='collaborator.suspension_changed',before={'active':before},after={'active':user.is_active})
    db.commit();return summary(user)
