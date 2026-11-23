import pathlib
import tempfile

import pytest


@pytest.fixture()
def 临时库(monkeypatch):
    """每个用例独立 sqlite 库，互不污染；夹具目录沿用仓库 fixtures。"""
    数据 = pathlib.Path(tempfile.mkdtemp(prefix="lw-data-"))
    import app.db as db
    from app import seed

    monkeypatch.setattr(db, "数据目录", 数据)
    monkeypatch.setattr(db, "库路径", 数据 / "播浪.db")
    monkeypatch.setattr(db, "夹具目录", pathlib.Path("/workspace/fixtures"))
    seed.初始化库()
    yield db.连接
