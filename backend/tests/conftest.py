from pathlib import Path
import os
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["DATA_DIR"] = str(ROOT / "backend" / "data_test")
os.environ["FIXTURES_DIR"] = str(ROOT / "fixtures")

# 统一在测试收集前清一次库，避免依赖各测试模块的导入顺序。
db_path = Path(os.environ["DATA_DIR"]) / "app.db"
if db_path.exists():
    db_path.unlink()


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c
