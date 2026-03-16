# FlightController を単一窓口とする案（論点洗い出し・評価）

**実施済み: 第1段階**（1A, 2C, 3A, 4A, 5B）。FC.refresh / get_last_bundle / DataSource / BundleBuildOptions、with_ib_fetcher → IBRawFetcher、reports は FC.refresh 経由。ドキュメントは DATA_FLOW_API_TO_FC.md を更新済み。  
**実施済み: 残ステップ**。formatter は fc のみ受け取り（bundle は内部で fc.get_last_bundle()）、fetch_* の format 呼び出しから bundle 削除。IBSignalBundleFetcher 廃止（signal_bundle.py 削除、ib_data は IBRawFetcher を IBDataFetcher として re-export）。test_ib_data は FC.refresh + モック DataSource に書き換え済み。

---

## 案の要約

- **Telegram / Cockpit が使う値はすべて FlightController 経由で取得する。**
- **FC 内で factor の組み立てと signal（bundle）の組み立てを行い、FC の指示で「最新値取得」を実行する。**
- **API（データ取得窓口）は最初に FC に注入する。**

現状の「reports/scripts が with_ib_fetcher → fetch_signal_bundle → build_cockpit_stack → fc.update_all(bundle) → format(fc, bundle)」を、「FC に data source を注入 → fc.refresh() で最新取得・bundle 組み立て・因子更新 → format(fc) で FC から必要な値をすべて取得」に変える。

---

## 論点の洗い出し

### 1. 責務の所在

| 論点 | 内容 |
|------|------|
| **FC の責務の範囲** | 現状は「計器結論（ICL/SCL/LCL）の算出」と「因子への bundle 配布」。案では「最新データ取得のトリガー」「bundle 組み立てのオーケストレーション」「表示用データの提供」まで FC が持つ。責務が増えるが、呼び出し側（Telegram/Cockpit/reports）は「FC だけ触る」で済む。 |
| **「組み立て」の意味** | Factor の組み立て＝現状どおり assembly が FC に mapping を渡す（または build_cockpit_stack が build_flight_controller を呼ぶ）。Signal の組み立て＝FC が「data source から Raw 取得 → build_signal_bundle → update_all(bundle)」を一連の流れとして実行する。build_signal_bundle は process.layer2 に置いたまま、FC がそれを呼ぶ。 |

### 2. API 注入の形

| 論点 | 内容 |
|------|------|
| **何を注入するか** | (A) 接続済み IBRawFetcher：呼び出し側が `async with with_ib_fetcher as fetcher` のブロック内で FC に fetcher を渡し、FC.refresh(fetcher) または fc.attach_data_source(fetcher); await fc.refresh()。接続ライフサイクルは呼び出し側が持つ。(B) 抽象 DataSource：`async def fetch_raw(as_of, symbols, ...) -> (RawProvider, Optional[RawCapitalSnapshot])` を持つプロトコルを注入。FC は IB を直接知らず、テストではモックを注入できる。 |
| **いつ注入するか** | 「最初に」＝FC 構築後、最初に refresh する前に 1 回。レポート取得のたびに「with_ib_fetcher で接続 → FC に渡して refresh → format」なら、注入は「このブロック内で有効な data source」であり、ブロックを出れば参照は使わない（毎回注入し直す形でもよい）。 |

### 3. 接続ライフサイクル

| 論点 | 内容 |
|------|------|
| **誰が接続するか** | 案でも「誰が接続するか」はエントリ（Script）。Script が `with_ib_fetcher` で接続し、得た fetcher を FC に渡して refresh。FC は「渡された data source で fetch する」だけ。接続・切断は Script が with で管理。 |
| **長生き FC と短命接続** | Telegram ボットはコマンドごとにレポート取得するので「毎回接続 → 取得 → 切断」が自然。FC インスタンスは build_cockpit_stack で 1 回作り、その都度 data source を渡して refresh する形でよい。 |

### 4. 「すべての値」の提供方法

| 論点 | 内容 |
|------|------|
| **現状 formatter が使うもの** | fc（get_flight_controller_signal, mapping）、bundle（復帰 x/N、raw_metrics、breakdown 用の中身）、symbols, now_utc, capital_snapshot（daily 用）。 |
| **FC 経由で揃えるには** | (A) FC が「最後に refresh した bundle」を保持し、get_last_bundle() で返す。formatter は fc と fc.get_last_bundle() を参照。(B) FC が「表示用スナップショット」を返す API を 1 本用意する（例: get_cockpit_display_data() が signal + bundle の必要な部分 + mapping をまとめたオブジェクト）。formatter は fc だけ受け取り、fc.get_cockpit_display_data() で中身を取得。(C) get_flight_controller_signal() は現状 bundle を引数に取り「復帰 x/N」を bundle から算出しているが、FC が最後の bundle を保持していれば get_flight_controller_signal() は引数なしで内部の bundle を使う。 |

### 5. 設定（高度・閾値・as_of）の所在

| 論点 | 内容 |
|------|------|
| **build_signal_bundle のパラメータ** | as_of, symbols, v_recovery_params, altitude 等。これらを FC がどこから取るか。(A) FC 構築時に「設定オブジェクト」を注入する。(B) refresh(as_of=..., symbols=...) の引数で呼び出し側が渡す。(C) FC が factors.toml 等を自ら読む。テスタビリティと「設定は一箇所」のバランスで (A) または (B) が扱いやすい。 |

### 6. レイヤー・依存関係

| 論点 | 内容 |
|------|------|
| **FC が Layer 1 を「知る」か** | FC は「DataSource プロトコル」にだけ依存し、実装が IB かモックかは知らない。すると Layer 1 の「実装」は FC に注入されるだけなので、FC の責務は「データ取得のトリガーと、その結果の bundle 組み立て・因子更新」に留められる。 |
| **process.layer2 への依存** | FC が build_signal_bundle を呼ぶので、FC は process.layer2（と data.signals）に依存する。現状も assembly が FC を組み立てる時点で間接的に因子や data に依存しており、同程度の依存増。 |

### 7. 既存 API との関係

| 論点 | 内容 |
|------|------|
| **reports.fetch_cockpit_report(host, port, symbols)** | 外から見た API はそのままにできる。中身を「with_ib_fetcher → fc に fetcher 注入 → fc.refresh() → format_cockpit_report(fc)（bundle は fc から取得）」に変える。 |
| **run_cockpit_with_ib** | 同様に with_ib_fetcher → fc に渡して refresh → format(fc)。 |

---

## 評価

### メリット

- **単一窓口**: Telegram/Cockpit は「FC を更新し、FC から表示に必要な値をすべて取る」だけになる。bundle を別途渡す必要がなくなる（FC が最後の bundle を保持する前提）。
- **データ取得の意図が明確**: 「最新で揃えたい」は FC.refresh() 一発で表現できる。呼び出し側は「接続を開く → FC に data source を渡して refresh → 表示」の流れだけ書けばよい。
- **テスト**: DataSource を抽象にすると、FC の単体テストで「モック data source を注入して refresh → signal を検証」がしやすい。
- **設定の集約**: 高度・閾値・as_of を FC または「FC に注入する設定」に寄せれば、reports/scripts が複数の引数を抱えずに済む。

### デメリット・リスク

- **FC の肥大化**: 「計器結論」に加え「取得トリガー」「bundle 組み立てオーケストレーション」「表示用データ保持」が FC に乗る。インターフェースを「refresh() と get_*() の少数」に絞れば、実装の見通しは保てる。
- **refresh の失敗扱い**: refresh が「接続失敗」「取得失敗」で例外を投げる場合、呼び出し側で捕捉する必要がある。現状の fetch_cockpit_report と同様に、reports 層で try/except してユーザー向けメッセージにすることはそのまま可能。
- **breakdown / daily の bundle 専用利用**: format_breakdown_report は bundle のみで完結している。FC 経由にするなら「fc.get_last_bundle() を渡す」か「format_breakdown_report(fc) にして中で fc.get_last_bundle() を呼ぶ」かのどちらかになる。

### 実現しやすさ

- **変更範囲**: reports の fetch_* と format_* の引数（bundle を FC から取る形に変更）、FC に refresh(data_source, ...) と last_bundle（または get_display_data）を追加、build_signal_bundle の呼び出しを FC 内に移動。IBSignalBundleFetcher は「Raw を返す data source」に置き換え可能。
- **段階的移行**: まず FC に refresh(data_source, as_of, symbols, ...) と get_last_bundle() を追加し、reports 側で「fetch_raw → build_signal_bundle を FC.refresh 内で実行」「format には fc と fc.get_last_bundle() を渡す」に変える。その後、formatter を「fc のみ受け取り、bundle は fc から取る」に統一できる。

---

## 結論的な整理

| 観点 | 評価 |
|------|------|
| **方向性** | Telegram/Cockpit の値を FC 経由にし、FC の指示で最新取得する案は、**単一窓口と意図の明確さ**の点で有効。 |
| **API 注入** | **DataSource 抽象（fetch_raw を提供）を FC に注入**し、実装は IB でもモックでもよい形にすると、責務の分離とテストのしやすさが保てる。接続ライフサイクルは従来どおり Script の with_ib_fetcher が持つ。 |
| **「すべての値」** | FC が **最後に refresh した bundle を保持**し、get_flight_controller_signal() は引数なしでその bundle を参照、formatter は fc と fc.get_last_bundle()（または get_cockpit_display_data() のような 1 本 API）で揃える。 |
| **推奨** | 採用を検討してよい。まずは「FC.refresh(data_source, ...) と last_bundle の保持」「reports は FC と fc.get_last_bundle() で format」から入れ、IBSignalBundleFetcher 廃止や formatter の fc のみ受け取りへの統一はその次のステップにすると、変更を分割しやすい。 |

この案は、先の「SignalBundle の役割・高度」の整理（Raw 取得と build_signal_bundle を呼び出し側で明示する案）とも両立する。FC が「呼び出し側」の役を担い、内部で fetch_raw → build_signal_bundle → update_all を一括実行する形にできる。
