"""
取引時間スキャン（IB 接続を使い、翌日以降の DST・短縮・休場を通知する）。

IB I/O と tradingHours 文字列のパースを担当する。
"""

from __future__ import annotations

import re
from datetime import time
from typing import Any, List

from ..models.contracts import contract_for_price
from ..models.schedule import DaySchedule

DATE_SESSION_RE = re.compile(r"(\d{8}):([^;]+)")


def parse_trading_hours(raw: str) -> List[DaySchedule]:
    if not raw or not raw.strip():
        raise ValueError("tradingHours is empty")
    result: List[DaySchedule] = []
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        match = DATE_SESSION_RE.match(part)
        if not match:
            for m in re.finditer(r"(\d{4})-?(\d{2})-?(\d{2}):(\d{4})-(\d{4})", part):
                y, mo, d = m.group(1), m.group(2), m.group(3)
                date_str = f"{y}{mo}{d}"
                left = m.group(4)
                right = m.group(5)
                sess = f"{left}-{right}"
                close_time = right
                result.append(
                    DaySchedule(
                        date_str=date_str,
                        sessions=[sess],
                        close_time=close_time,
                        start_times=[time(int(left[:2]), int(left[2:]))],
                        end_times=[time(int(right[:2]), int(right[2:]))],
                    )
                )
            continue
        date_str = match.group(1)
        session_part = match.group(2)
        sessions_raw = [s.strip() for s in session_part.split(",") if s.strip()]
        sessions: List[str] = []
        start_times: List[time] = []
        end_times: List[time] = []
        close_time = ""
        for s in sessions_raw:
            if s.upper() == "CLOSED":
                sessions.append("CLOSED")
                continue
            if "-" not in s:
                continue
            left, right = s.split("-", 1)
            left = left.strip()
            right = right.strip()
            if ":" in left:
                left = left.split(":")[-1].strip()
            if ":" in right:
                right = right.split(":")[-1].strip()
            left = re.sub(r"[:\s]", "", left)
            right = re.sub(r"[:\s]", "", right)
            if len(left) == 4 and left.isdigit() and len(right) == 4 and right.isdigit():
                sessions.append(f"{left}-{right}")
                start_times.append(time(int(left[:2]), int(left[2:])))
                end_times.append(time(int(right[:2]), int(right[2:])))
                close_time = right

        result.append(
            DaySchedule(
                date_str=date_str,
                sessions=sessions,
                close_time=close_time or "1600",
                start_times=start_times,
                end_times=end_times,
            )
        )
    if not result:
        raise ValueError(f"failed to parse tradingHours: {raw}")
    return result


class IBScheduleClient:
    """IB の取引時間 I/O を担当するクライアント。"""

    def __init__(self, ib: Any) -> None:
        self._ib = ib

    @staticmethod
    def contract_for_symbol(symbol: str) -> Any:
        return contract_for_price(symbol)

    async def fetch_trading_hours(self, contract: Any) -> List[DaySchedule]:
        """
        IB の reqContractDetails で契約詳細を取得し、tradingHours をパースして返す。

        返る時間はその銘柄の主市場の現地時間（NQ/GC は ET）。日付は Trade Date。
        """
        try:
            details_list = await self._ib.reqContractDetailsAsync(contract)
        except Exception as exc:
            raise ValueError(f"failed to fetch contract details: {exc}") from exc
        if not details_list:
            raise ValueError("contract details are empty")
        details = details_list[0]
        raw = getattr(details, "tradingHours", None) or getattr(details, "trading_hours", None)
        if not raw:
            raise ValueError("tradingHours field is empty")
        return parse_trading_hours(str(raw))

    async def fetch_schedule_bundle(self, contract: Any) -> dict[str, Any]:
        try:
            details_list = await self._ib.reqContractDetailsAsync(contract)
        except Exception as exc:
            raise ValueError(f"failed to fetch contract details: {exc}") from exc
        if not details_list:
            raise ValueError("contract details are empty")
        details = details_list[0]
        raw_trading = getattr(details, "tradingHours", None) or getattr(details, "trading_hours", None)
        raw_liquid = getattr(details, "liquidHours", None) or getattr(details, "liquid_hours", None)
        raw_tz = getattr(details, "timeZoneId", None) or getattr(details, "time_zone_id", None)
        if not raw_trading:
            raise ValueError("tradingHours field is empty")
        trading_schedule = parse_trading_hours(str(raw_trading))
        liquid_schedule = parse_trading_hours(str(raw_liquid)) if raw_liquid else []
        return {
            "trading_schedule": trading_schedule,
            "liquid_schedule": liquid_schedule,
            "timezone_id": str(raw_tz or ""),
        }

