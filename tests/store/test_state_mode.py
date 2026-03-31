"""state / mode / target_futures の CRUD テスト。"""
from __future__ import annotations

import os
import sqlite3
import tempfile

import pytest


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


def test_read_state_initial(conn: sqlite3.Connection) -> None:
    from store.state import read_state

    s = read_state(conn)
    assert s["altitude"] == "mid"


def test_update_altitude(conn: sqlite3.Connection) -> None:
    from store.state import read_state, update_altitude

    update_altitude(conn, "low")
    s = read_state(conn)
    assert s["altitude"] == "low"
    assert s["altitude_changed_at"] is not None


def test_update_altitude_same_value_noop(conn: sqlite3.Connection) -> None:
    from store.state import read_state, update_altitude

    before = read_state(conn)
    update_altitude(conn, "mid")
    after = read_state(conn)
    assert before["altitude"] == after["altitude"]


def test_target_futures_crud(conn: sqlite3.Connection) -> None:
    from store.state import read_target_futures, upsert_target_futures

    for sym in ("NQ", "GC"):
        upsert_target_futures(conn, sym, 5.0)
    targets = read_target_futures(conn)
    assert targets["NQ"] == 5.0
    assert targets["GC"] == 5.0

    upsert_target_futures(conn, "NQ", 7.0)
    targets = read_target_futures(conn)
    assert targets["NQ"] == 7.0
    assert targets["GC"] == 5.0


def test_read_mode_initial(conn: sqlite3.Connection) -> None:
    from store.mode import read_mode

    m = read_mode(conn)
    assert m["ap_mode"] == "Manual"
    assert m["execution_lock"] == 0


def test_s_factor_baseline_crud(conn: sqlite3.Connection) -> None:
    from store.state import read_s_factor_baseline, upsert_s_factor_baseline

    upsert_s_factor_baseline(conn, "NQ", 1234.0)
    upsert_s_factor_baseline(conn, "GC", 567.0)
    rows = read_s_factor_baseline(conn)
    assert rows["NQ"] == 1234.0
    assert rows["GC"] == 567.0

    upsert_s_factor_baseline(conn, "NQ", 1500.0)
    rows = read_s_factor_baseline(conn)
    assert rows["NQ"] == 1500.0


def test_db_wrapped_read_apis(conn: sqlite3.Connection) -> None:
    from store.state import (
        read_altitude_regime_from_db,
        read_s_factor_baseline_from_db,
        read_target_futures_from_db,
        upsert_s_factor_baseline,
        upsert_target_futures,
    )

    upsert_target_futures(conn, "NQ", 11.0)
    upsert_target_futures(conn, "GC", 22.0)
    upsert_s_factor_baseline(conn, "NQ", 1111.0)
    upsert_s_factor_baseline(conn, "GC", 2222.0)

    assert read_altitude_regime_from_db() == "mid"
    assert read_target_futures_from_db() == {"NQ": 11.0, "GC": 22.0}
    assert read_s_factor_baseline_from_db() == {"NQ": 1111.0, "GC": 2222.0}


def test_set_target_futures_in_db(conn: sqlite3.Connection) -> None:
    from store.state import upsert_target_futures
    from store.target_futures import set_target_futures_in_db

    upsert_target_futures(conn, "GC", 20.0)
    out = set_target_futures_in_db("mnq", base=15.0)
    assert out["NQ"] == 15.0
    assert out["GC"] == 20.0


def test_update_ap_mode(conn: sqlite3.Connection) -> None:
    from store.mode import read_mode, update_ap_mode

    update_ap_mode(conn, "SemiAuto")
    m = read_mode(conn)
    assert m["ap_mode"] == "SemiAuto"

    update_ap_mode(conn, "Auto")
    m = read_mode(conn)
    assert m["ap_mode"] == "Auto"


def test_update_execution_lock(conn: sqlite3.Connection) -> None:
    from store.mode import read_mode, update_execution_lock

    update_execution_lock(conn, True)
    m = read_mode(conn)
    assert m["execution_lock"] == 1

    update_execution_lock(conn, False)
    m = read_mode(conn)
    assert m["execution_lock"] == 0
