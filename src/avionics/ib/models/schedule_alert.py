from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ScheduleAlertKind = Literal[
    "market_closed",
    "shortened_close",
    "dst_transition",
]


@dataclass(frozen=True)
class ScheduleAlert:
    """取引時間スキャンで検知した差分（日本語本文は reports 層で付与）。"""

    kind: ScheduleAlertKind
    relative_offset: int
    """today からの日数（1 = 翌暦日）。"""
    trade_date_key: str
    """YYYYMMDD。DST のときは該当する暦日が取れるなら入れる（なければ空）。"""
    close_hhmm: str | None = None
    """短縮営業時の終了 4 桁 HHMM。"""
    tz_label: str | None = None
    """短縮メッセージ用 CT/ET 等。"""
