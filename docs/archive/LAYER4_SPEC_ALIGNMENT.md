# 定義書に合わせた Layer 4（Control Levels）修正案

定義書「4-2 情報の階層構造」「3層制御構造」に従い、ICL / SCL / LCL を明示し、Effective Level でモード決定する形に揃えるための修正案です。

---

## 定義書の式（再掲）

```
ICL = max(P, V, L)   ← 銘柄ごと（L も銘柄ごと。NQ と GC で別定義）
SCL = T相関ロジック   ← T は銘柄別トレンドの Signal を入力にした因子。両Downtrend=2, 片方=1, 両Uptrend=0
LCL = max(U, S)
Effective Level = max(ICL, SCL, LCL)
スロットルモード: Effective 0→Boost, 1→Cruise, 2→Emergency
```

**T と L の位置づけ（情報の階層）**

- **T**: 入力は **特定銘柄のトレンド** であり、これは **Layer 2 の Signal**。T 因子はその Signal を消費して level 0/2 を出力し、SCL の入力となる。level そのものも「トレンドの Signal を因子で量化したもの」として扱う。
- **L**: **Nasdaq（NQ）と Gold（GC）で別定義**（例: NQ は credit 系 HYG/LQD、GC は TIP 等）。共通する判定要素（below_sma20, daily_change, tip_drawdown 等）も **Signal（Layer 2）** として算出し、L 因子は Signal のみを入力とする。L は銘柄ごとに登録する（ICL は銘柄ごとに max(P, V, L) で L もその銘柄の L を使う）。

---

## 現状とのギャップ

| 項目 | 現状 | 定義書 |
|------|------|--------|
| ICL | `get_market_level(symbol)` に T も含まれる（max(P,V,T,L)） | ICL = max(P, V, L) のみ。T は SCL 用。**L は銘柄ごと** |
| SCL | 銘柄別 M と艦隊 M に暗黙に含まれる | 明示的に「T 相関」で 0/1/2。T の入力は銘柄別トレンド Signal |
| LCL | `get_capital_level()` で実質 LCL | 同じ |
| Effective | M×C の2変数でモード決定 | Effective = max(ICL, SCL, LCL) の1変数でモード決定 |

---

## 修正方針

1. **Avionics** で ICL / SCL / LCL を定義書どおりに算出し、Effective を追加する。
2. **OSCore** では、Effective のみでモードを決める（定義書の対応表に合わせる）。必要なら従来の M×C 表はレガシーとして残す。

---

## 1. Avionics の変更

### 1.1 因子の役割分け

- **ICL 用**: 銘柄ごと P, V, **L**。L は NQ/GC で別定義のため **銘柄ごとの L** を symbol_factors に含め、ICL(symbol) = max(P, V, L) はその銘柄の P, V, L のみで算出する。
- **SCL 用**: 銘柄ごと T。T の入力は **銘柄別トレンドの Signal（Layer 2）**。SCL は全銘柄の T の level から 1 つだけ算出。
- **LCL 用**: U, S（現行の `get_capital_level()` と同じ）。

実装では、`symbol_factors[symbol]` に P, V, L, T をすべて銘柄ごとに持つ形を想定する（L を global ではなく銘柄別にすると定義書と一致する）。ICL/SCL の区別:

- **A) 型で判定**: `isinstance(f, (PFactor, VFactor, LFactor))` → ICL。`isinstance(f, TFactor)` → SCL。
- **B) 登録グループを分ける**: 例）`icl_factors_per_symbol`, `scl_factors` のように登録時から分けて持つ。

ここでは **A) 型で判定** する案で揃える。L を銘柄ごとに登録する場合は、`symbol_factors["NQ"] = [P_NQ, V_NQ, L_NQ, T_NQ]`, `symbol_factors["GC"] = [P_GC, V_GC, L_GC, T_GC]` のようにする。

### 1.2 追加・変更する API

```python
# 追加
async def get_icl(self, symbol: str) -> int:
    """ICL = max(P, V, L) を銘柄 symbol について返す。T は含めない。"""
    # global_market_factors (L) + symbol_factors[symbol] のうち P, V のみ
    ...

async def get_scl(self) -> int:
    """SCL = T 相関。両 Downtrend→2, 片方→1, 両 Uptrend→0。銘柄が1つの場合はその T のレベル。"""
    # symbol_factors から T 因子のみを集め、定義書 4-2-2 のロジック
    ...

async def get_lcl(self) -> int:
    """LCL = max(U, S)。get_capital_level() と同じ。"""
    return await self.get_capital_level()

async def get_effective_level(self, symbol: str) -> int:
    """Effective Level = max(ICL(symbol), SCL, LCL)。定義書 4-2。"""
    icl = await self.get_icl(symbol)
    scl = await self.get_scl()
    lcl = await self.get_lcl()
    return max(icl, scl, lcl)
```

- `get_market_level(symbol)` は **後方互換** のため残す。実装を「ICL(symbol) と SCL の max」に変えるか、あるいは「ICL のみ」に変えて「従来の M ≒ max(ICL, SCL) 相当」を呼び出し元で組み立てるかは、OSCore をどう変えるかと合わせて決める（下記 2. の方針に合わせる）。

### 1.3 get_icl の実装イメージ

- L を銘柄ごとにする場合: `relevant = [f for f in self._symbol_factors.get(symbol, []) if isinstance(f, (PFactor, VFactor, LFactor))]` で、その銘柄の P, V, L のみから max。
- L を従来どおり global に置く場合: `relevant = [f for f in (self._global_market_factors + self._symbol_factors.get(symbol, [])) if isinstance(f, (PFactor, VFactor, LFactor))]`。
- `return max(f.level for f in relevant)`（空なら 0）。

### 1.4 get_scl の実装イメージ

- 全 `symbol_factors` から T 因子だけ取り出す（`isinstance(f, TFactor)`）。
- 銘柄が **2 つ以上**: 各銘柄の T レベル（0 or 2）を取得し、  
  - すべて 2 → SCL = 2  
  - いずれか 1 つが 2 → SCL = 1  
  - すべて 0 → SCL = 0  
- 銘柄が **1 つ**: その銘柄の T のレベルをそのまま SCL とする（0 or 2）。

---

## 2. OSCore の変更

### 2.1 サブスクリプション時（定義書準拠）

- 各エンジンについて  
  `effective = await self.avionics.get_effective_level(engine.symbol_type)`  
  のみでモードを決定する。
- モード決定: **Effective 0→Boost, 1→Cruise, 2→Emergency**（定義書の表どおり）。
- つまり `_determine_mode(m, c)` の代わりに、  
  `_determine_mode_from_effective(effective: int) -> ModeType` を新設し、  
  `effective` の 0/1/2 をそのまま Boost/Cruise/Emergency に写像する。

```python
@staticmethod
def _determine_mode_from_effective(effective: int) -> ModeType:
    """定義書 4-2 Effective Level × スロットルモード対応表。"""
    if effective == 0:
        return "Boost"
    if effective == 1:
        return "Cruise"
    return "Emergency"
```

- サブスクリプション時の `_pulse_subscription` では、  
  - 各エンジンで `effective = await self.avionics.get_effective_level(engine.symbol_type)`  
  - `target_mode = self._determine_mode_from_effective(effective)`  
  とし、Emergency 時のコールバック・プロトコル実行は現行どおり行う。

### 2.2 レガシー時（単一 M/C）

- 引数なしの Avionics では銘柄が実質 1 つ（NQ）のため、  
  - `effective = await self.avionics.get_effective_level("NQ")` で統一するか、  
  - 従来どおり `get_market_level()` / `get_capital_level()` で M, C を取り、  
    `Effective = max(M, C)` と解釈して `_determine_mode_from_effective(Effective)` を呼ぶか、のどちらかでよい。
- 定義書の「Effective = max(ICL, SCL, LCL)」に合わせるなら、レガシーでも `get_effective_level("NQ")` があればそれを使うのが一貫する。

### 2.3 M×C 表の扱い

- 定義書の「情報の階層構造」では、**Effective の 0/1/2 のみ**でモードが決まる。
- 別セクション（4-2-1-5 等）で M×C 表が参照されている場合は、  
  「Effective = max(ICL, SCL, LCL) と M×C の関係」を定義書側で確認したうえで、  
  - 実装は Effective ベースに統一し、  
  - M×C は「ICL/SCL/LCL をまとめた結果」として説明する、  
  という整理が考えられる。

---

## 3. 実装順序の提案

1. **Avionics**: `get_icl(symbol)`, `get_scl()`, `get_lcl()`（= `get_capital_level()`）, `get_effective_level(symbol)` を追加。型判定は `_update_all_from_signals` と同様に `isinstance` で P/V/L/T を区別。
2. **OSCore**: `_determine_mode_from_effective(effective)` を追加。サブスクリプション時は `get_effective_level(symbol)` のみでモード決定に切り替え。
3. **レガシー**: `get_effective_level("NQ")` を使うか、M/C から `effective = max(M, C)` で `_determine_mode_from_effective` を呼ぶかで統一。
4. **テスト**: ICL/SCL/LCL が定義書どおりになるケースと、Effective → Boost/Cruise/Emergency の対応表どおりになるケースを追加。

---

## 4. 補足（T と L の Signal 扱い）

- **T**: 特定銘柄のトレンドは **Layer 2 の Signal**。T 因子はその Signal（up/down/flat）を入力に level 0/2 を出力する。level は SCL の入力として扱う。TFactor は `levels=[0, 2]` で、SCL の「T 相関ロジック」にそのまま使える。
- **L**: Nasdaq（NQ）と Gold（GC）で **別定義**（基準・閾値が異なる）。共通する要素（below_sma20, daily_change, tip_drawdown_from_high 等）も **Signal（Layer 2）** として算出し、L 因子は Raw を直接見ず Signal のみを入力とする。L は銘柄ごとに登録する想定（ICL = max(P, V, L) の L はその銘柄の L）。

---

*定義書「4-2 情報の階層構造」「3層制御構造」「4-2-2 SCL」に基づく修正案。*
