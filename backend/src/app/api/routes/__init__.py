from fastapi import APIRouter

from src.app.api.routes.projects import router as projects_router
from src.app.api.routes.templates import router as templates_router
from src.app.api.routes.runs import router as runs_router
from src.app.api.routes.stream import router as stream_router
from src.app.api.routes.admin import router as admin_router
from src.app.api.routes.simulations import router as simulations_router
from src.app.api.routes.society import router as society_router
from src.app.api.routes.scenario_pairs import (
    router as scenario_pairs_router,
    audit_trail_router,
    populations_router,
)

api_router = APIRouter()
api_router.include_router(projects_router, prefix="/projects", tags=["projects"])
api_router.include_router(templates_router, prefix="/templates", tags=["templates"])
api_router.include_router(runs_router, prefix="/runs", tags=["runs"])
api_router.include_router(stream_router, prefix="/runs", tags=["stream"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(simulations_router, prefix="/simulations", tags=["simulations"])
api_router.include_router(society_router, prefix="/society", tags=["society"])
api_router.include_router(scenario_pairs_router, prefix="/scenario-pairs", tags=["scenario-pairs"])
api_router.include_router(audit_trail_router, prefix="/simulations", tags=["audit-trail"])
api_router.include_router(populations_router, prefix="/populations", tags=["populations"])
