
from fastapi import APIRouter

router = APIRouter(
    prefix="/health",
    tags=["Health"]
)


@router.get(
    "",
    summary="Consultar estado de NEXO AI",
    description="Comprueba si la API está funcionando."
)
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "nexo-ai-api",
        "version": "0.1.0"
    }
