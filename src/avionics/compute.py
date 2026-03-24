"""
Layer 2 Process: RawMarketSnapshot と as_of から各シグナル（PriceSignals, VolatilitySignal 等）を算出する。

型は avionics.data にあり、ここでは計算のみ行う。定義書「4-2 情報の階層構造」参照。
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional, Tuple

from .data.raw import PriceBar, PriceBar1h, RawCapitalSnapshot, VolatilitySeriesPoint
from .data.raw_market_snapshot import RawMarketSnapshot
from .data.signals import (
    AltitudeRegime,
    CapitalSignals,
    CreditDailyRow,
    LiquiditySignals,
    PriceDailyRow,
    PriceSignals,
    TipDailyRow,
    TrendType,
    VolatilitySignal,
)

RECOVERY_LOOKBACK_DAYS = 10
MIN_BARS_FOR_RECOVERY = 20 + RECOVERY_LOOKBACK_DAYS


def _price_bars_from_snapshot(snapshot: RawMarketSnapshot, symbol: str) -> List[PriceBar]:
    if symbol == "NQ":
        bars = list(snapshot.nq_price_bars)
    elif symbol == "GC":
        bars = list(snapshot.gc_price_bars)
    else:
        bars = []
    return sorted(bars, key=lambda b: b.date)


def _price_bars_1h_from_snapshot(snapshot: RawMarketSnapshot, symbol: str) -> List[PriceBar1h]:
    if symbol == "NQ":
        bars = list(snapshot.nq_price_bars_1h)
    elif symbol == "GC":
        bars = list(snapshot.gc_price_bars_1h)
    else:
        bars = []
    return sorted(bars, key=lambda b: b.bar_end)


def _volatility_series_from_snapshot(snapshot: RawMarketSnapshot, symbol: str) -> List[VolatilitySeriesPoint]:
    if symbol == "NQ":
        series = list(snapshot.nq_volatility_series)
    elif symbol == "GC":
        series = list(snapshot.gc_volatility_series)
    else:
        series = []
    return sorted(series, key=lambda x: x[0])


def _volatility_index_from_series(series: List[VolatilitySeriesPoint], as_of: date) -> Optional[float]:
    candidates = [(d, v) for d, v in series if d <= as_of]
    return max(candidates, key=lambda x: x[0])[1] if candidates else None


def _sma(series: list[PriceBar], n: int) -> float:
    """直近 n 本の終値の単純移動平均。"""
    if not series or len(series) < n:
        return 0.0
    return sum(b.close for b in series[-n:]) / n


def _settlement_bar_indices_from_date(
    bars: List[PriceBar],
    ref_date: date,
) -> Tuple[int, int]:
    """
    ref_date でバーを検索し、「当日」と「前営業日」のインデックスを返す。
    bars は日付昇順。一致するバーが無い場合は (-1, -2)。
    """
    if not bars or len(bars) < 2:
        return (-1, -2)
    idx = -1
    for i, b in enumerate(bars):
        if b.date == ref_date:
            idx = i
            break
    if idx >= 1:
        return (idx, idx - 1)
    return (-1, -2)


def _price_daily_row_at_index(
    bars: list[PriceBar],
    i: int,
) -> Optional[PriceDailyRow]:
    """
    bars[i] の日付・daily_change・cum5・downside_gap・trend・cum2 を返す。
    i が 0 未満や範囲外の場合は None。復帰確認の日次カウント用。
    """
    if i < 0 or i >= len(bars):
        return None
    bar = bars[i]
    prev_idx = i - 1
    if prev_idx < 0:
        return None
    prev = bars[prev_idx]
    daily_change = (bar.close - prev.close) / prev.close if prev.close else 0.0
    cum5_idx = i - 5
    cum5_change = 0.0
    if cum5_idx >= 0 and bars[cum5_idx].close:
        cum5_change = (bar.close - bars[cum5_idx].close) / bars[cum5_idx].close
    cum2_idx = i - 2
    cum2_change: Optional[float] = None
    if cum2_idx >= 0 and bars[cum2_idx].close:
        cum2_change = (bar.close - bars[cum2_idx].close) / bars[cum2_idx].close
    sma_bars = bars[max(0, i - 19) : i]
    sma20 = _sma(sma_bars, min(20, len(sma_bars))) if sma_bars else (prev.close or 1.0)
    if sma20 <= 0:
        sma20 = prev.close or 1.0
    if bar.close > sma20 * 1.005:
        trend: TrendType = "up"
    elif bar.close < sma20 * 0.995:
        trend = "down"
    else:
        trend = "flat"
    high_slice = bars[max(0, i - 19) : i + 1]
    high_20 = max(b.high for b in high_slice) if high_slice else (bar.high or bar.close)
    downside_gap = (bar.close / high_20 - 1.0) if high_20 else -0.01
    return (bar.date, daily_change, cum5_change, downside_gap, trend, cum2_change)


def compute_price_signals_from_bars(
    bars: List[PriceBar],
    symbol: str,
    as_of: date,
) -> PriceSignals:
    """
    終値系列から trend, daily_change, cum5, cum2, downside_gap を算出する。

    トレンド定義（定義書 4-2-2）: Uptrend = 終値 > SMA20×1.005,
    Downtrend = 終値 < SMA20×0.995。SMA20 は過去20営業日終値の単純移動平均。

    「今日の清算値」は as_of の日付でバーを検索し、その足と1本前を比較する（as_of は呼び出し元で NY の今日などに揃える）。
    """
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

    latest_idx, prev_idx = _settlement_bar_indices_from_date(bars, as_of)
    latest = bars[latest_idx]
    prev = bars[prev_idx]

    # SMA20: 清算値の足の直前20本
    sma_bars = bars[:latest_idx] if latest_idx != -1 else bars[:-1]
    sma20 = _sma(sma_bars, 20) if len(sma_bars) >= 20 else prev.close
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
    cum5_idx = latest_idx - 5
    if len(bars) + cum5_idx >= 0 and cum5_idx >= -len(bars) and bars[cum5_idx].close:
        cum5_change = (latest.close - bars[cum5_idx].close) / bars[cum5_idx].close

    cum2_change: Optional[float] = None
    cum2_idx = latest_idx - 2
    if len(bars) + cum2_idx >= 0 and cum2_idx >= -len(bars) and bars[cum2_idx].close:
        cum2_change = (latest.close - bars[cum2_idx].close) / bars[cum2_idx].close

    if latest_idx == -1:
        high_20_slice = bars[-20:] if len(bars) >= 20 else bars
    else:
        high_20_slice = bars[latest_idx - 19 : latest_idx + 1] if latest_idx - 19 >= -len(bars) else bars[: latest_idx + 1]
    high_20 = max(b.high for b in high_20_slice) if high_20_slice else (latest.high or latest.close)
    downside_gap = (latest.close / high_20 - 1.0) if high_20 else -0.01

    # 復帰確認用: 基準日から遡る。各日で SMA20・20日高値を使うため j>=19 の日のみ（20本揃い）
    daily_history_list: List[PriceDailyRow] = []
    j_min = max(19, latest_idx - RECOVERY_LOOKBACK_DAYS)
    for j in range(latest_idx, j_min - 1, -1):
        row = _price_daily_row_at_index(bars, j)
        if row is not None:
            daily_history_list.append(row)
    daily_history = tuple(daily_history_list)

    return PriceSignals(
        symbol=symbol,
        trend=trend,
        daily_change=daily_change,
        cum5_change=cum5_change,
        cum2_change=cum2_change,
        downside_gap=downside_gap,
        last_close=latest.close,
        daily_history=daily_history,
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


def _v1_to_v0_knock_in_ok(
    daily: List[PriceBar],
    bars_1h: List[PriceBar1h],
    as_of: date,
) -> Optional[bool]:
    """
    SPEC 4-2-1-2「1hノックイン」: 直近1h足で「終値>前日ET16:00終値 AND 1h足が陽線」を満たすか。
    前日終値は as_of で当日足を特定し、その1本前の終値を使う。
    """
    daily = sorted(daily, key=lambda b: b.date)
    if len(daily) < 2 or not bars_1h:
        return None
    _, prev_idx = _settlement_bar_indices_from_date(daily, as_of)
    prev_close = daily[prev_idx].close
    latest_1h = sorted(bars_1h, key=lambda b: b.bar_end)[-1]
    return bool(
        latest_1h.close > prev_close
        and latest_1h.close > latest_1h.open
    )


def compute_volatility_signal_from_inputs(
    *,
    index_value: float,
    altitude: AltitudeRegime,
    knock_in: Optional[bool],
    series: List[VolatilitySeriesPoint],
    v1_off_threshold: Optional[float],
    v2_off_threshold: Optional[float],
) -> VolatilitySignal:
    is_intraday = knock_in is True
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
        index_value=index_value,
        altitude=altitude,
        v1_to_v0_knock_in_ok=knock_in,
        is_intraday_condition_met=is_intraday,
        recovery_confirm_satisfied_days_v1_off=satisfied_v1,
        recovery_confirm_satisfied_days_v2_off=satisfied_v2,
    )


def compute_capital_signals_from_cap(cap: Optional[RawCapitalSnapshot]) -> CapitalSignals:
    """
    証拠金スナップショットから U/S 用シグナルを算出する。

    mm_over_nlv = MM/NLV。span_ratio = Current Density / Base Density。
    証拠金密度 = MM / (現在値 × 先物倍率)（定義書 4-2-3-2）。
    """
    if cap is None or cap.nlv <= 0:
        return CapitalSignals(mm_over_nlv=0.0, span_ratio=1.0)
    mm_over_nlv = cap.mm / cap.nlv
    denom = cap.current_value * cap.futures_multiplier
    current_density = cap.mm / denom if denom > 0 else 0.0
    span_ratio = current_density / cap.base_density if cap.base_density > 0 else 1.0
    return CapitalSignals(mm_over_nlv=mm_over_nlv, span_ratio=span_ratio)


def compute_liquidity_signals_credit_from_bars(
    bars: List[PriceBar],
    as_of: date,
    altitude: AltitudeRegime,
) -> LiquiditySignals:
    """HYG/LQD 等の価格系列から L 因子 credit 用シグナルを算出する。as_of で当日足を特定。SMA20 のため 20+遡り日数本取得。"""
    bars = sorted(bars, key=lambda b: b.date)
    if len(bars) < 2:
        return LiquiditySignals(
            altitude=altitude,
            below_sma20=False,
            daily_change=0.0,
        )
    latest_idx, prev_idx = _settlement_bar_indices_from_date(bars, as_of)
    latest = bars[latest_idx]
    prev = bars[prev_idx]
    sma_bars = bars[:latest_idx] if latest_idx != -1 else bars[:-1]
    sma20 = _sma(sma_bars, 20) if len(sma_bars) >= 20 else prev.close or 0.0
    below_sma20 = latest.close < sma20 if sma20 else False
    daily_change = (latest.close - prev.close) / prev.close if prev.close else 0.0

    daily_history_credit_list: List[CreditDailyRow] = []
    j_min = max(20, latest_idx - RECOVERY_LOOKBACK_DAYS)  # SMA20 のため j>=20 の日のみ
    for j in range(latest_idx, j_min - 1, -1):
        if j < 1:
            break
        b, prev_b = bars[j], bars[j - 1]
        sma_j = _sma(bars[max(0, j - 20) : j], 20) if j >= 20 else (prev_b.close or 0.0)
        below = b.close < sma_j if sma_j else False
        dc = (b.close - prev_b.close) / prev_b.close if prev_b.close else 0.0
        daily_history_credit_list.append((b.date, below, dc))
    daily_history_credit = tuple(daily_history_credit_list)

    return LiquiditySignals(
        altitude=altitude,
        below_sma20=below_sma20,
        daily_change=daily_change,
        daily_history_credit=daily_history_credit,
    )


def compute_liquidity_signals_tip_from_bars(
    bars: List[PriceBar],
    as_of: date,
    altitude: AltitudeRegime,
) -> LiquiditySignals:
    """TIP 価格系列から L 因子 tip 用（高値比ドローダウン）を算出する。as_of で当日足を特定。20日高値のため 20+遡り日数本取得。"""
    bars = sorted(bars, key=lambda b: b.date)
    if len(bars) < 2:
        return LiquiditySignals(altitude=altitude, tip_drawdown_from_high=-0.001)
    latest_idx, _ = _settlement_bar_indices_from_date(bars, as_of)
    latest = bars[latest_idx]
    if latest_idx == -1:
        high_20_slice = bars[-20:] if len(bars) >= 20 else bars
    else:
        high_20_slice = bars[max(0, latest_idx - 19) : latest_idx + 1]
    high_20 = max(b.high for b in high_20_slice) if high_20_slice else (latest.high or latest.close)
    if not high_20 or high_20 <= 0:
        return LiquiditySignals(altitude=altitude, tip_drawdown_from_high=-0.001)
    drawdown = (latest.close / high_20) - 1.0

    daily_history_tip_list: List[TipDailyRow] = []
    j_min = max(19, latest_idx - RECOVERY_LOOKBACK_DAYS)  # 20日高値のため j>=19 の日のみ
    for j in range(latest_idx, j_min - 1, -1):
        if j < 0:
            break
        b = bars[j]
        high_slice = bars[max(0, j - 19) : j + 1]
        h = max(bar.high for bar in high_slice) if high_slice else (b.high or b.close)
        dd = (b.close / h - 1.0) if h and h > 0 else -0.001
        daily_history_tip_list.append((b.date, dd))
    daily_history_tip = tuple(daily_history_tip_list)

    return LiquiditySignals(
        altitude=altitude,
        tip_drawdown_from_high=drawdown,
        daily_history_tip=daily_history_tip,
    )


def compute_price_signals_from_snapshot(
    snapshot: RawMarketSnapshot,
    symbol: str,
    as_of: date,
) -> PriceSignals:
    """RawMarketSnapshot から PriceSignals を算出する（Phase3: snapshot直）。"""
    bars = _price_bars_from_snapshot(snapshot, symbol)[-MIN_BARS_FOR_RECOVERY:]
    return compute_price_signals_from_bars(bars, symbol, as_of)


def compute_volatility_signal_from_snapshot(
    snapshot: RawMarketSnapshot,
    symbol: str,
    as_of: date,
    altitude: AltitudeRegime,
    *,
    v1_off_threshold: Optional[float] = None,
    v2_off_threshold: Optional[float] = None,
) -> VolatilitySignal:
    """RawMarketSnapshot から VolatilitySignal を算出する（Phase3: snapshot直）。"""
    full_series = _volatility_series_from_snapshot(snapshot, symbol)
    v = _volatility_index_from_series(full_series, as_of) or 0.0

    daily = _price_bars_from_snapshot(snapshot, symbol)[-5:]
    bars_1h = _price_bars_1h_from_snapshot(snapshot, symbol)[-24:]
    knock_in = _v1_to_v0_knock_in_ok(daily, bars_1h, as_of)

    series = full_series[-5:] if len(full_series) > 5 else full_series
    return compute_volatility_signal_from_inputs(
        index_value=v,
        altitude=altitude,
        knock_in=knock_in,
        series=series,
        v1_off_threshold=v1_off_threshold,
        v2_off_threshold=v2_off_threshold,
    )


def compute_capital_signals_from_snapshot(snapshot: RawMarketSnapshot, as_of: date) -> CapitalSignals:
    """RawMarketSnapshot から CapitalSignals を算出する（Phase3: snapshot直）。"""
    _ = as_of  # 互換: RawCapitalSnapshot は取得時点の値を保持
    return compute_capital_signals_from_cap(snapshot.capital_snapshot)


def compute_liquidity_signals_credit_from_snapshot(
    snapshot: RawMarketSnapshot,
    symbol: str,
    as_of: date,
    altitude: AltitudeRegime,
) -> LiquiditySignals:
    bars = sorted(snapshot.credit_bars.get(symbol, []), key=lambda b: b.date)[-MIN_BARS_FOR_RECOVERY:]
    return compute_liquidity_signals_credit_from_bars(bars, as_of, altitude)


def compute_liquidity_signals_tip_from_snapshot(
    snapshot: RawMarketSnapshot,
    as_of: date,
    altitude: AltitudeRegime,
) -> LiquiditySignals:
    bars = sorted(snapshot.tip_bars, key=lambda b: b.date)[-MIN_BARS_FOR_RECOVERY:]
    return compute_liquidity_signals_tip_from_bars(bars, as_of, altitude)
