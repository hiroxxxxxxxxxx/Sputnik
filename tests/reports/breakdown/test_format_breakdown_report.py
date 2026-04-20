from __future__ import annotations

from datetime import date

import pytest

from cockpit.mode import BOOST
from avionics.factors.c_factor import CFactor
from avionics.factors.p_factor import PFactor
from avionics.factors.r_factor import RFactor
from avionics.factors.v_factor import VFactor
from avionics.data.factor_mapping import EngineFactorMapping
from avionics.data.raw_types import RawCapitalSnapshot
from avionics.data.signals import (
    CapitalSignals,
    LiquiditySignals,
    PriceDailyRow,
    PriceSignals,
    SignalBundle,
    VolatilitySignal,
)
from reports.format_breakdown_report import format_breakdown_report


class _DummyFC:
    def __init__(self) -> None:
        self._bundle = SignalBundle(
            liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
            liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
            as_of=date(2026, 3, 30),
            price_signals={
                "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
                "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
            },
            volatility_signals={},
            capital_signals=CapitalSignals(
                mm_over_nlv=0.1,
                span_ratio=1.05,
                s_whatif_mm_per_lot={"NQ": 1200.0, "GC": 600.0},
                s_baseline_mm_per_lot={"NQ": 1000.0, "GC": 500.0},
                s_whatif_errors={},
            ),
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
    assert "[7] POSITION SNAPSHOT" in text
    assert "━━━━━━━━ NQ ━━━━━━━━" in text
    assert "Futures target diff (MNQ/MGC 相当枚数; target / actual_net / delta)" in text
    assert "MNQ | target=" in text
    assert "actual=18" in text
    assert "PB | target=" in text
    assert "UNCLASSIFIED | actual=2 | P B=0 S=2 | C B=0 S=0" in text
    assert "[6-A] U（資本使用率）" in text
    assert "使用率 (MM/NLV) | 0.10 (10.00%)" in text
    assert "MM | 100,000.00" in text
    assert "NLV | 1,000,000.00" in text
    assert "ExcessLiq (NLV-MM) | 900,000.00" in text
    assert "[6-B] S（SPAN）" in text
    assert "項目 | whatIf | baseline | ratio" in text
    assert "TOTAL | 1800.00 | 1500.00 | 1.20" in text
    assert "NQ | 1200.00 | 1000.00 | 1.20" in text
    assert "GC | 600.00 | 500.00 | 1.20" in text


def test_format_breakdown_report_without_positions_detail() -> None:
    fc = _DummyFC()
    text = format_breakdown_report(fc)
    assert "[7] POSITION SNAPSHOT" in text
    assert "※ ★ = 因子判定の決定枝に関係する入力行を示す。" in text
    assert "P/T 入力 <NQ> [ P=— T=— ]" in text
    assert "[5] T（SCL） [ SCL=0 ]" in text
    assert "NQ トレンド | up" in text
    assert "[6-A] U（資本使用率） [ U=— ]" in text
    assert "[6-B] S（SPAN） [ S=— ]" in text


def test_format_breakdown_report_span_breakdown_na_fallback() -> None:
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={},
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    text = format_breakdown_report(fc)
    assert "TOTAL | N/A | N/A | N/A" in text
    assert "NQ | N/A | N/A | N/A" in text
    assert "GC | N/A | N/A | N/A" in text


def test_format_breakdown_report_span_breakdown_partial_success() -> None:
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={},
        capital_signals=CapitalSignals(
            mm_over_nlv=0.1,
            span_ratio=0.1,
            s_whatif_mm_per_lot={"NQ": 1200.0},
            s_baseline_mm_per_lot={"NQ": 1000.0, "GC": 500.0},
            s_whatif_errors={"GC": "ValueError: No Trading Permission"},
        ),
    )
    text = format_breakdown_report(fc)
    assert "TOTAL | 1200.00 | 1500.00 | 1.20" in text
    assert "NQ | 1200.00 | 1000.00 | 1.20" in text
    assert "GC | N/A | 500.00 | N/A" in text
    assert "GC reason | PermissionError: No Trading Permission" in text


def test_format_breakdown_report_span_breakdown_all_failed_with_baseline() -> None:
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={},
        capital_signals=CapitalSignals(
            mm_over_nlv=0.1,
            span_ratio=0.1,
            s_whatif_mm_per_lot={},
            s_baseline_mm_per_lot={"NQ": 1000.0, "GC": 500.0},
            s_whatif_errors={"NQ": "ValueError: failed", "GC": "ValueError: failed"},
        ),
    )
    text = format_breakdown_report(fc)
    assert "TOTAL | N/A | 1500.00 | N/A" in text
    assert "NQ reason | ValueError: failed" in text
    assert "GC reason | ValueError: failed" in text


def test_format_breakdown_report_marks_hits_for_icl_factors() -> None:
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(
            below_sma20=True,
            daily_change=-0.03,
            last_close=77.0,
            sma20=78.0,
            sma20_gap=-0.012,
        ),
        liquidity_credit_lqd=LiquiditySignals(
            below_sma20=False,
            daily_change=0.0,
            last_close=100.0,
            sma20=99.0,
            sma20_gap=0.01,
        ),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={
            "NQ": VolatilitySignal(
                index_value=42.0,
                high_20=45.0,
                recovery_confirm_satisfied_days_v2_off=1,
                index_history=(
                    (date(2026, 3, 27), 41.0),
                    (date(2026, 3, 30), 42.0),
                ),
            ),
        },
        liquidity_tip=LiquiditySignals(
            tip_drawdown_from_high=-0.03,
            tip_reference_high=106.0,
            last_close=103.0,
        ),
    )

    v = VFactor(
        name="V",
        thresholds={
            "high": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "mid": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "low": {"V2_on": 35.0, "V2_off": 33.0, "V2_confirm_days": 2, "V1_on": 25.0, "V1_off": 23.0, "V1_confirm_days": 1},
        },
    )
    v.level = 2
    c = CFactor(name="C", thresholds={"daily_change_C2": -0.025, "confirm_days": 2})
    c.level = 2
    r = RFactor(
        name="R",
        thresholds={
            "drawdown_high_L2": -0.03,
            "drawdown_mid_L2": -0.025,
            "drawdown_low_L2": -0.02,
            "drawdown_high_L0": -0.02,
            "drawdown_mid_L0": -0.015,
            "drawdown_low_L0": -0.01,
            "confirm_days": 2,
        },
    )
    r.level = 2
    fc._mapping = EngineFactorMapping(
        symbol_factors={"NQ": [v, c], "GC": [r]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "ボラ指数 (VXN) | 42.00 ★" in text
    assert "V2→V1復帰判定 | 1/2日目 ★" in text
    assert "C（HYG） [ C=2 ]" in text
    assert "SMA20乖離率 | -1.20% ★" in text
    assert "日次変化率 | -3.00% ★" in text
    assert "[4] R（TIP） [ R=2 ]" in text
    assert "20日高値乖離率 | -3.00% ★" in text


def test_format_breakdown_report_does_not_mark_credit_hit_when_level_is_stale() -> None:
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(
            below_sma20=True,
            daily_change=0.0,
            last_close=77.0,
            sma20=78.0,
            sma20_gap=-0.012,
        ),
        liquidity_credit_lqd=LiquiditySignals(
            below_sma20=False,
            daily_change=0.0,
            last_close=100.0,
            sma20=99.0,
            sma20_gap=0.01,
        ),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={},
        liquidity_tip=LiquiditySignals(
            tip_drawdown_from_high=-0.01,
            tip_reference_high=106.0,
            last_close=105.0,
        ),
    )
    c = CFactor(name="C", thresholds={"daily_change_C2": -0.025, "confirm_days": 2})
    c.level = 0
    fc._mapping = EngineFactorMapping(
        symbol_factors={"NQ": [c]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "C（HYG） [ C=0 ]" in text
    assert "SMA20乖離率 | -1.20% ★" not in text


def test_format_breakdown_report_does_not_mark_r_hit_when_level_is_stale() -> None:
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={},
        liquidity_tip=LiquiditySignals(
            tip_drawdown_from_high=-0.03,
            tip_reference_high=106.0,
            last_close=103.0,
        ),
    )
    r = RFactor(
        name="R",
        thresholds={
            "drawdown_high_L2": -0.03,
            "drawdown_mid_L2": -0.025,
            "drawdown_low_L2": -0.02,
            "drawdown_high_L0": -0.02,
            "drawdown_mid_L0": -0.015,
            "drawdown_low_L0": -0.01,
            "confirm_days": 2,
        },
    )
    r.level = 0
    fc._mapping = EngineFactorMapping(
        symbol_factors={"GC": [r]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "[4] R（TIP） [ R=0 ]" in text
    assert "20日高値乖離率 | -3.00% ★" not in text


def test_format_breakdown_report_marks_v2_to_v1_decision_branch_inputs() -> None:
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={
            "NQ": VolatilitySignal(
                index_value=37.0,
                high_20=45.0,
                recovery_confirm_satisfied_days_v1_off=0,
                recovery_confirm_satisfied_days_v2_off=2,
                index_history=(
                    (date(2026, 3, 26), 41.0),
                    (date(2026, 3, 27), 37.5),
                    (date(2026, 3, 30), 37.0),
                ),
            ),
        },
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    v = VFactor(
        name="V",
        thresholds={
            "high": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "mid": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "low": {"V2_on": 35.0, "V2_off": 33.0, "V2_confirm_days": 2, "V1_on": 25.0, "V1_off": 23.0, "V1_confirm_days": 1},
        },
    )
    v.level = 1
    fc._mapping = EngineFactorMapping(
        symbol_factors={"NQ": [v]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "V 入力 <NQ> [ V=1 ]" in text
    assert "ボラ指数 (VXN) | 37.00 ★" in text
    assert "V2→V1復帰判定 | 2/2日目 ★" in text
    assert "V1→V0復帰判定 | 0/1日目 ★" not in text


def test_format_breakdown_report_marks_index_in_v1_hysteresis_band() -> None:
    """V1_off < index < V1_on の V1維持でも、指数は判定入力として ★ を付ける。"""
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={
            "GC": VolatilitySignal(
                index_value=28.95,
                high_20=45.51,
                recovery_confirm_satisfied_days_v1_off=0,
                index_history=(
                    (date(2026, 3, 27), 31.0),
                    (date(2026, 3, 30), 28.95),
                ),
            ),
        },
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    v = VFactor(
        name="V_GC",
        thresholds={
            "high": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "mid": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "low": {"V2_on": 35.0, "V2_off": 33.0, "V2_confirm_days": 2, "V1_on": 25.0, "V1_off": 23.0, "V1_confirm_days": 1},
        },
    )
    v.level = 1
    fc._mapping = EngineFactorMapping(
        symbol_factors={"GC": [v]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "V 入力 <GC> [ V=1 ]" in text
    assert "ボラ指数 (GVZ) | 28.95 ★" in text
    assert "V1→V0復帰判定 | 0/1日目 ★" not in text


def test_format_breakdown_report_marks_only_recovery_when_index_allows_v0() -> None:
    """index が V1_off 未満でも復帰条件で止まる場合、復帰判定のみ ★ にする。"""
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={
            "GC": VolatilitySignal(
                index_value=27.50,
                high_20=45.51,
                recovery_confirm_satisfied_days_v1_off=0,
                index_history=(
                    (date(2026, 3, 27), 31.0),
                    (date(2026, 3, 30), 27.50),
                ),
            ),
        },
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    v = VFactor(
        name="V_GC",
        thresholds={
            "high": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "mid": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "low": {"V2_on": 35.0, "V2_off": 33.0, "V2_confirm_days": 2, "V1_on": 25.0, "V1_off": 23.0, "V1_confirm_days": 1},
        },
    )
    v.level = 1
    fc._mapping = EngineFactorMapping(
        symbol_factors={"GC": [v]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "ボラ指数 (GVZ) | 27.50 ★" not in text
    assert "V1→V0復帰判定 | 0/1日目 ★" in text


def test_format_breakdown_report_raises_on_v_level_mismatch() -> None:
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(symbol="NQ", trend="up", daily_change=0.01, cum5_change=0.02, cum2_change=0.01, last_close=18000.0),
            "GC": PriceSignals(symbol="GC", trend="flat", daily_change=0.0, cum5_change=0.0, cum2_change=0.0, last_close=2300.0),
        },
        volatility_signals={
            "GC": VolatilitySignal(
                index_value=28.95,
                high_20=45.51,
                recovery_confirm_satisfied_days_v1_off=0,
                index_history=(
                    (date(2026, 3, 27), 31.0),
                    (date(2026, 3, 30), 28.95),
                ),
            ),
        },
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    v = VFactor(
        name="V_GC",
        thresholds={
            "high": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "mid": {"V2_on": 40.0, "V2_off": 38.0, "V2_confirm_days": 2, "V1_on": 30.0, "V1_off": 28.0, "V1_confirm_days": 1},
            "low": {"V2_on": 35.0, "V2_off": 33.0, "V2_confirm_days": 2, "V1_on": 25.0, "V1_off": 23.0, "V1_confirm_days": 1},
        },
    )
    v.level = 2
    fc._mapping = EngineFactorMapping(
        symbol_factors={"GC": [v]},
        limit_factors=[],
        global_market_factors=[],
    )

    with pytest.raises(ValueError, match="V breakdown mismatch"):
        _ = format_breakdown_report(fc)


def test_format_breakdown_report_p1_gap_band_also_marks_p0_trend_when_flat() -> None:
    """P1_gap_band でも P0 不合格軸（例: トレンド flat）は ★ 対象に含める。"""
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(
                symbol="NQ",
                trend="flat",
                daily_change=0.0,
                cum5_change=0.0,
                cum2_change=0.0,
                high_20_gap=-0.15,
                last_close=18000.0,
            ),
        },
        volatility_signals={},
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    p = PFactor(
        name="P_NQ",
        thresholds={
            "P2_daily_max": -0.3,
            "P2_cum2_max": -0.3,
            "P2_gap_trend": -0.5,
            "P1_daily_lo": -0.2,
            "P1_daily_hi": -0.1,
            "P1_cum5_lo": -0.2,
            "P1_cum5_hi": -0.1,
            "P1_gap_lo": -0.2,
            "P1_gap_hi": -0.1,
            "P0_daily_abs": 0.015,
            "P0_cum5_min": -0.03,
            "P0_gap_min": -0.03,
        },
    )
    p.level = 1
    fc._mapping = EngineFactorMapping(
        symbol_factors={"NQ": [p]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "20日高値乖離率 | -15.00% ★" in text
    assert "トレンド | flat ★" in text
    assert "日次変化率 | 0.00% ★" not in text


def test_format_breakdown_report_p_hits_use_snapshot_p0_keys_not_factor_cache() -> None:
    """因子の last_p0_failed_row_keys が古くても、表示 latest 行に対する P0 失敗軸で ★ を付ける。"""
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(
                symbol="NQ",
                trend="flat",
                daily_change=0.0,
                cum5_change=0.0,
                cum2_change=0.0,
                high_20_gap=-0.15,
                last_close=18000.0,
            ),
        },
        volatility_signals={},
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    p = PFactor(
        name="P_NQ",
        thresholds={
            "P2_daily_max": -0.3,
            "P2_cum2_max": -0.3,
            "P2_gap_trend": -0.5,
            "P1_daily_lo": -0.2,
            "P1_daily_hi": -0.1,
            "P1_cum5_lo": -0.2,
            "P1_cum5_hi": -0.1,
            "P1_gap_lo": -0.2,
            "P1_gap_hi": -0.1,
            "P0_daily_abs": 0.015,
            "P0_cum5_min": -0.03,
            "P0_gap_min": -0.03,
        },
    )
    p.level = 1
    p.last_classify_reason = "P1_gap_band"
    p.last_p0_failed_row_keys = frozenset({"high_20_gap"})  # 真なら trend も含むが、キャッシュが古い想定
    fc._mapping = EngineFactorMapping(
        symbol_factors={"NQ": [p]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "トレンド | flat ★" in text
    assert "20日高値乖離率 | -15.00% ★" in text


def test_format_breakdown_report_price_inputs_follow_daily_history_when_present() -> None:
    """daily_history があるとき、表と P ★ は newest-first 先頭行を正本とする（トップレベルと食い違う場合は先頭が勝つ）。"""
    d = date(2026, 3, 30)
    hist_row: PriceDailyRow = (d, 0.0, 0.0, -0.15, "up", 0.0)
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=d,
        price_signals={
            "NQ": PriceSignals(
                symbol="NQ",
                trend="flat",
                daily_change=0.0,
                cum5_change=0.0,
                cum2_change=0.0,
                high_20_gap=-0.15,
                last_close=18000.0,
                daily_history=(hist_row,),
            ),
        },
        volatility_signals={},
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    p = PFactor(
        name="P_NQ",
        thresholds={
            "P2_daily_max": -0.3,
            "P2_cum2_max": -0.3,
            "P2_gap_trend": -0.5,
            "P1_daily_lo": -0.2,
            "P1_daily_hi": -0.1,
            "P1_cum5_lo": -0.2,
            "P1_cum5_hi": -0.1,
            "P1_gap_lo": -0.2,
            "P1_gap_hi": -0.1,
            "P0_daily_abs": 0.015,
            "P0_cum5_min": -0.03,
            "P0_gap_min": -0.03,
        },
    )
    p.level = 1
    fc._mapping = EngineFactorMapping(
        symbol_factors={"NQ": [p]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "トレンド | up" in text
    assert "トレンド | flat" not in text


def test_format_breakdown_report_p1_default_marks_only_failed_p0_inputs() -> None:
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(
                symbol="NQ",
                trend="down",
                daily_change=0.0,
                cum5_change=-0.04,
                cum2_change=0.0,
                high_20_gap=-0.04,
                last_close=18000.0,
            ),
        },
        volatility_signals={},
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    p = PFactor(
        name="P_NQ",
        thresholds={
            "P2_daily_max": -0.3,
            "P2_cum2_max": -0.3,
            "P2_gap_trend": -0.5,
            "P1_daily_lo": -0.2,
            "P1_daily_hi": -0.1,
            "P1_cum5_lo": -0.2,
            "P1_cum5_hi": -0.1,
            "P1_gap_lo": -0.2,
            "P1_gap_hi": -0.1,
            "P0_daily_abs": 0.015,
            "P0_cum5_min": -0.03,
            "P0_gap_min": -0.03,
        },
    )
    # 不一致は許容せずエラーで検知する。
    p.level = 0
    fc._mapping = EngineFactorMapping(
        symbol_factors={"NQ": [p]},
        limit_factors=[],
        global_market_factors=[],
    )

    with pytest.raises(ValueError, match="P breakdown mismatch"):
        _ = format_breakdown_report(fc)


def test_format_breakdown_report_p0_relaxed_no_stars_on_price_inputs() -> None:
    """P0（P0_calm）では価格入力行に ★ を付けない。"""
    fc = _DummyFC()
    fc._bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(below_sma20=False, daily_change=0.01),
        liquidity_credit_lqd=LiquiditySignals(below_sma20=False, daily_change=0.01),
        as_of=date(2026, 3, 30),
        price_signals={
            "NQ": PriceSignals(
                symbol="NQ",
                trend="up",
                daily_change=0.01,
                cum5_change=0.02,
                cum2_change=0.0,
                high_20_gap=0.02,
                last_close=18000.0,
            ),
        },
        volatility_signals={},
        capital_signals=CapitalSignals(mm_over_nlv=0.1, span_ratio=1.05),
    )
    p = PFactor(
        name="P_NQ",
        thresholds={
            "P2_daily_max": -0.3,
            "P2_cum2_max": -0.3,
            "P2_gap_trend": -0.5,
            "P1_daily_lo": -0.2,
            "P1_daily_hi": -0.1,
            "P1_cum5_lo": -0.2,
            "P1_cum5_hi": -0.1,
            "P1_gap_lo": -0.2,
            "P1_gap_hi": -0.1,
            "P0_daily_abs": 0.015,
            "P0_cum5_min": -0.03,
            "P0_gap_min": -0.03,
        },
    )
    p.level = 0
    fc._mapping = EngineFactorMapping(
        symbol_factors={"NQ": [p]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "P/T 入力 <NQ> [ P=0 T=— ]" in text
    assert "トレンド | up ★" not in text
    assert "日次変化率 | 1.00% ★" not in text
    assert "5日累積変動率 | 2.00% ★" not in text
    assert "20日高値乖離率 | 2.00% ★" not in text
