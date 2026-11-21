"""RF-023: invitation one-time hash, tenant-isolated and expiring."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, String, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class CollaboratorInvite(Base):
    __tablename__='collaborator_invites'
    __table_args__=(
        UniqueConstraint('organization_id','token_hash',name='uq_invite_hash_org'),
        ForeignKeyConstraint(['created_by_user_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_invite_creator_tenant'),
    )
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    created_by_user_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False)
    email:Mapped[str]=mapped_column(String(254),nullable=False)
    permissions_json:Mapped[str]=mapped_column(Text,nullable=False)
    token_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    consumed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
