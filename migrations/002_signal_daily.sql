-- Phase 2: 日次信号（計器結論）保存。
-- NQ/GC 固定で、ICL/SCL/LCL と因子レベル（P,V,C,R,T,U,S）を 1 行に格納する。

CREATE TABLE IF NOT EXISTS signal_daily (
    as_of TEXT PRIMARY KEY,         -- ISO date "YYYY-MM-DD"
    scl INTEGER NOT NULL,
    lcl INTEGER NOT NULL,

    nq_icl INTEGER NOT NULL,
    gc_icl INTEGER NOT NULL,

    nq_p INTEGER NOT NULL,
    nq_v INTEGER NOT NULL,
    nq_c INTEGER NOT NULL,
    nq_r INTEGER NOT NULL,

    gc_p INTEGER NOT NULL,
    gc_v INTEGER NOT NULL,
    gc_c INTEGER NOT NULL,
    gc_r INTEGER NOT NULL,

    t INTEGER NOT NULL,
    u INTEGER NOT NULL,
    s INTEGER NOT NULL,

    created_at TEXT NOT NULL         -- ISO datetime
);

UPDATE schema_version SET version = 2;
