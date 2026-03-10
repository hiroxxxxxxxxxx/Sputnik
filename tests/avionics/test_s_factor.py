from __future__ import annotations

import asyncio

import pytest

from avionics import SFactor
from avionics.factors_config import FactorsConfigError, get_s_thresholds, load_factors_config


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
    """
    S2→S1が2日、S1→S0が3日連続確認で復帰することを確認する。
    """
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 2

    async def scenario():
        # S2→S1 復帰テスト
        for i in range(2):
            await sf.update_from_ratio(1.19)
            if i == 0:
                assert sf.level == 2
        assert sf.level == 1

        # S1→S0 復帰テスト
        for i in range(3):
            await sf.update_from_ratio(1.04)
            if i < 2:
                assert sf.level == 1
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


def test_sfactor_update_runs_with_defaults(s_thresholds) -> None:
    """
    SFactor.update がデフォルト引数で update_from_ratio を呼び正常終了することを確認する。
    """
    sf = SFactor(thresholds=s_thresholds)

    async def scenario():
        await sf.update()
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
        level = await sf.update_from_ratio(1.25)
        assert level == 2

    _run(scenario())


def test_sfactor_current1_middle_band_between_recovery_and_reactivation(s_thresholds) -> None:
    """
    current=S1かつ1.05<=s<1.1の中間帯でS1維持となるパスをカバーする。
    """
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 1

    async def scenario():
        level = await sf.update_from_ratio(1.06)
        assert level == 1

    _run(scenario())


def test_update_from_ratio_exact_threshold_1_2_current2(s_thresholds) -> None:
    """
    current=S2かつsがちょうど1.2未満でS1候補になる境界をカバーする。
    定義書: S2→S1復帰は s < 1.2（2日確認）。
    """
    sf = SFactor(thresholds=s_thresholds)
    sf.level = 2

    async def scenario():
        level = await sf.update_from_ratio(1.19)
        assert level == 2  # 1日目はまだS2
        level = await sf.update_from_ratio(1.19)
        assert level == 1  # 2日目でS1復帰

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
        # 1日目: s<1.2 で candidate=1 だが confirm_days=2 のためまだ S2
        level = await sf.update_from_ratio(1.04)
        assert level == 2
        # 2日目: S2→S1 復帰
        level = await sf.update_from_ratio(1.04)
        assert level == 1
        # さらに3日で S1→S0
        for _ in range(3):
            await sf.update_from_ratio(1.04)
        assert sf.level == 0

    _run(scenario())

