# 未実装・暫定事項一覧

ソースコード内に散在していた TODO / 暫定仕様をここに集約する。
実装完了時は該当項目を削除し、対応するソースの暫定コメントも除去すること。

---

## 1. Protocol 注文系（IB 連携）

| 対象ファイル | 内容 |
|---|---|
| `src/protocols/booster_ignition_protocol.py` | Boost 適用時の IB 発注ロジックが未実装。`validate_margin` や約定確認が必要。 |
| `src/protocols/booster_cutoff_protocol.py` | Cutoff（Cruise 復帰）時の IB 発注ロジックが未実装。同上。 |
| `src/protocols/restoration_protocol.py` | Emergency 解除→Cruise 復旧時の IB 発注・段階的復旧ロジックが未実装。`validate_margin` 含む。 |

**背景**: 現在 Protocol は `Engine.apply_mode()` で目標差分を算出するのみ。
IB Gateway 連携により実際の発注（ExecutionProvider）を接続する段階で、
マージン検証・発注・約定確認・部分充当のフローを各 Protocol の `run()` に追加する。

---

## 2. Engine 執行反映（sync / ExecutionProvider）

| 対象ファイル | 内容 |
|---|---|
| `src/engines/engine.py` — `sync()` | 【予約】段階的パージ（Booster→Attitude→Main の順）の実行反映。定義書「6-2」参照。 |
| `src/engines/engine.py` — `apply_mode()` | `_executor` が注入されていれば `execute(all_deltas)` を呼ぶ設計だが、ExecutionProvider の実装は未着手。 |

**背景**: `Engine.calculate_deltas()` は差分を算出するが、実際の約定反映は ExecutionProvider（未実装）が担う。

---

## 3. Engine actual ポジション取得

| 対象ファイル | 内容 |
|---|---|
| `src/engines/engine.py` — `calculate_deltas()` | `actual` 未指定時は全て 0 とみなす（暫定）。IB 連携時に実ポジションを取得して渡す必要がある。 |

---

## 4. 高度（Altitude）を設定に集約

| 対象 | 内容 |
|---|---|
| `BundleBuildOptions` / `build_signal_bundle` | `v_altitude`, `c_altitude`, `r_altitude` が個別引数として散在。 |
| `VolatilitySignal` / `LiquiditySignals` | シグナル型に `altitude` フィールドがある。 |

**背景**: 高度は「運用レジーム（金利サイクルに応じた設定）」であり、データではなく設定。
現在は `build_signal_bundle` の引数とシグナル型のフィールドの両方に持ち、呼び出し側が毎回渡している。
factors.toml 等に `[regime] altitude = "high"` として一箇所で定義し、build 時と因子の両方がそれを参照する形に統一すると API が簡潔になる。
SQLite 計画の Phase 2-0（高度を3値に拡張）と合わせて実施が望ましい。

---

## 5. Daily Report カレンダー連携

| 対象ファイル | 内容 |
|---|---|
| `src/reports/format_daily_report.py` | メンテナンス行に「カレンダー連携は未実装のためスキップ」と表示。経済指標カレンダー API 等との連携が必要。 |

---

## 変更履歴

- 2026-03-24: 初版。ソースコード内の TODO を集約。
