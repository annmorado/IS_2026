"""RF-028–RF-032: subscription entitlements, OCR review, consented messaging,
sector template snapshots and read-only agent workflows.

Revision ID: extensions_0016
Revises: business_0015
"""
from alembic import op
import sqlalchemy as sa
revision='extensions_0016'
down_revision='business_0015'
branch_labels=None
depends_on=None
U=sa.Uuid(as_uuid=True)
D=sa.DateTime(timezone=True)

def owner_fk(name,actor='actor_id'):
    return sa.ForeignKeyConstraint([actor,'organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name=name)
def org_fk():
    return sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE')
def index(table):
    op.create_index('ix_'+table+'_org',table,['organization_id'])

def upgrade():
    op.create_table('organization_subscriptions',
        sa.Column('organization_id',U,primary_key=True),sa.Column('plan_code',sa.String(32),nullable=False,server_default=sa.text("'starter'")),
        sa.Column('status',sa.String(16),nullable=False,server_default=sa.text("'active'")),
        sa.Column('trial_consumed',sa.Boolean,nullable=False,server_default=sa.text('false')),
        sa.Column('trial_ends_at',D),sa.Column('created_at',D,nullable=False,server_default=sa.func.now()),org_fk(),
        sa.CheckConstraint("status IN ('active','trial','suspended','expired')",name='ck_ext_subscription_status'))
    op.create_table('extension_feature_usage',sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),sa.Column('feature',sa.String(32),nullable=False),
        sa.Column('period',sa.String(7),nullable=False),sa.Column('used',sa.Integer,nullable=False,server_default=sa.text('0')),
        org_fk(),sa.UniqueConstraint('organization_id','feature','period',name='uq_ext_feature_period'),
        sa.CheckConstraint('used >= 0',name='ck_ext_usage_nonnegative'))
    index('extension_feature_usage')
    op.create_table('ocr_document_proposals',sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),sa.Column('created_by_user_id',U,nullable=False),
        sa.Column('document_type',sa.String(24),nullable=False),sa.Column('filename',sa.String(120),nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),sa.Column('extracted_json',sa.Text,nullable=False),
        sa.Column('reviewed_json',sa.Text),sa.Column('status',sa.String(16),nullable=False,server_default=sa.text("'proposed'")),
        sa.Column('created_at',D,nullable=False,server_default=sa.func.now()),org_fk(),owner_fk('fk_ext_ocr_actor','created_by_user_id'),
        sa.CheckConstraint("status IN ('proposed','reviewed')",name='ck_ext_ocr_status'))
    index('ocr_document_proposals')
    op.create_table('messaging_integrations',sa.Column('organization_id',U,primary_key=True),
        sa.Column('provider',sa.String(32),nullable=False,server_default=sa.text("'whatsapp_cloud'")),
        sa.Column('phone_number_id',sa.String(40),nullable=False),sa.Column('enabled',sa.Boolean,nullable=False,server_default=sa.text('false')),
        sa.Column('updated_at',D,nullable=False,server_default=sa.func.now()),org_fk())
    op.create_table('messaging_consents',sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),sa.Column('actor_id',U,nullable=False),
        sa.Column('recipient_e164',sa.String(16),nullable=False),sa.Column('evidence_reference',sa.String(160),nullable=False),
        sa.Column('expires_at',D,nullable=False),sa.Column('revoked_at',D),
        sa.Column('created_at',D,nullable=False,server_default=sa.func.now()),
        org_fk(),owner_fk('fk_ext_consent_actor'),
        sa.UniqueConstraint('organization_id','recipient_e164',name='uq_ext_consent_recipient'))
    index('messaging_consents')
    op.create_table('messaging_outbound_events',sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),sa.Column('actor_id',U,nullable=False),
        sa.Column('recipient_tail',sa.String(4),nullable=False),sa.Column('consent_reference',sa.String(160),nullable=False),
        sa.Column('template_name',sa.String(80),nullable=False),sa.Column('provider_message_id',sa.String(150),nullable=False),
        sa.Column('created_at',D,nullable=False,server_default=sa.func.now()),org_fk(),owner_fk('fk_ext_msg_actor'))
    index('messaging_outbound_events')
    op.create_table('organization_sector_templates',sa.Column('organization_id',U,primary_key=True),
        sa.Column('template_code',sa.String(32),nullable=False),sa.Column('version',sa.Integer,nullable=False,server_default=sa.text('1')),
        sa.Column('config_json',sa.Text,nullable=False),sa.Column('applied_at',D,nullable=False,server_default=sa.func.now()),org_fk())
    op.create_table('sector_template_events',sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),sa.Column('actor_id',U,nullable=False),
        sa.Column('template_code',sa.String(32),nullable=False),sa.Column('version',sa.Integer,nullable=False),
        sa.Column('snapshot_json',sa.Text,nullable=False),sa.Column('created_at',D,nullable=False,server_default=sa.func.now()),
        org_fk(),owner_fk('fk_ext_template_actor'))
    index('sector_template_events')
    op.create_table('agent_workflows',sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),sa.Column('actor_id',U,nullable=False),
        sa.Column('agent_kind',sa.String(32),nullable=False),sa.Column('input_json',sa.Text,nullable=False),
        sa.Column('result_json',sa.Text,nullable=False),sa.Column('status',sa.String(16),nullable=False,server_default=sa.text("'prepared'")),
        sa.Column('engine_version',sa.String(32),nullable=False,server_default=sa.text("'rules-1.0'")),
        sa.Column('authorized_by',U),sa.Column('authorized_at',D),
        sa.Column('created_at',D,nullable=False,server_default=sa.func.now()),org_fk(),owner_fk('fk_ext_agent_actor'),
        sa.CheckConstraint("status IN ('prepared','authorized','cancelled')",name='ck_ext_agent_status'))
    index('agent_workflows')

def downgrade():
    for name in ['agent_workflows','sector_template_events','messaging_consents','messaging_outbound_events','ocr_document_proposals','extension_feature_usage']:
        op.drop_index('ix_'+name+'_org',table_name=name)
    for name in ['agent_workflows','sector_template_events','organization_sector_templates',
                 'messaging_outbound_events','messaging_consents','messaging_integrations','ocr_document_proposals',
                 'extension_feature_usage','organization_subscriptions']:
        op.drop_table(name)
