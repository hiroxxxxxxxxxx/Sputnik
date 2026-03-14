-- Phase 1: 基盤。スキーマバージョン用メタテーブルのみ。
-- 後続マイグレーションで state / mode / signal_daily 等を追加する。

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

INSERT INTO schema_version (version) VALUES (1);
