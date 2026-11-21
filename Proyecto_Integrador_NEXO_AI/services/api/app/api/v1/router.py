from fastapi import APIRouter

from app.api.v1.endpoints import health
from app.modules.organizations.router import router as organizations_router
from app.modules.auth.router import router as auth_router
from app.modules.authorization.router import router as authorization_router
from app.modules.tenancy.router import router as tenancy_router
from app.modules.products.router import router as products_router
from app.modules.materials.router import materials_router, recipe_router
from app.modules.capacity.router import router as capacity_router
from app.modules.orders.router import router as orders_router

api_router = APIRouter()
api_router.include_router(health.router)
# Route /organizations/me must precede the bootstrap /organizations/{id} route.
api_router.include_router(authorization_router)
api_router.include_router(organizations_router)
api_router.include_router(auth_router)
api_router.include_router(tenancy_router)
api_router.include_router(products_router)

api_router.include_router(materials_router)
api_router.include_router(recipe_router)
api_router.include_router(capacity_router)

from app.modules.order_search.router import router as order_search_router
api_router.include_router(order_search_router)  # RF-012: ruta estatica antes de /{order_id}
api_router.include_router(orders_router)
from app.modules.voice_notes.router import router as voice_notes_router
from app.modules.review.router import router as review_router
api_router.include_router(voice_notes_router)

api_router.include_router(review_router)

from app.modules.order_status.router import router as order_status_router
api_router.include_router(order_status_router)

from app.modules.quotes.router import router as quotes_router
api_router.include_router(quotes_router)

from app.modules.quote_documents.router import router as quote_documents_router
api_router.include_router(quote_documents_router)

from app.modules.scenarios.router import router as scenarios_router
api_router.include_router(scenarios_router)

# RF-018--RF-022: recomendaciones, auditoria y panel operativo
from app.modules.decisions.router import router as decisions_router, audit_router
from app.modules.operations.router import router as operations_router
api_router.include_router(decisions_router)
api_router.include_router(audit_router)
api_router.include_router(operations_router)

# RF-023 a RF-027
from app.modules.collaborators.router import router as collaborators_router
from app.modules.purchasing.router import router as purchasing_router
from app.modules.scheduling.router import router as scheduling_router
from app.modules.notifications.router import router as notifications_router
from app.modules.reports.router import router as reports_router
api_router.include_router(collaborators_router)
api_router.include_router(purchasing_router)
api_router.include_router(scheduling_router)
api_router.include_router(notifications_router)
api_router.include_router(reports_router)

# RF-028–RF-032: planes, OCR, mensajería, plantillas y agentes supervisados
from app.modules.extensions.subscriptions import router as subscription_router
from app.modules.extensions.ocr import router as ocr_router
from app.modules.extensions.messaging import router as messaging_router
from app.modules.extensions.templates import router as sector_templates_router
from app.modules.extensions.agents import router as agent_router
for ext_router in (subscription_router, ocr_router, messaging_router, sector_templates_router, agent_router):
    api_router.include_router(ext_router)

# RIA-001..RIA-005: transcription, extraction, validation, provenance, baseline estimates
from app.modules.ai.router import router as ai_router
api_router.include_router(ai_router)

# RIA-006..RIA-018: evaluation, optimization, agent guard, governance, twin
from app.modules.ai_ops.router import router as advanced_ai_router
api_router.include_router(advanced_ai_router)
