# 注文処理とプロトコル階層（アーキテクチャ）

定義書「4-1 操縦制御」「6-2 Emergencyプロトコル」および執行原則を、コードの責務分離として整理した文書。

---

## 1. 注文処理の「どこで」：2段階の分離

| 段階 | 役割 | 担当 | 内容 |
|------|------|------|------|
| **物理的な発注** | 執行 (Execution) | Engine / Part | limit_order() や placeOrder()（ib_async）を叩く。各 Part が get_target_delta() で計算し、OrderManager（ib_async ラッパー）で発注する。 |
| **発注のシーケンス制御** | 作戦 (Scenario) | FlightController / Protocol | 「どの順番で、どのエンジンを動かすか」を決定。Emergency など銘柄を跨ぐ順序制御は個別 Engine には判断できないため、ここで行う。 |

- **注文を「書く」**: Engine 配下の Part（PB/CC/BPS）。
- **注文を「並べる」**: FlightController 配下の Protocol クラス。

---

## 2. 注文処理の階層構造（司令から発注まで）

| 階層 | 役割 | 処理内容 |
|------|------|----------|
| **FlightController** | 司令 (Command) | 「Emergency モードへの遷移」を決定し、対応するプロトコルを起動する。 |
| **Protocol**（EmergencyProtocol 等） | 作戦 (Scenario) | 「ステップ1: 先物削減」「ステップ2: …」と Engine に順番に命令を出す。 |
| **Engine / Part** | 執行 (Execution) | 命令を受け、ib_async で市場に注文を送る。 |

---

## 3. プロトコル階層の再定義

Emergency だけを特別扱いせず、モード遷移に伴う一連の行動を「プロトコル」として共通の階層に置く。

FlightController の直下に、以下の 4 プロトコルを配置する。

| プロトコル名 | 役割・ニュアンス | 執行の性格 |
|--------------|------------------|------------|
| **BoosterIgnition** | 余剰証拠金を確認し、BPS 等の「加速装置」に点火する。 | 能動的・攻勢 |
| **BoosterCutoff** | 加速を停止し、リスクを切り離して通常巡航に戻る。 | 制御・減速 |
| **Emergency** | 即時パニック停止。最優先の防衛シーケンス。定義書 6-2。 | 即時・強制 |
| **Restoration** | 異常事態から通常（Level 0/1）へ復旧する手順。 | 慎重・再構築 |

- 定義書の**執行原則**（ギアダウン時: 先物削減→ブースターBPS削減→メインエンジンPB転換の順）は、単一 Engine では完結せず、**ポートフォリオ全体の順序制御**である。そのため Engine 内部ではなく Protocol 階層で記述する。
- Engine は「言われた時に、言われたパーツを動かす」コンポーネントに徹し、FlightController は「どのプロトコルを選ぶか」に専念する。

---

## 4. BaseProtocol：共通の枠組みと安全装置

基底クラスが持つのは**「個別の執行ロジック」ではなく「執行の安全装置と共通の作法」**。

### 4.1 基底クラスの主な役割

1. **共通の事前・事後チェック (Guard & Clean-up)**
   - **Pre-run Simulation**: 実行直前に「今の証拠金でこの注文を出しても大丈夫か？」を各 Engine に計算させる。
   - **Post-run Validation**: 執行後、目標デルタや証拠金状態に正しく着地したかを検証する。

2. **タイムアウトとリトライの制御 (Execution Control)**
   - **Step Timeout**: 1 つの注文が一定時間内に約定しなかった場合の共通ハンドリング。
   - **Atomic Transaction**: 一連のステップが途中で失敗した場合のフラグ管理。

3. **共通のロギング・通知**
   - 「ステップ 1/9 完了: NQ先物 5枚決済済」などを Telegram／内部ログへ標準フォーマットで出力。

### 4.2 抽象メソッド（子クラスが実装）

- `async def run(self, engines)`: プロトコルのメインシーケンス。
- `def get_priority(self)`: 複数プロトコルが衝突しそうな場合の優先度。

### 4.3 実行フロー

```
execute(engines):
  1. 事前シミュレーション (validate_margin 等)
  2. run(engines)  # 子クラスのシーケンス
  3. 事後確認 (report_completion)
```

---

## 5. Docker 化と ib_async 接続（Phase 4 留意点）

- **接続の共通化**: IB クライアント（ib_async.IB()）は OS 全体のトップレベルで 1 つ保持し、各 Engine に DI する。
- **非同期の待機**: 「約定 (Fill) を待つか、注文送信 (Placed) だけで次に進むか」を、プロトコルのステップごとに定義する（定義書「裸売り時間をゼロにする」のため）。
