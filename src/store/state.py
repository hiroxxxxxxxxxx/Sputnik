"""
飛行状態（state テーブル）の読み書き。

state はシングルトン行（id=1）。現在高度と target_futures を管理する。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from avionics.data.signals import AltitudeRegime
from engines.blueprint import PART_NAMES


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


def update_altitude(
    conn: sqlite3.Connection,
    new_altitude: AltitudeRegime,
) -> None:
    """高度を変更する。現在と同じ場合は何もしない。"""
    current = read_state(conn)
    old_altitude = current["altitude"]
    if old_altitude == new_altitude:
        return
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE state SET altitude = ?, altitude_changed_at = ?, updated_at = ? WHERE id = 1",
        (new_altitude, now, now),
    )
    conn.commit()


def read_target_futures(conn: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    """
    target_futures を {engine_symbol: {part_name: target_qty}} で返す。
    target_qty は MNQ/MGC 相当枚数（DB の symbol は NQ/GC）。全行が揃わなければ ValueError。
    """
    rows = conn.execute(
        "SELECT symbol, part_name, target_qty FROM target_futures"
    ).fetchall()
    engine_symbols = ("NQ", "GC")
    out: Dict[str, Dict[str, float]] = {s: {} for s in engine_symbols}
    for r in rows:
        sym = str(r["symbol"]).strip().upper()
        if sym not in engine_symbols:
            continue
        out[sym][str(r["part_name"])] = float(r["target_qty"])
    missing: list[str] = []
    for sym in engine_symbols:
        for p in PART_NAMES:
            if p not in out[sym]:
                missing.append(f"{sym}/{p}")
    if missing:
        raise ValueError(f"target_futures missing rows: {missing}")
    return out


def upsert_target_futures(
    conn: sqlite3.Connection,
    engine_symbol: str,
    part_name: str,
    target_qty: float,
) -> None:
    """
    target_futures の 1 行を upsert する。target_qty は MNQ/MGC 相当枚数。
    """
    es = str(engine_symbol).strip().upper()
    if es not in ("NQ", "GC"):
        raise ValueError(f"engine_symbol must be NQ or GC, got {engine_symbol!r}")
    if part_name not in PART_NAMES:
        raise ValueError(f"part_name must be one of {PART_NAMES}, got {part_name!r}")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO target_futures (symbol, part_name, target_qty, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(symbol, part_name) DO UPDATE SET
            target_qty = excluded.target_qty,
            updated_at = excluded.updated_at
        """,
        (es, part_name, target_qty, now),
    )
    conn.commit()
