from __future__ import annotations

from typing import Any

BREAKDOWN_LEVEL_STR = {0: "0", 1: "1", 2: "2"}
def breakdown_level_suffix(fac: Any) -> str:
    if fac is None:
        return "—"
    return BREAKDOWN_LEVEL_STR.get(int(fac.level), "?")


def value_entry(value: str, *, hit: bool = False) -> dict[str, object]:
    entry: dict[str, object] = {"value": value}
    if hit:
        entry["hit"] = True
    return entry


def mark_value_keys(values: dict[str, dict[str, object]], keys: set[str]) -> None:
    for k in keys:
        if k in values:
            values[k]["hit"] = True


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
