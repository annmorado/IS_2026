"""RF-024: Supplier directory and explicit purchase proposal approval."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID,uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Numeric, String, UniqueConstraint, Uuid, func, text
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base

class Supplier(Base):
    __tablename__='suppliers'
    __table_args__=(UniqueConstraint('id','organization_id',name='uq_supplier_id_org'),UniqueConstraint('organization_id','code',name='uq_supplier_code_org'))
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey('organizations.id',ondelete='CASCADE'),index=True,nullable=False)
    code:Mapped[str]=mapped_column(String(64),nullable=False)
    name:Mapped[str]=mapped_column(String(160),nullable=False)
    contact_email:Mapped[str|None]=mapped_column(String(254))
    active:Mapped[bool]=mapped_column(nullable=False,server_default=text('true'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())

class PurchaseRequest(Base):
    __tablename__='purchase_requests'
    __table_args__=(
        UniqueConstraint('id','organization_id',name='uq_purchase_id_org'),
        ForeignKeyConstraint(['supplier_id','organization_id'],['suppliers.id','suppliers.organization_id'],ondelete='CASCADE',name='fk_purchase_supplier_tenant'),
        ForeignKeyConstraint(['material_id','organization_id'],['materials.id','materials.organization_id'],name='fk_purchase_material_tenant'),
        ForeignKeyConstraint(['created_by_user_id','organization_id'],['users.id','users.organization_id'],name='fk_purchase_creator_tenant'),
        ForeignKeyConstraint(['decided_by_user_id','organization_id'],['users.id','users.organization_id'],name='fk_purchase_decider_tenant'),
        CheckConstraint('quantity > 0 AND unit_cost_mxn >= 0',name='ck_purchase_amounts'),
        CheckConstraint("status IN ('pending','approved','rejected')",name='ck_purchase_status'),
    )
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    supplier_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False)
    material_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False)
    quantity:Mapped[Decimal]=mapped_column(Numeric(15,3),nullable=False)
    unit_cost_mxn:Mapped[Decimal]=mapped_column(Numeric(12,2),nullable=False)
    status:Mapped[str]=mapped_column(String(16),nullable=False,server_default=text("'pending'"))
    comment:Mapped[str|None]=mapped_column(String(500))
    created_by_user_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False)
    decided_by_user_id:Mapped[UUID|None]=mapped_column(Uuid(as_uuid=True))
    decision_note:Mapped[str|None]=mapped_column(String(500))
    decided_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
