"""取引時間スキャン（/schedule）の本文整形。"""

from __future__ import annotations

from avionics.ib.models.schedule_alert import ScheduleAlert
from avionics.ib.models.schedule_scan_row import ScheduleScanRow


def _schedule_raw_list_lines(heading: str, raw: str) -> list[str]:
    out = [heading]
    stripped = (raw or "").strip()
    if not stripped:
        out.append("  （なし）")
        return out
    parts = [p.strip() for p in stripped.split(";") if p.strip()]
    for i, part in enumerate(parts, 1):
        out.append(f"  {i}. {part}")
    return out


def _relative_day_label_jp(offset: int) -> str:
    if offset == 1:
        return "明日"
    if offset == 2:
        return "明後日"
    return f"{offset}日後"


def _ib_hours_source_label(scan_used_liquid: bool) -> str:
    return "liquidHours" if scan_used_liquid else "tradingHours"


def _format_alert_line(alert: ScheduleAlert, scan_used_liquid: bool) -> str:
    off = alert.relative_offset
    key = alert.trade_date_key
    day_l = _relative_day_label_jp(off)
    src = _ib_hours_source_label(scan_used_liquid)
    if alert.kind == "market_closed":
        return (
            f"【休場】{day_l}（{key}）。"
            f"IB {src} 上は取引なし（または当該日がスケジュールに含まれない）。"
        )
    if alert.kind == "shortened_close":
        hhmm = alert.close_hhmm or ""
        tz = alert.tz_label or "ET"
        if len(hhmm) != 4:
            raise ValueError(f"shortened_close requires 4-digit close_hhmm, got {hhmm!r}")
        return (
            f"【短縮営業】{day_l}（{key}）。"
            f"終了 {hhmm[:2]}:{hhmm[2:]} {tz}（通常より早い）。"
        )
    if alert.kind == "dst_transition":
        return (
            f"【夏冬時間】{day_l}（{key}）。"
            "米国の夏時間/冬時間切替の見込み。日本時間での監視開始時刻を確認してください。"
        )
    raise ValueError(f"unknown ScheduleAlert.kind: {alert.kind!r}")


def format_schedule_scan(rows: list[ScheduleScanRow]) -> str:
    """ScheduleScanRow 一覧を Telegram 向けプレーンテキストにする。"""
    lines: list[str] = ["【取引時間スキャン】"]
    for row in rows:
        lines.append(f"\n{row.symbol}:")
        if row.fetch_error:
            lines.append("  取引時間の取得に失敗しました。")
            lines.append(f"  詳細: {row.fetch_error}")
            continue
        tz_disp = (
            row.timezone_id.strip() if row.timezone_id.strip() else "（未取得）"
        )
        lines.append(f"  timeZoneId: {tz_disp}")
        lines.append(
            f"  判定スケジュール: {'liquidHours' if row.scan_used_liquid else 'tradingHours'}"
        )
        lines.extend(
            _schedule_raw_list_lines("  tradingHours（RAW・;区切り）:", row.trading_hours_raw)
        )
        lines.extend(
            _schedule_raw_list_lines("  liquidHours（RAW・;区切り）:", row.liquid_hours_raw)
        )
        lines.append("  ── 判定 ──")
        if row.alerts:
            for alert in row.alerts:
                lines.append(f"  {_format_alert_line(alert, row.scan_used_liquid)}")
        else:
            lines.append("明日以降の変化なし")
    return "\n".join(lines)
