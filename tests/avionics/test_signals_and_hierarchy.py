"""
Layer 1 / Layer 2 / SignalBundle と Cockpit.update_all(signal_bundle) のテスト。

定義書 4-2 情報の階層構造に基づく分離の動作を検証する。
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

import pytest

from avionics import PFactor, SFactor, TFactor, UFactor, VFactor
from avionics.factors_config import (
    FactorsConfigError,
    get_p_thresholds,
    get_v_thresholds,
    load_factors_config,
)
from avionics.Instruments.raw_data import PriceBar, PriceBar1h, RawCapitalSnapshot, RawDataProvider
from avionics.Instruments.signals import (
    CapitalSignals,
    LiquiditySignals,
    PriceSignals,
    SignalBundle,
    VolatilitySignal,
    compute_capital_signals,
    compute_price_signals,
)

try:
    _config = load_factors_config()
except FactorsConfigError:
    pytest.skip("config/factors.toml required", allow_module_level=True)


def _run(coro):
    return asyncio.run(coro)


class _MockRawProvider:
    """テスト用 RawDataProvider。価格系列と証拠金スナップショットを返す。"""

    def __init__(
        self,
        bars: list[PriceBar] | None = None,
        capital: RawCapitalSnapshot | None = None,
        volatility: float | None = None,
    ) -> None:
        self.bars = bars or []
        self.capital = capital
        self.volatility = volatility or 0.0

    def get_price_series(self, symbol: str, limit: int) -> list[PriceBar]:
        return self.bars[-limit:] if self.bars else []

    def get_price_series_1h(self, symbol: str, limit: int) -> list[PriceBar1h]:
        return []

    def get_volatility_series(self, symbol: str, limit: int) -> list:
        return []

    def get_volatility_index(self, symbol: str, as_of: date) -> float | None:
        return self.volatility

    def get_capital_snapshot(self, as_of: date) -> RawCapitalSnapshot | None:
        return self.capital

    def get_credit_series(self, symbol: str, limit: int) -> list[PriceBar]:
        return self.bars[-limit:] if self.bars else []

    def get_tip_series(self, limit: int) -> list[PriceBar]:
        return self.bars[-limit:] if self.bars else []


def test_compute_price_signals_insufficient_bars_returns_safe_defaults() -> None:
    """価格系列が不足しているときは安全なデフォルトの PriceSignals を返す。"""
    provider = _MockRawProvider(bars=[])
    out = compute_price_signals(provider, "NQ", date(2025, 3, 1))
    assert out.symbol == "NQ"
    assert out.trend == "up"
    assert out.daily_change == 0.0
    assert out.cum5_change == 0.0
    assert out.downside_gap == -0.01


def test_compute_price_signals_from_series() -> None:
    """十分な本数の価格系列から trend, daily_change, cum5, downside_gap を算出する。"""
    base = date(2025, 2, 1)
    # 20本の過去 + 直近2本で SMA20, daily_change が計算できる
    bars = [
        PriceBar(date=base + timedelta(days=i), close=100.0 + i * 0.5, high=101.0 + i, volume=1000)
        for i in range(22)
    ]
    bars[-1] = PriceBar(
        date=bars[-1].date,
        close=102.0,
        high=120.0,
        volume=1000,
    )
    bars[-2] = PriceBar(
        date=bars[-2].date,
        close=101.0,
        high=119.0,
        volume=1000,
    )
    provider = _MockRawProvider(bars=bars)
    out = compute_price_signals(provider, "NQ", bars[-1].date)
    assert out.symbol == "NQ"
    assert out.daily_change == pytest.approx((102.0 - 101.0) / 101.0)
    assert out.downside_gap != 0.0


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
    provider = _MockRawProvider(capital=cap)
    out = compute_capital_signals(provider, date(2025, 3, 1))
    assert out.mm_over_nlv == 0.4
    assert out.span_ratio == pytest.approx(0.2)  # current_density = 40/200 = 0.2, base=1.0


def test_compute_capital_signals_none_returns_defaults() -> None:
    """スナップショットが None のときは安全なデフォルトを返す。"""
    provider = _MockRawProvider()
    out = compute_capital_signals(provider, date(2025, 3, 1))
    assert out.mm_over_nlv == 0.0
    assert out.span_ratio == 1.0


def test_signal_bundle_update_all_distributes_to_factors() -> None:
    """update_all(signal_bundle) で P/V/T にシグナルが配布され、レベルが更新される。"""
    from avionics import Cockpit
    from avionics.factors_config import get_t_thresholds

    p = PFactor(name="P_NQ", thresholds=get_p_thresholds(_config, "NQ"))
    v = VFactor(name="V_NQ", thresholds=get_v_thresholds(_config, "NQ"))
    t = TFactor(symbol="NQ", thresholds=get_t_thresholds(_config))

    av = Cockpit(
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
    vol = VolatilitySignal(index_value=35.0, altitude="high_mid")
    bundle = SignalBundle(
        price_signals={"NQ": price},
        volatility_signals={"NQ": vol},
    )

    _run(av.update_all(signal_bundle=bundle))

    assert p.level == 2
    assert t.level == 2
    assert v.level >= 1


def test_signal_bundle_update_all_capital_factors() -> None:
    """update_all(signal_bundle) で U/S に capital_signals が配布される。"""
    from avionics import Cockpit
    from avionics.factors_config import get_s_thresholds, get_u_thresholds

    u_th = get_u_thresholds(_config)
    s_th = get_s_thresholds(_config)
    u = UFactor(thresholds=u_th)
    s = SFactor(thresholds=s_th)
    av = Cockpit(
        global_market_factors=[],
        global_capital_factors=[u, s],
        symbol_factors={},
    )
    cap = CapitalSignals(mm_over_nlv=0.50, span_ratio=1.25)
    bundle = SignalBundle(capital_signals=cap)

    _run(av.update_all(signal_bundle=bundle))

    assert u.level == 2
    assert s.level >= 1


