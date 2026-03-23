"""
Data: FlightController が入出力に使う型（Layer 3 の計器結論）。

EngineFactorMapping / FlightControllerSignal。
定義書「3.フライトコントローラー」「4-2」「Phase 5 Signal」参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


@dataclass
class EngineFactorMapping:
    """
    エンジン(Symbol) ↔ Factor のマッピング。ICL/SCL/LCL の入力となる。
    Assembly が組み立て、FlightController と三層算出は受け取って参照するだけ。
    定義書「4-2」因子の割り当て参照。
    """

    symbol_factors: Dict[str, List[Any]]
    """銘柄別因子。{"NQ": [P,V,T,C], "GC": [P,V,T,R]} 等。ICL 用 P,V,C/R と SCL 用 T を含む。"""

    limit_factors: List[Any]
    """制限制御層(LCL)用因子。U, S。全エンジン共通。"""

    global_market_factors: List[Any] = field(default_factory=list)
    """全エンジン共通の個別制御用因子（未使用時は空で可）。"""


SymbolType = Literal["NQ", "GC"]


@dataclass
class FlightControllerSignal:
    """
    FlightController が出力する計器の結論（固定版）。

    NQ/GC を固定シンボルとして扱い、ICL/SCL/LCL と因子レベル（P,V,C,R,T,U,S）をすべて包含する。
    DB書き込み・レポート生成が同一オブジェクトを参照できるようにする。
    定義書「Phase 5 Telegram統合」Signal 定義参照。
    """

    scl: int
    """SCL（同期制御層）= T 相関のレベル。全銘柄共通。"""

    lcl: int
    """LCL（制限制御層）= max(U, S)。全銘柄共通。"""

    nq_icl: int = 0
    gc_icl: int = 0

    # Factor levels (symbol-specific)
    nq_p: int = 0
    nq_v: int = 0
    nq_c: int = 0
    nq_r: int = 0

    gc_p: int = 0
    gc_v: int = 0
    gc_c: int = 0
    gc_r: int = 0

    # Factor levels (common)
    t: int = 0
    u: int = 0
    s: int = 0

    @property
    def icl_by_symbol(self) -> Dict[str, int]:
        """互換用: 銘柄→ICL の辞書ビュー（読み取り専用）。"""
        return {"NQ": self.nq_icl, "GC": self.gc_icl}

    @property
    def throttle_by_symbol(self) -> Dict[str, int]:
        """銘柄ごとの実行レベル Effective = max(ICL, SCL, LCL)。Cockpit の apply_mode 用。"""
        return {"NQ": self.throttle_level("NQ"), "GC": self.throttle_level("GC")}

    def throttle_level(self, symbol: SymbolType | str) -> int:
        """指定銘柄の実行レベル。銘柄が無い場合は 0。"""
        if symbol == "NQ":
            icl = self.nq_icl
        elif symbol == "GC":
            icl = self.gc_icl
        else:
            return 0
        return max(icl, self.scl, self.lcl)

    @property
    def worst_throttle_level(self) -> int:
        """全銘柄の throttle_level の最大値。承認ゲート・dispatch_protocol 用。"""
        return max(self.throttle_level("NQ"), self.throttle_level("GC"))

    @property
    def any_critical(self) -> bool:
        """LCL>=2 のとき True。承認スキップ判定用。"""
        return self.lcl >= 2
