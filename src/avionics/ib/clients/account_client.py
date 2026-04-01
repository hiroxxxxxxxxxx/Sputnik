from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from ...account_parsers import (
    parse_position_detail_from_ib_positions,
    parse_position_legs_from_ib_positions,
)
from ...data.account_positions import PositionDetailBySymbol, PositionLegsBySymbol
from ...data.raw_types import RawCapitalSnapshot


class IBAccountClient:
    """IB の口座情報・whatIf・positions 取得専用。"""

    def __init__(self, ib: Any) -> None:
        self._ib = ib

    async def fetch_positions_raw(self) -> List[Any]:
        if hasattr(self._ib, "reqPositionsAsync"):
            try:
                out = await self._ib.reqPositionsAsync()
            except Exception as exc:
                raise ValueError(f"failed to fetch positions via reqPositionsAsync: {exc}") from exc
            if out is None:
                raise ValueError("positions are None via reqPositionsAsync")
            return out
        if hasattr(self._ib, "positionsAsync"):
            try:
                out = await self._ib.positionsAsync()
            except Exception as exc:
                raise ValueError(f"failed to fetch positions via positionsAsync: {exc}") from exc
            if out is None:
                raise ValueError("positions are None via positionsAsync")
            return out
        if hasattr(self._ib, "positions"):
            try:
                out = self._ib.positions()
            except Exception as exc:
                raise ValueError(f"failed to fetch positions via positions: {exc}") from exc
            if out is None:
                raise ValueError("positions are None via positions")
            return out
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
        s_whatif_mm_per_lot: Optional[Dict[str, float]] = None,
        s_whatif_errors: Optional[Dict[str, str]] = None,
    ) -> Optional[RawCapitalSnapshot]:
        """証拠金サマリから RawCapitalSnapshot を組み立てる。"""
        try:
            summary = await self._ib.accountSummaryAsync(account)
        except Exception as exc:
            raise ValueError(f"failed to fetch account summary (account={account!r}): {exc}") from exc
        if summary is None:
            raise ValueError(f"account summary is None (account={account!r})")
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
            s_whatif_mm_per_lot=s_whatif_mm_per_lot,
            s_baseline_mm_per_lot=s_baseline_by_symbol,
            s_whatif_errors=s_whatif_errors,
        )
