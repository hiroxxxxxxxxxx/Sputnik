from __future__ import annotations

from cockpit.mode import CRUISE
from reports.position_report_context import build_position_report_context


def test_build_position_report_context_contains_strategy_and_unclassified_detail() -> None:
    positions_detail = {
        "NQ": {
            "futures": {
                "nq_buy": 2.0,
                "nq_sell": 1.0,
                "mnq_buy": 10.0,
                "mnq_sell": 2.0,
                "gc_buy": 0.0,
                "gc_sell": 0.0,
                "mgc_buy": 0.0,
                "mgc_sell": 0.0,
            },
            "options": {
                "nq_call_buy": 1.0,
                "nq_call_sell": 3.0,
                "nq_put_buy": 0.0,
                "nq_put_sell": 2.0,
                "mnq_call_buy": 0.0,
                "mnq_call_sell": 0.0,
                "mnq_put_buy": 0.0,
                "mnq_put_sell": 0.0,
                "gc_call_buy": 0.0,
                "gc_call_sell": 0.0,
                "gc_put_buy": 0.0,
                "gc_put_sell": 0.0,
                "mgc_call_buy": 0.0,
                "mgc_call_sell": 0.0,
                "mgc_put_buy": 0.0,
                "mgc_put_sell": 0.0,
            },
        }
    }
    out = build_position_report_context(
        ["NQ"],
        positions_detail=positions_detail,
        target_base_by_symbol={"NQ": 10.0, "GC": 10.0},
        modes_by_symbol={"NQ": CRUISE},
        altitude="mid",
    )
    assert out["futures_target_rows"][0]["target"] == "15"
    cc = [r for r in out["options_rows"] if r["strategy"] == "CC"][0]
    assert cc["actual"] == "2"


def test_build_position_report_context_unclassified_detail_breakdown() -> None:
    positions_detail = {
        "NQ": {
            "futures": {
                "nq_buy": 0.0,
                "nq_sell": 0.0,
                "mnq_buy": 0.0,
                "mnq_sell": 0.0,
                "gc_buy": 0.0,
                "gc_sell": 0.0,
                "mgc_buy": 0.0,
                "mgc_sell": 0.0,
            },
            "options": {
                "nq_call_buy": 3.0,
                "nq_call_sell": 0.0,
                "nq_put_buy": 0.0,
                "nq_put_sell": 0.0,
                "mnq_call_buy": 0.0,
                "mnq_call_sell": 0.0,
                "mnq_put_buy": 0.0,
                "mnq_put_sell": 0.0,
                "gc_call_buy": 0.0,
                "gc_call_sell": 0.0,
                "gc_put_buy": 0.0,
                "gc_put_sell": 0.0,
                "mgc_call_buy": 0.0,
                "mgc_call_sell": 0.0,
                "mgc_put_buy": 0.0,
                "mgc_put_sell": 0.0,
            },
        }
    }
    out = build_position_report_context(
        ["NQ"],
        positions_detail=positions_detail,
        target_base_by_symbol={"NQ": 10.0, "GC": 10.0},
        modes_by_symbol={"NQ": CRUISE},
        altitude="mid",
    )
    unc = [r for r in out["options_rows"] if r["strategy"] == "UNCLASSIFIED"][0]
    assert unc["actual"] == "3"
    assert unc["unclassified_detail"] == "P B=0 S=0 | C B=3 S=0"
