"""RF-016: endpoint exclusivamente de simulacion, sin escritura productiva."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import AuthContext
from app.modules.authorization.dependencies import require_owner
from app.modules.scenarios.schemas import ScenarioInput, ScenarioResult
from app.modules.scenarios.service import evaluate
from app.modules.tenancy.scope import scope_from_context

router = APIRouter(prefix="/simulations", tags=["RF-016 Simulacion editable"])


@router.post("/evaluate", response_model=ScenarioResult)
def evaluate_scenario(
    payload: ScenarioInput,
    context: AuthContext = Depends(require_owner),
    db: Session = Depends(get_db),
):
    return evaluate(db, scope_from_context(context), payload)
