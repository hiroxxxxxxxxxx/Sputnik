"""
NY 市場カレンダー・RTH 判定。bundle の as_of 日付解決に使用。

定義書「Phase 5 fetch_signal_bundle」参照。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

NY_TZ = ZoneInfo("America/New_York")

# NY 現物 RTH: 9:30–16:00 ET（復帰判定で「当日未確定」を避けるため場中は前営業日を使う）
NY_RTH_START = (9, 30)
NY_RTH_END = (16, 0)


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


def is_ny_rth(utc_now: datetime | None = None) -> bool:
    """
    NY 現物の RTH（9:30–16:00 ET）場中かどうか。
    土日は False。定義書・avionics.ib の useRTH と合わせる。
    """
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    if utc_now.tzinfo is None:
        utc_now = utc_now.replace(tzinfo=timezone.utc)
    ny = utc_now.astimezone(NY_TZ)
    if ny.weekday() >= 5:  # Sat=5, Sun=6
        return False
    t = ny.time()
    start = datetime.strptime(f"{NY_RTH_START[0]:02d}:{NY_RTH_START[1]:02d}", "%H:%M").time()
    end = datetime.strptime(f"{NY_RTH_END[0]:02d}:{NY_RTH_END[1]:02d}", "%H:%M").time()
    return start <= t < end


def previous_ny_business_day(ny_date: date) -> date:
    """NY の日付を受け取り、前営業日を返す。土日はスキップ。"""
    d = ny_date - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def as_of_for_bundle(utc_now: datetime | None = None) -> date:
    """
    fetch_signal_bundle に渡す as_of を返す。
    場中（NY RTH）のときは前営業日を使い、復帰 x/N が未確定の当日バーで 0 に振れるのを防ぐ。
    場外なら NY の「今日」。
    """
    ny_today = ny_date_now(utc_now)
    if is_ny_rth(utc_now):
        return previous_ny_business_day(ny_today)
    return ny_today
