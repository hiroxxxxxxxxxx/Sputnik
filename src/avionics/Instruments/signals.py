"""
Layer 2（Signals）：Raw Data のみを入力に統計加工した共通部品。

トレンド・日次変動率・累積変動率・Downside Gap・証拠金比率等を算出し、
複数因子が共有参照する。因子は Layer 2 の出力のみを入力とする。
定義書「4-2 情報の階層構造」「4-2-2 SCL トレンド定義」参照。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, List, Literal, Optional, Tuple

from .raw_data import PriceBar, RawCapitalSnapshot, RawDataProvider


TrendType = Literal["up", "down", "flat"]
AltitudeRegime = Literal["high_mid", "low"]

# 復帰確認で遡る最大日数。config の confirm_days は 1〜3 のため余裕を見て 10。
# 各日で SMA20・20日高値を使うため「その日を含め20本」必要。遡り N 日なら bar は 20 + N 本以上必要。
RECOVERY_LOOKBACK_DAYS = 10
MIN_BARS_FOR_RECOVERY = 20 + RECOVERY_LOOKBACK_DAYS  # 30


# 復帰確認用。1日分の価格シグナル (date, daily_change, cum5_change, downside_gap, trend, cum2_change)。newest first。
PriceDailyRow = Tuple[date, float, float, float, TrendType, Optional[float]]


@dataclass(frozen=True)
class PriceSignals:
    """
    P 因子・T 因子用。定義書 Layer 2：トレンド・日次変動率・累積変動率・Downside Gap。

    P因子・同期制御層が共通参照する共用シグナル（定義書 4-2-2）。
    daily_history: 基準日から遡った日次値（newest first）。復帰ヒステリシスをステートレスに数える用。
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


# 復帰確認用。1日分 (date, below_sma20, daily_change)。newest first。
CreditDailyRow = Tuple[date, bool, float]
# 復帰確認用。1日分 (date, tip_drawdown_from_high)。newest first。
TipDailyRow = Tuple[date, float]


@dataclass(frozen=True)
class LiquiditySignals:
    """
    C 因子（credit）・R 因子（tip）用。credit は below_sma20/daily_change、tip は tip_drawdown_from_high。
    daily_history_credit / daily_history_tip: 基準日から遡った日次（newest first）。復帰をステートレスに数える用。
    """
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
    Layer 2 の出力を一括保持し、Cockpit が因子へ配布するための束。

    定義書「4-2 情報の階層構造」に基づき、update_all(signal_bundle) で渡す。
    """
    price_signals: dict[str, PriceSignals] = field(default_factory=dict)
    volatility_signals: dict[str, VolatilitySignal] = field(default_factory=dict)
    liquidity_credit: Optional[LiquiditySignals] = None
    """C因子用。HYG のシグナル。定義書「HYG or LQD」の HYG 側。"""
    liquidity_credit_lqd: Optional[LiquiditySignals] = None
    """C因子用。LQD のシグナル。定義書「HYG AND LQD」の LQD 側。"""
    liquidity_tip: Optional[LiquiditySignals] = None
    capital_signals: Optional[CapitalSignals] = None


def _sorted_bars(provider: RawDataProvider, symbol: str, limit: int) -> list[PriceBar]:
    """get_price_series を日付昇順で返す。"""
    bars = provider.get_price_series(symbol, limit)
    return sorted(bars, key=lambda b: b.date)


def _sorted_credit_bars(provider: RawDataProvider, symbol: str, limit: int) -> list[PriceBar]:
    """get_credit_series（HYG/LQD）を日付昇順で返す。"""
    bars = provider.get_credit_series(symbol, limit)
    return sorted(bars, key=lambda b: b.date)


def _sma(series: list[PriceBar], n: int) -> float:
    """直近 n 本の終値の単純移動平均。"""
    if not series or len(series) < n:
        return 0.0
    return sum(b.close for b in series[-n:]) / n


def _settlement_bar_indices_from_date(
    bars: List[Any],
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
        if getattr(b, "date", None) == ref_date:
            idx = i
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
    bar_date = getattr(bar, "date", None)
    if not isinstance(bar_date, date):
        return None
    return (bar_date, daily_change, cum5_change, downside_gap, trend, cum2_change)


def compute_price_signals(
    raw_provider: RawDataProvider,
    symbol: str,
    as_of: date,
) -> PriceSignals:
    """
    終値系列から trend, daily_change, cum5, cum2, downside_gap を算出する。

    トレンド定義（定義書 4-2-2）: Uptrend = 終値 > SMA20×1.005,
    Downtrend = 終値 < SMA20×0.995。SMA20 は過去20営業日終値の単純移動平均。

    「今日の清算値」は as_of の日付でバーを検索し、その足と1本前を比較する（as_of は呼び出し元で NY の今日などに揃える）。
    """
    bars = _sorted_bars(raw_provider, symbol, limit=MIN_BARS_FOR_RECOVERY)
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
    raw_provider: RawDataProvider,
    symbol: str,
    as_of: date,
) -> Optional[bool]:
    """
    SPEC 4-2-1-2「1hノックイン」: 直近1h足で「終値>前日ET16:00終値 AND 1h足が陽線」を満たすか。
    前日終値は as_of で当日足を特定し、その1本前の終値を使う。
    """
    daily = raw_provider.get_price_series(symbol, 5)
    bars_1h = raw_provider.get_price_series_1h(symbol, 24)
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
    knock_in = _v1_to_v0_knock_in_ok(raw_provider, symbol, as_of)
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
    """HYG/LQD 等の価格系列から L 因子 credit 用シグナルを算出する。as_of で当日足を特定。SMA20 のため 20+遡り日数本取得。"""
    bars = _sorted_credit_bars(raw_provider, symbol, limit=MIN_BARS_FOR_RECOVERY)
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
        d = getattr(b, "date", None)
        if isinstance(d, date):
            daily_history_credit_list.append((d, below, dc))
    daily_history_credit = tuple(daily_history_credit_list)

    return LiquiditySignals(
        altitude=altitude,
        below_sma20=below_sma20,
        daily_change=daily_change,
        daily_history_credit=daily_history_credit,
    )


def compute_liquidity_signals_tip(
    raw_provider: RawDataProvider,
    as_of: date,
    altitude: AltitudeRegime,
) -> LiquiditySignals:
    """TIP 価格系列から L 因子 tip 用（高値比ドローダウン）を算出する。as_of で当日足を特定。20日高値のため 20+遡り日数本取得。"""
    bars = raw_provider.get_tip_series(limit=MIN_BARS_FOR_RECOVERY)
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
        d = getattr(b, "date", None)
        if isinstance(d, date):
            daily_history_tip_list.append((d, dd))
    daily_history_tip = tuple(daily_history_tip_list)

    return LiquiditySignals(
        altitude=altitude,
        tip_drawdown_from_high=drawdown,
        daily_history_tip=daily_history_tip,
    )


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
            f"  C(HYG): below_sma20={lc.below_sma20} daily_change={lc.daily_change!s} altitude={lc.altitude}"
        )
    lc_lqd = getattr(bundle, "liquidity_credit_lqd", None)
    if lc_lqd:
        lines.append(
            f"  C(LQD): below_sma20={lc_lqd.below_sma20} daily_change={lc_lqd.daily_change!s} altitude={lc_lqd.altitude}"
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
