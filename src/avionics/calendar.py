"""
NY 市場カレンダー・RTH 判定。bundle の as_of 日付解決に使用。

定義書「Phase 5 fetch_signal_bundle」参照。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

NY_TZ = ZoneInfo("America/New_York")
JST_TZ = ZoneInfo("Asia/Tokyo")

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


def next_ny_business_day(ny_date: date) -> date:
    """NY の日付を受け取り、次の営業日を返す。土日はスキップ。"""
    d = ny_date + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def latest_closed_ny_session_date(utc_now: datetime | None = None) -> date:
    """
    直前に close した NY セッション日を返す。

    入口層（Telegram/CLI/Batch）で as_of を統一決定するための共通関数。
    以下の規則で、必ず「既に確定した日足」を返す:
    - 週末: 直前営業日
    - 平日 RTH 場中: 前営業日
    - 平日 RTH 外かつ 16:00 ET 以降: 当日
    - 平日 RTH 外かつ 16:00 ET 未満: 前営業日

    注: 米国祝日は未モデル化（必要なら取引所カレンダー連携で拡張）。
    """
    if utc_now is None:
        utc_now = datetime.now(timezone.utc)
    if utc_now.tzinfo is None:
        utc_now = utc_now.replace(tzinfo=timezone.utc)
    ny = utc_now.astimezone(NY_TZ)
    d = ny.date()
    if ny.weekday() >= 5:
        return previous_ny_business_day(d)
    if is_ny_rth(utc_now):
        return previous_ny_business_day(d)
    close_t = time(NY_RTH_END[0], NY_RTH_END[1])
    if ny.time() >= close_t:
        return d
    return previous_ny_business_day(d)


def zoneinfo_or_none(tz_id: str | None) -> ZoneInfo | None:
    """tz_id を ZoneInfo に変換して返す。解決できない場合は None。"""
    if not tz_id:
        return None
    try:
        return ZoneInfo(str(tz_id))
    except Exception:
        return None


def local_datetime_from_date_time(
    *,
    d: date,
    t: time,
    tz_id: str | None,
) -> datetime:
    """
    (date, time, tz_id) から tz-aware datetime を作る。
    tz_id が解決できない場合は NY_TZ を使う（現行シンボルが ET で返る前提の後方互換）。
    """
    tz = zoneinfo_or_none(tz_id) or NY_TZ
    return datetime.combine(d, t, tzinfo=tz)


def convert_datetime(dt: datetime, tz: ZoneInfo) -> datetime:
    """tz-aware datetime を別タイムゾーンへ変換して返す。"""
    if dt.tzinfo is None:
        raise ValueError("convert_datetime requires tz-aware datetime")
    return dt.astimezone(tz)


def ceil_to_next_hour(dt: datetime) -> datetime:
    """
    dt を「次の1時間境界（XX:00）」へ切り上げる。
    すでにちょうど HH:00:00 の場合はそのまま返す。
    """
    if dt.tzinfo is None:
        raise ValueError("ceil_to_next_hour requires tz-aware datetime")
    if dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt
    base = dt.replace(minute=0, second=0, microsecond=0)
    return base + timedelta(hours=1)
