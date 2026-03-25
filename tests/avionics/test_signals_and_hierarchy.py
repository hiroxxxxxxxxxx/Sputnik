"""
Layer 1 / Layer 2 / SignalBundle と FC.apply_all(signal_bundle) のテスト。

定義書 4-2 情報の階層構造に基づく分離の動作を検証する。
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest

from avionics import PFactor, SFactor, TFactor, UFactor, VFactor
from avionics.factors import (
    FactorsConfigError,
    get_p_thresholds,
    get_v_thresholds,
    load_factors_config,
)
from avionics.data.raw_types import PriceBar, RawCapitalSnapshot
from avionics.data.raw_market_snapshot import RawMarketSnapshot
from avionics.data.signals import (
    CapitalSignals,
    PriceSignals,
    SignalBundle,
    VolatilitySignal,
)
from avionics.compute import (
    _settlement_bar_indices_from_date,
    compute_capital_signals_from_cap,
    compute_price_signals_from_snapshot,
)

try:
    _config = load_factors_config()
except FactorsConfigError:
    pytest.skip("config/factors.toml required", allow_module_level=True)


def _run(coro):
    return asyncio.run(coro)


def test_compute_price_signals_insufficient_bars_raises() -> None:
    """価格系列が不足しているときは ValueError を送出する。"""
    snapshot = RawMarketSnapshot(as_of=date(2025, 3, 1))
    with pytest.raises(ValueError, match="requires >= 2 bars"):
        compute_price_signals_from_snapshot(snapshot, "NQ", date(2025, 3, 1))


def test_compute_price_signals_from_series() -> None:
    """十分な本数の価格系列から trend, daily_change, cum5, downside_gap を算出する。"""
    base = date(2025, 2, 1)
    bars = [
        PriceBar(date=base + timedelta(days=i), close=100.0 + i * 0.5, high=101.0 + i, volume=1000)
        for i in range(22)
    ]
    bars[-1] = PriceBar(date=bars[-1].date, close=102.0, high=120.0, volume=1000)
    bars[-2] = PriceBar(date=bars[-2].date, close=101.0, high=119.0, volume=1000)
    snapshot = RawMarketSnapshot(as_of=bars[-1].date, nq_price_bars=bars)
    out = compute_price_signals_from_snapshot(snapshot, "NQ", bars[-1].date)
    assert out.symbol == "NQ"
    assert out.daily_change == pytest.approx((102.0 - 101.0) / 101.0)
    assert out.downside_gap != 0.0


def test_compute_price_signals_settlement_uses_as_of() -> None:
    """as_of の日付でバーを検索し、その足と1本前で daily_change を算出する。"""
    base = date(2025, 2, 1)
    bars = [
        PriceBar(date=base + timedelta(days=i), close=100.0 + i, high=101.0 + i, volume=1000)
        for i in range(25)
    ]
    bars[-3] = PriceBar(date=bars[-3].date, close=98.0, high=99.0, volume=1000)
    bars[-2] = PriceBar(date=bars[-2].date, close=99.0, high=100.0, volume=1000)
    bars[-1] = PriceBar(date=bars[-1].date, close=100.0, high=101.0, volume=1000)
    snapshot = RawMarketSnapshot(as_of=bars[-2].date, nq_price_bars=bars)
    out = compute_price_signals_from_snapshot(snapshot, "NQ", as_of=bars[-2].date)
    assert out.daily_change == pytest.approx((99.0 - 98.0) / 98.0)
    assert out.last_close == 99.0


def test_settlement_bar_indices_finds_ref_date() -> None:
    """ref_date と一致するバーがあればそのインデックスと1本前を返す。"""
    base = date(2025, 2, 1)
    bars = [
        PriceBar(date=base + timedelta(days=i), close=100.0 + i, high=101.0, volume=1000)
        for i in range(10)
    ]
    ref = base + timedelta(days=4)
    latest_idx, prev_idx = _settlement_bar_indices_from_date(bars, ref)
    assert latest_idx == 4
    assert prev_idx == 3


def test_settlement_bar_indices_not_found_uses_last_two() -> None:
    """ref_date がリストに無い場合は (-1, -2)。"""
    base = date(2025, 2, 1)
    bars = [
        PriceBar(date=base + timedelta(days=i), close=100.0, high=101.0, volume=1000)
        for i in range(5)
    ]
    latest_idx, prev_idx = _settlement_bar_indices_from_date(bars, date(2025, 3, 1))
    assert (latest_idx, prev_idx) == (-1, -2)


def test_compute_capital_signals() -> None:
    """証拠金スナップショットから mm_over_nlv と span_ratio を算出する。"""
    cap = RawCapitalSnapshot(
        as_of=date(2025, 3, 1),
        mm=40.0,
        nlv=100.0,
        base_density=1.0,
        current_value=200.0,
        futures_multiplier=1.0,
    )
    out = compute_capital_signals_from_cap(cap)
    assert out.mm_over_nlv == 0.4
    assert out.span_ratio == pytest.approx(0.2)


def test_compute_capital_signals_none_raises() -> None:
    """スナップショットが None のときは ValueError を送出する。"""
    with pytest.raises(ValueError, match="RawCapitalSnapshot is required"):
        compute_capital_signals_from_cap(None)


def test_signal_bundle_apply_all_distributes_to_factors() -> None:
    """apply_all(signal_bundle) で P/V/T にシグナルが配布され、レベルが更新される。"""
    from avionics import FlightController
    from avionics.factors import get_t_thresholds

    p = PFactor(name="P_NQ", thresholds=get_p_thresholds(_config, "NQ"))
    v = VFactor(name="V_NQ", thresholds=get_v_thresholds(_config, "NQ"))
    t = TFactor(symbol="NQ", thresholds=get_t_thresholds(_config))

    av = FlightController(
        global_market_factors=[],
        global_capital_factors=[],
        symbol_factors={"NQ": [p, v, t]},
    )

    price = PriceSignals(
        symbol="NQ",
        trend="down",
        daily_change=-0.04,
        cum5_change=-0.05,
        cum2_change=-0.06,
        downside_gap=-0.06,
    )
    vol = VolatilitySignal(index_value=35.0, altitude="mid")
    bundle = SignalBundle(
        price_signals={"NQ": price},
        volatility_signals={"NQ": vol},
    )

    _run(av.apply_all(bundle))

    assert p.level == 2
    assert t.level == 2
    assert v.level >= 1


def test_signal_bundle_apply_all_capital_factors() -> None:
    """apply_all(signal_bundle) で U/S に capital_signals が配布される。"""
    from avionics import FlightController
    from avionics.factors import get_s_thresholds, get_u_thresholds

    u_th = get_u_thresholds(_config)
    s_th = get_s_thresholds(_config)
    u = UFactor(thresholds=u_th)
    s = SFactor(thresholds=s_th)
    av = FlightController(
        global_market_factors=[],
        global_capital_factors=[u, s],
        symbol_factors={},
    )
    cap = CapitalSignals(mm_over_nlv=0.50, span_ratio=1.25)
    bundle = SignalBundle(capital_signals=cap)

    _run(av.apply_all(bundle))

    assert u.level == 2
    assert s.level >= 1
