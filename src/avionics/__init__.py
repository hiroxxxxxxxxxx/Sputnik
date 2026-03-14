from __future__ import annotations

"""
Macro Income Strategy 計器レイヤーの因子クラス群と管制層。

FlightController: 計器層（3層フレームワーク）。各因子は非対称ヒステリシスを備えたFSMとして実装され、
Market Level / Capital Level を算出。Cockpit: 管制層。スロットルモードの遷移・配布と承認フローを担当。
定義書「2.コックピット」「3.フライトコントローラー」「4-2 OS構造」セクション参照。
"""

from protocols.emergency_protocol import EmergencyProtocol
from .flight_controller import FlightController, FlightControllerSignal
from .Instruments import (
    BaseFactor,
    CapitalSignals,
    CFactor,
    LiquiditySignals,
    PFactor,
    PriceBar,
    PriceBar1h,
    PriceSignals,
    RawCapitalSnapshot,
    RawDataProvider,
    RFactor,
    SFactor,
    SignalBundle,
    TFactor,
    UFactor,
    VFactor,
    VolatilitySignal,
)

__all__ = [
    "BaseFactor",
    "CapitalSignals",
    "FlightControllerSignal",
    "EmergencyProtocol",
    "CFactor",
    "FlightController",
    "LiquiditySignals",
    "PFactor",
    "PriceBar",
    "PriceBar1h",
    "PriceSignals",
    "RawCapitalSnapshot",
    "RawDataProvider",
    "RFactor",
    "SFactor",
    "SignalBundle",
    "TFactor",
    "UFactor",
    "VFactor",
    "VolatilitySignal",
]

