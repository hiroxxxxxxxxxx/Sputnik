"""
表示用ヘルパー: reason / raw_metrics / recovery_metrics / summary_reason の組み立て。

FlightController は三層の算出のみ行い、表示用データはここで組み立てる。
呼び出し側（Cockpit・reports）は signal と mapping（と必要なら bundle）を渡して取得する。
定義書「Phase 5 通知」「Phase 5 raw_metrics」参照。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from avionics.data.fc_signals import EngineFactorMapping, FlightControllerSignal

if TYPE_CHECKING:
    from avionics.data.signals import SignalBundle


def build_reason(icl: int, scl: int, lcl: int) -> str:
    """
    個別・同期・制限の三層レベルから判定理由文字列を組み立てる。通知用。
    定義書「Phase 5 通知」参照。
    """
    parts: list[str] = []
    if lcl > 0:
        parts.append(f"制限層(LCL)={lcl}")
    if scl > 0:
        parts.append(f"同期層(SCL)={scl}")
    if icl > 0:
        parts.append(f"個別層(ICL)={icl}")
    return " / ".join(parts) if parts else "全層0"


def get_raw_metrics(mapping: EngineFactorMapping, symbol: str) -> Dict[str, Any]:
    """
    P, V, C, R, T, U, S の現在レベルを収集する。通知用。定義書「Phase 5 raw_metrics」参照。
    """
    metrics: Dict[str, int] = {"P": 0, "V": 0, "C": 0, "R": 0, "T": 0, "U": 0, "S": 0}
    sym_factors = mapping.symbol_factors.get(symbol, [])
    for f in mapping.global_market_factors + mapping.limit_factors + sym_factors:
        name = getattr(f, "name", None)
        if not name or not hasattr(f, "level"):
            continue
        if name in metrics:
            metrics[name] = max(metrics[name], f.level)
        elif name.startswith("T_"):
            metrics["T"] = max(metrics["T"], f.level)
    return metrics


def get_recovery_metrics(
    mapping: EngineFactorMapping,
    symbol: str,
    bundle: Optional["SignalBundle"] = None,
) -> Dict[str, str]:
    """
    復帰ヒステリシス中の因子について「x/N日目」を収集する。Daily Report 用。
    bundle を渡すとステートレス因子は get_recovery_progress_from_bundle でその場計算。未渡しなら recovery_confirm_progress（U/S 用）。
    """
    result: Dict[str, str] = {}
    sym_factors = mapping.symbol_factors.get(symbol, [])
    for f in mapping.global_market_factors + mapping.limit_factors + sym_factors:
        name = getattr(f, "name", None)
        if name is None:
            continue
        key = "T" if (name.startswith("T_")) else name
        if key not in ("P", "V", "C", "R", "T", "U", "S"):
            continue
        p = None
        if bundle is not None:
            from_bundle = getattr(f, "get_recovery_progress_from_bundle", None)
            if callable(from_bundle):
                p = from_bundle(symbol, bundle)
        if p is None:
            prog = getattr(f, "recovery_confirm_progress", None)
            if callable(prog):
                p = prog()
        if p is not None:
            result[key] = f"{p[0]}/{p[1]}"
    return result


def build_summary_reason(signal: FlightControllerSignal) -> str:
    """銘柄ごとの reason を連結した文字列。承認待ちメッセージ用。"""
    parts = [
        f"{sym}: {build_reason(icl, signal.scl, signal.lcl)}"
        for sym, icl in sorted(signal.icl_by_symbol.items())
    ]
    return "; ".join(parts)
