# ステートフル箇所の洗い出し（サーバ定期再起動前提）

原則: 再起動でリセットされると**判定結果や運用**に影響する状態は持たない。

---

## 1. 判定ロジックに影響（要対応）

### 1.1 復帰ヒステリシスの stateful カウンタ（U/S 因子）

| 場所 | 変数 | 説明 |
|------|------|------|
| `base_factor.py` | `_target_level`, `_confirm_counter`, `_confirm_days_required` | U 因子・S 因子が `upgrade(..., recovery_confirm_satisfied_days=None)` で使用。日をまたいで加算され、再起動で 0 に戻る。復帰判定が「やり直し」になる。 |

**対応方針**: 証拠金（U/S）の日次履歴を API または DB で取得し、基準日から遡って連続日数を数えるステートレス化（P/R/C/T と同様）。取得できない場合は「再起動後は復帰カウント 0 から」を仕様として明示。

---

### 1.2 V 因子（対応済み）

V はステートレス専用に変更済み。`update_from_index` は `recovery_confirm_satisfied_days_v1_off` / `v2_off` を必須引数とし、stateful 経路は廃止。`update()` は未実装（基底の NotImplementedError）。必ず `update_from_volatility_signal(vol)` で更新する。

---

## 2. 表示・UI のみ（再起動で消えるが判定には使わない）

| 場所 | 変数 | 説明 |
|------|------|------|
| `base_factor.py` | `history` (deque) | レベル履歴。`record_level()` で append。本番では参照していない（テストのみ）。再起動で空になる。 |

**対応方針（実施済み）**: 復帰「x/N日目」の表示用キャッシュ（`_last_recovery_display`, V の `_last_recovery_*`）は廃止した。表示時は `get_cockpit_signal(symbol, bundle)` に bundle を渡し、`EngineFactorMapping.get_recovery_progress(symbol, bundle)` 内で各ステートレス因子の `get_recovery_progress_from_bundle(symbol, bundle)` を呼んでその場で算出する。bundle 未渡しの場合は U/S のみ `recovery_confirm_progress()` で stateful な値を返す。呼び出し元（`run_cockpit_with_ib.py`, `format_daily_report.py`, `format_cockpit_report`）は bundle を渡すよう変更済み。

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
| 1 | BaseFactor（U/S） | 復帰カウンタ stateful | 証拠金の日次履歴でステートレス化、または仕様明示 |
| 2 | ~~VFactor~~ | ~~stateful フォールバック~~ | **対応済み**: ステートレス専用・必須引数化 |
| 3 | FlightController | 現在モード・承認待ち | 再起動で初期値／失効を仕様として明記 |
| 4 | Part | ~~_last_instruction~~ | **削除済み** |

その他（表示用キャッシュ・history・CachedRawDataProvider）は再起動で消えても**判定**には使っていないため、原則禁止の対象外とするか、必要に応じて表示だけ永続化する。
