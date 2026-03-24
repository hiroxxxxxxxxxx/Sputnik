"""
Booster Cutoff プロトコル。加速を停止し、通常巡航に戻す。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, List, Optional

from .base_protocol import BaseProtocol

if TYPE_CHECKING:
    from engines.engine import Engine


class BoosterCutoffProtocol(BaseProtocol):
    """加速を停止し、通常巡航に戻す。制御・減速。"""

    def __init__(
        self,
        engines: Optional[List["Engine"]] = None,
        *,
        notifier: Any = None,
    ) -> None:
        super().__init__(engines, notifier=notifier)

    async def run(self) -> None:
        if self._engines:
            await asyncio.gather(*[e.apply_mode("Cruise") for e in self._engines])
        await self._notify_info("BoosterCutoff: engines applied Cruise")
