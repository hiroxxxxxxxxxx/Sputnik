"""target_futures セッターの関数テスト。"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parent.parent.parent
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))


@pytest.fixture()
def conn():
    from store.db import get_connection

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    old = os.environ.get("SPUTNIK_DB_PATH")
    os.environ["SPUTNIK_DB_PATH"] = db_path
    c = get_connection()
    yield c
    c.close()
    os.unlink(db_path)
    if old is not None:
        os.environ["SPUTNIK_DB_PATH"] = old
    elif "SPUTNIK_DB_PATH" in os.environ:
        del os.environ["SPUTNIK_DB_PATH"]


def _seed_full_targets(conn: sqlite3.Connection) -> None:
    from store.state import upsert_target_futures

    for sym in ("NQ", "GC"):
        upsert_target_futures(conn, sym, 1.0)


def test_set_target_futures_function(conn: sqlite3.Connection) -> None:
    from store.state import read_target_futures
    from store.target_futures import set_target_futures

    _seed_full_targets(conn)
    set_target_futures(conn, "NQ", base=8.0)
    current = read_target_futures(conn)
    assert current["NQ"] == 8.0
    assert current["GC"] == 1.0


def test_set_target_futures_validate_missing_raises() -> None:
    from store.target_futures import validate_target_futures_input

    with pytest.raises(ValueError):
        validate_target_futures_input(base=None)


def test_normalize_engine_symbol_raises() -> None:
    from store.target_futures import normalize_engine_symbol

    with pytest.raises(ValueError, match="NQ or GC"):
        normalize_engine_symbol("ES")


def test_normalize_engine_symbol_mnq_mgc_alias() -> None:
    from store.target_futures import normalize_engine_symbol

    assert normalize_engine_symbol("mnq") == "NQ"
    assert normalize_engine_symbol("MGC") == "GC"


