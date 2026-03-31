# Phase 2 テーブル仕様（案B ベース・確定方針）

定義書（SPEC 2-2 操縦制御、3-2/3-3/3-4 レイヤー）に従ったテーブル定義。  
**案B**（目標枚数は別テーブル）を採用し、**銘柄ごと**の目標枚数・effective_level を扱う。

---

## 1. state テーブル（飛行状態・1行）

**役割**: 現在の飛行状態スナップショット。再起動後に復元する。

- **effective_level**: 銘柄ごとに異なるため、`effective_nq` / `effective_gc` で保持する。
- **altitude**: 3値（高/中/低）。6ヶ月ルール・閾値切り替え用。
- **高度変更日時**: state には持たない。`altitude_changes` の最新行 `changed_at` で取得する。
- 目標枚数は **target_futures** テーブルで管理（案B）。

```sql
CREATE TABLE state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    effective_nq INTEGER NOT NULL CHECK (effective_nq IN (0, 1, 2)),
    effective_gc INTEGER NOT NULL CHECK (effective_gc IN (0, 1, 2)),
    altitude TEXT NOT NULL CHECK (altitude IN ('high', 'mid', 'low')),
    updated_at TEXT
);
```

---

## 2. target_futures（目標先物枚数・銘柄×Part×契約）

**役割**: 運用開始時に決める「銘柄側×Part×契約シンボルごとの目標枚数」。Mini（NQ/GC）と Micro（MNQ/MGC）を区別する。

### symbol と contract の使い分け

| 項目 | 意味 | とりうる値 | 用途 |
|------|------|------------|------|
| **symbol** | **銘柄側（エンジン）**。どちらの「エンジン」に属するか。計器・Blueprint・運用上のグルーピング。 | `NQ` \| `GC` | どの Engine（NQ 用 / GC 用）の目標か。FlightController の get_flight_controller_signal(symbol).throttle_level や Engine の symbol_type と対応。 |
| **contract** | **取引所の契約銘柄**。実際に発注するときの銘柄。Mini と Micro を区別する。 | `NQ` \| `MNQ` \| `GC` \| `MGC` | 注文・ポジション照会で使うシンボル。contract_symbol(symbol_type, layer_type) の結果と対応。 |

- **symbol** が「NQ」の行は、すべて NASDAQ 側の目標。そのうち **contract** が `NQ` なら Mini 1枚分、`MNQ` なら Micro 1枚分を表す。
- **symbol** が「GC」の行は、すべて Gold 側の目標。**contract** は `GC`（Mini）または `MGC`（Micro）。
- 通常は NQ 側で contract が NQ/MNQ、GC 側で contract が GC/MGC のみ（他側の契約は持たない）。PK で (symbol, part_name, contract) としているので、同じ part で Mini と Micro を両方持つ場合も行を分けて表現できる。

- **part_name**: 'Main' | 'Attitude' | 'Booster'。
- **contracts**: 目標枚数（整数）。
- 例: NASDAQ の Main = NQ 1枚 + MNQ 2枚 → (NQ, Main, NQ, 1), (NQ, Main, MNQ, 2)。GC 側は (GC, Main, GC, 1), (GC, Attitude, MGC, 2) など。

```sql
CREATE TABLE target_futures (
    symbol TEXT NOT NULL CHECK (symbol IN ('NQ', 'GC')),
    part_name TEXT NOT NULL CHECK (part_name IN ('Main', 'Attitude', 'Booster')),
    contract TEXT NOT NULL CHECK (contract IN ('NQ', 'MNQ', 'GC', 'MGC')),
    contracts INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, part_name, contract)
);
```

---

## 3. altitude_changes（高度変更履歴）

変更の都度 INSERT。6ヶ月ルールの監査用。

```sql
CREATE TABLE altitude_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at TEXT NOT NULL,
    from_altitude TEXT NOT NULL CHECK (from_altitude IN ('high', 'mid', 'low')),
    to_altitude TEXT NOT NULL CHECK (to_altitude IN ('high', 'mid', 'low'))
);
```

---

## 4. mode（制御系・1行）

**用語**: 計画の「ap_mode」は **auto_pilot_mode** とする（定義書 2-2 操縦制御に合わせる）。

- **auto_pilot_mode**: 定義書どおり **3値** — `Manual`（マニュアル） / `Semi`（半自動） / `Full`（全自動）。
- **execution_lock**: 発注・執行を止める安全スイッチ（0=OFF, 1=ON）。

```sql
CREATE TABLE mode (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    auto_pilot_mode TEXT NOT NULL CHECK (auto_pilot_mode IN ('Manual', 'Semi', 'Full')),
    execution_lock INTEGER NOT NULL CHECK (execution_lock IN (0, 1)),
    updated_at TEXT
);
```

---

## 5. signal_daily（日次・Layer2/3/4 のみ・銘柄別 effective）

**方針**: Layer1（Raw Data）は保存しない。**Layer2（Signals）・Layer3（Factors）・Layer4（Control Levels）** を保存する。

- 定義書: Layer2=Signals, Layer3=Factors, Layer4=Control Levels（ICL, SCL, LCL → Effective）。
- 保存するのは **Layer4 の出力**: ICL（銘柄別）, SCL, LCL, **effective_level（銘柄別）**。
- 1 日あたり **1 行** にまとめ、銘柄別はカラムで分ける（as_of が同じ日の NQ/GC を 1 行で持つ）。

```sql
CREATE TABLE signal_daily (
    as_of TEXT NOT NULL PRIMARY KEY,
    icl_nq INTEGER NOT NULL CHECK (icl_nq IN (0, 1, 2)),
    icl_gc INTEGER NOT NULL CHECK (icl_gc IN (0, 1, 2)),
    scl INTEGER NOT NULL CHECK (scl IN (0, 1, 2)),
    lcl INTEGER NOT NULL CHECK (lcl IN (0, 1, 2)),
    effective_nq INTEGER NOT NULL CHECK (effective_nq IN (0, 1, 2)),
    effective_gc INTEGER NOT NULL CHECK (effective_gc IN (0, 1, 2))
);
```

- `as_of`: 営業日（`YYYY-MM-DD`）。
- Layer2/3 の中間（個別因子 P,V,C,R,T,U,S のレベル）は保存しない。必要なら後フェーズでカラム追加可能。

---

## 6. コード方針: get_throttle_mode 廃止・Cockpit で get_flight_controller_signal

- **effective_level を DB で持つ** ため、**FlightController の get_throttle_mode** は廃止済み。
- **Cockpit** から **get_flight_controller_signal(symbol).throttle_level** で level (0/1/2) を取得し、スロットルモード（Boost/Cruise/Emergency）に変換して Engine へ **apply_mode** する。get_effective_level は廃止済み。
- 変換は Cockpit 内で行う（`level 0 → Boost`, `1 → Cruise`, `2 → Emergency`）。  
  **cockpit/mode.py** に定数（BOOST, CRUISE, EMERGENCY, ModeType）を置き、Engine / Blueprint / Protocol が参照する。FlightController は mode を参照しない。

---

## 7. まとめ

| テーブル | 内容 |
|----------|------|
| **state** | 1行。effective_nq, effective_gc, altitude。高度変更日時は altitude_changes から取得。 |
| **target_futures** | 銘柄×Part×契約の目標枚数。(symbol, part_name, contract) PK。contracts で枚数を保持。Mini/Micro 対応。 |
| **altitude_changes** | 高度変更履歴。INSERT のみ。 |
| **mode** | 1行。auto_pilot_mode (Manual/Semi/Full), execution_lock。 |
| **signal_daily** | 日次 1 行。Layer4 のみ: icl_nq, icl_gc, scl, lcl, effective_nq, effective_gc。 |

この仕様で `002_*.sql` のマイグレーションと、Cockpit / FlightController の接続を進める。
