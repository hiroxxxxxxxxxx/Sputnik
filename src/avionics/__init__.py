from __future__ import annotations

"""
Macro Income Strategy 計器レイヤーの因子クラス群と管制層。

Cockpit: 計器層。各因子は非対称ヒステリシスを備えたFSMとして実装され、
Market Level / Capital Level を算出。FlightController: 管制層。スロットルモードの遷移・配布。
定義書「3.コックピット」「4-2 OS構造」セクション参照。
"""

from protocols.emergency_protocol import EmergencyProtocol
from .cockpit import Cockpit, CockpitSignal
from .flight_controller import FlightController
from .mode import BOOST, CRUISE, EMERGENCY, ModeType, MODES
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
    "BOOST",
    "BaseFactor",
    "CapitalSignals",
    "Cockpit",
    "CockpitSignal",
    "CRUISE",
    "EMERGENCY",
    "EmergencyProtocol",
    "CFactor",
    "FlightController",
    "LiquiditySignals",
    "MODES",
    "ModeType",
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

