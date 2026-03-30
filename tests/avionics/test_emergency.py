"""
Emergency プロトコルのテスト。

Protocol は Engine に apply_mode("Emergency") を依頼するだけ。step 概念は排除。定義書「6-2」「Phase 4」参照。
"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from cockpit.cockpit import Cockpit
from avionics import FlightController
from protocols.emergency_protocol import EmergencyProtocol
from engines.engine import Engine
from engines.factory import _default_blueprints, build_nq_engine


@pytest.fixture
def engine_with_fc() -> tuple[Cockpit, Engine]:
    """Cockpit（管制）と 1 エンジン（Blueprint ベース）を返す。"""
    flight_controller = FlightController(global_market_factors=[], global_capital_factors=[], symbol_factors={})
    fc = Cockpit(fc=flight_controller, engines=[], initial_mode="Cruise")
    engine = build_nq_engine(
        blueprints=_default_blueprints(),
        config={"base_unit": 1.0, "boost_ratio": 1.0},
    )
    fc.engines.append(engine)
    return fc, engine


def test_emergency_protocol_run_applies_emergency_to_engines(engine_with_fc: tuple[Cockpit, Engine]) -> None:
    """EmergencyProtocol.run() で全エンジンに apply_mode("Emergency") が依頼され、完了する。"""
    _, engine = engine_with_fc
    messages = []
    class Notifier:
        async def info(self, msg: str) -> None:
            messages.append(msg)
    protocol = EmergencyProtocol(engines=[engine], notifier=Notifier())
    asyncio.run(protocol.run())
    assert "Emergency protocol complete" in messages


def test_emergency_protocol_empty_engines() -> None:
    """エンジンが空でも run() は完了し、通知が送られる。"""
    messages = []
    class Notifier:
        async def info(self, msg: str) -> None:
            messages.append(msg)
    protocol = EmergencyProtocol(engines=[], notifier=Notifier())
    asyncio.run(protocol.run())
    assert "Emergency protocol complete" in messages


def test_emergency_protocol_engines_property(engine_with_fc: tuple[Cockpit, Engine]) -> None:
    """protocol.engines で対象エンジン群を取得できる。"""
    _, engine = engine_with_fc
    protocol = EmergencyProtocol(engines=[engine])
    assert protocol.engines == [engine]


def test_cockpit_level_to_mode() -> None:
    """Cockpit._level_to_mode は 0/1/2 を Boost/Cruise/Emergency に写す。定義書 4-2。"""
    fc = Cockpit(
        fc=FlightController(global_market_factors=[], global_capital_factors=[], symbol_factors={}),
        engines=[],
        initial_mode="Cruise",
    )
    assert fc._level_to_mode(0) == "Boost"
    assert fc._level_to_mode(1) == "Cruise"
    assert fc._level_to_mode(2) == "Emergency"


def test_fc_pulse_entering_emergency_runs_protocol(engine_with_fc: tuple[Cockpit, Engine]) -> None:
    """Cockpit.pulse で Emergency に遷移すると、コールバック未設定時は EmergencyProtocol が実行される。"""
    from avionics.data.flight_controller_signal import FlightControllerSignal

    fc, engine = engine_with_fc
    sym = engine.symbol_type

    class _DummyDataSource:
        async def fetch_raw(self, *args: object, **kwargs: object) -> object:
            raise AssertionError("Mock FC.refresh は fetch を呼ばない")

    class MockEmergencyEvaluator:
        async def refresh(
            self,
            data_source: object,
            as_of: date,
            symbols: list[str],
            *,
            conn=None,
            altitude=None,
        ) -> None:
            pass

        async def get_flight_controller_signal(self):
            return FlightControllerSignal(scl=0, lcl=2, nq_icl=0, gc_icl=0)

    fc.fc = MockEmergencyEvaluator()  # type: ignore[assignment]
    asyncio.run(fc.pulse(_DummyDataSource(), date(2025, 1, 1), [sym], altitude="mid"))
    assert fc.current_mode == "Emergency"
