from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..clients.whatif_order_client import (
    contract_diag,
    pick_nearest_active_fut_contract,
    resolve_ib_account_with_fallback,
    run_whatif_margin_probe,
)
from ..models.contracts import contract_for_micro_future


class IBWhatIfOrderService:
    def __init__(self, ib: Any) -> None:
        self._ib = ib

    async def preview_whatif_for_symbol(
        self,
        *,
        symbol: str,
        account: Optional[str] = None,
        timeout_seconds: float = 12.0,
    ) -> Dict[str, Any]:
        sym = str(symbol).strip().upper()
        try:
            resolved_account = account or await resolve_ib_account_with_fallback(self._ib)
        except ValueError as exc:
            raise ValueError(f"failed to resolve IB account (symbol={symbol}): {exc}") from exc

        if sym == "AAPL":
            from ib_async import Stock  # type: ignore

            contract = Stock("AAPL", "SMART", "USD")
        elif sym in ("NQ", "MNQ", "GC", "MGC"):
            engine_symbol = "NQ" if sym in ("NQ", "MNQ") else "GC"
            base = contract_for_micro_future(engine_symbol)
            contract = base
            try:
                if hasattr(self._ib, "reqContractDetailsAsync"):
                    details = await self._ib.reqContractDetailsAsync(base)
                    picked = pick_nearest_active_fut_contract(details)
                    if picked is not None:
                        contract = picked
                elif hasattr(self._ib, "qualifyContractsAsync"):
                    qualified = await self._ib.qualifyContractsAsync(base)
                    first_qualified = qualified[0] if qualified else None
                    if first_qualified is not None:
                        contract = first_qualified
            except Exception as exc:
                raise ValueError(f"failed to resolve contract for {sym}: {exc}") from exc
        else:
            raise ValueError(f"unsupported whatIf symbol: {symbol!r}")

        if contract is None:
            raise ValueError(f"{sym} contract not resolved")

        try:
            probe = await run_whatif_margin_probe(
                self._ib,
                contract,
                symbol_for_price=sym,
                account=resolved_account,
                timeout_seconds=timeout_seconds,
            )
        except ValueError as exc:
            raise ValueError(
                f"failed whatIf probe (symbol={sym}, account={resolved_account!r}, contract={contract_diag(contract)}): {exc}"
            ) from exc
        return {
            "account": resolved_account,
            "contract": contract,
            "contract_diag": contract_diag(contract),
            "margin_change": probe["margin_change"],
            "margin_path": probe["margin_path"],
            "warning": probe["warning"],
            "state_source": probe["state_source"],
            "state": probe["state"],
        }

    async def fetch_s_whatif_mm_per_lot(
        self, symbols: List[str]
    ) -> Tuple[Dict[str, float], Dict[str, str]]:
        out: Dict[str, float] = {}
        errors: Dict[str, str] = {}
        resolved_account = await resolve_ib_account_with_fallback(self._ib)
        for sym in symbols:
            probe: Dict[str, Any] = {}
            try:
                probe = await self.preview_whatif_for_symbol(
                    symbol=sym,
                    account=resolved_account,
                    timeout_seconds=12.0,
                )
                parsed = float(probe["margin_change"])
                if parsed <= 0:
                    raise ValueError(f"whatIf margin must be > 0 for {sym}, got {parsed}")
                out[sym] = parsed
            except Exception as e:
                state_obj = probe.get("state")
                state_desc = (
                    f"maintChange={getattr(state_obj, 'maintMarginChange', None)!r}, "
                    f"initChange={getattr(state_obj, 'initMarginChange', None)!r}, "
                    f"initBefore={getattr(state_obj, 'initMarginBefore', None)!r}, "
                    f"initAfter={getattr(state_obj, 'initMarginAfter', None)!r}, "
                    f"maintBefore={getattr(state_obj, 'maintMarginBefore', None)!r}, "
                    f"maintAfter={getattr(state_obj, 'maintMarginAfter', None)!r}, "
                    f"warning={getattr(state_obj, 'warningText', None)!r}"
                )
                errors[sym] = (
                    f"{type(e).__name__}: {e}; account={resolved_account!r}; "
                    f"contract=({probe.get('contract_diag', 'none')}); "
                    f"stateSource={probe.get('state_source')!r}; state=({state_desc})"
                )
                continue
        return out, errors
