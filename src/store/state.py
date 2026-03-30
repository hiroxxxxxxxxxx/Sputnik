"""
飛行状態（state テーブル）の読み書き。

state はシングルトン行（id=1）。高度変更時は altitude_changes にも履歴を追記する。
target_futures は part 別の目標先物枚数。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from avionics.data.signals import AltitudeRegime


def read_state(conn: sqlite3.Connection) -> dict:
    """state テーブルのシングルトン行を辞書で返す。"""
    row = conn.execute("SELECT * FROM state WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError("state row (id=1) not found. Run migrations first.")
    return dict(row)


def read_altitude_regime(conn: sqlite3.Connection) -> AltitudeRegime:
    """
    state.altitude を AltitudeRegime として返す。

    不正値・欠損時は ValueError（暗黙デフォルトは付与しない）。
    """
    raw = str(read_state(conn).get("altitude", "")).strip()
    if raw not in ("high", "mid", "low"):
        raise ValueError(f"Invalid state.altitude in DB: {raw!r}")
    return raw  # type: ignore[return-value]


def update_effective_level(conn: sqlite3.Connection, level: int) -> None:
    """effective_level を更新する。"""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE state SET effective_level = ?, updated_at = ? WHERE id = 1",
        (level, now),
    )
    conn.commit()


def update_altitude(
    conn: sqlite3.Connection,
    new_altitude: AltitudeRegime,
) -> None:
    """
    高度を変更し、altitude_changes に履歴を追記する。

    現在の高度と同じ場合は何もしない。
    """
    current = read_state(conn)
    old_altitude = current["altitude"]
    if old_altitude == new_altitude:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE state SET altitude = ?, altitude_changed_at = ?, updated_at = ? WHERE id = 1",
        (new_altitude, now, now),
    )
    conn.execute(
        "INSERT INTO altitude_changes (changed_at, from_altitude, to_altitude) VALUES (?, ?, ?)",
        (now, old_altitude, new_altitude),
    )
    conn.commit()


def read_altitude_changes(
    conn: sqlite3.Connection, limit: int = 50
) -> list[dict]:
    """altitude_changes の最新 N 件を返す（降順）。"""
    rows = conn.execute(
        "SELECT * FROM altitude_changes ORDER BY changed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def read_target_futures(conn: sqlite3.Connection) -> Dict[str, float]:
    """target_futures を {part_name: target_qty} 辞書で返す。"""
    rows = conn.execute("SELECT part_name, target_qty FROM target_futures").fetchall()
    return {r["part_name"]: r["target_qty"] for r in rows}


def upsert_target_futures(
    conn: sqlite3.Connection,
    part_name: str,
    target_qty: float,
) -> None:
    """target_futures に part 別の目標枚数を upsert する。"""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO target_futures (part_name, target_qty, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(part_name) DO UPDATE SET
            target_qty = excluded.target_qty,
            updated_at = excluded.updated_at
        """,
        (part_name, target_qty, now),
    )
    conn.commit()
