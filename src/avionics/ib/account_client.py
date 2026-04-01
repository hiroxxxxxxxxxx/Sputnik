from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from ..account_parsers import (
    parse_position_detail_from_ib_positions,
    parse_position_legs_from_ib_positions,
)
from ..data.account_positions import PositionDetailBySymbol, PositionLegsBySymbol
from ..data.raw_types import RawCapitalSnapshot
from .contracts import contract_for_micro_future


def parse_float_value(raw: Any, *, field_name: str) -> float:
    if raw is None:
        raise ValueError(f"{field_name} is None")
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).replace(",", "").strip()
    if not s:
        raise ValueError(f"{field_name} is empty")
    return float(s)


class IBAccountClient:
    """IB の口座情報・whatIf・positions 取得専用。"""

    def __init__(self, ib: Any) -> None:
        self._ib = ib

    async def fetch_positions_raw(self) -> List[Any]:
        if hasattr(self._ib, "reqPositionsAsync"):
            return await self._ib.reqPositionsAsync()
        if hasattr(self._ib, "positionsAsync"):
            return await self._ib.positionsAsync()
        if hasattr(self._ib, "positions"):
            return self._ib.positions()
        raise ValueError("IB fetcher does not support positions API")

    async def fetch_position_legs(self, symbols: List[str]) -> PositionLegsBySymbol:
        return parse_position_legs_from_ib_positions(symbols, await self.fetch_positions_raw())

    async def fetch_position_detail(self, symbols: List[str]) -> PositionDetailBySymbol:
        return parse_position_detail_from_ib_positions(symbols, await self.fetch_positions_raw())

    def parse_position_legs_from_raw(
        self, symbols: List[str], positions_raw: List[Any]
    ) -> PositionLegsBySymbol:
        return parse_position_legs_from_ib_positions(symbols, positions_raw)

    def parse_position_detail_from_raw(
        self, symbols: List[str], positions_raw: List[Any]
    ) -> PositionDetailBySymbol:
        return parse_position_detail_from_ib_positions(symbols, positions_raw)

    async def fetch_account_summary(
        self,
        account: str = "",
        base_density: float = 1.0,
        as_of: Optional[date] = None,
        s_baseline_by_symbol: Optional[Dict[str, float]] = None,
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
        s_whatif_mm_per_lot: Optional[Dict[str, float]] = None
        s_whatif_errors: Optional[Dict[str, str]] = None
        if s_baseline_by_symbol is not None:
            try:
                s_whatif_mm_per_lot, s_whatif_errors = await self.fetch_s_whatif_mm_per_lot(
                    sorted(s_baseline_by_symbol.keys())
                )
            except Exception:
                s_whatif_mm_per_lot = None
                s_whatif_errors = None
        return RawCapitalSnapshot(
            as_of=d,
            mm=mm,
            nlv=nlv,
            base_density=base_density,
            current_value=current_value,
            futures_multiplier=1.0,
            s_whatif_mm_per_lot=s_whatif_mm_per_lot,
            s_baseline_mm_per_lot=s_baseline_by_symbol,
            s_whatif_errors=s_whatif_errors,
        )

    async def fetch_s_whatif_mm_per_lot(
        self, symbols: List[str]
    ) -> Tuple[Dict[str, float], Dict[str, str]]:
        """S因子用 whatIf（1枚あたりMM）を銘柄別に取得する。"""
        from ib_async import MarketOrder

        out: Dict[str, float] = {}
        errors: Dict[str, str] = {}
        for sym in symbols:
            try:
                base_contract = contract_for_micro_future(sym)
                contract = base_contract
                if hasattr(self._ib, "reqContractDetailsAsync"):
                    details = await self._ib.reqContractDetailsAsync(base_contract)
                    if details:
                        candidates = [
                            getattr(d, "contract", None)
                            for d in details
                            if getattr(d, "contract", None) is not None
                        ]
                        futs = [c for c in candidates if getattr(c, "secType", None) == "FUT"]
                        if futs:
                            contract = sorted(
                                futs,
                                key=lambda c: str(getattr(c, "lastTradeDateOrContractMonth", "")),
                            )[0]
                elif hasattr(self._ib, "qualifyContractsAsync"):
                    qualified = await self._ib.qualifyContractsAsync(base_contract)
                    first_qualified = qualified[0] if qualified else None
                    if first_qualified is not None:
                        contract = first_qualified
                if contract is None:
                    raise ValueError(f"whatIf contract resolve failed for {sym}: contract is None")
                if getattr(contract, "secType", None) in (None, ""):
                    raise ValueError(
                        f"whatIf contract resolve failed for {sym}: secType missing on contract"
                    )
                order = MarketOrder("BUY", 1)
                order.whatIf = True
                if hasattr(self._ib, "whatIfOrderAsync"):
                    trade_or_state = await asyncio.wait_for(
                        self._ib.whatIfOrderAsync(contract, order), timeout=12
                    )
                elif hasattr(self._ib, "whatIfOrder"):
                    trade_or_state = self._ib.whatIfOrder(contract, order)
                else:
                    raise ValueError("IB client does not support whatIf order API")
                state = getattr(trade_or_state, "orderState", trade_or_state)
                mm_value = None
                for field in ("maintMarginChange", "initMarginChange"):
                    if hasattr(state, field):
                        mm_value = getattr(state, field)
                        if mm_value not in (None, "", "0", "0.0"):
                            break
                if mm_value in (None, "", "0", "0.0"):
                    raise ValueError(f"whatIf margin value missing for {sym}")
                parsed = parse_float_value(mm_value, field_name=f"whatIf margin for {sym}")
                if parsed <= 0:
                    raise ValueError(f"whatIf margin must be > 0 for {sym}, got {parsed}")
                out[sym] = parsed
            except Exception as e:
                errors[sym] = f"{type(e).__name__}: {e}"
                continue
        return out, errors
