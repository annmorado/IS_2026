"""RIA-001..005: supervised audio STT, grounded structured data and baseline estimates.

Revision ID: ai_0017
Revises: extensions_0016
"""
from alembic import op
import sqlalchemy as sa

revision='ai_0017'
down_revision='extensions_0016'
branch_labels=None
depends_on=None
U=sa.Uuid(as_uuid=True)
D=sa.DateTime(timezone=True)


def org_fk():
    return sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE')


def actor_fk(name):
    return sa.ForeignKeyConstraint(['actor_id','organization_id'],['users.id','users.organization_id'],name=name)


def upgrade():
    op.create_table('ai_transcription_jobs',
        sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),
        sa.Column('actor_id',U,nullable=False),
        sa.Column('voice_note_id',U,sa.ForeignKey('voice_notes.id',ondelete='CASCADE'),nullable=False),
        sa.Column('status',sa.String(16),nullable=False,server_default=sa.text("'queued'")),
        sa.Column('engine',sa.String(64),nullable=False,server_default=sa.text("'whisper-local'")),
        sa.Column('language',sa.String(8),nullable=False,server_default=sa.text("'es'")),
        sa.Column('duration_ms',sa.Integer),
        sa.Column('attempt_count',sa.Integer,nullable=False,server_default=sa.text('1')),
        sa.Column('transcript',sa.Text),
        sa.Column('reviewed_text',sa.Text),
        sa.Column('error_code',sa.String(40)),
        sa.Column('created_at',D,nullable=False,server_default=sa.func.now()),
        sa.Column('completed_at',D),
        org_fk(),actor_fk('fk_ai_transcript_actor_tenant'),
        sa.UniqueConstraint('organization_id','voice_note_id',name='uq_ai_transcription_note_tenant'),
        sa.CheckConstraint("status IN ('queued','processing','completed','failed','cancelled','reviewed')",name='ck_ai_transcription_status'),
        sa.CheckConstraint('attempt_count >= 1 AND attempt_count <= 3',name='ck_ai_transcription_attempts'))
    op.create_index('ix_ai_transcription_jobs_org','ai_transcription_jobs',['organization_id'])
    op.create_table('ai_structured_extractions',
        sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),
        sa.Column('actor_id',U,nullable=False),
        sa.Column('source_text',sa.String(5000),nullable=False),
        sa.Column('fields_json',sa.Text,nullable=False),
        sa.Column('extractor_version',sa.String(64),nullable=False),
        sa.Column('reviewed_json',sa.Text),
        sa.Column('reviewed_at',D),
        sa.Column('created_at',D,nullable=False,server_default=sa.func.now()),
        org_fk(),actor_fk('fk_ai_extract_actor_tenant'),
        sa.CheckConstraint('length(trim(source_text)) > 0 AND length(source_text) <= 5000',name='ck_ai_source_length'))
    op.create_index('ix_ai_structured_extractions_org','ai_structured_extractions',['organization_id'])
    op.create_table('ai_fulfillment_estimates',
        sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),
        sa.Column('actor_id',U,nullable=False),
        sa.Column('product_id',U,nullable=False),
        sa.Column('engine_version',sa.String(64),nullable=False),
        sa.Column('feature_version',sa.String(32),nullable=False),
        sa.Column('input_json',sa.Text,nullable=False),
        sa.Column('result_json',sa.Text,nullable=False),
        sa.Column('created_at',D,nullable=False,server_default=sa.func.now()),
        org_fk(),actor_fk('fk_ai_estimate_actor_tenant'),
        sa.ForeignKeyConstraint(['product_id','organization_id'],
                                ['products.id','products.organization_id'],name='fk_ai_estimate_product_tenant'))
    op.create_index('ix_ai_fulfillment_estimates_org','ai_fulfillment_estimates',['organization_id'])


def downgrade():
    for table in ('ai_fulfillment_estimates','ai_structured_extractions','ai_transcription_jobs'):
        op.drop_index('ix_'+table+'_org',table_name=table)
        op.drop_table(table)
