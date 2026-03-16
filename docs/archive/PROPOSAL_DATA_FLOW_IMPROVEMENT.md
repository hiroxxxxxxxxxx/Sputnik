# データの流れ・依存関係の改善案（Data / API / Process の整理）

現状「データの流れや依存関係が分かりにくい」「API / Data / Process の責務が分かりにくい」という問題に対する改善の方向性と具体案。

---

## 1. 用語の整理：Data / API / Process をどう割り当てるか

| 用語 | 意味（本案での定義） | 入出力のイメージ |
|------|----------------------|------------------|
| **Data** | **型・構造の定義**。値の「形」と、永続化や取得の**インターフェース（Protocol）**だけを定める。計算・取得ロジックは持たない。 | 入力: なし（他層から参照されるだけ） / 出力: 型・Protocol |
| **API（Acquisition）** | **外部システムから Raw を取得する**責務。IB / DB / CSV などに問い合わせ、**Data で定義した Raw 型**を返す。加工や Layer 2 計算は行わない。 | 入力: 接続情報・パラメータ / 出力: Raw の集合（または RawDataProvider 相当） |
| **Process** | **計算・変換**の責務。Raw → Signal、Signal → Level、Level → FlightControllerSignal など、**定義済みの型の間の変換**を行う。 | 入力: 上流の型（Raw / Signal 等）/ 出力: 下流の型（Signal / Level / FlightControllerSignal） |

この 3 つを分けておくと、「どこに何を書くか」と「依存の向き」が揃う。

---

## 2. 現状の問題点

### 2.1 責務の混在

| モジュール | 現状やっていること | 問題 |
|------------|--------------------|------|
| **raw_data** | Data（型 + RawDataProvider Protocol） | ✅ 役割は明確。 |
| **signals** | **Data**（PriceSignals, SignalBundle 等の型）**と Process**（compute_*）が同一ファイルに同居 | 「型の定義」と「Raw→Signal の計算」が分離されておらず、流れが読みにくい。 |
| **ib_data** | **API**（IB から取得）**と Process**（CachedRawDataProvider に詰めたあと compute_* を呼び SignalBundle を組み立て）が同居 | 「取得」と「Layer 2 計算・Bundle 組み立て」が一体になっており、API と Process の境界が不明瞭。 |
| **factor** | Process（Signal → Level） | ✅ 役割は明確。 |
| **fc** | Process（SignalBundle の配布 + Level の集約） | 配布ロジックが因子の型（isinstance）に依存しており、別案（Layer2Context 等）で分離を検討中。 |

### 2.2 依存の向きとデータの流れ

- **理想**: Data → API → Process の一方向。Process は「上流の型」だけを知り、取得手段（IB か DB か）は知らない。
- **現状**: ib_data が「API + Process」なので、**データの流れ**が「IB → ib_data（取得＋計算＋Bundle 構築）→ FC」と長く、かつ「どこまでが API でどこからが Process か」がコード上で分かりにくい。

---

## 3. 改善の方向性（2 パターン）

### 案 A: コード配置は変えず、責務とデータの流れを「見える化」する（軽い改善）

コードの移動は最小限にし、**ドキュメントと命名**で Data / API / Process を明確にする。

- **やること**:
  1. **1 枚の「データフロー図」**を 1 ファイルにまとめる（例: `docs/spec/DATA_FLOW.md`）。
     - 縦軸: レイヤー（Raw / Signal / Level / FlightControllerSignal）。
     - 横軸 or フロー: Data（型）→ API（取得）→ Process（計算）を矢印で書く。
     - どのモジュールが「Data の提供」「API」「Process」のどれを担うか、図中に注釈する。
  2. **モジュールの docstring** に役割を 1 行で書く。
     - 例: `raw_data.py` → "Data: Layer 1 の型と RawDataProvider Protocol。"
     - 例: `signals.py` → "Data: Layer 2 の型（PriceSignals, SignalBundle 等）。Process: Raw → Signal の compute_*。"
     - 例: `ib_data.py` → "API: IB から Raw 取得。Process: 取得結果で SignalBundle を組み立て（内部で signals.compute_* を利用）。"
  3. **README や LAYER_CHARTER** に「avionics 内の Data / API / Process の対応表」を 1 表追加する。

- **メリット**: 実装変更が少ない。読む人が「どこが Data でどこが Process か」をすぐ把握できる。
- **デメリット**: コード構造の混在は残る。

---

### 案 B: 責務に合わせて「Data / API / Process」を分離する（構造改善）

「Data は型だけ」「API は取得だけ」「Process は計算だけ」になるように、役割ごとにファイルまたはパッケージを分ける。

#### B-1 ディレクトリ・モジュールの再編（イメージ）

```
avionics/
  data/                    # Data: 型と Protocol のみ
    raw.py                 # PriceBar, RawCapitalSnapshot, RawDataProvider
    signals.py             # PriceSignals, VolatilitySignal, ..., SignalBundle（型のみ）
  acquisition/             # API: 外部から Raw を取得
    ib_fetcher.py          # IB 呼び出し → Raw の辞書 or CachedRawDataProvider を返すだけ
  process/                 # Process: 計算・変換
    layer2/                # Raw → Signal
      compute.py           # compute_price_signals, compute_volatility_signal, ...（data.raw, data.signals の型を参照）
    layer3/                # Signal → Level, Level → FlightControllerSignal
      factors/             # 既存の P,V,T,C,R,U,S（data.signals の型を参照）
      control_levels.py    # ICL/SCL/LCL
      flight_controller.py # SignalBundle の配布 + 集約
```

- **data**: 他に依存しない。型と Protocol の定義のみ。
- **acquisition**: **data.raw** にだけ依存。IB から取得した結果を **Raw の集合 or RawDataProvider 実装**として返す。**signals や compute_* は知らない**。
- **process.layer2**: **data.raw** と **data.signals** に依存。RawDataProvider を受け取り compute_* で Signal を返す。**IB は知らない**。
- **process.layer3**: **data.signals**（SignalBundle 等）と factor に依存。**raw や acquisition は知らない**。

これにより、「データの流れ」が **Acquisition → Raw → Process(Layer2) → Signal → Process(Layer3) → FlightControllerSignal** と一方向になる。

#### B-2 ib_data の分割（API と Process の分離）

現在の `ib_data` を次の 2 つに分ける案。

| 分割後 | 責務 | 入力 | 出力 |
|--------|------|------|------|
| **acquisition/ib_fetcher.py**（API） | IB に問い合わせ、Raw を取得して **CachedRawDataProvider に詰める**だけ。 | IB 接続, as_of, symbols 等 | CachedRawDataProvider（と Optional[RawCapitalSnapshot]） |
| **process/bundle_builder.py**（Process） | **RawDataProvider** と as_of を受け取り、**compute_* を呼んで SignalBundle を組み立てて返す**。 | RawDataProvider, as_of, オプション（銘柄リスト等） | SignalBundle |

- 呼び出し側（scripts）: `raw = await ib_fetcher.fetch_raw(...)` → `bundle = build_signal_bundle(raw, as_of, ...)` → `fc.update_all(signal_bundle=bundle)`。
- こうすると「API = Raw 取得」「Process = Raw → SignalBundle」の境界がコード上で明確になる。

#### B-3 signals の分割（Data と Process の分離）

- **data/signals.py**: `PriceSignals`, `VolatilitySignal`, `LiquiditySignals`, `CapitalSignals`, `SignalBundle` の**型定義のみ**。可能なら raw への依存も「型の import」だけにする。
- **process/layer2/compute.py**: `compute_price_signals(raw_provider, symbol, as_of)` などの**計算関数**。data.raw と data.signals を import して使用。

- メリット: 「型を変える」と「計算を変える」の変更が別ファイルになり、責務が分かりやすい。
- デメリット: 既存の signals.py を分割するため、import パスやテストの修正が発生する。

---

## 4. 改善後の「データの流れ」の目標イメージ（案 B を採用した場合）

```
[外部: IB]
      │
      ▼
  API (acquisition): Raw 取得 → CachedRawDataProvider
      │
      ▼
  Process (layer2): RawDataProvider + as_of → compute_* → SignalBundle
      │
      ▼
  Process (layer3): SignalBundle → fc.update_all → 因子更新
      │
      ▼
  Process (layer3): get_flight_controller_signal → ICL/SCL/LCL 集約 → FlightControllerSignal
      │
      ▼
  Cockpit / レポート / スクリプト
```

- **Data**: 各段の「入出力の型」が定義されているだけ。
- **API**: 一番上流の「Raw を取ってくる」だけ。
- **Process**: 型から型への変換だけ。どのデータソースで Raw が用意されたかは知らない。

---

## 5. 推奨の進め方

1. **まず案 A** で、現状のまま「Data / API / Process の対応」と「データの流れ 1 枚図」をドキュメントに起こす。これで「どこが分かりにくいか」を共通認識にする。
2. **必要なら案 B** を段階的に適用する。
   - 第一歩: **ib_data の分割**（API 部分と SignalBundle 組み立て部分の分離）。呼び出し側で「取得 → build_signal_bundle → fc」と 2 段に分けるだけでも、流れがかなり分かりやすくなる。
   - 第二歩: signals の「型」と「compute_*」の分離（data.signals と process.layer2.compute）。
   - 第三歩: ディレクトリを data / acquisition / process に再編するかは、規模とチームの好みに合わせて検討。

---

## 6. まとめ表（改善後の責務の目標）

| 責務 | 担当 | 入力 | 出力 | 依存 |
|------|------|------|------|------|
| **Data** | raw_data, signals（型のみ） | — | 型・Protocol | なし（または型同士のみ） |
| **API** | acquisition（例: ib_fetcher） | 接続・パラメータ | Raw の集合 or RawDataProvider | Data (raw) のみ |
| **Process (L2)** | process.layer2（compute_*） | RawDataProvider, as_of | SignalBundle | Data (raw, signals) |
| **Process (L3)** | factor, fc, control_levels | SignalBundle, 因子マッピング | Level, FlightControllerSignal | Data (signals), 因子 |

このように揃えると、「データの流れ」と「API / Data / Process の責務」を説明しやすくなる。
