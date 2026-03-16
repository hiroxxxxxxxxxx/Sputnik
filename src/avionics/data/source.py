"""
DataSource 抽象と Bundle ビルド用設定。

FC が「最新取得」する際に使う DataSource Protocol と、
refresh 時に build_signal_bundle へ渡すオプションの型を定義する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Protocol, Tuple

from .raw import RawCapitalSnapshot
from .signals import AltitudeRegime

# CachedRawDataProvider は cache モジュールにあるが、Protocol は型だけ参照する
# 実装で import するためここでは TYPE_CHECKING または str で遅延参照しない
from .cache import CachedRawDataProvider


class DataSource(Protocol):
    """
    Raw を取得できるデータ源。FC.refresh に注入する。
    実装例: avionics.ib.fetcher.IBRawFetcher。
    """

    async def fetch_raw(
        self,
        as_of: date,
        price_symbols: List[str],
        *,
        volatility_symbols: Optional[Dict[str, str]] = None,
        liquidity_credit_symbol: Optional[str] = None,
        liquidity_tip: bool = True,
        account: str = "",
        base_density: float = 1.0,
        v_recovery_params: Optional[Dict[str, dict]] = None,
    ) -> Tuple[CachedRawDataProvider, Optional[RawCapitalSnapshot]]:
        ...
        """Layer 1 の Raw を取得し、CachedRawDataProvider と Optional[RawCapitalSnapshot] を返す。"""


@dataclass(frozen=True)
class BundleBuildOptions:
    """
    FC 構築時に注入する、build_signal_bundle 用のオプション。
    refresh 時に FC がこの値を使って bundle を組み立てる。
    """

    liquidity_credit_symbol: Optional[str] = "HYG"
    liquidity_tip: bool = True
    base_density: float = 1.0
    v_altitude: AltitudeRegime = "high_mid"
    c_altitude: AltitudeRegime = "high_mid"
    r_altitude: AltitudeRegime = "high_mid"
    account: str = ""
    volatility_symbols: Optional[Dict[str, str]] = None
    v_recovery_params: Optional[Dict[str, dict]] = None
