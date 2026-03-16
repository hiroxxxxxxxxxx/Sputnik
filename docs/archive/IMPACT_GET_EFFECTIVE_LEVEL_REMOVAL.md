# get_effective_level 廃止の影響確認（廃止済み）

**実施済み**: `FlightController.get_effective_level` は削除し、呼び出し元は `get_flight_controller_signal(symbol).throttle_level` に統一した。

以下は廃止前の影響確認メモ。

---

## 1. 呼び出し元一覧

| 場所 | 用途 | 対応方針 |
|------|------|----------|
| **src/cockpit/cockpit.py** L178 | `_pulse_subscription()` で銘柄ごとの実行レベルを取得し `_level_to_mode(level)` でモードに変換 | **get_flight_controller_signal(symbol).throttle_level** に置き換え可能。FC 内で既に `effective = max(ind, syn, lim)` を算出して Signal の throttle_level に入れている。 |
| **tests/avionics/test_avionics.py** | 複数テストで `av.get_effective_level("NQ")` を直接使用 | **get_flight_controller_signal("NQ").throttle_level** に変更するか、三層 getter（get_individual_control_level / get_synchronous_control_level / get_limit_control_level）と max で検証する形に変更。 |
| **tests/avionics/test_emergency.py** L80 | Mock が `get_effective_level(self, symbol)` を実装 | Cockpit が get_flight_controller_signal に変える場合、Mock は **get_flight_controller_signal(symbol)** を実装し、`.throttle_level = 2` 等を返すように変更。 |

---

## 2. 置き換えの根拠

- **get_flight_controller_signal(symbol, bundle=None)** が、内部で `ind, syn, lim` を取得し **effective = max(ind, syn, lim)** を計算し、**FlightControllerSignal.throttle_level** に格納している（flight_controller.py L300–309）。
- したがって「実行レベル（0/1/2）」は **get_flight_controller_signal(symbol).throttle_level** で取得可能。get_effective_level はこの計算の薄いラッパー。

---

## 3. 廃止時の変更案

### 3.1 cockpit/cockpit.py

```python
# 変更前
level = await self.fc.get_effective_level(engine.symbol_type)
target_mode = self._level_to_mode(level)

# 変更後
signal = await self.fc.get_flight_controller_signal(engine.symbol_type)
target_mode = self._level_to_mode(signal.throttle_level)
```

- `get_flight_controller_signal` は bundle 省略可（recovery_metrics が簡易になるだけ）。pulse では bundle なしで問題なし。

### 3.2 tests/avionics/test_avionics.py

- `av.get_effective_level("NQ")` → `(await av.get_flight_controller_signal("NQ")).throttle_level` に変更（async のため _run で実行）。
- または「effective = max(個別, 同期, 制限)」を検証するテストは、三層 getter をそれぞれ呼び max を assert する形に変更。

### 3.3 tests/avionics/test_emergency.py

- Mock: `get_effective_level` の代わりに **get_flight_controller_signal** を実装し、`throttle_level=2` の Signal を返す。

### 3.4 ドキュメント・docstring

- flight_controller.py / cockpit.py / cockpit/mode.py の「get_effective_level」言及を「get_flight_controller_signal(symbol).throttle_level」に合わせて修正。

---

## 4. まとめ

| 項目 | 内容 |
|------|------|
| **実装上の重複** | 実行レベルの計算は get_effective_level と get_flight_controller_signal の両方にある。廃止すると一箇所にまとまる。 |
| **呼び出し元** | 本番は Cockpit の 1 箇所のみ。テストが複数。 |
| **代替 API** | get_flight_controller_signal(symbol).throttle_level で同一値が得られる。 |
| **リスク** | 低。Signal 取得のコスト（raw_metrics / recovery_metrics 計算）は pulse でも許容範囲。 |

廃止する場合は上記のとおり Cockpit を get_flight_controller_signal に切り替え、テストを修正し、get_effective_level を削除すればよい。
