# API 取得から FlightController までのデータフロー（補助資料）

> [!IMPORTANT]
> この文書は `ARCHITECTURE.md` の補助資料です。  
> 責務境界・依存ルール・運用ガードレールの正本は `docs/spec/ARCHITECTURE.md` を優先してください。

「どこで IB 接続が起こるか」「`apply_all` で API が呼ばれるか」「どこで計算されるか」を Layer と対応付けて説明する。  
ib_async 依存は **avionics.ib** パッケージに集約されている（エントリポイントは `avionics.ib` を介して利用）。

---

## 1. 結論の要約

| 段階 | API 呼び出し | 計算内容 | Layer | ファイル・クラス/関数 |
|------|--------------|----------|-------|----------------------|
| **IB 接続** | あり（エントリ側でトリガー） | なし | — | `avionics.ib.infra.session`: `with_ib_market_data_service`（`IBMarketDataService` を yield）/ `with_ib_connection` / `check_ib_connection`。主な呼び元は `scripts/*`。 |
| **FC.refresh(data_source, as_of, symbols)** | 内部で data_source.fetch_raw（API 呼び出し） | 内部で build_signal_bundle → update_all | L1+L2+L3 入力 | `flight_controller.py`。DataSource（例: `IBMarketDataService`）から Raw 取得 → `build_signal_bundle`（`BundleBuildOptions` は FC 構築時注入）→ `_update_all_from_signals`。最後の bundle は `get_last_bundle()` で参照。 |
| **fetch_raw** | あり（reqHistoricalDataAsync 等） | なし（Raw を詰めるだけ） | Layer 1 | `avionics/ib/services/market_data_service.py` の `IBMarketDataService.fetch_raw()`。実際の I/O は `clients/*` が担当。 |
| **build_signal_bundle** | なし | あり（compute_* で Layer 2 算出） | Layer 2 | `avionics/process/layer2/bundle_builder.py`。FC.refresh 内から呼ばれる。 |
| **get_flight_controller_signal()** | なし | あり（因子 level → ICL/SCL/LCL） | Layer 3 出力 | `flight_controller.py` の `get_flight_controller_signal()`（引数なし）。ICL/SCL/LCL 算出は `FlightController` のメソッド内で直接実行。戻り値は `FlightControllerSignal`（`data/flight_controller_signal.py`）。 |

**FlightController.apply_all が呼ばれるとき、API は一切呼ばれない。** 渡された SignalBundle を因子に配布し、各因子が自分の level を更新するだけ。

---

## 2. トリガー: 誰が IB 接続するか

IB 接続（`ib.connectAsync(...)`）は **avionics.ib.infra.session** 内で行われ、トリガーは常にエントリ（scripts / bot）側。

| トリガー | 場所 | やること |
|----------|------|----------|
| **レポート取得（Telegram /cockpit 等）** | `scripts/telegram_cockpit_bot.py` の `_fetch_*_report` | `with_ib_market_data_service` で `IBMarketDataService` を取得 → `build_cockpit_stack(symbols)` で FC 取得 → `fc.refresh(service, as_of, symbols)` → `format_*(fc, ...)`。 |
| **CLI サンプル** | `scripts/run_cockpit_with_ib.py` | 同上。`with_ib_market_data_service` → `fc.refresh(service, as_of, symbols)` → `fc.get_flight_controller_signal()` / `fc.get_last_bundle()`。 |
| **取引時間スキャン（/schedule）** | `scripts/telegram_cockpit_bot.py` の `fetch_schedule_alerts` | `avionics.ib.with_ib_connection` で接続 → `IBScheduleService(ib).run_daily_schedule_scan(symbols)`。 |
| **Gateway 起動完了通知** | `scripts/telegram_cockpit_bot.py` の `_notify_gateway_ready`（post_init で起動） | `avionics.ib.check_ib_connection(host, port, ...)` で接続試行のみ。成功時「起動完了」、失敗時「接続できませんでした」を Telegram 送信。 |

FlightController も Cockpit も **IB を参照しない**。接続と取得タイミングはすべて reports / scripts が決める。

---

## 2.1 avionics.ib の構成（現行）

| モジュール | 役割 |
|------------|------|
| **infra/session** | `with_ib_market_data_service`（`IBMarketDataService` を yield）、`with_ib_connection`（生の `ib` を yield）、`check_ib_connection`（成否のみ）。接続・切断をここに集約。 |
| **services** | ユースケース層。`market_data_service` / `whatif_order_service` / `schedule_service` / `healthcheck_service`。 |
| **clients** | IB API I/O 層。`market_client` / `account_client` / `whatif_order_client` / `schedule_client`。 |
| **models** | contracts, fetch_results, schedule DTO。 |

SignalBundle は FC.refresh のあと `fc.get_last_bundle()` でのみ取得する。

---

## 3. レポート取得フローの詳細（Layer 対応）

例: `/cockpit` や `run_cockpit_with_ib` で「計器レポート文字列が欲しい」場合。

```
[エントリ] scripts/telegram_cockpit_bot.py または run_cockpit_with_ib
    │
    ▼
① IB 接続（avionics.ib.infra.session）
    async with with_ib_market_data_service(host, port, ...) as service:
    # service の型は IBMarketDataService（DataSource の実装）
    fc, _ = build_cockpit_stack(symbols)
    │
    ▼
② 最新取得・bundle 組み立て・因子更新（FC.refresh）
    await fc.refresh(service, as_of, symbols)
    │   ├─ data_source.fetch_raw(...)  ← ここで IB API（reqHistoricalDataAsync 等）
    │   ├─ build_signal_bundle(cache, as_of, ...)  [BundleBuildOptions は FC 構築時注入]
    │   ├─ _last_bundle / _last_capital_snapshot を保持
    │   └─ _update_all_from_signals(bundle)  → 各因子の update_from_signal_bundle
    │
    ▼
③ Layer 3 出力（計器結論）
    signal = await fc.get_flight_controller_signal()   # 引数なし
    │   → compute_icl / compute_scl / compute_lcl で FlightControllerSignal を返す
    │
    ▼
④ 表示
    format_cockpit_report(fc, symbols, now_utc, bundle=fc.get_last_bundle())
    → Script が Telegram に送信（または CLI が表示）
```

---

## 4. Layer と処理の対応表

| Layer | モジュール・型 | 処理内容 | API |
|-------|----------------|----------|-----|
| **接続** | `avionics/ib/infra/session.py` | `with_ib_market_data_service`（IBMarketDataService を yield）/ `with_ib_connection` / `check_ib_connection`。 | あり（接続時） |
| **FC.refresh** | `avionics/flight_controller.py` | DataSource（例: IBMarketDataService）を渡すと、内部で fetch_raw → build_signal_bundle（BundleBuildOptions 使用）→ update_all。最後の bundle は get_last_bundle() で取得。 | 内部で fetch_raw が API 呼び出し |
| **Layer 1（Raw 取得）** | `avionics/ib/services/market_data_service.py` | `fetch_raw`: clients を介して reqHistoricalDataAsync / accountSummaryAsync などで Raw を取得。 | **あり** |
| **Layer 1（型）** | `avionics/data/raw_types.py`, `data/cache.py` | Raw の型定義と CachedRawDataProvider。計算なし。 | なし |
| **Layer 2（Signals）** | `avionics/process/layer2/bundle_builder.py` + `compute.py` | `build_signal_bundle`: compute_price_signals / compute_volatility_signal / compute_liquidity_signals_* / compute_capital_signals で SignalBundle を組み立てる。 | なし |
| **Layer 3 入力** | `avionics/flight_controller.py` の `update_all(signal_bundle=bundle)` | SignalBundle を各因子に配布。各因子が `update_from_signal_bundle` で level を更新。 | なし |
| **Layer 3 出力** | `flight_controller.py` の `get_flight_controller_signal` | 因子の level から ICL / SCL / LCL を算出し FlightControllerSignal を返す。 | なし |
| **表示** | `reports/format_*.py` | FlightControllerSignal と fc.mapping からレポート文字列を組み立て。 | なし |


---

## 5. よくある整理

- **「update_all したときは API は呼ばれず、データ計算のみ」**  
  → その通り。`update_all(signal_bundle=bundle)` は手元の bundle を因子に配布し、各因子が level を更新するだけ。IB 等の API は呼ばない。
- **「どこから IB 接続がトリガーされるか」**  
  → reports の `fetch_*` または scripts（run_cockpit_with_ib / telegram_cockpit_bot）が、レポート・計器・取引時間・起動通知が必要なタイミングで `avionics.ib` の `with_ib_market_data_service` / `with_ib_connection` / `check_ib_connection` を呼ぶ。FlightController はその後に登場し、bundle を受け取って update_all → get_flight_controller_signal するだけ。
- **「レポート取得の流れ」**  
  → reports は `with_ib_market_data_service` で `IBMarketDataService` を取得し、`build_cockpit_stack(symbols)` で FC を取得したあと、`fc.refresh(service, as_of, symbols)` で最新取得・bundle 組み立て・因子更新を一括実行。表示時は `fc.get_flight_controller_signal()` と `fc.get_last_bundle()` を利用。FC 構築時の `BundleBuildOptions`（assembly が config から組み立て）で build_signal_bundle のオプションを指定。

この流れは定義書「4-2 情報の階層構造」および `docs/spec/ARCHITECTURE.md` と整合している。