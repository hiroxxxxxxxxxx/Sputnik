"""SQLite 接続・マイグレーションのテスト。"""
from __future__ import annotations

import os
from pathlib import Path

from store.db import get_connection, get_db_path


def test_get_db_path_default() -> None:
    """SPUTNIK_DB_PATH 未設定時はプロジェクトルートの data/sputnik.db。"""
    if "SPUTNIK_DB_PATH" in os.environ:
        del os.environ["SPUTNIK_DB_PATH"]
    path = get_db_path()
    assert path.name == "sputnik.db"
    assert path.parent.name == "data"


def test_get_db_path_env() -> None:
    """SPUTNIK_DB_PATH が設定されていればそのパス。"""
    os.environ["SPUTNIK_DB_PATH"] = "/tmp/sputnik_test.db"
    try:
        path = get_db_path()
        assert path == Path("/tmp/sputnik_test.db").resolve()
    finally:
        del os.environ["SPUTNIK_DB_PATH"]


def test_get_connection_applies_migrations() -> None:
    """get_connection で schema_version が 1 以上になる。"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        assert row is not None
        assert row[0] >= 1
    finally:
        conn.close()
