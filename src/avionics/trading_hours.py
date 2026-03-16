"""
取引所カレンダー（tradingHours）のパースと、夏冬・短縮・休場の事前通知ロジック。

IBKR の tradingHours 文字列をパースし、翌日以降の「終了時刻の変化」「短縮営業」「休場」を
検知してメッセージを返す。IB 接続を使う取得・スキャンは avionics.ib.schedule_scan に集約済み。

タイムゾーン:
  tradingHours / liquidHours に含まれる時間は、その銘柄の主市場の現地時間です。
  NQ（CME）・GC（COMEX）はニューヨーク時間（EST/EDT）で返ります。
  判定ロジックでは OS のローカル時間に頼らず、zoneinfo（または pytz）で明示的に
  ニューヨーク時間を取得して比較するのが安全です。

Trade Date（日付ラベル）:
  日付ラベルは、その取引所の時刻基準で清算がつく日＝ Trade Date（清算日）です。
  例: 月曜 09:30–16:00 ET のセッションは「月曜」の足。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List

# tradingHours の典型形式（いずれも取引所現地時間 ET）:
#   "20250310:0930-1600;20250311:0930-1600"  日足現物
#   "20260312:1800-1700"                      23h市場: 18:00オープン〜翌17:00クローズ（日付は Trade Date＝クローズ日）
# 1日複数セッションはカンマ区切り。日付ごとはセミコロン。
DATE_SESSION_RE = re.compile(r"(\d{8}):([^;]+)")


@dataclass
class DaySchedule:
    """
    1日分の取引スケジュール（取引所現地時間 ET）。

    date_str は Trade Date ＝ そのセッションが終了する日の YYYYMMDD。
    close_time は最後のセッション終了時刻 "1600" など（ET）。
    """
    date_str: str  # YYYYMMDD（Trade Date = セッション終了日）
    sessions: List[str]  # ["0930-1600"] または "1800-1700"（23h）など
    close_time: str = ""  # 最後のセッション終了 "1600" / "1700"（ET）


def parse_trading_hours(raw: str) -> List[DaySchedule]:
    """
    IBKR の tradingHours 文字列をパースし、日付ごとのスケジュールリストを返す。

    時間は取引所現地時間（NQ/GC は ET）。日付は Trade Date（セッション終了日）。
    形式例: "20250310:0930-1600;20250311:0930-1300"
    23h市場例: "20260312:1800-1700" → その日の Trade Date で 17:00 クローズ。
    該当なし・空の場合は [] を返す。
    """
    if not raw or not raw.strip():
        return []
    result: List[DaySchedule] = []
    # セミコロンで日付ブロックに分割
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        # "YYYYMMDD:session1,session2,..."
        match = DATE_SESSION_RE.match(part)
        if not match:
            # 別形式: YYYY-MM-DD:HHMM-HHMM の可能性
            for m in re.finditer(r"(\d{4})-?(\d{2})-?(\d{2}):(\d{4})-(\d{4})", part):
                y, mo, d = m.group(1), m.group(2), m.group(3)
                date_str = f"{y}{mo}{d}"
                sess = f"{m.group(4)}-{m.group(5)}"
                close_time = m.group(5)
                result.append(DaySchedule(date_str=date_str, sessions=[sess], close_time=close_time))
            continue
        date_str = match.group(1)
        session_part = match.group(2)
        sessions = [s.strip() for s in session_part.split(",") if s.strip()]
        close_time = ""
        for s in sessions:
            # "0930-1600" -> 1600
            if "-" in s:
                close_time = s.split("-")[-1].strip()[:4]
        result.append(DaySchedule(date_str=date_str, sessions=sessions, close_time=close_time or "1600"))
    return result


def _normalize_close(close_time: str) -> str:
    """1600, 16:00, 4:00 PM などを 1600 形式に。"""
    s = re.sub(r"[:\s]", "", close_time).strip()
    if len(s) == 4 and s.isdigit():
        return s
    return "1600"


def check_upcoming_schedule(
    schedule_list: List[DaySchedule],
    days: int = 3,
    normal_close_et: str = "1600",
) -> List[str]:
    """
    パース済みスケジュールから、DST 切り替え・短縮営業・休場の通知メッセージを生成する。

    比較はすべて取引所現地時間（ET）で行う。today は実行環境の date.today() であり、
    スケジュールの日付（Trade Date）と対応づけて今日・明日を判定する。

    :param schedule_list: parse_trading_hours の戻り値（日付昇順推奨）
    :param days: 何日先まで見るか（今日・明日・明後日なら 3）
    :param normal_close_et: 通常終了時刻 "1600"（ET）
    :return: Telegram に送る文言のリスト。空なら変化なし。
    """
    normal_close = _normalize_close(normal_close_et)
    by_date = {s.date_str: s for s in schedule_list}
    today = date.today()
    messages: List[str] = []

    # 今日の終了時刻（明日との比較で DST 検知に使う）
    today_key = today.strftime("%Y%m%d")
    today_sched = by_date.get(today_key)
    today_close = _normalize_close(today_sched.close_time) if today_sched else "1600"

    for i in range(1, days):
        d = today + timedelta(days=i)
        key = d.strftime("%Y%m%d")
        sched = by_date.get(key)
        if not sched:
            if i == 1:
                messages.append("⚠️ 明日は取引所休場のため、システム監視をスキップすることを推奨します。")
            else:
                day_label = "明後日" if i == 2 else f"{i}日後"
                messages.append(f"⚠️ {day_label}（{key}）はスケジュールに含まれていません。休場の可能性があります。")
            continue

        day_close = _normalize_close(sched.close_time)
        if len(day_close) == 4 and day_close.isdigit():
            day_close_val = int(day_close)
        else:
            day_close_val = 1600
        today_close_val = int(today_close) if today_close.isdigit() else 1600

        if i == 1:
            # 短縮営業: 明日の終了が通常より早い
            if day_close < normal_close:
                messages.append(
                    f"⚠️ 明日は短縮営業です（終了: {day_close[:2]}:{day_close[2:]} ET）。"
                    "1時間足監視はスキップすることを推奨します。"
                )
            # 夏冬切り替え: 今日と明日の終了時刻が1時間ズレ
            if abs(day_close_val - today_close_val) == 100:
                messages.append(
                    "⏰ 明日から米国時間（夏時間/冬時間）が切り替わります。"
                    "日本時間の日次判定・監視開始時刻が1時間スライドします。"
                )
            elif abs(day_close_val - today_close_val) in (2300, 900):  # 23:00→00:00 等の境界
                messages.append(
                    "⏰ 明日から米国時間が切り替わります。"
                    "日次判定・監視開始時刻の見直しを推奨します。"
                )

    return messages
