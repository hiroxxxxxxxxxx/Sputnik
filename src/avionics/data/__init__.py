"""
Data: 型と Protocol の定義のみ。他モジュールに依存しない。

- raw: Layer 1 の型（PriceBar, RawCapitalSnapshot 等）。import は avionics.data.raw から。
- raw_market_snapshot: Layer 1 のスナップショット DTO（RawMarketSnapshot）。
- signals: Layer 2 の型（PriceSignals, SignalBundle 等）。import は avionics.data.signals から。
- fc_signals: Layer 3 の計器結論（EngineFactorMapping, FlightControllerSignal）。NQ/GC 固定のフィールドを持つ。import は avionics.data.fc_signals から。
- source: DataSource Protocol と BundleBuildOptions。FC.refresh に注入する。
"""
