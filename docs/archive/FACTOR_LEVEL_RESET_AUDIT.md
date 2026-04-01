# 因子 level リセット経路と他因子ポリシー監査

運用上「前回の因子レベル」とずれる原因をコード根拠で整理する調査レポート。実装方針（DB 非依存の履歴再算出、V2→V0 禁止など）は別紙の計画と `.cursor` 側の計画と整合させる。

---

## 1. 結論サマリ

**プロセス再起動以外で、多くの因子が毎回 `BaseFactor` 初期化により `level = levels[0]`（多くは 0）から始まる主因は、Telegram レポート経路でコマンドごとに新しい `FlightController`（＝新因子インスタンス）を `build_cockpit_stack` していることである。**

根拠:

- `_refreshed_fc`: `build_cockpit_stack` のあと 1 回だけ `fc.refresh`。

```325:333:scripts/telegram_cockpit_bot.py
    async with with_ib_fetcher(host, port, client_id=client_id, timeout=timeout) as fetcher:
        fc, _ = build_cockpit_stack(
            symbols, altitude=altitude, s_baseline_by_symbol=s_baseline_by_symbol
        )
        as_of = as_of_for_bundle()
        await fc.refresh(fetcher, as_of, symbols, altitude=altitude)
```

- 因子は常に `levels[0]` で初期化。

```45:47:src/avionics/factors/base_factor.py
        self.name: str = name
        self.levels: list[LevelType] = sorted(levels)
        self.level: LevelType = self.levels[0]
```

- [src/cockpit/stack.py](src/cockpit/stack.py) の `build_cockpit_stack` → `build_flight_controller` で FC を毎回新規生成する。

`scripts/run_daily_signal_persist.py` や `scripts/run_cockpit_with_ib.py` も **実行単位で新 FC** になる。履歴からレベルを再構成する処理が無い限り、**単一 `refresh` ティックだけでは「連続したヒステリシス状態」と一致しない**場合がある。

### 1.1 DB と因子レベル

[src/store/signal_daily.py](src/store/signal_daily.py) は `FlightControllerSignal` を日次 upsert する **監査・ログ用**である。因子の `previous_level` を DB から読み込んでシードする設計は採らない。**P/V/T/C/R** はバンドル内の日次系列を畳み込み再算出する。**U/S** は SPEC.md どおり **当該ティックの CapitalSignals（MM/NLV・SPAN 比）のみ**で即時判定し、**日次連続カウントによるヒステリシスは採用しない**（on/off バッファ幅のみ）。

---

## 2. `level` が 0 側に寄る／実質 0 相当になる経路（根拠付き）

| 経路 | 対象因子 | 説明 | 根拠（ソース） |
|------|-----------|------|----------------|
| 新 FC 生成 | P, V, T, C, R, U, S | 各 `apply_signal_bundle` 前に `level=levels[0]`。Telegram はコマンドごと `_refreshed_fc` → `build_cockpit_stack`。 | `base_factor.py` 初期化；`telegram_cockpit_bot.py` `_refreshed_fc` |
| プロセス再起動・新コンテナ | 同上 | インスタンス再生成と同効。 | （上と同じ初期化規則） |
| 仕様上の復帰で 0 | P, V, T, C, R | `upgrade(..., target=0)` または条件付きで `level=0`（確認日数・バッファ等）。 | `p_factor.py` `update_from_signals`；`v_factor.py` V1→V0；`t_factor.py`；`c_factor.py` / `r_factor.py` の `upgrade(0, ...)` |
| 仕様上の復帰で 0 | U, S | SPEC.md：復帰閾値未満で一段ずつ下げる（**即時・日数カウントなし**）。 | `u_factor.py`／`s_factor.py` |
| U/S の段階復帰 | U, S | 2 からは常に `c2_off/s2_off` 未満で **1**、`2→0` 直跳びはなし。0↔1↔2 は on/off で定義。 | ```49:65:src/avionics/factors/u_factor.py``` 等 |
| テスト・手動 | 任意 | `test_downgrade` 等。本番経路外。 | （テストコード） |

---

## 3. 他因子：冷スタート（Cold start）と段階スキップ

共通（**主に P/V/T/C/R**）: 新 FC では `self.level == levels[0]` から始まる。日次系列を畳み込む因子では、履歴不足や単一ティックのみだと実効レベルがずれることがある。**U/S は当該 `CapitalSignals` のみで SPEC 通り即時判定**（前段と同型の「日次履歴欠如」は別問題）。

### 3.1 P（[p_factor.py](src/avionics/factors/p_factor.py)）

| 観点 | 内容 |
|------|------|
| 冷スタート | `new_level = _classify(...)` は **当日特徴量のみ**。`self.level` は主に悪化／`upgrade` 復帰に使用（```136:154:src/avionics/factors/p_factor.py```）。境界付近では 0 起点のままだと「連続した P1/P2 履歴」と不一致になりうる。 |
| 段階スキップ | P2 は条件一致で **即 2**（```172:177:src/avionics/factors/p_factor.py```）。意図された即時悪化。復帰は `daily_history` 由来の `recovery_confirm_satisfied_days` で **ステートレス連続日数**（```105:117:src/avionics/factors/p_factor.py```）。 |

### 3.2 C（[c_factor.py](src/avionics/factors/c_factor.py)）

| 観点 | 内容 |
|------|------|
| レベル集合 | `[0, 2]` のみ（```43:43:src/avionics/factors/c_factor.py```）。V1 相当なし。 |
| 冷スタート | 当日トリガで C2 に上げ直すまで **過去の C2 を引きずらない**。 |
| 段階スキップ | **2→0** は `upgrade(0, confirm_days, recovery_confirm_satisfied_days=...)`（```172:178:src/avionics/factors/c_factor.py```）。「V2→V0 禁止」と同型の **中間段なし禁止** 問題にはならない（中間レベルが無い設計）。 |

### 3.3 R（[r_factor.py](src/avionics/factors/r_factor.py)）

| 観点 | 内容 |
|------|------|
| レベル集合 | `[0, 2]`（```45:45:src/avionics/factors/r_factor.py```）。 |
| 冷スタート | C と同型。 |
| 段階スキップ | **2→0** は `upgrade(0, ...)`（```134:140:src/avionics/factors/r_factor.py```）。 |

### 3.4 T（[t_factor.py](src/avionics/factors/t_factor.py)）

| 観点 | 内容 |
|------|------|
| レベル集合 | `[0, 2]`（```42:45:src/avionics/factors/t_factor.py```）。 |
| 冷スタート | `trend=="down"` で即 2、復帰は `daily_history` の up/flat 連続日数（```104:117:src/avionics/factors/t_factor.py```）。 |
| 段階スキップ | 悪化は即 T2。復帰は確認付き T0。 |

### 3.5 U（[u_factor.py](src/avionics/factors/u_factor.py)）

| 観点 | 内容 |
|------|------|
| 仕様 | SPEC.md：リアルタイム・**日数ヒステリシスなし**（発動/復帰とも即時、on/off のみ）。 |
| 冷スタート | 新 FC では `level` は 0 初期化のため、マルコフの前状態が「実効レベル」とずれる可能性は P/V 型の**履歴再算出**問題とは別（資本はスナップショットのみ）。 |
| 段階スキップ | **2→0 直跳びなし**。`current==2` では次は 1 か 2 のみ。 |

### 3.6 S（[s_factor.py](src/avionics/factors/s_factor.py)）

| 観点 | 内容 |
|------|------|
| 仕様 | SPEC.md：U と同様に**日数ヒステリシスなし**（即時＋切上げ/切捨て＋on/off）。 |
| 冷スタート | U と同型（前レベルはインスタンス由来）。資本以外の履歴は参照しない。 |
| 段階スキップ | **2→0 直跳びなし**（```55:56:src/avionics/factors/s_factor.py```）。 |

### 3.7 V（[v_factor.py](src/avionics/factors/v_factor.py)）

| 観点 | 内容 |
|------|------|
| 実装 | `VolatilitySignal.index_history` を日付順に畳み込み、当該 as_of の指数・ノックインで決定。 |
| ポリシー | **V2→V0 直落ちなし**（2→1→0 と V1 ノックインに整合）。 |

---

## 4. FlightController に載る因子一覧（参照）

[src/avionics/assembly.py](src/avionics/assembly.py): 銘柄ごとに P, V, T；NQ に C；GC に R；共通で U, S（```69:85:src/avionics/assembly.py```）。

---

## 5. 是正方針の要点（実装は別タスク・要許可）

1. **DB から `previous_level` を読まない**（監査は `signal_daily` のみ）。
2. **履歴の畳み込み（P/V/T/C/R）**: バンドル上の日次系列などから再算出する。**U/S は SPEC 上スナップショット即時判定のため対象外**（無断で日次畳み込みを足さない）。
3. **V**: 履歴系列から as_of 時点のレベルを求める方式に寄せ、**V2→V0 の直接候補と危険な `upgrade(..., recovery_confirm_satisfied_days=1)` 分岐**を排除（2→1→0 と V1 ノックインに整合）。
4. **欠損・履歴窓不足**: 計算に必要な履歴が無い場合は *無断デフォルト level で埋めない*（プロジェクト規約）。明示エラーか、仕様で最小窓を定義。

---

## 6. 受け入れ条件（本ドキュメントとして）

- 再起動以外の **level=0 相当**の原因として **FC 再生成** と **V の V2→V0 近傍分岐** を根拠付きで記載した。
- P/C/R/T について **冷スタート** と、**V** の **V2→V0 型**、**U/S** の **SPEC（スナップショット即時・日数なし）** を区別して記載した。
- DB を因子シードに使わない方針と、**P/V/T/C/R の履歴再算出**＋欠損時の明示扱いを §5 に含めた。
