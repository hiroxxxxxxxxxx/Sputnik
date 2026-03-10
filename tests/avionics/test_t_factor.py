from __future__ import annotations

import asyncio

import pytest

from avionics import TFactor
from avionics.factors_config import FactorsConfigError, get_t_thresholds, load_factors_config


def _run(coro):
    """async関数を同期テスト内で実行するユーティリティ。"""
    return asyncio.run(coro)


@pytest.fixture
def t_thresholds():
    """config/factors.toml の [T] から閾値を取得。無ければ skip。"""
    try:
        config = load_factors_config()
    except FactorsConfigError:
        pytest.skip("config/factors.toml required")
    try:
        return get_t_thresholds(config)
    except Exception:
        pytest.skip("config/factors.toml [T] required")


def test_downgrade_immediate(t_thresholds) -> None:
    """
    担当銘柄が down のとき T2 へ即時降格することを確認する（銘柄特化・サブスクリプション方式）。
    """
    tf = TFactor(symbol="NQ", thresholds=t_thresholds)
    assert tf.level == 0

    async def scenario():
        level = await tf.apply_trend("down")
        assert level == 2

    _run(scenario())


def test_upgrade_delayed(t_thresholds) -> None:
    """
    T因子が改善方向では連続2日確認後にのみ昇格することを確認する。
    """
    tf = TFactor(symbol="NQ", thresholds=t_thresholds)
    tf.level = 2

    async def scenario():
        await tf.apply_trend("up")
        assert tf.level == 2
        await tf.apply_trend("up")
        assert tf.level == 0

    _run(scenario())


def test_level_calculation_single_symbol(t_thresholds) -> None:
    """
    単一銘柄のトレンドが T0/T2 に正しくマッピングされることを確認する。
    """
    tf = TFactor(symbol="GC", thresholds=t_thresholds)

    async def scenario():
        level_down = await tf.apply_trend("down")
        assert level_down == 2
        # 改善は2日連続で適用
        await tf.apply_trend("up")
        assert tf.level == 2
        await tf.apply_trend("up")
        assert tf.level == 0
        # flat も T0 扱い
        await tf.apply_trend("flat")
        assert tf.level == 0

    _run(scenario())


def test_tfactor_update_runs_with_defaults(t_thresholds) -> None:
    """
    TFactor.update が引数なしで正常終了し、レベルは 0 または 2 のいずれかに留まることを確認する。
    """
    tf = TFactor(symbol="NQ", thresholds=t_thresholds)

    async def scenario():
        await tf.update()
        assert tf.level in (0, 2)

    _run(scenario())


def test_tfactor_no_change_records_history(t_thresholds) -> None:
    """
    トレンドが変わらずレベルが変化しない場合に record_level のみ行われるパスを確認する。
    """
    tf = TFactor(symbol="NQ", thresholds=t_thresholds)
    tf.level = 2

    async def scenario():
        before_len = len(tf.history)
        await tf.apply_trend("down")
        assert tf.level == 2
        assert len(tf.history) == before_len + 1

    _run(scenario())


def test_tfactor_symbol_identity(t_thresholds) -> None:
    """銘柄ごとに独立した TFactor が持つ symbol と name を確認する。"""
    nq = TFactor(symbol="NQ", thresholds=t_thresholds)
    gc = TFactor(symbol="GC", thresholds=t_thresholds)
    assert nq.symbol == "NQ"
    assert gc.symbol == "GC"
    assert nq.name == "T_NQ"
    assert gc.name == "T_GC"
