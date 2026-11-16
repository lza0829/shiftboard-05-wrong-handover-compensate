from __future__ import annotations

from app.db import connect
from app.services import compensation as comp_svc
from app.services import handover as ho_svc


def list_records() -> list[dict]:
    """交班记录页的统一单据流：正向交班 + 补偿回拨，按单据类型区分。"""
    forward = []
    for h in ho_svc.list_handovers():
        forward.append(
            {
                "kind": "forward",
                "doc_type": "正向交班",
                "doc_no": h["doc_no"],
                "id": h["id"],
                "related_doc_no": None,
                "from_shift_name": h["from_shift_name"],
                "to_shift_name": h["to_shift_name"],
                "count": h["batch_count"],
                "count_label": "批次数",
                "status": h["status"],
                "started_at": h["started_at"],
                "finished_at": h["finished_at"],
                "reason": h["reason"],
            }
        )
    compensation = []
    for c in comp_svc.list_compensations():
        compensation.append(
            {
                "kind": "compensation",
                "doc_type": c["doc_type"],
                "doc_no": c["doc_no"],
                "id": c["id"],
                "related_doc_no": c["related_doc_no"],
                "from_shift_name": c["from_shift_name"],
                "to_shift_name": c["to_shift_name"],
                "count": c["key_count"],
                "count_label": "业务键数",
                "status": c["status"],
                "started_at": c["started_at"],
                "finished_at": c["finished_at"],
                "reason": c["reason"],
            }
        )
    records = forward + compensation
    records.sort(key=lambda r: (r["started_at"], r["kind"]), reverse=True)
    return records
