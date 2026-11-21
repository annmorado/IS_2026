"""RF-026: per-user preferences and deduplicated in-app alerts."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime,ForeignKey,ForeignKeyConstraint,String,UniqueConstraint,Uuid,func
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base

class NotificationPreference(Base):
    __tablename__='notification_preferences'
    __table_args__=(
        ForeignKeyConstraint(['user_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_notify_pref_user_tenant'),
    )
    user_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True)
    organization_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False,index=True)
    due_soon:Mapped[bool]=mapped_column(nullable=False,default=False)
    risk:Mapped[bool]=mapped_column(nullable=False,default=False)
    material_shortage:Mapped[bool]=mapped_column(nullable=False,default=False)

class BusinessNotification(Base):
    __tablename__='business_notifications'
    __table_args__=(
        UniqueConstraint('user_id','kind','source_key',name='uq_notify_user_kind_source'),
        ForeignKeyConstraint(['user_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_notify_user_tenant'),
    )
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    user_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False,index=True)
    kind:Mapped[str]=mapped_column(String(32),nullable=False)
    source_key:Mapped[str]=mapped_column(String(160),nullable=False)
    message:Mapped[str]=mapped_column(String(500),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
    read_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
