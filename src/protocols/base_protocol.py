"""
BaseProtocol：執行の安全装置と共通の作法を担う基底クラス。

個別の執行ロジックは子クラスの run() に記述し、本クラスは事前・事後チェック、
ロギングの枠組みを提供する。docs/spec/ARCHITECTURE.md 参照。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from engines.engine import Engine


class BaseProtocol(ABC):
    """
    プロトコル基底クラス。execute() で run() → 事後報告の流れを保証する。

    :param notifier: 通知用（Telegram 等）。未注入時は report は no-op。
    """

    def __init__(
        self,
        engines: Optional[List["Engine"]] = None,
        *,
        notifier: Any = None,
    ) -> None:
        self._engines: List["Engine"] = list(engines) if engines else []
        self._notifier = notifier

    @property
    def engines(self) -> List["Engine"]:
        """対象エンジンリスト。"""
        return self._engines

    async def execute(self) -> None:
        """
        共通フロー: run() → 事後報告。
        子クラスは run() のみ実装すればよい。
        """
        try:
            await self.run()
        except Exception as e:
            await self.handle_error(e)
            raise
        await self.report_completion()

    @abstractmethod
    async def run(self) -> None:
        """プロトコルのメインシーケンス。子クラスで実装。"""
        ...

    async def handle_error(self, error: Exception) -> None:
        """run() 内の例外を共通処理。未注入 notifier の場合は no-op。"""
        if self._notifier is not None and hasattr(self._notifier, "alert"):
            await self._notifier.alert(f"Protocol error: {error!s}")

    async def report_completion(self) -> None:
        """執行完了の報告・ログ。未注入 notifier の場合は no-op。"""
        if self._notifier is not None and hasattr(self._notifier, "report"):
            await self._notifier.report(self.__class__.__name__, "completed")

    async def _notify_info(self, message: str) -> None:
        """
        ステップ実況用。notifier に info があれば送信。Telegram 等へのリアルタイム通知用。
        定義書「Phase 5 進行報告」参照。
        """
        if self._notifier is not None and hasattr(self._notifier, "info"):
            await self._notifier.info(message)
