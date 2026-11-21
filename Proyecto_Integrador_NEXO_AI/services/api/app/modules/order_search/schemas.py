"""RF-012: respuestas de busqueda con totales y paginacion."""
from pydantic import BaseModel, Field
from app.modules.orders.schemas import OrderRead

class OrderSearchPage(BaseModel):
    items: list[OrderRead]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
    has_more: bool
    next_offset: int | None = None
