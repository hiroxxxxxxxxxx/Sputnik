from __future__ import annotations

from avionics.factors.c_factor import c_breakdown_hit_row_keys_from_snapshot

_DC2 = -0.025


def test_c_breakdown_hit_keys_below_sma_only() -> None:
    assert c_breakdown_hit_row_keys_from_snapshot(True, 0.01, _DC2) == frozenset({"sma20_gap"})


def test_c_breakdown_hit_keys_daily_only() -> None:
    assert c_breakdown_hit_row_keys_from_snapshot(False, -0.03, _DC2) == frozenset({"daily_change"})


def test_c_breakdown_hit_keys_both_axes() -> None:
    assert c_breakdown_hit_row_keys_from_snapshot(True, -0.03, _DC2) == frozenset({"sma20_gap", "daily_change"})


def test_c_breakdown_hit_keys_neither_c2_snapshot() -> None:
    assert c_breakdown_hit_row_keys_from_snapshot(False, 0.0, _DC2) == frozenset()
    assert c_breakdown_hit_row_keys_from_snapshot(False, None, _DC2) == frozenset()
