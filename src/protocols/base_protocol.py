"""
BaseProtocol：執行の安全装置と共通の作法を担う基底クラス。

個別の執行ロジックは子クラスの run() に記述し、本クラスは事前・事後チェック、
タイムアウト・リトライ、ロギングの枠組みを提供する。docs/spec/ARCHITECTURE.md 参照。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from engines.engine import Engine


class BaseProtocol(ABC):
    """
    プロトコル基底クラス。execute() で事前検証 → run() → 事後報告の流れを保証する。

    :param ib_client: IB クライアント（ib_async 等）。未注入時は検証・発注はスキップ可能。
    :param notifier: 通知用（Telegram 等）。未注入時は report は no-op。
    """

    def __init__(
        self,
        engines: Optional[List["Engine"]] = None,
        *,
        ib_client: Any = None,
        notifier: Any = None,
    ) -> None:
        self._engines: List["Engine"] = list(engines) if engines else []
        self._ib = ib_client
        self._notifier = notifier

    @property
    def engines(self) -> List["Engine"]:
        """対象エンジンリスト。"""
        return self._engines

    async def execute(self) -> None:
        """
        共通フロー: 事前検証 → run() → 事後報告。
        子クラスは run() のみ実装すればよい。
        """
        if not await self.validate_margin():
            if self._notifier is not None and hasattr(self._notifier, "alert"):
                await self._notifier.alert("Margin Check Failed!")
            return
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

    def get_priority(self) -> int:
        """
        複数プロトコルが衝突しそうな場合の優先度。大きいほど優先。
        Emergency=3, Restoration=2, BoosterCutoff=1, BoosterIgnition=0 等。
        """
        return 0

    async def validate_margin(self) -> bool:
        """
        実行前の証拠金検証（価格-10%/IV+10% 等のストレス下で Engine に問い合わせ）。
        デフォルトは True。子クラスまたは DI で上書き。
        """
        return True

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
