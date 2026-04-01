from __future__ import annotations

import asyncio
from datetime import date
from typing import Any, Optional


def resolve_ib_account(ib: Any) -> Optional[str]:
    accounts = getattr(ib, "managedAccounts", None)
    if isinstance(accounts, (list, tuple)):
        for a in accounts:
            s = str(a).strip()
            if s:
                return s
    if isinstance(accounts, str):
        s = accounts.strip()
        if s:
            return s.split(",")[0].strip() or None
    return None


async def resolve_ib_account_with_fallback(ib: Any) -> Optional[str]:
    account = resolve_ib_account(ib)
    if account:
        return account
    if not hasattr(ib, "accountSummaryAsync"):
        return None
    try:
        summary = await ib.accountSummaryAsync("")
    except Exception as exc:
        raise ValueError(f"failed to fetch account summary for fallback: {exc}") from exc
    for av in summary or []:
        acc = str(getattr(av, "account", "")).strip()
        if acc:
            return acc
    return None


def parse_float_or_none(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return float(raw)
        s = str(raw).replace(",", "").strip()
        if not s:
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def extract_whatif_margin_change(state: Any) -> tuple[float, str]:
    mm_change = parse_float_or_none(getattr(state, "maintMarginChange", None))
    if mm_change not in (None, 0.0):
        return (float(mm_change), "maintMarginChange")
    init_change = parse_float_or_none(getattr(state, "initMarginChange", None))
    if init_change not in (None, 0.0):
        return (float(init_change), "initMarginChange")

    init_before = parse_float_or_none(getattr(state, "initMarginBefore", None))
    init_after = parse_float_or_none(getattr(state, "initMarginAfter", None))
    if init_before is not None and init_after is not None:
        return (float(init_after - init_before), "initMarginAfter-initMarginBefore")

    maint_before = parse_float_or_none(getattr(state, "maintMarginBefore", None))
    maint_after = parse_float_or_none(getattr(state, "maintMarginAfter", None))
    if maint_before is not None and maint_after is not None:
        return (float(maint_after - maint_before), "maintMarginAfter-maintMarginBefore")

    raise ValueError(
        "whatIf margin fields missing: "
        f"maintChange={getattr(state, 'maintMarginChange', None)!r}, "
        f"initChange={getattr(state, 'initMarginChange', None)!r}, "
        f"initBefore={getattr(state, 'initMarginBefore', None)!r}, "
        f"initAfter={getattr(state, 'initMarginAfter', None)!r}, "
        f"maintBefore={getattr(state, 'maintMarginBefore', None)!r}, "
        f"maintAfter={getattr(state, 'maintMarginAfter', None)!r}"
    )


def extract_order_state_from_whatif_result(result: Any) -> tuple[Any, str]:
    direct = result
    if direct is not None and any(
        hasattr(direct, f)
        for f in (
            "maintMarginChange",
            "initMarginChange",
            "initMarginBefore",
            "initMarginAfter",
            "maintMarginBefore",
            "maintMarginAfter",
        )
    ):
        return direct, "result"
    nested_order_state = getattr(result, "orderState", None)
    if nested_order_state is not None:
        return nested_order_state, "result.orderState"
    status = getattr(result, "orderStatus", None)
    status_state = getattr(status, "orderState", None)
    if status_state is not None:
        return status_state, "result.orderStatus.orderState"
    return result, "fallback(result)"


def parse_contract_expiry_ymd(raw: Any) -> str:
    s = str(raw or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if len(digits) >= 8:
        return digits[:8]
    if len(digits) == 6:
        return f"{digits}31"
    return "00000000"


def pick_nearest_active_fut_contract(details: Any) -> Optional[Any]:
    contracts = [
        getattr(d, "contract", None)
        for d in (details or [])
        if getattr(getattr(d, "contract", None), "secType", None) == "FUT"
    ]
    if not contracts:
        return None
    today = date.today().strftime("%Y%m%d")
    active = [
        c
        for c in contracts
        if parse_contract_expiry_ymd(getattr(c, "lastTradeDateOrContractMonth", "")) >= today
    ]
    pool = active if active else contracts
    return sorted(
        pool,
        key=lambda c: parse_contract_expiry_ymd(
            getattr(c, "lastTradeDateOrContractMonth", "")
        ),
    )[0]


def contract_diag(contract: Optional[Any]) -> str:
    if contract is None:
        return "none"
    return (
        f"symbol={getattr(contract, 'symbol', None)!r}, "
        f"localSymbol={getattr(contract, 'localSymbol', None)!r}, "
        f"exchange={getattr(contract, 'exchange', None)!r}, "
        f"expiry={getattr(contract, 'lastTradeDateOrContractMonth', None)!r}, "
        f"tradingClass={getattr(contract, 'tradingClass', None)!r}, "
        f"multiplier={getattr(contract, 'multiplier', None)!r}, "
        f"conId={getattr(contract, 'conId', None)!r}"
    )


def whatif_limit_price_for_symbol(symbol: str) -> float:
    s = str(symbol).strip().upper()
    if s in ("NQ", "MNQ"):
        return 20000.0
    if s in ("GC", "MGC"):
        return 2500.0
    if s == "AAPL":
        return 200.0
    raise ValueError(f"unsupported whatIf limit symbol: {symbol!r}")


async def run_whatif_margin_probe(
    ib: Any,
    contract: Any,
    *,
    symbol_for_price: str,
    account: Optional[str],
    timeout_seconds: float = 12.0,
) -> dict[str, Any]:
    from ib_async import LimitOrder

    order = LimitOrder("BUY", 1, whatif_limit_price_for_symbol(symbol_for_price))
    order.whatIf = True
    if account:
        order.account = account

    try:
        if hasattr(ib, "whatIfOrderAsync"):
            result = await asyncio.wait_for(
                ib.whatIfOrderAsync(contract, order), timeout=timeout_seconds
            )
        elif hasattr(ib, "whatIfOrder"):
            result = ib.whatIfOrder(contract, order)
        else:
            raise ValueError("IB client does not support whatIf order API")
    except Exception as exc:
        raise ValueError(
            f"failed to run whatIf probe (symbol={symbol_for_price}, account={account!r}): {exc}"
        ) from exc

    state, state_source = extract_order_state_from_whatif_result(result)
    warning_text = getattr(state, "warningText", None)
    margin_change, margin_path = extract_whatif_margin_change(state)
    return {
        "margin_change": margin_change,
        "margin_path": margin_path,
        "warning": (str(warning_text) if warning_text not in (None, "") else None),
        "state_source": state_source,
        "state": state,
    }
