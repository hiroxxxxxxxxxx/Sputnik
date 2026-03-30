from __future__ import annotations

import asyncio

import pytest

from avionics import TFactor
from avionics.factors import FactorsConfigError, get_t_thresholds, load_factors_config
from avionics.data.signals import LiquiditySignals, SignalBundle


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
    T因子が改善方向では confirm_days 連続確認後にのみ昇格することを確認する。
    daily_history が不十分なときは復帰せず、十分な連続日数を渡すと復帰する。
    """
    from datetime import date, timedelta
    tf = TFactor(symbol="NQ", thresholds=t_thresholds)
    tf.level = 2
    confirm = int(t_thresholds["confirm_days"])

    async def scenario():
        short_history = tuple(
            (date(2025, 3, 1) - timedelta(days=i), 0.0, 0.0, -0.01, "up", None)
            for i in range(confirm - 1)
        )
        await tf.apply_trend("up", daily_history=short_history)
        assert tf.level == 2

        full_history = tuple(
            (date(2025, 3, 1) - timedelta(days=i), 0.0, 0.0, -0.01, "up", None)
            for i in range(confirm)
        )
        await tf.apply_trend("up", daily_history=full_history)
        assert tf.level == 0

    _run(scenario())


def test_level_calculation_single_symbol(t_thresholds) -> None:
    """
    単一銘柄のトレンドが T0/T2 に正しくマッピングされることを確認する。
    """
    from datetime import date, timedelta
    tf = TFactor(symbol="GC", thresholds=t_thresholds)
    confirm = int(t_thresholds["confirm_days"])

    async def scenario():
        level_down = await tf.apply_trend("down")
        assert level_down == 2
        full_history = tuple(
            (date(2025, 3, 1) - timedelta(days=i), 0.0, 0.0, -0.01, "up", None)
            for i in range(confirm)
        )
        await tf.apply_trend("up", daily_history=full_history)
        assert tf.level == 0
        await tf.apply_trend("flat")
        assert tf.level == 0

    _run(scenario())


def test_tfactor_apply_empty_bundle_runs_safely(t_thresholds) -> None:
    """
    TFactor.apply_signal_bundle が空の SignalBundle で正常終了し、レベルは 0 または 2 のいずれかに留まることを確認する。
    """
    tf = TFactor(symbol="NQ", thresholds=t_thresholds)

    async def scenario():
        await tf.apply_signal_bundle(
            "NQ",
            SignalBundle(
                liquidity_credit_hyg=LiquiditySignals(),
                liquidity_credit_lqd=LiquiditySignals(),
            ),
            altitude="mid",
        )
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
