"""knockin_watch のCRUDテスト。"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date

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


def test_knockin_watch_create_and_set(conn: sqlite3.Connection) -> None:
    from store.knockin_watch import create_watch, get_watch_row, list_pending_symbols, set_knocked_in

    as_of = date(2026, 3, 25)
    create_watch(conn, as_of=as_of, symbol="NQ")
    row = get_watch_row(conn, as_of=as_of, symbol="NQ")
    assert row is not None
    assert row["knocked_in_bar_end"] is None

    assert list_pending_symbols(conn, as_of=as_of) == ["NQ"]

    set_knocked_in(conn, as_of=as_of, symbol="NQ", bar_end_iso="2026-03-25T11:00:00-04:00")
    row2 = get_watch_row(conn, as_of=as_of, symbol="NQ")
    assert row2 is not None
    assert row2["knocked_in_bar_end"].startswith("2026-03-25T11:00:00")
    assert list_pending_symbols(conn, as_of=as_of) == []

