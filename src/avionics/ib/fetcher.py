"""
IB（ib_async）経由で Raw のみ取得する（Layer 1）。

IBRawFetcher は IB から Raw を取得し RawMarketSnapshot（NQ/GC固定DTO）として返す。SignalBundle は作らない。
SignalBundle は FC.refresh 経由で get_last_bundle() から取得する。
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from ..data.account_positions import PositionDetailBySymbol, PositionLegsBySymbol
from ..data.raw_types import PriceBar, PriceBar1h, RawCapitalSnapshot, VolatilitySeriesPoint
from ..data.raw_market_snapshot import RawMarketSnapshot
from .account_client import IBAccountClient
from .contracts import contract_for_etf, contract_for_price, contract_for_volatility
from .market_client import IBMarketClient
from .fetch_results import AccountFetchResult, MarketFetchResult


class IBRawFetcher:
    """
    ib_async の IB インスタンスを使い、Raw を非同期で取得する（Layer 1 のみ）。
    IB から Raw を取得し RawMarketSnapshot として返す。SignalBundle は作らない。
    """

    def __init__(self, ib: Any) -> None:
        self._ib = ib
        self._market = IBMarketClient(ib)
        self._account = IBAccountClient(ib)

    # Backward-compatible private wrappers
    async def _fetch_positions_raw(self) -> List[Any]:
        return await self._account.fetch_positions_raw()

    async def _fetch_account_summary(
        self,
        account: str = "",
        base_density: float = 1.0,
        as_of: Optional[date] = None,
        s_baseline_by_symbol: Optional[Dict[str, float]] = None,
    ) -> Optional[RawCapitalSnapshot]:
        return await self._account.fetch_account_summary(
            account=account,
            base_density=base_density,
            as_of=as_of,
            s_baseline_by_symbol=s_baseline_by_symbol,
        )

    async def _fetch_s_whatif_mm_per_lot(
        self, symbols: List[str]
    ) -> Tuple[Dict[str, float], Dict[str, str]]:
        return await self._account.fetch_s_whatif_mm_per_lot(symbols)

    async def fetch_position_legs(self, symbols: List[str]) -> Dict[str, Dict[str, float]]:
        """
        口座ポジションを銘柄別に集計し、{symbol: {future,k1,k2}} を返す。

        - future: 先物（FUT/CONTFUT）を **マイクロ相当枚数**（NQ 群→MNQ 相当、GC 群→MGC 相当）に換算したネット
        - k1: オプションC（OPT/FOP, right=C）。エンジン銘柄（NQ/GC）へ MNQ/MGC ルートは正規化して集計
        - k2: オプションP（OPT/FOP, right=P）。同上
        """
        return await self._account.fetch_position_legs(symbols)

    async def fetch_position_detail(self, symbols: List[str]) -> Dict[str, Dict[str, Dict[str, float]]]:
        """
        Daily 表示用の詳細ポジションを返す。

        futures は契約ごとに buy/sell 枚数（正の position を buy、負を sell に分類）。
        キー: nq_buy, nq_sell, mnq_buy, mnq_sell, gc_buy, gc_sell, mgc_buy, mgc_sell。
        options も契約ごとに C/P の buy/sell を分離。
        """
        return await self._account.fetch_position_detail(symbols)

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
    ) -> Tuple[
        RawMarketSnapshot,
        Optional[RawCapitalSnapshot],
        PositionLegsBySymbol,
        PositionDetailBySymbol,
    ]:
        """
        IB から Raw を取得し、RawMarketSnapshot（NQ/GC固定DTO）として返す。
        Layer 2 計算は行わない。SignalBundle が欲しい場合は呼び出し側で build_signal_bundle を呼ぶ。

        :return: (RawMarketSnapshot, Optional[RawCapitalSnapshot])
        """
        vol_map = volatility_symbols or {s: "VXN" if s == "NQ" else "GVZ" for s in price_symbols}

        def _series_limit(sym: str) -> int:
            if not v_recovery_params or sym not in v_recovery_params:
                return 20
            th = v_recovery_params[sym]
            v1 = int(th.get("V1_confirm_days", 1))
            v2 = int(th.get("V2_confirm_days", 2))
            return max(v1, v2, 20)

        market_tasks: dict[str, Any] = {}
        for sym in price_symbols:
            market_tasks[f"price:{sym}"] = self._market.fetch_bars(
                contract_for_price(sym), as_of
            )
            market_tasks[f"vol:{sym}"] = self._market.fetch_volatility_series(
                contract_for_volatility(vol_map[sym]), as_of, limit=_series_limit(sym)
            )
            market_tasks[f"bars1h:{sym}"] = self._market.fetch_bars_1h(
                contract_for_price(sym), as_of, duration_str="5 D"
            )
        market_tasks[f"credit:{liquidity_credit_hyg_symbol}"] = self._market.fetch_bars(
            contract_for_etf(liquidity_credit_hyg_symbol), as_of
        )
        market_tasks[f"credit:{liquidity_credit_lqd_symbol}"] = self._market.fetch_bars(
            contract_for_etf(liquidity_credit_lqd_symbol), as_of
        )
        if liquidity_tip_symbol:
            market_tasks[f"tip:{liquidity_tip_symbol}"] = self._market.fetch_bars(
                contract_for_etf(liquidity_tip_symbol), as_of
            )

        market_keys = list(market_tasks.keys())
        market_values = await asyncio.gather(*(market_tasks[k] for k in market_keys))
        market_map = dict(zip(market_keys, market_values))

        price_bars: Dict[str, List[PriceBar]] = {
            sym: market_map[f"price:{sym}"] for sym in price_symbols
        }
        vol_series: Dict[str, List[VolatilitySeriesPoint]] = {
            sym: market_map[f"vol:{sym}"] for sym in price_symbols if market_map[f"vol:{sym}"]
        }
        bars_1h: Dict[str, List[PriceBar1h]] = {
            sym: market_map[f"bars1h:{sym}"] for sym in price_symbols
        }
        credit_map: Dict[str, List[PriceBar]] = {
            liquidity_credit_hyg_symbol: market_map[f"credit:{liquidity_credit_hyg_symbol}"],
            liquidity_credit_lqd_symbol: market_map[f"credit:{liquidity_credit_lqd_symbol}"],
        }
        tip: List[PriceBar] = (
            market_map.get(f"tip:{liquidity_tip_symbol}", []) if liquidity_tip_symbol else []
        )

        positions_raw, capital = await asyncio.gather(
            self._account.fetch_positions_raw(),
            self._account.fetch_account_summary(
                account=account,
                base_density=base_density,
                as_of=as_of,
                s_baseline_by_symbol=s_baseline_by_symbol,
            ),
        )
        positions_legs = self._account.parse_position_legs_from_raw(price_symbols, positions_raw)
        positions_detail = self._account.parse_position_detail_from_raw(price_symbols, positions_raw)
        account_result = AccountFetchResult(
            capital=capital,
            positions_legs=positions_legs,
            positions_detail=positions_detail,
        )
        market_result = MarketFetchResult(
            price_bars=price_bars,
            volatility_series=vol_series,
            credit_bars=credit_map,
            tip_bars=tip,
            bars_1h=bars_1h,
        )

        snapshot = RawMarketSnapshot(
            as_of=as_of,
            nq_price_bars=list(market_result.price_bars.get("NQ", [])),
            gc_price_bars=list(market_result.price_bars.get("GC", [])),
            nq_price_bars_1h=list(market_result.bars_1h.get("NQ", [])),
            gc_price_bars_1h=list(market_result.bars_1h.get("GC", [])),
            nq_volatility_series=list(market_result.volatility_series.get("NQ", [])),
            gc_volatility_series=list(market_result.volatility_series.get("GC", [])),
            capital_snapshot=account_result.capital,
            credit_bars=market_result.credit_bars,
            tip_bars=market_result.tip_bars,
        )
        return snapshot, account_result.capital, account_result.positions_legs, account_result.positions_detail
