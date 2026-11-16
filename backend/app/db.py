from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))
FIXTURES_DIR = Path(
    os.environ.get("FIXTURES_DIR", Path(__file__).resolve().parents[2] / "fixtures")
)
DB_PATH = DATA_DIR / "app.db"


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """以 BEGIN IMMEDIATE 开事务：校验与写入在同一把写锁内完成。

    成功提交、异常回滚，最后一定关闭连接。连接关闭时 sqlite3 的隐式事务
    行为不再生效（isolation_level=None），事务边界完全由这里控制。
    """
    conn = connect()
    conn.isolation_level = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        else:
            conn.commit()
    finally:
        conn.close()


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]
