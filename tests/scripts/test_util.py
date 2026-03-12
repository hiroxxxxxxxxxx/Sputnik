"""
scripts.util（ny_date_now 等）のテスト。
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

# scripts を path に追加して util を import 可能に
_scripts = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from util import ny_date_now


def test_ny_date_now_returns_ny_date() -> None:
    """utc_now を渡すと NY の日付が返る。"""
    utc = datetime(2025, 3, 12, 22, 0, 0, tzinfo=timezone.utc)  # 22:00 UTC = 18:00 ET
    assert ny_date_now(utc) == date(2025, 3, 12)
