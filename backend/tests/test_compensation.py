"""补偿回拨：整单原子、全局互斥、单据可区分、禁止绕过。"""

from __future__ import annotations


def _db():
    from app.db import connect

    return connect()


def _seed_shifts(shift_ids: list[tuple[int, str]]) -> None:
    with _db() as conn:
        for sid, name in shift_ids:
            conn.execute(
                "INSERT INTO shifts(id, name, keeper, status) VALUES (?, ?, ?, '空闲')",
                (sid, name, f"值班人{sid}"),
            )
        conn.commit()


def _seed_batches(batch_ids: list[tuple[int, str, int, str]]) -> None:
    with _db() as conn:
        for bid, key, owner, status in batch_ids:
            conn.execute(
                """
                INSERT INTO batches(id, biz_key, title, owner_shift_id, status, note)
                VALUES (?, ?, ?, ?, ?, '')
                """,
                (bid, key, f"批次{key}", owner, status),
            )
        conn.commit()


def _owner(batch_id: int) -> tuple[int, str]:
    with _db() as conn:
        row = conn.execute(
            "SELECT owner_shift_id, status FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
    return row["owner_shift_id"], row["status"]


def _forward(client, from_id: int, to_id: int) -> int:
    r = client.post(
        "/api/handovers/start", json={"from_shift_id": from_id, "to_shift_id": to_id}
    )
    assert r.status_code == 200, r.text
    hid = r.json()["id"]
    done = client.post(f"/api/handovers/{hid}/complete")
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "已完成", done.text
    return hid


def _prepare(prefix: int) -> tuple[int, int, int, list[int], int]:
    """为每组用例准备独立班次/批次，互不影响。返回 (班次A, 班次B, 班次C, 批次, 已结清批次)。"""
    a, b, c = prefix, prefix + 1, prefix + 2
    _seed_shifts([(a, f"甲班{prefix}"), (b, f"乙班{prefix}"), (c, f"丙班{prefix}")])
    batch_ids = [prefix * 10 + i for i in range(1, 5)]
    keys = [f"K{prefix}-{i}" for i in range(1, 5)]
    _seed_batches(
        [(batch_ids[i], keys[i], a, "在途") for i in range(4)]
        + [(prefix * 10 + 9, f"K{prefix}-CLOSED", a, "已结清")]
    )
    return a, b, c, batch_ids, prefix * 10 + 9


def test_happy_path_and_compensable(client):
    a, b, c, batch_ids, closed = _prepare(101)
    hid = _forward(client, a, b)

    # 正向交班完成：四个键都归接班方
    assert all(_owner(bid) == (b, "在途") for bid in batch_ids)

    comp = client.get(f"/api/handovers/{hid}/compensable")
    assert comp.status_code == 200, comp.text
    assert [r["batch_id"] for r in comp.json()] == batch_ids

    created = client.post(
        "/api/compensations",
        json={
            "handover_id": hid,
            "biz_keys": [f"K101-1", f"K101-2"],
            "reason": "错交晚班",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "进行中"
    assert body["doc_type"] == "补偿回拨"
    assert body["doc_no"] == f"补偿单#{body['id']}"
    assert body["related_doc_no"] == f"交班单#{hid}"
    assert (body["from_shift_id"], body["to_shift_id"]) == (b, a)
    assert body["key_count"] == 2
    assert {i["biz_key"] for i in body["items"]} == {"K101-1", "K101-2"}
    assert all(i["owner_shift_id_before"] == b for i in body["items"])

    # 进行中补偿必须全局互斥正向交班，且错误写明对端单号
    blocked = client.post(
        "/api/handovers/start", json={"from_shift_id": b, "to_shift_id": c}
    )
    assert blocked.status_code == 409, blocked.text
    assert f"补偿单#{body['id']}" in blocked.text

    done = client.post(f"/api/compensations/{body['id']}/complete")
    assert done.status_code == 200, done.text
    finished = done.json()
    assert finished["status"] == "已完成"
    assert _owner(batch_ids[0]) == (a, "在途")
    assert _owner(batch_ids[1]) == (a, "在途")
    assert _owner(batch_ids[2]) == (b, "在途")
    assert _owner(batch_ids[3]) == (b, "在途")

    # 已回拨的键不再可补偿
    again = client.post(
        "/api/compensations",
        json={"handover_id": hid, "biz_keys": ["K101-1"]},
    )
    assert again.status_code == 409, again.text
    assert "K101-1" in again.text

    # 非本单业务键 / 已结清批次
    outsider = client.post(
        "/api/compensations",
        json={"handover_id": hid, "biz_keys": ["K102-1"]},
    )
    assert outsider.status_code == 400, outsider.text
    closed_key = client.post(
        "/api/compensations",
        json={"handover_id": hid, "biz_keys": ["K101-CLOSED"]},
    )
    assert closed_key.status_code == 400, closed_key.text

    # 回拨后剩余可补偿键
    left = client.get(f"/api/handovers/{hid}/compensable")
    assert left.status_code == 200
    assert {r["batch_id"] for r in left.json()} == set(batch_ids[2:])

    # 不提供手工改归属入口：只能走单据
    for method in ("patch", "put", "post"):
        r = getattr(client, method)(
            f"/api/batches/{batch_ids[2]}", json={"owner_shift_id": a}
        )
        assert r.status_code in (404, 405), (method, r.status_code, r.text)
    assert _owner(batch_ids[2]) == (b, "在途")


def test_forward_handover_blocks_compensation(client):
    a, b, c, batch_ids, _ = _prepare(201)
    hid = _forward(client, a, b)

    started = client.post(
        "/api/handovers/start", json={"from_shift_id": b, "to_shift_id": c}
    )
    assert started.status_code == 200, started.text
    fhid = started.json()["id"]

    blocked = client.post(
        "/api/compensations",
        json={"handover_id": hid, "biz_keys": ["K201-1"]},
    )
    assert blocked.status_code == 409, blocked.text
    assert f"交班单#{fhid}" in blocked.text

    # 清理：完成正向交班
    done = client.post(f"/api/handovers/{fhid}/complete")
    assert done.status_code == 200, done.text


def test_compensation_is_atomic_on_partial_failure(client, monkeypatch):
    from app.services import compensation as comp_svc

    a, b, c, batch_ids, _ = _prepare(301)
    hid = _forward(client, a, b)

    created = client.post(
        "/api/compensations",
        json={"handover_id": hid, "biz_keys": ["K301-1", "K301-2"]},
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]

    def partial_then_fail(conn, ids, to_shift_id):
        conn.execute(
            "UPDATE batches SET owner_shift_id = ? WHERE id = ? AND status = '在途'",
            (to_shift_id, ids[0]),
        )
        raise RuntimeError("注入失败")

    monkeypatch.setattr(comp_svc, "_apply_compensation_updates", partial_then_fail)

    failed = client.post(f"/api/compensations/{cid}/complete")
    assert failed.status_code == 409, failed.text
    assert "整单已回滚" in failed.text

    # 一个键都不能被部分回拨
    assert _owner(batch_ids[0]) == (b, "在途")
    assert _owner(batch_ids[1]) == (b, "在途")

    detail = client.get(f"/api/compensations/{cid}").json()
    assert detail["status"] == "失败"
    assert "注入失败" in detail["reason"]

    with _db() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM reconcile_reports WHERE compensation_id = ?",
            (cid,),
        ).fetchone()["c"]
    assert n == 0

    # 失败单不能再次完成
    again = client.post(f"/api/compensations/{cid}/complete")
    assert again.status_code == 400, again.text


def test_records_and_reconcile_distinguish_doc_types(client):
    records = client.get("/api/records").json()
    types = {r["doc_type"] for r in records}
    assert {"正向交班", "补偿回拨"} <= types

    comp_records = [r for r in records if r["doc_type"] == "补偿回拨"]
    assert comp_records
    assert all(r["related_doc_no"].startswith("交班单#") for r in comp_records)
    assert all(r["count_label"] == "业务键数" for r in comp_records)

    reports = client.get("/api/reconcile").json()
    comp_reports = [r for r in reports if r["doc_type"] == "补偿回拨"]
    assert comp_reports
    r = comp_reports[0]
    assert r["doc_no"].startswith("补偿单#")
    assert r["related_doc_no"].startswith("交班单#")
    assert r["一致"] is True
    detail = r["detail"]
    assert detail["单据类型"] == "补偿回拨"
    assert len(detail["清单"]) == r["before_count"]
    assert set(detail["回拨前计数"]) == {"回拨方", "接收方"}
    assert set(detail["回拨后计数"]) == {"回拨方", "接收方"}
    # 对账中的清单必须与补偿单清单逐键同源
    cid = int(r["doc_no"].split("#")[1])
    items = client.get(f"/api/compensations/{cid}").json()["items"]
    assert {i["biz_key"] for i in items} == {i["业务键"] for i in detail["清单"]}


def test_dashboard_counts_active_compensation(client):
    a, b, c, batch_ids, _ = _prepare(401)
    hid = _forward(client, a, b)
    created = client.post(
        "/api/compensations", json={"handover_id": hid, "biz_keys": ["K401-1"]}
    )
    assert created.status_code == 200, created.text
    dash = client.get("/api/dashboard").json()
    assert dash["进行中补偿"] == 1
    done = client.post(f"/api/compensations/{created.json()['id']}/complete")
    assert done.status_code == 200, done.text
    dash = client.get("/api/dashboard").json()
    assert dash["进行中补偿"] == 0
