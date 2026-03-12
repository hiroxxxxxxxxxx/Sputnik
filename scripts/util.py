"""
scripts 用ユーティリティ。日付・時刻など。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

NY_TZ = ZoneInfo("America/New_York")


def ny_date_now(utc_now: datetime | None = None) -> date:
    """
    基準時刻を NY の日付に変換して返す。
    fetch_signal_bundle の as_of に渡して、バー日付（Trade Date）と整合させる。

    :param utc_now: 基準とする UTC 時刻。None のときは datetime.now(timezone.utc)
    """
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    if utc_now.tzinfo is None:
        utc_now = utc_now.replace(tzinfo=timezone.utc)
    return utc_now.astimezone(NY_TZ).date()
