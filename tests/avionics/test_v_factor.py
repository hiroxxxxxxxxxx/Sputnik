from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest

from avionics import VFactor
from avionics.data.signals import LiquiditySignals, SignalBundle, VolatilitySignal
from avionics.factors import FactorsConfigError, get_v_thresholds, load_factors_config

try:
    _config = load_factors_config()
except FactorsConfigError:
    pytest.skip("config/factors.toml required", allow_module_level=True)


def _run(coro):
    """async関数を同期テスト内で実行するユーティリティ。"""
    return asyncio.run(coro)


def _v_nq() -> dict:
    return get_v_thresholds(_config, "NQ")


def _hist(*points: tuple[date, float]) -> tuple[tuple[date, float], ...]:
    return tuple(points)


def test_downgrade_immediate() -> None:
    """
    日次指数履歴を畳み込むと V1/V2 へ到達することを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())
    d0 = date(2025, 1, 1)

    async def scenario():
        hist = _hist(
            (d0, 20.0),
            (d0 + timedelta(days=1), 30.5),
            (d0 + timedelta(days=2), 41.0),
        )
        sig = VolatilitySignal(
            index_value=41.0,
            index_history=hist,
            v1_to_v0_knock_in_ok=False,
        )
        await vf.update_from_volatility_signal(sig, altitude="mid")
        assert vf.level == 2

    _run(scenario())


def test_upgrade_delayed_v2_to_v1() -> None:
    """
    V2→V1 復帰には V2_off 未満の連続が V2_confirm_days 以上必要なことを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())
    d0 = date(2025, 1, 1)

    async def scenario():
        hist = _hist(
            (d0, 41.0),
            (d0 + timedelta(days=1), 37.5),
            (d0 + timedelta(days=2), 37.0),
        )
        sig = VolatilitySignal(
            index_value=37.0,
            index_history=hist,
            v1_to_v0_knock_in_ok=False,
        )
        await vf.update_from_volatility_signal(sig, altitude="mid")
        assert vf.level == 1

    _run(scenario())


def test_v_recovery_with_1h_knockin() -> None:
    """
    V1→V0 復帰が連続日数＋1h ノックイン条件で制御されることを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())
    d0 = date(2025, 1, 1)

    async def scenario():
        hist_base = _hist((d0, 31.0), (d0 + timedelta(days=1), 27.0))
        sig_false = VolatilitySignal(
            index_value=27.0,
            index_history=hist_base,
            v1_to_v0_knock_in_ok=False,
        )
        await vf.update_from_volatility_signal(sig_false, altitude="mid")
        assert vf.level == 1

        sig_true = VolatilitySignal(
            index_value=27.0,
            index_history=hist_base,
            v1_to_v0_knock_in_ok=True,
        )
        await vf.update_from_volatility_signal(sig_true, altitude="mid")
        assert vf.level == 0

    _run(scenario())


def test_level_calculation_altitude_tables() -> None:
    """
    高・中高度と低高度で異なる閾値テーブルが適用されることを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())
    d0 = date(2025, 1, 1)

    async def scenario():
        sig_mid = VolatilitySignal(
            index_value=35.0,
            index_history=_hist((d0, 35.0)),
            v1_to_v0_knock_in_ok=False,
        )
        await vf.update_from_volatility_signal(sig_mid, altitude="mid")
        assert vf.level == 1

        sig_low = VolatilitySignal(
            index_value=35.0,
            index_history=_hist((d0, 35.0)),
            v1_to_v0_knock_in_ok=False,
        )
        await vf.update_from_volatility_signal(sig_low, altitude="low")
        assert vf.level == 2

    _run(scenario())


def test_vfactor_apply_empty_bundle_runs_safely() -> None:
    """
    VFactor.apply_signal_bundle が空の SignalBundle で正常終了することを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())

    async def scenario():
        await vf.apply_signal_bundle(
            "NQ",
            SignalBundle(
                liquidity_credit_hyg=LiquiditySignals(),
                liquidity_credit_lqd=LiquiditySignals(),
            ),
            altitude="mid",
        )
        assert vf.level in (0, 1, 2)

    _run(scenario())


def test_vfactor_no_change_records_history() -> None:
    """
    畳み込み後レベルが 0 のままでも history が増えることを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())
    d0 = date(2025, 1, 1)

    async def scenario():
        before_len = len(vf.history)
        sig = VolatilitySignal(
            index_value=20.0,
            index_history=_hist((d0, 20.0)),
            v1_to_v0_knock_in_ok=False,
        )
        level = await vf.update_from_volatility_signal(sig, altitude="mid")
        assert level == 0
        assert len(vf.history) == before_len + 1

    _run(scenario())


def test_v1_to_v0_requires_knock_in() -> None:
    """
    V1 から指数が V1_off 未満でも 1h ノックインが無ければ V0 に落ちない。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())
    d0 = date(2025, 1, 1)
    hist = _hist((d0, 31.0), (d0 + timedelta(days=1), 27.0))

    async def scenario():
        sig = VolatilitySignal(
            index_value=27.0,
            index_history=hist,
            v1_to_v0_knock_in_ok=False,
        )
        await vf.update_from_volatility_signal(sig, altitude="mid")
        assert vf.level == 1

    _run(scenario())


def test_vfactor_update_from_volatility_signal_uses_1h_knock_in() -> None:
    """
    update_from_volatility_signal で v1_to_v0_knock_in_ok が効くことを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())
    d0 = date(2025, 1, 1)
    hist = _hist((d0, 31.0), (d0 + timedelta(days=1), 27.0))

    async def scenario():
        sig_false = VolatilitySignal(
            index_value=27.0,
            index_history=hist,
            v1_to_v0_knock_in_ok=False,
            recovery_confirm_satisfied_days_v1_off=1,
            recovery_confirm_satisfied_days_v2_off=0,
        )
        await vf.update_from_volatility_signal(sig_false, altitude="mid")
        assert vf.level == 1

        sig_true = VolatilitySignal(
            index_value=27.0,
            index_history=hist,
            v1_to_v0_knock_in_ok=True,
            recovery_confirm_satisfied_days_v1_off=1,
            recovery_confirm_satisfied_days_v2_off=0,
        )
        await vf.update_from_volatility_signal(sig_true, altitude="mid")
        assert vf.level == 0

    _run(scenario())


def test_vfactor_update_from_index_v1_unchanged_records_history() -> None:
    """
    V1 を維持する指数帯でレベル不変のとき history が増えるパスをカバーする。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())

    async def scenario():
        before_len = len(vf.history)
        level = await vf.update_from_index(
            index_value=30.0,
            altitude="mid",
            recovery_confirm_satisfied_days_v1_off=0,
            recovery_confirm_satisfied_days_v2_off=0,
        )
        assert level == 1
        assert len(vf.history) == before_len + 1

    _run(scenario())


def test_vfactor_no_direct_v2_to_v0() -> None:
    """
    V2 から V1_off 未満へ下落しても V2_confirm を満たさなければ V2 を維持し、
    V0 へは直接落ちない（V2→V0 経路なし）。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq())
    d0 = date(2025, 1, 1)
    hist = _hist(
        (d0, 41.0),
        (d0 + timedelta(days=1), 27.0),
    )
    sig = VolatilitySignal(
        index_value=27.0,
        index_history=hist,
        v1_to_v0_knock_in_ok=False,
        recovery_confirm_satisfied_days_v1_off=0,
        recovery_confirm_satisfied_days_v2_off=1,
    )

    async def scenario():
        await vf.update_from_volatility_signal(sig, altitude="mid")
        assert vf.level == 2

    _run(scenario())
