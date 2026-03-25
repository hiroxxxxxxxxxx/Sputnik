"""
V 因子復帰（V1→V0）の 1h ノックイン監視日テーブル ``knockin_watch`` の読み書き。

監視が必要な日だけ (as_of, symbol) を作り、ノックインしたら bar_end 文字列を更新する。
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from typing import Optional


def create_watch(conn: sqlite3.Connection, *, as_of: date, symbol: str) -> None:
    """監視レコードを作成する（既にあれば no-op）。"""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO knockin_watch (as_of, symbol, knocked_in_bar_end, created_at)
        VALUES (?, ?, NULL, ?)
        """,
        (as_of.isoformat(), symbol, now),
    )
    conn.commit()


def set_knocked_in(
    conn: sqlite3.Connection,
    *,
    as_of: date,
    symbol: str,
    bar_end_iso: str,
) -> None:
    """ノックイン成立（何時足か）を保存する。"""
    conn.execute(
        """
        UPDATE knockin_watch
        SET knocked_in_bar_end = ?
        WHERE as_of = ? AND symbol = ?
        """,
        (bar_end_iso, as_of.isoformat(), symbol),
    )
    conn.commit()


def get_watch_row(
    conn: sqlite3.Connection,
    *,
    as_of: date,
    symbol: str,
) -> Optional[dict]:
    """監視レコードを返す。無ければ None。"""
    row = conn.execute(
        "SELECT * FROM knockin_watch WHERE as_of = ? AND symbol = ?",
        (as_of.isoformat(), symbol),
    ).fetchone()
    return dict(row) if row is not None else None


def list_pending_symbols(conn: sqlite3.Connection, *, as_of: date) -> list[str]:
    """当日 as_of のうち、未ノックインの監視対象 symbol を返す。"""
    rows = conn.execute(
        """
        SELECT symbol
        FROM knockin_watch
        WHERE as_of = ? AND knocked_in_bar_end IS NULL
        ORDER BY symbol
        """,
        (as_of.isoformat(),),
    ).fetchall()
    return [r["symbol"] for r in rows]

