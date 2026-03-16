# RawDataProvider の配置・名前の改善案

**※ 案2 を実施済み（data/cache.py に CachedRawDataProvider を配置）**

## 現状の分かりにくさ

| 場所 | 内容 | 役割 |
|------|------|------|
| **data/raw.py** | PriceBar, RawCapitalSnapshot 等の**値型** ＋ **RawDataProvider**（Protocol＝抽象インターフェース） | 型と「取得窓口」の**定義** |
| **acquisition/ib_fetcher.py** | **CachedRawDataProvider**（RawDataProvider を**実装**）＋ IB 取得ロジック | 抽象の**実装**が acquisition にある |

- 「raw」というファイル名に「型」と「インターフェース」が同居しており、**実装**は別フォルダ（acquisition）にあるため、継承関係が追いにくい。
- 「抽象が data、実装が acquisition」という分離は案Bの設計どおりだが、**実装が 1 つしかない**現状では「Protocol の実装はどこ？」が直感で見つけにくい。

---

## 改善案

### 案1: 名前で「型」と「インターフェース」を分ける（軽い変更）

- **data/raw.py** … **値型のみ**（PriceBar, PriceBar1h, RawCapitalSnapshot, VolatilitySeriesPoint）
- **data/raw_provider.py** … **RawDataProvider Protocol のみ**（新規）
- **acquisition/ib_fetcher.py** … 現状どおり（CachedRawDataProvider ＋ IB 取得）

**効果**: 「raw = Raw の形」「raw_provider = 取得インターフェース」とファイル名で対応が付く。実装が acquisition にあることは変わらないが、定義側の役割は明確になる。

---

### 案2: Protocol の「汎用実装」を data に寄せる（推奨）

**考え方**: CachedRawDataProvider は **IB に依存しない**「メモリキャッシュ」の実装。取得元（IB / DB / CSV）に依存しないので、**Data 層の実装**として data に置く。

| 場所 | 内容 | 役割 |
|------|------|------|
| **data/raw.py** | 値型 ＋ **RawDataProvider**（Protocol） | Raw の形と取得インターフェースの定義 |
| **data/cache.py** | **CachedRawDataProvider**（RawDataProvider を実装） | 「メモリに保持して返す」汎用実装（取得手段に非依存） |
| **acquisition/ib_fetcher.py** | IBDataFetcher, fetch_raw, _bar_to_*, _contract_* のみ | IB から取得し、**data.cache.CachedRawDataProvider に詰めて返す** |

**効果**:
- **抽象（Protocol）とその 1 つ目の実装（Cache）が同じ data 配下**になり、継承関係がフォルダ内で追える。
- acquisition は「IB 呼び出しと変換」だけに集中し、**「RawDataProvider を実装したクラス」を定義しない**。
- ファイル名と中身の対応: `raw.py` = Raw の型とインターフェース、`cache.py` = そのキャッシュ実装。

**依存の向き**: data ← acquisition（acquisition が data.cache を import して利用）。Process（bundle_builder, compute）は従来どおり data.raw の RawDataProvider にのみ依存。

---

### 案3: ドキュメントのみで補足（変更なし）

- **data/raw.py** の docstring に「RawDataProvider の実装例: `avionics.acquisition.ib_fetcher.CachedRawDataProvider`」と明記。
- **docs/spec/ARCHITECTURE.md** または **docs/archive/DATA_FLOW_AND_DEPENDENCIES.md** に「型・Protocol と実装の対応表」を 1 表追加。

**効果**: コード配置はそのまま。どこに何があるかを文書で補強するだけ。

---

## 推奨

**案2** を推奨する。

- ファイル名（raw / cache）と「型・Protocol / 実装」の対応がはっきりする。
- 継承関係（RawDataProvider ← CachedRawDataProvider）が data 内で完結し、acquisition は「取得して詰める」だけになる。

実装時の注意:
- **data/cache.py** は `..data.raw` の型と RawDataProvider のみ import（ib_async 等は使わない）。
- **acquisition/ib_fetcher.py** は CachedRawDataProvider を `data.cache` から import し、fetch_raw 内で `CachedRawDataProvider()` を生成して詰める。
- **ib_data.py** および **Instruments/raw_data.py** で CachedRawDataProvider を re-export している場合は、import 元を `avionics.data.cache` に変更する。
