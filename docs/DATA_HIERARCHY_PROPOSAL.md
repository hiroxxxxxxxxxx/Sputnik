# 定義書 4-2 に基づく Raw Data / Signal / Factor 分離の対応案

定義書「情報の階層構造（Data Hierarchy）」に従い、Layer 1（Raw Data）・Layer 2（Signals）・Layer 3（Factors）を責務ごとに分離する設計案です。

**実装済み（2025-03）**: `avionics/raw_data.py`（Layer 1）、`avionics/signals.py`（Layer 2）、`Avionics.update_all(signal_bundle)` および各因子の `update_from_*_signals` 系 API。テストは `tests/avionics/test_signals_and_hierarchy.py`。

---

## 1. 定義書の階層（再掲）

| 階層 | 名称 | 内容 | 役割 |
|------|------|------|------|
| Layer 1 | Raw Data | 終値・出来高・IV・金利・証拠金・VIX | 未加工の市場・内部データ |
| Layer 2 | Signals | トレンド・日次変動率・累積変動率・Hourlyショック | 統計加工した共通部品。**複数因子が共有参照** |
| Layer 3 | Factors | P/V/L/T/U/S（各 0/1/2 判定） | シグナルのみを入力に状態判定 |
| Layer 4 | Control Levels | ICL/SCL/LCL → Effective | 既存（Avionics / OSCore） |

**原則**: 因子（Layer 3）は **Layer 2 の出力のみ**を入力とする。Raw Data を直接触らない。

---

## 2. 現状の整理

| 因子 | 現在の入力 | 種別 | 備考 |
|------|------------|------|------|
| P | daily_change, cum5_change, downside_gap, trend, cum2_change | いずれも Signal | すでにシグナル前提。Raw（終値系列）から誰が計算するかは未定義 |
| V | index_value (VXN/GVZ), altitude | 指数=Rawに近い／Signal扱い可 | 終値確定値なら Layer 2 出力として扱うのが自然 |
| L | below_sma20, daily_change, tip_drawdown_from_high, altitude | Signal | **銘柄（NQ/GC）ごとに別定義**（Nasdaq は credit 系、Gold は TIP 等）。共通部分も Signal として Layer 2 で算出 |
| T | trend | **Signal（銘柄別）** | **特定銘柄のトレンドは Signal**。T はその Signal を入力に 0/2 を出力し SCL へ渡す。P と共通のトレンドシグナルを参照（定義書 4-2-2） |
| U | mm_over_nlv (MM/NLV) | 比率＝加工済み | Raw は MM と NLV。比率計算は Layer 2 に寄せる |
| S | span_ratio (Current/Base Density) | 比率＝加工済み | Raw は MM・現在値・倍率・Base Density。比率計算は Layer 2 |

**ギャップ**  
- Raw を保持・提供する **Layer 1** がコード上にない。  
- Raw → Signal を一括計算する **Layer 2** モジュールがなく、「呼び出し元がシグナルを計算して渡す」前提のまま。

---

## 3. 対応案の概要

1. **Layer 1（Raw Data）**  
   - 未加工データの「型」と「取得インターフェース」を定義する。  
   - 実体（DB・API・CSV 等）は別モジュールや外部システムに委譲する。

2. **Layer 2（Signals）**  
   - Raw のみを入力に、定義書で言及されているシグナルを一括計算するモジュールを新設する。  
   - 因子はこのモジュールの出力（のみ）を参照する。

3. **Layer 3（Factors）**  
   - 既存の `update_from_signals` / `update_from_ratio` を「Layer 2 出力を渡す窓口」として明示する。  
   - 必要に応じて「シグナル用の型（構造体）」を導入し、Factor は Raw を引数に取らないようにする。

---

## 4. Layer 1（Raw Data）の設計案

### 4.1 役割

- 終値・高値・出来高・IV・証拠金・金利・VIX 等の **未加工データ** を保持または取得する。  
- **加工（変動率・トレンド・SMA・比率など）は行わない**。  
- 実装は「インメモリ」「DB」「外部 API」のどれでもよいが、**インターフェースを共通化**する。

### 4.2 インターフェース案（Protocol）

```python
# avionics/raw_data.py または data/layer1.py のイメージ

from typing import Protocol, Optional, List
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class PriceBar:
    """1本の価格（終値・高値・出来高など）。Layer 1 の最小単位の一例。"""
    date: date
    close: float
    high: float
    volume: float
    # 必要に応じて open, low 等

@dataclass(frozen=True)
class RawMarketSnapshot:
    """銘柄・日次の Raw スナップショット。Layer 2 が参照する。"""
    symbol: str  # "NQ" | "GC"
    as_of: date
    # 価格系列（直近 N 本）は別メソッドで取得する想定
    # または close_series, high_series をここに含める

@dataclass(frozen=True)
class RawCapitalSnapshot:
    """証拠金・NLV 等の内部 Raw。U/S 用シグナル計算の元。"""
    as_of: date
    mm: float
    nlv: float
    # SPAN 用: current_density, base_density など

class RawDataProvider(Protocol):
    """Layer 1 の取得窓口。実装は DB/API/CSV 等。"""
    def get_price_series(self, symbol: str, limit: int) -> List[PriceBar]: ...
    def get_volatility_index(self, symbol: str, as_of: date) -> Optional[float]: ...  # VXN/GVZ
    def get_capital_snapshot(self, as_of: date) -> Optional[RawCapitalSnapshot]: ...
    # HYG/LQD/TIP 用の get_credit_series, get_tip_series 等は必要に応じて
```

- まずは **Protocol と dataclass で「型」だけ** をプロジェクトに置き、実データ取得は後から差し替え可能にするとよい。

---

## 5. Layer 2（Signals）の設計案

### 5.1 役割

- **Layer 1 の出力のみ**を入力に、定義書で言及されているシグナルを計算する。  
- トレンド（Up/Down/Flat）・日次変動率・累積変動率・Downside Gap・SMA20 関係・証拠金比率などは **すべて Layer 2 で算出**し、因子は受け取るだけにする。

### 5.2 シグナル種別（定義書・現行因子から抽出）

| シグナル名 | 用途 | 算出元（Raw） |
|------------|------|----------------|
| trend | P, T（SCL） | 終値 vs SMA20×1.005 / 0.995 |
| daily_change | P, L（credit） | 終値の日次変動率 |
| cum5_change | P | 過去5営業日累積変動率 |
| cum2_change | P | 過去2営業日累積変動率 |
| downside_gap | P | (終値/過去20日高値) - 1 |
| index_value (VXN/GVZ) | V | Raw の指数終値（そのまま渡すか、ここで正規化） |
| below_sma20 | L（credit） | HYG/LQD 終値 vs SMA20 |
| tip_drawdown_from_high | L（tip） | TIP 高値比ドローダウン |
| mm_over_nlv | U | MM / NLV |
| span_ratio | S | Current Density / Base Density |
| altitude | V, L | フライトプラン／設定（Raw ではなくコンテキスト） |

- **trend**: 銘柄ごとのトレンド Signal。T 因子はこれを入力に level 0/2 を出し SCL へ渡す。
- **L**: NQ（Nasdaq）と GC（Gold）で別定義。below_sma20 / daily_change / tip_drawdown 等の共通部分も Signal として Layer 2 で算出し、L 因子は Signal のみを入力とする。

### 5.3 モジュール・API 案

```python
# avionics/signals.py または data/signals.py のイメージ

from dataclasses import dataclass
from typing import Optional, Literal

TrendType = Literal["up", "down", "flat"]

@dataclass(frozen=True)
class PriceSignals:
    """P 因子用。定義書 Layer 2：トレンド・日次変動率・累積変動率・Downside Gap。"""
    symbol: str
    trend: TrendType
    daily_change: float
    cum5_change: float
    cum2_change: Optional[float]
    downside_gap: float

@dataclass(frozen=True)
class VolatilitySignal:
    """V 因子用。指数値＋高度はコンテキストで別注入でも可。"""
    index_value: float
    altitude: Literal["high_mid", "low"]

@dataclass(frozen=True)
class LiquiditySignals:
    """L 因子用。credit / tip で必要な項目が異なる。"""
    altitude: Literal["high_mid", "low"]
    below_sma20: Optional[bool] = None
    daily_change: Optional[float] = None
    tip_drawdown_from_high: Optional[float] = None

@dataclass(frozen=True)
class CapitalSignals:
    """U, S 用。"""
    mm_over_nlv: float
    span_ratio: float

def compute_price_signals(raw_provider: RawDataProvider, symbol: str, as_of: date) -> PriceSignals:
    """終値系列から trend, daily_change, cum5, cum2, downside_gap を算出。"""
    series = raw_provider.get_price_series(symbol, limit=32)
    # ここで SMA20, 変動率, gap を計算
    ...
    return PriceSignals(...)

def compute_volatility_signal(raw_provider: RawDataProvider, symbol: str, as_of: date, altitude: str) -> VolatilitySignal:
    v = raw_provider.get_volatility_index(symbol, as_of) or 0.0
    return VolatilitySignal(index_value=v, altitude=altitude)

def compute_capital_signals(raw_provider: RawDataProvider, as_of: date) -> CapitalSignals:
    cap = raw_provider.get_capital_snapshot(as_of)
    ...
    return CapitalSignals(mm_over_nlv=..., span_ratio=...)
```

- **共有**: トレンドは `compute_price_signals` で 1 回だけ計算し、P と T（および SCL）が同じ値を使う（定義書「P因子・SCLが共通参照する共用シグナル」）。

### 5.4 配置の選択肢

- **A) avionics 配下**  
  `avionics/raw_data.py`, `avionics/signals.py`  
  - 計器レイヤー内で「データ階層」を完結させたい場合向き。  
- **B) 専用パッケージ**  
  `data/` または `signals/` を新設し、`data/layer1.py`, `data/layer2.py`  
  - データパイプラインを将来拡張しやすい。  
- **C) 既存 config 隣**  
  `config/` と並べて `data/` を置く。  

いずれでも、「Factor は data を import して Raw を読まない」「Factor は Signals の型だけ import して、値は Avionics 経由で受け取る」という依存方向にするとよい。

---

## 6. Layer 3（Factors）との接続

### 6.1 契約の明確化

- 各因子は **「Layer 2 の出力」だけ**を引数に取るメソッドを公式の更新 API とする。  
  - 例: `PFactor.update_from_signals(signals: PriceSignals)`  
  - 既存の `update_from_signals(daily_change=..., trend=..., ...)` を、内部で `PriceSignals` を分解する形にリネーム／統合してもよい。

- **update() の役割**  
  - 「Avionics が保持している最新シグナル」を、各因子に渡して `update_from_signals`（または `update_from_ratio`）を呼ぶだけにする。  
  - シグナルの「計算」は Avionics ではなく、**Layer 2 モジュール**が行う。

### 6.2 Avionics の役割

- **現状**: `update_all()` で各因子の `update()` を呼ぶ。因子は未注入時はデフォルト値で自己更新。  
- **分離後**  
  1. 外部（Orchestrator や Pulse）で、RawDataProvider から最新 Raw を取得。  
  2. Layer 2 の `compute_*` でシグナルを計算。  
  3. 計算したシグナルを Avionics に「渡す」か、Avionics が「SignalProvider」を保持して `update_all()` 内で取得。  
  4. `update_all(signals_by_symbol, capital_signals)` のような形で、因子ごとに適切なシグナルを渡し、`factor.update_from_signals(...)` を呼ぶ。

- Avionics は **「どの因子にどのシグナルを渡すか」** だけを担当し、Raw の取得やシグナル計算は行わない（Layer 2 に委譲）。

### 6.3 段階的移行

1. **Phase 1**  
   - `avionics/signals.py` を新設し、`PriceSignals` 等の dataclass と `compute_price_signals` 等の関数だけを定義。  
   - 中身はスタブでもよい。因子のインターフェースはまだ既存のまま。

2. **Phase 2**  
   - `RawDataProvider` の Protocol と、最小限の Raw 型（例: PriceBar, RawCapitalSnapshot）を定義。  
   - `compute_price_signals` を「RawDataProvider を引数に取り、PriceSignals を返す」実装にし、テスト用のモック Provider で単体テスト。

3. **Phase 3**  
   - Avionics の `update_all(signals: ...)` を追加し、呼び出し元（または Orchestrator）で Layer 1 → Layer 2 を実行したうえで、その結果を Avionics に渡す。  
   - 既存の `update()` は「シグナル未注入時のデフォルト」として残し、両立させる。

4. **Phase 4**  
   - 因子の `update_from_signals` を、引数を `PriceSignals` 等の型にまとめて受け取る形にリファクタし、docstring で「Layer 2 出力のみを入力とする」と明記。

---

## 7. まとめ

| レイヤー | 責務 | 新設・変更の要点 |
|----------|------|------------------|
| **Layer 1** | Raw Data の保持・提供 | Protocol と dataclass で型を定義。実装は別モジュールや外部に委譲。 |
| **Layer 2** | Raw → Signals の計算。複数因子が共有するシグナルを一括算出 | `signals` モジュールと `compute_*` 関数。トレンドは P/T/SCL で共有。 |
| **Layer 3** | シグナルのみを入力に 0/1/2 判定 | 既存 Factor はそのまま。入力を「Layer 2 出力」と明示し、Raw を渡さない。 |
| **Avionics** | シグナルを因子に配り、update を駆動 | `update_all(signals)` で Layer 2 の結果を注入。Raw は扱わない。 |

この分離により、定義書 4-2 の「情報の階層構造」と、**Raw Data / Signal / Factor の責務分離**をコード上で満たせます。

---

*定義書「4-2 OS構造」「情報の階層構造（Data Hierarchy）」に基づく対応案。実装時はテストと後方互換に配慮しつつ Phase 1 から順次適用することを推奨する。*
