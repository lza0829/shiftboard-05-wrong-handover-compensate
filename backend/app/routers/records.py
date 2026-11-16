from fastapi import APIRouter

from app.services import records as svc
from app.services import compensation as comp_svc

router = APIRouter(tags=["交班记录与对账"])


@router.get("/records")
def get_records():
    return svc.list_records()


@router.get("/handovers/{handover_id}/compensable")
def get_compensable(handover_id: int):
    return comp_svc.list_compensable(handover_id)
