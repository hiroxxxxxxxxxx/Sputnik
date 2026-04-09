from __future__ import annotations

from types import SimpleNamespace

from reports.breakdown.breakdown_v_hits import v_breakdown_hit_row_keys


def test_v_breakdown_hit_row_keys_index_only() -> None:
    vs = SimpleNamespace(index_value=25.0, recovery_confirm_satisfied_days_v1_off=0)
    th = {"V2_on": 30.0, "V1_on": 20.0}
    assert v_breakdown_hit_row_keys(vs, th, 0, 2) == {"index_value"}


def test_v_breakdown_hit_row_keys_v2_includes_recovery() -> None:
    vs = SimpleNamespace(index_value=15.0, recovery_confirm_satisfied_days_v1_off=0)
    th = {"V2_on": 30.0, "V1_on": 20.0}
    assert v_breakdown_hit_row_keys(vs, th, 2, 3) == {"v2_recovery"}


def test_v_breakdown_hit_row_keys_v1_knock_in() -> None:
    vs = SimpleNamespace(index_value=15.0, recovery_confirm_satisfied_days_v1_off=3)
    th = {"V2_on": 30.0, "V1_on": 20.0}
    assert v_breakdown_hit_row_keys(vs, th, 1, 2) == {"v1_recovery", "v1_knock_in"}
