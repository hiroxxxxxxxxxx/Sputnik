from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import AltitudeRegime, LiquiditySignals

BREAKDOWN_LEVEL_STR = {0: "0", 1: "1", 2: "2"}
BREAKDOWN_HIT_LEGEND = "※ ★ = 因子判定の決定枝に関係する入力行を示す。"
P_BREAKDOWN_HIT_MARKER = "★"


def kv(label: str, value: str, *, row_key: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {"label": label, "value": value, "hit": ""}
    if row_key is not None:
        row["row_key"] = row_key
    return row


def mark_hits(rows: list[dict[str, Any]], hit_keys: set[str]) -> None:
    for row in rows:
        rk = row.get("row_key")
        if rk and rk in hit_keys:
            row["hit"] = P_BREAKDOWN_HIT_MARKER


def fmt_price(value: float | None) -> str:
    return "—" if value is None else f"{float(value):,.2f}"


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{float(value) * 100:.2f}%"


def fmt_float_or_na(value: float | None) -> str:
    return "N/A" if value is None else f"{float(value):.2f}"


def safe_ratio_text(numerator: float | None, denominator: float | None) -> str:
    if numerator is None or denominator is None or denominator <= 0:
        return "N/A"
    return f"{float(numerator / denominator):.2f}"


def v_confirm_days(
    fc: "FlightController",
    symbol: str,
    *,
    altitude: "AltitudeRegime",
) -> tuple[int | None, int | None]:
    from avionics.factors.v_factor import VFactor

    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, VFactor):
            th = f._get_thresholds(altitude)
            return (int(th["V1_confirm_days"]), int(th["V2_confirm_days"]))
    raise ValueError(f"VFactor not found for symbol={symbol!r} in FlightController mapping")


def v_factor_level(fc: "FlightController", symbol: str) -> int:
    from avionics.factors.v_factor import VFactor

    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, VFactor):
            return int(f.level)
    raise ValueError(f"VFactor not found for symbol={symbol!r} in FlightController mapping")


def factor_from_symbol(fc: "FlightController", symbol: str, cls: type) -> Any:
    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, cls):
            return f
    return None


def first_factor_among_symbols(
    fc: "FlightController",
    symbols: list[str],
    cls: type,
) -> Any:
    for sym in symbols:
        f = factor_from_symbol(fc, sym, cls)
        if f is not None:
            return f
    return None


def limit_factor(fc: "FlightController", cls: type) -> Any:
    for f in fc.mapping.limit_factors:
        if isinstance(f, cls):
            return f
    return None


def breakdown_level_suffix(fac: Any) -> str:
    if fac is None:
        return "—"
    return BREAKDOWN_LEVEL_STR.get(int(fac.level), "?")


def scl_level_for_breakdown(fc: "FlightController") -> int:
    getter = getattr(fc, "get_synchronous_control_level", None)
    if callable(getter):
        return int(getter())
    from avionics.factors.t_factor import TFactor

    t_levels: list[int] = []
    for factors in fc.mapping.symbol_factors.values():
        for fac in factors:
            if isinstance(fac, TFactor):
                t_levels.append(int(fac.level))
                break
    if not t_levels:
        return 0
    if len(t_levels) == 1:
        return t_levels[0]
    if all(lv == 2 for lv in t_levels):
        return 2
    if any(lv == 2 for lv in t_levels):
        return 1
    return 0


def fmt_progress(x: int, total: int) -> str:
    if total <= 0:
        raise ValueError(f"confirm_days must be positive, got {total}")
    return f"{x}/{total}日目"


def liquidity_credit_section(
    section_id: str,
    title: str,
    lc: "LiquiditySignals",
) -> dict[str, Any]:
    rows = [
        kv("終値", fmt_price(lc.last_close)),
        kv("SMA20", fmt_price(lc.sma20)),
        kv("SMA20乖離率", fmt_pct(lc.sma20_gap), row_key="sma20_gap"),
        kv("日次変化率", fmt_pct(lc.daily_change), row_key="daily_change"),
    ]
    return {"section_id": section_id, "title": title, "rows": rows}
