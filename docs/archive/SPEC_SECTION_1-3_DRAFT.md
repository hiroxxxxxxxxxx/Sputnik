# 仕様書 1-3 改訂ドラフト（プログラムに合わせた案）

以下は、現行実装（Blueprint ベース・層別 Part）に合わせて **1-3. ユニット動力機構** を書き換えたドラフトです。SPEC.md への反映前にレビュー用。

---

## 改訂対象（現行 SPEC.md の記載）

```markdown
### **1-3. ユニット動力機構（ストラテジーバンドル）**

各エンジンユニットには、NQとGCの「バンドル」が装填されている。

* Miniバンドル：NQ/GC（Mini）＋標準OP。メインエンジン専用  
* Microバンドル：MNQ/MGC（Micro）＋Micro OP。姿勢制御エンジン・ブースター用  
* 構成要素：すべてのバンドルは「先物 ＋ PB ＋ CC ＋ BPS」を1パッケージとする  
* 対称配分（1:1）：NQ系列とGC系列のエクスポージャを常に等価に保つ  
* 最大出力上限：NLV $1Mに対し、総エクスポージャ $2M（200%）を上限とする
```

---

## 改訂ドラフト（プログラムに合わせた文言）

```markdown
### **1-3. ユニット動力機構（設計図・Blueprint）**

各エンジンは NQ 専用または GC 専用の 1 インスタンスであり、層ごとの**設計図（LayerBlueprint）**に基づいて 3 層（メイン・姿勢制御・ブースター）で構成される。設計図は TOML 等で定義し、起動時に読み込んで実行中は変更しない（定義書 0-1-Ⅵ）。

* **メインエンジン層**：Mini 先物（NQ/GC）＋ PB ＋ CC ＋ BPS。設計図は Main 用 Blueprint。  
* **姿勢制御エンジン層**：Micro 先物（MNQ/MGC）＋ PB。CC・BPS は装着不可（定義書 5-1, 5-2）。設計図は Attitude 用 Blueprint。  
* **ブースター層**：Micro 先物（MNQ/MGC）＋ BPS。PB・CC は装着不可。設計図は Booster 用 Blueprint。  

* **構成**：層ごとに「先物 ＋ 当該層で装着する操縦翼面（PB/CC/BPS）」を Blueprint の比率で保持する。全層で「先物＋PB＋CC＋BPS」を一括したパッケージではなく、メイン層のみが PB/CC/BPS をすべて持つ。  
* **対称配分（1:1）**：NQ 用エンジンと GC 用エンジンを同構造で組み立て、NQ 系列と GC 系列のエクスポージャを常に等価に保つ。  
* **最大出力上限**：NLV $1M に対し、総エクスポージャ $2M（200%）を上限とする。
```

---

## 変更の要点

| 項目 | 旧（バンドル表記） | 新（プログラム対応） |
|------|-------------------|----------------------|
| 用語 | ストラテジーバンドル / バンドル | 設計図（LayerBlueprint） |
| 単位 | 「バンドルが装填」 | エンジン = NQ 専用 or GC 専用の 1 インスタンス、層は Part + Blueprint |
| Mini/Micro | Miniバンドル / Microバンドル | メイン層＝Mini、姿勢・ブースター層＝Micro（層ごとの設計図） |
| 構成要素 | すべてのバンドルが「先物＋PB＋CC＋BPS」 | メイン層のみ PB/CC/BPS をすべて保持。姿勢は 先物+PB、ブースターは 先物+BPS。 |
| 0-1-Ⅵ | 未言及 | 設計図は起動時読み込み・実行中変更禁止に言及 |

---

## 補足（実装との対応）

* **Engine**：`symbol_type`（NQ/GC）、`blueprints`（Main / Attitude / Booster の LayerBlueprint）、`main_part` / `attitude_part` / `booster_part`。  
* **LayerBlueprint**：`get_ratios(mode)` で Boost/Cruise/Emergency 別の比率を返す。frozen。  
* **contract_symbol(symbol_type, layer_type)**：Mini→NQ/GC、Micro→MNQ/MGC。  
* **MainPart**：wings_pb, wings_cc, wings_bps。  
* **AttitudePart**：wings_pb のみ。  
* **BoosterPart**：wings_bps のみ。

このドラフトを SPEC.md の 1-3 にそのまま差し替えるか、文言を調整したうえで反映してください。
