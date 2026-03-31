from __future__ import annotations

from datetime import date

from avionics.compute import compute_capital_signals_from_cap
from avionics.data.raw_types import RawCapitalSnapshot


def test_compute_capital_signals_uses_s_whatif_ratio_when_present() -> None:
    cap = RawCapitalSnapshot(
        as_of=date(2026, 3, 31),
        mm=100_000.0,
        nlv=1_000_000.0,
        base_density=2.0,
        current_value=1_000_000.0,
        futures_multiplier=1.0,
        s_whatif_mm_per_lot={"NQ": 1200.0, "GC": 600.0},
        s_baseline_mm_per_lot={"NQ": 1000.0, "GC": 500.0},
    )
    out = compute_capital_signals_from_cap(cap)
    assert out.mm_over_nlv == 0.1
    assert round(out.span_ratio, 4) == 1.2


def test_compute_capital_signals_keeps_density_ratio_when_s_baseline_missing_whatif_symbol() -> None:
    cap = RawCapitalSnapshot(
        as_of=date(2026, 3, 31),
        mm=100_000.0,
        nlv=1_000_000.0,
        base_density=1.0,
        current_value=1_000_000.0,
        futures_multiplier=1.0,
        s_whatif_mm_per_lot={"NQ": 1200.0},
        s_baseline_mm_per_lot={"NQ": 1000.0, "GC": 500.0},
    )
    out = compute_capital_signals_from_cap(cap)
    assert out.mm_over_nlv == 0.1
    assert round(out.span_ratio, 4) == 0.1


def test_compute_capital_signals_allows_missing_whatif_when_baseline_present() -> None:
    cap = RawCapitalSnapshot(
        as_of=date(2026, 3, 31),
        mm=100_000.0,
        nlv=1_000_000.0,
        base_density=2.0,
        current_value=1_000_000.0,
        futures_multiplier=1.0,
        s_whatif_mm_per_lot=None,
        s_baseline_mm_per_lot={"NQ": 1000.0, "GC": 500.0},
    )
    out = compute_capital_signals_from_cap(cap)
    assert out.mm_over_nlv == 0.1
    assert round(out.span_ratio, 4) == 0.05


def test_compute_capital_signals_propagates_whatif_errors() -> None:
    cap = RawCapitalSnapshot(
        as_of=date(2026, 3, 31),
        mm=100_000.0,
        nlv=1_000_000.0,
        base_density=1.0,
        current_value=1_000_000.0,
        futures_multiplier=1.0,
        s_whatif_mm_per_lot={"NQ": 1200.0},
        s_baseline_mm_per_lot={"NQ": 1000.0, "GC": 500.0},
        s_whatif_errors={"GC": "ValueError: No Trading Permission"},
    )
    out = compute_capital_signals_from_cap(cap)
    assert out.s_whatif_errors == {"GC": "ValueError: No Trading Permission"}
