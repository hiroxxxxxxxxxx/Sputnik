"""
Booster Ignition プロトコル。全エンジンに Boost を適用。docs/spec/ARCHITECTURE.md 参照。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, List, Optional

from .base_protocol import BaseProtocol
if TYPE_CHECKING:
    from engines.engine import Engine

class BoosterIgnitionProtocol(BaseProtocol):
    """加速モードへ移行。全エンジンに apply_mode(\"Boost\") を並列適用。"""

    def __init__(
        self,
        engines: Optional[List["Engine"]] = None,
        *,
        ib_client: Any = None,
        notifier: Any = None,
    ) -> None:
        super().__init__(engines, ib_client=ib_client, notifier=notifier)

    def get_priority(self) -> int:
        return 0
    async def run(self) -> None:
        if self._engines:
            await asyncio.gather(*[e.apply_mode("Boost") for e in self._engines])
        await self._notify_info("BoosterIgnition: engines applied Boost")
