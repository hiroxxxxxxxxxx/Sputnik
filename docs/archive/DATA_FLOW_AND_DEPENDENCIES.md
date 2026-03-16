# SignalBundle の定義と依存関係・処理責務

**「singlebundle」** という名前の型はコードベースにありません。Layer 2 の束は **`SignalBundle`** です。

---

## 1. SignalBundle の定義場所

| 項目 | 内容 |
|------|------|
| **定義ファイル** | `src/avionics/Instruments/signals.py` |
| **定義行** | 93 行付近 `class SignalBundle` |
| **役割** | Layer 2 の出力を一括保持する dataclass。price_signals / volatility_signals / liquidity_credit / liquidity_tip / capital_signals を持つ。 |

```python
# signals.py L93 付近
@dataclass(frozen=True)
class SignalBundle:
    price_signals: dict[str, PriceSignals] = ...
    volatility_signals: dict[str, VolatilitySignal] = ...
    liquidity_credit: Optional[LiquiditySignals] = None
    liquidity_credit_lqd: Optional[LiquiditySignals] = None
    liquidity_tip: Optional[LiquiditySignals] = None
    capital_signals: Optional[CapitalSignals] = None
```

---

## 2. モジュールごとの依存関係（誰が何を import するか）

```
                    ┌─────────────────┐
                    │   raw_data      │
                    │ (Layer 1 型のみ) │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│    signals      │  │    ib_data      │  │ (その他 Raw 実装) │
│ RawDataProvider │  │ RawDataProvider │  │                  │
│ PriceBar 等を   │  │ の IB 実装      │  │                  │
│ 使って compute_*│  │ + signals の    │  │                  │
│ で Signal 生成 │  │ compute_* で    │  │                  │
└────────┬────────┘  │ SignalBundle 構築│  └─────────────────┘
         │           └────────┬────────┘
         │                    │
         │  PriceSignals 等   │  SignalBundle
         │  SignalBundle      │
         │                    │
         ▼                    ▼
┌─────────────────┐  ┌─────────────────┐
│  factor (P,V,T, │  │  flight_        │
│  C,R,U,S)       │  │  controller     │
│ signals の型のみ│  │ SignalBundle を │
│ を参照          │  │ 受け update_all │
│ raw_data は見ない│  │ で因子に配布    │
└─────────────────┘  └─────────────────┘
```

### 2.1 依存の向き（簡潔）

| モジュール | 依存するもの | 依存されないもの |
|------------|--------------|------------------|
| **raw_data** | なし（型と Protocol のみ） | signals, factor, ib_data, fc |
| **signals** | raw_data（RawDataProvider, PriceBar, RawCapitalSnapshot） | factor, ib_data, fc |
| **factor** (P,V,T,C,R,U,S) | signals（PriceSignals, VolatilitySignal, LiquiditySignals, CapitalSignals） | raw_data, ib_data, fc |
| **ib_data** | raw_data, signals（compute_* と SignalBundle） | factor, fc |
| **fc** (flight_controller) | signals（SignalBundle）, control_levels, EngineFactorMapping。因子は「マッピングで渡されたオブジェクト」としてのみ触る | raw_data, ib_data。因子の**型**は _update_all_from_signals 内で isinstance するため「知っている」 |

---

## 3. 処理責務（データの流れと誰が何をするか）

### 3.1 raw_data（`Instruments/raw_data.py`）

- **責務**: Layer 1 の**型と取得インターフェース**の定義のみ。
- **提供**: `PriceBar`, `PriceBar1h`, `RawCapitalSnapshot`, `RawDataProvider`（Protocol）。加工は一切しない。
- **依存**: 他モジュールに依存しない。

### 3.2 signals（`Instruments/signals.py`）

- **責務**: Raw → Layer 2 の**計算**と、その結果を入れる**型**の定義。
- **提供**:
  - 型: `PriceSignals`, `VolatilitySignal`, `LiquiditySignals`, `CapitalSignals`, **`SignalBundle`**
  - 関数: `compute_price_signals(raw_provider, symbol, as_of)` など。いずれも **RawDataProvider** と as_of を渡し、上記 Signal 型のインスタンスを返す。
- **依存**: **raw_data**（RawDataProvider で価格系列などを取得して計算する）。factor / ib_data / fc には依存しない。

### 3.3 factor（`Instruments/p_factor.py` 等）

- **責務**: Layer 2 の**出力（シグナル）を入力にレベル判定**する。非対称ヒステリシスなどはここで実装。
- **提供**: 各因子クラス。`update()`（データなし）と `update_from_price_signals(price)` など**特定シグナル型用**の更新メソッド。
- **依存**: **signals** の型（PriceSignals, CapitalSignals 等）のみ。**raw_data / ib_data / fc は参照しない**。FC が「どの因子にどのシグナルを渡すか」を決める。

### 3.4 ib_data（`avionics/ib_data.py`）

- **責務**: **IB API で Layer 1 を取得**し、**signals の compute_*** を呼んで **SignalBundle を組み立てる**。
- **流れ**:
  1. IB から価格・ボラ・証拠金・流動性（HYG/LQD/TIP）などを取得。
  2. 取得結果を **CachedRawDataProvider**（RawDataProvider の実装）に詰める。
  3. `compute_price_signals(cache, sym, as_of)` などを銘柄・シンボルごとに呼ぶ。
  4. 得た `PriceSignals` / `VolatilitySignal` / `LiquiditySignals` / `CapitalSignals` を **SignalBundle** にまとめる。
  5. `(SignalBundle, Optional[RawCapitalSnapshot])` を返す。
- **依存**: **raw_data**（型と RawDataProvider）、**signals**（compute_* と SignalBundle）。**factor / fc は参照しない**。

### 3.5 fc（flight_controller）

- **責務**: **SignalBundle を受け取り、全因子を更新し、ICL/SCL/LCL をまとめて FlightControllerSignal を返す**。
- **流れ**:
  1. `update_all(signal_bundle=bundle)` が呼ばれると `_update_all_from_signals(bundle)` を実行。
  2. bundle から `price_signals.get(symbol)` などを**自分で取り出し**、各因子の**型（isinstance）** に応じて `update_from_price_signals(price)` や `update_from_ratio(...)` を呼ぶ。
  3. `get_flight_controller_signal(bundle)` では、control_levels で ICL/SCL/LCL を算出し、SymbolSignal / FlightControllerSignal を組み立てる（recovery_metrics 用に bundle を参照することはある）。
- **依存**: **signals**（SignalBundle）、**control_levels**、**EngineFactorMapping**（因子リスト）。**raw_data / ib_data は参照しない**。因子の**具象型**は _update_all_from_signals 内の isinstance で参照している。

---

## 4. まとめ図（処理の流れ）

```
[IB / 他ソース]
       │
       ▼
  ib_data: Raw 取得 → CachedRawDataProvider に格納
       │
       │  RawDataProvider として
       ▼
  signals: compute_price_signals(cache, sym, as_of) 等
       │
       ▼
  SignalBundle 構築（ib_data 内）
       │
       │  スクリプトが fc.update_all(signal_bundle=bundle) を呼ぶ
       ▼
  fc: _update_all_from_signals(bundle)
       │  bundle から銘柄・種別ごとに取り出し、因子の型に応じて
       │  update_from_* を呼ぶ
       ▼
  factor (P,V,T,C,R,U,S): レベル更新
       │
       ▼
  fc: get_flight_controller_signal() → ICL/SCL/LCL 集約 → FlightControllerSignal
       │
       ▼
  Cockpit / レポート / スクリプト
```

- **SignalBundle** は **signals.py** で定義され、**ib_data** が **compute_*** の結果を詰めて**組み立て、**fc** がそれを受け取って因子に配布する、という関係になっている。
