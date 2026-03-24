"""
Data: 型と Protocol の定義のみ。他モジュールに依存しない。

- raw_types: Layer 1 の型（PriceBar, RawCapitalSnapshot 等）。
- raw_market_snapshot: Layer 1 のスナップショット DTO（RawMarketSnapshot）。
- signals: Layer 2 の型（PriceSignals, SignalBundle 等）。
- factor_mapping: エンジン↔因子のマッピング構造（EngineFactorMapping）。
- flight_controller_signal: Layer 3 の計器結論（FlightControllerSignal）。
- data_source: DataSource Protocol。FC.refresh に注入する。
"""
