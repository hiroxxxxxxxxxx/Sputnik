"""futures_micro_equiv の換算。"""
from __future__ import annotations

import pytest

from avionics.data.futures_micro_equiv import (
    MICRO_CONTRACTS_PER_MINI_FUTURES,
    engine_symbol_to_micro_notional_label,
    micro_equivalent_net_gc_family,
    micro_equivalent_net_nq_family,
    signed_future_root_qty_to_micro_equivalent,
)


def test_engine_symbol_to_micro_notional_label() -> None:
    assert engine_symbol_to_micro_notional_label("NQ") == "MNQ"
    assert engine_symbol_to_micro_notional_label("gc") == "MGC"


def test_engine_symbol_to_micro_notional_label_bad_raises() -> None:
    with pytest.raises(ValueError, match="NQ or GC"):
        engine_symbol_to_micro_notional_label("MES")


def test_signed_future_root_qty_to_micro_equivalent() -> None:
    assert signed_future_root_qty_to_micro_equivalent("NQ", 1.0) == 10.0
    assert signed_future_root_qty_to_micro_equivalent("nq", -2.0) == -20.0
    assert signed_future_root_qty_to_micro_equivalent("MNQ", 3.0) == 3.0
    assert signed_future_root_qty_to_micro_equivalent("GC", 1.0) == 10.0
    assert signed_future_root_qty_to_micro_equivalent("MGC", -1.0) == -1.0


def test_signed_future_unknown_root_raises() -> None:
    with pytest.raises(ValueError, match="unsupported futures root"):
        signed_future_root_qty_to_micro_equivalent("MES", 1.0)


def test_micro_equivalent_net_nq_family() -> None:
    assert (
        micro_equivalent_net_nq_family(
            {
                "nq_buy": 2.0,
                "nq_sell": 1.0,
                "mnq_buy": 5.0,
                "mnq_sell": 3.0,
            }
        )
        == MICRO_CONTRACTS_PER_MINI_FUTURES * (2.0 - 1.0) + (5.0 - 3.0)
    )


def test_micro_equivalent_net_gc_family() -> None:
    assert micro_equivalent_net_gc_family(
        {
            "gc_buy": 1.0,
            "gc_sell": 0.0,
            "mgc_buy": 0.0,
            "mgc_sell": 2.0,
        }
    ) == MICRO_CONTRACTS_PER_MINI_FUTURES * 1.0 - 2.0
