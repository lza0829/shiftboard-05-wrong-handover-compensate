from fastapi import APIRouter

from app.routers import (
    batches,
    compensations,
    dashboard,
    handovers,
    reconcile,
    records,
    shifts,
)

api = APIRouter(prefix="/api")
api.include_router(dashboard.router)
api.include_router(shifts.router)
api.include_router(batches.router)
api.include_router(handovers.router)
api.include_router(compensations.router)
api.include_router(records.router)
api.include_router(reconcile.router)
