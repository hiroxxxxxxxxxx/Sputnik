# SignalBundle の役割と高度の扱い（改善案）

## 現状の整理

### SignalBundle の役割（現状）

- **型**（`data/signals.SignalBundle`）: Layer 2 の出力を一括保持するコンテナ。price_signals, volatility_signals, liquidity_*, capital_signals。FC が `update_all(signal_bundle=bundle)` で受け取り、各因子の `update_from_signal_bundle(symbol, bundle)` に渡す。因子は bundle から自分のシグナルを取り出して**レベル判定**する。
- **IBSignalBundleFetcher**（`ib/signal_bundle.py`）: 「Raw 取得 ＋ build_signal_bundle」を一括で行い、SignalBundle を返す。`with_ib_fetcher` が yield する型。reports / run_cockpit_with_ib は `fetcher.fetch_signal_bundle(...)` のみ呼ぶ。

つまり「signal を factor に渡してレベル判定」は**すでに**やっている（bundle 経由）。違和感のポイントは次の二つと考えられる。

1. **なぜ「bundle を返す fetcher」が必要か** — Raw を取って呼び出し側で build_signal_bundle すればよいのでは？
2. **高度がシグナル（や fetch_signal_bundle API）にある違和感** — 高度は「データ」ではなく「運用レジーム／設定」では？

---

## 改善案

### 1. SignalBundle の役割を「型＋組み立て」に限定し、fetcher は Raw のみ返す

**現状**: エントリ → `with_ib_fetcher` → `fetcher.fetch_signal_bundle(...)` → FC.update_all(bundle)。

**案**: エントリ → `with_ib_fetcher`（yield するのは **IBRawFetcher** のみ）→ 呼び出し側で `raw = await fetcher.fetch_raw(...)` → `bundle = build_signal_bundle(raw, as_of, ...)`（ここで高度・閾値は設定から取得）→ `fc.update_all(bundle)`。

- **IBSignalBundleFetcher を廃止**。`with_ib_fetcher` が yield するのは IBRawFetcher だけにする。
- reports / run_cockpit_with_ib では「fetch_raw → build_signal_bundle → update_all」の 3 段を明示的に書く。
- **メリット**: 「Raw → Signal(Bundle) → Factor に渡してレベル判定」の流れがコード上はっきりする。SignalBundle は「Layer 2 の出力型」と「build_signal_bundle で組み立てる」だけの役割になる。
- **デメリット**: 呼び出し箇所が 1 行から 3 行程度に増える。共通化したい場合は「build_signal_bundle までやるヘルパー」を reports 側に一つ置く形にできる。

---

### 2. 高度を「シグナルの属性」から「設定」に寄せる

**現状**: `VolatilitySignal` / `LiquiditySignals` に `altitude: AltitudeRegime` がフィールドとしてある。Layer 2 で「どの閾値セットで計算したか」をシグナルに載せ、因子が `signal.altitude` で同じ閾値セットを参照する。

**違和感**: 高度は「このシグナルがどのレジームで計算されたか」のメタ情報であり、「運用側の設定（今は high_mid で運用している）」と考えると、シグナル型のフィールドより「Cockpit / FC の設定」にある方が自然。

**案 A — レジームを一箇所で持つ**

- Cockpit ビルド時または factors.toml で「現在のレジーム」（例: `high_mid`）を一つ決める。
- `build_signal_bundle` には `regime: AltitudeRegime` を渡す（v/c/r で分けず 1 つ。必要なら「v_regime, c_regime, r_regime」は設定から読む）。
- シグナル型から `altitude` を削除。因子は「自分の設定（mapping や config から取得した regime）」で閾値を参照する。Layer 2 は「その regime で計算した結果」だけを返す（値のみ。どの regime で計算したかは呼び出し側と因子の設定が一致している前提）。

**案 B — 現状に近いが API を整理**

- 高度は「build 時のパラメータ」であり、シグナルに「どの高度で計算したか」を残すのは「因子が同じ閾値セットを参照するため」のメタデータとして許容する。
- 違和感を減らすため、**fetch_signal_bundle / build_signal_bundle の引数から v_altitude, c_altitude, r_altitude を外し**、**設定オブジェクト（factors config や Cockpit の regime）から読む**ようにする。例: `build_signal_bundle(..., regime_source=config)` や、factors.toml に `[regime] altitude = "high_mid"` を置き、build 時と因子の両方がそれを参照する。

**推奨**: まずは **案 B**（高度は build と因子の両方で「設定から読む」に統一し、シグナルに altitude を持たせるかは後続のリファクタで検討）。案 A は「シグナルから altitude 削除」により因子と Layer 2 の契約が変わるため、変更量が大きい。

---

## まとめ

| 論点 | 改善の方向 |
|------|------------|
| **SignalBundle の役割** | 型と `build_signal_bundle` はそのまま。「bundle を返す fetcher」をやめ、**IBRawFetcher のみ**にし、呼び出し側で fetch_raw → build_signal_bundle → update_all と明示する。 |
| **高度の違和感** | 高度を「シグナルの属性」ではなく**設定（regime）**として扱う。build_signal_bundle / 因子が設定（factors.toml や Cockpit の regime）から参照する形にし、API の v_altitude/c_altitude/r_altitude を減らす。必要ならシグナルから altitude を外すのは次のステップ。 |

この流れで進めると、「signal を factor に渡してレベル判定」がより明確になり、高度は「データ」ではなく「運用設定」として整理できる。
