"""
Emergency プロトコルのテスト。

Protocol は Engine に apply_mode("Emergency") を依頼するだけ。step 概念は排除。定義書「6-2」「Phase 4」参照。
"""

from __future__ import annotations

import asyncio

import pytest

from avionics import Cockpit, EmergencyProtocol, FlightController
from engines.engine import Engine
from engines.factory import _default_blueprints, build_nq_engine


@pytest.fixture
def engine_with_fc() -> tuple[FlightController, Engine]:
    """FlightController と 1 エンジン（Blueprint ベース）を返す。"""
    cockpit = Cockpit(global_market_factors=[], global_capital_factors=[], symbol_factors={})
    fc = FlightController(cockpit=cockpit, engines=[], initial_mode="Cruise")
    engine = build_nq_engine(
        fc,
        blueprints=_default_blueprints(),
        config={"base_unit": 1.0, "boost_ratio": 1.0},
    )
    fc.engines.append(engine)
    return fc, engine


def test_emergency_protocol_run_applies_emergency_to_engines(engine_with_fc: tuple[FlightController, Engine]) -> None:
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


def test_emergency_protocol_engines_property(engine_with_fc: tuple[FlightController, Engine]) -> None:
    """protocol.engines で対象エンジン群を取得できる。"""
    _, engine = engine_with_fc
    protocol = EmergencyProtocol(engines=[engine])
    assert protocol.engines == [engine]


def test_fc_pulse_entering_emergency_runs_protocol(engine_with_fc: tuple[FlightController, Engine]) -> None:
    """FlightController.pulse で Emergency に遷移すると、コールバック未設定時は EmergencyProtocol が実行される。"""
    fc, _ = engine_with_fc
    class MockEmergencyEvaluator:
        async def update_all(self, signal_bundle=None) -> None:
            pass
        async def get_throttle_mode(self, symbol: str) -> str:
            return "Emergency"
    fc.cockpit = MockEmergencyEvaluator()  # type: ignore[assignment]
    asyncio.run(fc.pulse())
    assert fc.current_mode == "Emergency"
