"""RF-025: explicit resource/day order allocation; no implied scheduling."""
from datetime import date,datetime
from decimal import Decimal
from uuid import UUID,uuid4
from sqlalchemy import CheckConstraint,Date,DateTime,ForeignKey,ForeignKeyConstraint,Numeric,UniqueConstraint,Uuid,func
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base

class ResourceAllocation(Base):
    __tablename__='resource_allocations'
    __table_args__=(
        UniqueConstraint('resource_id','order_id','day',name='uq_allocation_resource_order_day'),
        ForeignKeyConstraint(['resource_id','organization_id'],['production_resources.id','production_resources.organization_id'],ondelete='CASCADE',name='fk_allocation_resource_org'),
        ForeignKeyConstraint(['order_id','organization_id'],['orders.id','orders.organization_id'],ondelete='CASCADE',name='fk_allocation_order_org'),
        ForeignKeyConstraint(['created_by_user_id','organization_id'],['users.id','users.organization_id'],name='fk_allocation_actor_org'),
        CheckConstraint('quantity > 0',name='ck_allocation_quantity_positive'),
    )
    id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    organization_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),ForeignKey('organizations.id',ondelete='CASCADE'),nullable=False,index=True)
    resource_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False)
    order_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False)
    day:Mapped[date]=mapped_column(Date,nullable=False,index=True)
    quantity:Mapped[Decimal]=mapped_column(Numeric(12,3),nullable=False)
    created_by_user_id:Mapped[UUID]=mapped_column(Uuid(as_uuid=True),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
