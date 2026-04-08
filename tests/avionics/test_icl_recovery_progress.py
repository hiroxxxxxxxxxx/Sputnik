"""ICL の復帰 x/N 表示統一（R/C/V）。bundle.as_of と前営業日畳み込みを検証する。"""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from avionics.data.signals import LiquiditySignals, SignalBundle, VolatilitySignal
from avionics.factors.c_factor import CFactor, _c_level_at_as_of_prev
from avionics.factors.r_factor import RFactor, r_level_from_tip_history
from avionics.factors.v_factor import VFactor, v_level_from_index_history_sync


def _run(coro):
    return asyncio.run(coro)


def test_r_recovery_stable_r0_returns_none() -> None:
    """安定 R0（前日も R0）では復帰表示なし。"""
    th = {
        "drawdown_mid_L2": -0.03,
        "drawdown_mid_L0": -0.02,
        "confirm_days": 2,
    }
    r = RFactor(name="R", thresholds=th)
    days = [date(2026, 4, i) for i in range(6, 11)]
    daily_tip = tuple((d, -0.01) for d in reversed(days))
    d0 = date(2026, 4, 10)
    tip = LiquiditySignals(
        tip_drawdown_from_high=-0.01,
        daily_history_tip=daily_tip,
    )
    bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(),
        liquidity_credit_lqd=LiquiditySignals(),
        as_of=d0,
        liquidity_tip=tip,
    )

    async def go():
        await r.apply_signal_bundle("GC", bundle, altitude="mid")

    _run(go())
    assert r.level == 0
    assert r.get_recovery_progress_from_bundle("GC", bundle, altitude="mid") is None


def test_r_recovery_completion_day_shows_nn() -> None:
    """前営業日時点 R2、当日 R0 のとき N/N。"""
    th = {
        "drawdown_mid_L2": -0.03,
        "drawdown_mid_L0": -0.02,
        "confirm_days": 2,
    }
    r = RFactor(name="R", thresholds=th)
    d_mon = date(2026, 4, 6)
    d_tue = date(2026, 4, 7)
    d_wed = date(2026, 4, 8)
    d_thu = date(2026, 4, 9)
    daily_tip_newest_first = (
        (d_thu, -0.01),
        (d_wed, -0.01),
        (d_tue, -0.04),
        (d_mon, -0.04),
    )
    tip = LiquiditySignals(
        tip_drawdown_from_high=-0.01,
        daily_history_tip=daily_tip_newest_first,
    )
    bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(),
        liquidity_credit_lqd=LiquiditySignals(),
        as_of=d_thu,
        liquidity_tip=tip,
    )

    async def go():
        await r.apply_signal_bundle("GC", bundle, altitude="mid")

    _run(go())
    assert r.level == 0
    rows_prev = [r for r in daily_tip_newest_first if r[0] <= date(2026, 4, 8)]
    assert r_level_from_tip_history(
        sorted(rows_prev, key=lambda x: x[0]), "mid", th
    ) == 2
    prog = r.get_recovery_progress_from_bundle("GC", bundle, altitude="mid")
    assert prog == (2, 2)


def test_c_recovery_stable_c0_returns_none() -> None:
    """安定 C0（前日も C0）では復帰表示なし。"""
    c_th = {"daily_change_C2": -0.025, "confirm_days": 2}
    c = CFactor(name="C", thresholds=c_th)
    d_prev = date(2026, 4, 9)
    d0 = date(2026, 4, 10)
    row_prev = (d_prev, False, 0.0)
    row_now = (d0, False, 0.0)
    hyg = (row_now, row_prev)
    lqd = (row_now, row_prev)
    credit_hyg = LiquiditySignals(
        below_sma20=False,
        daily_change=0.0,
        daily_history_credit=hyg,
    )
    credit_lqd = LiquiditySignals(
        below_sma20=False,
        daily_change=0.0,
        daily_history_credit=lqd,
    )
    bundle = SignalBundle(
        liquidity_credit_hyg=credit_hyg,
        liquidity_credit_lqd=credit_lqd,
        as_of=d0,
    )

    async def go():
        await c.apply_signal_bundle("NQ", bundle, altitude="mid")

    _run(go())
    assert c.level == 0
    assert c.get_recovery_progress_from_bundle("NQ", bundle, altitude="mid") is None


def test_c_recovery_requires_both_symbols_row_on_as_of_prev() -> None:
    c_th = {"daily_change_C2": -0.025, "confirm_days": 2}
    d0 = date(2026, 4, 10)
    hyg = ((d0, False, 0.0),)
    lqd = ()
    bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(
            below_sma20=False,
            daily_change=0.0,
            daily_history_credit=hyg,
        ),
        liquidity_credit_lqd=LiquiditySignals(
            below_sma20=False,
            daily_change=0.0,
            daily_history_credit=lqd,
        ),
        as_of=d0,
    )
    with pytest.raises(ValueError, match="missing HYG or LQD"):
        _c_level_at_as_of_prev(hyg, lqd, date(2026, 4, 9), c_th)


def test_v_recovery_v0_after_v1_shows_nn() -> None:
    """V1→V0 遷移完了日は N/N（index_history 畳み込みで level_prev=1）。"""
    th_mid = {
        "V2_on": 40.0,
        "V2_off": 38.0,
        "V2_confirm_days": 2,
        "V1_on": 30.0,
        "V1_off": 28.0,
        "V1_confirm_days": 1,
    }
    v = VFactor(name="V", thresholds={"high": th_mid, "mid": th_mid, "low": th_mid})
    d1 = date(2026, 4, 7)
    d2 = date(2026, 4, 8)
    d3 = date(2026, 4, 9)
    hist = (
        (d1, 35.0),
        (d2, 29.0),
        (d3, 27.0),
    )
    sig = VolatilitySignal(
        index_value=27.0,
        index_history=hist,
        recovery_confirm_satisfied_days_v1_off=1,
        v1_to_v0_knock_in_ok=True,
    )
    bundle = SignalBundle(
        liquidity_credit_hyg=LiquiditySignals(),
        liquidity_credit_lqd=LiquiditySignals(),
        as_of=d3,
        volatility_signals={"NQ": sig},
    )

    async def go():
        await v.apply_signal_bundle("NQ", bundle, altitude="mid")

    _run(go())
    assert v.level == 0
    hist_prev = tuple((d, x) for d, x in hist if d <= d2)
    assert v_level_from_index_history_sync(hist_prev, th_mid, last_knock_in=True) == 1
    prog = v.get_recovery_progress_from_bundle("NQ", bundle, altitude="mid")
    assert prog == (1, 1)
