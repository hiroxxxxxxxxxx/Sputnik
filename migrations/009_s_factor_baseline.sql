-- Phase 9: S factor baseline (mm per lot) by symbol.

CREATE TABLE IF NOT EXISTS s_factor_baseline (
    symbol TEXT PRIMARY KEY,               -- NQ / GC
    mm_per_lot REAL NOT NULL,              -- baseline MM per 1 lot
    updated_at TEXT NOT NULL               -- ISO datetime
);

UPDATE schema_version SET version = 9;
