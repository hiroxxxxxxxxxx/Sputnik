from __future__ import annotations

import datetime as dt
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Optional, Deque

from transitions import Machine

if TYPE_CHECKING:
    from avionics.data.signals import AltitudeRegime, SignalBundle


LevelType = int
BufferCondition = Callable[["BaseFactor", LevelType], Awaitable[bool] | bool]


class BaseFactor:
    """
    共通因子基底クラス。

    非対称ヒステリシスを備えたレベル判定FSMを提供する。
    定義書「0-4 ヒステリシス原則」および
    「4-2-1 / 4-2-2 各因子定義」セクション参照。
    """

    def __init__(
        self,
        name: str,
        levels: list[LevelType],
        history_size: int = 64,
    ) -> None:
        """
        因子の基本状態を初期化する。

        :param name: 因子名（P/V/L/T/U/Sなど）
        :param levels: 許容される整数レベル値（例: [0, 1, 2] または [0, 2]）
        :param history_size: レベル履歴バッファの最大長

        定義書「3-1 主計器」「4-2 OS構造」参照。
        """
        if not levels:
            raise ValueError("levels must not be empty")

        self.name: str = name
        self.levels: list[LevelType] = sorted(levels)
        self.level: LevelType = self.levels[0]

        # upgrade(..., recovery_confirm_satisfied_days=None) 用のメモリ内カウンタ。
        # 量産因子では P/V/C/R/T がステートレス日数を渡し、U/S は即時復帰で upgrade 非使用。
        self._target_level: Optional[LevelType] = None
        self._confirm_counter: int = 0
        self._confirm_days_required: Optional[int] = None

        self.history: Deque[tuple[dt.datetime, LevelType]] = deque(
            maxlen=history_size
        )

        state_names = [f"level_{lv}" for lv in self.levels]
        initial_state = f"level_{self.level}"

        self._machine = Machine(
            model=self,
            states=state_names,
            initial=initial_state,
            ignore_invalid_triggers=True,
        )

    async def apply_signal_bundle(
        self,
        symbol: Optional[str],
        bundle: "SignalBundle",
        *,
        altitude: "AltitudeRegime",
    ) -> None:
        """
        Layer 2 の SignalBundle から自身の入力を取り出し、レベルを更新する。

        :param altitude: 本ティックの運用高度（DB 由来を refresh で渡す。Layer 2 データではない）。
        銘柄別因子は symbol で bundle 内の該当シグナルを参照する。
        制限因子（U/S）や global_market は symbol=None。各因子でオーバーライドする。
        定義書「4-2 情報の階層構造」参照。
        """
        raise NotImplementedError

    def record_level(self) -> None:
        """
        現在のレベルを履歴バッファに記録する。

        定義書「0-4 ヒステリシス原則」の
        「状態は瞬間値で決定しない」要件に対応。
        """
        self.history.append((dt.datetime.now(dt.timezone.utc), self.level))

    def recovery_confirm_progress(self) -> Optional[tuple[int, int]]:
        """
        復帰ヒステリシスの「x日目 / N日」。
        upgrade を recovery_confirm_satisfied_days 省略で呼ぶ場合のみ（主にテスト）。
        ステートレス因子は get_recovery_progress_from_bundle。U/S は即時復帰のため通常 None。
        """
        if self._target_level is not None and self._confirm_days_required is not None:
            return (self._confirm_counter, self._confirm_days_required)
        return None

    def get_recovery_progress_from_bundle(
        self,
        symbol: str,
        bundle: Any,
        *,
        altitude: "AltitudeRegime",
    ) -> Optional[tuple[int, int]]:
        """
        bundle から復帰 x/N をその場で算出する。ステートレス因子がオーバーライド。デフォルトは None。
        """
        return None

    def reset_confirmation(self) -> None:
        """ダウングレード時などに復帰用カウンタをクリアする。"""
        self._target_level = None
        self._confirm_counter = 0
        self._confirm_days_required = None

    def downgrade(self, new_level: LevelType) -> None:
        """
        悪化方向のレベル遷移を即時適用する。

        :param new_level: 新しいレベル（現在値以上であること）

        非対称ヒステリシスの原則に従い、
        降格は継続確認やバッファ条件なしで即時に適用する。
        定義書「0-4」「4-2-1〜4-2-2」参照。
        """
        if new_level not in self.levels:
            raise ValueError(f"invalid level {new_level} for factor {self.name}")
        if new_level < self.level:
            raise ValueError(
                f"downgrade must not decrease level "
                f"(current={self.level}, requested={new_level})"
            )

        self.level = new_level
        self.reset_confirmation()

        trigger_name = f"to_level_{new_level}"
        trigger: Optional[Callable[..., Any]] = getattr(self, trigger_name, None)
        if callable(trigger):
            trigger()

        self.record_level()

    async def upgrade(
        self,
        new_level: LevelType,
        confirm_days: int,
        *,
        recovery_confirm_satisfied_days: Optional[int] = None,
        condition_met: bool = True,
        buffer_condition: Optional[BufferCondition] = None,
    ) -> bool:
        """
        改善方向のレベル遷移を、継続確認とバッファ条件付きで適用する。

        :param recovery_confirm_satisfied_days: None なら呼び出し回数ベースの内部カウンタ（主にテスト）。
            int ならステートレス（P/R/C/T/V: 系列から数えた連続日数を渡す）。
        """
        if new_level not in self.levels:
            raise ValueError(f"invalid level {new_level} for factor {self.name}")
        if new_level > self.level:
            raise ValueError(
                f"upgrade must not increase level "
                f"(current={self.level}, requested={new_level})"
            )
        if confirm_days <= 0:
            raise ValueError("confirm_days must be positive")

        use_stateless = recovery_confirm_satisfied_days is not None
        if use_stateless:
            satisfied = recovery_confirm_satisfied_days
        else:
            if not condition_met:
                self.reset_confirmation()
                return False
            if self._target_level is None or self._target_level != new_level:
                self._target_level = new_level
                self._confirm_counter = 0
                self._confirm_days_required = confirm_days
            if buffer_condition is not None:
                result = buffer_condition(self, new_level)
                if isinstance(result, Awaitable):
                    result = await result
                if not result:
                    self.reset_confirmation()
                    return False
                self._confirm_counter += 1
            else:
                self._confirm_counter += 1
            if self._confirm_counter < confirm_days:
                return False
            self.level = new_level
            trigger_name = f"to_level_{new_level}"
            trigger: Optional[Callable[..., Any]] = getattr(self, trigger_name, None)
            if callable(trigger):
                trigger()
            self.record_level()
            self.reset_confirmation()
            return True

        if not condition_met:
            return False
        if buffer_condition is not None:
            result = buffer_condition(self, new_level)
            if isinstance(result, Awaitable):
                result = await result
            if not result:
                return False
        if satisfied < confirm_days:
            return False
        self.level = new_level
        trigger_name = f"to_level_{new_level}"
        trigger = getattr(self, trigger_name, None)
        if callable(trigger):
            trigger()
        self.record_level()
        return True

    def test_downgrade(self) -> bool:
        """
        降格ロジックが基本仕様どおりに動作するかの簡易テストを行う。

        定義書「0-4 ヒステリシス原則」参照。
        """
        if len(self.levels) < 2:
            return True

        lowest = self.levels[0]
        highest = self.levels[-1]

        self.level = lowest
        self.record_level()

        self.downgrade(highest)

        return self.level == highest

