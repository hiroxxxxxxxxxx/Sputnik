# FlightController と scripts / reports の公開・隠蔽レイヤー改善案

## 1. 現状の問題

- **scripts/telegram_cockpit_bot.py** が次の責務をすべて持っている。
  - Telegram API の注入（token, chat_id）・IB 接続情報（host, port）の読み取り … **注入として妥当**
  - IB 接続・`fetch_signal_bundle` の呼び出し（`liquidity_credit_symbol`, `v_recovery_params`, `load_factors_config` 等の知識）
  - `build_cockpit_stack(symbols)` による FC 構築
  - `fc.update_all(signal_bundle=bundle)` の実行
  - `format_cockpit_report(fc, symbols, now_utc, bundle)` 等の formatter 呼び出し
- その結果、**Script が「データ取得・FC 更新・表示」のオーケストレーションまで知っており**、FlightController の戻り値を reports の formatter に任せるという流れがはっきりしていない。
- 同じ「IB 接続 → bundle 取得 → (FC 更新) → format」が `fetch_cockpit_report` / `fetch_daily_report` / `fetch_breakdown_report` で重複している。

## 2. 望ましい流れ

1. **API 情報の注入**: Script は **環境変数（TELEGRAM_TOKEN, IBKR_HOST, IBKR_PORT, TELEGRAM_COCKPIT_SYMBOLS）の読み取りと Telegram への送信**だけを行う。
2. **基本処理は FlightController に委譲**: 「計器の結論」は FC が `get_flight_controller_signal(bundle)` で返す。Script は FC を直接触らない。
3. **表示は reports の formatter に委譲**: 「レポート文字列が欲しい」という要求は **reports の公開 API 一発**で満たし、その戻り値を Script はそのまま送信する。

つまり:

- **Script**: 注入 + 「レポート文字列を返す API」の呼び出し + その文字列の送信。
- **Reports**: 「(host, port, symbols) から計器レポート文字列を返す」公開 API を提供。内部で IB 接続・bundle 取得・FC 構築・`update_all`・formatter 呼び出しを行う。
- **FlightController**: 変更なし。reports が fc.update_all(bundle) のうえで formatter(fc, …) を呼ぶ。

## 3. 改善案（責務の切り分け）


| レイヤー                                            | 責務                                                                                                              | 公開するもの / 隠蔽するもの                                                                                                                                                                                       |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Script (telegram_cockpit_bot)**               | Telegram の起動・コマンド受付・**API 情報の注入**（env から host, port, symbols を渡す）。レポート文字列の取得は **reports の 1 関数呼び出し**に委譲。        | **隠蔽**: IB 接続の詳細、build_cockpit_stack、load_factors_config、format_* の引数。**公開**: なし（呼び出し側なので「何を注入するか」だけ）。                                                                                                |
| **Reports**                                     | 「計器レポート文字列」「Daily 文字列」「Breakdown 文字列」を返す **公開 API** を提供。その中で IB 接続・bundle 取得・FC 構築・update_all・既存 formatter を実行。 | **公開**: `fetch_cockpit_report(host, port, symbols) -> str`, `fetch_daily_report(...)`, `fetch_breakdown_report(...)`（いずれも async）。**隠蔽**: IB/client_id/timeout、factors config、build_cockpit_stack の詳細。 |
| **FlightController**                            | 三層算出と `get_flight_controller_signal(bundle)` のみ。                                                                | 変更なし。reports が fc を組み立てて update_all → formatter(fc, …) と使う。                                                                                                                                           |
| **Reports formatter (format_cockpit_report 等)** | fc と bundle（と symbols 等）を受け取り、レポート文字列を返す。                                                                       | 変更なし。**呼び出し元**を「reports の fetch_*」にすることで、Script は formatter を直接知らなくする。                                                                                                                                |


## 4. 具体的な変更

### 4.1 reports に「取得オーケストレーション」を追加

- **新規** `reports/fetch_reports.py`（または既存の `format_cockpit_report.py` の隣に `cockpit_fetcher.py` など）を置く。
- 次の 3 関数を **reports の公開 API** として定義する（中身は現在の `scripts/telegram_cockpit_bot.py` の `fetch_cockpit_report` / `fetch_breakdown_report` / `fetch_daily_report` を移動したもの）。
  - `async def fetch_cockpit_report(host: str, port: int, symbols: list[str], *, client_id: int = 3, timeout: float = 75) -> str`
  - `async def fetch_breakdown_report(host: str, port: int, symbols: list[str], ...) -> str`
  - `async def fetch_daily_report(host: str, port: int, symbols: list[str], ...) -> str`
- 各関数の内部で行うこと:
  1. IB に接続（host, port, client_id, timeout）
  2. （必要なら）factors config を読んで `v_recovery_params` 等を組み立て
  3. `IBDataFetcher(ib).fetch_signal_bundle(...)` で bundle 取得
  4. cockpit/daily の場合は `build_cockpit_stack(symbols)` → `fc.update_all(bundle)` → `format_cockpit_report(fc, symbols, now_utc, bundle)` または `format_daily_flight_log(fc, bundle, symbols, ...)`
  5. breakdown の場合は `format_breakdown_report(bundle)`
  6. 最後に `ib.disconnect()`（try/finally）
  7. レポート文字列を返す

### 4.2 scripts/telegram_cockpit_bot.py のスリム化

- `fetch_cockpit_report`, `fetch_breakdown_report`, `fetch_daily_report` の **定義を削除**し、代わりに **reports から import** する。
  - 例: `from reports.fetch_reports import fetch_cockpit_report, fetch_breakdown_report, fetch_daily_report`
- コマンドハンドラでは、env から `host`, `port`, `symbols` を組み立て、上記 `fetch_`* を **引数 (host, port, symbols) で 1 回呼ぶ**だけにする。
- IB 接続・build_cockpit_stack・load_factors_config・format_* への参照は Script からは **一切削除**する。

### 4.3 オプション: 接続情報のまとめ渡し

- 複数パラメータをまとめる場合は、例えば `reports` 側で `ConnectionParams(host, port, client_id, timeout)` のような小さな dataclass を用意し、Script は env からそれを組み立てて `fetch_cockpit_report(params, symbols)` のように渡してもよい。その場合でも、Script は「接続情報と銘柄リスト」だけを渡し、中身は reports に閉じる。

## 5. まとめ

- **Script**: API 情報を注入し、「レポート文字列を返す関数」を **reports の 1 API** で呼ぶ。処理内容は知らない。
- **Reports**: 「host, port, symbols からレポート文字列を返す」公開 API を提供し、その中で IB 取得・FC 更新・既存 formatter を実行する。
- **FlightController**: 従来どおり。reports が fc を組み立てて使い、戻り値を formatter に渡して表示文字列を得る。

これにより、公開・隠蔽のレイヤーが「Script = 注入と送信」「Reports = 取得オーケストレーション + 表示」「FC = 計器結論」と明確になる。

---

## 6. 補足: 二点の整理

### 6.1 Script で API 情報を「注入」する案は適切か

**二通りあり得る。**

- **案 A（現案）: Script が env を読んで渡す**  
  Script が `IBKR_HOST`, `IBKR_PORT`, `TELEGRAM_COCKPIT_SYMBOLS` を読み、`fetch_cockpit_report(host, port, symbols)` に渡す。  
  - 利点: 接続先・銘柄が「呼び出しの引数」として明示され、テストで host/port/symbols を差し替えやすい。  
  - 注入というより「プロセス入口（Script）で設定を読み、レポート取得 API に渡す」という意味で適切。

- **案 B: Fetcher が env を読む**  
  `fetch_cockpit_report()` を引数なし（または `report_type="cockpit"` だけ）にし、reports 側で `os.environ.get("IBKR_HOST", ...)` を読む。  
  - 利点: Script は「レポート取得」と「送信」だけを知り、さらに薄くなる。  
  - 欠点: 接続先が fetcher に固定され、テストでは env の差し替えやモックが必要。

**結論**: 「API 情報をどこで読むか」は設計の好み。  
- テストや複数環境を引数で切り替えたいなら **案 A（Script が env を読んで渡す）** が適切。  
- Script を「トリガー専用」にしたいなら **案 B** も可。その場合でも「注入」は「プロセス起動時の env」であり、Script が渡すのではなく fetcher が読む形になる。

### 6.2 `update_all(signal_bundle)` の引数は必要か

**必要。** FlightController は「データの取得」を持たない方がよい。

- **現状の役割分担**
  - **bundle を持つ側**（reports の fetch_* や、Cockpit を動かすオーケストレータ）が、IB 等から SignalBundle を取得する。
  - その bundle を **引数で** `fc.update_all(signal_bundle=bundle)` に渡す。
  - FC は「渡された bundle を因子に配布する」だけに専念する。

- **もし `update_all()` に bundle を渡さないとすると**
  - FC の内部で「どこかから bundle を取得する」必要が出る。
  - すると FC が IB や Fetcher に依存し、計器層がデータ取得層に縛られる（レイヤー混合）。

- **`signal_bundle` を Optional にしている理由**
  - 渡す場合: Layer 2 の bundle を因子に配布する（本番・レポート・サブスクリプション想定）。
  - 渡さない場合: 各因子の `update()` だけ実行（テストや、因子が自分でデータを持つ構成）。

**結論**: `update_all(signal_bundle=...)` の引数は、**FC がデータ取得に依存しない**ようにするために必要。呼び出し側が「bundle を取得 → update_all(bundle) → get_flight_controller_signal(bundle)」と渡す現状の形が適切。