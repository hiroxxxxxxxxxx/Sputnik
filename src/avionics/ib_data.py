"""
IB（Interactive Brokers）API 経由で Cockpit 用 Layer 1 データを取得し、SignalBundle を組み立てる。

ib_async を使用。非同期のみ。定義書「4-2 情報の階層構造」に従い、
Raw 取得 → 既存の compute_*（Layer 2）で SignalBundle を生成。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .Instruments.raw_data import (
    PriceBar,
    PriceBar1h,
    RawCapitalSnapshot,
    RawDataProvider,
    VolatilitySeriesPoint,
)
from .Instruments.signals import (
    AltitudeRegime,
    CapitalSignals,
    LiquiditySignals,
    PriceSignals,
    SignalBundle,
    VolatilitySignal,
    compute_capital_signals,
    compute_liquidity_signals_credit,
    compute_liquidity_signals_tip,
    compute_price_signals,
    compute_volatility_signal,
)

def _bar_to_price_bar(bar: Any) -> PriceBar:
    """ib_async の BarData を PriceBar（日足）に変換する。"""
    d = getattr(bar, "date", date.today())
    if isinstance(d, datetime):
        bar_date = d.date()
    elif isinstance(d, date):
        bar_date = d
    else:
        bar_date = date.today()
    return PriceBar(
        date=bar_date,
        close=float(bar.close),
        high=float(bar.high),
        volume=float(bar.volume),
    )


def _bar_to_price_bar_1h(bar: Any) -> PriceBar1h:
    """ib_async の BarData を PriceBar1h に変換する。"""
    d = getattr(bar, "date", datetime.now(timezone.utc))
    if not isinstance(d, datetime):
        d = datetime(d.year, d.month, d.day, 16, 0, 0, tzinfo=timezone.utc) if isinstance(d, date) else datetime.now(timezone.utc)
    return PriceBar1h(
        bar_end=d,
        open=float(getattr(bar, "open", bar.close)),
        close=float(bar.close),
        high=float(bar.high),
        volume=float(bar.volume),
    )


@dataclass
class CachedRawDataProvider(RawDataProvider):
    """
    Layer 1 の取得窓口のキャッシュ実装。IB 取得結果を保持し、RawDataProvider として渡す。

    定義書「4-2 情報の階層構造」参照。
    """

    _price_bars: Dict[str, List[PriceBar]] = field(default_factory=dict)
    _price_bars_1h: Dict[str, List[PriceBar1h]] = field(default_factory=dict)
    _volatility_series: Dict[str, List[VolatilitySeriesPoint]] = field(default_factory=dict)
    _capital_snapshot: Optional[RawCapitalSnapshot] = None
    _credit_bars: Dict[str, List[PriceBar]] = field(default_factory=dict)
    _tip_bars: List[PriceBar] = field(default_factory=list)

    def get_price_series(self, symbol: str, limit: int) -> List[PriceBar]:
        bars = self._price_bars.get(symbol, [])
        return bars[-limit:] if limit else bars

    def get_price_series_1h(self, symbol: str, limit: int) -> List[PriceBar1h]:
        bars = self._price_bars_1h.get(symbol, [])
        return bars[-limit:] if limit else bars

    def get_volatility_index(self, symbol: str, as_of: date) -> Optional[float]:
        series = self._volatility_series.get(symbol, [])
        candidates = [(d, v) for d, v in series if d <= as_of]
        return max(candidates, key=lambda x: x[0])[1] if candidates else None

    def get_volatility_series(self, symbol: str, limit: int) -> List[VolatilitySeriesPoint]:
        series = self._volatility_series.get(symbol, [])
        return series[-limit:] if limit else series

    def get_capital_snapshot(self, as_of: date) -> Optional[RawCapitalSnapshot]:
        return self._capital_snapshot

    def get_credit_series(self, symbol: str, limit: int) -> List[PriceBar]:
        bars = self._credit_bars.get(symbol, [])
        return bars[-limit:] if limit else bars

    def get_tip_series(self, limit: int) -> List[PriceBar]:
        return self._tip_bars[-limit:] if limit else self._tip_bars


def _contract_for_price(symbol: str) -> Any:
    """
    価格系列用の IB 契約。SPEC 3-1: シグナル判定は連続足を使用。
    ContFuture + 根シンボル（NQ/GC）で IB API は継続足を返す（secType=CONTFUT）。
    """
    from ib_async import ContFuture

    # ContFuture + 根シンボルで IB は継続足を返す（API では NQ!/GC! ではなく NQ/GC を指定）。
    m = {"NQ": ("NQ", "CME", "USD"), "GC": ("GC", "COMEX", "USD")}
    if symbol in m:
        s, ex, cur = m[symbol]
        return ContFuture(symbol=s, exchange=ex, currency=cur)
    return ContFuture(symbol=symbol, exchange="SMART", currency="USD")


def _contract_for_volatility(symbol: str) -> Any:
    """ボラティリティ指数用。VXN/GVZ は IND。"""
    from ib_async import Index

    # VXN: Nasdaq Volatility, GVZ: Gold VIX
    ex = "CBOE" if symbol in ("VXN", "VIX", "GVZ") else "SMART"
    return Index(symbol=symbol, exchange=ex, currency="USD")


def _contract_for_etf(symbol: str) -> Any:
    """ETF（HYG, LQD, TIP 等）用。"""
    from ib_async import Stock

    return Stock(symbol=symbol, exchange="SMART", currency="USD")


class IBDataFetcher:
    """
    ib_async の IB インスタンスを使い、Cockpit 用 SignalBundle を非同期で取得する。

    価格・ボラ・流動性・証拠金を IB から取得し、既存の Layer 2 計算で SignalBundle を組み立てる。
    定義書「4-2 情報の階層構造」参照。
    """

    def __init__(self, ib: Any) -> None:
        """
        :param ib: 接続済み ib_async.IB インスタンス。
        """
        self._ib = ib

    async def _fetch_bars(
        self,
        contract: Any,
        end_date: date,
        duration_str: str = "40 D",
        bar_size: str = "1 day",
    ) -> List[PriceBar]:
        """
        日足の履歴を取得し PriceBar のリストで返す。
        useRTH=True で現物市場のオープンクローズに合わせる（SPEC: 終値はNY現物クローズ ET 16:00）。
        連続先物では endDateTime を渡さない（IB 制約）。
        """
        from ib_async import ContFuture
        from ib_async.util import formatIBDatetime

        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
        end_str = formatIBDatetime(end_dt)
        is_cont_future = isinstance(contract, ContFuture)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime="" if is_cont_future else end_str,
            durationStr=duration_str,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,  # NY現物時間に合わせる（ET 09:30〜16:00）
            timeout=30,
        )
        return [_bar_to_price_bar(b) for b in bars]

    async def _fetch_bars_1h(
        self,
        contract: Any,
        end_date: date,
        duration_str: str = "5 D",
    ) -> List[PriceBar1h]:
        """
        1h足の履歴を取得。useRTH=True でNY現物時間（ET 09:30〜16:00）に合わせる（SPEC 4-2-1-2 1hノックイン等）。
        """
        from ib_async import ContFuture
        from ib_async.util import formatIBDatetime

        end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=timezone.utc)
        end_str = formatIBDatetime(end_dt)
        is_cont_future = isinstance(contract, ContFuture)
        bars = await self._ib.reqHistoricalDataAsync(
            contract,
            endDateTime="" if is_cont_future else end_str,
            durationStr=duration_str,
            barSizeSetting="1 hour",
            whatToShow="TRADES",
            useRTH=True,
            timeout=30,
        )
        return [_bar_to_price_bar_1h(b) for b in bars]

    async def _fetch_volatility_index(self, contract: Any, as_of: date) -> Optional[float]:
        """ボラ指数はその日の 1 本の終値を返す。"""
        bars = await self._fetch_bars(contract, as_of, duration_str="2 D", bar_size="1 day")
        for b in reversed(bars):
            if b.date <= as_of:
                return b.close
        return None

    async def _fetch_volatility_series(
        self, contract: Any, as_of: date, limit: int = 5
    ) -> List[VolatilitySeriesPoint]:
        """直近 limit 営業日分の (日付, 終値) を取得。復帰確認の連続日数算出用。"""
        bars = await self._fetch_bars(
            contract, as_of, duration_str="15 D", bar_size="1 day"
        )
        points: List[VolatilitySeriesPoint] = []
        for b in sorted(bars, key=lambda x: x.date):
            if b.date <= as_of:
                points.append((b.date, b.close))
        return points[-limit:] if len(points) > limit else points

    async def _fetch_account_summary(
        self,
        account: str = "",
        base_density: float = 1.0,
        as_of: Optional[date] = None,
    ) -> Optional[RawCapitalSnapshot]:
        """証拠金サマリから RawCapitalSnapshot を組み立てる。"""
        summary = await self._ib.accountSummaryAsync(account)
        by_tag: Dict[str, float] = {}
        for av in summary:
            try:
                by_tag[av.tag] = float(av.value)
            except (ValueError, TypeError):
                continue
        nlv = by_tag.get("NetLiquidation") or by_tag.get("EquityWithLoanValue") or 0.0
        mm = by_tag.get("MaintMarginReq") or by_tag.get("InitMarginReq") or 0.0
        if nlv <= 0:
            return None
        current_value = by_tag.get("GrossPositionValue") or nlv
        d = as_of or date.today()
        return RawCapitalSnapshot(
            as_of=d,
            mm=mm,
            nlv=nlv,
            base_density=base_density,
            current_value=current_value,
            futures_multiplier=1.0,
        )

    async def fetch_signal_bundle(
        self,
        as_of: date,
        price_symbols: List[str],
        volatility_symbols: Optional[Dict[str, str]] = None,
        liquidity_credit_symbol: Optional[str] = None,
        liquidity_tip: bool = True,
        base_density: float = 1.0,
        v_altitude: AltitudeRegime = "high_mid",
        c_altitude: AltitudeRegime = "high_mid",
        r_altitude: AltitudeRegime = "high_mid",
        account: str = "",
        v_recovery_params: Optional[Dict[str, dict]] = None,
    ) -> Tuple[SignalBundle, Optional[RawCapitalSnapshot]]:
        """
        IB から Raw を取得し、Layer 2 計算で SignalBundle を組み立てる。

        :param liquidity_credit_symbol: C因子用（NQ系）。例: "HYG"。None のときは取得しない。
        :param liquidity_tip: R因子用（GC系）TIP 系列を取得するか。
        :param v_recovery_params: 銘柄→V因子の高度スライス（V1_off, V2_off, V1_confirm_days, V2_confirm_days 等）。
            復帰確認の閾値と取得本数（max(confirm_days)）に利用。None なら閾値は未使用・取得本数はデフォルト。
        :return: (SignalBundle, RawCapitalSnapshot または None)。Daily レポートで NLV 等表示に利用可。
        """
        cache = CachedRawDataProvider()
        vol_map = volatility_symbols or {s: "VXN" if s == "NQ" else "GVZ" for s in price_symbols}

        def _series_limit(sym: str) -> int:
            """復帰日数パラメータから取得本数を決める。"""
            if not v_recovery_params or sym not in v_recovery_params:
                return 5
            th = v_recovery_params[sym]
            v1 = int(th.get("V1_confirm_days", 1))
            v2 = int(th.get("V2_confirm_days", 2))
            return max(v1, v2, 1)

        # 価格・ボラ・証拠金・流動性（C/R因子用）を並列取得
        coros: List[Any] = []
        for sym in price_symbols:
            coros.append(self._fetch_bars(_contract_for_price(sym), as_of))
        for sym in price_symbols:
            coros.append(
                self._fetch_volatility_series(
                    _contract_for_volatility(vol_map[sym]), as_of, limit=_series_limit(sym)
                )
            )
        coros.append(
            self._fetch_account_summary(
                account=account, base_density=base_density, as_of=as_of
            )
        )
        if liquidity_credit_symbol:
            coros.append(
                self._fetch_bars(_contract_for_etf(liquidity_credit_symbol), as_of)
            )
        if liquidity_tip:
            coros.append(self._fetch_bars(_contract_for_etf("TIP"), as_of))
        for sym in price_symbols:
            coros.append(
                self._fetch_bars_1h(_contract_for_price(sym), as_of, duration_str="5 D")
            )

        results = await asyncio.gather(*coros)
        idx = 0
        for sym in price_symbols:
            cache._price_bars[sym] = results[idx]
            idx += 1
        for sym in price_symbols:
            series = results[idx]
            idx += 1
            if series:
                cache._volatility_series[sym] = series
        cache._capital_snapshot = results[idx]
        idx += 1
        if liquidity_credit_symbol:
            cache._credit_bars[liquidity_credit_symbol] = results[idx]
            idx += 1
        if liquidity_tip:
            cache._tip_bars = results[idx]
            idx += 1
        for sym in price_symbols:
            cache._price_bars_1h[sym] = results[idx]
            idx += 1

        # Layer 2 計算
        price_signals: Dict[str, PriceSignals] = {}
        for sym in price_symbols:
            price_signals[sym] = compute_price_signals(cache, sym, as_of)

        vol_signals: Dict[str, VolatilitySignal] = {}
        for sym in price_symbols:
            th = v_recovery_params.get(sym) if v_recovery_params else None
            v1_off = float(th["V1_off"]) if th and "V1_off" in th else None
            v2_off = float(th["V2_off"]) if th and "V2_off" in th else None
            vol_signals[sym] = compute_volatility_signal(
                cache, sym, as_of, v_altitude,
                v1_off_threshold=v1_off,
                v2_off_threshold=v2_off,
            )

        cap_signals = compute_capital_signals(cache, as_of)

        liquidity_credit: Optional[LiquiditySignals] = None
        if liquidity_credit_symbol:
            liquidity_credit = compute_liquidity_signals_credit(
                cache, liquidity_credit_symbol, as_of, c_altitude
            )

        liquidity_tip_sig: Optional[LiquiditySignals] = None
        if liquidity_tip:
            liquidity_tip_sig = compute_liquidity_signals_tip(cache, as_of, r_altitude)

        bundle = SignalBundle(
            price_signals=price_signals,
            volatility_signals=vol_signals,
            liquidity_credit=liquidity_credit,
            liquidity_tip=liquidity_tip_sig,
            capital_signals=cap_signals,
        )
        return bundle, cache._capital_snapshot
