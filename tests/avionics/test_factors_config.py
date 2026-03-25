"""
因子しきい値設定の読込テスト。config/factors.toml から注入できることを確認する。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from avionics.factors import (
    FactorsConfigError,
    get_c_thresholds,
    get_p_thresholds,
    get_r_thresholds,
    get_s_thresholds,
    get_t_thresholds,
    get_u_thresholds,
    get_v_thresholds,
    load_factors_config,
)
from avionics import PFactor


def test_load_factors_config_from_project_config() -> None:
    """プロジェクトの config/factors.toml を読むと NQ/GC の P/V が取得できる。"""
    try:
        config = load_factors_config()
    except FactorsConfigError:
        pytest.skip("config/factors.toml not found (optional)")
    assert "NQ" in config
    assert "P" in config["NQ"]
    assert config["NQ"]["P"]["P2_daily_max"] == -0.03
    assert "V" in config["NQ"]
    assert "high" in config["NQ"]["V"]
    assert "mid" in config["NQ"]["V"]
    assert "GC" in config
    assert config["GC"]["P"]["P2_gap_trend"] == -0.04


def test_pfactor_from_loaded_config() -> None:
    """読込んだ設定で PFactor を組み立て、判定が動作する。"""
    try:
        config = load_factors_config()
    except FactorsConfigError:
        pytest.skip("config/factors.toml not found")
    if not config or "NQ" not in config or "P" not in config["NQ"]:
        pytest.skip("config missing NQ.P")
    pf = PFactor(name="P_NQ", thresholds=config["NQ"]["P"])
    assert pf.name == "P_NQ"
    assert pf.thresholds["confirm_days"] == 1
    # ショック条件で P2
    import asyncio
    async def run():
        return await pf.update_from_signals(
            daily_change=-0.04,
            cum5_change=0.0,
            downside_gap=-0.01,
            trend="up",
            recovery_confirm_satisfied_days=0,
            cum2_change=None,
        )
    level = asyncio.run(run())
    assert level == 2


def test_get_p_thresholds_raises_when_config_empty() -> None:
    """設定が空のとき get_p_thresholds は FactorsConfigError を上げる。"""
    with pytest.raises(FactorsConfigError) as exc_info:
        get_p_thresholds({}, "NQ")
    assert "NQ" in str(exc_info.value)
    assert "config/factors.toml" in str(exc_info.value)


def test_get_v_thresholds_raises_when_config_empty() -> None:
    """設定が空のとき get_v_thresholds は FactorsConfigError を上げる。"""
    with pytest.raises(FactorsConfigError) as exc_info:
        get_v_thresholds({}, "NQ")
    assert "NQ" in str(exc_info.value)


def test_get_t_thresholds_raises_when_config_empty() -> None:
    """設定が空または [T] がないとき get_t_thresholds は FactorsConfigError を上げる。"""
    with pytest.raises(FactorsConfigError) as exc_info:
        get_t_thresholds({})
    assert "T" in str(exc_info.value)


def test_get_u_thresholds_raises_when_config_empty() -> None:
    """設定が空または [U] がないとき get_u_thresholds は FactorsConfigError を上げる。"""
    with pytest.raises(FactorsConfigError) as exc_info:
        get_u_thresholds({})
    assert "U" in str(exc_info.value)


def test_get_s_thresholds_raises_when_config_empty() -> None:
    """設定が空または [S] がないとき get_s_thresholds は FactorsConfigError を上げる。"""
    with pytest.raises(FactorsConfigError) as exc_info:
        get_s_thresholds({})
    assert "S" in str(exc_info.value)


def test_get_c_thresholds_raises_when_config_empty() -> None:
    """設定が空または [symbol.C] がないとき get_c_thresholds は FactorsConfigError を上げる。"""
    with pytest.raises(FactorsConfigError):
        get_c_thresholds({}, "NQ")
    with pytest.raises(FactorsConfigError):
        get_c_thresholds({"NQ": {}}, "NQ")


def test_get_r_thresholds_raises_when_config_empty() -> None:
    """設定が空または [symbol.R] がないとき get_r_thresholds は FactorsConfigError を上げる。"""
    with pytest.raises(FactorsConfigError):
        get_r_thresholds({}, "GC")
    with pytest.raises(FactorsConfigError):
        get_r_thresholds({"GC": {}}, "GC")
