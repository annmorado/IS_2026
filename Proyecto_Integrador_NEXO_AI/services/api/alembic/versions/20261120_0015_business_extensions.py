"""RF-023 a RF-027: collaborators, purchasing, calendar, notifications.

Revision ID: business_0015
Revises: decisions_0014
"""
from alembic import op
import sqlalchemy as sa
revision='business_0015'
down_revision='decisions_0014'
branch_labels=None
depends_on=None
U=sa.Uuid(as_uuid=True)

def upgrade():
    op.add_column('users',sa.Column('permissions_json',sa.Text,nullable=True))
    op.create_table('collaborator_invites',
        sa.Column('id',U,primary_key=True),sa.Column('organization_id',U,nullable=False),
        sa.Column('created_by_user_id',U,nullable=False),sa.Column('email',sa.String(254),nullable=False),
        sa.Column('permissions_json',sa.Text,nullable=False),sa.Column('token_hash',sa.String(64),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('consumed_at',sa.DateTime(timezone=True)),
        sa.Column('revoked_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_invite_creator_tenant'),
        sa.UniqueConstraint('organization_id','token_hash',name='uq_invite_hash_org'),
    )
    op.create_index('ix_collaborator_invites_organization_id','collaborator_invites',['organization_id'])
    op.create_table('suppliers',
        sa.Column('id',U,primary_key=True),sa.Column('organization_id',U,nullable=False),
        sa.Column('code',sa.String(64),nullable=False),sa.Column('name',sa.String(160),nullable=False),
        sa.Column('contact_email',sa.String(254)),sa.Column('active',sa.Boolean,nullable=False,server_default=sa.text('true')),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE'),
        sa.UniqueConstraint('id','organization_id',name='uq_supplier_id_org'),
        sa.UniqueConstraint('organization_id','code',name='uq_supplier_code_org'),
    )
    op.create_index('ix_suppliers_organization_id','suppliers',['organization_id'])
    op.create_table('purchase_requests',
        sa.Column('id',U,primary_key=True),sa.Column('organization_id',U,nullable=False),
        sa.Column('supplier_id',U,nullable=False),sa.Column('material_id',U,nullable=False),
        sa.Column('quantity',sa.Numeric(15,3),nullable=False),sa.Column('unit_cost_mxn',sa.Numeric(12,2),nullable=False),
        sa.Column('status',sa.String(16),nullable=False,server_default=sa.text("'pending'")),
        sa.Column('comment',sa.String(500)),sa.Column('created_by_user_id',U,nullable=False),
        sa.Column('decided_by_user_id',U),sa.Column('decision_note',sa.String(500)),
        sa.Column('decided_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['supplier_id','organization_id'],['suppliers.id','suppliers.organization_id'],ondelete='CASCADE',name='fk_purchase_supplier_tenant'),
        sa.ForeignKeyConstraint(['material_id','organization_id'],['materials.id','materials.organization_id'],name='fk_purchase_material_tenant'),
        sa.ForeignKeyConstraint(['created_by_user_id','organization_id'],['users.id','users.organization_id'],name='fk_purchase_creator_tenant'),
        sa.ForeignKeyConstraint(['decided_by_user_id','organization_id'],['users.id','users.organization_id'],name='fk_purchase_decider_tenant'),
        sa.CheckConstraint('quantity > 0 AND unit_cost_mxn >= 0',name='ck_purchase_amounts'),
        sa.CheckConstraint("status IN ('pending','approved','rejected')",name='ck_purchase_status'),
        sa.UniqueConstraint('id','organization_id',name='uq_purchase_id_org'),
    )
    op.create_index('ix_purchase_requests_organization_id','purchase_requests',['organization_id'])
    op.create_table('resource_allocations',
        sa.Column('id',U,primary_key=True),sa.Column('organization_id',U,nullable=False),
        sa.Column('resource_id',U,nullable=False),sa.Column('order_id',U,nullable=False),
        sa.Column('day',sa.Date,nullable=False),sa.Column('quantity',sa.Numeric(12,3),nullable=False),
        sa.Column('created_by_user_id',U,nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resource_id','organization_id'],['production_resources.id','production_resources.organization_id'],ondelete='CASCADE',name='fk_allocation_resource_org'),
        sa.ForeignKeyConstraint(['order_id','organization_id'],['orders.id','orders.organization_id'],ondelete='CASCADE',name='fk_allocation_order_org'),
        sa.ForeignKeyConstraint(['created_by_user_id','organization_id'],['users.id','users.organization_id'],name='fk_allocation_actor_org'),
        sa.UniqueConstraint('resource_id','order_id','day',name='uq_allocation_resource_order_day'),
        sa.CheckConstraint('quantity > 0',name='ck_allocation_quantity_positive'),
    )
    op.create_index('ix_resource_allocations_organization_id','resource_allocations',['organization_id'])
    op.create_index('ix_resource_allocations_day','resource_allocations',['day'])
    op.create_table('notification_preferences',
        sa.Column('user_id',U,primary_key=True),sa.Column('organization_id',U,nullable=False),
        sa.Column('due_soon',sa.Boolean,nullable=False),sa.Column('risk',sa.Boolean,nullable=False),
        sa.Column('material_shortage',sa.Boolean,nullable=False),
        sa.ForeignKeyConstraint(['user_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_notify_pref_user_tenant'),
    )
    op.create_index('ix_notification_preferences_organization_id','notification_preferences',['organization_id'])
    op.create_table('business_notifications',
        sa.Column('id',U,primary_key=True),sa.Column('organization_id',U,nullable=False),
        sa.Column('user_id',U,nullable=False),sa.Column('kind',sa.String(32),nullable=False),
        sa.Column('source_key',sa.String(160),nullable=False),sa.Column('message',sa.String(500),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('read_at',sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id','organization_id'],['users.id','users.organization_id'],ondelete='CASCADE',name='fk_notify_user_tenant'),
        sa.UniqueConstraint('user_id','kind','source_key',name='uq_notify_user_kind_source'),
    )
    op.create_index('ix_business_notifications_organization_id','business_notifications',['organization_id'])
    op.create_index('ix_business_notifications_user_id','business_notifications',['user_id'])

def downgrade():
    op.drop_table('business_notifications')
    op.drop_table('notification_preferences')
    op.drop_table('resource_allocations')
    op.drop_table('purchase_requests')
    op.drop_table('suppliers')
    op.drop_table('collaborator_invites')
    op.drop_column('users','permissions_json')
