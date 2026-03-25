"""日次 signal 永続化のテスト。"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from avionics.data.flight_controller_signal import FlightControllerSignal


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


def test_persist_signal_daily_after_refresh_writes_row(conn: sqlite3.Connection) -> None:
    from store.daily_signal import persist_signal_daily_after_refresh

    fc = MagicMock()
    fc.refresh = AsyncMock()
    fc.get_flight_controller_signal = AsyncMock(
        return_value=FlightControllerSignal(
            scl=1,
            lcl=0,
            nq_icl=1,
            gc_icl=0,
        )
    )
    ds = MagicMock()

    async def run() -> None:
        used = await persist_signal_daily_after_refresh(
            conn,
            fc,
            ds,
            ["NQ", "GC"],
            as_of=date(2025, 3, 10),
        )
        assert used == date(2025, 3, 10)

    asyncio.run(run())
    fc.refresh.assert_awaited_once()
    row = conn.execute(
        "SELECT as_of, scl, nq_icl FROM signal_daily WHERE as_of = ?",
        ("2025-03-10",),
    ).fetchone()
    assert row is not None
    assert row["scl"] == 1
    assert row["nq_icl"] == 1
