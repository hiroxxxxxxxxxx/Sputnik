"""
Cockpit（管制層）：司令。FlightController（3層）が返すスロットルモードを遷移・配布する。

役割: 「どのプロトコルを選ぶか」を決定し、対応する Protocol（作戦）を起動する。
Manual モード時は FlightControllerSignal を受信すると Telegram 承認を待ち、承認後に dispatch_protocol を実行する。
定義書「2.コックピット」「4-2 OS構造」「Phase 5 Telegram統合」参照。
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING, Any, Awaitable, Callable, List, Literal, Optional

from avionics.data.fc_signals import FlightControllerSignal
from avionics.data.source import DataSource
from avionics.flight_controller import FlightController
from reports.format_fc_signal import build_summary_reason
from protocols.emergency_protocol import EmergencyProtocol

from .mode import BOOST, CRUISE, EMERGENCY, ModeType

if TYPE_CHECKING:
    from engines.engine import Engine

ApprovalMode = Literal["Manual", "Auto"]
APPROVAL_TIMEOUT_SEC = 600


def _mode_severity(mode: ModeType) -> int:
    """Emergency=2, Cruise=1, Boost=0。最悪モード比較用。"""
    return 2 if mode == EMERGENCY else (1 if mode == CRUISE else 0)


class Cockpit:
    """
    管制層：FlightController が返すスロットルモードを遷移・配布する。判定は FlightController に委譲。

    エンジンは外からリストで注入する。get_flight_controller_signal の throttle_level からスロットルモードを導き、
    遷移・プロトコル・全エンジンへの apply_mode に専念する。定義書「4-2」参照。
    """

    def __init__(
        self,
        fc: FlightController,
        engines: List["Engine"],
        *,
        initial_mode: ModeType,
        approval_mode: ApprovalMode = "Manual",
        on_emergency_entered: Optional[Callable[[], Awaitable[None]]] = None,
        telegram: Optional[Any] = None,
    ) -> None:
        """
        FlightController を初期化する。

        :param fc: 計器層（実行レベル・スロットルモード算出）。レイヤー混合を避けるため必須注入
        :param engines: 外で生成したエンジンのリスト（NQ/GC 等）。空リストで生成し後から extend しても可
        :param initial_mode: 初期スロットルモード（必須。大元で指定）
        :param approval_mode: 「Manual」で Telegram 承認待ち、「Auto」で即時プロトコル発火。Phase 5 用
        :param on_emergency_entered: Emergency 遷移前に呼ぶ async コールバック（ログ・EICAS 等）。定義書「3-2 EICAS」連携用
        :param telegram: Phase 5 用。未注入時は request_telegram_approval は no-op、タイムアウト時も送信しない
        定義書「4-2」「Phase 5」参照。
        """
        self.fc: FlightController = fc
        self.engines: List["Engine"] = list(engines)
        self._on_emergency_entered: Optional[Callable[[], Awaitable[None]]] = on_emergency_entered
        self._current_mode: ModeType = initial_mode
        self._approval_mode: ApprovalMode = approval_mode
        self._approval_event: asyncio.Event = asyncio.Event()
        self._approval_wait_id: int = 0
        """承認待ちの世代。新しい信号でスーパーセードした場合にインクリメントし、古い待機は dispatch しない。"""
        self._pending_approval_signal: Optional[FlightControllerSignal] = None
        """承認待ち中の信号。None でない間に新信号が来たらスーパーセードする。"""
        self._telegram: Optional[Any] = telegram

    @property
    def current_mode(self) -> ModeType:
        """現在のスロットルモード（Boost / Cruise / Emergency）。"""
        return self._current_mode

    @property
    def approval_mode(self) -> ApprovalMode:
        """承認ゲート。「Manual」で Telegram 承認待ち、「Auto」で即時実行。Phase 5 用。"""
        return self._approval_mode

    def approval_granted(self) -> None:
        """
        Telegram の「実行」ボタン押下時に外部から呼ぶ。
        approval_event.set() により、承認待ち中の on_flight_controller_signal が再開する。Phase 5 用。
        """
        self._approval_event.set()

    async def on_flight_controller_signal(self, signal: FlightControllerSignal) -> None:
        """
        FlightController からの信号を受信し、承認ゲートを経てプロトコルを起動する。
        is_critical または Auto の場合は即時 dispatch_protocol。Manual の場合は Telegram 承認待ち。
        承認待ち中に新たな信号が届いた場合は既存の待機をスーパーセードし、古い待機は dispatch しない。
        定義書「Phase 5 検知と保留 / 承認待ち / プロトコル起動」参照。
        """
        if signal.any_critical or self._approval_mode == "Auto":
            await self.dispatch_protocol(signal)
            return
        if self._pending_approval_signal is not None:
            self._approval_wait_id += 1
            self._approval_event.set()
            await asyncio.sleep(0)
        self._pending_approval_signal = signal
        my_id = self._approval_wait_id
        await self.request_telegram_approval(signal)
        try:
            await asyncio.wait_for(
                self._approval_event.wait(), timeout=APPROVAL_TIMEOUT_SEC
            )
            if self._approval_wait_id == my_id:
                await self.dispatch_protocol(signal)
        except asyncio.TimeoutError:
            if self._approval_wait_id == my_id and self._telegram is not None and hasattr(self._telegram, "send"):
                await self._telegram.send(
                    "承認タイムアウト。安全のため現状維持、または低速巡航へ"
                )
        finally:
            self._pending_approval_signal = None
            self._approval_event.clear()

    async def request_telegram_approval(self, signal: FlightControllerSignal) -> None:
        """
        「実行 / 却下」のインラインボタン付きメッセージを Telegram に送信する。Phase 5 のメイン実装ポイント。
        未注入 telegram の場合は no-op。Telegram Bot のコールバックで approval_granted() を呼ぶと承認完了。
        """
        if self._telegram is None:
            return
        if hasattr(self._telegram, "request_approval"):
            await self._telegram.request_approval(signal)
            return
        if hasattr(self._telegram, "send"):
            await self._telegram.send(
                f"[承認待ち] {build_summary_reason(signal)} (throttle={signal.worst_throttle_level})"
            )

    async def dispatch_protocol(self, signal: FlightControllerSignal) -> None:
        """
        信号に応じたプロトコル（Ignition / Cutoff / Emergency 等）をロードして実行する。
        throttle_level=2 の場合は EmergencyProtocol。それ以外はモード遷移のみ全エンジンへ apply_mode。
        定義書「Phase 5 プロトコル起動」参照。
        """
        target_mode: ModeType = (
            EMERGENCY
            if signal.worst_throttle_level >= 2
            else (CRUISE if signal.worst_throttle_level == 1 else BOOST)
        )
        if signal.worst_throttle_level >= 2:
            if self._on_emergency_entered is not None:
                await self._on_emergency_entered()
            protocol = EmergencyProtocol(self.engines)
            await protocol.execute()
        self._current_mode = target_mode
        for engine in self.engines:
            await engine.apply_mode(self._current_mode)

    async def pulse(self, data_source: DataSource, as_of: date, symbols: List[str]) -> None:
        """
        管制サイクル。DataSource から FC.refresh（Raw 取得 → bundle → 因子更新）を行い、
        三層方式で銘柄ごとにスロットルモード取得 → 遷移 → 全エンジンへ指令。
        判定は行わず、get_flight_controller_signal の throttle_level からスロットルモードを導き遷移・配布する。定義書「0-4」「4-2」「0-1-Ⅲ」参照。
        """
        await self.fc.refresh(data_source, as_of, symbols)
        await self._pulse_subscription()

    def _level_to_mode(self, level: int) -> ModeType:
        """実行レベル 0/1/2 をスロットルモード（Boost/Cruise/Emergency）に変換。定義書 4-2 対応表。"""
        if level >= 2:
            return EMERGENCY
        if level == 1:
            return CRUISE
        return BOOST

    async def _pulse_subscription(self) -> None:
        """pulse で refresh 済みの FC から get_flight_controller_signal で計器結論を取得し、銘柄ごとにモードに変換して遷移・配布。定義書 4-2。"""
        signal = await self.fc.get_flight_controller_signal()
        worst_mode: ModeType = BOOST  # 最小 severity から開始し、全エンジンで最悪のモードを集約
        any_emergency = False
        engine_modes: List[tuple["Engine", ModeType]] = []
        for engine in self.engines:
            if engine.symbol_type not in ("NQ", "GC"):
                continue
            level = signal.throttle_level(engine.symbol_type)
            target_mode = self._level_to_mode(level)
            engine_modes.append((engine, target_mode))
            if target_mode == EMERGENCY:
                any_emergency = True
            if _mode_severity(target_mode) > _mode_severity(worst_mode):
                worst_mode = target_mode
        if any_emergency:
            if self._on_emergency_entered is not None:
                await self._on_emergency_entered()
            else:
                protocol = EmergencyProtocol(self.engines)
                await protocol.execute()
        if worst_mode != self._current_mode:
            self._current_mode = worst_mode
        for engine, target_mode in engine_modes:
            await engine.apply_mode(target_mode)

    def force_mode(self, mode: ModeType) -> None:
        """テスト用: 指定モードへ強制遷移。"""
        self._current_mode = mode

