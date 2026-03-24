"""
C因子（Credit Stress）：NQ系専用。信用収縮の検知。

HYG/LQD の below_sma20 または前日比で C0/C2 を判定する。C1廃止。二択のみ。
悪化は即時、復帰は confirm_days 連続確認。
定義書「4-2-1-3 C因子（Credit Stress：NQ系）」参照。
"""

from __future__ import annotations

from typing import Any, Optional, TYPE_CHECKING

from .base_factor import BaseFactor, LevelType

if TYPE_CHECKING:
    from avionics.data.signals import LiquiditySignals, SignalBundle


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

    def _row_satisfies_c0(self, row: tuple, c2_th: float) -> bool:
        """1日分 (date, below_sma20, daily_change) が C0 を満たすか。"""
        return len(row) >= 3 and not row[1] and row[2] > c2_th

    def _count_recovery_satisfied_days(
        self,
        daily_history_credit: tuple,
    ) -> int:
        """基準日から遡り、C0 条件（not below_sma20 and daily_change > C2）を満たす連続日数を返す。(date, below_sma20, daily_change)。"""
        th = self.thresholds
        c2_th = float(th["daily_change_C2"])
        count = 0
        for row in daily_history_credit:
            if self._row_satisfies_c0(row, c2_th):
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
        th = self.thresholds
        c2_th = float(th["daily_change_C2"])
        by_date: dict = {}
        for row in daily_history_hyg:
            if len(row) >= 1:
                d = row[0]
                by_date[d] = [self._row_satisfies_c0(row, c2_th), False]
        for row in daily_history_lqd:
            if len(row) >= 1:
                d = row[0]
                if d in by_date:
                    by_date[d][1] = self._row_satisfies_c0(row, c2_th)
                else:
                    by_date[d] = [False, self._row_satisfies_c0(row, c2_th)]
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

    def get_recovery_progress_from_bundle(self, symbol: str, bundle: Any) -> Optional[tuple[int, int]]:
        """bundle の liquidity_credit（と liquidity_credit_lqd）から復帰 x/N を算出。定義書: HYG AND LQD とも維持。"""
        credit_hyg = getattr(bundle, "liquidity_credit", None)
        if not credit_hyg:
            return None
        daily_hyg = getattr(credit_hyg, "daily_history_credit", ()) or ()
        credit_lqd = getattr(bundle, "liquidity_credit_lqd", None)
        if credit_lqd is not None:
            daily_lqd = getattr(credit_lqd, "daily_history_credit", ()) or ()
            count = self._count_recovery_satisfied_days_two_symbols(daily_hyg, daily_lqd)
        else:
            count = self._count_recovery_satisfied_days(daily_hyg) if daily_hyg else 0
        confirm = int(self.thresholds["confirm_days"])
        return (min(count, confirm), confirm)

    async def apply_signal_bundle(
        self, symbol: Optional[str], bundle: "SignalBundle"
    ) -> None:
        lc = getattr(bundle, "liquidity_credit", None)
        if lc is not None:
            lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
            await self.update_from_signals(
                altitude=lc.altitude,
                below_sma20=lc.below_sma20 is True,
                daily_change=lc.daily_change if lc.daily_change is not None else 0.0,
                daily_history_credit=getattr(lc, "daily_history_credit", ()),
                below_sma20_lqd=lc_lqd.below_sma20 if lc_lqd is not None else None,
                daily_change_lqd=lc_lqd.daily_change if lc_lqd and lc_lqd.daily_change is not None else None,
                daily_history_credit_lqd=getattr(lc_lqd, "daily_history_credit", ()) if lc_lqd else (),
            )

    async def update_from_signals(
        self,
        altitude: str,
        below_sma20: bool,
        daily_change: float,
        daily_history_credit: tuple = (),
        *,
        below_sma20_lqd: Optional[bool] = None,
        daily_change_lqd: Optional[float] = None,
        daily_history_credit_lqd: tuple = (),
    ) -> LevelType:
        """
        事前計算済みシグナル（LiquiditySignals 相当）から C レベルを更新する。

        定義書 4-2-1-3: C2発動は HYG or LQD のいずれかが SMA20下 OR 前日比≦閾値。C0復帰は HYG AND LQD とも 2 日維持。
        LQD 未渡しの場合は HYG のみで判定（後方互換）。
        """
        th = self.thresholds
        daily_change_C2 = float(th["daily_change_C2"])
        confirm_days = int(th["confirm_days"])

        c2_hyg = below_sma20 or (daily_change <= daily_change_C2)
        use_lqd = below_sma20_lqd is not None and daily_change_lqd is not None
        if use_lqd:
            c2_lqd = below_sma20_lqd or (daily_change_lqd <= daily_change_C2)
            c2_triggered = c2_hyg or c2_lqd
            c0_condition_met = not c2_hyg and not c2_lqd
            recovery_satisfied = self._count_recovery_satisfied_days_two_symbols(
                daily_history_credit, daily_history_credit_lqd
            ) if (daily_history_credit or daily_history_credit_lqd) else 0
        else:
            c2_triggered = c2_hyg
            c0_condition_met = not c2_hyg
            recovery_satisfied = (
                self._count_recovery_satisfied_days(daily_history_credit)
                if daily_history_credit
                else 0
            )

        if c2_triggered:
            self.downgrade(2)
            return 2

        if self.level == 2:
            await self.upgrade(
                0,
                confirm_days,
                recovery_confirm_satisfied_days=recovery_satisfied,
                condition_met=c0_condition_met,
            )
        return self.level
