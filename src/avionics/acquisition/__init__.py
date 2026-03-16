"""
Acquisition (API): 外部システムから Raw を取得する責務のみ。

- ib_fetcher: IB に問い合わせ、data.cache.CachedRawDataProvider に詰めて返す。Layer 2 計算は行わない。
"""

from .ib_fetcher import IBDataFetcher, fetch_raw

__all__ = [
    "IBDataFetcher",
    "fetch_raw",
]
