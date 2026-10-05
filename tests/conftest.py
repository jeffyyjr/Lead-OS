import pytest

from app import store


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATABASE_URL", None)
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")
    store.init_db()
