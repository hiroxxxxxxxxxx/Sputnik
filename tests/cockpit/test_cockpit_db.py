"""Cockpit の DB 結合・SemiAuto・執行ロックのテスト。"""
from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import date

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


def _run(coro):
    return asyncio.run(coro)


def _make_cockpit(conn, *, approval_mode="Manual"):
    """DB の ap_mode を先に設定してから Cockpit を生成する。"""
    from store.mode import update_ap_mode

    update_ap_mode(conn, approval_mode)

    from avionics.flight_controller import FlightController

    fc = FlightController(
        global_market_factors=[],
        global_capital_factors=[],
        symbol_factors={},
    )
    from cockpit.cockpit import Cockpit

    return Cockpit(
        fc=fc,
        engines=[],
        initial_mode="Boost",
        conn=conn,
    )


def test_cockpit_restores_approval_mode_from_db(conn) -> None:
    from store.mode import update_ap_mode

    update_ap_mode(conn, "SemiAuto")
    cp = _make_cockpit(conn, approval_mode="SemiAuto")
    assert cp.approval_mode == "SemiAuto"


def test_cockpit_restores_execution_lock_from_db(conn) -> None:
    from store.mode import update_execution_lock

    update_execution_lock(conn, True)
    cp = _make_cockpit(conn)
    assert cp.execution_lock is True


def test_cockpit_persists_mode_on_dispatch(conn) -> None:
    cp = _make_cockpit(conn, approval_mode="Auto")
    signal = FlightControllerSignal(scl=0, lcl=0, nq_icl=1)

    _run(cp.on_flight_controller_signal(signal))
    assert cp.current_mode == "Cruise"


def test_cockpit_semiauto_emergency_auto_dispatch(conn) -> None:
    """SemiAuto: Emergency(Lv2) は即時実行。"""
    cp = _make_cockpit(conn, approval_mode="SemiAuto")
    signal = FlightControllerSignal(scl=0, lcl=2)

    _run(cp.on_flight_controller_signal(signal))
    assert cp.current_mode == "Emergency"


def test_cockpit_semiauto_cruise_needs_approval(conn) -> None:
    """SemiAuto: Cruise(Lv1) は承認待ち。"""
    cp = _make_cockpit(conn, approval_mode="SemiAuto")
    signal = FlightControllerSignal(scl=0, lcl=0, nq_icl=1)

    assert not cp._should_auto_dispatch(signal)


def test_execution_lock_skips_engine_apply(conn) -> None:
    """execution_lock ON 時はプロトコル実行をスキップする。"""
    cp = _make_cockpit(conn, approval_mode="Auto")
    cp.execution_lock = True

    signal = FlightControllerSignal(scl=0, lcl=2)
    _run(cp.on_flight_controller_signal(signal))
    assert cp.current_mode == "Emergency"

    from store.mode import read_mode

    m = read_mode(conn)
    assert m["execution_lock"] == 1


def test_approval_mode_setter_persists(conn) -> None:
    cp = _make_cockpit(conn)
    cp.approval_mode = "Auto"

    from store.mode import read_mode

    m = read_mode(conn)
    assert m["ap_mode"] == "Auto"


def test_cockpit_pulse_applies_with_ib_positions_and_target_futures(conn) -> None:
    from store.state import upsert_target_futures

    upsert_target_futures(conn, "Main", 8.0)
    upsert_target_futures(conn, "Attitude", 2.0)
    upsert_target_futures(conn, "Booster", 0.0)

    class DummyEngine:
        symbol_type = "NQ"

        def __init__(self) -> None:
            self.calls = []

        async def apply_mode(self, mode, *, actual_by_part=None, target_futures_by_part=None):
            self.calls.append((mode, actual_by_part, target_futures_by_part))

    class MockFlightController:
        async def refresh(self, data_source, as_of, symbols, *, altitude):
            return None

        async def get_flight_controller_signal(self):
            return FlightControllerSignal(scl=0, lcl=0, nq_icl=1)

    class MockDataSource:
        async def fetch_position_legs(self, symbols):
            assert symbols == ["NQ"]
            return {"NQ": {"future": 5.0, "k1": 1.0, "k2": -1.0}}

    cp = _make_cockpit(conn, approval_mode="Auto")
    engine = DummyEngine()
    cp.fc = MockFlightController()
    cp.engines = [engine]

    _run(cp.pulse(MockDataSource(), as_of=date(2025, 1, 1), symbols=["NQ"]))
    assert len(engine.calls) == 1
    mode, actual_by_part, target_futures_by_part = engine.calls[0]
    assert mode == "Cruise"
    assert target_futures_by_part["Main"] == 8.0
    assert actual_by_part["Main"]["future"] > actual_by_part["Attitude"]["future"]
