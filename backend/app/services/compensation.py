from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException

from app.db import connect, rows_to_dicts, transaction

DOC_TYPE = "补偿回拨"


class CompensationConflict(Exception):
    """补偿校验失败：整单必须回滚，不能留下部分回拨。"""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conflict_message(conflict: CompensationConflict) -> str:
    return f"{conflict}；整单已回滚，业务键归属未发生任何变更"


def _load(conn, compensation_id: int) -> dict:
    row = conn.execute(
        """
        SELECT c.*,
               fs.name AS from_shift_name,
               ts.name AS to_shift_name,
               h.from_shift_id AS handover_from_shift_id,
               h.to_shift_id AS handover_to_shift_id,
               h.status AS handover_status
        FROM compensations c
        JOIN shifts fs ON fs.id = c.from_shift_id
        JOIN shifts ts ON ts.id = c.to_shift_id
        JOIN handovers h ON h.id = c.handover_id
        WHERE c.id = ?
        """,
        (compensation_id,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "补偿单不存在")
    out = dict(row)
    items = conn.execute(
        """
        SELECT ci.*, b.status AS batch_status, b.owner_shift_id AS owner_shift_id_now
        FROM compensation_items ci
        JOIN batches b ON b.id = ci.batch_id
        WHERE ci.compensation_id = ?
        ORDER BY ci.batch_id
        """,
        (compensation_id,),
    ).fetchall()
    out["items"] = rows_to_dicts(items)
    out["doc_type"] = DOC_TYPE
    out["doc_no"] = f"补偿单#{compensation_id}"
    out["related_doc_no"] = f"交班单#{out['handover_id']}"
    return out


def list_compensations(status: str | None = None) -> list[dict]:
    with connect() as conn:
        if status is None:
            rows = conn.execute(
                """
                SELECT c.*,
                       fs.name AS from_shift_name,
                       ts.name AS to_shift_name
                FROM compensations c
                JOIN shifts fs ON fs.id = c.from_shift_id
                JOIN shifts ts ON ts.id = c.to_shift_id
                ORDER BY c.id DESC
                """
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT c.*,
                       fs.name AS from_shift_name,
                       ts.name AS to_shift_name
                FROM compensations c
                JOIN shifts fs ON fs.id = c.from_shift_id
                JOIN shifts ts ON ts.id = c.to_shift_id
                WHERE c.status = ?
                ORDER BY c.id DESC
                """,
                (status,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["doc_type"] = DOC_TYPE
            d["doc_no"] = f"补偿单#{d['id']}"
            d["related_doc_no"] = f"交班单#{d['handover_id']}"
            out.append(d)
        return out


def get_compensation(compensation_id: int) -> dict:
    with connect() as conn:
        return _load(conn, compensation_id)


def list_compensable(handover_id: int) -> list[dict]:
    """该正向交班单里仍可回拨的业务键：仍在原接班方名下、且在途。

    已成功回拨过的键不会再出现在这里（此时归属已回到原交班方）。
    """
    with connect() as conn:
        h = conn.execute("SELECT * FROM handovers WHERE id = ?", (handover_id,)).fetchone()
        if not h:
            raise HTTPException(404, "交班单不存在")
        rows = conn.execute(
            """
            SELECT b.id AS batch_id, b.biz_key, b.title, b.owner_shift_id
            FROM handover_items hi
            JOIN batches b ON b.id = hi.batch_id
            WHERE hi.handover_id = ?
              AND b.status = '在途'
              AND b.owner_shift_id = ?
            ORDER BY b.id
            """,
            (handover_id, h["to_shift_id"]),
        ).fetchall()
        return rows_to_dicts(rows)


def _assert_exclusive(conn) -> None:
    """全局互斥：进行中的补偿与进行中的正向交班不能并存。"""
    active_handover = conn.execute(
        "SELECT id FROM handovers WHERE status = '进行中' LIMIT 1"
    ).fetchone()
    if active_handover:
        raise HTTPException(
            409,
            f"交班单#{active_handover['id']} 正在进行中，禁止同时办理补偿回拨",
        )
    active_comp = conn.execute(
        "SELECT id FROM compensations WHERE status = '进行中' LIMIT 1"
    ).fetchone()
    if active_comp:
        raise HTTPException(
            409, f"补偿单#{active_comp['id']} 正在进行中，禁止同时办理正向交班或补偿"
        )


def create_compensation(handover_id: int, biz_keys: list[str], reason: str = "") -> dict:
    keys = [k.strip() for k in biz_keys if isinstance(k, str) and k.strip()]
    # 去重但保留用户给定顺序，便于错误消息点名
    keys = list(dict.fromkeys(keys))
    if not keys:
        raise HTTPException(400, "至少指定一个要回拨的业务键")

    with transaction() as conn:
        h = conn.execute("SELECT * FROM handovers WHERE id = ?", (handover_id,)).fetchone()
        if not h:
            raise HTTPException(404, "交班单不存在")
        if h["status"] != "已完成":
            raise HTTPException(409, f"只有已完成的交班单才能补偿，交班单#{handover_id} 当前为{h['status']}")
        _assert_exclusive(conn)

        placeholders = ",".join("?" * len(keys))
        rows = conn.execute(
            f"""
            SELECT b.id, b.biz_key, b.title, b.owner_shift_id, b.status
            FROM batches b
            WHERE b.biz_key IN ({placeholders})
            """,
            keys,
        ).fetchall()
        found = {r["biz_key"]: r for r in rows}

        missing = [k for k in keys if k not in found]
        if missing:
            raise HTTPException(400, f"业务键不属于该交班单或不存在：{'、'.join(missing)}")

        in_handover = {
            r["biz_key"]
            for r in conn.execute(
                """
                SELECT b.biz_key
                FROM handover_items hi
                JOIN batches b ON b.id = hi.batch_id
                WHERE hi.handover_id = ?
                """,
                (handover_id,),
            )
        }
        not_in_handover = [k for k in keys if k not in in_handover]
        if not_in_handover:
            raise HTTPException(
                400, f"业务键不在交班单#{handover_id} 的清单内：{'、'.join(not_in_handover)}"
            )

        already = [
            r["biz_key"]
            for r in conn.execute(
                """
                SELECT ci.biz_key
                FROM compensation_items ci
                JOIN compensations c ON c.id = ci.compensation_id
                WHERE c.handover_id = ? AND c.status = '已完成'
                """,
                (handover_id,),
            )
            if r["biz_key"] in keys
        ]
        if already:
            raise HTTPException(
                409, f"业务键已回拨过，不能重复补偿：{'、'.join(already)}"
            )

        not_returnable = [
            k
            for k in keys
            if found[k]["status"] != "在途" or found[k]["owner_shift_id"] != h["to_shift_id"]
        ]
        if not_returnable:
            raise HTTPException(
                400, f"业务键当前不在接班方名下或非在途，无法回拨：{'、'.join(not_returnable)}"
            )

        cur = conn.execute(
            """
            INSERT INTO compensations(
              handover_id, from_shift_id, to_shift_id, status,
              key_count, reason, started_at
            ) VALUES (?, ?, ?, '进行中', ?, ?, ?)
            """,
            (
                handover_id,
                h["to_shift_id"],    # 回拨方 = 原接班方（现持有方）
                h["from_shift_id"],  # 接收方 = 原交班方
                len(keys),
                reason or "",
                _now(),
            ),
        )
        cid = cur.lastrowid
        for key in keys:
            row = found[key]
            conn.execute(
                """
                INSERT INTO compensation_items(
                  compensation_id, batch_id, biz_key, title, owner_shift_id_before
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (cid, row["id"], row["biz_key"], row["title"], row["owner_shift_id"]),
            )

    return get_compensation(cid)


def _apply_compensation_updates(conn, batch_ids: list[int], to_shift_id: int) -> int:
    """回拨写入的唯一出口；返回实际更新的行数。

    单独成函数是为了让测试可以替换它来验证「部分更新后失败」也会整单回滚。
    """
    placeholders = ",".join("?" * len(batch_ids))
    cur = conn.execute(
        f"""
        UPDATE batches
        SET owner_shift_id = ?
        WHERE id IN ({placeholders}) AND status = '在途'
        """,
        (to_shift_id, *batch_ids),
    )
    return cur.rowcount


def _in_transit_keys(conn, shift_id: int) -> list[str]:
    rows = conn.execute(
        """
        SELECT biz_key FROM batches
        WHERE owner_shift_id = ? AND status = '在途'
        ORDER BY biz_key
        """,
        (shift_id,),
    ).fetchall()
    return [r["biz_key"] for r in rows]


def _batch_ids_of_shift(conn, shift_id: int) -> set[int]:
    rows = conn.execute(
        "SELECT id FROM batches WHERE owner_shift_id = ? AND status = '在途'",
        (shift_id,),
    ).fetchall()
    return {r["id"] for r in rows}


def _fail(compensation_id: int, reason: str) -> None:
    """事务回滚之后另开短事务落失败原因；只覆盖仍处于进行中的单据。

    落失败本身失败时也不能吞掉原始错误：调用方仍会抛出冲突响应。
    """
    try:
        with transaction() as conn:
            conn.execute(
                """
                UPDATE compensations
                SET status = '失败', reason = ?, finished_at = ?
                WHERE id = ? AND status = '进行中'
                """,
                (reason, _now(), compensation_id),
            )
    except Exception:  # noqa: BLE001 - 补偿单状态写入是尽力而为，不覆盖原始失败原因
        pass


def complete_compensation(compensation_id: int) -> dict:
    try:
        with transaction() as conn:
            comp = conn.execute(
                "SELECT * FROM compensations WHERE id = ?", (compensation_id,)
            ).fetchone()
            if not comp:
                raise HTTPException(404, "补偿单不存在")
            if comp["status"] != "进行中":
                raise HTTPException(400, "只能完成进行中的补偿单")

            active_handover = conn.execute(
                "SELECT id FROM handovers WHERE status = '进行中' LIMIT 1"
            ).fetchone()
            if active_handover:
                # 数据异常才会到这里：正向交班与补偿建立时本就互斥。
                # 不标记补偿单失败，保持进行中，待交班结束后可重试。
                raise HTTPException(
                    409,
                    f"交班单#{active_handover['id']} 正在进行中，无法完成补偿回拨",
                )

            items = conn.execute(
                """
                SELECT ci.batch_id, ci.biz_key, ci.owner_shift_id_before,
                       b.status, b.owner_shift_id
                FROM compensation_items ci
                JOIN batches b ON b.id = ci.batch_id
                WHERE ci.compensation_id = ?
                ORDER BY ci.batch_id
                """,
                (compensation_id,),
            ).fetchall()
            if not items:
                raise CompensationConflict("补偿单没有清单，拒绝完成")

            stale = [
                it["biz_key"]
                for it in items
                if it["status"] != "在途" or it["owner_shift_id"] != comp["from_shift_id"]
            ]
            if stale:
                raise CompensationConflict(
                    "以下业务键已不在回拨方名下或非在途："
                    + "、".join(stale)
                )

            from_id = comp["from_shift_id"]
            to_id = comp["to_shift_id"]
            batch_ids = [it["batch_id"] for it in items]
            n = len(batch_ids)

            before_from = conn.execute(
                "SELECT COUNT(*) AS c FROM batches WHERE owner_shift_id = ? AND status = '在途'",
                (from_id,),
            ).fetchone()["c"]
            before_to = conn.execute(
                "SELECT COUNT(*) AS c FROM batches WHERE owner_shift_id = ? AND status = '在途'",
                (to_id,),
            ).fetchone()["c"]
            before_sets = {
                "from": _in_transit_keys(conn, from_id),
                "to": _in_transit_keys(conn, to_id),
            }
            before_ids = {
                "from": _batch_ids_of_shift(conn, from_id),
                "to": _batch_ids_of_shift(conn, to_id),
            }

            updated = _apply_compensation_updates(conn, batch_ids, to_id)
            if updated != n:
                raise CompensationConflict(
                    f"回拨更新行数 {updated} 与清单 {n} 不符"
                )

            landed = {
                r["id"]: r["owner_shift_id"]
                for r in conn.execute(
                    "SELECT id, owner_shift_id FROM batches WHERE id IN ("
                    + ",".join("?" * n)
                    + ")",
                    batch_ids,
                )
            }
            wrong = [bid for bid, owner in landed.items() if owner != to_id]
            if wrong:
                raise CompensationConflict(
                    f"回拨后仍有批次未归属原交班方：{wrong}"
                )

            after_from = conn.execute(
                "SELECT COUNT(*) AS c FROM batches WHERE owner_shift_id = ? AND status = '在途'",
                (from_id,),
            ).fetchone()["c"]
            after_to = conn.execute(
                "SELECT COUNT(*) AS c FROM batches WHERE owner_shift_id = ? AND status = '在途'",
                (to_id,),
            ).fetchone()["c"]
            if after_from != before_from - n:
                raise CompensationConflict(
                    f"回拨方在途数应为 {before_from - n}，实际 {after_from}"
                )
            if after_to != before_to + n:
                raise CompensationConflict(
                    f"接收方在途数应为 {before_to + n}，实际 {after_to}"
                )
            after_sets = {
                "from": _in_transit_keys(conn, from_id),
                "to": _in_transit_keys(conn, to_id),
            }
            after_ids = {
                "from": _batch_ids_of_shift(conn, from_id),
                "to": _batch_ids_of_shift(conn, to_id),
            }

            # 同源校验：报告里的前后在途集合必须与补偿清单逐键吻合，
            # 不能出现「清单说回拨了、集合里却没动」的口径分叉。
            moved_ids = set(batch_ids)
            if not moved_ids <= before_ids["from"]:
                raise CompensationConflict("清单批次不在回拨方回拨前的在途集合内")
            if after_ids["from"] != before_ids["from"] - moved_ids:
                raise CompensationConflict("回拨方在途集合与清单不一致")
            if after_ids["to"] != before_ids["to"] | moved_ids:
                raise CompensationConflict("接收方在途集合与清单不一致")

            conn.execute(
                "UPDATE compensations SET status = '已完成', finished_at = ? WHERE id = ?",
                (_now(), compensation_id),
            )

            detail = {
                "单据类型": DOC_TYPE,
                "原交班单": f"交班单#{comp['handover_id']}",
                "回拨方": {"班次": comp["from_shift_id"], "回拨前在途": before_sets["from"], "回拨后在途": after_sets["from"]},
                "接收方": {"班次": comp["to_shift_id"], "回拨前在途": before_sets["to"], "回拨后在途": after_sets["to"]},
                "清单": [
                    {
                        "业务键": it["biz_key"],
                        "批次ID": it["batch_id"],
                        "回拨前归属": it["owner_shift_id_before"],
                        "回拨后归属": to_id,
                    }
                    for it in items
                ],
                "回拨前计数": {"回拨方": before_from, "接收方": before_to},
                "回拨后计数": {"回拨方": after_from, "接收方": after_to},
            }
            conn.execute(
                """
                INSERT INTO reconcile_reports(
                  handover_id, before_count, after_from_count, after_to_count,
                  consistent, detail_json, created_at, doc_type, compensation_id
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                """,
                (
                    comp["handover_id"],
                    n,
                    after_from,
                    after_to,
                    json.dumps(detail, ensure_ascii=False),
                    _now(),
                    DOC_TYPE,
                    compensation_id,
                ),
            )
    except HTTPException:
        # 单据不存在 / 状态不对 / 互斥冲突：没有产生回拨动作，不改单据状态。
        raise
    except CompensationConflict as conflict:
        _fail(compensation_id, str(conflict))
        raise HTTPException(409, _conflict_message(conflict)) from conflict
    except Exception as exc:  # noqa: BLE001 - 任何写入异常都必须整单回滚并落失败
        _fail(compensation_id, f"补偿写入失败：{exc}")
        raise HTTPException(
            409, f"补偿完成失败：{exc}；整单已回滚，业务键归属未发生任何变更"
        ) from exc
    # 读取放在事务与异常处理之外：提交已成功，读失败不应被误报为回拨失败。
    return get_compensation(compensation_id)
