from __future__ import annotations

import asyncio

import pytest

from avionics import PFactor
from avionics.factors import FactorsConfigError, get_p_thresholds, load_factors_config
from avionics.data.signals import LiquiditySignals, SignalBundle

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


def test_upgrade_delayed() -> None:
    """
    P因子が改善方向では confirm_days 連続確認後にのみ昇格することを確認する。
    """
    pf = PFactor(name="P_NQ", thresholds=_p_nq())
    pf.level = 2

    async def scenario():
        calm_kwargs = dict(
            daily_change=0.0,
            cum5_change=0.0,
            high_20_gap=-0.01,
            trend="up",
            recovery_confirm_satisfied_days=1,
            cum2_change=-0.01,
        )

        # 1日目：calm 条件かつ recovery_confirm_satisfied_days=1 で昇格
        await pf.update_from_signals(**calm_kwargs)
        assert pf.level == 0

    _run(scenario())


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
            ),
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
