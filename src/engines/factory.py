"""
エンジンペアの組み立て（Factory）。Blueprint で設計図を確定し、Engine を生成する。

StrategyBundle は廃止。Main/Attitude/Booster の各 LayerBlueprint を渡す。
定義書「1-3」参照。
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

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


def build_nq_engine(
    *,
    blueprints: Optional[Dict[str, LayerBlueprint]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Engine:
    """
    NQ 用エンジンを1台組み立てる。Blueprint で設計図を確定。

    :param blueprints: 層名→LayerBlueprint。必須。大元で _default_blueprints() を渡すか独自設計図を渡す。
    :param config: NQ 用銘柄固有設定（base_unit, boost_ratio 等）
    :raises ValueError: blueprints が None の場合。
    定義書「1-3」参照。
    """
    if blueprints is None:
        raise ValueError(
            "blueprints is required. Pass e.g. engines.factory._default_blueprints() or your own Dict[str, LayerBlueprint]."
        )
    return Engine("NQ", blueprints, config=config)


def build_gc_engine(
    *,
    blueprints: Optional[Dict[str, LayerBlueprint]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Engine:
    """
    GC 用エンジンを1台組み立てる。Blueprint で設計図を確定。

    :param blueprints: 層名→LayerBlueprint。必須。大元で _default_blueprints() を渡すか独自設計図を渡す。
    :param config: GC 用銘柄固有設定
    :raises ValueError: blueprints が None の場合。
    定義書「1-3」参照。
    """
    if blueprints is None:
        raise ValueError(
            "blueprints is required. Pass e.g. engines.factory._default_blueprints() or your own Dict[str, LayerBlueprint]."
        )
    return Engine("GC", blueprints, config=config)


def build_engine_pair(
    *,
    blueprints_nq: Optional[Dict[str, LayerBlueprint]] = None,
    blueprints_gc: Optional[Dict[str, LayerBlueprint]] = None,
    nq_config: Optional[Dict[str, Any]] = None,
    gc_config: Optional[Dict[str, Any]] = None,
) -> Tuple[Engine, Engine]:
    """
    NQ/GC 用のエンジンペアを生成する。呼び出し側で engines に extend する。

    :param blueprints_nq: NQ 用設計図。未指定時はデフォルト
    :param blueprints_gc: GC 用設計図。未指定時はデフォルト
    :param nq_config: NQ 用銘柄固有設定
    :param gc_config: GC 用銘柄固有設定
    :return: (engine_nq, engine_gc)
    定義書「1-3」参照。
    """
    engine_nq = build_nq_engine(blueprints=blueprints_nq, config=nq_config)
    engine_gc = build_gc_engine(blueprints=blueprints_gc, config=gc_config)
    return (engine_nq, engine_gc)
