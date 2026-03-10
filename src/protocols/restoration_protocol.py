"""
Restoration プロトコル。異常事態から通常（Level 0/1）へ復旧する手順。

Emergency 解除後、慎重に再構築する際に FlightController から起動。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, List, Optional

from .base_protocol import BaseProtocol

if TYPE_CHECKING:
    from engines.engine import Engine


class RestorationProtocol(BaseProtocol):
    """
    異常事態から通常へ復旧するプロトコル。
    執行の性格: 慎重・再構築。ARCHITECTURE.md 参照。
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
        return 2

    async def run(self) -> None:
        """復旧シーケンス。全エンジンに Cruise を並列適用。"""
        if self._engines:
            await asyncio.gather(*[e.apply_mode("Cruise") for e in self._engines])
        await self._notify_info("Restoration: engines applied Cruise")
