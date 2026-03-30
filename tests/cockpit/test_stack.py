"""build_cockpit_stack のテスト。FC と Engine が同一 symbols で組み立てられることを確認する。"""

from __future__ import annotations

from cockpit.stack import build_cockpit_stack


def test_build_cockpit_stack_returns_fc_and_engines() -> None:
    """build_cockpit_stack(["NQ", "GC"]) は (FlightController, list[Engine]) を返し、engines の順は symbols に一致する。"""
    fc, engines = build_cockpit_stack(["NQ", "GC"], altitude="mid")
    assert fc is not None
    assert hasattr(fc, "get_flight_controller_signal")
    assert len(engines) == 2
    assert engines[0].symbol_type == "NQ"
    assert engines[1].symbol_type == "GC"


def test_build_cockpit_stack_single_symbol() -> None:
    """build_cockpit_stack(["NQ"]) は FC と 1 台の Engine を返す。"""
    fc, engines = build_cockpit_stack(["NQ"], altitude="mid")
    assert len(engines) == 1
    assert engines[0].symbol_type == "NQ"
