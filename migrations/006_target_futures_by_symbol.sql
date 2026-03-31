-- target_futures にエンジン銘柄（NQ / GC）を追加し、複合 PK (symbol, part_name) とする。
-- 既存行は NQ / GC の双方へ同一値で複製する（従来の Part のみスキーマからの明示的移行）。

CREATE TABLE target_futures_new (
    symbol TEXT NOT NULL CHECK (symbol IN ('NQ', 'GC')),
    part_name TEXT NOT NULL CHECK (part_name IN ('Main', 'Attitude', 'Booster')),
    target_qty REAL NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (symbol, part_name)
);

INSERT INTO target_futures_new (symbol, part_name, target_qty, updated_at)
SELECT 'NQ', part_name, target_qty, updated_at FROM target_futures;

INSERT INTO target_futures_new (symbol, part_name, target_qty, updated_at)
SELECT 'GC', part_name, target_qty, updated_at FROM target_futures;

DROP TABLE target_futures;
ALTER TABLE target_futures_new RENAME TO target_futures;

UPDATE schema_version SET version = 6;
