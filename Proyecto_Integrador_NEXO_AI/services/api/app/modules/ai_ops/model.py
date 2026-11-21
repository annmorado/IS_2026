"""Tenant-bound immutable evidence and explicit lifecycle of baseline/candidate models."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
                        Index, Integer, String, Text, UniqueConstraint, Uuid, func, text)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class AIModelVersion(Base):
    __tablename__ = 'ai_model_versions'
    __table_args__ = (
        UniqueConstraint('organization_id', 'model_key', 'version', name='uq_ai_model_org_key_version'),
        UniqueConstraint('id', 'organization_id', name='uq_ai_model_id_org'),
        ForeignKeyConstraint(['actor_id','organization_id'], ['users.id','users.organization_id'], name='fk_ai_model_actor_org'),
        CheckConstraint("status IN ('candidate','active','archived','rejected')", name='ck_ai_model_status'),
        Index('uq_ai_active_model_per_org','organization_id','model_key',unique=True,
              postgresql_where=text("status = 'active'"),sqlite_where=text("status = 'active'")),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    model_key: Mapped[str] = mapped_column(String(40),nullable=False)
    version: Mapped[str] = mapped_column(String(80),nullable=False)
    feature_version: Mapped[str] = mapped_column(String(40),nullable=False)
    engine_kind: Mapped[str] = mapped_column(String(45),nullable=False)
    config_json: Mapped[str] = mapped_column(Text,nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64),nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text,nullable=False)
    status: Mapped[str] = mapped_column(String(16),nullable=False,server_default=text("'candidate'"))
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
    approved_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))


class AIEvidenceRun(Base):
    __tablename__ = 'ai_evidence_runs'
    __table_args__ = (
        ForeignKeyConstraint(['actor_id','organization_id'], ['users.id','users.organization_id'], name='fk_ai_run_actor_org'),
        ForeignKeyConstraint(['model_id','organization_id'], ['ai_model_versions.id','ai_model_versions.organization_id'], name='fk_ai_run_model_org'),
        CheckConstraint("kind IN ('forecast','optimization','agent','digital_twin')",name='ck_ai_run_kind'),
        Index('ix_ai_runs_org_kind_created','organization_id','kind','created_at'),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True,default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    model_id: Mapped[UUID|None] = mapped_column(Uuid(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(20),nullable=False)
    engine_version: Mapped[str] = mapped_column(String(80),nullable=False)
    feature_version: Mapped[str] = mapped_column(String(40),nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64),nullable=False)
    input_json: Mapped[str] = mapped_column(Text,nullable=False)
    result_json: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())


class AIQualityWindow(Base):
    __tablename__ = 'ai_quality_windows'
    __table_args__ = (
        ForeignKeyConstraint(['actor_id','organization_id'], ['users.id','users.organization_id'],name='fk_ai_quality_actor_org'),
        ForeignKeyConstraint(['model_id','organization_id'], ['ai_model_versions.id','ai_model_versions.organization_id'],name='fk_ai_quality_model_org'),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    model_id: Mapped[UUID|None] = mapped_column(Uuid(as_uuid=True))
    version: Mapped[str] = mapped_column(String(80),nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
