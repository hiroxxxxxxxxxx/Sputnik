from __future__ import annotations

from reports.breakdown_p_hits import p_breakdown_hit_row_keys


def test_p_breakdown_hit_row_keys_p0_calm_no_row_marks() -> None:
    """P0（Calm）は入力行への ★ を付けない。"""
    assert p_breakdown_hit_row_keys("P0_calm") == frozenset()


def test_p_breakdown_hit_row_keys_p1_default_no_row_marks() -> None:
    assert p_breakdown_hit_row_keys("P1_default") == frozenset()


def test_p_breakdown_hit_row_keys_p2_reasons_unchanged() -> None:
    assert p_breakdown_hit_row_keys("P2_daily") == frozenset({"daily_change"})
    assert p_breakdown_hit_row_keys("P2_cum2") == frozenset({"cum2_change"})
    assert p_breakdown_hit_row_keys("P2_gap_down") == frozenset({"high_20_gap", "trend"})
