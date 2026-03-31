-- 旧スキーマの残骸テーブル target_futures を削除する。
-- 現行は target_base_futures を使用する。

DROP TABLE IF EXISTS target_futures;

UPDATE schema_version SET version = 8;
