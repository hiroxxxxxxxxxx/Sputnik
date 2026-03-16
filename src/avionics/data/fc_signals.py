"""
Data: FlightController が入出力に使う型（Layer 3 の計器結論）。

EngineFactorMapping / SymbolSignal / FlightControllerSignal。
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
class SymbolSignal:
    """
    1 銘柄分の「計器の結論」。throttle_level(=Effective) / icl / is_critical のみ保持。
    表示用（reason / raw_metrics / recovery_metrics）は呼び出し側で format_fc_signal ヘルパーから取得。
    FlightControllerSignal.by_symbol[symbol] で参照する。SCL/LCL は全銘柄共通のため FlightControllerSignal 側に保持。
    """

    throttle_level: int
    """0: Boost, 1: Cruise, 2: Emergency。Effective = max(ICL, SCL, LCL)。"""

    icl: int
    """ICL（個別制御層）= max(P, V, C/R) の銘柄別レベル。内訳・レポート用。"""

    is_critical: bool
    """True なら FC での承認をスキップして即時プロトコル発火。現在は LCL>=2（制限層 Emergency）のみ。定義書で変更可。"""


@dataclass
class FlightControllerSignal:
    """
    FlightController が出力する「計器の結論」を全銘柄分まとめてカプセル化したデータ構造。
    by_symbol[symbol] で銘柄ごとの SymbolSignal を参照する。scl / lcl は全銘柄共通のためここに保持。
    Cockpit（管制層）の承認ゲートや Protocol 起動の入力。定義書「Phase 5 Telegram統合」Signal 定義参照。
    """

    by_symbol: Dict[str, SymbolSignal]
    """銘柄ごとの計器結論。キーは symbol（例: "NQ", "GC"）。"""

    scl: int
    """SCL（同期制御層）= T 相関のレベル。全銘柄共通。内訳・レポート用。"""

    lcl: int
    """LCL（制限制御層）= max(U, S)。全銘柄共通。内訳・レポート用。"""

    @property
    def worst_throttle_level(self) -> int:
        """全銘柄の throttle_level の最大値。承認ゲート・dispatch_protocol 用。"""
        return max((s.throttle_level for s in self.by_symbol.values()), default=0)

    @property
    def any_critical(self) -> bool:
        """いずれか銘柄が is_critical のとき True。承認スキップ判定用。"""
        return any(s.is_critical for s in self.by_symbol.values())
