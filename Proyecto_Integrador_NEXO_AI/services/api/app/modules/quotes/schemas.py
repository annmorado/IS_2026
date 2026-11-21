"""Contratos estrictos RF-013: cantidades y dinero con Decimal, sin precios del cliente."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class QuoteTaxUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tax_percent: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)

class QuoteTaxRead(BaseModel):
    configured: bool
    tax_percent: Decimal | None

class QuoteLineInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)

class QuoteCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    order_id: UUID
    discount_percent: Decimal = Field(default=Decimal('0'), ge=0, le=100, max_digits=5, decimal_places=2)
    items: list[QuoteLineInput] = Field(min_length=1, max_length=30)

    @model_validator(mode='after')
    def unique_products(self):
        if len({item.product_id for item in self.items}) != len(self.items):
            raise ValueError('No repitas productos: usa una sola partida por producto')
        return self

class QuoteLineRead(BaseModel):
    product_id: UUID
    product_sku: str
    product_name: str
    unit: str
    quantity: Decimal
    unit_price: Decimal
    unit_cost: Decimal
    line_subtotal: Decimal
    line_direct_cost: Decimal

class QuoteTotals(BaseModel):
    currency: Literal['MXN'] = 'MXN'
    discount_percent: Decimal
    tax_percent: Decimal
    subtotal: Decimal
    discount_amount: Decimal
    taxable_base: Decimal
    tax_amount: Decimal
    total: Decimal
    direct_cost: Decimal
    estimated_gross_margin: Decimal
    items: list[QuoteLineRead]

class QuoteRead(QuoteTotals):
    id: UUID
    organization_id: UUID
    order_id: UUID
    version: int
    status: Literal['draft', 'approved']
    created_by_user_id: UUID
    approved_by_user_id: UUID | None
    created_at: datetime
    approved_at: datetime | None
