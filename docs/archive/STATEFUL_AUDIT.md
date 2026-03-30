# ステートフル箇所の洗い出し（サーバ定期再起動前提）

原則: 再起動でリセットされると**判定結果や運用**に影響する状態は持たない。

---

## 1. 判定ロジックに影響

### 1.1 U/S 因子（対応済み・2026-03）

| 項目 | 内容 |
|------|------|
| 実装 | `UFactor` / `SFactor` は **即時復帰**（on/off バッファ）。`upgrade()` 不使用。 |
| `BaseFactor` の `_confirm_*` | `upgrade(..., recovery_confirm_satisfied_days=None)` 用。**量産 U/S からは未使用**（テスト・他用途向け経路）。 |

旧案の「証拠金日次でステートレス化／DB 連続日数」は、SPEC 変更により **不要**（`docs/plans/TODO.md` 項目 7 クローズ）。

---

### 1.2 V 因子（対応済み）

V はステートレス専用に変更済み。`update_from_index` は `recovery_confirm_satisfied_days_v1_off` / `v2_off` を必須引数とし、stateful 経路は廃止。`update()` は未実装（基底の NotImplementedError）。必ず `update_from_volatility_signal(vol)` で更新する。

---

## 2. 表示・UI のみ（再起動で消えるが判定には使わない）

| 場所 | 変数 | 説明 |
|------|------|------|
| `base_factor.py` | `history` (deque) | レベル履歴。`record_level()` で append。本番では参照していない（テストのみ）。再起動で空になる。 |

**対応方針（実施済み）**: 復帰「x/N日目」の表示用キャッシュ（`_last_recovery_display`, V の `_last_recovery_*`）は廃止した。表示時は `get_cockpit_signal(symbol, bundle)` に bundle を渡し、`EngineFactorMapping.get_recovery_progress(symbol, bundle)` 内で各ステートレス因子の `get_recovery_progress_from_bundle(symbol, bundle)` を呼んでその場で算出する。bundle 未渡しの場合は `recovery_confirm_progress()` にフォールバック（U/S は即時復帰のため通常 None）。呼び出し元（`run_cockpit_with_ib.py`, `format_daily_report.py`, `format_cockpit_report`）は bundle を渡すよう変更済み。

---

## 3. ランタイム・セッション状態（再起動でリセット）

### 3.1 FlightController

| 場所 | 変数 | 説明 |
|------|------|------|
| `flight_controller.py` | `_current_mode` | 現在のスロットルモード。再起動で `initial_mode` に戻る。 |
| `flight_controller.py` | `_pending_approval_signal`, `_approval_wait_id`, `_approval_event` | Manual 承認待ちの 1 件分。再起動で消える（待機中は再起動しない運用なら影響小）。 |

**対応方針**: `_current_mode` は再起動後に `pulse()` で Cockpit から再取得する設計なら、実質「次回 pulse まで初期値」でよい。承認待ちは再起動で失うことを仕様として明記するか、永続化するか検討。

---

### 3.2 Engine / Part

（`_last_instruction` は未使用のため削除済み。Part 階層は廃止され Engine が Blueprint を直接管理。）

---

## 4. リクエスト／1 回の fetch 内のみ（再起動をまたがない）

| 場所 | 説明 |
|------|------|
| `ib_data.py` | `CachedRawDataProvider` の `_price_bars`, `_tip_bars` 等 | `fetch_signal_bundle` の 1 回の呼び出し内でだけ保持。再起動とは無関係。 |

**対応方針**: 対象外（ステートフルではない）。

---

## 5. 因子の level 自体

| 場所 | 説明 |
|------|------|
| 全因子 | `self.level` | 再起動で `__init__` の初期値（通常 0）に戻る。次回 `update_all(signal_bundle)` で bundle を渡せば再計算される。 |

**対応方針**: 「定期で bundle 取得 → update_all」していれば実質ステートレス。再起動直後〜次回取得まではレベル 0 になることを仕様として許容するか、起動直後に 1 回 fetch する運用にする。

---

## まとめ（原則禁止に直結するもの）

| # | 箇所 | 内容 | 推奨 |
|---|------|------|------|
| 1 | ~~BaseFactor（U/S）~~ | ~~復帰カウンタ stateful~~ | **対応済み**: U/S 即時復帰。DB 化は不採用 |
| 2 | ~~VFactor~~ | ~~stateful フォールバック~~ | **対応済み**: ステートレス専用・必須引数化 |
| 3 | FlightController | 現在モード・承認待ち | 再起動で初期値／失効を仕様として明記 |
| 4 | Part | ~~_last_instruction~~ | **削除済み** |

その他（表示用キャッシュ・history・CachedRawDataProvider）は再起動で消えても**判定**には使っていないため、原則禁止の対象外とするか、必要に応じて表示だけ永続化する。
