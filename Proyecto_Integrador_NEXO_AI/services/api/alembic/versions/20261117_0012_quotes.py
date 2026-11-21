"""RF-013: impuestos explicitos, cotizaciones versionadas y partidas.

Revision ID: quotes_0012
Revises: search_0011
"""
from alembic import op
import sqlalchemy as sa

revision = 'quotes_0012'
down_revision = 'search_0011'
branch_labels = None
depends_on = None

U = sa.Uuid(as_uuid=True)
D = sa.Numeric(16, 2)
P = sa.Numeric(5, 2)


def upgrade() -> None:
    op.create_table('quote_tax_configs',
        sa.Column('organization_id', U, nullable=False),
        sa.Column('tax_percent', P, nullable=False),
        sa.Column('updated_by_user_id', U, nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('organization_id'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by_user_id', 'organization_id'],
                                ['users.id', 'users.organization_id'], name='fk_quote_tax_editor_tenant'),
        sa.CheckConstraint('tax_percent >= 0 AND tax_percent <= 100', name='ck_quote_tax_range'),
    )
    op.create_table('quotes',
        sa.Column('id', U, primary_key=True),
        sa.Column('organization_id', U, nullable=False),
        sa.Column('order_id', U, nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft'),
        sa.Column('currency', sa.String(3), nullable=False, server_default='MXN'),
        sa.Column('discount_percent', P, nullable=False),
        sa.Column('tax_percent', P, nullable=False),
        sa.Column('subtotal', D, nullable=False),
        sa.Column('discount_amount', D, nullable=False),
        sa.Column('taxable_base', D, nullable=False),
        sa.Column('tax_amount', D, nullable=False),
        sa.Column('total', D, nullable=False),
        sa.Column('direct_cost', D, nullable=False),
        sa.Column('estimated_gross_margin', D, nullable=False),
        sa.Column('created_by_user_id', U, nullable=False),
        sa.Column('approved_by_user_id', U, nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint('id', 'organization_id', name='uq_quotes_id_org'),
        sa.UniqueConstraint('organization_id', 'order_id', 'version', name='uq_quotes_org_order_version'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id', 'organization_id'],
                                ['orders.id', 'orders.organization_id'],
                                name='fk_quotes_order_tenant', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id', 'organization_id'],
                                ['users.id', 'users.organization_id'], name='fk_quotes_creator_tenant'),
        sa.ForeignKeyConstraint(['approved_by_user_id', 'organization_id'],
                                ['users.id', 'users.organization_id'], name='fk_quotes_approver_tenant'),
        sa.CheckConstraint('version >= 1', name='ck_quotes_positive_version'),
        sa.CheckConstraint("status IN ('draft', 'approved')", name='ck_quotes_status'),
        sa.CheckConstraint('discount_percent >= 0 AND discount_percent <= 100', name='ck_quotes_discount_range'),
        sa.CheckConstraint('tax_percent >= 0 AND tax_percent <= 100', name='ck_quotes_tax_range'),
        sa.CheckConstraint('subtotal >= 0 AND discount_amount >= 0 AND taxable_base >= 0 AND tax_amount >= 0 AND total >= 0', name='ck_quotes_nonnegative_money'),
        sa.CheckConstraint('direct_cost >= 0', name='ck_quotes_nonnegative_cost'),
        sa.CheckConstraint("(status = 'draft' AND approved_by_user_id IS NULL AND approved_at IS NULL) OR (status = 'approved' AND approved_by_user_id IS NOT NULL AND approved_at IS NOT NULL)", name='ck_quotes_approval_consistent'),
    )
    op.create_index('ix_quotes_org_order_version', 'quotes', ['organization_id', 'order_id', 'version'])
    op.create_table('quote_lines',
        sa.Column('id', U, primary_key=True),
        sa.Column('quote_id', U, nullable=False),
        sa.Column('organization_id', U, nullable=False),
        sa.Column('product_id', U, nullable=False),
        sa.Column('product_sku', sa.String(64), nullable=False),
        sa.Column('product_name', sa.String(120), nullable=False),
        sa.Column('unit', sa.String(32), nullable=False),
        sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('unit_cost', sa.Numeric(12, 2), nullable=False),
        sa.Column('line_subtotal', D, nullable=False),
        sa.Column('line_direct_cost', D, nullable=False),
        sa.ForeignKeyConstraint(['quote_id', 'organization_id'],
                                ['quotes.id', 'quotes.organization_id'],
                                name='fk_quote_lines_quote_tenant', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id', 'organization_id'],
                                ['products.id', 'products.organization_id'],
                                name='fk_quote_lines_product_tenant'),
        sa.UniqueConstraint('quote_id', 'product_id', name='uq_quote_lines_product'),
        sa.CheckConstraint('quantity > 0', name='ck_quote_lines_positive_quantity'),
        sa.CheckConstraint('unit_price >= 0 AND unit_cost >= 0 AND line_subtotal >= 0 AND line_direct_cost >= 0',
                           name='ck_quote_lines_nonnegative_money'),
    )
    op.create_index('ix_quote_lines_quote_id', 'quote_lines', ['quote_id'])


def downgrade() -> None:
    op.drop_index('ix_quote_lines_quote_id', table_name='quote_lines')
    op.drop_table('quote_lines')
    op.drop_index('ix_quotes_org_order_version', table_name='quotes')
    op.drop_table('quotes')
    op.drop_table('quote_tax_configs')
