# 階層化憲章（Layer 1〜4）適合性確認

「OSの核となるロジックが汚染されない不変の構造」を維持するための憲章に基づく適合性の再確認結果。

---

## Layer 1: Raw Data（生データ層）

| ルール／制限 | 実装 | 適合 |
|--------------|------|------|
| 計算・加工を一切行わない「純粋な事実」の保持 | `avionics/raw_data.py`: PriceBar, RawCapitalSnapshot, RawDataProvider(Protocol) のみ。SMA・トレンド・変動率などの計算は一切なし。 | ✅ |
| API取得直後の OHLCV, IV, 金利, 証拠金額 | RawDataProvider の get_price_series, get_volatility_index, get_capital_snapshot 等で型定義。実装は外部委譲。 | ✅ |
| **この層のデータが直接 OSCore（Layer 4）に触れることは禁止** | OSCore は `core/oscore.py` のみで、`raw_data` / `RawDataProvider` / `PriceBar` を import していない。Avionics 経由で get_effective_level のみ参照。 | ✅ |
| 異常値のフィルタリング（スパイク除去）はこの層の出口で行う | RawDataProvider の戻り値に対するスパイク除去は、現状コード内に明示的な実装なし。Provider 実装側または Layer 1 出口で行う想定。 | ⚠️ 要検討 |

---

## Layer 2: Signals（共通シグナル層）

| ルール／制限 | 実装 | 適合 |
|--------------|------|------|
| 複数因子が参照する「共通言語」への変換 | `avionics/signals.py`: PriceSignals（trend, daily_change, cum5/cum2, downside_gap）, VolatilitySignal, LiquiditySignals, CapitalSignals。compute_* は RawDataProvider のみを入力に算出。 | ✅ |
| トレンド・日次変動率・Downside Gap・x日累積・1h足陽線判定等 | compute_price_signals（SMA20, トレンド, 変動率, gap）, compute_capital_signals, compute_liquidity_signals_* で実装。 | ✅ |
| 計算の唯一性（P因子と同期制御層でトレンド認識の不一致が起こらない） | トレンドは Layer 2 で1回だけ計算し、PriceSignals.trend として P と T（→同期制御層）に同一値を配布。 | ✅ |
| **レベル判定（0/1/2）は行わない。数値や状態として保持** | Signal 型は trend(up/down/flat), float, bool 等のみ。0/1/2 のレベルは一切持たない。 | ✅ |

---

## Layer 3: Factors（因子判定層）

| ルール／制限 | 実装 | 適合 |
|--------------|------|------|
| P/V/L/T/U/S の各因子。Layer 2 からシグナルを購読し閾値テーブルで 0/1/2 を出力 | 各 `*_factor.py` は update_from_signals / update_from_ratio / apply_trend 等で「シグナル（数値・状態）」のみを受け取り、.level として 0/1/2 を出力。 | ✅ |
| **「自分がどの銘柄の個別制御層に使われるか」「同期制御層との兼ね合い」を知ってはならない** | 因子は avionics / oscore を import していない。割り当ては Avionics の symbol_factors / global_* の登録側の責務。 | ✅ |
| 割り当てられたシグナルのみを見て淡々とレベルを算出する「単機能の計器」 | 各因子は渡されたシグナルと自身の thresholds のみで _classify / レベル更新。銘柄名は表示用ラベルのみで、制御ロジックには使っていない。 | ✅ |
| Raw Data を直接参照しない | 因子は `raw_data` を import していない。入力はすべて update_from_* の引数（Layer 2 由来）。 | ✅ |

---

## Layer 4: Control Levels（制御レベル層）

| ルール／制限 | 実装 | 適合 |
|--------------|------|------|
| 個別・同期・制限制御層の実装。実行レベルの算出 | `avionics/avionics.py`: get_individual_control_level(symbol)=max(P,V,L), get_synchronous_control_level()=T相関, get_limit_control_level()=max(U,S), get_effective_level(symbol)=三層の max。 | ✅ |
| 個別: max(P,V,L) 銘柄ごと / 同期: T相関 / 制限: max(U,S) | 上記の通り実装。定義書 4-2 と一致。 | ✅ |
| **実行レベル以外、OSCore は下位レイヤーを参照してはならない** | OSCore は `get_effective_level(symbol)` のみでモード決定。レガシー・サブスクリプションとも同一API。表示が必要なら呼び出し元が Avionics の get_individual_control_level / get_limit_control_level 等を参照。 | ✅ |

---

## 依存方向の確認

| 確認項目 | 結果 |
|----------|------|
| Layer 1 を import しているのは | `avionics/signals.py`（Layer 2）, `avionics/__init__.py`（型の再公開）, テストのみ。因子・OSCore は import しない。 | ✅ |
| Layer 2 を import しているのは | Avionics（SignalBundle, 配布）, 各因子（TYPE_CHECKING で PriceSignals 等の型のみ）。因子は「値」を Avionics 経由で受け取るだけ。 | ✅ |
| OSCore が import しているのは | Avionics, state_machine, engines。raw_data / signals は import していない。 | ✅ |

---

## 結論

- **Layer 1〜4 の責務分離と制限は、現行実装で満たしている。**
- **未実装・要検討**: Layer 1 出口でのスパイク除去（RawDataProvider 実装または Layer 1→2 境界で行う方針を明示するとよい）。
- OSCore は M/C を保持しない。制御に使うのは get_effective_level のみ。表示が必要な場合は呼び出し元が Avionics（get_individual_control_level / get_limit_control_level 等）を参照する。

将来の新銘柄・新因子の追加は、憲章どおり次の2点に限定できる。

1. **Layer 2** に新しい Signal を追加する。  
2. **Layer 3** の該当因子の判定ロジックを、その Signal を参照するように書き換える。  

**Layer 4（個別・同期・制限制御層）や OSCore のコードは触らない。**

---

*階層化憲章に基づく適合性確認。*
