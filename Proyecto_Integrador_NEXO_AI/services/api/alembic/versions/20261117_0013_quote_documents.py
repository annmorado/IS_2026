"""RF-014: PDF inmutable con folio y vigencia.

Revision ID: pdf_0013
Revises: quotes_0012
"""
from alembic import op
import sqlalchemy as sa

revision='pdf_0013'
down_revision='quotes_0012'
branch_labels=None
depends_on=None
U=sa.Uuid(as_uuid=True)

def upgrade():
    op.create_table('quote_documents',
        sa.Column('id',U,primary_key=True),
        sa.Column('organization_id',U,nullable=False),
        sa.Column('quote_id',U,nullable=False),
        sa.Column('sequence_number',sa.Integer(),nullable=False),
        sa.Column('folio',sa.String(80),nullable=False),
        sa.Column('valid_until',sa.Date(),nullable=False),
        sa.Column('generated_by_user_id',U,nullable=False),
        sa.Column('generated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('sha256',sa.String(64),nullable=False),
        sa.Column('size_bytes',sa.Integer(),nullable=False),
        sa.Column('pdf_bytes',sa.LargeBinary(),nullable=False),
        sa.UniqueConstraint('quote_id','organization_id',name='uq_quote_doc_quote_org'),
        sa.UniqueConstraint('organization_id','sequence_number',name='uq_quote_doc_org_seq'),
        sa.UniqueConstraint('folio',name='uq_quote_doc_folio'),
        sa.ForeignKeyConstraint(['organization_id'],['organizations.id'],ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['quote_id','organization_id'],['quotes.id','quotes.organization_id'],
            name='fk_quote_doc_quote_tenant',ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['generated_by_user_id','organization_id'],
            ['users.id','users.organization_id'],name='fk_quote_doc_actor_tenant'),
        sa.CheckConstraint('sequence_number > 0',name='ck_quote_doc_sequence_positive'),
        sa.CheckConstraint('size_bytes > 100',name='ck_quote_doc_size_positive'),
    )

def downgrade():
    op.drop_table('quote_documents')
