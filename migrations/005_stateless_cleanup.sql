-- Phase 5: stateless cleanup.
-- Remove state.effective_level and altitude_changes table.

DROP TABLE IF EXISTS altitude_changes;

CREATE TABLE IF NOT EXISTS state_new (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    altitude TEXT NOT NULL DEFAULT 'mid',
    altitude_changed_at TEXT,
    updated_at TEXT NOT NULL
);

INSERT INTO state_new (id, altitude, altitude_changed_at, updated_at)
SELECT id, altitude, altitude_changed_at, updated_at
FROM state;

DROP TABLE state;
ALTER TABLE state_new RENAME TO state;

UPDATE schema_version SET version = 5;
