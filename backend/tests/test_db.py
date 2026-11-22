from fastapi.testclient import TestClient

from aztarna import db
from aztarna.main import app


def test_db_created_on_startup_and_persists(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    with TestClient(app):
        assert db.path().exists()

    with db.connect() as conn:
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('x')")
    with db.connect() as conn:
        assert conn.execute("SELECT v FROM t").fetchall() == [("x",)]
