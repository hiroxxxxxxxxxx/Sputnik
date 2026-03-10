"""
航空機推進・制御システム（Phase 3 最終階層）。

FlightController はエンジンを生成せず、外から list[Engine] を注入。エンジン組み立ては build_engine_pair で行う。
Engine は NQ/GC 単一銘柄で MainPart / AttitudePart / BoosterPart の3層。バンドルは単一銘柄専用（NQ or GC）。
定義書「1」セクション1-1〜1-5参照。
"""

from .blueprint import LayerBlueprint
from .blueprint import LayerType, ModeType, contract_size, contract_symbol
from .engine import Engine
from .factory import build_engine_pair, build_gc_engine, build_nq_engine
from .inventory import EngineInventory
from .main_part import MainPart
from .attitude_part import AttitudePart
from .booster_part import BoosterPart

__all__ = [
    "Engine",
    "EngineInventory",
    "LayerBlueprint",
    "LayerType",
    "ModeType",
    "contract_size",
    "contract_symbol",
    "build_engine_pair",
    "build_nq_engine",
    "build_gc_engine",
    "MainPart",
    "AttitudePart",
    "BoosterPart",
]
