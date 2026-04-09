from __future__ import annotations

from reports.breakdown.breakdown_r_hits import r_breakdown_hit_row_keys


def test_r_breakdown_hit_row_keys_r2() -> None:
    assert r_breakdown_hit_row_keys(2) == frozenset({"tip_drawdown"})


def test_r_breakdown_hit_row_keys_not_r2() -> None:
    assert r_breakdown_hit_row_keys(1) == frozenset()
    assert r_breakdown_hit_row_keys(0) == frozenset()
