"""
エンジンペアの組み立て（Factory）。Blueprint で設計図を確定し、Engine を生成する。

定義書「1-3」参照。
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Tuple

from .blueprint import LayerBlueprint
from .engine import Engine


def _default_blueprints() -> Dict[str, LayerBlueprint]:
    """Main / Attitude / Booster のデフォルト設計図。定義書「1-4」「6-2」に準拠。"""
    main = LayerBlueprint.from_dict(
        "Main",
        {
            "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Emergency": {"future": 1.0, "option_k1": -1.0, "option_k2": 1.0},
        },
    )
    attitude = LayerBlueprint.from_dict(
        "Attitude",
        {
            "Boost": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
        },
    )
    booster = LayerBlueprint.from_dict(
        "Booster",
        {
            "Boost": {"future": 1.5, "option_k1": -1.5, "option_k2": 0.0},
            "Cruise": {"future": 1.0, "option_k1": -1.0, "option_k2": 0.0},
            "Emergency": {"future": 0.0, "option_k1": 0.0, "option_k2": 0.0},
        },
    )
    return {"Main": main, "Attitude": attitude, "Booster": booster}


def build_engine(
    symbol_type: Literal["NQ", "GC"],
    *,
    blueprints: Optional[Dict[str, LayerBlueprint]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Engine:
    """
    指定銘柄用エンジンを1台組み立てる。

    :param symbol_type: "NQ" or "GC"
    :param blueprints: 層名→LayerBlueprint。必須。
    :param config: 銘柄固有設定（base_unit, boost_ratio 等）
    :raises ValueError: blueprints が None の場合。
    定義書「1-3」参照。
    """
    if blueprints is None:
        raise ValueError(
            "blueprints is required. Pass e.g. engines.factory._default_blueprints() or your own Dict[str, LayerBlueprint]."
        )
    return Engine(symbol_type, blueprints, config=config)


def build_nq_engine(
    *,
    blueprints: Optional[Dict[str, LayerBlueprint]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Engine:
    """NQ 用エンジンを1台組み立てる。build_engine のエイリアス。"""
    return build_engine("NQ", blueprints=blueprints, config=config)


def build_gc_engine(
    *,
    blueprints: Optional[Dict[str, LayerBlueprint]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Engine:
    """GC 用エンジンを1台組み立てる。build_engine のエイリアス。"""
    return build_engine("GC", blueprints=blueprints, config=config)


def build_engine_pair(
    *,
    blueprints_nq: Optional[Dict[str, LayerBlueprint]] = None,
    blueprints_gc: Optional[Dict[str, LayerBlueprint]] = None,
    nq_config: Optional[Dict[str, Any]] = None,
    gc_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Engine, Engine]:
    """
    NQ/GC 用のエンジンペアを生成する。

    :return: (engine_nq, engine_gc)
    定義書「1-3」参照。
    """
    engine_nq = build_engine("NQ", blueprints=blueprints_nq, config=nq_config)
    engine_gc = build_engine("GC", blueprints=blueprints_gc, config=gc_config)
    return (engine_nq, engine_gc)
