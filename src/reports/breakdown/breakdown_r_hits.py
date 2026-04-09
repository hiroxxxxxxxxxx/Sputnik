"""breakdown レポート用: R ★ 付与キー。

R2 は履歴畳み込みの結果レベルであり、★ は当日ティッカー上の tip_drawdown 行の突出表示のみとする。
履歴上の「真の決定因」までは追わない（別途仕様）。
"""

from __future__ import annotations


def r_breakdown_hit_row_keys(r_level: int) -> frozenset[str]:
    """R2 のとき tip_drawdown 行のみ ★ 対象。"""
    if int(r_level) == 2:
        return frozenset({"tip_drawdown"})
    return frozenset()
