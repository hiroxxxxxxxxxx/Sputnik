"""
C因子（Credit Stress）：NQ系専用。信用収縮の検知。

HYG/LQD の below_sma20 または前日比で C0/C2 を判定する。C1廃止。二択のみ。
悪化は即時、復帰は confirm_days 連続確認。
定義書「4-2-1-3 C因子（Credit Stress：NQ系）」参照。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, Optional, TYPE_CHECKING, Tuple

from avionics.data.signals import CreditDailyRow
from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import AltitudeRegime, SignalBundle


def _c_row_triggers_c2(
    row: CreditDailyRow,
    daily_change_C2: float,
) -> bool:
    return len(row) >= 3 and (row[1] or row[2] <= daily_change_C2)


def _c_count_recovery_two_symbols(
    daily_history_hyg: Tuple[CreditDailyRow, ...],
    daily_history_lqd: Tuple[CreditDailyRow, ...],
) -> int:
    """HYG AND LQD とも C0（newest first）。"""
    by_date: dict = {}
    for row in daily_history_hyg:
        if len(row) >= 1:
            d = row[0]
            by_date[d] = [not row[1] if len(row) >= 3 else False, False]
    for row in daily_history_lqd:
        if len(row) >= 1:
            d = row[0]
            if d in by_date:
                by_date[d][1] = not row[1] if len(row) >= 3 else False
            else:
                by_date[d] = [False, not row[1] if len(row) >= 3 else False]
    count = 0
    for row in daily_history_hyg:
        if len(row) < 1:
            break
        d = row[0]
        pair = by_date.get(d)
        if pair and pair[0] and pair[1]:
            count += 1
        else:
            break
    return count


def _c_count_recovery_one_symbol(daily_history_credit: Tuple[CreditDailyRow, ...]) -> int:
    count = 0
    for row in daily_history_credit:
        if len(row) >= 3 and not row[1]:
            count += 1
        else:
            break
    return count


def c_level_from_credit_histories(
    *,
    below_sma20_hyg: bool,
    daily_change_hyg: float,
    hyg_nf: Tuple[CreditDailyRow, ...],
    below_sma20_lqd: Optional[bool],
    daily_change_lqd: Optional[float],
    lqd_nf: Tuple[CreditDailyRow, ...],
    thresholds: dict,
) -> LevelType:
    """HYG/LQD 日次を畳み込み C レベルを決定する。"""
    th = thresholds
    daily_change_C2 = float(th["daily_change_C2"])
    confirm_days = int(th["confirm_days"])
    use_lqd = below_sma20_lqd is not None and daily_change_lqd is not None

    hyg_by: Dict[date, CreditDailyRow] = {r[0]: r for r in hyg_nf if len(r) >= 3}
    lqd_by: Dict[date, CreditDailyRow] = {
        r[0]: r for r in lqd_nf if len(r) >= 3
    }
    if not hyg_by:
        hyg_by = {
            date.min: (date.min, below_sma20_hyg, daily_change_hyg),
        }
    if use_lqd and not lqd_by:
        lqd_by = {
            date.min: (
                date.min,
                below_sma20_lqd if below_sma20_lqd is not None else False,
                float(daily_change_lqd),
            ),
        }

    if use_lqd:
        dates = sorted(set(hyg_by) & set(lqd_by))
    else:
        dates = sorted(hyg_by.keys())

    level: LevelType = 0
    for i, d in enumerate(dates):
        if use_lqd:
            hr = hyg_by[d]
            lr = lqd_by[d]
            c2_h = _c_row_triggers_c2(hr, daily_change_C2)
            c2_l = _c_row_triggers_c2(lr, daily_change_C2)
            c2 = c2_h or c2_l
            c0_met = not c2_h and not c2_l
            prefix_hyg = tuple(hyg_by[x] for x in reversed(dates[: i + 1]))
            prefix_lqd = tuple(lqd_by[x] for x in reversed(dates[: i + 1]))
            recovery = _c_count_recovery_two_symbols(prefix_hyg, prefix_lqd)
        else:
            hr = hyg_by[d]
            c2 = _c_row_triggers_c2(hr, daily_change_C2)
            c0_met = not c2
            prefix_hyg = tuple(hyg_by[x] for x in reversed(dates[: i + 1]))
            recovery = _c_count_recovery_one_symbol(prefix_hyg)

        if c2:
            level = 2
            continue
        if level == 2 and c0_met and recovery >= confirm_days:
            level = 0
    return level


class CFactor(BaseFactor):
    """
    C因子（Credit Stress）：NQ系専用。

    C2発動（即）: SMA20を下回る OR 前日比が閾値以下。
    C0復帰（2日確認）: SMA20以上を維持。
    定義書「4-2-1-3」「0-4」参照。
    """

    def __init__(
        self,
        name: str,
        thresholds: dict,
        history_size: int = 64,
    ) -> None:
        """
        C因子を初期化する。

        :param name: 表示用ラベル（例: "C"）。
        :param thresholds: しきい値辞書（daily_change_C2, confirm_days）。factors_config.get_c_thresholds で注入。
        :param history_size: レベル履歴バッファ長
        定義書「4-2-1-3 C因子」参照。
        """
        self.thresholds: dict = dict(thresholds)
        super().__init__(name=name, levels=[0, 2], history_size=history_size)

    def _row_satisfies_c0(self, row: tuple) -> bool:
        """1日分 (date, below_sma20, daily_change) が C0 を満たすか（SPEC準拠: SMA20以上のみ）。"""
        return len(row) >= 3 and not row[1]

    def _count_recovery_satisfied_days(
        self,
        daily_history_credit: tuple,
    ) -> int:
        """基準日から遡り、C0 条件（not below_sma20）を満たす連続日数を返す。(date, below_sma20, daily_change)。"""
        count = 0
        for row in daily_history_credit:
            if self._row_satisfies_c0(row):
                count += 1
            else:
                break
        return count

    def _count_recovery_satisfied_days_two_symbols(
        self,
        daily_history_hyg: tuple,
        daily_history_lqd: tuple,
    ) -> int:
        """HYG AND LQD とも C0 を満たす連続日数（newest first）。日付で揃えて両方満たす日のみカウント。"""
        by_date: dict = {}
        for row in daily_history_hyg:
            if len(row) >= 1:
                d = row[0]
                by_date[d] = [self._row_satisfies_c0(row), False]
        for row in daily_history_lqd:
            if len(row) >= 1:
                d = row[0]
                if d in by_date:
                    by_date[d][1] = self._row_satisfies_c0(row)
                else:
                    by_date[d] = [False, self._row_satisfies_c0(row)]
        count = 0
        for row in daily_history_hyg:
            if len(row) < 1:
                break
            d = row[0]
            pair = by_date.get(d)
            if pair and pair[0] and pair[1]:
                count += 1
            else:
                break
        return count

    def get_recovery_progress_from_bundle(
        self,
        symbol: str,
        bundle: "SignalBundle",
        *,
        altitude: "AltitudeRegime",
    ) -> Optional[tuple[int, int]]:
        """bundle の liquidity_credit_hyg（と liquidity_credit_lqd）から復帰 x/N を算出。定義書: HYG AND LQD とも維持。"""
        credit_hyg = bundle.liquidity_credit_hyg
        credit_lqd = bundle.liquidity_credit_lqd
        daily_hyg = credit_hyg.daily_history_credit
        daily_lqd = credit_lqd.daily_history_credit
        count = self._count_recovery_satisfied_days_two_symbols(daily_hyg, daily_lqd)
        confirm = int(self.thresholds["confirm_days"])
        return (min(count, confirm), confirm)

    async def apply_signal_bundle(
        self,
        symbol: Optional[str],
        bundle: "SignalBundle",
        *,
        altitude: "AltitudeRegime",
    ) -> None:
        lc = bundle.liquidity_credit_hyg
        lc_lqd = bundle.liquidity_credit_lqd
        if lc.below_sma20 is None or lc.daily_change is None:
            raise ValueError("CFactor requires HYG credit signals (below_sma20, daily_change)")
        if lc_lqd.below_sma20 is None or lc_lqd.daily_change is None:
            raise ValueError("CFactor requires LQD credit signals (below_sma20, daily_change)")
        level = c_level_from_credit_histories(
            below_sma20_hyg=lc.below_sma20,
            daily_change_hyg=lc.daily_change,
            hyg_nf=lc.daily_history_credit,
            below_sma20_lqd=lc_lqd.below_sma20,
            daily_change_lqd=lc_lqd.daily_change,
            lqd_nf=lc_lqd.daily_history_credit,
            thresholds=self.thresholds,
        )
        self.assign_level_from_computation(level)

    async def update_from_signals(
        self,
        below_sma20: bool,
        daily_change: float,
        daily_history_credit: tuple = (),
        *,
        below_sma20_lqd: Optional[bool] = None,
        daily_change_lqd: Optional[float] = None,
        daily_history_credit_lqd: tuple = (),
    ) -> LevelType:
        """
        事前計算済みシグナルから C レベルを更新する（テスト用）。
        """
        level = c_level_from_credit_histories(
            below_sma20_hyg=below_sma20,
            daily_change_hyg=daily_change,
            hyg_nf=tuple(daily_history_credit),
            below_sma20_lqd=below_sma20_lqd,
            daily_change_lqd=daily_change_lqd,
            lqd_nf=tuple(daily_history_credit_lqd),
            thresholds=self.thresholds,
        )
        self.assign_level_from_computation(level)
        return level
