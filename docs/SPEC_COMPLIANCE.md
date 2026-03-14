# 仕様書・憲章との照合結果

SPEC.md（マクロインカム戦略 完全運用定義書 2026年2月改訂）および .cursorrules（憲章）との差異・違反の洗い出し。

---

## 1. 憲章違反の可能性がある箇所

### 1-1. Emergency プロトコル 処理順序（6-2）【対応済】

**憲章**: 「Emergencyプロトコルは処理順序を厳密に守る」（.cursorrules）

**定義書 6-2 表の処理順**（7ステップ。不要ステップ削除済み）:
| 処理順 | ユニット | 対象 | アクション |
|--------|----------|------|------------|
| 1 | メインエンジン | BPS | K2を1枚追加しPB転換（1:2構成） |
| 2 | ブースター | 先物 | 即時決済 |
| 3 | メインエンジン | K1（売りP） | 即時買戻し |
| 4 | 姿勢制御エンジン | K1（売りP） | 即時買戻し |
| 5 | メインエンジン | CC（売りC） | 即時買戻し |
| 6 | 姿勢制御エンジン | 先物 | 全決済 |
| 7 | 全ユニット | 残存K2 | 6-3-1（PB利益確定）へ移行 |

**実装**（`core/emergency_protocol.py`）: 定義書の 7 ステップに合わせて実行順を一致済み。3・6 は現行 wings に専用APIがなければ予約。

---

### 1-2. 市場因子の直接 Capital 注入（0-1-Ⅲ, Ⅶ）

**憲章**: 「市場因子を直接Capitalに注入禁止」「市場因子を直接Cへ注入しない」

**確認**: Avionics では M 用の因子（P,V,L,T）と C 用の因子（U,S）を別リストで保持し、`get_market_level()` と `get_capital_level()` を分離。OSCore は M と C を別々に取得し、M×C でモード決定。**違反なし**。

---

### 1-3. M → C → Engine の順序（0-1-Ⅲ）

**憲章**: 「M → C → Engine この順序を破らない」

**確認**: OSCore の pulse では `update_all()` → `get_capital_level()` → `get_fleet_market_level()` → 各エンジンで `get_market_level(symbol)` → `_determine_mode(effective_m, c_level)` → `apply_mode()`。M と C を先に取得し、その後にエンジンへモードを伝達。**違反なし**。

---

## 2. 仕様書との相違（仕様 vs 実装）

以下は過去に指摘した相違のうち、対応済みまたは定義書更新で解消した項目の記録。

### 2-1. Emergency プロトコル（6-2） ステップ内容【対応済】

**定義書 6-2**: 処理順 1〜9 は「どのユニットのどの対象に何をするか」で定義。

**実装**: 定義書の 7 ステップに合わせて実装済み。1=メインPB転換、2=ブースター、3=メインK1、4=姿勢K1、5=メインCC、6=姿勢先物、7=6-3-1。3・6は予約。

---

### 2-2. U因子・S因子 復帰時の一気飛び（C2→C0 / S2→S0）【対応済】

**定義書**:
- U: C2 復帰は「< 45%（2日確認）」→ C2→C1。C1 復帰は「< 38%（3日確認）」→ C1→C0。
- S: S2 復帰は「< 1.2（2日確認）」→ S2→S1。S1 復帰は「< 1.05（3日確認）」→ S1→S0。

**実装**: 定義書どおり一段階ずつ復帰に修正済み。C2/S2 からは candidate=1 のみ許容し、C0/S0 への直飛びは行わない。

---

### 2-3. 1-3 ユニット動力機構・T因子の位置づけ【定義書更新済】

**定義書の更新内容**（SPEC.md 反映済み）:
- **1-3**: ストラテジーバンドルを廃止し、「**ユニット動力機構（設計図・Blueprint）**」に改訂。各エンジンは NQ/GC 専用 1 インスタンス、層ごとに LayerBlueprint で 3 層構成と明記。
- **T因子の位置づけ**: OS 構造を「ICL（個別制御層）・SCL（同期制御層）・LCL（制限制御層）」の 3 層に整理。T は **SCL（銘柄間トレンド相関）** として、ICL（max(P,V,L)）とは独立した層で定義。Effective Level = max(ICL, SCL, LCL)。

**実装との対応**: 実装は銘柄別 `get_market_level(symbol)`（P,V,L,T の max）と `get_fleet_market_level()` を `effective_m = max(m_single, m_fleet)` で合成しており、個別＋相関の二段構えは定義書の ICL＋SCL の考え方と対応する。

---

## 3. 憲章・仕様で確認済みで問題なしと判断した点

| 項目 | 内容 |
|------|------|
| 0-1-Ⅵ 自己改造禁止 | しきい値は config/factors.toml で注入。コードに銘柄別閾値を直書きしない。 |
| 0-1-Ⅳ ヒステリシス | 因子側で降格即時・昇格は confirm_days/バッファ。OS は因子出力をそのまま使用。 |
| 4-2 M×C 対応表 | OSCore._determine_mode が定義書の表どおり（M2/C2→Emergency 等）。 |
| 4-2-1-1 P因子 | NQ/GC の閾値は設定ファイルで分離。判定ロジックは単一 _classify。 |
| 4-2-1-2 V因子 | 高・低高度の閾値注入。悪化即時・復帰は確認日数＋バッファ。 |
| 4-2-1-3 L因子 | credit/tip で分岐。L0/L2 のみ。 |
| 4-2-2-1 / 4-2-2-2 U,S | 発動閾値は定義書通り。復帰は一段階ずつ（C2→C1→C0, S2→S1→S0）に修正済み。 |
| docstring | 主要クラス・メソッドに定義書セクション参照の docstring あり。 |

---

## 4. 対応推奨の優先度

1. ~~**最優先**: Emergency プロトコル（6-2）の処理順序を定義書に一致させる~~ → **対応済**。
2. ~~**高**: T因子の定義書との整合~~ → **定義書更新済**（SCL として位置づけ。1-3 とあわせて改訂反映）。
3. ~~**中**: U/S の C2→C0 / S2→S0 の一気復帰を定義書どおり一段階ずつに合わせる~~ → **対応済**。
4. ~~**低**: 1-3 の「ストラテジーバンドル」を「Blueprint／設計図」に用語更新~~ → **定義書更新済**（1-3 を設計図・Blueprint に改訂済み）。

---

## 5. 定義書更新後の照合（プログラムとの齟齬チェック）

SPEC.md（完全運用定義書 2026年2月改訂）を前提に、主要な実装との一致・齟齬を確認した結果。

### 5-1. 一致している項目

| 定義書 | 実装 | 備考 |
|--------|------|------|
| **0-3 / 4-2** ICL・SCL・LCL・Effective | `cockpit.py`: ICL = max(P,V,C/R), SCL = T相関, LCL = max(U,S), Effective = max(ICL, SCL, LCL) | 3層構造・公式どおり |
| **4-2** Effective Level × スロットル | Cockpit が `get_effective_level` の 0/1/2 を `_level_to_mode` で Boost/Cruise/Emergency に変換。`cockpit/mode.py` で定数定義 | 対応表どおり |
| **Layer2** Trend | Uptrend: 終値 > SMA20×1.005, Downtrend: < SMA20×0.995（`signals.py`） | 定義書 4-2 Layer2 表と一致 |
| **Layer2** 清算値・RTH | `ib_data.py`: useRTH=True, 日足は清算値前提 | 定義書「前日比計算には清算値を使用」と整合 |
| **P因子** NQ/GC 別閾値・判定ルール | `p_factor.py`: _classify は P0/P1/P2 条件。閾値は `factors.toml` で NQ.P / GC.P に分離 | 定義書の数値は toml で反映（P2_gap_trend NQ -5% / GC -4% 等） |
| **V因子** 高・低高度・復帰確認日数・1hノックイン | `v_factor.py`: V2/V1 閾値・confirm_days・buffer_condition（1hノックイン） | 定義書 4-2-1-2 と一致 |
| **R因子** TIP・高値比・2日確認 | `r_factor.py`: tip_drawdown_from_high, drawdown_L2/L0, confirm_days | 定義書 4-2-1-4 と一致 |
| **T因子** 0/1/2・復帰確認 | `t_factor.py`: down→2, up/flat→0。復帰は confirm_days 連続 up/flat | 定義書「両安定/片Downtrend/両Downtrend」と一致 |
| **U因子** 50%/45%（2日）、40%/38%（3日） | `factors.toml` [U]: C2_on/off, C1_on/off, C2/C1_confirm_days。`u_factor.py` で一段階ずつ復帰 | 定義書 4-2 U因子表と一致 |
| **S因子** 1.3/1.2（2日）、1.1/1.05（3日） | `factors.toml` [S]: S2_on/off, S1_on/off, S2/S1_confirm_days。`s_factor.py` で一段階ずつ復帰 | 定義書 4-2 S因子表と一致 |
| **復帰表示** ステートレス化 | 表示用キャッシュ廃止。bundle を渡して `get_recovery_progress_from_bundle` でその場計算 | STATEFUL_AUDIT 方針どおり |

### 5-2. 齟齬あり（要対応 or 仕様確認）

（C因子の HYG/LQD 2銘柄要件は **対応済み**。以下に実施内容を記載。）

**C因子（4-2-1-3）【対応済み】**

| 定義書 | 実装 |
|--------|------|
| C2発動: **HYG or LQD**がSMA20を下回る OR 前日比-2.5%以上 | `ib_data`: HYG 取得時に LQD も取得。`SignalBundle.liquidity_credit`（HYG）と `liquidity_credit_lqd`（LQD）を設定。`c_factor.update_from_signals`: `c2_triggered = c2_hyg or c2_lqd`。 |
| C0復帰: **HYG AND LQDとも**SMA20以上を2日維持 | `c_factor._count_recovery_satisfied_days_two_symbols`: 日付で揃え、両方 C0 を満たす連続日数をカウント。`get_recovery_progress_from_bundle`: LQD あり時は両方で算出。 |

LQD 未渡し（後方互換）の場合は従来どおり HYG のみで判定。

### 5-3. その他（参照のみ）

* **LAYER_CHARTER_COMPLIANCE.md** の「get_individual = max(P,V,L)」の「L」は、定義書の ICL における C（Credit）／R（Real-Rate）を指す旧表記。実装は NQ で max(P,V,C)、GC で max(P,V,R) で定義書と一致。
* Emergency プロトコル（6-2）の実行順は `emergency_protocol.py` 側の実装次第。avionics 配下には 6-2 の執行コードはないため、別リポジトリ／wings があればそこで照合すること。

---

*このドキュメントは SPEC.md および .cursorrules を参照し、実装（avionics, core, wings 等）と照合した結果に基づく。*
