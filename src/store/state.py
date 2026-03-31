"""
飛行状態（state テーブル）の読み書き。

state はシングルトン行（id=1）。現在高度と target_futures を管理する。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Dict, Optional

from avionics.data.signals import AltitudeRegime
from .db import get_connection


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


def read_altitude_regime_from_db() -> AltitudeRegime:
    """DB 接続を内部で管理して altitude_regime を返す。"""
    conn = get_connection()
    try:
        return read_altitude_regime(conn)
    finally:
        conn.close()


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


def read_target_futures(conn: sqlite3.Connection) -> Dict[str, float]:
    """
    target_base_futures を {engine_symbol: base_qty} で返す。
    base_qty は MNQ/MGC 相当枚数。NQ/GC 行が揃わなければ ValueError。
    """
    rows = conn.execute(
        "SELECT symbol, base_qty FROM target_base_futures"
    ).fetchall()
    out: Dict[str, float] = {}
    for r in rows:
        sym = str(r["symbol"]).strip().upper()
        if sym in ("NQ", "GC"):
            out[sym] = float(r["base_qty"])
    missing = [sym for sym in ("NQ", "GC") if sym not in out]
    if missing:
        raise ValueError(f"target_base_futures missing rows: {missing}")
    return out


def read_target_futures_from_db() -> Dict[str, float]:
    """DB 接続を内部で管理して target_base_futures を返す。"""
    conn = get_connection()
    try:
        return read_target_futures(conn)
    finally:
        conn.close()


def upsert_target_futures(
    conn: sqlite3.Connection,
    engine_symbol: str,
    target_qty: float,
) -> None:
    """
    target_base_futures の 1 行を upsert する。target_qty は MNQ/MGC 相当枚数。
    """
    es = str(engine_symbol).strip().upper()
    if es not in ("NQ", "GC"):
        raise ValueError(f"engine_symbol must be NQ or GC, got {engine_symbol!r}")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO target_base_futures (symbol, base_qty, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            base_qty = excluded.base_qty,
            updated_at = excluded.updated_at
        """,
        (es, target_qty, now),
    )
    conn.commit()


def read_s_factor_baseline(conn: sqlite3.Connection) -> Dict[str, float]:
    """
    S因子の基準値（1枚あたりMM）を {symbol: mm_per_lot} で返す。
    NQ/GC 行が揃っていない場合は ValueError。
    """
    rows = conn.execute(
        "SELECT symbol, mm_per_lot FROM s_factor_baseline"
    ).fetchall()
    out: Dict[str, float] = {}
    for r in rows:
        sym = str(r["symbol"]).strip().upper()
        if sym in ("NQ", "GC"):
            out[sym] = float(r["mm_per_lot"])
    missing = [sym for sym in ("NQ", "GC") if sym not in out]
    if missing:
        raise ValueError(f"s_factor_baseline missing rows: {missing}")
    return out


def read_s_factor_baseline_from_db() -> Dict[str, float]:
    """DB 接続を内部で管理して s_factor_baseline を返す。"""
    conn = get_connection()
    try:
        return read_s_factor_baseline(conn)
    finally:
        conn.close()


def upsert_s_factor_baseline(
    conn: sqlite3.Connection,
    engine_symbol: str,
    mm_per_lot: float,
) -> None:
    """
    s_factor_baseline の 1 行を upsert する。
    """
    es = str(engine_symbol).strip().upper()
    if es not in ("NQ", "GC"):
        raise ValueError(f"engine_symbol must be NQ or GC, got {engine_symbol!r}")
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO s_factor_baseline (symbol, mm_per_lot, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            mm_per_lot = excluded.mm_per_lot,
            updated_at = excluded.updated_at
        """,
        (es, float(mm_per_lot), now),
    )
    conn.commit()
