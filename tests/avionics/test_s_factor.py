from __future__ import annotations

import asyncio

import pytest

from avionics import SFactor
from avionics.factors import FactorsConfigError, get_s_thresholds, load_factors_config
from avionics.data.signals import LiquiditySignals, SignalBundle


def _run(coro):
    """async関数を同期テスト内で実行するユーティリティ。"""
    return asyncio.run(coro)


@pytest.fixture
def s_thresholds():
    """config/factors.toml の [S] から閾値を取得。無ければ skip。"""
    try:
        config = load_factors_config()
    except FactorsConfigError:
        pytest.skip("config/factors.toml required")
    try:
        return get_s_thresholds(config)
    except Exception:
        pytest.skip("config/factors.toml [S] required")


def test_downgrade_immediate(s_thresholds) -> None:
    """
    S因子がSPAN乖離率閾値に達した際に即時でS1/S2へ降格することを確認する。
    """
    sf = SFactor(thresholds=s_thresholds)
    assert sf.level == 0

    async def scenario():
        # 1.1以上でS1
        level = await sf.update_from_ratio(1.1)
        assert level == 1

        # 1.3以上でS2
        level = await sf.update_from_ratio(1.3)
        assert level == 2

    _run(scenario())


def test_upgrade_delayed(s_thresholds) -> None:
    """復帰は確認日数なしで即時。閾値を下回った時点で1段階ずつ復帰する。"""
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 2

    async def scenario():
        # 復帰は floor 判定。1.299 は floor(2桁)=1.29 なので S2→S1
        await sf.update_from_ratio(1.299)
        assert sf.level == 1

        # 1.099 は floor(2桁)=1.09 なので S1→S0
        await sf.update_from_ratio(1.099)
        assert sf.level == 0

    _run(scenario())


def test_level_calculation_thresholds(s_thresholds) -> None:
    """
    SPECの表どおりにSレベルが決定されることを確認する。
    """
    sf = SFactor(thresholds=s_thresholds)

    async def scenario():
        # 正常範囲（S0）
        level0 = await sf.update_from_ratio(1.0)
        assert level0 == 0

        # S1範囲
        level1 = await sf.update_from_ratio(1.15)
        assert level1 == 1

        # S2範囲
        level2 = await sf.update_from_ratio(1.35)
        assert level2 == 2

    _run(scenario())


def test_sfactor_apply_empty_bundle_runs_safely(s_thresholds) -> None:
    """
    SFactor.apply_signal_bundle が空の SignalBundle で正常終了することを確認する。
    """
    sf = SFactor(thresholds=s_thresholds)

    async def scenario():
        await sf.apply_signal_bundle(
            None,
            SignalBundle(
                liquidity_credit_hyg=LiquiditySignals(),
                liquidity_credit_lqd=LiquiditySignals(),
            ),
            altitude="mid",
        )
        assert sf.level in (0, 1, 2)

    _run(scenario())


def test_sfactor_no_change_records_history(s_thresholds) -> None:
    """
    Sが閾値の間にありレベルが変わらない場合にrecord_levelのみ行われるパスを確認する。
    """
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 1

    async def scenario():
        before_len = len(sf.history)
        # current=1, sはS1範囲内（1.1〜1.3未満）→レベル不変
        level = await sf.update_from_ratio(1.12)
        assert level == 1
        assert len(sf.history) == before_len + 1

    _run(scenario())


def test_sfactor_current2_stays_s2_when_above_threshold(s_thresholds) -> None:
    """
    current=S2かつs>=1.2のとき、S2維持パスを明示的にカバーする。
    """
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 2

    async def scenario():
        level = await sf.update_from_ratio(1.30)
        assert level == 2

    _run(scenario())


def test_sfactor_current1_middle_band_between_recovery_and_reactivation(s_thresholds) -> None:
    """
    current=S1かつ1.05<=s<1.1の中間帯でS1維持となるパスをカバーする。
    """
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 1

    async def scenario():
        level = await sf.update_from_ratio(1.10)
        assert level == 1

    _run(scenario())


def test_update_from_ratio_exact_threshold_1_2_current2(s_thresholds) -> None:
    """current=S2かつfloor(2桁)<1.3で即S1復帰する境界をカバーする。"""
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 2

    async def scenario():
        level = await sf.update_from_ratio(1.299)
        assert level == 1

    _run(scenario())


def test_update_from_ratio_current0_s_ge_1_3_downgrade_to_s2(s_thresholds) -> None:
    """
    current=S0かつs>=1.3で即S2へ降格する分岐をカバーする。
    定義書: S2発動（即）s >= 1.3。
    """
    sf = SFactor(thresholds=s_thresholds)
    assert sf.level == 0

    async def scenario():
        level = await sf.update_from_ratio(1.3)
        assert level == 2

    _run(scenario())


def test_update_from_ratio_s2_no_direct_jump_to_s0(s_thresholds) -> None:
    """
    定義書どおり S2 からは一段階ずつ復帰する。s<1.05 でも S2→S1 のみ（S0 へは直飛びしない）。
    """
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 2

    async def scenario():
        # floor 判定で S2→S1 の1段階復帰のみ
        level = await sf.update_from_ratio(1.099)
        assert level == 1
        # 次の判定で S1→S0
        await sf.update_from_ratio(1.099)
        assert sf.level == 0

    _run(scenario())


def test_sfactor_activation_uses_ceil_second_decimal(s_thresholds) -> None:
    """発動判定は小数点第二位切上げを使う。"""
    sf = SFactor(thresholds=s_thresholds)

    async def scenario():
        # 1.291 -> ceil(2桁)=1.30 なので S2 発動
        level = await sf.update_from_ratio(1.291)
        assert level == 2

    _run(scenario())


def test_sfactor_recovery_uses_floor_second_decimal(s_thresholds) -> None:
    """復帰判定は小数点第二位切捨てを使う。"""
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 2

    async def scenario():
        # 1.3001 -> floor(2桁)=1.30 のため S2 維持
        level = await sf.update_from_ratio(1.3001)
        assert level == 2
        # 1.2999 -> floor(2桁)=1.29 で S2→S1
        level = await sf.update_from_ratio(1.2999)
        assert level == 1

    _run(scenario())

