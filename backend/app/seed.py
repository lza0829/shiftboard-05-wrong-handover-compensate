from __future__ import annotations

import json
from pathlib import Path

from app.db import FIXTURES_DIR, connect


SCHEMA = """
CREATE TABLE IF NOT EXISTS shifts (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  keeper TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '空闲'
);
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY,
  biz_key TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  owner_shift_id INTEGER REFERENCES shifts(id),
  status TEXT NOT NULL DEFAULT '在途',
  note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS handovers (
  id INTEGER PRIMARY KEY,
  from_shift_id INTEGER NOT NULL REFERENCES shifts(id),
  to_shift_id INTEGER NOT NULL REFERENCES shifts(id),
  status TEXT NOT NULL,
  batch_count INTEGER NOT NULL DEFAULT 0,
  reason TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS handover_items (
  handover_id INTEGER NOT NULL REFERENCES handovers(id),
  batch_id INTEGER NOT NULL REFERENCES batches(id),
  PRIMARY KEY (handover_id, batch_id)
);
CREATE TABLE IF NOT EXISTS compensations (
  id INTEGER PRIMARY KEY,
  handover_id INTEGER NOT NULL REFERENCES handovers(id),
  from_shift_id INTEGER NOT NULL REFERENCES shifts(id),
  to_shift_id INTEGER NOT NULL REFERENCES shifts(id),
  status TEXT NOT NULL,
  key_count INTEGER NOT NULL DEFAULT 0,
  reason TEXT NOT NULL DEFAULT '',
  started_at TEXT NOT NULL,
  finished_at TEXT
);
CREATE TABLE IF NOT EXISTS compensation_items (
  compensation_id INTEGER NOT NULL REFERENCES compensations(id),
  batch_id INTEGER NOT NULL REFERENCES batches(id),
  biz_key TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  owner_shift_id_before INTEGER NOT NULL,
  PRIMARY KEY (compensation_id, batch_id)
);
CREATE TABLE IF NOT EXISTS reconcile_reports (
  id INTEGER PRIMARY KEY,
  handover_id INTEGER REFERENCES handovers(id),
  before_count INTEGER NOT NULL,
  after_from_count INTEGER NOT NULL,
  after_to_count INTEGER NOT NULL,
  consistent INTEGER NOT NULL,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  doc_type TEXT NOT NULL DEFAULT '正向交班',
  compensation_id INTEGER REFERENCES compensations(id)
);
"""

# 旧库补列：SQLite 的 ALTER TABLE ADD COLUMN 只能加带常量默认值的列。
MIGRATIONS = {
    "reconcile_reports": {
        "doc_type": "TEXT NOT NULL DEFAULT '正向交班'",
        "compensation_id": "INTEGER REFERENCES compensations(id)",
    },
}


def _migrate(conn) -> None:
    for table, columns in MIGRATIONS.items():
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        for column, ddl in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
        n = conn.execute("SELECT COUNT(*) AS c FROM shifts").fetchone()["c"]
        if n:
            return
        seed_path = FIXTURES_DIR / "seed.json"
        data = json.loads(Path(seed_path).read_text(encoding="utf-8"))
        for s in data["shifts"]:
            conn.execute(
                "INSERT INTO shifts(id, name, keeper, status) VALUES (?, ?, ?, ?)",
                (s["id"], s["name"], s["keeper"], s["status"]),
            )
        for b in data["batches"]:
            conn.execute(
                "INSERT INTO batches(id, biz_key, title, owner_shift_id, status, note) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    b["id"],
                    b["biz_key"],
                    b["title"],
                    b["owner_shift_id"],
                    b["status"],
                    b.get("note", ""),
                ),
            )
        conn.commit()
