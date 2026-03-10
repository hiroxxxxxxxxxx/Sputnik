"""
Layer 2（Signals）：Raw Data のみを入力に統計加工した共通部品。

トレンド・日次変動率・累積変動率・Downside Gap・証拠金比率等を算出し、
複数因子が共有参照する。因子は Layer 2 の出力のみを入力とする。
定義書「4-2 情報の階層構造」「4-2-2 SCL トレンド定義」参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from .raw_data import PriceBar, RawCapitalSnapshot, RawDataProvider


TrendType = Literal["up", "down", "flat"]
AltitudeRegime = Literal["high_mid", "low"]


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


@dataclass(frozen=True)
class VolatilitySignal:
    """
    V 因子用。指数値と高度レジーム。

    復帰確認は営業日遡りで算出（docs/recovery_confirm_spec_options.md）。
    v1_to_v0_knock_in_ok / is_intraday_condition_met: SPEC 4-2-1-2「1hノックイン」。
    """
    index_value: float
    altitude: AltitudeRegime
    v1_to_v0_knock_in_ok: Optional[bool] = None
    is_intraday_condition_met: bool = False
    recovery_confirm_satisfied_days_v1_off: int = 0
    recovery_confirm_satisfied_days_v2_off: int = 0


@dataclass(frozen=True)
class LiquiditySignals:
    """C 因子（credit）・R 因子（tip）用。credit は below_sma20/daily_change、tip は tip_drawdown_from_high。"""
    altitude: AltitudeRegime
    below_sma20: Optional[bool] = None
    daily_change: Optional[float] = None
    tip_drawdown_from_high: Optional[float] = None


@dataclass(frozen=True)
class CapitalSignals:
    """U 因子・S 因子用。証拠金使用率と SPAN 乖離率。"""
    mm_over_nlv: float
    span_ratio: float


@dataclass(frozen=True)
class SignalBundle:
    """
    Layer 2 の出力を一括保持し、Cockpit が因子へ配布するための束。

    定義書「4-2 情報の階層構造」に基づき、update_all(signal_bundle) で渡す。
    """
    price_signals: dict[str, PriceSignals] = field(default_factory=dict)
    volatility_signals: dict[str, VolatilitySignal] = field(default_factory=dict)
    liquidity_credit: Optional[LiquiditySignals] = None
    liquidity_tip: Optional[LiquiditySignals] = None
    capital_signals: Optional[CapitalSignals] = None


def _sorted_bars(provider: RawDataProvider, symbol: str, limit: int) -> list[PriceBar]:
    """get_price_series を日付昇順で返す。"""
    bars = provider.get_price_series(symbol, limit)
    return sorted(bars, key=lambda b: b.date)


def _sma(series: list[PriceBar], n: int) -> float:
    """直近 n 本の終値の単純移動平均。"""
    if not series or len(series) < n:
        return 0.0
    return sum(b.close for b in series[-n:]) / n


def compute_price_signals(
    raw_provider: RawDataProvider,
    symbol: str,
    as_of: date,
) -> PriceSignals:
    """
    終値系列から trend, daily_change, cum5, cum2, downside_gap を算出する。

    トレンド定義（定義書 4-2-2）: Uptrend = 終値 > SMA20×1.005,
    Downtrend = 終値 < SMA20×0.995。SMA20 は過去20営業日終値の単純移動平均。
    """
    bars = _sorted_bars(raw_provider, symbol, limit=32)
    if len(bars) < 2:
        return PriceSignals(
            symbol=symbol,
            trend="up",
            daily_change=0.0,
            cum5_change=0.0,
            cum2_change=None,
            downside_gap=-0.01,
            last_close=bars[-1].close if bars else 0.0,
        )

    latest = bars[-1]
    prev = bars[-2]
    sma20 = _sma(bars[:-1], 20) if len(bars) >= 21 else prev.close
    if sma20 <= 0:
        sma20 = prev.close or 1.0

    if latest.close > sma20 * 1.005:
        trend: TrendType = "up"
    elif latest.close < sma20 * 0.995:
        trend = "down"
    else:
        trend = "flat"

    daily_change = (latest.close - prev.close) / prev.close if prev.close else 0.0

    cum5_change = 0.0
    if len(bars) >= 6 and bars[-6].close:
        cum5_change = (latest.close - bars[-6].close) / bars[-6].close

    cum2_change: Optional[float] = None
    if len(bars) >= 3 and bars[-3].close:
        cum2_change = (latest.close - bars[-3].close) / bars[-3].close

    high_20 = max(b.high for b in bars[-20:]) if len(bars) >= 20 else latest.high or latest.close
    downside_gap = (latest.close / high_20 - 1.0) if high_20 else -0.01

    return PriceSignals(
        symbol=symbol,
        trend=trend,
        daily_change=daily_change,
        cum5_change=cum5_change,
        cum2_change=cum2_change,
        downside_gap=downside_gap,
        last_close=latest.close,
    )


def _count_consecutive_days_below(
    series: list[tuple[date, float]], threshold: float
) -> int:
    """系列を newest から遡り、閾値未満が連続する日数を返す。series は日付昇順。"""
    if not series or threshold <= 0:
        return 0
    count = 0
    for _d, v in reversed(series):
        if v < threshold:
            count += 1
        else:
            break
    return count


def _v1_to_v0_knock_in_ok(raw_provider: RawDataProvider, symbol: str) -> Optional[bool]:
    """
    SPEC 4-2-1-2「1hノックイン」: 直近1h足で「終値>前日ET16:00終値 AND 1h足が陽線」を満たすか。

    :return: True=満たす, False=満たさない, None=データ不足で未判定
    """
    daily = raw_provider.get_price_series(symbol, 3)
    bars_1h = raw_provider.get_price_series_1h(symbol, 24)
    daily = sorted(daily, key=lambda b: b.date)
    if len(daily) < 2 or not bars_1h:
        return None
    prev_close = daily[-2].close
    latest_1h = sorted(bars_1h, key=lambda b: b.bar_end)[-1]
    return bool(
        latest_1h.close > prev_close
        and latest_1h.close > latest_1h.open
    )


def compute_volatility_signal(
    raw_provider: RawDataProvider,
    symbol: str,
    as_of: date,
    altitude: AltitudeRegime,
    *,
    v1_off_threshold: Optional[float] = None,
    v2_off_threshold: Optional[float] = None,
) -> VolatilitySignal:
    """
    VXN/GVZ 相当の指数値から V 因子用シグナルを返す。

    復帰確認: get_volatility_series から閾値未満の連続日数を算出（営業日遡り）。
    1hノックインは is_intraday_condition_met / v1_to_v0_knock_in_ok に載せる。
    """
    v = raw_provider.get_volatility_index(symbol, as_of) or 0.0
    knock_in = _v1_to_v0_knock_in_ok(raw_provider, symbol)
    is_intraday = knock_in is True

    series = raw_provider.get_volatility_series(symbol, 5)
    satisfied_v1 = (
        _count_consecutive_days_below(series, v1_off_threshold)
        if v1_off_threshold is not None
        else 0
    )
    satisfied_v2 = (
        _count_consecutive_days_below(series, v2_off_threshold)
        if v2_off_threshold is not None
        else 0
    )

    return VolatilitySignal(
        index_value=v,
        altitude=altitude,
        v1_to_v0_knock_in_ok=knock_in,
        is_intraday_condition_met=is_intraday,
        recovery_confirm_satisfied_days_v1_off=satisfied_v1,
        recovery_confirm_satisfied_days_v2_off=satisfied_v2,
    )


def compute_capital_signals(
    raw_provider: RawDataProvider,
    as_of: date,
) -> CapitalSignals:
    """
    証拠金スナップショットから U/S 用シグナルを算出する。

    mm_over_nlv = MM/NLV。span_ratio = Current Density / Base Density。
    証拠金密度 = MM / (現在値 × 先物倍率)（定義書 4-2-3-2）。
    """
    cap = raw_provider.get_capital_snapshot(as_of)
    if cap is None or cap.nlv <= 0:
        return CapitalSignals(mm_over_nlv=0.0, span_ratio=1.0)
    mm_over_nlv = cap.mm / cap.nlv
    denom = cap.current_value * cap.futures_multiplier
    current_density = cap.mm / denom if denom > 0 else 0.0
    span_ratio = current_density / cap.base_density if cap.base_density > 0 else 1.0
    return CapitalSignals(mm_over_nlv=mm_over_nlv, span_ratio=span_ratio)


def compute_liquidity_signals_credit(
    raw_provider: RawDataProvider,
    symbol: str,
    as_of: date,
    altitude: AltitudeRegime,
) -> LiquiditySignals:
    """HYG/LQD 等の価格系列から L 因子 credit 用シグナルを算出する。"""
    bars = _sorted_bars(raw_provider, symbol, limit=25)
    if len(bars) < 2:
        return LiquiditySignals(
            altitude=altitude,
            below_sma20=False,
            daily_change=0.0,
        )
    latest = bars[-1]
    prev = bars[-2]
    sma20 = _sma(bars[:-1], 20) if len(bars) >= 21 else prev.close or 0.0
    below_sma20 = latest.close < sma20 if sma20 else False
    daily_change = (latest.close - prev.close) / prev.close if prev.close else 0.0
    return LiquiditySignals(
        altitude=altitude,
        below_sma20=below_sma20,
        daily_change=daily_change,
    )


def compute_liquidity_signals_tip(
    raw_provider: RawDataProvider,
    as_of: date,
    altitude: AltitudeRegime,
) -> LiquiditySignals:
    """TIP 価格系列から L 因子 tip 用（高値比ドローダウン）を算出する。"""
    bars = raw_provider.get_tip_series(limit=22)
    bars = sorted(bars, key=lambda b: b.date)
    if len(bars) < 2:
        return LiquiditySignals(altitude=altitude, tip_drawdown_from_high=-0.001)
    latest = bars[-1]
    high_20 = max(b.high for b in bars[-20:]) if len(bars) >= 20 else latest.high or latest.close
    if not high_20 or high_20 <= 0:
        return LiquiditySignals(altitude=altitude, tip_drawdown_from_high=-0.001)
    drawdown = (latest.close / high_20) - 1.0
    return LiquiditySignals(altitude=altitude, tip_drawdown_from_high=drawdown)


def format_signal_bundle_breakdown(bundle: SignalBundle) -> str:
    """
    Layer 2 シグナル（各因子の入力）を人が読める文字列で返す。
    因子の計算内訳確認用。定義書「4-2 情報の階層構造」参照。
    """
    lines: list[str] = ["【Layer 2 シグナル内訳】"]
    for sym, ps in bundle.price_signals.items():
        lines.append(
            f"  P/T入力({sym}): trend={ps.trend} "
            f"daily_change={ps.daily_change:.4f} cum5={ps.cum5_change:.4f} "
            f"cum2={ps.cum2_change!s} downside_gap={ps.downside_gap:.4f}"
        )
    for sym, vs in bundle.volatility_signals.items():
        extra = f" 1h_knock_in_ok={vs.v1_to_v0_knock_in_ok}" if vs.v1_to_v0_knock_in_ok is not None else ""
        lines.append(f"  V入力({sym}): index_value={vs.index_value:.2f} altitude={vs.altitude}{extra}")
    if bundle.liquidity_credit:
        lc = bundle.liquidity_credit
        lines.append(
            f"  C(credit): below_sma20={lc.below_sma20} daily_change={lc.daily_change!s} altitude={lc.altitude}"
        )
    if bundle.liquidity_tip:
        lt = bundle.liquidity_tip
        lines.append(
            f"  R(tip): tip_drawdown_from_high={lt.tip_drawdown_from_high!s} altitude={lt.altitude}"
        )
    if bundle.capital_signals:
        cs = bundle.capital_signals
        lines.append(f"  U/S入力: mm_over_nlv={cs.mm_over_nlv:.4f} span_ratio={cs.span_ratio:.4f}")
    return "\n".join(lines)
