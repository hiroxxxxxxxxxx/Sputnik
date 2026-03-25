-- Phase 2+: V 因子復帰（V1→V0）の 1h ノックイン監視日を銘柄ごとに記録する。
--
-- 監視が必要な日のみ (as_of, symbol) レコードを作り、ノックインしたら
-- knocked_in_bar_end に 1h 足の bar_end（datetime.isoformat() 文字列）を保存する。

CREATE TABLE IF NOT EXISTS knockin_watch (
    as_of TEXT NOT NULL,                 -- ISO date "YYYY-MM-DD"（NY セッション日）
    symbol TEXT NOT NULL,                -- "NQ" / "GC"
    knocked_in_bar_end TEXT,             -- PriceBar1h.bar_end.isoformat()（未成立なら NULL）
    created_at TEXT NOT NULL,            -- ISO datetime（作成時刻）
    PRIMARY KEY (as_of, symbol)
);

UPDATE schema_version SET version = 4;

