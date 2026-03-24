"""
Data: FlightController が出力する型（Layer 3 の計器結論）。

FlightControllerSignal。
定義書「3.フライトコントローラー」「4-2」「Phase 5 Signal」参照。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal


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

    def get_factor_levels(self, symbol: str) -> Dict[str, int]:
        """
        指定銘柄の P, V, C, R, T, U, S 現在レベルを辞書で返す。
        定義書「Phase 5 raw_metrics」参照。
        """
        base: Dict[str, int] = {"P": 0, "V": 0, "C": 0, "R": 0, "T": int(self.t), "U": int(self.u), "S": int(self.s)}
        if symbol == "NQ":
            base["P"] = int(self.nq_p)
            base["V"] = int(self.nq_v)
            base["C"] = int(self.nq_c)
            base["R"] = int(self.nq_r)
        elif symbol == "GC":
            base["P"] = int(self.gc_p)
            base["V"] = int(self.gc_v)
            base["C"] = int(self.gc_c)
            base["R"] = int(self.gc_r)
        return base

    def reason(self, symbol: str) -> str:
        """
        指定銘柄の三層レベルから判定理由文字列を組み立てる。通知用。
        定義書「Phase 5 通知」参照。
        """
        icl = self.nq_icl if symbol == "NQ" else (self.gc_icl if symbol == "GC" else 0)
        parts: list[str] = []
        if self.lcl > 0:
            parts.append(f"制限層(LCL)={self.lcl}")
        if self.scl > 0:
            parts.append(f"同期層(SCL)={self.scl}")
        if icl > 0:
            parts.append(f"個別層(ICL)={icl}")
        return " / ".join(parts) if parts else "全層0"

    @property
    def summary_reason(self) -> str:
        """銘柄ごとの reason を連結した文字列。承認待ちメッセージ用。"""
        parts = [
            f"NQ: {self.reason('NQ')}",
            f"GC: {self.reason('GC')}",
        ]
        return "; ".join(parts)
