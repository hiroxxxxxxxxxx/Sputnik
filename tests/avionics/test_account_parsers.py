from __future__ import annotations

from avionics.account_parsers import (
    build_engine_part_on_off_state,
    build_engine_actual_state,
    build_option_strategy_state_from_option_detail,
    resolve_attached_strategy_name,
)


def test_build_engine_actual_state_splits_by_target_weight() -> None:
    actual = {"future": 9.0, "k1": 3.0, "k2": -3.0}
    targets = {"Main": 2.0, "Attitude": 1.0, "Booster": 0.0}
    out = build_engine_actual_state(actual, targets)
    assert out["Main"]["future"] == 6.0
    assert out["Attitude"]["future"] == 3.0
    assert out["Booster"]["future"] == 0.0


def test_build_option_strategy_state_exposes_unclassified_detail() -> None:
    option_detail = {
        "nq_call_buy": 3.0,
        "nq_call_sell": 0.0,
        "nq_put_buy": 0.0,
        "nq_put_sell": 0.0,
        "mnq_call_buy": 0.0,
        "mnq_call_sell": 0.0,
        "mnq_put_buy": 0.0,
        "mnq_put_sell": 0.0,
    }
    out = build_option_strategy_state_from_option_detail(option_detail, family="NQ")
    unc = out["UNCLASSIFIED"]
    assert unc.qty == 3.0
    assert unc.attached is True
    assert unc.unclassified_detail is not None
    assert unc.unclassified_detail.call_buy == 3.0


def test_build_engine_part_on_off_state_uses_actual_allocation() -> None:
    symbol_actual = {"future": 0.0, "k1": 0.0, "k2": 0.0}
    targets = {"Main": 2.0, "Attitude": 1.0, "Booster": 0.0}
    out = build_engine_part_on_off_state(symbol_actual, targets)
    assert out["Main"] is False
    assert out["Attitude"] is False
    assert out["Booster"] is False


def test_resolve_attached_strategy_name_single_or_none() -> None:
    option_detail = {
        "nq_call_buy": 0.0,
        "nq_call_sell": 1.0,
        "nq_put_buy": 0.0,
        "nq_put_sell": 0.0,
        "mnq_call_buy": 0.0,
        "mnq_call_sell": 0.0,
        "mnq_put_buy": 0.0,
        "mnq_put_sell": 0.0,
    }
    states = build_option_strategy_state_from_option_detail(option_detail, family="NQ")
    assert resolve_attached_strategy_name(states) == "CC"

    empty_states = build_option_strategy_state_from_option_detail(
        {
            "nq_call_buy": 0.0,
            "nq_call_sell": 0.0,
            "nq_put_buy": 0.0,
            "nq_put_sell": 0.0,
            "mnq_call_buy": 0.0,
            "mnq_call_sell": 0.0,
            "mnq_put_buy": 0.0,
            "mnq_put_sell": 0.0,
        },
        family="NQ",
    )
    assert resolve_attached_strategy_name(empty_states) == "NONE"


def test_resolve_attached_strategy_name_multiple_raises() -> None:
    states = build_option_strategy_state_from_option_detail(
        {
            "nq_call_buy": 0.0,
            "nq_call_sell": 1.0,
            "nq_put_buy": 2.0,
            "nq_put_sell": 2.0,
            "mnq_call_buy": 0.0,
            "mnq_call_sell": 0.0,
            "mnq_put_buy": 0.0,
            "mnq_put_sell": 0.0,
        },
        family="NQ",
    )
    try:
        resolve_attached_strategy_name(states)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "multiple option strategies attached" in str(e)
