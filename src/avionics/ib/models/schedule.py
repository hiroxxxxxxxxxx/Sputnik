from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from typing import List


@dataclass
class DaySchedule:
    date_str: str
    sessions: List[str]
    close_time: str
    start_times: List[time]
    end_times: List[time]

    @property
    def as_date(self) -> date:
        return date(
            int(self.date_str[:4]),
            int(self.date_str[4:6]),
            int(self.date_str[6:8]),
        )
