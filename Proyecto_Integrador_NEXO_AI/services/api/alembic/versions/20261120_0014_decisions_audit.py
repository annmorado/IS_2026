"""RF-018–RF-022: recomendaciones versionadas y auditoría append-only.

Revision ID: decisions_0014
Revises: pdf_0013
"""
from alembic import op
import sqlalchemy as sa

revision='decisions_0014'
down_revision='pdf_0013'
branch_labels=None
depends_on=None
U=sa.Uuid(as_uuid=True)

def upgrade():
    op.add_column('orders',sa.Column('idempotency_key',sa.String(128),nullable=True))
    op.add_column('orders',sa.Column('idempotency_hash',sa.String(64),nullable=True))
    op.create_unique_constraint('uq_order_org_actor_idempotency','orders',
        ['organization_id','created_by_user_id','idempotency_key'])
    op.add_column('quotes',sa.Column('idempotency_key',sa.String(128),nullable=True))
    op.add_column('quotes',sa.Column('idempotency_hash',sa.String(64),nullable=True))
    op.create_unique_constraint('uq_quote_org_actor_idempotency','quotes',
        ['organization_id','created_by_user_id','idempotency_key'])
    op.create_table('decision_recommendations',
        sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),
        sa.Column('order_id',U,nullable=False),
        sa.Column('created_by_user_id',U,nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('engine_version',sa.String(32),nullable=False,server_default=sa.text("'rf017-v1'")),
        sa.Column('create_key',sa.String(128),nullable=False),
        sa.Column('create_hash',sa.String(64),nullable=False),
        sa.Column('input_json',sa.Text(),nullable=False),
        sa.Column('result_json',sa.Text(),nullable=False),
        sa.Column('result_hash',sa.String(64),nullable=False),
        sa.Column('expected_review_revision',sa.Integer(),nullable=False),
        sa.Column('expected_order_status',sa.String(20),nullable=False),
        sa.Column('status',sa.String(16),nullable=False,server_default=sa.text("'proposed'")),
        sa.Column('confirmed_by_user_id',U),sa.Column('confirmed_at',sa.DateTime(timezone=True)),
        sa.Column('confirmation_key',sa.String(128)),
        sa.Column('confirmation_hash',sa.String(64)),
        sa.Column('exception_reason',sa.String(500)),sa.Column('applied_json',sa.Text()),
        sa.UniqueConstraint('id','organization_id',name='uq_decision_id_org'),
        sa.UniqueConstraint('organization_id','created_by_user_id','create_key',name='uq_decision_create_key'),
        sa.UniqueConstraint('organization_id','confirmation_key',name='uq_decision_confirmation_key'),
        sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id','organization_id'],['orders.id','orders.organization_id'],
                                name='fk_decision_order_tenant',ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id','organization_id'],['users.id','users.organization_id'],
                                name='fk_decision_creator_tenant',ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['confirmed_by_user_id','organization_id'],['users.id','users.organization_id'],
                                name='fk_decision_confirmer_tenant',ondelete='CASCADE'),
        sa.CheckConstraint("status IN ('proposed','applied','rejected')",name='ck_decision_status'),
        sa.CheckConstraint('expected_review_revision >= 0',name='ck_decision_revision'),
    )
    op.create_index('ix_decision_org_created','decision_recommendations',['organization_id','created_at'])
    op.create_index('ix_decision_order','decision_recommendations',['order_id'])
    op.create_table('business_audit_events',
        sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),
        sa.Column('actor_user_id',U,nullable=False),
        sa.Column('entity_type',sa.String(40),nullable=False),
        sa.Column('entity_id',U,nullable=False),
        sa.Column('action',sa.String(80),nullable=False),
        sa.Column('before_json',sa.Text()),sa.Column('after_json',sa.Text()),
        sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['actor_user_id','organization_id'],['users.id','users.organization_id'],
                                name='fk_audit_actor_tenant',ondelete='CASCADE'),
    )
    op.create_index('ix_audit_org_time','business_audit_events',['organization_id','occurred_at'])
    op.create_index('ix_audit_org_entity','business_audit_events',['organization_id','entity_type','entity_id'])
    # El propietario también tiene una bitácora inmutable. Solo cascade interno puede limpiar un tenant.
    if op.get_bind().dialect.name == 'postgresql':
        op.execute("""CREATE FUNCTION nexo_audit_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' AND pg_trigger_depth()>1 THEN RETURN OLD; END IF;
          RAISE EXCEPTION 'La auditoria no admite UPDATE ni DELETE';
        END; $$""")
        op.execute("""CREATE TRIGGER trg_nexo_audit_immutable BEFORE UPDATE OR DELETE
            ON business_audit_events FOR EACH ROW EXECUTE FUNCTION nexo_audit_immutable()""")

def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP TRIGGER IF EXISTS trg_nexo_audit_immutable ON business_audit_events')
        op.execute('DROP FUNCTION IF EXISTS nexo_audit_immutable()')
    op.drop_index('ix_audit_org_entity','business_audit_events')
    op.drop_index('ix_audit_org_time','business_audit_events')
    op.drop_table('business_audit_events')
    op.drop_index('ix_decision_order','decision_recommendations')
    op.drop_index('ix_decision_org_created','decision_recommendations')
    op.drop_table('decision_recommendations')
    op.drop_constraint('uq_quote_org_actor_idempotency','quotes',type_='unique')
    op.drop_column('quotes','idempotency_hash')
    op.drop_column('quotes','idempotency_key')
    op.drop_constraint('uq_order_org_actor_idempotency','orders',type_='unique')
    op.drop_column('orders','idempotency_hash')
    op.drop_column('orders','idempotency_key')
