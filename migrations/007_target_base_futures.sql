-- target_futures(part別) を target_base_futures(symbol別 base) に最小化する。
-- 既存値は Main 行を base として移行する（Emergency Main-only 仕様に整合）。

CREATE TABLE IF NOT EXISTS target_base_futures (
    symbol TEXT PRIMARY KEY CHECK (symbol IN ('NQ', 'GC')),
    base_qty REAL NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO target_base_futures (symbol, base_qty, updated_at)
SELECT symbol, target_qty, updated_at
FROM target_futures
WHERE part_name = 'Main'
ON CONFLICT(symbol) DO UPDATE SET
    base_qty = excluded.base_qty,
    updated_at = excluded.updated_at;

UPDATE schema_version SET version = 7;
