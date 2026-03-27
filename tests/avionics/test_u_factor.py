from __future__ import annotations

import asyncio

import pytest

from avionics import UFactor
from avionics.factors import FactorsConfigError, get_u_thresholds, load_factors_config
from avionics.data.signals import LiquiditySignals, SignalBundle


def _run(coro):
    """async関数を同期テスト内で実行するユーティリティ。"""
    return asyncio.run(coro)


@pytest.fixture
def u_thresholds():
    """config/factors.toml の [U] から閾値を取得。無ければ skip。"""
    try:
        config = load_factors_config()
    except FactorsConfigError:
        pytest.skip("config/factors.toml required")
    try:
        return get_u_thresholds(config)
    except Exception:
        pytest.skip("config/factors.toml [U] required")


def test_downgrade_immediate(u_thresholds) -> None:
    """
    U因子がMM/NLV閾値に達した際に即時でC1/C2へ降格することを確認する。
    """
    uf = UFactor(thresholds=u_thresholds)
    assert uf.level == 0

    async def scenario():
        # 40%以上でC1
        level = await uf.update_from_ratio(0.40)
        assert level == 1

        # 50%以上でC2
        level = await uf.update_from_ratio(0.50)
        assert level == 2

    _run(scenario())


def test_upgrade_delayed(u_thresholds) -> None:
    """復帰は確認日数なしで即時。閾値を下回った時点で1段階ずつ復帰する。"""
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 2

    async def scenario():
        # C2→C1 は即時（< 0.43）
        await uf.update_from_ratio(0.42)
        assert uf.level == 1

        # C1→C0 も即時（< 0.36）
        await uf.update_from_ratio(0.35)
        assert uf.level == 0

    _run(scenario())


def test_level_calculation_thresholds(u_thresholds) -> None:
    """
    SPECの表どおりにCレベルが決定されることを確認する。
    """
    uf = UFactor(thresholds=u_thresholds)

    async def scenario():
        # 適正負荷（C0）
        level0 = await uf.update_from_ratio(0.30)
        assert level0 == 0

        # 超過負荷（C1）
        level1 = await uf.update_from_ratio(0.42)
        assert level1 == 1

        # 限界負荷（C2）
        level2 = await uf.update_from_ratio(0.55)
        assert level2 == 2

    _run(scenario())


def test_ufactor_apply_empty_bundle_runs_safely(u_thresholds) -> None:
    """
    UFactor.apply_signal_bundle が空の SignalBundle で正常終了することを確認する。
    """
    uf = UFactor(thresholds=u_thresholds)

    async def scenario():
        await uf.apply_signal_bundle(
            None,
            SignalBundle(
                liquidity_credit_hyg=LiquiditySignals(),
                liquidity_credit_lqd=LiquiditySignals(),
            ),
        )
        assert uf.level in (0, 1, 2)

    _run(scenario())


def test_ufactor_no_change_records_history(u_thresholds) -> None:
    """
    Uが閾値の間にありレベルが変わらない場合にrecord_levelのみ行われるパスを確認する。
    """
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 1

    async def scenario():
        before_len = len(uf.history)
        # current=1, rが0.36〜0.40の間 → C1維持
        level = await uf.update_from_ratio(0.39)
        assert level == 1
        assert len(uf.history) == before_len + 1

    _run(scenario())


def test_ufactor_current2_stays_c2_when_above_threshold(u_thresholds) -> None:
    """
    current=C2かつr>=0.45のとき、C2維持パスを明示的にカバーする。
    """
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 2

    async def scenario():
        level = await uf.update_from_ratio(0.43)
        assert level == 2

    _run(scenario())


def test_ufactor_current1_upgrades_to_c2_on_high_ratio(u_thresholds) -> None:
    """
    current=C1かつr>=0.50でC2へ悪化する分岐をカバーする。
    """
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 1

    async def scenario():
        level = await uf.update_from_ratio(0.55)
        assert level == 2

    _run(scenario())


def test_update_from_ratio_exact_threshold_0_45_current2(u_thresholds) -> None:
    """current=C2かつrが0.43未満で即C1復帰する境界をカバーする。"""
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 2

    async def scenario():
        level = await uf.update_from_ratio(0.42)
        assert level == 1

    _run(scenario())


def test_update_from_ratio_exact_threshold_0_38_current1(u_thresholds) -> None:
    """current=C1かつrが0.36未満で即C0復帰する境界をカバーする。"""
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 1

    async def scenario():
        await uf.update_from_ratio(0.35)
        assert uf.level == 0

    _run(scenario())


def test_update_from_ratio_current0_r_ge_50_downgrade_to_c2(u_thresholds) -> None:
    """
    current=C0かつr>=0.50で即C2へ降格する分岐をカバーする。
    定義書: C2発動（即）r >= 50%。
    """
    uf = UFactor(thresholds=u_thresholds)
    assert uf.level == 0

    async def scenario():
        level = await uf.update_from_ratio(0.50)
        assert level == 2

    _run(scenario())


def test_update_from_ratio_exact_threshold_0_45_c2_stays(u_thresholds) -> None:
    """current=C2かつrが0.43以上のときC2維持の境界をカバーする。"""
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 2

    async def scenario():
        level = await uf.update_from_ratio(0.43)
        assert level == 2

    _run(scenario())


def test_update_from_ratio_exact_threshold_0_38_current1_else_branch(u_thresholds) -> None:
    """current=C1かつ0.36<=r<0.40のときcandidate=1となる境界をカバーする。"""
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 1

    async def scenario():
        level = await uf.update_from_ratio(0.36)
        assert level == 1

    _run(scenario())


def test_update_from_ratio_current1_r_ge_0_40_candidate_1(u_thresholds) -> None:
    """
    current=C1かつr>=0.40（かつr<0.50）のとき「elif r >= 0.40: candidate = 1」をカバーする。
    """
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 1

    async def scenario():
        level = await uf.update_from_ratio(0.42)
        assert level == 1

    _run(scenario())


def test_update_from_ratio_c2_no_direct_jump_to_c0(u_thresholds) -> None:
    """
    定義書どおり C2 からは一段階ずつ復帰する。r<0.38 でも C2→C1 のみ（C0 へは直飛びしない）。
    """
    uf = UFactor(thresholds=u_thresholds)
    uf.level = 2

    async def scenario():
        # r<0.36 でも C2→C1 の1段階復帰のみ
        level = await uf.update_from_ratio(0.35)
        assert level == 1
        # 次の判定で C1→C0
        await uf.update_from_ratio(0.35)
        assert uf.level == 0

    _run(scenario())

