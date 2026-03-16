# docs の構成

**ルート直下の位置づけ**

| ファイル | 役割 |
|----------|------|
| **SPEC.md**（ルート） | 戦略・運用の**正本**（マクロインカム戦略 完全運用定義書）。憲章・因子・制御構造のマスター。ここを最新にメンテする。 |
| **docs/spec/** | 実装レベルの**仕様・設計**。PHASE2 テーブル、注文処理・プロトコル階層（ARCHITECTURE）など。SPEC.md を具体化したもの。 |

| フォルダ | 用途 |
|----------|------|
| **spec/** | **最新の仕様としてメンテナンスするものだけ**。実装の参照元。照合結果・古い説明は置かない。 |
| **runbooks/** | 運用・環境構築手順（Docker 等）。 |
| **proposals/** | **検討中・メンテする提案だけ**。採用済み・見送り・古い案は archive。 |
| **plans/** | **進行中・メンテする実施計画だけ**。完了済み・レビュー結果・ドラフトは archive。 |
| **archive/** | 照合結果・テンポラリ・古い説明・完了済み計画・採用済み/見送り提案。履歴参照用。 |

## 各フォルダの主なファイル

- **spec:** PHASE2_TABLE_SPEC.md, ARCHITECTURE.md
- **runbooks:** DOCKER.md
- **proposals:** （検討中の提案のみ。空でも可）
- **plans:** SQLITE_IMPLEMENTATION_PLAN.md
- **archive:** DATA_FLOW_AND_DEPENDENCIES.md, LAYER_CHARTER_COMPLIANCE.md, SPEC_COMPLIANCE.md, AVIONICS_RESTRUCTURE_PLAN.md, LAYER4_SPEC_ALIGNMENT.md, SPEC_SECTION_1-3_DRAFT.md, SQLITE_DATA_SPEC_REVIEW.md, PROPOSAL_*.md, DATA_HIERARCHY_PROPOSAL.md, recovery_confirm_spec_options.md, IMPACT_GET_EFFECTIVE_LEVEL_REMOVAL.md, STATEFUL_AUDIT.md

新規ドキュメントは上記分類に従って配置する。仕様は spec、進行中計画は plans、検討中提案は proposals。完了・古い・照合結果は archive。
