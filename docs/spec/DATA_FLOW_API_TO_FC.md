# API 取得から FlightController までのデータフロー（Layer 対応）

「どこで IB 接続が起こるか」「update_all で API が呼ばれるか」「どこで計算されるか」を Layer と対応付けて説明する。  
ib_async 依存は **avionics.ib** パッケージに集約されている（reports / scripts は `avionics.ib` のみ import）。

---

## 1. 結論の要約

| 段階 | API 呼び出し | 計算内容 | Layer | ファイル・クラス/関数 |
|------|--------------|----------|-------|----------------------|
| **IB 接続** | あり（エントリ側でトリガー） | なし | — | `avionics.ib.session`: `with_ib_fetcher`（**IBRawFetcher** を yield）/ `with_ib_connection` / `check_ib_connection`。呼び元は `reports/fetch_*` または `scripts/run_cockpit_with_ib.py` / `telegram_cockpit_bot.py`。 |
| **FC.refresh(data_source, as_of, symbols)** | 内部で data_source.fetch_raw（API 呼び出し） | 内部で build_signal_bundle → update_all | L1+L2+L3 入力 | `flight_controller.py`。DataSource（例: IBRawFetcher）から Raw 取得 → `build_signal_bundle`（`BundleBuildOptions` は FC 構築時注入）→ `_update_all_from_signals`。最後の bundle は `get_last_bundle()` で参照。 |
| **fetch_raw** | あり（reqHistoricalDataAsync 等） | なし（Raw を詰めるだけ） | Layer 1 | `avionics/ib/fetcher.py` の **IBRawFetcher.fetch_raw()**。FC.refresh 内で呼ばれる。 |
| **build_signal_bundle** | なし | あり（compute_* で Layer 2 算出） | Layer 2 | `avionics/bundle_builder.py`。FC.refresh 内から呼ばれる。 |
| **get_flight_controller_signal()** | なし | あり（因子 level → ICL/SCL/LCL） | Layer 3 出力 | `flight_controller.py` の `get_flight_controller_signal()`（引数なし）。`control_levels.compute_icl/scl/lcl`。戻り値は `FlightControllerSignal`（`data/flight_controller_signal.py`）。 |

**FlightController.apply_all が呼ばれるとき、API は一切呼ばれない。** 渡された SignalBundle を因子に配布し、各因子が自分の level を更新するだけ。

---

## 2. トリガー: 誰が IB 接続するか

IB 接続（`ib.connectAsync(...)`）は **avionics.ib.session** 内で行われ、トリガーは常にエントリ（reports / scripts）側。

| トリガー | 場所 | やること |
|----------|------|----------|
| **レポート取得（Telegram /cockpit 等）** | `reports/fetch_reports.py` の `fetch_cockpit_report` / `fetch_breakdown_report` / `fetch_daily_report` | `with_ib_fetcher` で **IBRawFetcher** を取得 → `build_cockpit_stack(symbols)` で FC 取得 → `fc.refresh(fetcher, as_of, symbols)` → `format_*(fc, ...)`（bundle は formatter 内で fc.get_last_bundle() を使用）。 |
| **CLI サンプル** | `scripts/run_cockpit_with_ib.py` | 同上。`with_ib_fetcher` → `fc.refresh(fetcher, as_of, symbols)` → `fc.get_flight_controller_signal()` / `fc.get_last_bundle()`。 |
| **取引時間スキャン（/schedule）** | `scripts/telegram_cockpit_bot.py` の `fetch_schedule_alerts` | `avionics.ib.with_ib_connection` で接続 → `avionics.ib.run_daily_schedule_scan(ib, symbols)`。 |
| **Gateway 起動完了通知** | `scripts/telegram_cockpit_bot.py` の `_notify_gateway_ready`（post_init で起動） | `avionics.ib.check_ib_connection(host, port, ...)` で接続試行のみ。成功時「起動完了」、失敗時「接続できませんでした」を Telegram 送信。 |

FlightController も Cockpit も **IB を参照しない**。接続と取得タイミングはすべて reports / scripts が決める。

---

## 2.1 avionics.ib の構成

| モジュール | 役割 |
|------------|------|
| **session** | `with_ib_fetcher`（**IBRawFetcher** を yield）、`with_ib_connection`（生の `ib` を yield）、`check_ib_connection`（成否のみ）。接続・切断をここに集約。reports/scripts は fetcher を FC.refresh に渡す。 |
| **fetcher** | **IBRawFetcher**: Layer 1 のみ。`fetch_raw` で CachedRawDataProvider に詰める。FC.refresh に注入する DataSource の実装。 |
| **schedule_scan** | `run_daily_schedule_scan(ib, symbols)`。取引時間（tradingHours）取得と DST・短縮・休場の通知。`with_ib_connection` と組み合わせて利用。 |

**IBSignalBundleFetcher は廃止済み。** SignalBundle は FC.refresh のあと `fc.get_last_bundle()` でのみ取得する。  
Raw 取得窓口は `avionics.ib.IBRawFetcher` を直接利用する（re-export は行わない）。`avionics.ib_data` は廃止済み。

---

## 3. レポート取得フローの詳細（Layer 対応）

例: `/cockpit` や `run_cockpit_with_ib` で「計器レポート文字列が欲しい」場合。

```
[エントリ] reports.fetch_cockpit_report(host, port, symbols) または run_cockpit_with_ib
    │
    ▼
① IB 接続（avionics.ib.session）
    async with with_ib_fetcher(host, port, ...) as fetcher:
    # fetcher の型は IBRawFetcher（DataSource の実装）
    fc, _ = build_cockpit_stack(symbols)
    │
    ▼
② 最新取得・bundle 組み立て・因子更新（FC.refresh）
    await fc.refresh(fetcher, as_of, symbols)
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
| **接続** | `avionics/ib/session.py` | `with_ib_fetcher`（IBRawFetcher を yield）/ `with_ib_connection` / `check_ib_connection`。 | あり（接続時） |
| **FC.refresh** | `avionics/flight_controller.py` | DataSource（例: IBRawFetcher）を渡すと、内部で fetch_raw → build_signal_bundle（BundleBuildOptions 使用）→ update_all。最後の bundle は get_last_bundle() で取得。 | 内部で fetch_raw が API 呼び出し |
| **Layer 1（Raw 取得）** | `avionics/ib/fetcher.py` の **IBRawFetcher** | `fetch_raw`: reqHistoricalDataAsync / accountSummaryAsync で Raw を取得。FC.refresh に注入する DataSource の実装。 | **あり** |
| **Layer 1（型）** | `avionics/data/raw.py`, `data/cache.py` | Raw の型定義と CachedRawDataProvider。計算なし。 | なし |
| **Layer 2（Signals）** | `avionics/process/layer2/bundle_builder.py` + `compute.py` | `build_signal_bundle`: compute_price_signals / compute_volatility_signal / compute_liquidity_signals_* / compute_capital_signals で SignalBundle を組み立てる。 | なし |
| **Layer 3 入力** | `avionics/flight_controller.py` の `update_all(signal_bundle=bundle)` | SignalBundle を各因子に配布。各因子が `update_from_signal_bundle` で level を更新。 | なし |
| **Layer 3 出力** | `flight_controller.py` の `get_flight_controller_signal` + `control_levels.py` | 因子の level から ICL / SCL / LCL を算出し FlightControllerSignal を返す。 | なし |
| **表示** | `reports/format_*.py` | FlightControllerSignal と fc.mapping からレポート文字列を組み立て。 | なし |


---

## 5. よくある整理

- **「update_all したときは API は呼ばれず、データ計算のみ」**  
  → その通り。`update_all(signal_bundle=bundle)` は手元の bundle を因子に配布し、各因子が level を更新するだけ。IB 等の API は呼ばない。
- **「どこから IB 接続がトリガーされるか」**  
  → reports の `fetch_*` または scripts（run_cockpit_with_ib / telegram_cockpit_bot）が、レポート・計器・取引時間・起動通知が必要なタイミングで `avionics.ib` の `with_ib_fetcher` / `with_ib_connection` / `check_ib_connection` を呼ぶ。FlightController はその後に登場し、bundle を受け取って update_all → get_flight_controller_signal するだけ。
- **「レポート取得の流れ」**  
  → reports は `with_ib_fetcher` で **IBRawFetcher** を取得し、`build_cockpit_stack(symbols)` で FC を取得したあと、`fc.refresh(fetcher, as_of, symbols)` で最新取得・bundle 組み立て・因子更新を一括実行。表示時は `fc.get_flight_controller_signal()` と `fc.get_last_bundle()` を利用。FC 構築時の `BundleBuildOptions`（assembly が config から組み立て）で build_signal_bundle のオプションを指定。

この流れは定義書「4-2 情報の階層構造」および `docs/proposals/LAYER_SCRIPT_REPORTS_FC.md` と整合している。