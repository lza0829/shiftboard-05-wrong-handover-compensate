from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.services import compensation as svc

router = APIRouter(prefix="/compensations", tags=["补偿回拨"])


class CreateBody(BaseModel):
    handover_id: int = Field(..., description="原正向交班单")
    biz_keys: list[str] = Field(default_factory=list, description="要回拨的业务键")
    keys: list[str] | None = Field(default=None, description="biz_keys 的别名")
    reason: str = ""

    @field_validator("biz_keys")
    @classmethod
    def _strip_keys(cls, value: list[str]) -> list[str]:
        return [k.strip() for k in value if k.strip()]


@router.get("")
def get_compensations(status: str | None = None):
    return svc.list_compensations(status)


@router.get("/{compensation_id}")
def get_one(compensation_id: int):
    return svc.get_compensation(compensation_id)


@router.post("")
def create(body: CreateBody):
    keys = body.biz_keys or body.keys or []
    return svc.create_compensation(body.handover_id, keys, body.reason)


@router.post("/{compensation_id}/complete")
def complete(compensation_id: int):
    return svc.complete_compensation(compensation_id)
