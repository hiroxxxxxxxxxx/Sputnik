"""
Layer 2 Process: RawMarketSnapshot + as_of → 各 compute_* → SignalBundle 構築。
"""

from .bundle_builder import build_signal_bundle
from .compute import (
    MIN_BARS_FOR_RECOVERY,
    RECOVERY_LOOKBACK_DAYS,
)

__all__ = [
    "MIN_BARS_FOR_RECOVERY",
    "RECOVERY_LOOKBACK_DAYS",
    "build_signal_bundle",
]
