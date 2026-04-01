from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from avionics.ib.services import healthcheck_service as healthcheck

pytest.importorskip("ib_async")


class _OkIb:
    managedAccounts = ["U1234567"]

    async def reqHistoricalDataAsync(self, *args, **kwargs):
        return [object(), object()]

    async def reqContractDetailsAsync(self, _base):
        class _Detail:
            def __init__(self):
                self.contract = type(
                    "C",
                    (),
                    {
                        "secType": "FUT",
                        "lastTradeDateOrContractMonth": "20260428",
                    },
                )()

        return [_Detail()]

    async def whatIfOrderAsync(self, _contract, _order):
        assert getattr(_order, "account", None) == "U1234567"
        assert float(getattr(_order, "lmtPrice", 0.0)) > 0.0

        class _State:
            initMarginChange = "120.5"

        return _State()


def test_run_ib_healthcheck_ok(monkeypatch):
    @asynccontextmanager
    async def _stub_with_ib_connection(*args, **kwargs):
        yield _OkIb()

    monkeypatch.setattr(healthcheck, "with_ib_connection", _stub_with_ib_connection)

    async def _run():
        out = await healthcheck.run_ib_healthcheck("127.0.0.1", 8888)
        assert out["ib_connected"] is True
        assert out["historical_nq_ok"] is True
        assert out["historical_nq_bars"] == 2
        assert out["whatif_stock_ok"] is True
        assert out["whatif_mnq_contract"] != "none"
        assert out["overall"] in ("OK", "DEGRADED")

    import asyncio

    asyncio.run(_run())


def test_run_ib_healthcheck_whatif_fallback_before_after(monkeypatch):
    class _FallbackIb(_OkIb):
        async def whatIfOrderAsync(self, _contract, _order):
            class _State:
                initMarginChange = ""
                maintMarginChange = ""
                initMarginBefore = "1000"
                initMarginAfter = "1125.5"

            return _State()

    @asynccontextmanager
    async def _stub_with_ib_connection(*args, **kwargs):
        yield _FallbackIb()

    monkeypatch.setattr(healthcheck, "with_ib_connection", _stub_with_ib_connection)

    async def _run():
        out = await healthcheck.run_ib_healthcheck("127.0.0.1", 8888)
        assert out["whatif_mnq_ok"] is True
        assert out["whatif_mnq_margin_path"] == "initMarginAfter-initMarginBefore"
        assert out["whatif_mnq_margin_change"] == 125.5

    import asyncio

    asyncio.run(_run())


def test_run_ib_healthcheck_connect_fail(monkeypatch):
    @asynccontextmanager
    async def _stub_with_ib_connection(*args, **kwargs):
        raise RuntimeError("connect fail")
        yield

    monkeypatch.setattr(healthcheck, "with_ib_connection", _stub_with_ib_connection)

    async def _run():
        out = await healthcheck.run_ib_healthcheck("127.0.0.1", 8888)
        assert out["ib_connected"] is False
        assert out["overall"] == "FAIL"

    import asyncio

    asyncio.run(_run())


def test_run_ib_healthcheck_resolves_account_from_summary(monkeypatch):
    class _SummaryAccountIb(_OkIb):
        managedAccounts = ""

        async def accountSummaryAsync(self, _account):
            return [
                type("AV", (), {"account": "U7654321", "tag": "NetLiquidation", "value": "1"})()
            ]

        async def whatIfOrderAsync(self, _contract, _order):
            assert getattr(_order, "account", None) == "U7654321"
            return await super().whatIfOrderAsync(_contract, _order)

    @asynccontextmanager
    async def _stub_with_ib_connection(*args, **kwargs):
        yield _SummaryAccountIb()

    monkeypatch.setattr(healthcheck, "with_ib_connection", _stub_with_ib_connection)

    async def _run():
        out = await healthcheck.run_ib_healthcheck("127.0.0.1", 8888)
        assert out["whatif_mnq_ok"] is True
        assert out["whatif_mnq_account"] == "U7654321"

    import asyncio

    asyncio.run(_run())


def test_run_ib_healthcheck_extracts_state_from_order_status(monkeypatch):
    class _StatusStateIb(_OkIb):
        async def whatIfOrderAsync(self, _contract, _order):
            class _State:
                initMarginChange = "10"

            class _OrderStatus:
                orderState = _State()

            return type("Trade", (), {"orderStatus": _OrderStatus()})()

    @asynccontextmanager
    async def _stub_with_ib_connection(*args, **kwargs):
        yield _StatusStateIb()

    monkeypatch.setattr(healthcheck, "with_ib_connection", _stub_with_ib_connection)

    async def _run():
        out = await healthcheck.run_ib_healthcheck("127.0.0.1", 8888)
        assert out["whatif_mnq_ok"] is True
        assert out["whatif_mnq_state_source"] == "result.orderStatus.orderState"
        assert out["whatif_stock_ok"] is True
        assert out["whatif_stock_state_source"] == "result.orderStatus.orderState"

    import asyncio

    asyncio.run(_run())
