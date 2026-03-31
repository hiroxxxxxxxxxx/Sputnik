from __future__ import annotations

import asyncio
from datetime import date

from avionics.data.factor_mapping import EngineFactorMapping
from avionics.data.flight_controller_signal import FlightControllerSignal
from avionics.data.raw_types import RawCapitalSnapshot
from avionics.data.signals import (
    CapitalSignals,
    LiquiditySignals,
    PriceSignals,
    SignalBundle,
    VolatilitySignal,
)
from reports.format_daily_report import format_daily_report, format_position_report


class _DummyFC:
    def __init__(self) -> None:
        self._bundle = SignalBundle(
            liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
            liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
            price_signals={
                "NQ": PriceSignals(
                    symbol="NQ",
                    trend="up",
                    daily_change=0.01,
                    cum5_change=0.02,
                    cum2_change=0.01,
                    last_close=18000.0,
                ),
                "GC": PriceSignals(
                    symbol="GC",
                    trend="flat",
                    daily_change=0.0,
                    cum5_change=0.0,
                    cum2_change=0.0,
                    last_close=2300.0,
                ),
            },
            volatility_signals={
                "NQ": VolatilitySignal(index_value=18.5),
                "GC": VolatilitySignal(index_value=14.2),
            },
            capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
        )
        self._capital = RawCapitalSnapshot(
            as_of=date(2026, 3, 30),
            mm=100_000.0,
            nlv=1_000_000.0,
            base_density=1.0,
            current_value=1_000_000.0,
        )
        self._mapping = EngineFactorMapping(
            symbol_factors={"NQ": [], "GC": []},
            limit_factors=[],
            global_market_factors=[],
        )
        self._signal = FlightControllerSignal(
            scl=0,
            lcl=0,
            nq_icl=1,
            gc_icl=0,
            nq_p=1,
            nq_v=0,
            nq_c=0,
            gc_p=0,
            gc_v=0,
            gc_r=0,
            u=0,
            s=0,
        )

    def get_last_bundle(self):
        return self._bundle

    @property
    def last_altitude_regime(self):
        return "mid"

    def get_last_capital_snapshot(self):
        return self._capital

    @property
    def mapping(self):
        return self._mapping

    async def get_flight_controller_signal(self):
        return self._signal


def test_format_daily_report_with_positions() -> None:
    fc = _DummyFC()
    positions_detail = {
        "NQ": {
            "futures": {
                "nq_buy": 2.0,
                "nq_sell": 1.0,
                "mnq_buy": 10.0,
                "mnq_sell": 2.0,
                "gc_buy": 0.0,
                "gc_sell": 0.0,
                "mgc_buy": 0.0,
                "mgc_sell": 0.0,
            },
            "options": {
                "nq_call_buy": 1.0,
                "nq_call_sell": 3.0,
                "nq_put_buy": 0.0,
                "nq_put_sell": 2.0,
                "mnq_call_buy": 0.0,
                "mnq_call_sell": 0.0,
                "mnq_put_buy": 0.0,
                "mnq_put_sell": 0.0,
                "gc_call_buy": 0.0,
                "gc_call_sell": 0.0,
                "gc_put_buy": 0.0,
                "gc_put_sell": 0.0,
                "mgc_call_buy": 0.0,
                "mgc_call_sell": 0.0,
                "mgc_put_buy": 0.0,
                "mgc_put_sell": 0.0,
            },
        },
        "GC": {
            "futures": {
                "nq_buy": 0.0,
                "nq_sell": 0.0,
                "mnq_buy": 0.0,
                "mnq_sell": 0.0,
                "gc_buy": 2.0,
                "gc_sell": 0.0,
                "mgc_buy": 1.0,
                "mgc_sell": 3.0,
            },
            "options": {
                "nq_call_buy": 0.0,
                "nq_call_sell": 0.0,
                "nq_put_buy": 0.0,
                "nq_put_sell": 0.0,
                "mnq_call_buy": 0.0,
                "mnq_call_sell": 0.0,
                "mnq_put_buy": 0.0,
                "mnq_put_sell": 0.0,
                "gc_call_buy": 0.0,
                "gc_call_sell": 1.0,
                "gc_put_buy": 2.0,
                "gc_put_sell": 0.0,
                "mgc_call_buy": 0.0,
                "mgc_call_sell": 0.0,
                "mgc_put_buy": 0.0,
                "mgc_put_sell": 0.0,
            },
        },
    }
    text = asyncio.run(
        format_daily_report(
            fc,
            ["NQ", "GC"],
            positions_detail=positions_detail,
            target_futures_by_symbol={
                "NQ": {"Main": 5.0, "Attitude": 3.0, "Booster": 2.0},
                "GC": {"Main": 5.0, "Attitude": 3.0, "Booster": 2.0},
            },
            as_of=date(2026, 3, 30),
        )
    )
    assert "[4] POSITIONS DETAIL" in text
    assert "NQ | NQ B=2 S=1 | MNQ B=10 S=2" in text
    assert "GC | GC B=2 S=0 | MGC B=1 S=3" in text
    assert "MNQ | target=10 | actual=18 | delta=-8" in text
    assert "MGC | target=10 | actual=18 | delta=-8" in text


def test_format_daily_report_without_positions() -> None:
    fc = _DummyFC()
    text = asyncio.run(format_daily_report(fc, ["NQ", "GC"], as_of=date(2026, 3, 30)))
    assert "[4] POSITIONS DETAIL" not in text


def test_format_daily_report_target_futures_missing_part_raises() -> None:
    fc = _DummyFC()
    try:
        asyncio.run(
            format_daily_report(
                fc,
                ["NQ", "GC"],
                positions_detail={"NQ": {"futures": {}, "options": {}}, "GC": {"futures": {}, "options": {}}},
                target_futures_by_symbol={
                    "NQ": {"Main": 1.0, "Attitude": 1.0, "Booster": 0.0},
                },
                as_of=date(2026, 3, 30),
            )
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "target_futures missing engine symbol" in str(e)


def test_format_position_report_with_positions() -> None:
    positions_detail = {
        "NQ": {
            "futures": {
                "nq_buy": 2.0,
                "nq_sell": 1.0,
                "mnq_buy": 10.0,
                "mnq_sell": 2.0,
                "gc_buy": 0.0,
                "gc_sell": 0.0,
                "mgc_buy": 0.0,
                "mgc_sell": 0.0,
            },
            "options": {
                "nq_call_buy": 1.0,
                "nq_call_sell": 3.0,
                "nq_put_buy": 0.0,
                "nq_put_sell": 2.0,
                "mnq_call_buy": 0.0,
                "mnq_call_sell": 0.0,
                "mnq_put_buy": 0.0,
                "mnq_put_sell": 0.0,
                "gc_call_buy": 0.0,
                "gc_call_sell": 0.0,
                "gc_put_buy": 0.0,
                "gc_put_sell": 0.0,
                "mgc_call_buy": 0.0,
                "mgc_call_sell": 0.0,
                "mgc_put_buy": 0.0,
                "mgc_put_sell": 0.0,
            },
        },
        "GC": {
            "futures": {
                "nq_buy": 0.0,
                "nq_sell": 0.0,
                "mnq_buy": 0.0,
                "mnq_sell": 0.0,
                "gc_buy": 2.0,
                "gc_sell": 0.0,
                "mgc_buy": 1.0,
                "mgc_sell": 3.0,
            },
            "options": {
                "nq_call_buy": 0.0,
                "nq_call_sell": 0.0,
                "nq_put_buy": 0.0,
                "nq_put_sell": 0.0,
                "mnq_call_buy": 0.0,
                "mnq_call_sell": 0.0,
                "mnq_put_buy": 0.0,
                "mnq_put_sell": 0.0,
                "gc_call_buy": 0.0,
                "gc_call_sell": 1.0,
                "gc_put_buy": 2.0,
                "gc_put_sell": 0.0,
                "mgc_call_buy": 0.0,
                "mgc_call_sell": 0.0,
                "mgc_put_buy": 0.0,
                "mgc_put_sell": 0.0,
            },
        },
    }
    text = asyncio.run(
        format_position_report(
            ["NQ", "GC"],
            positions_detail=positions_detail,
            target_futures_by_symbol={
                "NQ": {"Main": 5.0, "Attitude": 3.0, "Booster": 2.0},
                "GC": {"Main": 5.0, "Attitude": 3.0, "Booster": 2.0},
            },
            as_of=date(2026, 3, 30),
        )
    )
    assert "【POSITIONS】 2026-03-30" in text
    assert "NQ | NQ B=2 S=1 | MNQ B=10 S=2" in text
    assert "Options (Buy/Sell per contract)" in text
    assert "MNQ | target=10 | actual=18 | delta=-8" in text
    assert "MGC | target=10 | actual=18 | delta=-8" in text
