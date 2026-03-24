# ib/fetcher と ib_data の責務整理

**実施済み: 案B**（IBSignalBundleFetcher を avionics.ib に集約、ib_data は re-export のみ）

---

## 現状の問題（案B 実施前）

| ファイル | 内容 | 問題 |
|----------|------|------|
| **avionics/ib/fetcher.py** | `IBDataFetcher`（fetch_raw のみ）＋ `fetch_raw(ib, ...)` | クラス名が「Data」で Raw 専用であることが伝わりにくい。 |
| **avionics/ib_data.py** | `IBDataFetcher` の**サブクラス**（同名）に `fetch_signal_bundle` を追加 | 同じ名前で「Raw 用」と「SignalBundle 用」が共存し、どちらが窓口か分かりにくい。モジュール名「ib_data」も「IB のデータ全般」で曖昧。 |

- **session** が yield するのは `avionics.ib_data.IBDataFetcher`（SignalBundle を返す方）であり、reports/scripts は `fetch_signal_bundle` のみ利用している。
- 一方で `avionics.ib` は `IBDataFetcher`（Raw 専用）を re-export しており、「IBDataFetcher」が二種類ある状態になっている。

---

## 責務の整理（望ましい分担）

| 責務 | 担当 | 出力 |
|------|------|------|
| **Layer 1: IB から Raw を取得** | `avionics.ib.fetcher` | `CachedRawDataProvider` ＋ `Optional[RawCapitalSnapshot]` |
| **Cockpit 用: Raw 取得 ＋ Layer 2 で SignalBundle を組み立て** | 一箇所に集約 | `SignalBundle` ＋ `Optional[RawCapitalSnapshot]` |

「誰が fetch_signal_bundle を提供するか」をはっきりさせ、名前で役割が分かるようにする。

---

## 改善案

### 案 A: 名前とドキュメントで責務を明確化（変更最小）

- **ib/fetcher.py**
  - クラス名を **`IBRawFetcher`** に変更（Raw 専用であることを名前で示す）。
  - docstring: 「Layer 1 のみ。IB から Raw を取得し CachedRawDataProvider に詰める。SignalBundle は作らない。」
- **ib_data.py**
  - クラス名を **`IBSignalBundleFetcher`** に変更（Cockpit が使う「SignalBundle を返す fetcher」であることを示す）。
  - 継承元を `IBRawFetcher` に変更。
  - docstring: 「Cockpit 用オーケストレーション。IBRawFetcher.fetch_raw と build_signal_bundle を組み合わせ、SignalBundle を返す。with_ib_fetcher が yield するのはこのクラス。」
- **ib/session.py**
  - `avionics.ib_data.IBSignalBundleFetcher` を import して yield。
- **avionics.ib.__init__**
  - `IBDataFetcher` の代わりに `IBRawFetcher` を re-export（後方互換が必要なら `IBDataFetcher = IBRawFetcher` の alias を残す）。
- **acquisition/__init__.py**
  - Raw 用として `IBRawFetcher` / `fetch_raw` を re-export。

**メリット**: 変更箇所が少ない。**デメリット**: `ib_data.py` が avionics 直下に残り、「IB 由来の窓口」が ib と ib_data に分かれたまま。

---

### 案 B: SignalBundle 用オーケストレーションを avionics.ib に集約（推奨）

「IB に依存する窓口」をすべて `avionics.ib` 配下にまとめる。

1. **ib/fetcher.py**
   - クラス名を **`IBRawFetcher`** に変更（案 A と同様）。
   - 役割: Layer 1 のみ。`fetch_raw` で Raw を返す。

2. **ib/signal_bundle.py**（新規）
   - **`IBSignalBundleFetcher`** を定義。
   - `IBRawFetcher` を継承し、`fetch_signal_bundle` を実装（中身は現 ib_data と同様: `fetch_raw` → `build_signal_bundle`）。
   - `avionics.process.layer2.bundle_builder.build_signal_bundle` を import（ib パッケージは process に依存するが、process は ib に依存しないので循環しない）。

3. **ib/session.py**
   - `avionics.ib_data` ではなく **`avionics.ib.signal_bundle.IBSignalBundleFetcher`** を import して yield。

4. **ib/__init__.py**
   - `IBRawFetcher`, `IBSignalBundleFetcher`, `fetch_raw` を re-export。
   - 必要なら `IBDataFetcher` を `IBSignalBundleFetcher` の alias として残し、既存の「IBDataFetcher という名前」に依存する箇所を減らしつつ移行。

5. **ib_data.py**
   - **削除**するか、中身を「`from avionics.ib import IBSignalBundleFetcher as IBDataFetcher` の re-export のみ」にし、後方互換用の薄いラッパーにする。

**メリット**:  
- 「IB に触れるもの」がすべて `avionics.ib` 以下にまとまる。  
- Raw 用と SignalBundle 用でクラス名が分かれ、責務が明確。  
- テストや session の利用先は `avionics.ib` だけ見ればよい。

**デメリット**:  
- `avionics.ib` が `avionics.process.layer2` に依存する（現状も ib_data 経由で同じ依存あり）。

---

## 推奨

**案 B** を推奨する。

- 責務: **ib/fetcher.py = Raw 取得のみ**、**ib/signal_bundle.py = Cockpit 用（Raw + Layer 2 → SignalBundle）** と名前と配置で一致する。
- ib_async 依存はすでに `avionics.ib` に集約されているため、その中で「Raw 用」と「SignalBundle 用」を分離すると一貫する。
- `ib_data.py` は廃止するか re-export のみにし、新規コードは `avionics.ib.IBSignalBundleFetcher` / `avionics.ib.IBRawFetcher` を参照するようにする。

---

## 移行時の参照先

| 現在 | 案 B 後 |
|------|---------|
| `avionics.ib_data.IBDataFetcher` | `avionics.ib.IBSignalBundleFetcher`（session が yield する型） |
| `avionics.ib.fetcher.IBDataFetcher` | `avionics.ib.IBRawFetcher` |
| `avionics.acquisition.IBDataFetcher` | `avionics.ib.IBRawFetcher` または `avionics.ib.IBSignalBundleFetcher`（用途に応じて re-export） |

tests の `IBDataFetcher(mock_ib)` で `fetch_signal_bundle` を検証している場合は `IBSignalBundleFetcher` に差し替える。
