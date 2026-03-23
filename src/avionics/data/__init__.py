"""
Data: 型と Protocol の定義のみ。他モジュールに依存しない。

- raw: Layer 1 の型と RawDataProvider（Protocol）。import は avionics.data.raw から。
- cache: RawDataProvider の汎用実装（CachedRawDataProvider）。import は avionics.data.cache から。
- signals: Layer 2 の型（PriceSignals, SignalBundle 等）。import は avionics.data.signals から。
- fc_signals: Layer 3 の計器結論（EngineFactorMapping, FlightControllerSignal）。NQ/GC 固定のフィールドを持つ。import は avionics.data.fc_signals から。
"""
