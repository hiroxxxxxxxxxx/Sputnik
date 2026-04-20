from __future__ import annotations

from typing import TYPE_CHECKING, Any

from avionics.factors.v_factor import v_level_from_index_history_sync
from reports.breakdown.common import BREAKDOWN_LEVEL_STR, fmt_price, mark_value_keys, value_entry

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import AltitudeRegime, SignalBundle


def _factor_from_symbol(fc: "FlightController", symbol: str, cls: type) -> Any:
    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, cls):
            return f
    return None


def _v_confirm_days(fc: "FlightController", symbol: str, *, altitude: "AltitudeRegime") -> tuple[int, int]:
    from avionics.factors.v_factor import VFactor

    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, VFactor):
            th = f._get_thresholds(altitude)
            return (int(th["V1_confirm_days"]), int(th["V2_confirm_days"]))
    raise ValueError(f"VFactor not found for symbol={symbol!r} in FlightController mapping")


def _v_factor_level(fc: "FlightController", symbol: str) -> int:
    from avionics.factors.v_factor import VFactor

    for f in fc.mapping.symbol_factors.get(symbol, []):
        if isinstance(f, VFactor):
            return int(f.level)
    raise ValueError(f"VFactor not found for symbol={symbol!r} in FlightController mapping")


def _infer_v_transition(vs: Any, v_th: dict) -> tuple[int, int, float] | None:
    history = tuple(sorted((getattr(vs, "index_history", ()) or ()), key=lambda x: x[0]))
    if not history:
        return None
    if len(history) == 1:
        prev_level = 0
    else:
        prev_level = int(v_level_from_index_history_sync(history[:-1], v_th, last_knock_in=True))
    current_from_history = int(
        v_level_from_index_history_sync(history, v_th, last_knock_in=bool(vs.v1_to_v0_knock_in_ok))
    )
    latest_index = float(history[-1][1])
    return (prev_level, current_from_history, latest_index)


def _v_hit_keys(vs: Any, v_th: dict, v1_days: int, transition: tuple[int, int, float]) -> set[str]:
    prev_level, current_level, latest_index = transition
    keys: set[str] = set()
    if current_level == 2:
        if latest_index >= float(v_th["V2_on"]):
            keys.add("index_value")
        keys.add("v2_recovery")
        return keys

    if current_level == 1:
        if prev_level == 2:
            # V2->V1 復帰枝では index と復帰日数の両方が決定枝に入る。
            keys.update({"index_value", "v2_recovery"})
            return keys
        if prev_level == 0:
            if latest_index >= float(v_th["V1_on"]):
                keys.add("index_value")
            return keys
        if prev_level == 1:
            v1_off = float(v_th["V1_off"])
            if latest_index < v1_off:
                # 指数は V0 側だが復帰条件で止まるケース: 復帰判定のみ★。
                keys.add("v1_recovery")
                if vs.recovery_confirm_satisfied_days_v1_off >= v1_days:
                    keys.add("v1_knock_in")
            else:
                # 指数条件だけで V1 を維持するケース: 指数のみ★。
                keys.add("index_value")
            return keys

    return keys


def build_v_sections(fc: "FlightController", bundle: "SignalBundle", vol_symbols: list[str], *, altitude: "AltitudeRegime") -> list[dict[str, Any]]:
    from avionics.factors.v_factor import VFactor

    sections: list[dict[str, Any]] = []
    for sym in vol_symbols:
        vs = bundle.volatility_signals[sym]
        v_fac = _factor_from_symbol(fc, sym, VFactor)
        if v_fac is None:
            raise ValueError(f"VFactor not found for symbol={sym!r} in FlightController mapping")
        v_th = v_fac._get_thresholds(altitude)
        v1_days, v2_days = _v_confirm_days(fc, sym, altitude=altitude)
        v_level = _v_factor_level(fc, sym)
        transition = _infer_v_transition(vs, v_th)
        if transition is None:
            raise ValueError(f"V breakdown requires non-empty index_history for symbol={sym!r}")
        if int(transition[1]) != int(v_level):
            raise ValueError(
                f"V breakdown mismatch for symbol={sym!r}: "
                f"factor.level={v_level}, transition_level={transition[1]}"
            )
        values: dict[str, dict[str, object]] = {
            "index_value": value_entry(f"{vs.index_value:.2f}"),
            "high_20": value_entry(fmt_price(vs.high_20)),
        }
        if v_level == 1:
            x1 = min(vs.recovery_confirm_satisfied_days_v1_off, v1_days)
            values["v1_recovery"] = {"done": x1, "total": v1_days}
            if vs.recovery_confirm_satisfied_days_v1_off >= v1_days:
                values["v1_knock_in"] = value_entry("はい" if vs.v1_to_v0_knock_in_ok else "いいえ")
                values["v1_knock_in_time"] = value_entry(vs.knock_in_bar_end or "—")
            if transition[0] == 2:
                x2 = min(vs.recovery_confirm_satisfied_days_v2_off, v2_days)
                values["v2_recovery"] = {"done": x2, "total": v2_days}
        elif v_level == 2:
            x2 = min(vs.recovery_confirm_satisfied_days_v2_off, v2_days)
            values["v2_recovery"] = {"done": x2, "total": v2_days}

        mark_value_keys(values, _v_hit_keys(vs, v_th, v1_days, transition))
        sections.append({"symbol": sym, "v_level": BREAKDOWN_LEVEL_STR[v_level], "values": values})
    return sections


def _default_value(value: str = "—", *, hit: bool = False) -> dict[str, object]:
    row: dict[str, object] = {"value": value}
    if hit:
        row["hit"] = True
    return row


def _default_volatility_section(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "v_level": "—",
        "values": {
            "index_value": _default_value(),
            "high_20": _default_value(),
            "v1_recovery": {"done": "—", "total": "—"},
            "v1_knock_in": _default_value("—"),
            "v1_knock_in_time": _default_value("—"),
            "v2_recovery": {"done": "—", "total": "—"},
        },
    }


def _normalize_volatility_section(section: dict[str, Any] | None, symbol: str) -> dict[str, Any]:
    base = _default_volatility_section(symbol)
    if section is None:
        return base
    values = dict(base["values"])
    values.update(section.get("values", {}))
    return {
        "symbol": section.get("symbol", symbol),
        "v_level": section.get("v_level", "—"),
        "values": values,
    }


def build_fixed_v_sections(
    fc: "FlightController",
    bundle: "SignalBundle",
    vol_symbols: list[str],
    *,
    altitude: "AltitudeRegime",
) -> dict[str, dict[str, Any]]:
    by_symbol = {s["symbol"]: s for s in build_v_sections(fc, bundle, vol_symbols, altitude=altitude)}
    return {
        "nq": _normalize_volatility_section(by_symbol.get("NQ"), "NQ"),
        "gc": _normalize_volatility_section(by_symbol.get("GC"), "GC"),
    }
