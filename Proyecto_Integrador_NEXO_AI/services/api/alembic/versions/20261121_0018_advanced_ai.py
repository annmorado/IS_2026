"""RIA-006..018 model registry, simulation evidence and aggregate monitoring.

Revision ID: ai_0018
Revises: ai_0017
"""
from alembic import op
import sqlalchemy as sa
revision='ai_0018';down_revision='ai_0017';branch_labels=None;depends_on=None
U=sa.Uuid(as_uuid=True);D=sa.DateTime(timezone=True)
def actor_fk(name):
 return sa.ForeignKeyConstraint(['actor_id','organization_id'],['users.id','users.organization_id'],name=name)
def org_fk():
 return sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE')
def upgrade():
 op.create_table('ai_model_versions',
  sa.Column('id',U,primary_key=True),sa.Column('organization_id',U,nullable=False),sa.Column('actor_id',U,nullable=False),
  sa.Column('model_key',sa.String(40),nullable=False),sa.Column('version',sa.String(80),nullable=False),
  sa.Column('feature_version',sa.String(40),nullable=False),sa.Column('engine_kind',sa.String(45),nullable=False),
  sa.Column('config_json',sa.Text,nullable=False),sa.Column('config_sha256',sa.String(64),nullable=False),
  sa.Column('metrics_json',sa.Text,nullable=False),sa.Column('status',sa.String(16),server_default=sa.text("'candidate'"),nullable=False),
  sa.Column('trained_at',D,server_default=sa.func.now(),nullable=False),sa.Column('approved_at',D),
  org_fk(),actor_fk('fk_ai_model_actor_org'),
  sa.UniqueConstraint('organization_id','model_key','version',name='uq_ai_model_org_key_version'),
  sa.UniqueConstraint('id','organization_id',name='uq_ai_model_id_org'),
  sa.CheckConstraint("status IN ('candidate','active','archived','rejected')",name='ck_ai_model_status'))
 op.create_index('ix_ai_model_versions_organization_id','ai_model_versions',['organization_id'])
 op.create_index('uq_ai_active_model_per_org','ai_model_versions',['organization_id','model_key'],unique=True,
  postgresql_where=sa.text("status = 'active'"),sqlite_where=sa.text("status = 'active'"))
 op.create_table('ai_evidence_runs',
  sa.Column('id',U,primary_key=True),sa.Column('organization_id',U,nullable=False),sa.Column('actor_id',U,nullable=False),
  sa.Column('model_id',U),sa.Column('kind',sa.String(20),nullable=False),
  sa.Column('engine_version',sa.String(80),nullable=False),sa.Column('feature_version',sa.String(40),nullable=False),
  sa.Column('config_sha256',sa.String(64),nullable=False),sa.Column('input_json',sa.Text,nullable=False),
  sa.Column('result_json',sa.Text,nullable=False),sa.Column('created_at',D,server_default=sa.func.now(),nullable=False),
  org_fk(),actor_fk('fk_ai_run_actor_org'),
  sa.ForeignKeyConstraint(['model_id','organization_id'],['ai_model_versions.id','ai_model_versions.organization_id'],name='fk_ai_run_model_org'),
  sa.CheckConstraint("kind IN ('forecast','optimization','agent','digital_twin')",name='ck_ai_run_kind'))
 op.create_index('ix_ai_evidence_runs_organization_id','ai_evidence_runs',['organization_id'])
 op.create_index('ix_ai_runs_org_kind_created','ai_evidence_runs',['organization_id','kind','created_at'])
 op.create_table('ai_quality_windows',
  sa.Column('id',U,primary_key=True),sa.Column('organization_id',U,nullable=False),sa.Column('actor_id',U,nullable=False),
  sa.Column('model_id',U),sa.Column('version',sa.String(80),nullable=False),sa.Column('metrics_json',sa.Text,nullable=False),
  sa.Column('created_at',D,server_default=sa.func.now(),nullable=False),
  org_fk(),actor_fk('fk_ai_quality_actor_org'),
  sa.ForeignKeyConstraint(['model_id','organization_id'],['ai_model_versions.id','ai_model_versions.organization_id'],name='fk_ai_quality_model_org'))
 op.create_index('ix_ai_quality_windows_organization_id','ai_quality_windows',['organization_id'])
def downgrade():
 for t in ('ai_quality_windows','ai_evidence_runs','ai_model_versions'):
  if t=='ai_model_versions':op.drop_index('uq_ai_active_model_per_org',table_name=t)
  op.drop_index('ix_'+t+'_organization_id',table_name=t)
  if t=='ai_evidence_runs':op.drop_index('ix_ai_runs_org_kind_created',table_name=t)
  op.drop_table(t)
