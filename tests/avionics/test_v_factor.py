from __future__ import annotations

import asyncio

import pytest

from avionics import VFactor
from avionics.factors import FactorsConfigError, get_v_thresholds, load_factors_config
from avionics.data.signals import LiquiditySignals, SignalBundle

try:
    _config = load_factors_config()
except FactorsConfigError:
    pytest.skip("config/factors.toml required", allow_module_level=True)


def _run(coro):
    """async関数を同期テスト内で実行するユーティリティ。"""
    return asyncio.run(coro)


def _v_nq() -> dict:
    return get_v_thresholds(_config, "NQ")


def test_downgrade_immediate() -> None:
    """
    V因子が閾値接触時に即時で V1/V2 へ降格することを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")
    assert vf.level == 0

    async def scenario():
        level = await vf.update_from_index(
            index_value=30.5, altitude="mid",
            recovery_confirm_satisfied_days_v1_off=0, recovery_confirm_satisfied_days_v2_off=0,
        )
        assert level == 1

        level = await vf.update_from_index(
            index_value=41.0, altitude="mid",
            recovery_confirm_satisfied_days_v1_off=0, recovery_confirm_satisfied_days_v2_off=0,
        )
        assert level == 2

    _run(scenario())


def test_upgrade_delayed_v2_to_v1() -> None:
    """
    V2→V1 復帰には 2 日間の閾値未満継続が必要なことを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")
    vf.level = 2

    async def scenario():
        await vf.update_from_index(
            index_value=37.5, altitude="mid",
            recovery_confirm_satisfied_days_v1_off=0, recovery_confirm_satisfied_days_v2_off=0,
        )
        assert vf.level == 2

        await vf.update_from_index(
            index_value=37.0, altitude="mid",
            recovery_confirm_satisfied_days_v1_off=2, recovery_confirm_satisfied_days_v2_off=2,
        )
        assert vf.level == 1

    _run(scenario())


def test_v_recovery_with_1h_knockin() -> None:
    """
    V1→V0 復帰が 1 日確認＋1h ノックイン条件（buffer_condition）で制御されることを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")
    vf.level = 1

    async def scenario():
        index_value = 27.0

        async def buffer_false(_f, _lvl) -> bool:
            return False

        async def buffer_true(_f, _lvl) -> bool:
            return True

        await vf.update_from_index(
            index_value=index_value,
            altitude="mid",
            recovery_confirm_satisfied_days_v1_off=1,
            recovery_confirm_satisfied_days_v2_off=0,
            buffer_condition_v1_to_v0=buffer_false,
        )
        assert vf.level == 1

        await vf.update_from_index(
            index_value=index_value,
            altitude="mid",
            recovery_confirm_satisfied_days_v1_off=1,
            recovery_confirm_satisfied_days_v2_off=0,
            buffer_condition_v1_to_v0=buffer_true,
        )
        assert vf.level == 0

    _run(scenario())


def test_level_calculation_altitude_tables() -> None:
    """
    高・中高度と低高度で異なる閾値テーブルが適用されることを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")

    async def scenario():
        level_high = await vf.update_from_index(
            index_value=35.0, altitude="mid",
            recovery_confirm_satisfied_days_v1_off=0, recovery_confirm_satisfied_days_v2_off=0,
        )
        assert level_high == 1

        vf.level = 0
        level_low = await vf.update_from_index(
            index_value=35.0, altitude="low",
            recovery_confirm_satisfied_days_v1_off=0, recovery_confirm_satisfied_days_v2_off=0,
        )
        assert level_low == 2

    _run(scenario())


def test_vfactor_apply_empty_bundle_runs_safely() -> None:
    """
    VFactor.apply_signal_bundle が空の SignalBundle で正常終了することを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")

    async def scenario():
        await vf.apply_signal_bundle(
            "NQ",
            SignalBundle(
                liquidity_credit_hyg=LiquiditySignals(),
                liquidity_credit_lqd=LiquiditySignals(),
            ),
        )
        assert vf.level in (0, 1, 2)

    _run(scenario())


def test_vfactor_no_change_records_history() -> None:
    """
    閾値の外側でレベルが変わらない場合に record_level のみ行われるパスを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")
    assert vf.level == 0

    async def scenario():
        before_len = len(vf.history)
        level = await vf.update_from_index(
            index_value=20.0, altitude="mid",
            recovery_confirm_satisfied_days_v1_off=0, recovery_confirm_satisfied_days_v2_off=0,
        )
        assert level == 0
        assert len(vf.history) == before_len + 1

    _run(scenario())


def test_vfactor_v1_to_v0_without_buffer_condition() -> None:
    """
    V1→V0 復帰時に buffer_condition=None → buf_ok=False で V1 に留まることを確認する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")
    vf.level = 1

    async def scenario():
        await vf.update_from_index(
            index_value=27.0, altitude="mid",
            recovery_confirm_satisfied_days_v1_off=1, recovery_confirm_satisfied_days_v2_off=0,
        )
        assert vf.level == 1

    _run(scenario())


def test_vfactor_update_from_volatility_signal_uses_1h_knock_in() -> None:
    """
    update_from_volatility_signal で v1_to_v0_knock_in_ok が False のときは V1→V0 復帰しない、
    True のときは復帰することを確認する（SPEC 4-2-1-2 1hノックイン）。
    """
    from avionics.data.signals import VolatilitySignal

    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")
    vf.level = 1

    async def scenario():
        # 指数は閾値未満・連続1日満たすが 1h ノックイン未達のときは V1 のまま
        sig_false = VolatilitySignal(
            index_value=27.0,
            v1_to_v0_knock_in_ok=False,
            is_intraday_condition_met=False,
            recovery_confirm_satisfied_days_v1_off=1,
            recovery_confirm_satisfied_days_v2_off=0,
        )
        await vf.update_from_volatility_signal(sig_false)
        await vf.update_from_volatility_signal(sig_false)
        assert vf.level == 1

        # 1h ノックイン達成で V0 復帰（連続1日＋is_intraday で一発昇格）
        sig_true = VolatilitySignal(
            index_value=27.0,
            v1_to_v0_knock_in_ok=True,
            is_intraday_condition_met=True,
            recovery_confirm_satisfied_days_v1_off=1,
            recovery_confirm_satisfied_days_v2_off=0,
        )
        await vf.update_from_volatility_signal(sig_true)
        assert vf.level == 0

    _run(scenario())


def test_vfactor_update_from_index_v1_unchanged_records_history() -> None:
    """
    V1 のまま指数が V1 閾値内でレベル不変のとき record_level が呼ばれるパスをカバーする。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")
    vf.level = 1

    async def scenario():
        before_len = len(vf.history)
        level = await vf.update_from_index(
            index_value=30.0, altitude="mid",
            recovery_confirm_satisfied_days_v1_off=0, recovery_confirm_satisfied_days_v2_off=0,
        )
        assert level == 1
        assert len(vf.history) == before_len + 1

    _run(scenario())


def test_vfactor_update_from_index_v2_to_v0_upgrade_confirm_days_1() -> None:
    """
    current=V2 かつ v < V1_off のとき candidate=0 となり、1 日確認で V0 復帰する。
    """
    vf = VFactor(name="V_NQ", thresholds=_v_nq(), altitude="mid")
    vf.level = 2

    async def scenario():
        level = await vf.update_from_index(
            index_value=27.0, altitude="mid",
            recovery_confirm_satisfied_days_v1_off=0, recovery_confirm_satisfied_days_v2_off=1,
        )
        assert level == 0

    _run(scenario())
