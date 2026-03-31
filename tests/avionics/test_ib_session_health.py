from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from avionics.ib import session

pytest.importorskip("ib_async")


class _OkIb:
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
        return object()


def test_run_ib_healthcheck_ok(monkeypatch):
    @asynccontextmanager
    async def _stub_with_ib_connection(*args, **kwargs):
        yield _OkIb()

    monkeypatch.setattr(session, "with_ib_connection", _stub_with_ib_connection)

    async def _run():
        out = await session.run_ib_healthcheck("127.0.0.1", 8888)
        assert out["ib_connected"] is True
        assert out["historical_nq_ok"] is True
        assert out["historical_nq_bars"] == 2
        assert out["overall"] in ("OK", "DEGRADED")

    import asyncio

    asyncio.run(_run())


def test_run_ib_healthcheck_connect_fail(monkeypatch):
    @asynccontextmanager
    async def _stub_with_ib_connection(*args, **kwargs):
        raise RuntimeError("connect fail")
        yield

    monkeypatch.setattr(session, "with_ib_connection", _stub_with_ib_connection)

    async def _run():
        out = await session.run_ib_healthcheck("127.0.0.1", 8888)
        assert out["ib_connected"] is False
        assert out["overall"] == "FAIL"

    import asyncio

    asyncio.run(_run())
