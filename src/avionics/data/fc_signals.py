"""
Data: FlightController が入出力に使う型（Layer 3 の計器結論）。

EngineFactorMapping / FlightControllerSignal。
定義書「3.フライトコントローラー」「4-2」「Phase 5 Signal」参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


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


@dataclass
class FlightControllerSignal:
    """
    FlightController が出力する計器の結論。銘柄別 ICL と共通の SCL/LCL のみ保持。
    throttle_level(symbol) = max(icl_by_symbol[symbol], scl, lcl)。Cockpit・Protocol の入力。
    定義書「Phase 5 Telegram統合」Signal 定義参照。
    """

    icl_by_symbol: Dict[str, int]
    """銘柄ごとの ICL（個別制御層）= max(P, V, C/R)。キーは symbol（例: "NQ", "GC"）。"""

    scl: int
    """SCL（同期制御層）= T 相関のレベル。全銘柄共通。"""

    lcl: int
    """LCL（制限制御層）= max(U, S)。全銘柄共通。"""

    @property
    def throttle_by_symbol(self) -> Dict[str, int]:
        """銘柄ごとの実行レベル Effective = max(ICL, SCL, LCL)。Cockpit の apply_mode 用。"""
        return {
            sym: max(icl, self.scl, self.lcl)
            for sym, icl in self.icl_by_symbol.items()
        }

    def throttle_level(self, symbol: str) -> int:
        """指定銘柄の実行レベル。銘柄が無い場合は 0。"""
        return max(self.icl_by_symbol.get(symbol, 0), self.scl, self.lcl)

    @property
    def worst_throttle_level(self) -> int:
        """全銘柄の throttle_level の最大値。承認ゲート・dispatch_protocol 用。"""
        if not self.icl_by_symbol:
            return max(0, self.scl, self.lcl)
        return max(self.throttle_level(sym) for sym in self.icl_by_symbol)

    @property
    def any_critical(self) -> bool:
        """LCL>=2 のとき True。承認スキップ判定用。"""
        return self.lcl >= 2
