-- Phase 2: state / mode / altitude_changes / target_futures テーブル。

-- state: 飛行状態のシングルトン行（id=1 固定）。
CREATE TABLE IF NOT EXISTS state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    effective_level INTEGER NOT NULL DEFAULT 0,
    altitude TEXT NOT NULL DEFAULT 'mid',      -- high / mid / low
    altitude_changed_at TEXT,                   -- ISO datetime（最後に高度を変更した日時）
    updated_at TEXT NOT NULL                    -- ISO datetime
);

INSERT OR IGNORE INTO state (id, effective_level, altitude, updated_at)
VALUES (1, 0, 'mid', datetime('now'));

-- altitude_changes: 高度変更履歴。
CREATE TABLE IF NOT EXISTS altitude_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    changed_at TEXT NOT NULL,                   -- ISO datetime
    from_altitude TEXT NOT NULL,                -- high / mid / low
    to_altitude TEXT NOT NULL                   -- high / mid / low
);

-- target_futures: part 別の目標先物枚数。運用開始時に設定し、ロール・リバランス時に見直す。
CREATE TABLE IF NOT EXISTS target_futures (
    part_name TEXT PRIMARY KEY,                 -- Main / Attitude / Booster
    target_qty REAL NOT NULL DEFAULT 0.0,
    updated_at TEXT NOT NULL                    -- ISO datetime
);

-- mode: 制御モードのシングルトン行（id=1 固定）。
CREATE TABLE IF NOT EXISTS mode (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    ap_mode TEXT NOT NULL DEFAULT 'Manual',     -- Manual / SemiAuto / Auto
    execution_lock INTEGER NOT NULL DEFAULT 0,  -- 0=OFF, 1=ON
    updated_at TEXT NOT NULL                    -- ISO datetime
);

INSERT OR IGNORE INTO mode (id, ap_mode, execution_lock, updated_at)
VALUES (1, 'Manual', 0, datetime('now'));

UPDATE schema_version SET version = 3;
