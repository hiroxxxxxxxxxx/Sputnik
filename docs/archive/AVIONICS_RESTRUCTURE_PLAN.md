# Avionics 責務分離・修正プラン

エンジン(Symbol)↔Factor マッピング、ICL/SCL/LCL の責務を定義書「4-2」の構造に合わせて整理するための修正プラン。Q1〜Q5 の決定に基づく実施内容を **4. 修正 Phase** にまとめている。

---

## 1. 目標とする構造（前提の確認）

| 概念 | 責務 | 出力 |
|------|------|------|
| **エンジン(Symbol) ↔ Factor のマッピング** | 「どの Symbol にどの Factor が属するか」の決定・保持。ICL/SCL/LCL の**入力**を提供。 | マッピング（型で表現するかは選択肢） |
| **ICL（個別制御層）** | エンジン(Symbol)ごとのレベル。入力: その Symbol の P,V,C/R。 | 銘柄別 ICL（例: `Dict[symbol, int]`） |
| **SCL（同期制御層）** | エンジン統合判定。入力: 全銘柄の T の level。T 相関で 0/1/2。 | 1 つの SCL（`int`） |
| **LCL（制限制御層）** | 機体全体。入力: U, S。 | 1 つの LCL（`int`） |
| **総合判定** | Effective(symbol) = max(ICL(symbol), SCL, LCL)。Cockpit へ渡すオブジェクトに格納。 | `FlightControllerSignal`（現行の by_symbol + 必要なら ICL/SCL/LCL の内訳） |
| **Cockpit** | 上記オブジェクトを受け取り、スロットルモードに変換して各 Engine に `apply_mode`。 | 変更なし（インターフェースは維持） |

---

## 2. 決定事項（Q1〜Q5）

| ID | 決定 |
|----|------|
| **Q1** | **専用型を導入。型名は `EngineFactorMapping`。** |
| **Q2** | **三層算出は専用クラスに切り出す。** |
| **Q3** | **各レベル内訳（ICL/SCL/LCL）を Signal に渡す。** |
| **Q4** | **B: 単一組み立てポイントで局所化（例: `build_cockpit_stack`）。** |
| **Q5** | **現状のまま（メソッド名は `get_individual_control_level` / `get_synchronous_control_level` / `get_limit_control_level` を維持）。** |

---

## 3. 要確認・選択肢一覧（参照用）

実装前に決めたい点を以下に列挙する。番号は後述の Phase 内で参照する。

### 3.1 マッピングの表現（Q1 → 決定: 専用型 `EngineFactorMapping`）

- 専用型 **`EngineFactorMapping`** を導入。
  - `symbol_factors: Dict[str, List[Factor]]`（銘柄→ICL用 P,V,C/R + SCL用 T）
  - `limit_factors: List[Factor]`（U, S）。必要なら `global_market_factors` も保持。
  - Assembly が組み立て、FlightController と三層専用クラスは受け取るだけ。

### 3.2 ICL/SCL/LCL の配置（Q2 → 決定: 専用クラスに切り出し）

- 三層算出は **専用クラス**（例: `ControlLevels` または `control_levels.py` 内のクラス）に切り出す。
  - 入力: `EngineFactorMapping`（または同等のマッピング）。因子は `update_all` 済みである前提。
  - 提供: `compute_icl(symbol)` / `compute_scl()` / `compute_lcl()`。FlightController はこのクラスを利用するだけ。

### 3.3 三層の結果の露出（Q3 → 決定: 各レベル内訳を渡す）

- **Signal に ICL/SCL/LCL を明示的に持たせる。**
  - `SymbolSignal` に `icl: int`, `scl: int`, `lcl: int` を追加（SCL/LCL は全銘柄共通なので `FlightControllerSignal` に `scl`/`lcl` を置き、銘柄別は `by_symbol[sym].icl` のみでも可。いずれにせよ「各レベル内訳を渡す」を満たす）。
  - レポート・監査・デバッグで「なぜその Effective になったか」を直接参照可能。`raw_metrics` は P,V,C,R,T,U,S の生 level で概念が異なるため重複許容。

### 3.4 エンジンと FC の Symbol リストの一致（Q4 → 決定: B で局所化）

- **単一の組み立てポイントで局所化する。**
  - 例: `build_cockpit_stack(symbols: list[str], ...) -> tuple[FlightController, list[Engine]]` を用意し、FC と Engine を同じ symbols で必ず組み立てる。scripts はその関数を呼ぶだけにする。
  - 配置場所は実装時に決定（cockpit パッケージに置くか、別モジュールに置くか）。

### 3.5 用語の統一（Q5 → 決定: 現状のまま）

- **メソッド名は変更しない。** `get_individual_control_level` / `get_synchronous_control_level` / `get_limit_control_level` を維持。docstring で「ICL（個別制御層）」「SCL（同期制御層）」「LCL（制限制御層）」と対応づけて明記する。

---

## 4. 修正 Phase（実施順）

以下は **2. 決定事項** に基づく実施内容。Phase 3 と 4 の順序は、マッピング型を先に導入してから三層クラスがそれを受け取る形にするとよい。

### Phase 1: 三層の明示と API の整理

- **目的**: ICL/SCL/LCL を定義書どおり「個別／同期／制限」としてコード上で明確にする。メソッド名は現状のまま（Q5）。
- **作業**:
  1. `get_flight_controller_signal()` 内の変数・コメントで ICL/SCL/LCL を明示（現状ロジックはそのまま）。
  2. docstring と LAYER_CHARTER / SPEC_COMPLIANCE 等で「個別制御層(ICL)」「同期制御層(SCL)」「制限制御層(LCL)」と対応づけて記述を統一。

### Phase 2: 三層結果の Signal への露出（各レベル内訳を渡す）

- **目的**: レポート・監査で「なぜその Effective になったか」を参照しやすくする（Q3 決定）。
- **作業**:
  1. `SymbolSignal` に `icl: int`, `scl: int`, `lcl: int` を追加。SCL/LCL は全銘柄共通のため、`FlightControllerSignal` に `scl: int`, `lcl: int` を置き、`by_symbol[sym]` の各 `SymbolSignal` には `icl` を渡す形でも可（いずれにせよ「各レベル内訳を渡す」を満たす）。
  2. `get_flight_controller_signal()` で各 SymbolSignal を組み立てる際に上記フィールドを代入。
  3. レポートで ICL/SCL/LCL を表示するかは別途判断（テンプレート変更が必要なら別タスク）。`raw_metrics` は生 level で概念が異なるため重複許容。

### Phase 3: マッピングの型導入（EngineFactorMapping）

- **目的**: エンジン(Symbol) ↔ Factor のマッピングを値オブジェクトにまとめ、組み立て（Assembly）と利用（FlightController・三層クラス）の責務を分離する（Q1 決定）。
- **作業**:
  1. **`EngineFactorMapping`** を dataclass で定義。
     - `symbol_factors: Dict[str, List[Factor]]`（銘柄→ICL用 P,V,C/R + SCL用 T）
     - `limit_factors: List[Factor]`（U, S）。必要なら `global_market_factors: List[Factor]` も保持。
  2. `assembly.build_flight_controller(symbols)` で、因子を組み立てた結果を **EngineFactorMapping** のインスタンスとして構築し、FlightController のコンストラクタに渡す。
  3. FlightController はコンストラクタで `EngineFactorMapping` を受け取り、内部ではそのフィールドを参照するだけにする。
  4. `register_factor` を残すかは実装時に検討（残す場合はマッピングを mutable として扱うか、組み立て時のみ登録とするか）。

### Phase 4: 三層算出の切り出し（専用クラス）

- **目的**: ICL/SCL/LCL の算出を FlightController から切り出し、三層専用のクラスに置く（Q2 決定）。Phase 3 の `EngineFactorMapping` を入力とする。
- **作業**:
  1. 三層専用クラス（例: `ControlLevels`。モジュールは `control_levels.py` 等）を新設。入力: **EngineFactorMapping**。因子は `update_all` 済みである前提を docstring で明記。
  2. `compute_icl(symbol)`, `compute_scl()`, `compute_lcl()` を実装（現行の `get_individual_control_level` / `get_synchronous_control_level` / `get_limit_control_level` のロジックを移動）。
  3. FlightController は `update_all` のあと、このクラスに `EngineFactorMapping` を渡して ICL/SCL/LCL を取得し、`get_flight_controller_signal()` で Effective と SymbolSignal（Phase 2 の icl/scl/lcl 含む）を組み立てる。FlightController から三層の getter を削除するか、専用クラスをラップして残すかは実装時に決定。

### Phase 5: エンジンと FC の組み立ての一元化（局所化）

- **目的**: symbols を一箇所でだけ使い、FC と Engine の整合を保証する（Q4 決定）。
- **作業**:
  1. **`build_cockpit_stack(symbols: list[str], ...) -> tuple[FlightController, list[Engine]]`**（または同等の名前）を用意。  
     - 内部で `build_flight_controller(symbols)` と、symbols に応じた Engine の組み立て（NQ/GC なら build_nq_engine / build_gc_engine）を呼ぶ。
  2. `run_cockpit_with_ib.py` と `telegram_cockpit_bot.py` では、symbols を決めたうえで `build_cockpit_stack(symbols)` を呼び、返ってきた FC と Engine リストを Cockpit に渡す。
  3. 配置場所は実装時に決定（cockpit パッケージに置くか、avionics に FC のみ返す関数を置き Engine は呼び出し側で組み立てるか。決定では「B で局所化」のため、FC と Engine を同一 symbols で組み立てる関数を用意する）。
  4. テストでは既存の build_flight_controller / build_nq_engine 等を直接使う形のままでも可。必要なら build_cockpit_stack のテストを追加。

---

## 5. 依存関係のまとめ

- **Phase 1**: 他 Phase に依存しない。まず実施。
- **Phase 2**: Phase 1 の後で可。Signal に icl/scl/lcl を追加するため、現行の get_* がまだ FC にある前提で実施可能。
- **Phase 3**: Phase 1 の後がよい。Assembly と FlightController の責務分離。Phase 2 とは並行可能だが、先に Phase 3 をすると FC が EngineFactorMapping を受け取る形になり、Phase 4 がやりやすい。
- **Phase 4**: Phase 3 の後がよい。三層専用クラスが EngineFactorMapping を入力とする。Phase 2 で SymbolSignal に icl/scl/lcl を追加済みなら、三層クラスからそのまま渡せる。
- **Phase 5**: 他 Phase と独立。いつでも実施可能。推奨は Phase 3 または 4 のあと（FC の組み立てが安定してから）。

**推奨実施順**: Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5（または Phase 1 → Phase 3 → Phase 4 → Phase 2 → Phase 5）。

---

## 6. 参照

- 定義書「4-2 情報の階層構造」「3層制御構造」
- 現行実装: `src/avionics/flight_controller.py`, `src/avionics/assembly.py`
- エンジン組み立て: `src/engines/factory.py`
- 既存の Layer4 案: `docs/archive/LAYER4_SPEC_ALIGNMENT.md`
- レイヤー憲章: `docs/archive/LAYER_CHARTER_COMPLIANCE.md`
