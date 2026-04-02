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
    if alert.kind == "missing_schedule_day":
        if off == 1:
            return (
                "⚠️ 明日は取引所休場のため、システム監視をスキップすることを推奨します。"
            )
        return (
            f"⚠️ {day_l}（{key}）はスケジュールに含まれていません。"
            "休場の可能性があります。"
        )
    if alert.kind == "closed_day":
        return f"⚠️ {day_l}（{key}）は終日休場です（IB {src}）。"
    if alert.kind == "shortened_close":
        hhmm = alert.close_hhmm or ""
        tz = alert.tz_label or "ET"
        if len(hhmm) != 4:
            raise ValueError(f"shortened_close requires 4-digit close_hhmm, got {hhmm!r}")
        return (
            f"⚠️ 明日は短縮営業です（終了: {hhmm[:2]}:{hhmm[2:]} {tz}）。"
            "1時間足監視はスキップすることを推奨します。"
        )
    if alert.kind == "dst_shift_1h":
        return (
            "⏰ 明日から米国時間（夏時間/冬時間）が切り替わります。"
            "日本時間の日次判定・監視開始時刻が1時間スライドします。"
        )
    if alert.kind == "dst_shift_other":
        return (
            "⏰ 明日から米国時間が切り替わります。"
            "日次判定・監視開始時刻の見直しを推奨します。"
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
            lines.append("  特記事項なし（明日以降の変化なし）")
    return "\n".join(lines)
