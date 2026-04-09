"""breakdown レポート用: P 分類理由 id → 入力行キー（★ 付与の一部）。

Calm 以外では format_breakdown_report が本辞書と p_failed_p0_row_keys の和集合で ★ を付ける（陥落要因の列挙）。
"""

from __future__ import annotations

from avionics.factors.p_factor import PClassifyReasonId

_P_BREAKDOWN_P_HIT_KEYS: dict[PClassifyReasonId, frozenset[str]] = {
    "P2_daily": frozenset({"daily_change"}),
    "P2_cum2": frozenset({"cum2_change"}),
    "P2_gap_down": frozenset({"high_20_gap", "trend"}),
    "P1_daily_band": frozenset({"daily_change"}),
    "P1_cum5_band": frozenset({"cum5_change"}),
    "P1_gap_band": frozenset({"high_20_gap"}),
    # P0 は「決定枝＝ストレス検知」ではないため入力行に ★ を付けない（異常側の枝だけマーク）
    "P0_calm": frozenset(),
    "P1_default": frozenset(),
}


def p_breakdown_hit_row_keys(reason: PClassifyReasonId) -> frozenset[str]:
    """breakdown の P/T 価格ブロックで、理由 id に応じて ★ を付ける row_key 集合。"""
    return _P_BREAKDOWN_P_HIT_KEYS[reason]
