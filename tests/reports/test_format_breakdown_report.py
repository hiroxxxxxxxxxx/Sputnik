from __future__ import annotations

from datetime import date

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
    PriceSignals,
    SignalBundle,
    VolatilitySignal,
)
from reports.format_breakdown_report import (
    BREAKDOWN_HIT_LEGEND,
    format_breakdown_report,
)


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
    assert "[6-B] S（SPAN）" in text
    assert "S whatIf total | 1800.00" in text
    assert "S baseline total | 1500.00" in text
    assert "S total ratio (whatIf/base) | 1.20" in text
    assert "S NQ (whatIf/base/ratio) | 1200.00 / 1000.00 / 1.20" in text
    assert "S GC (whatIf/base/ratio) | 600.00 / 500.00 / 1.20" in text


def test_format_breakdown_report_without_positions_detail() -> None:
    fc = _DummyFC()
    text = format_breakdown_report(fc)
    assert "[7] POSITION SNAPSHOT" not in text
    assert BREAKDOWN_HIT_LEGEND in text
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
    assert "S whatIf total | N/A" in text
    assert "S baseline total | N/A" in text
    assert "S total ratio (whatIf/base) | N/A" in text
    assert "S NQ (whatIf/base/ratio) | N/A / N/A / N/A" in text
    assert "S GC (whatIf/base/ratio) | N/A / N/A / N/A" in text


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
    assert "S whatIf total | N/A" in text
    assert "S baseline total | 1500.00" in text
    assert "S total ratio (whatIf/base) | N/A" in text
    assert "S NQ (whatIf/base/ratio) | 1200.00 / 1000.00 / 1.20" in text
    assert "S GC (whatIf/base/ratio) | N/A / 500.00 / N/A" in text
    assert "S GC reason | ValueError: No Trading Permission" in text


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
    assert "ボラ指数 (VXN/GVZ 相当) | 42.00 ★" in text
    assert "V2→V1復帰判定 | 1/2日目 ★" in text
    assert "C（HYG） [ C=2 ]" in text
    assert "SMA20乖離率 | -1.20% ★" in text
    assert "日次変化率 | -3.00% ★" in text
    assert "[4] R（TIP） [ R=2 ]" in text
    assert "20日高値乖離率 | -3.00% ★" in text


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
    # level がスナップショット分類とずれている場合は見出しは factor.level を正とし、注釈で知らせる。
    p.level = 0
    fc._mapping = EngineFactorMapping(
        symbol_factors={"NQ": [p]},
        limit_factors=[],
        global_market_factors=[],
    )

    text = format_breakdown_report(fc)
    assert "P/T 入力 <NQ> [ P=0 T=— ]" in text
    assert "表示時点の因子レベルと最新行分類が一致しません" in text
    assert "トレンド | down ★" in text
    assert "5日累積変動率 | -4.00% ★" in text
    assert "20日高値乖離率 | -4.00% ★" in text
    assert "日次変化率 | 0.00%" in text
    assert "日次変化率 | 0.00% ★" not in text


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
    assert "表示時点の因子レベルと最新行分類が一致しません" not in text
    assert "トレンド | up ★" not in text
    assert "日次変化率 | 1.00% ★" not in text
    assert "5日累積変動率 | 2.00% ★" not in text
    assert "20日高値乖離率 | 2.00% ★" not in text
