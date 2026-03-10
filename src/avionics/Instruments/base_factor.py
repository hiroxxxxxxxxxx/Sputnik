from __future__ import annotations

import datetime as dt
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any, Optional, Deque

import ib_async  # noqa: F401
from transitions import Machine


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

    async def update(self) -> None:
        """
        最新データを取得して内部状態を更新する。

        具体的なデータソース・ロジックは各因子クラスで実装する。
        定義書「3-1 PFD（主計器）」参照。
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
        復帰ヒステリシスの「x日目 / N日」を返す。復帰確認中でないときは None。

        :return: (現在の連続確認日数, 必要日数) または None
        """
        if self._target_level is None or self._confirm_days_required is None:
            return None
        return (self._confirm_counter, self._confirm_days_required)

    def reset_confirmation(self) -> None:
        """
        昇格判定用の内部カウンタとターゲットをリセットする。

        新しいターゲットレベルを評価する前や、
        ダウングレード発生時に呼び出すことを想定。
        """
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
        condition_met: bool = True,
        buffer_condition: Optional[BufferCondition] = None,
    ) -> bool:
        """
        改善方向のレベル遷移を、継続確認とバッファ条件付きで適用する。

        :param new_level: 新しいレベル（現在値以下であること）
        :param confirm_days: 必要とする「条件を満たした日」の連続日数
        :param condition_met: 当日の入力が昇格条件を満たしているかどうか。
            False の場合はカウンタをリセットし、昇格は行わない。
        :param buffer_condition: 追加バッファ条件（オプション）。
            シグネチャ: async or sync (factor, new_level) -> bool。
            連続確認の各日において True を返す必要がある。
        :return: 昇格が確定して実際にレベルが変更された場合 True

        非対称ヒステリシスの原則に従い、
        昇格には十分な継続期間と余裕（バッファ）を要求する。
        定義書「0-4」「4-2-1〜4-2-2」参照。
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

        # 当日の入力が昇格条件を満たしていない場合は連続性が切れる
        if not condition_met:
            self.reset_confirmation()
            return False

        # ターゲットレベルが変わった場合は連続カウンタをリセット
        if self._target_level is None or self._target_level != new_level:
            self._target_level = new_level
            self._confirm_counter = 0
            self._confirm_days_required = confirm_days

        # バッファ条件がある場合は本日分が満たされているかを先に確認
        if buffer_condition is not None:
            result = buffer_condition(self, new_level)
            if isinstance(result, Awaitable):
                result = await result
            if not result:
                # 1日でもバッファ条件を満たさなければ連続性が切れる
                self.reset_confirmation()
                return False

        # 条件＋バッファ条件を満たした日としてカウント
        self._confirm_counter += 1

        if self._confirm_counter < confirm_days:
            return False

        # 連続日数条件を満たしたので昇格を適用
        self.level = new_level

        trigger_name = f"to_level_{new_level}"
        trigger: Optional[Callable[..., Any]] = getattr(self, trigger_name, None)
        if callable(trigger):
            trigger()

        self.record_level()
        self.reset_confirmation()
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

