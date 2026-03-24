"""
Data: エンジン(Symbol) ↔ Factor のマッピング構造。

Assembly が組み立て、FlightController が三層算出（ICL/SCL/LCL）時に参照する。
定義書「4-2」因子の割り当て参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle


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

    def get_recovery_progress(
        self,
        symbol: str,
        bundle: Optional["SignalBundle"] = None,
    ) -> Dict[str, str]:
        """
        復帰ヒステリシス中の因子について「x/N日目」を収集する。
        bundle を渡すときは get_recovery_progress_from_bundle を優先し、
        未実装（None）の場合のみ recovery_confirm_progress にフォールバック。
        bundle 未指定時は recovery_confirm_progress のみ。
        """
        result: Dict[str, str] = {}
        sym_factors = self.symbol_factors.get(symbol, [])
        for f in self.global_market_factors + self.limit_factors + sym_factors:
            name = getattr(f, "name", None)
            if name is None:
                continue
            key = "T" if name.startswith("T_") else name
            if key not in ("P", "V", "C", "R", "T", "U", "S"):
                continue
            p: Optional[Tuple[int, int]] = None
            if bundle is not None:
                from_bundle = getattr(f, "get_recovery_progress_from_bundle", None)
                if callable(from_bundle):
                    p = from_bundle(symbol, bundle)
                if p is None:
                    prog = getattr(f, "recovery_confirm_progress", None)
                    if callable(prog):
                        p = prog()
            else:
                prog = getattr(f, "recovery_confirm_progress", None)
                if callable(prog):
                    p = prog()
            if p is not None:
                result[key] = f"{p[0]}/{p[1]}"
        return result
