"""
Cockpit（管制層）：司令。FlightController（3層）が返すスロットルモードを遷移・配布する。

役割: 「どのプロトコルを選ぶか」を決定し、対応する Protocol（作戦）を起動する。
Manual モード時は FlightControllerSignal を受信すると Telegram 承認を待ち、承認後に dispatch_protocol を実行する。
SemiAuto モード時は Emergency（Lv2）は即時実行、Cruise（Lv1）は承認待ち。
定義書「2.コックピット」「4-2 OS構造」「Phase 5 Telegram統合」参照。
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import date
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

from avionics.data.flight_controller_signal import FlightControllerSignal
from avionics.data.data_source import DataSource
from avionics.data.signals import AltitudeRegime
from avionics.flight_controller import FlightController
from protocols.emergency_protocol import EmergencyProtocol

from .mode import BOOST, CRUISE, EMERGENCY, ApprovalMode, ModeType

if TYPE_CHECKING:
    from engines.engine import Engine

APPROVAL_TIMEOUT_SEC = 600


def _mode_severity(mode: ModeType) -> int:
    """Emergency=2, Cruise=1, Boost=0。最悪モード比較用。"""
    return 2 if mode == EMERGENCY else (1 if mode == CRUISE else 0)


def _split_actual_by_target(
    symbol_actual: Dict[str, float],
    target_futures_by_part: Dict[str, float],
) -> Dict[str, Dict[str, float]]:
    """
    銘柄の実ポジション（future/k1/k2）を target_futures 比率で Part に配賦する。
    future レッグは MNQ/MGC 相当枚数（IBRawFetcher.fetch_position_legs と揃える）。
    """
    from engines.blueprint import PART_NAMES

    missing = [p for p in PART_NAMES if p not in target_futures_by_part]
    if missing:
        raise ValueError(f"target_futures missing part rows: {missing}")
    weights = {p: abs(float(target_futures_by_part[p])) for p in PART_NAMES}
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("target_futures total weight must be > 0")
    out: Dict[str, Dict[str, float]] = {}
    for part in PART_NAMES:
        share = weights[part] / total_weight
        out[part] = {
            "future": float(symbol_actual["future"]) * share,
            "k1": float(symbol_actual["k1"]) * share,
            "k2": float(symbol_actual["k2"]) * share,
        }
    return out


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
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """
        Cockpit を初期化する。

        :param fc: 計器層（実行レベル・スロットルモード算出）。レイヤー混合を避けるため必須注入
        :param engines: 外で生成したエンジンのリスト（NQ/GC 等）。空リストで生成し後から extend しても可
        :param initial_mode: 初期スロットルモード（必須。大元で指定）
        :param approval_mode: 承認ゲート。Manual/SemiAuto/Auto。Phase 5 用
        :param on_emergency_entered: Emergency 遷移前に呼ぶ async コールバック（ログ・EICAS 等）。定義書「3-2 EICAS」連携用
        :param telegram: Phase 5 用。未注入時は request_telegram_approval は no-op、タイムアウト時も送信しない
        :param conn: SQLite 接続。指定時は state/mode を DB から読み書きする
        定義書「4-2」「Phase 5」参照。
        """
        self.fc: FlightController = fc
        self.engines: List["Engine"] = list(engines)
        self._on_emergency_entered: Optional[Callable[[], Awaitable[None]]] = on_emergency_entered
        self._current_mode: ModeType = initial_mode
        self._approval_mode: ApprovalMode = approval_mode
        self._execution_lock: bool = False
        self._conn: Optional[sqlite3.Connection] = conn
        self._approval_event: asyncio.Event = asyncio.Event()
        self._approval_wait_id: int = 0
        self._pending_approval_signal: Optional[FlightControllerSignal] = None
        self._telegram: Optional[Any] = telegram

        if conn is not None:
            self._restore_from_db(conn)

    def _restore_from_db(self, conn: sqlite3.Connection) -> None:
        """DB の state / mode テーブルから起動時の状態を復元する。"""
        from store.mode import read_mode
        mode_row = read_mode(conn)

        ap = mode_row["ap_mode"]
        if ap in ("Manual", "SemiAuto", "Auto"):
            self._approval_mode = ap  # type: ignore[assignment]
        self._execution_lock = bool(mode_row["execution_lock"])

    def _persist_approval_mode(self) -> None:
        """ap_mode を DB に書き込む。"""
        if self._conn is None:
            return
        from store.mode import update_ap_mode

        update_ap_mode(self._conn, self._approval_mode)

    @property
    def current_mode(self) -> ModeType:
        """現在のスロットルモード（Boost / Cruise / Emergency）。"""
        return self._current_mode

    @property
    def approval_mode(self) -> ApprovalMode:
        """承認ゲート。Manual/SemiAuto/Auto。"""
        return self._approval_mode

    @approval_mode.setter
    def approval_mode(self, value: ApprovalMode) -> None:
        self._approval_mode = value
        self._persist_approval_mode()

    @property
    def execution_lock(self) -> bool:
        """執行ロック。True のとき発注・プロトコル執行を一時停止する。"""
        return self._execution_lock

    @execution_lock.setter
    def execution_lock(self, value: bool) -> None:
        self._execution_lock = value
        if self._conn is not None:
            from store.mode import update_execution_lock
            update_execution_lock(self._conn, value)

    def _should_auto_dispatch(self, signal: FlightControllerSignal) -> bool:
        """承認ゲートのロジック。True なら即時 dispatch_protocol、False なら承認待ち。"""
        if signal.any_critical:
            return True
        if self._approval_mode == "Auto":
            return True
        if self._approval_mode == "SemiAuto" and signal.worst_throttle_level >= 2:
            return True
        return False

    def approval_granted(self) -> None:
        """
        Telegram の「実行」ボタン押下時に外部から呼ぶ。
        approval_event.set() により、承認待ち中の on_flight_controller_signal が再開する。Phase 5 用。
        """
        self._approval_event.set()

    async def on_flight_controller_signal(self, signal: FlightControllerSignal) -> None:
        """
        FlightController からの信号を受信し、承認ゲートを経てプロトコルを起動する。
        Auto / SemiAuto(Emergency) / any_critical の場合は即時 dispatch_protocol。
        Manual / SemiAuto(Cruise) の場合は Telegram 承認待ち。
        承認待ち中に新たな信号が届いた場合は既存の待機をスーパーセードし、古い待機は dispatch しない。
        定義書「Phase 5 検知と保留 / 承認待ち / プロトコル起動」参照。
        """
        if self._should_auto_dispatch(signal):
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
                f"[承認待ち] {signal.summary_reason} (throttle={signal.worst_throttle_level})"
            )

    async def dispatch_protocol(self, signal: FlightControllerSignal) -> None:
        """
        信号に応じたプロトコル（Ignition / Cutoff / Emergency 等）をロードして実行する。
        throttle_level=2 の場合は EmergencyProtocol。それ以外はモード遷移のみ全エンジンへ apply_mode。
        execution_lock が ON の場合はプロトコル実行をスキップし、モード記録のみ行う。
        定義書「Phase 5 プロトコル起動」参照。
        """
        target_mode = self._level_to_mode(signal.worst_throttle_level)
        if not self._execution_lock:
            if target_mode == EMERGENCY:
                if self._on_emergency_entered is not None:
                    await self._on_emergency_entered()
                protocol = EmergencyProtocol(self.engines)
                await protocol.execute()
        self._current_mode = target_mode
        if not self._execution_lock:
            for engine in self.engines:
                await engine.apply_mode(self._current_mode)

    async def pulse(
        self,
        data_source: DataSource,
        as_of: date,
        symbols: List[str],
        *,
        altitude: Optional[AltitudeRegime] = None,
    ) -> None:
        """
        管制サイクル。DataSource から FC.refresh（Raw 取得 → bundle → 因子更新）を行い、
        三層方式で銘柄ごとにスロットルモード取得 → 遷移 → 全エンジンへ指令。
        conn があるときは DB から altitude を読み、refresh(..., altitude=...) を呼ぶ。
        conn がないときはテスト用に altitude= のみ許可。
        定義書「0-4」「4-2」「0-1-Ⅲ」参照。
        """
        if self._conn is not None:
            from store.state import read_altitude_regime, read_target_futures

            db_altitude = read_altitude_regime(self._conn)
            await self.fc.refresh(data_source, as_of, symbols, altitude=db_altitude)
            if not hasattr(data_source, "fetch_position_legs"):
                raise ValueError(
                    "Cockpit.pulse requires data_source.fetch_position_legs(...) when conn is provided"
                )
            fetch_position_legs = getattr(data_source, "fetch_position_legs")
            positions_by_symbol = await fetch_position_legs(symbols)
            target_futures_by_symbol = read_target_futures(self._conn)
        elif altitude is not None:
            await self.fc.refresh(data_source, as_of, symbols, altitude=altitude)
            positions_by_symbol = {}
            target_futures_by_symbol = {}
        else:
            raise ValueError(
                "Cockpit.pulse requires conn=... or altitude=... (tests only)"
            )
        signal = await self.fc.get_flight_controller_signal()
        worst_mode: ModeType = BOOST
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
        if any_emergency and not self._execution_lock:
            if self._on_emergency_entered is not None:
                await self._on_emergency_entered()
            else:
                protocol = EmergencyProtocol(self.engines)
                await protocol.execute()
        if worst_mode != self._current_mode:
            self._current_mode = worst_mode
        if not self._execution_lock:
            for engine, target_mode in engine_modes:
                if self._conn is not None:
                    symbol_actual = positions_by_symbol.get(engine.symbol_type)
                    if symbol_actual is None:
                        raise ValueError(
                            f"IB positions missing symbol: {engine.symbol_type}"
                        )
                    sym = engine.symbol_type
                    tf_part = target_futures_by_symbol[sym]
                    actual_by_part = _split_actual_by_target(symbol_actual, tf_part)
                    await engine.apply_mode(
                        target_mode,
                        actual_by_part=actual_by_part,
                        target_futures_by_part=tf_part,
                    )
                else:
                    await engine.apply_mode(target_mode)

    def _level_to_mode(self, level: int) -> ModeType:
        """実行レベル 0/1/2 をスロットルモード（Boost/Cruise/Emergency）に変換。定義書 4-2 対応表。"""
        if level >= 2:
            return EMERGENCY
        if level == 1:
            return CRUISE
        return BOOST

    def force_mode(self, mode: ModeType) -> None:
        """テスト用: 指定モードへ強制遷移。"""
        self._current_mode = mode
