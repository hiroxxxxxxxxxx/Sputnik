from __future__ import annotations

from datetime import date

from cockpit.mode import BOOST
from avionics.data.factor_mapping import EngineFactorMapping
from avionics.data.raw_types import RawCapitalSnapshot
from avionics.data.signals import (
    CapitalSignals,
    LiquiditySignals,
    PriceSignals,
    SignalBundle,
)
from reports.format_breakdown_report import format_breakdown_report


class _DummyFC:
    def __init__(self) -> None:
        self._bundle = SignalBundle(
            liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
            liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
            price_signals={
                "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
                "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
            },
            volatility_signals={},
            capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
        )
        self._capital = RawCapitalSnapshot(as_of=date(2026, 3, 30), mm=100_000.0, nlv=1_000_000.0, base_density=1.0, current_value=1_000_000.0)
        self._mapping = EngineFactorMapping(symbol_factors={"NQ": [], "GC": []}, limit_factors=[], global_market_factors=[])

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


def test_format_breakdown_report_with_positions_detail() -> None:
    fc = _DummyFC()
    positions_detail = {
        "NQ": {
            "futures": {"nq_buy": 2.0, "nq_sell": 1.0, "mnq_buy": 10.0, "mnq_sell": 2.0},
            "options": {"nq_call_buy": 1.0, "nq_call_sell": 3.0, "nq_put_buy": 0.0, "nq_put_sell": 2.0},
        }
    }
    text = format_breakdown_report(
        fc,
        positions_detail=positions_detail,
        target_base_by_symbol={"NQ": 10.0, "GC": 10.0},
        modes_by_symbol={"NQ": BOOST, "GC": BOOST},
    )
    assert "[6] POSITION SNAPSHOT" in text
    assert "━━━━━━━━ NQ ━━━━━━━━" in text
    assert "Futures target diff (MNQ/MGC 相当枚数; target / actual_net / delta)" in text
    assert "MNQ | target=" in text
    assert "actual=18" in text
    assert "PB | target=" in text
    assert "UNCLASSIFIED | actual=2 | P B=0 S=2 | C B=0 S=0" in text


def test_format_breakdown_report_without_positions_detail() -> None:
    fc = _DummyFC()
    text = format_breakdown_report(fc)
    assert "[6] POSITION SNAPSHOT" not in text
