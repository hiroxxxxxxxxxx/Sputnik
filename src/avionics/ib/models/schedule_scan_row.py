from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .schedule_alert import ScheduleAlert


@dataclass(frozen=True)
class ScheduleScanRow:
    """Telegram /schedule など向けの 1 銘柄分スキャン結果。"""

    symbol: str
    alerts: List[ScheduleAlert]
    trading_hours_raw: str
    liquid_hours_raw: str
    timezone_id: str
    scan_used_liquid: bool
    fetch_error: Optional[str] = None
