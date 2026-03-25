"""
制御モード（mode テーブル）の読み書き。

mode はシングルトン行（id=1）。ap_mode（Manual/SemiAuto/Auto）と execution_lock（0/1）を保持。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from cockpit.mode import ApprovalMode


def read_mode(conn: sqlite3.Connection) -> dict:
    """mode テーブルのシングルトン行を辞書で返す。"""
    row = conn.execute("SELECT * FROM mode WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError("mode row (id=1) not found. Run migrations first.")
    return dict(row)


def update_ap_mode(conn: sqlite3.Connection, ap_mode: ApprovalMode) -> None:
    """ap_mode を更新する。"""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE mode SET ap_mode = ?, updated_at = ? WHERE id = 1",
        (ap_mode, now),
    )
    conn.commit()


def update_execution_lock(conn: sqlite3.Connection, locked: bool) -> None:
    """execution_lock フラグを更新する。"""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE mode SET execution_lock = ?, updated_at = ? WHERE id = 1",
        (1 if locked else 0, now),
    )
    conn.commit()
