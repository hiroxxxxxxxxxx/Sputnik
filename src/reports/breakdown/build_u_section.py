from __future__ import annotations

from typing import TYPE_CHECKING, Any

from reports.breakdown.common import breakdown_level_suffix

if TYPE_CHECKING:
    from avionics import FlightController
    from avionics.data.signals import SignalBundle


def _limit_factor(fc: "FlightController", cls: type) -> Any:
    for f in fc.mapping.limit_factors:
        if isinstance(f, cls):
            return f
    return None


def build_u_section(fc: "FlightController", bundle: "SignalBundle") -> dict[str, Any] | None:
    from avionics.factors.u_factor import UFactor

    if not bundle.capital_signals:
        return None
    cs = bundle.capital_signals
    cap_snapshot = fc.get_last_capital_snapshot()
    mm = getattr(cap_snapshot, "mm", None)
    nlv = getattr(cap_snapshot, "nlv", None)
    excess_liq = (float(nlv) - float(mm)) if mm is not None and nlv is not None else None
    return {
        "u_level": breakdown_level_suffix(_limit_factor(fc, UFactor)),
        "u_ratio": f"{cs.mm_over_nlv:.2f} ({cs.mm_over_nlv * 100:.2f}%)",
        "mm": "N/A" if mm is None else f"{float(mm):,.2f}",
        "nlv": "N/A" if nlv is None else f"{float(nlv):,.2f}",
        "excess_liq": "N/A" if excess_liq is None else f"{float(excess_liq):,.2f}",
    }


def _default_u_section() -> dict[str, Any]:
    return {"u_level": "—", "u_ratio": "N/A", "mm": "N/A", "nlv": "N/A", "excess_liq": "N/A"}


def build_fixed_u_section(fc: "FlightController", bundle: "SignalBundle") -> dict[str, Any]:
    return build_u_section(fc, bundle) or _default_u_section()
