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
    assert s["effective_level"] == 0
    assert s["altitude"] == "mid"


def test_update_effective_level(conn: sqlite3.Connection) -> None:
    from store.state import read_state, update_effective_level

    update_effective_level(conn, 2)
    s = read_state(conn)
    assert s["effective_level"] == 2


def test_update_altitude_records_history(conn: sqlite3.Connection) -> None:
    from store.state import read_altitude_changes, read_state, update_altitude

    update_altitude(conn, "low")
    s = read_state(conn)
    assert s["altitude"] == "low"
    assert s["altitude_changed_at"] is not None

    changes = read_altitude_changes(conn)
    assert len(changes) == 1
    assert changes[0]["from_altitude"] == "mid"
    assert changes[0]["to_altitude"] == "low"


def test_update_altitude_same_value_noop(conn: sqlite3.Connection) -> None:
    from store.state import read_altitude_changes, update_altitude

    update_altitude(conn, "mid")
    changes = read_altitude_changes(conn)
    assert len(changes) == 0


def test_target_futures_crud(conn: sqlite3.Connection) -> None:
    from store.state import read_target_futures, upsert_target_futures

    upsert_target_futures(conn, "Main", 5.0)
    upsert_target_futures(conn, "Attitude", 2.0)
    targets = read_target_futures(conn)
    assert targets["Main"] == 5.0
    assert targets["Attitude"] == 2.0

    upsert_target_futures(conn, "Main", 7.0)
    targets = read_target_futures(conn)
    assert targets["Main"] == 7.0


def test_read_mode_initial(conn: sqlite3.Connection) -> None:
    from store.mode import read_mode

    m = read_mode(conn)
    assert m["ap_mode"] == "Manual"
    assert m["execution_lock"] == 0


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
