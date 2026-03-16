# 復帰確認「x日目」仕様（営業日遡り・プロセスキャッシュ廃止）

プロセス内の `_confirm_counter` は廃止し、**復帰判定パスに入った時点で過去営業日を遡って「連続何日条件を満たしたか」を計算する**設計。  
本ドキュメントは候補案の評価と、**採用すべき実装構成**を定める。

---

## 1. 各案の評価（システム憲章・OS構造の観点）

| 案 | 憲章・原則への適合性 | 実装の堅牢性（再起動耐性） | 評価・コメント |
| --- | --- | --- | --- |
| **案1** | **最高**（Layer 3 を単機能に保てる） | 高い | **推奨。** 因子（Layer 3）は「自分が何日目か」を管理せず、渡された「事実（日数）」で判定するのみ。憲章Ⅷに合致。 |
| **案2** | 中（Layer 3 に計算負荷が漏れる） | 高い | デバッグ性は良いが、Layer 3 が「日付リストを走査する」ロジックを持つのは階層分離の観点からやや過剰。 |
| **案3** | 高（Raw Data 層の効率化） | 高い | API 呼出の効率化として案1と併用すべき実務的な最適化案。 |
| **案4** | 中（市場実態との乖離リスク） | 高い | 運用初期としては許容範囲。米国株・先物市場は祝日休場が多いため、後続でのカレンダー注入は必須。 |

---

## 2. 戦略定義書（Sputnik）との整合性

- **ヒステリシス原則（0-1-Ⅳ, 0-3-351〜353）**  
  「状態は瞬間値で決定しない」「復帰は進入より遅くてよい」を、プロセスキャッシュではなく**過去の事実（時系列データ）から導出する**設計にすることで、コンテナ再起動後も「同じ市場データなら同じ Effective Level」が導出され、原則に忠実な実装となる。

- **階層分離原則（0-1-Ⅷ, 4-2-470）**  
  「Layer 3（因子）は単機能の計器に徹する」に対し、案1は「因子に計算をさせず、結果のみを渡す」ため、美学原則に最も叶う。

- **非対称性の徹底（4-2-1-2 等）**  
  V 因子の「V1→V0 復帰（1日確認＋1hノックイン）」のような複雑な復帰条件も、Layer 2 で「確認日数」を数値化すれば、Layer 3 のロジックを `satisfied_days >= required_days` と `is_intraday_condition_met` の単純な比較に集約できる。

---

## 3. 採用する実装構成（案1 ＋ 案3 ＋ 案4 拡張）

### ① データフロー：案3 ＋ 案1 のハイブリッド

1. **Raw 層**
   - `get_volatility_series(symbol, limit=5)` を実装する。
   - 直近 5 営業日分の volatility を一括取得・キャッシュする。

2. **Layer 2（Signal 層）**
   - 取得したシリーズから「当日終値が閾値未満か」を過去に遡って判定する。
   - 連続一致数を **`recovery_confirm_satisfied_days`** として算出し、シグナルに載せる。
   - **重要:** V1→V0 の「1hノックイン」は、Layer 2 で「本日の特定時間条件を満たしたか（bool）」として計算し、シグナルに含める（後述 **④ 1hノックイン**）。

3. **Layer 3（Factor 層）**
   - `satisfied_days >= required_days` かつ（V1→V0 の場合は）`is_intraday_condition_met` を見て昇格する。
   - プロセス内の `_confirm_counter` / `_confirm_days_required` は廃止する。
   - 表示用「x/N日目」は `x = recovery_confirm_satisfied_days`, `N = confirm_days` でシグナル由来の値をそのまま使う。

### ② 営業日判定：案4 拡張（カレンダー注入）

- 初期実装では「土日スキップ」のみでも可（案4 そのまま）。
- Docker 運用を見据え、**祝日は環境変数または設定（TOML）でコンテナに注入**する形を推奨する。
  - 例: `pandas_market_calendars` や、主要休場日（クリスマス、サンクスギビング等）のリストを `config/` 等で管理。

### ③ 案の詳細（参照用）

**案1（判定ロジック）**  
Layer 2 が「as_of および過去 (confirm_days - 1) 営業日」について条件を評価し、連続満たした日数だけをシグナルに載せる。因子はその整数と閾値の比較のみ行う。

**案3（Raw 取得形態）**  
`get_volatility_series(symbol, limit)` で直近 N 営業日分をまとめて取得。Layer 2 がその系列から `recovery_confirm_satisfied_days` を算出する。日付ごとの単発 get より API 効率が良い。

**案4（営業日）**  
「前日遡り＋土日は飛ばす」。案4 拡張で祝日リストを注入し、営業日列を生成する。

### ④ 1hノックイン（4-2-1-2）の扱い

復帰には**「1h足が陽線かつ前日終値より上」**という当日条件がある。

- **実装方針**
  - Layer 2 のシグナルに **`is_intraday_condition_met: bool`** を追加する（既存の `v1_to_v0_knock_in_ok` と同一意味で、命名を統一してもよい）。
  - 昇格条件は次の両立とする:
    - `recovery_confirm_satisfied_days >= 1`（前日条件クリア）
    - **AND** `is_intraday_condition_met == True`（当日の 1h 足条件クリア）
  - これらを満たしたタイミングで昇格させることで、「ノータイムでの執行」と「慎重な復帰」の両立をコードで明確に表現する。

---

## 4. 実装チェックリスト（作業時の参照用）

- [ ] **Raw**
  - [ ] `RawDataProvider` に `get_volatility_series(symbol, limit: int) -> List[Tuple[date, float]]`（または等価な型）を追加。
  - [ ] `CachedRawDataProvider` / IB 取得で直近 N 営業日分の volatility を取得・キャッシュ。
- [ ] **営業日**
  - [ ] Layer 2 用に `prev_business_days(as_of, n)` または `get_volatility_series` 内で営業日を考慮（土日＋祝日リスト注入対応）。
- [ ] **Layer 2**
  - [ ] `VolatilitySignal` に `recovery_confirm_satisfied_days: int` を追加。
  - [ ] `is_intraday_condition_met: bool` を追加（または `v1_to_v0_knock_in_ok` をその意味で明示）。
  - [ ] `get_volatility_series` と営業日から「閾値未満の連続日数」を算出し、上記フィールドに設定。
- [ ] **Layer 3**
  - [ ] V 因子: `satisfied_days >= required_days` かつ `is_intraday_condition_met`（V1→V0 時）で昇格。`upgrade()` の `confirm_days` による「複数日呼び出し」依存を廃止。
  - [ ] `_confirm_counter` / `_confirm_days_required` を廃止。`recovery_confirm_progress()` はシグナル由来の `(satisfied_days, confirm_days)` を返すようにする（要: シグナルを因子が参照する経路の確保）。
- [ ] **Daily Report**
  - [ ] 「x/N日目」表示がシグナル由来の `recovery_confirm_satisfied_days` / `confirm_days` を参照するようにする。

---

**評価結果:**  
「案1（ロジック）＋ 案4（営業日）＋ 案3（データ取得）」の組み合わせは、システム憲章に忠実であり、再起動によるカウントリセット等のバグを物理的に排除できるため、**採用すべき仕様**とする。
