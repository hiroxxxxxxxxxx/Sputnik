"""
航空機推進・制御システム（Phase 3 最終階層）。

FlightController はエンジンを生成せず、外から list[Engine] を注入。エンジン組み立ては build_engine_pair で行う。
Engine は NQ/GC 単一銘柄で Main / Attitude / Booster の3層を Blueprint で管理。
定義書「1」セクション1-1〜1-5参照。
"""

from .blueprint import LayerBlueprint
from .blueprint import LayerType, PART_LAYER_TYPES, PART_NAMES, contract_size, contract_symbol
from .engine import Engine, PartDelta, calculate_net_targets
from .factory import build_engine, build_engine_pair, build_gc_engine, build_nq_engine

__all__ = [
    "Engine",
    "PartDelta",
    "calculate_net_targets",
    "LayerBlueprint",
    "LayerType",
    "PART_LAYER_TYPES",
    "PART_NAMES",
    "contract_size",
    "contract_symbol",
    "build_engine",
    "build_engine_pair",
    "build_nq_engine",
    "build_gc_engine",
]
