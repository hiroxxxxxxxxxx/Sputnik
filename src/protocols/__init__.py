"""
プロトコル階層：モード遷移に伴う執行シーケンス（作戦）を定義する。

FlightController が「司令」、Protocol が「作戦」、Engine/Part が「執行」を担当。
定義書「4-1 操縦制御」「6-2 Emergencyプロトコル」および ARCHITECTURE.md 参照。
"""

from __future__ import annotations

from .base_protocol import BaseProtocol
from .booster_cutoff_protocol import BoosterCutoffProtocol
from .booster_ignition_protocol import BoosterIgnitionProtocol
from .emergency_protocol import EmergencyProtocol
from .restoration_protocol import RestorationProtocol

__all__ = [
    "BaseProtocol",
    "BoosterCutoffProtocol",
    "BoosterIgnitionProtocol",
    "EmergencyProtocol",
    "RestorationProtocol",
]
