"""
Data: Layer 2 の型定義のみ（PriceSignals, SignalBundle 等）。

計算ロジックは avionics.compute にあり、ここには型だけを置く。
定義書「4-2 情報の階層構造」「4-2-2 SCL トレンド定義」参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Literal, Optional, Tuple

TrendType = Literal["up", "down", "flat"]
AltitudeRegime = Literal["high", "mid", "low"]

# 復帰確認用。1日分の価格シグナル (date, daily_change, cum5_change, high_20_gap, trend, cum2_change)。newest first。
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
    last_close: float = 0.0
    sma20: Optional[float] = None
    sma20_gap: Optional[float] = None
    high_20: Optional[float] = None
    high_20_gap: Optional[float] = None
    daily_history: Tuple[PriceDailyRow, ...] = ()


@dataclass(frozen=True)
class VolatilitySignal:
    """V 因子用。指数値と復帰判定用フラグ。"""
    index_value: float
    high_20: Optional[float] = None
    v1_to_v0_knock_in_ok: bool = False
    knock_in_bar_end: Optional[str] = None
    recovery_confirm_satisfied_days_v1_off: int = 0
    recovery_confirm_satisfied_days_v2_off: int = 0


@dataclass(frozen=True)
class LiquiditySignals:
    """C 因子（credit）・R 因子（tip）用。

    - credit: last_close / sma20 を保持。
    - tip (R): last_close は TIP 当日終値、tip_reference_high はドローダウン比較に使う窓内最高値。
    """
    below_sma20: Optional[bool] = None
    daily_change: Optional[float] = None
    # credit 系: as_of 当日の終値（HYG/LQD）、当日基準 SMA20
    last_close: Optional[float] = None
    sma20: Optional[float] = None
    sma20_gap: Optional[float] = None
    tip_drawdown_from_high: Optional[float] = None
    # R/TIP: 高値比ドローダウン算出時の比較用高値（rolling 窓の max high）
    tip_reference_high: Optional[float] = None
    daily_history_credit: Tuple[CreditDailyRow, ...] = ()
    daily_history_tip: Tuple[TipDailyRow, ...] = ()


@dataclass(frozen=True)
class CapitalSignals:
    """U 因子・S 因子用。証拠金使用率と SPAN 乖離率。"""
    mm_over_nlv: float
    span_ratio: float
    s_whatif_mm_per_lot: Optional[Dict[str, float]] = None
    s_baseline_mm_per_lot: Optional[Dict[str, float]] = None
    s_whatif_errors: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class SignalBundle:
    """
    Layer 2 の出力を一括保持する型。Cockpit が因子へ配布するための束。
    定義書「4-2 情報の階層構造」に基づき、apply_all(bundle, altitude=...) で渡す。
    """
    liquidity_credit_hyg: LiquiditySignals
    liquidity_credit_lqd: LiquiditySignals
    price_signals: dict[str, PriceSignals] = field(default_factory=dict)
    volatility_signals: dict[str, VolatilitySignal] = field(default_factory=dict)
    liquidity_tip: Optional[LiquiditySignals] = None
    capital_signals: Optional[CapitalSignals] = None
