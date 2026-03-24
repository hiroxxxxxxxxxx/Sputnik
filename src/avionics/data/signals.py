"""
Data: Layer 2 の型定義のみ（PriceSignals, SignalBundle 等）。

計算ロジックは process.layer2.compute にあり、ここには型だけを置く。
定義書「4-2 情報の階層構造」「4-2-2 SCL トレンド定義」参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional, Tuple

TrendType = Literal["up", "down", "flat"]
AltitudeRegime = Literal["high_mid", "low"]

# 復帰確認用。1日分の価格シグナル (date, daily_change, cum5_change, downside_gap, trend, cum2_change)。newest first。
PriceDailyRow = Tuple[date, float, float, float, TrendType, Optional[float]]

# 復帰確認用。1日分 (date, below_sma20, daily_change)。newest first。
CreditDailyRow = Tuple[date, bool, float]
# 復帰確認用。1日分 (date, tip_drawdown_from_high)。newest first。
TipDailyRow = Tuple[date, float]


@dataclass(frozen=True)
class PriceSignals:
    """
    P 因子・T 因子用。定義書 Layer 2：トレンド・日次変動率・累積変動率・Downside Gap。
    P因子・同期制御層が共通参照する共用シグナル（定義書 4-2-2）。
    """
    symbol: str
    trend: TrendType
    daily_change: float
    cum5_change: float
    cum2_change: Optional[float]
    downside_gap: float
    last_close: float = 0.0
    daily_history: Tuple[PriceDailyRow, ...] = ()


@dataclass(frozen=True)
class VolatilitySignal:
    """V 因子用。指数値と高度レジーム。"""
    index_value: float
    altitude: AltitudeRegime
    v1_to_v0_knock_in_ok: Optional[bool] = None
    is_intraday_condition_met: bool = False
    recovery_confirm_satisfied_days_v1_off: int = 0
    recovery_confirm_satisfied_days_v2_off: int = 0


@dataclass(frozen=True)
class LiquiditySignals:
    """C 因子（credit）・R 因子（tip）用。"""
    altitude: AltitudeRegime
    below_sma20: Optional[bool] = None
    daily_change: Optional[float] = None
    tip_drawdown_from_high: Optional[float] = None
    daily_history_credit: Tuple[CreditDailyRow, ...] = ()
    daily_history_tip: Tuple[TipDailyRow, ...] = ()


@dataclass(frozen=True)
class CapitalSignals:
    """U 因子・S 因子用。証拠金使用率と SPAN 乖離率。"""
    mm_over_nlv: float
    span_ratio: float


@dataclass(frozen=True)
class SignalBundle:
    """
    Layer 2 の出力を一括保持する型。Cockpit が因子へ配布するための束。
    定義書「4-2 情報の階層構造」に基づき、apply_all(bundle) で渡す。
    """
    price_signals: dict[str, PriceSignals] = field(default_factory=dict)
    volatility_signals: dict[str, VolatilitySignal] = field(default_factory=dict)
    liquidity_credit: Optional[LiquiditySignals] = None
    liquidity_credit_lqd: Optional[LiquiditySignals] = None
    liquidity_tip: Optional[LiquiditySignals] = None
    capital_signals: Optional[CapitalSignals] = None
