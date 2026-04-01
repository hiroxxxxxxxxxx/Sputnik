"""
FC.refresh(DataSource) と get_last_bundle のテスト。

実 IB 接続は行わず、モック DataSource で refresh → get_last_bundle の組み立てを検証する。
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Dict, List, Optional, Tuple

import pytest

from avionics.data.factor_mapping import EngineFactorMapping
from avionics.data.raw_types import PriceBar, RawCapitalSnapshot
from avionics.data.raw_market_snapshot import RawMarketSnapshot
from avionics.bundle_builder import BundleBuildOptions
from avionics.flight_controller import FlightController
from avionics.ib.market_client import bar_to_price_bar
from avionics.ib.fetcher import IBRawFetcher


def _run(coro):
    return asyncio.run(coro)


# --- bar_to_price_bar ---


def test_bar_to_price_bar_from_date() -> None:
    """BarData の date が date のとき PriceBar に変換する。"""
    bar = _mock_bar(date(2025, 3, 1), 100.5, 101.0, 1000.0)
    out = bar_to_price_bar(bar)
    assert out.date == date(2025, 3, 1)
    assert out.close == 100.5
    assert out.high == 101.0
    assert out.volume == 1000.0


def test_bar_to_price_bar_from_datetime() -> None:
    """BarData の date が datetime のとき .date() で date に変換する。"""
    from datetime import datetime, timezone
    bar = _mock_bar(datetime(2025, 3, 1, 16, 0, 0, tzinfo=timezone.utc), 99.0, 100.0, 500.0)
    out = bar_to_price_bar(bar)
    assert out.date == date(2025, 3, 1)
    assert out.close == 99.0


def _mock_bar(d, close: float, high: float, volume: float):
    from unittest.mock import MagicMock
    bar = MagicMock()
    bar.date = d
    bar.close = close
    bar.high = high
    bar.volume = volume
    return bar


# --- Mock DataSource + FC.refresh → get_last_bundle ---


class MockDataSource:
    """テスト用: RawMarketSnapshot を返す DataSource。"""

    def __init__(
        self,
        snapshot: RawMarketSnapshot,
        capital_snapshot: Optional[RawCapitalSnapshot] = None,
    ) -> None:
        self._snapshot = snapshot
        self._capital_snapshot = capital_snapshot

    async def fetch_raw(
        self,
        as_of: date,
        price_symbols: List[str],
        *,
        volatility_symbols: Optional[Dict[str, str]] = None,
        liquidity_credit_hyg_symbol: str,
        liquidity_credit_lqd_symbol: str,
        liquidity_tip_symbol: Optional[str] = None,
        account: str = "",
        base_density: float = 1.0,
        s_baseline_by_symbol: Optional[Dict[str, float]] = None,
        v_recovery_params: Optional[Dict[str, dict]] = None,
    ) -> Tuple[RawMarketSnapshot, Optional[RawCapitalSnapshot]]:
        return (self._snapshot, self._capital_snapshot)


def _make_fc(symbols: List[str], options: Optional[BundleBuildOptions] = None) -> FlightController:
    """因子なしの FC（refresh で bundle だけ組み立てる用）。"""
    mapping = EngineFactorMapping(
        symbol_factors={s: [] for s in symbols},
        limit_factors=[],
        global_market_factors=[],
    )
    return FlightController(
        mapping=mapping,
        bundle_build_options=options or BundleBuildOptions(
            liquidity_credit_hyg_symbol="HYG",
            liquidity_credit_lqd_symbol="LQD",
            altitude="mid",
        ),
    )


def test_fc_refresh_returns_bundle_with_price_and_capital() -> None:
    """fc.refresh(mock_ds) のあと get_last_bundle() で price_signals / capital_signals が入る。"""
    bars = [
        PriceBar(date=date(2025, 2, 28), close=100.0, high=101.0, volume=1000.0),
        PriceBar(date=date(2025, 3, 1), close=101.0, high=102.0, volume=1100.0),
    ]
    cap = RawCapitalSnapshot(
        as_of=date(2025, 3, 1),
        mm=80_000.0,
        nlv=1_000_000.0,
        base_density=1.0,
        current_value=1_000_000.0,
        futures_multiplier=1.0,
    )
    snapshot = RawMarketSnapshot(
        as_of=date(2025, 3, 1),
        nq_price_bars=bars,
        nq_volatility_series=[(date(2025, 3, 1), 18.5)],
        capital_snapshot=cap,
        credit_bars={
            "HYG": bars,
            "LQD": [
                PriceBar(date=date(2025, 2, 28), close=99.0, high=100.0, volume=900.0),
                PriceBar(date=date(2025, 3, 1), close=99.5, high=100.5, volume=950.0),
            ],
        },
    )
    ds = MockDataSource(snapshot, capital_snapshot=cap)
    fc = _make_fc(["NQ"], options=BundleBuildOptions(
        liquidity_credit_hyg_symbol="HYG",
        liquidity_credit_lqd_symbol="LQD",
        liquidity_tip_symbol=None,
        altitude="mid",
    ))
    _run(fc.refresh(ds, date(2025, 3, 1), ["NQ"], altitude="mid"))
    bundle = fc.get_last_bundle()
    assert bundle is not None
    assert bundle.price_signals.get("NQ") is not None
    assert bundle.price_signals["NQ"].symbol == "NQ"
    assert bundle.volatility_signals.get("NQ") is not None
    assert bundle.capital_signals is not None
    assert bundle.capital_signals.mm_over_nlv > 0
    assert bundle.liquidity_credit_hyg is not None
    assert bundle.liquidity_credit_lqd is not None
    assert bundle.liquidity_tip is None
    assert fc.get_last_capital_snapshot() is cap


def test_fc_refresh_with_liquidity_options() -> None:
    """liquidity_credit_hyg_symbol / liquidity_tip_symbol 指定で C/R 用シグナルが bundle に入る。"""
    cap = RawCapitalSnapshot(
        as_of=date(2025, 3, 1),
        mm=80_000.0,
        nlv=1_000_000.0,
        base_density=1.0,
        current_value=1_000_000.0,
        futures_multiplier=1.0,
    )
    tip_bars = [
        PriceBar(date=date(2025, 2, i), close=105.0, high=106.0, volume=2000.0)
        for i in range(1, 4)
    ]
    snapshot = RawMarketSnapshot(
        as_of=date(2025, 3, 1),
        nq_price_bars=[
            PriceBar(date=date(2025, 2, 28), close=100.0, high=101.0, volume=1000.0),
            PriceBar(date=date(2025, 3, 1), close=101.0, high=102.0, volume=1100.0),
        ],
        nq_volatility_series=[(date(2025, 3, 1), 18.5)],
        capital_snapshot=cap,
        tip_bars=tip_bars,
        credit_bars={
            "HYG": [
                PriceBar(date=date(2025, 2, 28), close=100.0, high=101.0, volume=1000.0),
                PriceBar(date=date(2025, 3, 1), close=101.0, high=102.0, volume=1100.0),
            ],
            "LQD": [
                PriceBar(date=date(2025, 2, 28), close=99.0, high=100.0, volume=900.0),
                PriceBar(date=date(2025, 3, 1), close=99.5, high=100.5, volume=950.0),
            ],
        },
    )
    ds = MockDataSource(snapshot, capital_snapshot=cap)
    options = BundleBuildOptions(
        liquidity_credit_hyg_symbol="HYG",
        liquidity_credit_lqd_symbol="LQD",
        liquidity_tip_symbol="TIP",
        altitude="mid",
    )
    fc = _make_fc(["NQ"], options=options)
    _run(fc.refresh(ds, date(2025, 3, 1), ["NQ"], altitude="mid"))
    bundle = fc.get_last_bundle()
    assert bundle is not None
    assert bundle.liquidity_credit_hyg is not None
    assert bundle.liquidity_tip is not None


def test_fetch_s_whatif_collects_error_for_none_qualified_contract() -> None:
    """qualifyContractsAsync が [None] のとき、当該銘柄にエラー理由を記録する。"""
    pytest.importorskip("ib_async")

    class _FakeIb:
        async def qualifyContractsAsync(self, _contract):
            return [None]

        async def whatIfOrderAsync(self, _contract, _order):
            raise AssertionError("whatIfOrderAsync must not be called when contract is None")

    fetcher = IBRawFetcher(_FakeIb())
    values, errors = asyncio.run(fetcher._fetch_s_whatif_mm_per_lot(["NQ"]))
    assert values == {}
    assert "NQ" in errors
    assert "contract is None" in errors["NQ"]


def test_fetch_account_summary_continues_when_whatif_fails() -> None:
    """whatIf 失敗時も capital snapshot 自体は返す（S whatIf は None）。"""

    class _FakeAv:
        def __init__(self, tag: str, value: str) -> None:
            self.tag = tag
            self.value = value

    class _Fetcher(IBRawFetcher):
        async def _fetch_s_whatif_mm_per_lot(self, symbols):  # type: ignore[override]
            raise ValueError(f"boom: {symbols}")

    class _FakeIb:
        async def accountSummaryAsync(self, _account):
            return [
                _FakeAv("NetLiquidation", "1000000"),
                _FakeAv("MaintMarginReq", "80000"),
                _FakeAv("GrossPositionValue", "500000"),
            ]

    fetcher = _Fetcher(_FakeIb())
    cap = asyncio.run(
        fetcher._fetch_account_summary(
            account="",
            base_density=1.0,
            as_of=date(2026, 3, 31),
            s_baseline_by_symbol={"NQ": 1200.0, "GC": 600.0},
        )
    )
    assert cap is not None
    assert cap.s_whatif_mm_per_lot is None
    assert cap.s_baseline_mm_per_lot == {"NQ": 1200.0, "GC": 600.0}
