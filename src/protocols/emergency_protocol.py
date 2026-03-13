"""
Emergency プロトコル。他 Protocol と同様に Engine に apply_mode を依頼するだけ。

Engine が「Emergency」を目標値に翻訳し、Part はモードを知らない。定義書「6-2」「Phase 4」参照。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, List, Optional

from .base_protocol import BaseProtocol

if TYPE_CHECKING:
    from engines.engine import Engine


class EmergencyProtocol(BaseProtocol):
    """
    Emergency 時のみ実行。Protocol は Engine に apply_mode("Emergency") を依頼するだけ。
    役割分離: FlightController/Cockpit が「何か」を決め、Engine が翻訳し、Part が目標値で実行する。
    """

    def __init__(
        self,
        engines: Optional[List["Engine"]] = None,
        *,
        ib_client: Any = None,
        notifier: Any = None,
    ) -> None:
        super().__init__(engines, ib_client=ib_client, notifier=notifier)

    def get_priority(self) -> int:
        """Emergency は最優先。"""
        return 3

    async def run(self) -> None:
        """全エンジンに Emergency を適用。他 Protocol（Ignition/Cutoff）と同様に apply_mode のみ依頼。"""
        if self._engines:
            await asyncio.gather(*[e.apply_mode("Emergency") for e in self._engines])
        await self._notify_info("Emergency protocol complete")
