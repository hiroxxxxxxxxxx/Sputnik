"""
後方互換: IB Raw 取得窓口を re-export するだけ。

新規コードは avionics.ib.IBRawFetcher を利用し、SignalBundle は FC.refresh 経由で fc.get_last_bundle() から取得すること。
"""

from avionics.ib import IBRawFetcher as IBDataFetcher

__all__ = ["IBDataFetcher"]
