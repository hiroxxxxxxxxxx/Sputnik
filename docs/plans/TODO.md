# 未実装・暫定事項一覧

ソースコード内に散在していた TODO / 暫定仕様をここに集約する。
実装完了時は該当項目を削除し、対応するソースの暫定コメントも除去すること。

---

## 1. Protocol 注文系（IB 連携）


| 対象ファイル                                       | 内容                                                                 |
| -------------------------------------------- | ------------------------------------------------------------------ |
| `src/protocols/booster_ignition_protocol.py` | Boost 適用時の IB 発注ロジックが未実装。`validate_margin` や約定確認が必要。               |
| `src/protocols/booster_cutoff_protocol.py`   | Cutoff（Cruise 復帰）時の IB 発注ロジックが未実装。同上。                              |
| `src/protocols/restoration_protocol.py`      | Emergency 解除→Cruise 復旧時の IB 発注・段階的復旧ロジックが未実装。`validate_margin` 含む。 |


**背景**: 現在 Protocol は `Engine.apply_mode()` で目標差分を算出するのみ。
IB Gateway 連携により実際の発注（ExecutionProvider）を接続する段階で、
マージン検証・発注・約定確認・部分充当のフローを各 Protocol の `run()` に追加する。

---

## 2. Engine 執行反映（sync / ExecutionProvider）


| 対象ファイル                                   | 内容                                                                             |
| ---------------------------------------- | ------------------------------------------------------------------------------ |
| `src/engines/engine.py` — `sync()`       | 【予約】段階的パージ（Booster→Attitude→Main の順）の実行反映。定義書「6-2」参照。                          |
| `src/engines/engine.py` — `apply_mode()` | `_executor` が注入されていれば `execute(all_deltas)` を呼ぶ設計だが、ExecutionProvider の実装は未着手。 |


**背景**: `Engine.calculate_deltas()` は差分を算出するが、実際の約定反映は ExecutionProvider（未実装）が担う。

---

## 3. Engine actual ポジション取得


| 対象ファイル                                         | 内容                                                     |
| ---------------------------------------------- | ------------------------------------------------------ |
| `src/engines/engine.py` — `calculate_deltas()` | `actual` 未指定時は全て 0 とみなす（暫定）。IB 連携時に実ポジションを取得して渡す必要がある。 |


---

## 4. ~~高度（Altitude）の設定集約~~（クローズ）

**結論**: 当初メモの「factors.toml に `[regime] altitude` を一本化」案は採用せず、**運用高度の正は SQLite `state.altitude`** とした。閾値テーブルは引き続き `factors.toml`（`get_*_thresholds`）で銘柄・レジーム別に保持する。

| 状態 | 内容 |
| --- | --- |
| 正の所在 | `store.state.read_altitude_regime(conn)` → `AltitudeRegime`（`high` / `mid` / `low`）。 |
| API | `BundleBuildOptions` / `build_signal_bundle` / `FlightController.refresh` は **`altitude` 単一引数**で V/C/R 計算に渡す（旧来の v/c/r 分離は解消）。 |
| Layer 2 型 | `VolatilitySignal` / `LiquiditySignals` に運用レジームフィールドは載せず、計算結果のみ保持する方針。 |
| テスト | `FlightController.refresh(..., altitude=...)` で DB なしの解決を許可。 |

**背景**: 高度は「データ系列に付随する値」ではなく運用状態のため、**DB の state を正**とし、各ティックで refresh 経路に乗せる設計に統一した。

---

## 5. Daily Report カレンダー連携


| 対象ファイル                               | 内容                                                      |
| ------------------------------------ | ------------------------------------------------------- |
| `src/reports/format_daily_report.py` | メンテナンス行に「カレンダー連携は未実装のためスキップ」と表示。経済指標カレンダー API 等との連携が必要。 |


**運用（確定）**: 日次レポートの Telegram 配信は**日本時間 7:00～8:00 頃**。`signal_daily` の日次書き込みは **NY クローズ後・1 日 1 回**。

---

## 6. V因子 1hノックイン監視の時間制御（バッチ側）


| 対象ファイル                                    | 内容                                                  |
| ----------------------------------------- | --------------------------------------------------- |
| `scripts/run_v_knockin_monitor.py`（新規/拡張） | 1hごと実行される監視バッチで、コアタイム判定・2本目以降の足判定・当日監視ウィンドウ管理を実装する。 |
| `src/store/knockin_watch.py`              | 監視対象日の生成/消込に加え、監視状態（未開始/監視中/成立/失効）の管理を必要に応じて拡張する。   |
| `src/avionics/compute.py`                 | 1h足の時刻制御ロジックは持たせず、バッチで選別済みの条件入力を受ける責務に寄せる。          |


**背景**: V因子の1hノックインは、日次バッチとは別に「1hごとの監視」で運用する。  
コアタイム開始・終了、30分開始銘柄の最初の不完全足除外、任意1h足成立判定などの時間制御はバッチ層で担保する。

---

## 7. ~~U/S 復帰確認の DB 化~~（クローズ）

**結論**: SPEC 準拠の **即時復帰 + on/off バッファ**へ変更済みのため、復帰確認日数の stateful カウンタ／DB 連続日数テーブルは**不要**。

| 状態 | 内容 |
| --- | --- |
| 実装 | `UFactor` / `SFactor` は `upgrade()` を使わず閾値により即時に `level` を更新。 |
| `BaseFactor.upgrade(..., recovery_confirm_satisfied_days=None)` | **P/V/C/R/T 向け経路のテスト**等で引き続き利用。量産の U/S 因子からは呼ばれない。 |
| 清掃 | 未使用だった `_apply_two_level_ratio` を削除。コメントを現状に合わせて更新。 |

`docs/archive/STATEFUL_AUDIT.md` の U/S 記述も本方針に合わせて更新済み。

---

## 8. Cockpit 現在モードの起動時復元


| 対象ファイル                   | 内容                                                                             |
| ------------------------ | ------------------------------------------------------------------------------ |
| `src/cockpit/cockpit.py` | 起動時に `state.effective_level` を読み、`_current_mode`（Boost/Cruise/Emergency）へ復元する。 |
| `src/store/state.py`     | 復元元データ（effective_level）の整合ルールを明文化し、必要に応じて参照ヘルパーを追加する。                          |
| `scripts/`*（Cockpit 起動口） | 初期モード固定指定と DB 復元の優先順位を統一する。                                                    |


**背景**: 現状は `approval_mode` / `execution_lock` は DB 復元できるが、`current_mode` は `initial_mode` 依存で再起動時に不一致が生じうる。  
起動直後のモード不整合を防ぐため、モード復元を DB 基準に統一する。

---

## 9. ~~FlightController の一時キャッシュ依存整理~~（方針変更でクローズ）


**結論**: DB 正への全面移行は採用しない。  
出力は **都度 `refresh` によるステートレス再計算**を正とし、`_last_bundle` / `_last_capital_snapshot` は「同一リクエスト内で直前 refresh 結果を参照する一時キャッシュ」として扱う。

| 状態 | 内容 |
| --- | --- |
| 出力経路 | `no refresh, no report` を運用ルール化（初回を含め、出力前に必ず `refresh`）。 |
| キャッシュ位置づけ | `get_last_bundle()` / `get_last_capital_snapshot()` は直前 refresh の一時参照用途に限定。 |
| 永続化 | `signal_daily` は日次の計器結論保存（履歴・監査用途）として維持。 |

**背景**: 課題だった再起動時の再現性は、A+B（未初期化ガード + 初回 refresh 完了まで非公開）と、都度 refresh 運用で解消できる。DB への全面寄せは複雑化の割に効果が小さいため見送る。

---

## 10. SQLite Phase 3（復旧・運用）の未着手タスク


| 対象 | 内容 |
| --- | --- |
| State / Mode 初期化経路 | 起動時に State/Mode を読み出し、初期値へ確実に反映する（高度・高度変更日・6ヶ月ルール判定を含む）。 |
| Signal 参照 API / スクリプト | 月次レビュー用に `signal_daily` を集計・参照・エクスポートする手段を追加する。 |
| 運用ドキュメント | バックアップ/復元手順（運用Runbook）を文書化し、必要なら補助スクリプトを用意する。 |
| `target_futures` 復元 | 再起動時・ロール/リバランス時に運用開始基準（part別目標先物枚数）を読み出して適用する。 |


**背景**: `archive/SQLITE_IMPLEMENTATION_PLAN.md` の Phase 3 は未着手。  
計画管理は本ファイルに統一し、未着手項目をここで追跡する。

---

## 11. 補助計器の永続化（後フェーズA）


| 対象 | 内容 |
| --- | --- |
| 補助計器算出ロジック | Realized Skew / Theta率 など SPEC 2-3 の算出実装を追加する。 |
| `signal_daily` スキーマ | 補助計器カラム追加マイグレーションを作成する。 |
| 日次バッチ | 因子レベルと同じ `as_of` で補助計器を 1 日 1 回保存する。 |


**背景**: 先行実装は因子レベル日次のみ。補助計器は算出ロジック未実装のため後フェーズ扱い。

---

## 12. 承認フラグ永続化（後フェーズB）


| 対象 | 内容 |
| --- | --- |
| `mode` テーブル | 承認待ちフラグ・待機中 signal 要約（必要なら）を保持する拡張を検討する。 |
| `Cockpit` 承認フロー | 承認待ち開始・承認・却下時の DB 更新を追加する。 |
| 復元仕様 | 再起動時に承認待ちをクリアするか復元するかを仕様化する。 |


**背景**: 注文/執行フローの実装進捗に依存するため、先行フェーズでは未対応。

---

## 13. ログ基盤（後フェーズC）


| 対象 | 内容 |
| --- | --- |
| ログテーブル | `advisory_log` / `execution_log` を設計・作成する。 |
| 記録ポイント | ADVISORY/CAUTION/WARNING、プロトコル実行、承認/却下のイベントを記録する。 |
| 運用ポリシー | 保持期間・削除/アーカイブ方針・バックアップ方針を定義する。 |


**背景**: 監査ログは後フェーズで要件確定し、まとめて実装する方針。

---

## 14. S因子の whatIf 取得と基準値比較（DBは基準値のみ）


| 対象 | 内容 |
| --- | --- |
| `src/store/`（state または専用テーブル） | S因子の**基準値（1枚あたりMM）**のみをDBで保持する。日次実測値はDB保存しない。 |
| `src/avionics/ib/fetcher.py` | 他因子と同タイミングの処理内で、銘柄ごとの whatIf を実行して 1枚あたりMM を取得する。 |
| `src/avionics/compute.py` / `src/avionics/factors/s_factor.py` | 取得した whatIf 値とDB基準値から S 比率を計算し、Sレベル判定に使う。 |
| `src/store/signal_daily.py` | 既存方針どおり、DBには判定結果のレベル（signal_daily）のみ保存する。 |
| `src/reports/format_breakdown_report.py` | 詳細内訳として「whatIf 実測値・基準値・比率」を表示できるようにする。 |


**背景**: S因子は「基準値は設定値としてDB保持」「whatIfは日次バッチで取得計算」「DB保存は最終レベルのみ」「詳細はbreakdown表示」という運用方針に統一する。

---

## 15. ~~因子インスタンスの `level` 永続化~~（クローズ）


**結論**: `level` の DB 永続化は採用しない。  
初期値露出は **A+B 方針**（A: API ガード、B: 起動時初回 refresh 完了まで非公開）で解消する。

| 状態 | 内容 |
| --- | --- |
| A: API ガード | `FlightController.get_flight_controller_signal()` は未初期化時（初回 `refresh` / `apply_all` 前）に例外を返す。 |
| B: 起動シーケンス | 呼び出し側は初回 `refresh` 成功後にのみ signal 参照・配信を行う。 |
| 永続化 | `signal_daily` は日次の計器結論保存として維持するが、因子インスタンス状態の復元用途には使わない。 |

**背景**: 再起動後は `refresh` を実行すれば現行シグナルからレベルを再計算できるため、復元データの複製管理よりも「未初期化の公開禁止」を優先する。

---

## 16. ~~運用高度（altitude）の DB 参照の責務整理~~（クローズ）


**結論**: `read_altitude_regime` の呼び出しは **オーケストレーション層**へ寄せ、`avionics` は `altitude` 引数のみ受け取る責務に統一した。

| 状態 | 内容 |
| --- | --- |
| `FlightController.refresh` | `conn` 引数を廃止し、`altitude` 必須に変更。`avionics` から `store` 依存を除去。 |
| `build_cockpit_stack` | `altitude` を外部注入に変更。組み立て時の DB 読み取りを削除。 |
| 呼び出し側 | `scripts` / `reports.fetch_reports` / `store.daily_signal` / `Cockpit.pulse` で `read_altitude_regime(conn)` を呼び、`refresh(..., altitude=...)` に渡す。 |
| テスト | `build_cockpit_stack` 呼び出しを `altitude=...` へ更新。 |

**確認**: `src/avionics` 配下に `store` import は残っていない。`read_altitude_regime` は境界モジュールのみで使用。

---

## 変更履歴

- 2026-03-24: 初版。ソースコード内の TODO を集約。
- 2026-03-25: 項目 4 更新（P2-0 高度3値拡張 実施済み。API集約のみ残存）。
- 2026-03-25: 項目 5 に運用スケジュール追記（Telegram JST 朝／DB 日次は NY クローズ後）。
- 2026-03-27: 項目 6 追加（V因子1hノックイン監視の時間制御をバッチ側で実装する方針を明記）。
- 2026-03-27: 項目 7 追加（U/S の復帰確認を stateful カウンタから DB 管理へ移行する方針を明記）。
- 2026-03-27: 項目 8 追加（Cockpit current_mode の起動時 DB 復元方針を明記）。
- 2026-03-27: 項目 9 追加（FlightController 一時キャッシュ依存を DB 基準へ段階移行する方針を明記）。
- 2026-03-27: 項目 10〜13 追加（SQLite 実装計画の残タスクを本ファイルへ集約）。
- 2026-03-27: 項目 14 追加（S因子 whatIf 取得・基準値比較の運用方針を明記）。
- 2026-03-29: 項目 7 クローズ（U/S は即時復帰へ変更済み。DB 化タスクは採用せず。BaseFactor 死蔵メソッド削除・監査メモ更新）。
- 2026-03-29: 項目 15 追加（因子 `level` / 復帰状態の DB 永続化は未着手。`altitude` は refresh 経路で DB 参照済み）。
- 2026-03-29: 項目 4 をクローズ（運用高度は DB `state` 正・単一 `altitude` API に統一。旧 factors.toml 案は不採用として明記）。項目 16 追加（`read_altitude_regime` の責務をオーケストレーション層へ寄せる未着手タスク）。
- 2026-03-29: 項目 15 を方針変更でクローズ（`level` 永続化は不採用。A+B: 未初期化 API ガード + 初回 refresh 完了まで非公開）。
- 2026-03-29: 項目 16 をクローズ（`read_altitude_regime` は境界層へ集約。`FlightController.refresh` は `altitude` 必須、`build_cockpit_stack` は `altitude` 外部注入へ変更）。
- 2026-03-29: 項目 9 を方針変更でクローズ（DB 正への全面移行は不採用。都度 refresh のステートレス再計算を正とし、一時キャッシュは同一リクエスト内参照に限定）。

