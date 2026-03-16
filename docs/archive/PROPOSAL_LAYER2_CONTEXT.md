# 案2: Layer2Context による「共通コンテキスト」の詳細

`_update_all_from_signals` で FC が各因子の型を `isinstance` で分岐している問題を、**「因子に渡す引数オブジェクトを共通化する」**ことで解消する案の詳細。因子は `SignalBundle` を直接受けず、**Layer2Context** だけを受け取る。

---

## 1. 目的とアイデア

- **現状**: FC が `bundle.price_signals.get(symbol)` や `bundle.liquidity_credit` などを取り出し、因子の型に応じて `update_from_price_signals(price)` や `update_from_ratio(cap.mm_over_nlv)` など**別メソッド**を呼んでいる。
- **案2の狙い**:
  - FC は「**コンテキストを 1 つ組み立てて、全因子に同じインターフェースで渡す**」だけにする。
  - 因子は **`update_from_context(ctx, symbol)`** のような**共通メソッド**だけ持つ。中で `ctx` から自分に必要な情報を取りにいく。
  - 因子は **SignalBundle の型に依存しない**。`Layer2Context` という「Layer 2 の情報を因子向けに提供するインターフェース」だけに依存する。

---

## 2. Layer2Context の設計

「コンテキスト」には 2 つの設計の幅がある。

### 2.1 ラッパー型（推奨）

**Context は SignalBundle をラップし、因子が取りにいくためのアクセサだけを提供する。**

- **保持**: `SignalBundle` への参照（またはコピー）を 1 つ持つ。
- **提供**: 銘柄別・グローバルな「取り出し方」をメソッド or プロパティで固定する。
  - 因子は `ctx.price(symbol)` / `ctx.volatility(symbol)` / `ctx.liquidity_credit` / `ctx.capital` のように**コンテキストの API だけ**を知る。
  - 中身の型（`PriceSignals`, `VolatilitySignal` 等）はそのまま返してよい。因子は「P 用のシグナル」「V 用のシグナル」という**Layer 2 の型**には依存するが、**SignalBundle という入れ物**には依存しなくなる。

```python
# イメージ
@dataclass(frozen=True)
class Layer2Context:
    """Layer 2 の出力を因子向けに提供するコンテキスト。SignalBundle から構築する。"""
    _bundle: SignalBundle

    def price(self, symbol: str) -> Optional[PriceSignals]:
        return self._bundle.price_signals.get(symbol)

    def volatility(self, symbol: str) -> Optional[VolatilitySignal]:
        return self._bundle.volatility_signals.get(symbol)

    @property
    def liquidity_credit(self) -> Optional[LiquiditySignals]:
        return self._bundle.liquidity_credit

    @property
    def liquidity_credit_lqd(self) -> Optional[LiquiditySignals]:
        return getattr(self._bundle, "liquidity_credit_lqd", None)

    @property
    def liquidity_tip(self) -> Optional[LiquiditySignals]:
        return self._bundle.liquidity_tip

    @property
    def capital(self) -> Optional[CapitalSignals]:
        return self._bundle.capital_signals
```

- **つくり方**: `Layer2Context.from_bundle(bundle: SignalBundle) -> Layer2Context` のようなファクトリで、`_bundle` を保持するだけ。実装は上記のように薄いラッパーでよい。
- **メリット**: 既存の `PriceSignals` / `VolatilitySignal` / `LiquiditySignals` / `CapitalSignals` をそのまま使える。Context の追加フィールドが少なく、bundle と二重管理にならない。
- **デメリット**: 因子は依然として「P 用は PriceSignals」「V 用は VolatilitySignal」という**Layer 2 の具象型**を知る。テストで「bundle の代わりに context を差し替える」ことはしやすくなるが、型の抽象度は「bundle を隠す」ところまで。

---

### 2.2 完全 DTO 型（オプション）

**Context が「因子が本当に必要とする最小の値」だけを持ち、Layer 2 の型名を隠す。**

- Context のフィールドを「P 用」「V 用」など**用途別の専用 DTO** に分け、それらは `PriceSignals` などの名前を露出しない。
  - 例: `ctx.price_context(symbol)` が返す型を `PriceContext` とし、中身は `trend`, `daily_change`, `daily_history` などだけ持つ。P 因子は `PriceContext` にだけ依存する。
- **メリット**: 因子が Layer 2 の既存 dataclass（PriceSignals 等）に直接依存しなくできる。テストでは「最小のスタブ」だけ用意すればよい。
- **デメリット**: PriceSignals → PriceContext のような**写像が増える**。SignalBundle の変更時に Context の組み立てと DTO の両方をメンテする必要がある。実装コストが大きい。

実務では **2.1 ラッパー型** から入り、必要になったら 2.2 に寄せる、という段階でよい。

---

## 3. 誰が・いつつくるか

- **つくる場所**: `Layer2Context.from_bundle(bundle)` は **avionics 側**（例: `avionics/Instruments/signals.py` か `avionics/context.py`）に置く。SignalBundle を定義しているモジュールの近くがよい。
- **つくるタイミング**: FC の `_update_all_from_signals(bundle)` の**先頭**で 1 回だけつくる。
  - `ctx = Layer2Context.from_bundle(bundle)`
  - 以降、全因子に `ctx` と `symbol`（または `None`）を渡すだけ。

---

## 4. 因子のインターフェース

- **共通メソッド**: 各因子が **`async def update_from_context(self, ctx: Layer2Context, symbol: Optional[str]) -> None`** を実装する。
  - `symbol` は銘柄別因子のときはその銘柄、limit 因子（U/S）のときは `None`。
- **BaseFactor**: デフォルト実装で `await self.update()` を呼ぶ（コンテキストを使わないフォールバック）。
- **各因子の中身（例）**:
  - **P**: `price = ctx.price(symbol)` → `price` が非 None なら既存の `update_from_price_signals(price)` を呼ぶ。否则 `update()`。
  - **V**: `vol = ctx.volatility(symbol)` → 同様に `update_from_volatility_signal(vol)` または `update()`。
  - **T**: `price = ctx.price(symbol)` → `apply_trend(price.trend, daily_history=...)` または `update()`。
  - **C**: `lc = ctx.liquidity_credit`, `lc_lqd = ctx.liquidity_credit_lqd` → 既存の `update_from_signals(...)` または `update()`。
  - **R**: `lt = ctx.liquidity_tip` → 既存の `update_from_signals(...)` または `update()`。
  - **U**: `cap = ctx.capital` → `cap` が非 None なら `update_from_ratio(cap.mm_over_nlv)`、否则 `update()`。
  - **S**: 同様に `update_from_ratio(cap.span_ratio)` または `update()`。

因子は **自分が何であるか（P/V/T/C/R/U/S）** だけ知っていればよく、**FC は因子の型を一切知らない**。

---

## 5. FC 側の変更後（イメージ）

```python
async def _update_all_from_signals(self, bundle: SignalBundle) -> None:
    ctx = Layer2Context.from_bundle(bundle)
    tasks = []
    for symbol, factors in self._mapping.symbol_factors.items():
        for f in factors:
            tasks.append(f.update_from_context(ctx, symbol))
    for f in self._mapping.global_market_factors:
        tasks.append(f.update())
    for f in self._mapping.limit_factors:
        tasks.append(f.update_from_context(ctx, None))
    if tasks:
        await asyncio.gather(*tasks)
```

- `isinstance` は一切不要。新因子を追加しても FC は変更しない。
- `global_market_factors` は現状どおり `update()` のみでよい（コンテキスト不要ならそのまま）。

---

## 6. 依存関係の変化

| 対象 | 現状 | 案2 後 |
|------|------|--------|
| FlightController | SignalBundle と各因子の**具象型**（PFactor, VFactor, …）に依存 | SignalBundle と **Layer2Context** にのみ依存。因子は「update_from_context を持つ何か」として扱う |
| 各因子 | 自分用の Layer 2 型（PriceSignals 等）と **SignalBundle は知らない**（FC が切り出して渡す） | **Layer2Context** と自分用の Layer 2 型（ctx から取得）に依存。**SignalBundle は直接参照しない** |
| テスト | 因子単体では「update_from_price_signals(price)」などにモックを渡す | 因子単体では **Layer2Context のモック**（必要なメソッドだけ返す）を渡せる。FC のテストでは bundle の代わりに **context を差し替え**可能 |

---

## 7. メリット・デメリット・注意点

**メリット**

- FC が「配布ロジック」から解放され、**コンテキストを渡すだけ**の責務になる。
- 新因子追加時、FC を触らず**因子側に `update_from_context` を 1 本足す**だけでよい。
- 因子は **SignalBundle に直接依存しない**ため、将来「bundle 以外から context を組み立てる」（別データソース・テスト用スタブ）にしやすい。
- テストで「最小の context」だけ用意すればよく、bundle 全体を組み立てなくてよい。

**デメリット**

- **Context 型の定義・メンテ**が 1 つ増える。bundle にフィールドが増えたら、context の API を拡張する必要がある（ラッパーなら `from_bundle` とアクセサの追加で済む）。
- 因子は **Layer2Context のインターフェース**に依存する。context の API を破壊的に変えると全因子の修正が発生する。
- 現状の「因子が持つ既存メソッド」（`update_from_price_signals` 等）は **因子の内部実装**として残す形になる。それらを context 経由でしか呼ばないようにするかは、リファクタの度合い次第。

**注意点**

- `Layer2Context` を **immutable**（例: frozen dataclass + `_bundle` 参照のみ）にしておくと、「更新の流れ」が読みやすく、テストでも安全。
- 非同期の有無は現状に合わせる。`update_from_context` が async なら、FC は `asyncio.gather` でまとめて await すればよい。

---

## 8. 実装ステップ例（ラッパー型で進める場合）

1. **Layer2Context を定義**（`signals.py` または `context.py`）  
   - `from_bundle(bundle: SignalBundle) -> Layer2Context`  
   - 上記のような `price(symbol)`, `volatility(symbol)`, `liquidity_credit`, `liquidity_tip`, `capital` を提供。

2. **BaseFactor に `update_from_context(ctx, symbol)` を追加**  
   - デフォルトは `await self.update()`。

3. **P / V / T / C / R / U / S で `update_from_context` を実装**  
   - 中で `ctx.price(symbol)` 等を呼び、既存の `update_from_*` に渡す。取れない場合は `update()`。

4. **FC の `_update_all_from_signals` を書き換え**  
   - 先頭で `ctx = Layer2Context.from_bundle(bundle)`。  
   - 全因子に `update_from_context(ctx, symbol)` または `update_from_context(ctx, None)` を渡すだけにし、`isinstance` を削除。

5. **テスト**  
   - 因子単体: Layer2Context のモックで `update_from_context` が期待どおり既存ロジックを呼ぶことを確認。  
   - FC: 既存の `update_all(signal_bundle=bundle)` 系テストがそのまま通ることを確認。

---

## 9. 案1（update_from_bundle）との違い

| 観点 | 案1: update_from_bundle(bundle, symbol) | 案2: update_from_context(ctx, symbol) |
|------|----------------------------------------|---------------------------------------|
| 因子が依存する型 | **SignalBundle**（bundle.price_signals 等を自分で触る） | **Layer2Context**（ctx.price(symbol) 等の API だけ触る） |
| テスト時の差し替え | bundle をモックする必要がある | context をモックすればよい（bundle の形を隠せる） |
| 新規データソース | 因子が「bundle に似た別オブジェクト」を扱う必要がある | 「context を別ソースから組み立てる」だけで、因子は変更不要 |
| 実装コスト | 小（各因子に 1 メソッド + FC の簡略化） | 中（Context 型の定義 + 各因子の実装 + FC の簡略化） |

「引数オブジェクトの共通化」を**インターフェースの共通化**まで突き詰めるなら案2、**FC の型分岐をなくす**だけで十分なら案1、という使い分けになる。
