"""Tablas P2 aisladas por organización, nunca mezclan datos entre empresas."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
                        Integer, String, Text, UniqueConstraint, Uuid, func, text)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

U=Uuid(as_uuid=True)

class Subscription(Base):
    __tablename__='organization_subscriptions'
    __table_args__=(CheckConstraint("status IN ('active','trial','suspended','expired')",name='ck_ext_subscription_status'),)
    organization_id:Mapped[UUID]=mapped_column(U,ForeignKey('organizations.id',ondelete='CASCADE'),primary_key=True)
    plan_code:Mapped[str]=mapped_column(String(32),nullable=False,server_default=text("'starter'"))
    status:Mapped[str]=mapped_column(String(16),nullable=False,server_default=text("'active'"))
    trial_consumed:Mapped[bool]=mapped_column(Boolean,nullable=False,server_default=text('false'))
    trial_ends_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

class FeatureUsage(Base):
    __tablename__='extension_feature_usage'
    __table_args__=(UniqueConstraint('organization_id','feature','period',name='uq_ext_feature_period'),
                     CheckConstraint('used >= 0',name='ck_ext_usage_nonnegative'))
    id:Mapped[UUID]=mapped_column(U,primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(U,ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    feature:Mapped[str]=mapped_column(String(32),nullable=False)
    period:Mapped[str]=mapped_column(String(7),nullable=False)
    used:Mapped[int]=mapped_column(Integer,nullable=False,server_default=text('0'))

class OcrProposal(Base):
    __tablename__='ocr_document_proposals'
    __table_args__=(ForeignKeyConstraint(['created_by_user_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_ext_ocr_actor'),
                     CheckConstraint("status IN ('proposed','reviewed')",name='ck_ext_ocr_status'))
    id:Mapped[UUID]=mapped_column(U,primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(U,ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    created_by_user_id:Mapped[UUID]=mapped_column(U,nullable=False)
    document_type:Mapped[str]=mapped_column(String(24),nullable=False)
    filename:Mapped[str]=mapped_column(String(120),nullable=False)
    sha256:Mapped[str]=mapped_column(String(64),nullable=False)
    extracted_json:Mapped[str]=mapped_column(Text,nullable=False)
    reviewed_json:Mapped[str|None]=mapped_column(Text)
    status:Mapped[str]=mapped_column(String(16),nullable=False,server_default=text("'proposed'"))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

class MessagingConfig(Base):
    __tablename__='messaging_integrations'
    organization_id:Mapped[UUID]=mapped_column(U,ForeignKey('organizations.id',ondelete='CASCADE'),primary_key=True)
    provider:Mapped[str]=mapped_column(String(32),nullable=False,server_default=text("'whatsapp_cloud'"))
    phone_number_id:Mapped[str]=mapped_column(String(40),nullable=False)
    enabled:Mapped[bool]=mapped_column(Boolean,nullable=False,server_default=text('false'))
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now(),onupdate=func.now())

class MessagingConsent(Base):
    __tablename__='messaging_consents'
    __table_args__=(ForeignKeyConstraint(['actor_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_ext_consent_actor'),
                     UniqueConstraint('organization_id','recipient_e164',name='uq_ext_consent_recipient'))
    id:Mapped[UUID]=mapped_column(U,primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(U,ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    actor_id:Mapped[UUID]=mapped_column(U,nullable=False)
    recipient_e164:Mapped[str]=mapped_column(String(16),nullable=False)
    evidence_reference:Mapped[str]=mapped_column(String(160),nullable=False)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

class MessagingEvent(Base):
    __tablename__='messaging_outbound_events'
    __table_args__=(ForeignKeyConstraint(['actor_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_ext_msg_actor'),)
    id:Mapped[UUID]=mapped_column(U,primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(U,ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    actor_id:Mapped[UUID]=mapped_column(U,nullable=False)
    recipient_tail:Mapped[str]=mapped_column(String(4),nullable=False)
    consent_reference:Mapped[str]=mapped_column(String(160),nullable=False)
    template_name:Mapped[str]=mapped_column(String(80),nullable=False)
    provider_message_id:Mapped[str]=mapped_column(String(150),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

class AppliedSectorTemplate(Base):
    __tablename__='organization_sector_templates'
    organization_id:Mapped[UUID]=mapped_column(U,ForeignKey('organizations.id',ondelete='CASCADE'),primary_key=True)
    template_code:Mapped[str]=mapped_column(String(32),nullable=False)
    version:Mapped[int]=mapped_column(Integer,nullable=False,server_default=text('1'))
    config_json:Mapped[str]=mapped_column(Text,nullable=False)
    applied_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

class TemplateEvent(Base):
    __tablename__='sector_template_events'
    __table_args__=(ForeignKeyConstraint(['actor_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_ext_template_actor'),)
    id:Mapped[UUID]=mapped_column(U,primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(U,ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    actor_id:Mapped[UUID]=mapped_column(U,nullable=False)
    template_code:Mapped[str]=mapped_column(String(32),nullable=False)
    version:Mapped[int]=mapped_column(Integer,nullable=False)
    snapshot_json:Mapped[str]=mapped_column(Text,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

class AgentWorkflow(Base):
    __tablename__='agent_workflows'
    __table_args__=(ForeignKeyConstraint(['actor_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_ext_agent_actor'),
                     CheckConstraint("status IN ('prepared','authorized','cancelled')",name='ck_ext_agent_status'))
    id:Mapped[UUID]=mapped_column(U,primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(U,ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    actor_id:Mapped[UUID]=mapped_column(U,nullable=False)
    agent_kind:Mapped[str]=mapped_column(String(32),nullable=False)
    input_json:Mapped[str]=mapped_column(Text,nullable=False)
    result_json:Mapped[str]=mapped_column(Text,nullable=False)
    status:Mapped[str]=mapped_column(String(16),nullable=False,server_default=text("'prepared'"))
    engine_version:Mapped[str]=mapped_column(String(32),nullable=False,server_default=text("'rules-1.0'"))
    authorized_by:Mapped[UUID|None]=mapped_column(U)
    authorized_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
