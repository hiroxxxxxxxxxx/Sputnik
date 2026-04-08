from __future__ import annotations

import asyncio
from datetime import date

import pytest

from avionics import PFactor
from avionics.data.signals import LiquiditySignals, PriceSignals, SignalBundle
from avionics.factors import FactorsConfigError, get_p_thresholds, load_factors_config
from avionics.factors.p_factor import (
    _p_classify_row,
    p_classify_row_hit_row_keys,
    p_classify_row_with_reason,
    p_level_from_daily_rows,
)

try:
    _config = load_factors_config()
except FactorsConfigError:
    pytest.skip("config/factors.toml required", allow_module_level=True)


def _run(coro):
    """async関数を同期テスト内で実行するユーティリティ。"""
    return asyncio.run(coro)


def _p_nq() -> dict:
    return get_p_thresholds(_config, "NQ")


def _p_gc() -> dict:
    return get_p_thresholds(_config, "GC")


def test_downgrade_immediate() -> None:
    """
    P因子がショック条件で即時に高レベルへ降格することを確認する。
    """
    pf = PFactor(name="P_NQ", thresholds=_p_nq())
    assert pf.level == 0

    async def scenario():
        level = await pf.update_from_signals(
            daily_change=-0.04,
            cum5_change=-0.04,
            high_20_gap=-0.06,
            trend="down",
            recovery_confirm_satisfied_days=0,
            cum2_change=-0.06,
        )
        assert level == 2
        assert pf.level == 2

    _run(scenario())


def test_upgrade_immediate_when_p0_conditions_met() -> None:
    """
    P0 条件を満たす最新行があれば、履歴上の高レベルに関係なく即 P0 になる（N 日確認なし）。
    """
    pf = PFactor(name="P_NQ", thresholds=_p_nq())
    pf.level = 2

    async def scenario():
        calm_kwargs = dict(
            daily_change=0.0,
            cum5_change=0.0,
            high_20_gap=-0.01,
            trend="up",
            recovery_confirm_satisfied_days=0,
            cum2_change=-0.01,
        )

        await pf.update_from_signals(**calm_kwargs)
        assert pf.level == 0

    _run(scenario())


def test_p_level_from_daily_rows_empty_raises() -> None:
    with pytest.raises(ValueError, match="at least one"):
        p_level_from_daily_rows([], _p_nq())


def test_p_level_from_daily_rows_short_last_row_raises() -> None:
    from datetime import date as date_type

    bad_last = (date_type(2026, 1, 1), -0.01, -0.02, -0.03, "flat")
    with pytest.raises(ValueError, match="at least 6 fields"):
        p_level_from_daily_rows([bad_last], _p_nq())


def test_p_level_from_daily_rows_uses_last_row_only() -> None:
    """
    畳み込み復帰が無いため、末尾が P1 なら履歴先頭が P2 でもレベルは 1 になる。
    """
    from datetime import date as date_type

    t = _p_nq()
    row_old = (date_type(2026, 1, 1), -0.04, -0.04, -0.06, "down", -0.06)
    row_new = (date_type(2026, 1, 2), -0.02, -0.04, -0.035, "flat", -0.03)
    assert p_level_from_daily_rows([row_old, row_new], t) == 1


def test_level_calculation_nq_vs_gc() -> None:
    """
    しきい値の違いで NQ 用と GC 用で適切な P レベルが算出されることを確認する。
    """
    async def scenario():
        pf_nq = PFactor(name="P_NQ", thresholds=_p_nq())
        level_nq = await pf_nq.update_from_signals(
            daily_change=-0.02,
            cum5_change=-0.04,
            high_20_gap=-0.035,
            trend="flat",
            recovery_confirm_satisfied_days=0,
            cum2_change=-0.03,
        )
        assert level_nq == 1

        pf_gc = PFactor(name="P_GC", thresholds=_p_gc())
        level_gc = await pf_gc.update_from_signals(
            daily_change=0.01,
            cum5_change=-0.02,
            high_20_gap=-0.02,
            trend="up",
            recovery_confirm_satisfied_days=0,
            cum2_change=-0.01,
        )
        assert level_gc == 0

    _run(scenario())


def test_pfactor_apply_empty_bundle_runs_safely() -> None:
    """
    PFactor.apply_signal_bundle が空の SignalBundle で正常終了することを確認する。
    """
    pf = PFactor(name="P_NQ", thresholds=_p_nq())

    async def scenario():
        await pf.apply_signal_bundle(
            "NQ",
            SignalBundle(
                liquidity_credit_hyg=LiquiditySignals(),
                liquidity_credit_lqd=LiquiditySignals(),
                as_of=date(2025, 3, 1),
            ),
            altitude="mid",
        )
        assert pf.level in (0, 1, 2)

    _run(scenario())


def test_classify_nq_fallback_to_p1() -> None:
    """
    P2/P1/P0 いずれにも該当しない場合、安全側フォールバックとして P1 になることを確認する。
    """
    pf = PFactor(name="P_NQ", thresholds=_p_nq())

    async def scenario():
        level = await pf.update_from_signals(
            daily_change=0.02,
            cum5_change=0.0,
            high_20_gap=-0.02,
            trend="down",
            recovery_confirm_satisfied_days=0,
            cum2_change=0.0,
        )
        assert level == 1

    _run(scenario())


def test_classify_gc_p2_and_fallback_p1() -> None:
    """
    GC しきい値で P2 ショック条件およびフォールバック P1 が正しく動作することを確認する。
    """
    async def scenario():
        pf_p2 = PFactor(name="P_GC", thresholds=_p_gc())
        level_p2 = await pf_p2.update_from_signals(
            daily_change=-0.04,
            cum5_change=-0.04,
            high_20_gap=-0.05,
            trend="down",
            recovery_confirm_satisfied_days=0,
            cum2_change=-0.06,
        )
        assert level_p2 == 2

        pf_fb = PFactor(name="P_GC", thresholds=_p_gc())
        level_fb = await pf_fb.update_from_signals(
            daily_change=0.02,
            cum5_change=0.01,
            high_20_gap=-0.01,
            trend="down",
            recovery_confirm_satisfied_days=0,
            cum2_change=0.0,
        )
        assert level_fb == 1

    _run(scenario())


def test_p_classify_row_wrapper_matches_with_reason_level() -> None:
    t = _p_nq()
    inputs = (-0.04, -0.04, -0.06, "down", -0.06)
    assert _p_classify_row(t, *inputs) == p_classify_row_with_reason(t, *inputs)[0]


def test_p_classify_row_with_reason_p2_daily() -> None:
    t = _p_nq()
    level, rid = p_classify_row_with_reason(t, -0.04, 0.0, -0.02, "flat", None)
    assert level == 2 and rid == "P2_daily"


def test_p_classify_row_with_reason_p2_cum2_chain_order() -> None:
    t = _p_nq()
    level, rid = p_classify_row_with_reason(t, -0.02, -0.04, -0.02, "up", -0.06)
    assert level == 2 and rid == "P2_cum2"


def test_p_classify_row_hit_row_keys_p0_all_four() -> None:
    keys = p_classify_row_hit_row_keys("P0_relaxed")
    assert keys == frozenset(
        {"daily_change", "cum5_change", "high_20_gap", "trend"}
    )


def test_p_classify_row_hit_row_keys_p1_default_empty() -> None:
    assert p_classify_row_hit_row_keys("P1_default") == frozenset()


def test_latest_price_daily_row_newest_from_history() -> None:
    from datetime import date as date_type

    pf = PFactor(name="P", thresholds=_p_nq())
    row_old = (date_type(2026, 1, 1), -0.01, -0.02, -0.03, "flat", None)
    row_new = (date_type(2026, 1, 5), -0.05, -0.05, -0.05, "down", -0.05)
    ps = PriceSignals(
        symbol="NQ",
        trend="down",
        daily_change=-0.05,
        cum5_change=-0.05,
        cum2_change=-0.05,
        last_close=1.0,
        high_20_gap=-0.05,
        daily_history=(row_new, row_old),
    )
    latest = pf.latest_price_daily_row(ps)
    assert latest[0] == row_new[0]


def test_classify_gc_p1_gap_edge_case() -> None:
    """
    GC しきい値で Downside Gap 境界（P1_gap レンジ内）による P1 判定を確認する。
    """
    pf = PFactor(name="P_GC", thresholds=_p_gc())

    async def scenario():
        level = await pf.update_from_signals(
            daily_change=0.0,
            cum5_change=0.0,
            high_20_gap=-0.03,
            trend="flat",
            recovery_confirm_satisfied_days=0,
            cum2_change=0.0,
        )
        assert level == 1

    _run(scenario())
